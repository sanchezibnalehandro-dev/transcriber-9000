from __future__ import annotations

"""Strict JSON Lines transport for the local llama-helper process.

This module does not know about transcripts, report templates, Markdown, or
output files. Callers provide a complete model prompt and receive only the
non-empty ``response.text`` value or an explicit exception.
"""

import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any


DEFAULT_CONTEXT_SIZE = 16_384
DEFAULT_MAX_TOKENS = 2_200
DEFAULT_GENERATION_TIMEOUT_SECONDS = 3_600.0
DEFAULT_CONTROL_TIMEOUT_SECONDS = 5.0
_EOF = object()


class LlamaHelperError(RuntimeError):
    """Base error for helper startup, runtime, or generation failures."""


class LlamaHelperProtocolError(LlamaHelperError):
    """The helper violated the JSON Lines protocol."""


class LlamaHelperTimeoutError(LlamaHelperError, TimeoutError):
    """The helper did not return a response before the deadline."""


class LlamaHelperCancelledError(LlamaHelperError):
    """The active generation was cancelled and the helper was terminated."""


class LlamaHelperClient:
    """Own one llama-helper process and serialize requests to it."""

    def __init__(
        self,
        helper_path: str | os.PathLike[str],
        model_path: str | os.PathLike[str],
        *,
        context_size: int = DEFAULT_CONTEXT_SIZE,
        gpu_layers: int = 0,
        stderr_tail_lines: int = 200,
    ) -> None:
        self.helper_path = Path(helper_path).expanduser().resolve()
        self.model_path = Path(model_path).expanduser().resolve()
        if context_size <= 0:
            raise ValueError("context_size must be greater than zero")
        if gpu_layers < 0:
            raise ValueError("gpu_layers must not be negative")
        if stderr_tail_lines <= 0:
            raise ValueError("stderr_tail_lines must be greater than zero")

        self.context_size = context_size
        self.gpu_layers = gpu_layers
        self._stderr_tail: deque[str] = deque(maxlen=stderr_tail_lines)
        self._stdout_queue: queue.Queue[str | object] = queue.Queue()
        self._process: subprocess.Popen[str] | None = None
        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._active_generation = threading.Event()
        self._cancel_requested = threading.Event()

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._process is not None and self._process.poll() is None

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        with self._state_lock:
            return tuple(self._stderr_tail)

    def start(self) -> None:
        """Start the helper without loading the model."""
        with self._request_lock:
            if self.is_running:
                return
            self._validate_paths()
            self._start_unlocked()

    def ping(self, timeout: float = DEFAULT_CONTROL_TIMEOUT_SECONDS) -> None:
        """Check helper liveness while no generation is active."""
        with self._request_lock:
            response = self._request_unlocked({"type": "ping"}, timeout=timeout)
            self._expect_type(response, "pong")

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = DEFAULT_GENERATION_TIMEOUT_SECONDS,
        temperature: float = 0.2,
        top_k: int = 64,
        top_p: float = 0.9,
        presence_penalty: float = 0.0,
        frequency_penalty: float = 0.0,
        repeat_penalty: float = 1.0,
        penalty_last_n: int = 0,
        stop_tokens: tuple[str, ...] | list[str] = ("<|im_end|>",),
    ) -> str:
        """Generate from a complete prompt and return only response.text."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")

        request = {
            "type": "generate",
            "prompt": prompt,
            "model_path": str(self.model_path),
            "context_size": self.context_size,
            "gpu_layers": self.gpu_layers,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "repeat_penalty": repeat_penalty,
            "penalty_last_n": penalty_last_n,
            "stop_tokens": list(stop_tokens),
        }

        with self._request_lock:
            self._cancel_requested.clear()
            self._active_generation.set()
            try:
                response = self._request_unlocked(
                    request,
                    timeout=timeout,
                    cancellable=True,
                )
            finally:
                self._active_generation.clear()
                self._cancel_requested.clear()

        response_type = response.get("type")
        if response_type == "error":
            raise LlamaHelperError(self._error_message(response, "helper error"))
        if response_type != "response":
            raise LlamaHelperProtocolError(
                f"expected response, received {response_type!r}"
            )

        error = response.get("error")
        if error:
            raise LlamaHelperError(str(error))
        text = response.get("text")
        if not isinstance(text, str) or not text.strip():
            raise LlamaHelperProtocolError("helper returned an empty response.text")
        return text

    def cancel(self) -> bool:
        """Request cancellation of the active generation.

        The helper is synchronous, so cancellation terminates the process to
        prevent a late response from desynchronizing the JSONL stream.
        """
        if not self._active_generation.is_set():
            return False
        self._cancel_requested.set()
        return True

    def shutdown(self, timeout: float = 3.0) -> None:
        """Request graceful shutdown, then terminate if it does not exit."""
        with self._request_lock:
            if not self.is_running:
                self._clear_process_reference()
                return
            try:
                response = self._request_unlocked({"type": "shutdown"}, timeout=timeout)
                self._expect_type(response, "goodbye")
                process = self._get_process()
                if process is not None:
                    try:
                        process.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        self._abort_process()
                        raise LlamaHelperTimeoutError(
                            "helper acknowledged shutdown but did not exit"
                        )
            except LlamaHelperError:
                self._abort_process()
                raise
            finally:
                self._clear_process_reference()

    def _validate_paths(self) -> None:
        if not self.helper_path.is_file():
            raise LlamaHelperError(f"helper executable not found: {self.helper_path}")
        if not self.model_path.is_file():
            raise LlamaHelperError(f"GGUF model not found: {self.model_path}")

    def _start_unlocked(self) -> None:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        stdout_queue: queue.Queue[str | object] = queue.Queue()
        stderr_tail: deque[str] = deque(maxlen=self._stderr_tail.maxlen)
        try:
            process = subprocess.Popen(
                [str(self.helper_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as error:
            raise LlamaHelperError(f"failed to start helper: {error}") from error

        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.kill()
            raise LlamaHelperError("failed to open helper pipes")

        with self._state_lock:
            self._process = process
            self._stdout_queue = stdout_queue
            self._stderr_tail = stderr_tail

        threading.Thread(
            target=self._read_stdout,
            args=(process, stdout_queue),
            name="llama-helper-stdout",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr,
            args=(process, stderr_tail),
            name="llama-helper-stderr",
            daemon=True,
        ).start()

    @staticmethod
    def _read_stdout(
        process: subprocess.Popen[str],
        destination: queue.Queue[str | object],
    ) -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                destination.put(line.rstrip("\r\n"))
        finally:
            destination.put(_EOF)

    @staticmethod
    def _read_stderr(
        process: subprocess.Popen[str],
        destination: deque[str],
    ) -> None:
        assert process.stderr is not None
        for line in process.stderr:
            destination.append(line.rstrip("\r\n"))

    def _request_unlocked(
        self,
        payload: dict[str, Any],
        *,
        timeout: float,
        cancellable: bool = False,
    ) -> dict[str, Any]:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        process = self._get_process()
        if process is None or process.poll() is not None or process.stdin is None:
            raise LlamaHelperError("helper is not running")

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        try:
            process.stdin.write(encoded + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            self._abort_process()
            raise LlamaHelperError(
                f"failed to write request to helper: {error}{self._diagnostic_suffix()}"
            ) from error

        deadline = time.monotonic() + timeout
        while True:
            if cancellable and self._cancel_requested.is_set():
                self._abort_process()
                raise LlamaHelperCancelledError("generation cancelled")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._abort_process()
                raise LlamaHelperTimeoutError(
                    f"helper response timed out after {timeout:.1f} seconds"
                )

            try:
                item = self._stdout_queue.get(timeout=min(0.1, remaining))
            except queue.Empty:
                continue

            if item is _EOF:
                return_code = process.poll()
                self._abort_process()
                raise LlamaHelperProtocolError(
                    "helper stdout closed before a response "
                    f"(exit_code={return_code}){self._diagnostic_suffix()}"
                )
            if not isinstance(item, str) or not item:
                self._abort_process()
                raise LlamaHelperProtocolError("helper emitted an empty stdout line")

            try:
                response = json.loads(item)
            except json.JSONDecodeError as error:
                self._abort_process()
                raise LlamaHelperProtocolError(
                    f"helper emitted non-JSON stdout: {item!r}{self._diagnostic_suffix()}"
                ) from error
            if not isinstance(response, dict) or not isinstance(response.get("type"), str):
                self._abort_process()
                raise LlamaHelperProtocolError(
                    f"helper emitted an invalid response object: {response!r}"
                )
            return response

    def _expect_type(self, response: dict[str, Any], expected: str) -> None:
        response_type = response.get("type")
        if response_type == "error":
            raise LlamaHelperError(self._error_message(response, "helper error"))
        if response_type != expected:
            raise LlamaHelperProtocolError(
                f"expected {expected!r}, received {response_type!r}"
            )

    @staticmethod
    def _error_message(response: dict[str, Any], fallback: str) -> str:
        message = response.get("message")
        return str(message) if message else fallback

    def _get_process(self) -> subprocess.Popen[str] | None:
        with self._state_lock:
            return self._process

    def _clear_process_reference(self) -> None:
        with self._state_lock:
            self._process = None

    def _abort_process(self) -> None:
        process = self._get_process()
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        self._clear_process_reference()

    def _diagnostic_suffix(self) -> str:
        lines = self.stderr_tail
        if not lines:
            return ""
        return "\nhelper stderr tail:\n" + "\n".join(lines[-20:])


__all__ = [
    "DEFAULT_CONTEXT_SIZE",
    "DEFAULT_GENERATION_TIMEOUT_SECONDS",
    "DEFAULT_MAX_TOKENS",
    "LlamaHelperCancelledError",
    "LlamaHelperClient",
    "LlamaHelperError",
    "LlamaHelperProtocolError",
    "LlamaHelperTimeoutError",
]
