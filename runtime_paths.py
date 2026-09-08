from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DATA_DIRECTORY_NAME = "Transcriber 9000"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def application_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_root(environ: dict[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    local_app_data = values.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / APP_DATA_DIRECTORY_NAME
    return Path.home().resolve() / "AppData" / "Local" / APP_DATA_DIRECTORY_NAME


APP_ROOT = application_root()
REPORT_TEMPLATE_PATH = APP_ROOT / "report_templates" / "product_meeting.json"
REPORT_MODEL_CATALOG_PATH = APP_ROOT / "resources" / "report_models.json"
REPORT_CPU_HELPER_PATH = APP_ROOT / ".cache" / "llama-helper-cpu" / "release" / "llama-helper.exe"
REPORT_CUDA_HELPER_PATH = APP_ROOT / ".cache" / "llama-helper-cuda" / "release" / "llama-helper.exe"


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
    "user_data_root",
]
