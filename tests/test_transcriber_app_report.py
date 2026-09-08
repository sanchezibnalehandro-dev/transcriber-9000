from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import transcriber_app as gui


class ReportCommandTests(unittest.TestCase):
    def test_command_uses_absolute_runtime_paths_and_backend_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python_exe = root / "venv" / "python.exe"
            transcript = root / "output" / "meeting.txt"
            pipeline = root / "report_pipeline.py"
            template = root / "report_templates" / "product_meeting.json"
            model = root / "models" / "Qwen_Qwen3.5-9B-Q4_K_M.gguf"
            helper = root / ".cache" / "llama-helper-cuda" / "release" / "llama-helper.exe"
            with mock.patch.multiple(
                gui,
                REPORT_PIPELINE_PATH=pipeline,
                REPORT_TEMPLATE_PATH=template,
                REPORT_CUDA_HELPER_PATH=helper,
            ):
                command = gui.build_report_command(transcript, "cuda", python_exe, model)

        self.assertEqual(command[0], str(python_exe.resolve()))
        self.assertEqual(command[3], str(pipeline.resolve()))
        self.assertEqual(command[command.index("--transcript") + 1], str(transcript.resolve()))
        self.assertEqual(command[command.index("--template") + 1], str(template.resolve()))
        self.assertEqual(command[command.index("--helper") + 1], str(helper.resolve()))
        self.assertEqual(command[command.index("--model") + 1], str(model.resolve()))
        self.assertEqual(command[-2:], ["--device", "cuda"])
        for backend_default in ("--context-size", "--max-tokens", "--temperature", "--top-p"):
            self.assertNotIn(backend_default, command)

    def test_invalid_device_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            gui.report_helper_path("auto")

    def test_runtime_requires_all_fixed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / "report_pipeline.py", root / "product_meeting.json", root / "model.gguf", root / "cuda-helper.exe", root / "cpu-helper.exe"]
            for path in paths:
                path.write_bytes(b"x")
            with mock.patch.multiple(
                gui,
                REPORT_PIPELINE_PATH=paths[0],
                REPORT_TEMPLATE_PATH=paths[1],
                REPORT_CUDA_HELPER_PATH=paths[3],
                REPORT_CPU_HELPER_PATH=paths[4],
            ), mock.patch.object(gui, "active_report_model_path", return_value=paths[2]):
                with mock.patch.object(gui, "resolve_cuda_runtime_bin", return_value=root):
                    self.assertTrue(gui.report_runtime_available("cuda"))
                    self.assertTrue(gui.report_runtime_available("cpu"))
                    paths[3].unlink()
                    self.assertFalse(gui.report_runtime_available("cuda"))
                    self.assertTrue(gui.report_runtime_available("cpu"))

    def test_srt_only_result_has_no_report_source(self) -> None:
        self.assertIsNone(gui.first_txt_result([Path("meeting.srt")]))
        self.assertEqual(gui.first_txt_result([Path("meeting.srt"), Path("meeting.TXT")]), Path("meeting.TXT"))

    def test_cuda_environment_prepends_resolved_runtime_dll_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cuda_bin = Path(temporary) / "bin"
            cuda_bin.mkdir()
            for name in gui.CUDA_RUNTIME_DLLS:
                (cuda_bin / name).write_bytes(b"dll")
            environment = {"CUDA_PATH": temporary, "PATH": r"C:\Windows\System32"}
            result = gui.build_report_environment("cuda", environment)
        self.assertEqual(result["PATH"].split(gui.os.pathsep)[0], str(cuda_bin.resolve()))
        self.assertEqual(result["PYTHONIOENCODING"], "utf-8")

    def test_cuda_runtime_is_unavailable_when_required_dlls_cannot_be_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("pipeline.py", "template.json", "model.gguf", "helper.exe")]
            for path in paths:
                path.write_bytes(b"x")
            with (
                mock.patch.multiple(
                    gui,
                    REPORT_PIPELINE_PATH=paths[0],
                    REPORT_TEMPLATE_PATH=paths[1],
                    REPORT_CUDA_HELPER_PATH=paths[3],
                ),
                mock.patch.object(gui, "active_report_model_path", return_value=paths[2]),
                mock.patch.object(gui, "resolve_cuda_runtime_bin", return_value=None),
            ):
                self.assertFalse(gui.report_runtime_available("cuda"))


class FlowHarness:
    def __init__(self) -> None:
        self.report_transcript_path: Path | None = None
        self.report_output_path: Path | None = None
        self.report_action: str | None = None
        self.active_report_device: str | None = None
        self.created_result_paths: list[Path] = []
        self.started: list[str] = []
        self.actions: list[tuple[str, str]] = []
        self.statuses: list[str] = []
        self.logs: list[str] = []
        self.render_count = 0
        self.rendered_states: list[tuple[gui.UIState, str]] = []
        self.drop_signal = SimpleNamespace(configure=lambda **_kwargs: None)

    def hide_report_action(self) -> None:
        self.report_action = None

    def show_report_action(self, text: str, action: str) -> None:
        self.report_action = action
        self.actions.append((text, action))

    def start_report(self, device: str) -> None:
        self.started.append(device)

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def append_log(self, text: str) -> None:
        self.logs.append(text)

    def render_result_files(self) -> None:
        self.render_count += 1

    def render_ui_state(self, state: gui.UIState, detail: str = "") -> None:
        self.rendered_states.append((state, detail))


class ReportFlowTests(unittest.TestCase):
    def test_txt_completion_starts_cuda_automatically(self) -> None:
        harness = FlowHarness()
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "meeting.txt"
            transcript.write_text("meeting", encoding="utf-8")
            report = Path(temporary) / "meeting--product-meeting.md"
            with (
                mock.patch.object(gui, "expected_report_path", return_value=report),
                mock.patch.object(gui, "active_report_model_path", return_value=Path(temporary) / "model.gguf"),
                mock.patch.object(gui, "report_runtime_available", side_effect=lambda device: device == "cuda"),
            ):
                gui.Transcriber9000App.prepare_report_for_transcript(harness, transcript)
        self.assertEqual(harness.started, ["cuda"])
        self.assertEqual(harness.actions, [])

    def test_cpu_only_requires_explicit_action(self) -> None:
        harness = FlowHarness()
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "meeting.txt"
            transcript.write_text("meeting", encoding="utf-8")
            report = Path(temporary) / "meeting--product-meeting.md"
            with (
                mock.patch.object(gui, "expected_report_path", return_value=report),
                mock.patch.object(gui, "active_report_model_path", return_value=Path(temporary) / "model.gguf"),
                mock.patch.object(gui, "report_runtime_available", side_effect=lambda device: device == "cpu"),
            ):
                gui.Transcriber9000App.prepare_report_for_transcript(harness, transcript)
        self.assertEqual(harness.started, [])
        self.assertEqual(harness.actions[-1], ("Создать AI-отчёт на CPU", "start_cpu"))
        self.assertEqual(harness.rendered_states[-1][0], gui.UIState.CPU_FALLBACK)

    def test_existing_report_is_opened_without_generation(self) -> None:
        harness = FlowHarness()
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "meeting.txt"
            transcript.write_text("meeting", encoding="utf-8")
            report = Path(temporary) / "meeting--product-meeting.md"
            report.write_text("# report", encoding="utf-8")
            with (
                mock.patch.object(gui, "expected_report_path", return_value=report),
                mock.patch.object(gui, "report_runtime_available") as runtime,
            ):
                gui.Transcriber9000App.prepare_report_for_transcript(harness, transcript)
        self.assertEqual(harness.started, [])
        runtime.assert_not_called()
        self.assertEqual(harness.actions[-1], ("Открыть AI-отчёт", "open"))
        self.assertEqual(harness.report_output_path, report.resolve())
        self.assertEqual(harness.rendered_states[-1][0], gui.UIState.READY)

    def test_cuda_error_offers_cpu_retry_and_preserves_transcript(self) -> None:
        harness = FlowHarness()
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "meeting.txt"
            transcript.write_text("original transcript", encoding="utf-8")
            harness.report_transcript_path = transcript
            before = transcript.read_bytes()
            with mock.patch.object(
                gui, "report_runtime_available", side_effect=lambda device: device == "cpu"
            ):
                gui.Transcriber9000App.finish_report_error(harness, "cuda", "CUDA runtime error")
            after = transcript.read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(harness.started, [])
        self.assertEqual(harness.actions[-1], ("Повторить на CPU", "retry_cpu"))
        self.assertEqual(harness.rendered_states[-1][0], gui.UIState.REPORT_ERROR)
        self.assertEqual(harness.rendered_states[-1][1], "CUDA runtime error")

    def test_successful_result_uses_pipeline_output_path(self) -> None:
        harness = FlowHarness()
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.md"
            report.write_text("# report", encoding="utf-8")
            stdout = json.dumps({"output_path": str(report)}, ensure_ascii=False)
            gui.Transcriber9000App.finish_report(harness, 0, stdout, "")
        self.assertEqual(harness.report_output_path, report.resolve())
        self.assertEqual(harness.actions[-1], ("Открыть AI-отчёт", "open"))
        self.assertEqual(harness.rendered_states[-1][0], gui.UIState.READY)


class FinishTranscriptionHarness:
    def __init__(self, result_json: Path) -> None:
        self.result_json = result_json
        self.log_is_open = False
        self.created_result_paths: list[Path] = []
        self.report_prepared_for: list[Path] = []
        self.hide_count = 0
        self.statuses: list[str] = []
        self.logs: list[str] = []
        self.rendered_states: list[tuple[gui.UIState, str]] = []
        self.result_frame = SimpleNamespace(grid=lambda **_kwargs: None)
        self.drop_signal = SimpleNamespace(configure=lambda **_kwargs: None)

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def append_log(self, text: str) -> None:
        self.logs.append(text)

    def toggle_log(self) -> None:
        raise AssertionError("closed log must stay closed")

    def render_result_files(self) -> None:
        pass

    def refresh_environment(self) -> None:
        pass

    def prepare_report_for_transcript(self, transcript: Path) -> None:
        self.report_prepared_for.append(transcript)

    def hide_report_action(self) -> None:
        self.hide_count += 1

    def show_transcription_error(self, text: str) -> None:
        raise AssertionError(text)

    def render_ui_state(self, state: gui.UIState, detail: str = "") -> None:
        self.rendered_states.append((state, detail))


class TranscriptionHandoffTests(unittest.TestCase):
    def test_successful_txt_result_enters_report_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = root / "meeting.txt"
            transcript.write_text("meeting", encoding="utf-8")
            result_json = root / "result.json"
            result_json.write_text(
                json.dumps({"success": True, "created_files": [str(transcript)]}), encoding="utf-8"
            )
            harness = FinishTranscriptionHarness(result_json)
            gui.Transcriber9000App.finish_transcription(harness, 0)
        self.assertEqual(harness.report_prepared_for, [transcript.resolve()])
        self.assertEqual(harness.hide_count, 0)
        self.assertEqual(harness.rendered_states, [(gui.UIState.REPORT_STARTING, "")])

    def test_successful_srt_only_result_has_no_report_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subtitle = root / "meeting.srt"
            subtitle.write_text("subtitle", encoding="utf-8")
            result_json = root / "result.json"
            result_json.write_text(
                json.dumps({"success": True, "created_files": [str(subtitle)]}), encoding="utf-8"
            )
            harness = FinishTranscriptionHarness(result_json)
            gui.Transcriber9000App.finish_transcription(harness, 0)
        self.assertEqual(harness.report_prepared_for, [])
        self.assertEqual(harness.hide_count, 1)
        self.assertEqual(harness.rendered_states[-1][0], gui.UIState.READY)


class ProcessHarness:
    def __init__(self, transcript: Path) -> None:
        self.active_process = None
        self.active_process_kind = None
        self.active_report_device = None
        self.report_transcript_path = transcript
        self.report_action = None
        self.busy_calls: list[tuple[bool, str]] = []
        self.statuses: list[str] = []
        self.logs: list[str] = []
        self.rendered_states: list[tuple[gui.UIState, str]] = []
        self.progress = SimpleNamespace(configure=lambda **_kwargs: None, start=lambda: None)

    def hide_report_action(self) -> None:
        self.report_action = None

    def set_busy(self, busy: bool, operation: str = "transcription") -> None:
        self.busy_calls.append((busy, operation))

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def append_log(self, text: str) -> None:
        self.logs.append(text)

    def finish_report_error(self, _device: str, detail: str) -> None:
        raise AssertionError(detail)

    def render_ui_state(self, state: gui.UIState, detail: str = "") -> None:
        self.rendered_states.append((state, detail))


class ReportProcessTests(unittest.TestCase):
    def test_report_runs_in_background_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "meeting.txt"
            transcript.write_text("meeting", encoding="utf-8")
            harness = ProcessHarness(transcript)
            process = SimpleNamespace(pid=1234)
            with (
                mock.patch.object(gui, "report_runtime_available", return_value=True),
                mock.patch.object(gui, "build_report_command", return_value=["runtime.exe", "report_pipeline.py"]),
                mock.patch.object(gui.subprocess, "Popen", return_value=process) as popen,
            ):
                gui.Transcriber9000App.start_report(harness, "cuda")
        self.assertIs(harness.active_process, process)
        self.assertEqual(harness.active_process_kind, "report")
        self.assertEqual(harness.active_report_device, "cuda")
        self.assertEqual(harness.busy_calls, [(True, "report")])
        self.assertEqual(harness.rendered_states[-1][0], gui.UIState.REPORT_GENERATING)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.kwargs["cwd"], gui.APP_ROOT)
        self.assertEqual(popen.call_args.kwargs["stdout"], gui.subprocess.PIPE)
        self.assertEqual(popen.call_args.kwargs["stderr"], gui.subprocess.PIPE)

    def test_close_kills_report_process_tree_on_windows(self) -> None:
        process = SimpleNamespace(pid=4321, poll=lambda: None)
        harness = SimpleNamespace(
            active_process=process,
            active_process_kind="report",
            destroy=mock.Mock(),
        )
        with (
            mock.patch.object(gui.messagebox, "askyesno", return_value=True),
            mock.patch.object(gui.subprocess, "run") as run,
            mock.patch.object(gui.os, "name", "nt"),
        ):
            gui.Transcriber9000App.on_close(harness)
        command = run.call_args.args[0]
        self.assertEqual(command, ["taskkill", "/PID", "4321", "/T", "/F"])
        harness.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
