from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DATA_DIRECTORY_NAME = "Transcriber 9000"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def application_root() -> Path:
    if is_frozen():
        if sys.platform == "darwin":
            return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_root(environ: dict[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ

    if sys.platform == "darwin":
        return Path.home().resolve() / "Library" / "Application Support" / APP_DATA_DIRECTORY_NAME
    local_app_data = values.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / APP_DATA_DIRECTORY_NAME
    return Path.home().resolve() / "AppData" / "Local" / APP_DATA_DIRECTORY_NAME


APP_ROOT = application_root()
REPORT_TEMPLATE_PATH = APP_ROOT / "report_templates" / "product_meeting.json"
REPORT_MODEL_CATALOG_PATH = APP_ROOT / "resources" / "report_models.json"
REPORT_CPU_HELPER_PATH = APP_ROOT / ".cache" / "llama-helper-cpu" / "release" / "llama-helper.exe"
REPORT_CUDA_HELPER_PATH = APP_ROOT / ".cache" / "llama-helper-cuda" / "release" / "llama-helper.exe"


def transcription_data_root() -> Path:
    if is_frozen() and sys.platform == "darwin":
        return user_data_root()
    return APP_ROOT


def transcription_input_dir() -> Path:
    return transcription_data_root() / "input"


def transcription_output_dir() -> Path:
    return transcription_data_root() / "output"


def whisper_cache_dir() -> Path:
    return transcription_data_root() / ".cache" / "whisper"


def run_cache_dir() -> Path:
    return transcription_data_root() / ".cache" / "transcriber" / "runs"


def ffmpeg_executable() -> Path:
    return APP_ROOT / "tools" / "ffmpeg" / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")


def report_models_directory(environ: dict[str, str] | None = None) -> Path:
    return user_data_root(environ) / "models"


def report_model_settings_path(environ: dict[str, str] | None = None) -> Path:
    return user_data_root(environ) / "settings.json"


__all__ = [
    "APP_ROOT",
    "REPORT_CPU_HELPER_PATH",
    "REPORT_CUDA_HELPER_PATH",
    "REPORT_MODEL_CATALOG_PATH",
    "REPORT_TEMPLATE_PATH",
    "application_root",
    "is_frozen",
    "report_model_settings_path",
    "report_models_directory",
    "transcription_data_root",
    "transcription_input_dir",
    "transcription_output_dir",
    "whisper_cache_dir",
    "run_cache_dir",
    "ffmpeg_executable",
    "user_data_root",
]
