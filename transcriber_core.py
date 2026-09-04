from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


APP_DIR = Path(__file__).resolve().parent
INPUT_DIR = APP_DIR / "input"
OUTPUT_DIR = APP_DIR / "output"
CACHE_DIR = APP_DIR / ".cache" / "whisper"
VENV_PYTHON = APP_DIR / ".venv" / "Scripts" / "python.exe"
FFMPEG_DIR = APP_DIR / "tools" / "ffmpeg" / "bin"
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"

APP_TITLE = "Транскрибатор 9000"

LANGUAGE_OPTIONS = {
    "ru": "русский",
    "auto": "определить автоматически",
}

QUALITY_OPTIONS = {
    "fast": ("быстро", "tiny"),
    "balanced": ("оптимально", "base"),
    "best": ("высокое качество", "small"),
    "premium": ("премиум", "medium"),
    "maximum": ("максимум", "large-v3"),
}

MODEL_DOWNLOAD_URLS = {
    "tiny": "https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt",
    "base": "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5e0b6b1c0edf879ad9b11b1af5a0e6/base.pt",
    "small": "https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt",
    "medium": "https://openaipublic.azureedge.net/main/whisper/models/345ae4da62d5c06ac4d443766030b323e176523a8a8b0071a2a3b30be8b2f9a9/medium.pt",
    "large-v3": "https://openaipublic.azureedge.net/main/whisper/models/e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb/large-v3.pt",
}

MODEL_INFO = {
    "tiny": {
        "size_mb": 72,
        "summary": "самый быстрый старт, качество ниже",
        "recommendation": "для черновиков и коротких проверок",
    },
    "base": {
        "size_mb": 139,
        "summary": "быстро и заметно точнее tiny",
        "recommendation": "хороший минимум для публичной версии",
    },
    "small": {
        "size_mb": 461,
        "summary": "лучше слышит речь, медленнее base",
        "recommendation": "режим для большинства задач",
    },
    "medium": {
        "size_mb": 1458,
        "summary": "сильный рабочий режим, лучше на GPU",
        "recommendation": "для важных записей и длинных материалов",
    },
    "large-v3": {
        "size_mb": 2945,
        "summary": "максимальное качество, очень долго без GPU",
        "recommendation": "для финальной расшифровки, когда важна точность",
    },
}

FORMAT_OPTIONS = {
    "txt": "TXT",
    "srt": "SRT с таймкодами",
}

if FFMPEG_DIR.exists():
    os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")


class UserVisibleError(Exception):
    """An expected error that can be shown directly to a non-technical user."""


@dataclass(frozen=True)
class TranscriptionRequest:
    source: Path
    language_key: str
    quality_key: str
    formats: tuple[str, ...]

    @property
    def model_name(self) -> str:
        return QUALITY_OPTIONS[self.quality_key][1]

    @property
    def quality_label(self) -> str:
        return QUALITY_OPTIONS[self.quality_key][0]


def is_inside_input(path: Path) -> bool:
    try:
        path.resolve().relative_to(INPUT_DIR.resolve())
        return True
    except ValueError:
        return False


def expected_outputs(source: Path, formats: Iterable[str]) -> dict[str, Path]:
    return {fmt: OUTPUT_DIR / f"{source.stem}.{fmt}" for fmt in formats}


def validate_request(request: TranscriptionRequest) -> dict[str, Path]:
    source = request.source.resolve()

    if not INPUT_DIR.exists():
        raise UserVisibleError(
            f"Папка input не найдена:\n{INPUT_DIR}\n\n"
            "Причина: приложение берет исходные аудио и видео только из этой папки."
        )

    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not source.exists() or not source.is_file():
        raise UserVisibleError(
            f"Файл не найден:\n{source}\n\n"
            "Причина: выбранный файл больше недоступен."
        )

    if not is_inside_input(source):
        raise UserVisibleError(
            f"Выбран файл не из папки input:\n{source}\n\n"
            f"Причина: по правилам проекта исходные материалы можно брать только из:\n{INPUT_DIR}\n\n"
            "Что сделать: положите аудио или видео в папку input и выберите его оттуда."
        )

    if not request.formats:
        raise UserVisibleError("Не выбран формат результата.\n\nЧто сделать: отметьте TXT, SRT или оба формата.")

    unknown_formats = [fmt for fmt in request.formats if fmt not in FORMAT_OPTIONS]
    if unknown_formats:
        raise UserVisibleError(f"Неизвестный формат результата: {', '.join(unknown_formats)}")

    if request.language_key not in LANGUAGE_OPTIONS:
        raise UserVisibleError("Неизвестный режим языка. Выберите русский или автоопределение.")

    if request.quality_key not in QUALITY_OPTIONS:
        raise UserVisibleError("Неизвестный режим качества. Выберите режим заново.")

    if not FFMPEG_EXE.exists():
        raise UserVisibleError(
            f"Не найден локальный ffmpeg:\n{FFMPEG_EXE}\n\n"
            "Причина: Whisper не сможет прочитать аудио или видео без ffmpeg."
        )

    model_state = get_model_file_state(request.model_name)
    model_path = model_state["path"]
    if not model_state["installed"]:
        reason = "файл модели отсутствует" if not Path(model_path).exists() else "файл модели выглядит неполным или поврежденным"
        raise UserVisibleError(
            f"Для режима «{request.quality_label}» не найдена локальная модель Whisper:\n{model_path}\n\n"
            f"Причина: {reason}.\n"
            "Что сделать: откройте раздел «Сервис» и скачайте нужную модель заново."
        )

    outputs = expected_outputs(source, request.formats)
    conflicts = [path for path in outputs.values() if path.exists()]
    if conflicts:
        conflict_list = "\n".join(str(path) for path in conflicts)
        raise UserVisibleError(
            "Результат уже существует, поэтому перезапись остановлена:\n"
            f"{conflict_list}\n\n"
            "Ничего не перезаписано. Что сделать: переименуйте исходный файл или вручную уберите старый результат."
        )

    return outputs


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(path: Path, segments: Iterable[dict]) -> None:
    blocks: list[str] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        start = format_srt_timestamp(float(segment.get("start", 0.0)))
        end = format_srt_timestamp(float(segment.get("end", 0.0)))
        blocks.append(f"{len(blocks) + 1}\n{start} --> {end}\n{text}")

    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")


def append_status(path: Path | None, message: str) -> None:
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(message.rstrip() + "\n")


def write_result_json(path: Path | None, payload: dict) -> None:
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_torch_device_label() -> tuple[str, str]:
    try:
        import torch
    except Exception:
        return "cpu", "CPU"

    if torch.cuda.is_available():
        try:
            return "cuda", f"GPU: {torch.cuda.get_device_name(0)}"
        except Exception:
            return "cuda", "GPU: CUDA"

    return "cpu", "CPU"


def get_model_file_state(model_name: str) -> dict:
    path = CACHE_DIR / f"{model_name}.pt"
    expected_bytes = int(MODEL_INFO[model_name]["size_mb"] * 1024 * 1024)
    bytes_count = path.stat().st_size if path.exists() else 0
    installed = path.exists() and bytes_count >= int(expected_bytes * 0.9)
    damaged = path.exists() and not installed
    return {
        "path": path,
        "bytes": bytes_count,
        "installed": installed,
        "damaged": damaged,
    }


def get_model_status() -> list[dict]:
    status: list[dict] = []
    for quality_key, (quality_label, model_name) in QUALITY_OPTIONS.items():
        info = MODEL_INFO[model_name]
        state = get_model_file_state(model_name)
        status.append(
            {
                "quality_key": quality_key,
                "quality_label": quality_label,
                "model": model_name,
                "path": str(state["path"]),
                "installed": state["installed"],
                "damaged": state["damaged"],
                "bytes": state["bytes"],
                "size_mb": info["size_mb"],
                "summary": info["summary"],
                "recommendation": info["recommendation"],
                "download_url": MODEL_DOWNLOAD_URLS[model_name],
            }
        )
    return status


def check_environment() -> dict:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    checks = []

    def add_check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add_check("input", INPUT_DIR.exists(), str(INPUT_DIR))
    add_check("output", OUTPUT_DIR.exists(), str(OUTPUT_DIR))
    add_check("venv python", VENV_PYTHON.exists(), str(VENV_PYTHON))
    add_check("ffmpeg", FFMPEG_EXE.exists(), str(FFMPEG_EXE))

    try:
        import whisper  # noqa: F401

        add_check("whisper", True, "локальный Whisper доступен")
    except Exception as exc:
        add_check("whisper", False, str(exc))

    device, device_label = get_torch_device_label()
    models = get_model_status()
    required_ok = all(check["ok"] for check in checks)

    return {
        "app": APP_TITLE,
        "app_dir": str(APP_DIR),
        "input": str(INPUT_DIR),
        "output": str(OUTPUT_DIR),
        "cache": str(CACHE_DIR),
        "device": device,
        "device_label": device_label,
        "checks": checks,
        "models": models,
        "ready": required_ok,
        "installed_models": [model["model"] for model in models if model["installed"]],
        "missing_models": [model["model"] for model in models if not model["installed"]],
    }


def transcribe_file(
    request: TranscriptionRequest,
    status_callback: Callable[[str], None] | None = None,
) -> list[Path]:
    def status(message: str) -> None:
        if status_callback:
            status_callback(message)

    outputs = validate_request(request)

    device, device_label = get_torch_device_label()
    status(f"STATUS: Загружаю локальную модель Whisper: {request.model_name} ({device_label})")
    try:
        import whisper
    except Exception as exc:
        raise UserVisibleError(
            "Не удалось подключить локальный Whisper.\n\n"
            f"Причина: {exc}\n"
            "Что сделать: запускайте приложение через «Транскрибатор 9000.cmd», чтобы использовалась папка .venv."
        ) from exc

    model = whisper.load_model(request.model_name, device=device, download_root=str(CACHE_DIR))

    status("STATUS: Распознаю речь. Окно можно оставить открытым, оно не зависло.")
    options = {
        "task": "transcribe",
        "fp16": device == "cuda",
        "verbose": False,
    }
    if request.language_key == "ru":
        options["language"] = "ru"

    try:
        result = model.transcribe(str(request.source.resolve()), **options)
    except Exception as exc:
        raise UserVisibleError(
            "Не удалось расшифровать файл.\n\n"
            f"Причина: {exc}\n"
            "Что сделать: проверьте, что файл является аудио или видео и не поврежден."
        ) from exc

    status("STATUS: Сохраняю результаты в папку output.")
    created: list[Path] = []
    if "txt" in outputs:
        text = str(result.get("text", "")).strip()
        outputs["txt"].write_text(text + ("\n" if text else ""), encoding="utf-8")
        created.append(outputs["txt"])

    if "srt" in outputs:
        write_srt(outputs["srt"], result.get("segments", []))
        created.append(outputs["srt"])

    return created


def run_smoke_test() -> int:
    status = check_environment()
    missing = [check["name"] for check in status["checks"] if not check["ok"]]

    if missing:
        print("SMOKE_TEST_FAILED")
        for name in missing:
            print(f"missing: {name}")
        return 1

    models = ", ".join(status["installed_models"]) or "none"
    missing_models = ", ".join(status["missing_models"]) or "none"
    print("SMOKE_TEST_OK")
    print(f"app: {APP_TITLE}")
    print(f"input: {INPUT_DIR}")
    print(f"output: {OUTPUT_DIR}")
    print(f"installed models: {models}")
    print(f"missing models: {missing_models}")
    print(f"device: {status['device']} ({status['device_label']})")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--smoke-test", action="store_true", help="run a non-interactive startup check")
    parser.add_argument("--env-check", action="store_true", help="print a JSON environment readiness report")
    parser.add_argument("--transcribe-once", type=Path, help="transcribe one file without opening the GUI")
    parser.add_argument("--language", choices=("ru", "auto"), default="ru")
    parser.add_argument("--quality", choices=tuple(QUALITY_OPTIONS.keys()), default="fast")
    parser.add_argument("--formats", nargs="+", choices=tuple(FORMAT_OPTIONS.keys()), default=["txt"])
    parser.add_argument("--status-file", type=Path, help="write UTF-8 processing status lines to this file")
    parser.add_argument("--result-json", type=Path, help="write a UTF-8 JSON result summary to this file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if args.smoke_test:
            return run_smoke_test()

        if args.env_check:
            print(json.dumps(check_environment(), ensure_ascii=False, indent=2))
            return 0

        if args.transcribe_once:
            if args.status_file and args.status_file.exists():
                args.status_file.unlink()
            if args.result_json and args.result_json.exists():
                args.result_json.unlink()

            request = TranscriptionRequest(
                source=args.transcribe_once,
                language_key=args.language,
                quality_key=args.quality,
                formats=tuple(args.formats),
            )

            def status(message: str) -> None:
                print(message, flush=True)
                append_status(args.status_file, message)

            created = transcribe_file(request, status)
            created_files = [str(path.resolve()) for path in created]
            write_result_json(
                args.result_json,
                {
                    "success": True,
                    "created_files": created_files,
                    "error": None,
                },
            )
            print("CREATED_FILES")
            for path in created_files:
                print(path)
            return 0

        print("Это служебный файл обработки Whisper.")
        print("Для запуска приложения откройте двойным кликом файл: Транскрибатор 9000.cmd")
        return 0
    except UserVisibleError as exc:
        write_result_json(
            getattr(args, "result_json", None),
            {
                "success": False,
                "created_files": [],
                "error": str(exc),
                "kind": "user_visible",
            },
        )
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        message = (
            "Произошла непредвиденная ошибка.\n\n"
            f"Причина: {exc}\n\n"
            f"Технические детали:\n{traceback.format_exc()}"
        )
        write_result_json(
            getattr(args, "result_json", None),
            {
                "success": False,
                "created_files": [],
                "error": message,
                "kind": "unexpected",
            },
        )
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
