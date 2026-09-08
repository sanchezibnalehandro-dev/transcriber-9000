from __future__ import annotations

import multiprocessing

multiprocessing.freeze_support()

import json
import os
import subprocess
import sys


WORKER_FLAG = "--io-gate-worker"


def run_worker() -> int:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps({"status": "ok", "message": "прогресс"}, ensure_ascii=False), flush=True)
    print("worker-stderr: проверка", file=sys.stderr, flush=True)
    return 0


def run_parent() -> int:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, WORKER_FLAG],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
    passed = (
        completed.returncode == 0
        and '"message": "прогресс"' in completed.stdout
        and "worker-stderr: проверка" in completed.stderr
    )
    result = {
        "passed": passed,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "parent_stdout_is_none": sys.stdout is None,
        "parent_stderr_is_none": sys.stderr is None,
    }
    with open("io-gate-result.json", "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    return 0 if passed else 1


def main() -> int:
    if WORKER_FLAG in sys.argv[1:]:
        return run_worker()
    return run_parent()


if __name__ == "__main__":
    raise SystemExit(main())
