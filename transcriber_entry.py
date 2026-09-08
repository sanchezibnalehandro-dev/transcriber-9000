from __future__ import annotations

import multiprocessing

multiprocessing.freeze_support()

import sys


def _configure_worker_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def run_worker(worker_name: str, argv: list[str]) -> int:
    _configure_worker_streams()
    if worker_name == "transcription":
        from transcriber_core import main as transcription_main

        return transcription_main(argv)
    if worker_name == "report":
        from report_pipeline import ReportPipelineError, main as report_main

        try:
            return report_main(argv)
        except (ReportPipelineError, ValueError) as error:
            if sys.stderr is not None:
                print(f"Ошибка: {error}", file=sys.stderr, flush=True)
            return 2
    if sys.stderr is not None:
        print(f"Неизвестный worker: {worker_name}", file=sys.stderr, flush=True)
    return 2


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["--worker"]:
        if len(arguments) < 2:
            _configure_worker_streams()
            if sys.stderr is not None:
                print("После --worker требуется transcription или report", file=sys.stderr, flush=True)
            return 2
        return run_worker(arguments[1], arguments[2:])

    from transcriber_app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
