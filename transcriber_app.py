from __future__ import annotations

from array import array
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import uuid
from collections.abc import Iterable
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from data_import import copy_legacy_data, has_legacy_data, legacy_data_candidates, prune_stale_legacy_imports
from report_pipeline import ReportPipelineError, load_template, output_path_for
from safe_file_ops import publish_staged_file
from whisper_cache_maintenance import prune_stale_whisper_downloads
from report_model_manager import (
    ReportModelDownloadCancelled,
    ReportModelError,
    ReportModelManager,
)
from runtime_paths import (
    APP_ROOT,
    REPORT_CPU_HELPER_PATH,
    REPORT_CUDA_HELPER_PATH,
    REPORT_TEMPLATE_PATH,
    is_frozen,
    run_cache_dir,
    transcription_data_root,
)

from transcriber_core import (
    APP_DIR,
    APP_TITLE,
    CACHE_DIR,
    FFMPEG_EXE,
    FORMAT_OPTIONS,
    INPUT_DIR,
    MODEL_DOWNLOAD_URLS,
    MODEL_INFO,
    OUTPUT_DIR,
    QUALITY_OPTIONS,
    VENV_PYTHON,
    check_environment,
    get_model_file_state,
    is_inside_input,
)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    class TranscriberWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_enabled = True
            except Exception:
                self.dnd_enabled = False

    DND_ENABLED = True
except Exception:
    DND_FILES = ""
    TranscriberWindow = ctk.CTk
    DND_ENABLED = False


BG = "#0D0F12"
PANEL = "#121519"
CARD = "#171A1E"
CARD_2 = "#20252A"
BORDER = "#30363D"
TEXT = "#F3F0E8"
MUTED = "#9AA1A8"
DIM = "#737B83"
AMBER = "#FFB000"
AMBER_HOVER = "#E29C00"
GOOD = "#69C58F"
WARN = "#E6B85C"
ERROR = "#E36D6D"

UI_SCALE = 1.0 if sys.platform == "darwin" else 1.25
WINDOW_SIZE = "1080x720"
MIN_WINDOW_SIZE = (960, 640)
RUNS_DIR = run_cache_dir()
REPORT_PIPELINE_PATH = APP_DIR / "report_pipeline.py"
REPORT_MODEL_MANAGER = ReportModelManager()
MACOS_REPORTS_UNAVAILABLE = sys.platform == "darwin"
CUDA_RUNTIME_DLLS = ("cudart64_12.dll", "cublas64_12.dll", "cublasLt64_12.dll")

MEDIA_FILTER = (
    ("Аудио и видео", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.mp4 *.mov *.mkv *.avi *.webm"),
    ("Все файлы", "*.*"),
)
MEDIA_SUFFIXES = frozenset(
    {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".mov", ".mkv", ".avi", ".webm"}
)

QUALITY_NOTES = {
    "fast": "Черновик — быстро",
    "balanced": "Стандарт — уверенный баланс",
    "best": "Точный — для большинства задач",
    "premium": "Студийный — лучше на GPU",
    "maximum": "Максимум — высшая точность",
}


@dataclass(frozen=True)
class FontFamilies:
    body: str
    display: str
    mono: str


class UIState(str, Enum):
    """Presentation-only view state; process fields remain the runtime source of truth."""

    INITIAL = "initial"
    FILE_SELECTED = "file_selected"
    TRANSCRIBING = "transcribing"
    REPORT_STARTING = "report_starting"
    REPORT_GENERATING = "report_generating"
    CPU_FALLBACK = "cpu_fallback"
    READY = "ready"
    TRANSCRIPTION_ERROR = "transcription_error"
    REPORT_ERROR = "report_error"


def choose_font_families(
    available: Iterable[str],
    default_family: str,
    fixed_family: str,
) -> FontFamilies:
    by_lower = {family.casefold(): family for family in available}
    body = by_lower.get("segoe ui variable") or by_lower.get("segoe ui") or default_family
    display = by_lower.get("bahnschrift") or body or default_family
    return FontFamilies(body=body, display=display, mono=fixed_family)


def resolve_font_families(root: tk.Misc) -> FontFamilies:
    return choose_font_families(
        tkfont.families(root),
        str(tkfont.nametofont("TkDefaultFont", root=root).actual("family")),
        str(tkfont.nametofont("TkFixedFont", root=root).actual("family")),
    )


def format_bytes(value: int) -> str:
    if value <= 0:
        return "нет файла"
    units = ["B", "KB", "MB", "GB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def is_supported_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_SUFFIXES


def resolve_cuda_runtime_bin(environ: dict[str, str] | None = None) -> Path | None:
    if os.name != "nt":
        return None
    values = environ or os.environ
    candidates = [REPORT_CUDA_HELPER_PATH.parent]
    if not is_frozen():
        versioned_keys = sorted((name for name in values if name.startswith("CUDA_PATH_V")), reverse=True)
        for key in ("CUDA_PATH", *versioned_keys):
            root = values.get(key)
            if root:
                candidates.append(Path(root) / "bin")
    for candidate in candidates:
        if candidate.is_dir() and all((candidate / name).is_file() for name in CUDA_RUNTIME_DLLS):
            return candidate.resolve()
    return None


def build_report_environment(device: str, environ: dict[str, str] | None = None) -> dict[str, str]:
    if device not in {"cuda", "cpu"}:
        raise ValueError(f"Unsupported report device: {device}")
    env = dict(environ or os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if device == "cuda":
        runtime_bin = resolve_cuda_runtime_bin(env)
        if runtime_bin is not None:
            existing = env.get("PATH", "")
            env["PATH"] = str(runtime_bin) + (os.pathsep + existing if existing else "")
    return env


def active_report_model_path() -> Path | None:
    return REPORT_MODEL_MANAGER.active_model_path()


def report_runtime_available(device: str) -> bool:
    if MACOS_REPORTS_UNAVAILABLE:
        return False
    helper = report_helper_path(device)
    model_path = active_report_model_path()
    required = [REPORT_TEMPLATE_PATH, helper]
    if not is_frozen():
        required.append(REPORT_PIPELINE_PATH)
    artifacts_ready = model_path is not None and all(path.is_file() for path in required)
    if device == "cuda" and os.name == "nt":
        return artifacts_ready and resolve_cuda_runtime_bin() is not None
    return artifacts_ready


def report_helper_path(device: str) -> Path:
    if device == "cuda":
        return REPORT_CUDA_HELPER_PATH
    if device == "cpu":
        return REPORT_CPU_HELPER_PATH
    raise ValueError(f"Unsupported report device: {device}")


def build_report_command(
    transcript: Path,
    device: str,
    python_executable: Path | None = None,
    model_path: Path | None = None,
) -> list[str]:
    selected_model = model_path or active_report_model_path()
    if selected_model is None:
        raise ReportModelError("AI-модель не выбрана")
    executable = python_executable or (VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))
    prefix = (
        [str(Path(sys.executable).resolve()), "--worker", "report"]
        if is_frozen() and python_executable is None
        else [str(executable.resolve()), "-X", "utf8", str(REPORT_PIPELINE_PATH.resolve())]
    )
    return prefix + [
        "--transcript",
        str(transcript.resolve()),
        "--template",
        str(REPORT_TEMPLATE_PATH.resolve()),
        "--helper",
        str(report_helper_path(device).resolve()),
        "--model",
        str(selected_model.resolve()),
        "--device",
        device,
    ]


def build_transcription_command(
    source: Path,
    language: str,
    quality: str,
    status_file: Path,
    result_json: Path,
    formats: list[str],
    python_executable: Path | None = None,
) -> list[str]:
    executable = python_executable or (VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))
    prefix = (
        [str(Path(sys.executable).resolve()), "--worker", "transcription"]
        if is_frozen() and python_executable is None
        else [str(executable.resolve()), "-X", "utf8", str(APP_DIR / "transcriber_core.py")]
    )
    return prefix + [
        "--transcribe-once",
        str(source),
        "--language",
        language,
        "--quality",
        quality,
        "--status-file",
        str(status_file),
        "--result-json",
        str(result_json),
        "--formats",
        *formats,
    ]


def expected_report_path(transcript: Path) -> Path:
    return output_path_for(transcript, load_template(REPORT_TEMPLATE_PATH))


def first_txt_result(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.suffix.lower() == ".txt"), None)


def friendly_transcription_status(text: str) -> str:
    """Translate core progress into short user-facing copy without changing control flow."""

    lowered = text.casefold()
    if "загружа" in lowered or "модель" in lowered:
        return "Подготавливаю распознавание…"
    if "распозна" in lowered or "транскриб" in lowered:
        return "Распознаю речь. Окно можно оставить открытым."
    if "сохраня" in lowered or "записыва" in lowered:
        return "Сохраняю транскрипцию…"
    return "Расшифровываю запись. Окно можно оставить открытым."


class Transcriber9000App(TranscriberWindow):
    """Desktop shell for the local Whisper transcription workflow."""

    def __init__(self) -> None:
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
        super().__init__()
        self.dnd_enabled = getattr(self, "dnd_enabled", False)

        self.title(APP_TITLE)
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.fonts = resolve_font_families(self)

        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        prune_stale_whisper_downloads(CACHE_DIR, MODEL_DOWNLOAD_URLS)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        prune_stale_legacy_imports(transcription_data_root())

        self.selected_file: Path | None = None
        self.active_process: subprocess.Popen | None = None
        self.active_process_kind: str | None = None
        self.active_report_device: str | None = None
        self.active_stdout_chunks: list[str] = []
        self.active_stderr_chunks: list[str] = []
        self.active_pipe_threads: list[threading.Thread] = []
        self.status_file: Path | None = None
        self.result_json: Path | None = None
        self.last_status_count = 0
        self.created_result_paths: list[Path] = []
        self.report_transcript_path: Path | None = None
        self.report_output_path: Path | None = None
        self.report_action: str | None = None
        self.ui_state = UIState.INITIAL
        self.error_detail = ""
        self.import_in_progress = False
        self.log_is_open = False
        self.active_view = "work"
        self.waveform_values: list[float] | None = None
        self.waveform_request_id = 0

        self.download_queue: queue.Queue[tuple] = queue.Queue()
        self.report_model_queue: queue.Queue[tuple] = queue.Queue()
        self.import_queue: queue.Queue[tuple] = queue.Queue()
        self.legacy_import_queue: queue.Queue[tuple] = queue.Queue()
        self.waveform_queue: queue.Queue[tuple] = queue.Queue()
        self.download_buttons: dict[str, ctk.CTkButton] = {}
        self.model_status_labels: dict[str, ctk.CTkLabel] = {}
        self.model_detail_labels: dict[str, ctk.CTkLabel] = {}
        self.report_model_manager = REPORT_MODEL_MANAGER
        self.report_model_status_labels: dict[str, ctk.CTkLabel] = {}
        self.report_model_primary_buttons: dict[str, ctk.CTkButton] = {}
        self.report_model_select_buttons: dict[str, ctk.CTkButton] = {}
        self.report_model_delete_buttons: dict[str, ctk.CTkButton] = {}
        self.report_model_cancel_events: dict[str, threading.Event] = {}
        self.report_model_busy: dict[str, str] = {}

        self.language_var = ctk.StringVar(value="ru")
        self.quality_var = ctk.StringVar(value="balanced")
        self.txt_var = ctk.BooleanVar(value=True)
        self.srt_var = ctk.BooleanVar(value=False)

        self._build_layout()

        dpi_scaling = max(ctk.ScalingTracker.get_window_dpi_scaling(self), 1.0)
        ctk.set_widget_scaling(UI_SCALE / dpi_scaling)
        ctk.set_window_scaling(UI_SCALE / dpi_scaling)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)
        self.render_ui_state(UIState.INITIAL)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_environment()
        self.after(500, self.poll_process)
        self.after(300, self.poll_download_queue)
        self.after(200, self.poll_report_model_queue)
        self.after(150, self.poll_import_queue)
        self.after(200, self.poll_legacy_import_queue)
        self.after(150, self.poll_waveform_queue)
        if is_frozen() and sys.platform == "darwin":
            self.after(1000, self.maybe_offer_legacy_import)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 12))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="ТРАНСКРИБАТОР / 9000",
            font=self._font("display", 24, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")

        header_actions = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        header_actions.grid(row=0, column=1, sticky="e")
        self.ready_badge = ctk.CTkLabel(
            header_actions,
            text="● Обработка на этом компьютере",
            fg_color="transparent",
            padx=4,
            pady=6,
            text_color=MUTED,
            font=self._font("body", 12),
        )
        self.ready_badge.grid(row=0, column=0, padx=(0, 12))
        self.service_nav_button = self._button(
            header_actions,
            text="Настройки",
            command=self.show_service_view,
            width=112,
            height=36,
            fg_color="transparent",
            border_width=0,
        )
        self.service_nav_button.grid(row=0, column=1)

        self.view_host = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.view_host.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 22))
        self.view_host.grid_columnconfigure(0, weight=1)
        self.view_host.grid_rowconfigure(0, weight=1)

        self.work_view = ctk.CTkFrame(
            self.view_host,
            fg_color=BG,
            corner_radius=0,
        )
        self.service_view = ctk.CTkFrame(
            self.view_host,
            fg_color=PANEL,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        self._build_work_view()
        self._build_service_view()
        self.show_work_view()

    def _button(self, master, **kwargs):
        defaults = {
            "height": 40,
            "corner_radius": 7,
            "fg_color": CARD_2,
            "hover_color": BORDER,
            "text_color": TEXT,
            "border_width": 1,
            "border_color": BORDER,
            "font": self._font("body", 12, "bold"),
        }
        defaults.update(kwargs)
        button = ctk.CTkButton(master, **defaults)
        self._add_focus_ring(button, defaults["border_color"])
        return button

    def _font(self, role: str, size: int, weight: str = "normal") -> ctk.CTkFont:
        family = getattr(self.fonts, role)
        return ctk.CTkFont(family, size, weight)

    @staticmethod
    def _add_focus_ring(widget, default_color: str = BORDER) -> None:
        if hasattr(widget, "_canvas"):
            widget._canvas.configure(takefocus=1)
        widget.bind("<FocusIn>", lambda _event: widget.configure(border_color=TEXT, border_width=2))
        widget.bind("<FocusOut>", lambda _event: widget.configure(border_color=default_color, border_width=1))
        if hasattr(widget, "invoke"):
            widget.bind("<Return>", lambda _event: widget.invoke())
            widget.bind("<space>", lambda _event: widget.invoke())

    def _build_work_view(self) -> None:
        view = self.work_view
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(4, weight=1)

        intro = ctk.CTkFrame(view, fg_color="transparent", corner_radius=0)
        self.intro_frame = intro
        intro.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 14))
        intro.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            intro,
            text="Создать расшифровку",
            font=self._font("display", 22, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            intro,
            text="Добавьте запись — готовые файлы появятся здесь.",
            font=self._font("body", 13),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        self.drop_frame = ctk.CTkFrame(
            view,
            fg_color=CARD_2,
            border_color=BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.drop_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 12))
        self.drop_frame.grid_columnconfigure(0, weight=1)

        self.drop_signal = ctk.CTkLabel(
            self.drop_frame,
            text="Аудио или видео",
            font=self._font("body", 12),
            text_color=MUTED,
        )
        self.drop_signal.grid(row=0, column=0, sticky="e", padx=20, pady=(14, 0))

        self.waveform = tk.Canvas(
            self.drop_frame,
            height=round(48 * UI_SCALE),
            bg=CARD_2,
            highlightthickness=0,
            bd=0,
        )
        self.waveform.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 2))
        self.waveform.bind("<Configure>", self._draw_waveform)

        self.file_label = ctk.CTkLabel(
            self.drop_frame,
            text="Перетащите аудио или видео",
            font=self._font("display", 17, "bold"),
            text_color=TEXT,
        )
        self.file_label.grid(row=2, column=0, sticky="ew", padx=20, pady=(2, 0))
        self.file_meta_label = ctk.CTkLabel(
            self.drop_frame,
            text="или выберите файл с компьютера",
            font=self._font("body", 13),
            text_color=MUTED,
        )
        self.file_meta_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(2, 12))
        self.choose_button = self._button(
            self.drop_frame,
            text="Выбрать файл",
            command=self.choose_file,
            width=180,
            height=42,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            text_color=BG,
            border_color=AMBER,
        )
        self.choose_button.grid(row=4, column=0, pady=(0, 18))
        self.drop_hint = ctk.CTkLabel(
            self.drop_frame,
            text="Файл останется на этом компьютере",
            font=self._font("body", 10),
            text_color=DIM,
        )

        if self.dnd_enabled:
            self._register_drop_targets(
                self.drop_frame,
                self.waveform,
                self.file_label,
                self.file_meta_label,
                self.choose_button,
                self.drop_hint,
            )

        self._build_settings_panel(view)
        self._build_status_panel(view)

    def _build_status_panel(self, master) -> None:
        status = ctk.CTkFrame(master, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=10)
        self.status_panel = status
        status.grid(row=3, column=0, sticky="ew", padx=4, pady=(0, 4))
        status.grid_columnconfigure(0, weight=1)

        status_head = ctk.CTkFrame(status, fg_color="transparent", corner_radius=0)
        status_head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        status_head.grid_columnconfigure(1, weight=1)
        self.status_icon = ctk.CTkLabel(
            status_head,
            text="●",
            width=18,
            text_color=AMBER,
            font=self._font("body", 16, "bold"),
        )
        self.status_icon.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10))
        self.status_label = ctk.CTkLabel(
            status_head,
            text="",
            text_color=TEXT,
            anchor="w",
            font=self._font("display", 20, "bold"),
        )
        self.status_label.grid(row=0, column=1, sticky="ew")
        self.status_detail_label = ctk.CTkLabel(
            status_head,
            text="",
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=760,
            font=self._font("body", 13),
        )
        self.status_detail_label.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        self.status_step_label = ctk.CTkLabel(
            status_head,
            text="",
            text_color=MUTED,
            font=self._font("body", 12, "bold"),
        )
        self.log_toggle_button = self._button(
            status_head,
            text="Подробности",
            command=self.toggle_log,
            width=104,
            height=30,
            fg_color="transparent",
            text_color=MUTED,
            font=self._font("body", 10),
        )

        stage_frame = ctk.CTkFrame(status, fg_color=CARD_2, corner_radius=7)
        self.stage_frame = stage_frame
        stage_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(2, 8))
        stage_frame.grid_columnconfigure((0, 2), weight=1)
        self.transcription_stage_label = ctk.CTkLabel(
            stage_frame,
            text="1  Расшифровка",
            anchor="w",
            text_color=MUTED,
            font=self._font("body", 12, "bold"),
        )
        self.transcription_stage_label.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=9)
        self.stage_arrow_label = ctk.CTkLabel(
            stage_frame,
            text="→",
            width=28,
            text_color=DIM,
            font=self._font("body", 15, "bold"),
        )
        self.stage_arrow_label.grid(row=0, column=1, pady=9)
        self.report_stage_label = ctk.CTkLabel(
            stage_frame,
            text="2  AI-отчёт",
            anchor="e",
            text_color=MUTED,
            font=self._font("body", 12, "bold"),
        )
        self.report_stage_label.grid(row=0, column=2, sticky="ew", padx=(8, 12), pady=9)

        self.progress = ctk.CTkProgressBar(
            status,
            height=6,
            corner_radius=3,
            progress_color=AMBER,
            fg_color=CARD_2,
        )
        self.progress.set(0)
        self.progress.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 14))

        self.result_frame = ctk.CTkFrame(
            status,
            fg_color="transparent",
            corner_radius=0,
        )
        self.result_frame.grid_columnconfigure(0, weight=1)
        self.result_label = ctk.CTkLabel(
            self.result_frame,
            text="",
            anchor="w",
            justify="left",
            text_color=TEXT,
            font=self._font("body", 13),
        )
        self.result_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 16))
        self.report_action_button = self._button(
            self.result_frame,
            text="Создать AI-отчёт на CPU",
            command=self.handle_report_action,
            width=210,
            height=42,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            text_color=BG,
            border_color=AMBER,
        )
        self.open_results_button = self._button(
            self.result_frame,
            text="Показать в папке",
            command=lambda: self.open_folder(OUTPUT_DIR),
            width=148,
            height=42,
            fg_color="transparent",
        )

        self.log_box = ctk.CTkTextbox(
            status,
            height=92,
            fg_color=BG,
            text_color=MUTED,
            border_color=BORDER,
            border_width=1,
            corner_radius=6,
            font=self._font("mono", 10),
        )
        self.append_log("Журнал системы готов.")

    def _build_settings_panel(self, master) -> None:
        settings = ctk.CTkFrame(master, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=10)
        self.settings_panel = settings
        settings.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 12))
        settings.grid_columnconfigure(0, weight=2, minsize=138)
        settings.grid_columnconfigure(1, weight=4, minsize=250)
        settings.grid_columnconfigure(2, weight=2, minsize=156)
        settings.grid_columnconfigure(3, weight=3, minsize=212)

        ctk.CTkLabel(
            settings,
            text="Язык",
            font=self._font("body", 12, "bold"),
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w", padx=(20, 10), pady=(14, 5))
        self.language_segment = ctk.CTkSegmentedButton(
            settings,
            values=["русский", "авто"],
            command=lambda value: self.language_var.set("ru" if value == "русский" else "auto"),
            height=36,
            selected_color=AMBER,
            selected_hover_color=AMBER_HOVER,
            text_color=TEXT,
            unselected_color=CARD_2,
            unselected_hover_color=BORDER,
            font=self._font("body", 12, "bold"),
        )
        self.language_segment.grid(row=1, column=0, sticky="ew", padx=(20, 10), pady=(0, 16))
        self.language_segment.set("русский")

        ctk.CTkLabel(
            settings,
            text="Качество",
            font=self._font("body", 12, "bold"),
            text_color=MUTED,
        ).grid(row=0, column=1, sticky="w", padx=10, pady=(14, 5))
        self.quality_menu = ctk.CTkOptionMenu(
            settings,
            values=[QUALITY_NOTES[key] for key in QUALITY_OPTIONS],
            command=self.on_quality_change,
            height=36,
            corner_radius=7,
            fg_color=CARD_2,
            button_color=AMBER,
            button_hover_color=AMBER_HOVER,
            text_color=TEXT,
            font=self._font("body", 12),
        )
        self.quality_menu.grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 16))
        self.quality_menu.set(QUALITY_NOTES[self.quality_var.get()])
        self.quality_state = ctk.CTkLabel(
            settings,
            text="",
            text_color=DIM,
            font=self._font("body", 10),
        )

        ctk.CTkLabel(
            settings,
            text="Результат",
            font=self._font("body", 12, "bold"),
            text_color=MUTED,
        ).grid(row=0, column=2, sticky="w", padx=10, pady=(14, 5))
        format_frame = ctk.CTkFrame(settings, fg_color="transparent", corner_radius=0)
        format_frame.grid(row=1, column=2, sticky="w", padx=10, pady=(0, 16))
        self.txt_checkbox = ctk.CTkCheckBox(
            format_frame,
            text=FORMAT_OPTIONS["txt"],
            variable=self.txt_var,
            height=36,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=3,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            border_color=MUTED,
            text_color=TEXT,
            font=self._font("body", 12),
        )
        self.txt_checkbox.grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.srt_checkbox = ctk.CTkCheckBox(
            format_frame,
            text="SRT",
            variable=self.srt_var,
            height=36,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=3,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            border_color=MUTED,
            text_color=TEXT,
            font=self._font("body", 12),
        )
        self.srt_checkbox.grid(row=0, column=1, sticky="w")

        self.start_button = self._button(
            settings,
            text="Начать обработку",
            command=self.start_transcription,
            height=42,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            text_color=BG,
            border_color=AMBER,
            font=self._font("body", 13, "bold"),
        )
        self.start_button.grid(row=0, column=3, rowspan=2, sticky="ew", padx=(10, 20), pady=16)

    def _build_service_view(self) -> None:
        view = self.service_view
        view.grid_columnconfigure(0, weight=3)
        view.grid_columnconfigure(1, weight=2)
        view.grid_rowconfigure(1, weight=1)

        heading = ctk.CTkFrame(view, fg_color="transparent", corner_radius=0)
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(20, 14))
        heading.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            heading,
            text="Настройки",
            font=self._font("display", 22, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            heading,
            text="Модели распознавания и состояние приложения",
            font=self._font("body", 12),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self._button(
            heading,
            text="Вернуться",
            command=self.show_work_view,
            width=112,
            height=34,
            fg_color="transparent",
        ).grid(row=0, column=1, rowspan=2, padx=(0, 8))
        self._button(
            heading,
            text="Проверить систему",
            command=self.refresh_environment,
            width=140,
            height=34,
        ).grid(row=0, column=2, rowspan=2)
        if sys.platform == "darwin":
            self._button(
                heading,
                text="Импорт данных",
                command=self.choose_legacy_import,
                width=120,
                height=34,
            ).grid(row=0, column=3, rowspan=2, padx=(8, 0))

        models_panel = ctk.CTkScrollableFrame(
            view,
            fg_color=CARD,
            border_color=BORDER,
            border_width=1,
            corner_radius=8,
            label_text="Модели распознавания",
            label_font=self._font("display", 15, "bold"),
            label_text_color=TEXT,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
        )
        models_panel.grid(row=1, column=0, sticky="nsew", padx=(24, 10), pady=(0, 22))
        models_panel.grid_columnconfigure(0, weight=1)

        for row, (_quality_key, (quality_label, model_name)) in enumerate(QUALITY_OPTIONS.items()):
            info = MODEL_INFO[model_name]
            item = ctk.CTkFrame(models_panel, fg_color=CARD_2, border_color=BORDER, border_width=1, corner_radius=4)
            item.grid(row=row, column=0, sticky="ew", padx=6, pady=5)
            item.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                item,
                text=model_name,
                width=86,
                font=self._font("display", 18, "bold"),
                text_color=AMBER,
            ).grid(row=0, column=0, rowspan=2, padx=12, pady=12)
            ctk.CTkLabel(
                item,
                text=quality_label,
                font=self._font("body", 12, "bold"),
                text_color=TEXT,
            ).grid(row=0, column=1, sticky="w", pady=(11, 1))
            detail = ctk.CTkLabel(
                item,
                text=info["summary"],
                font=self._font("body", 10),
                text_color=MUTED,
                anchor="w",
            )
            detail.grid(row=1, column=1, sticky="ew", pady=(0, 11))
            self.model_detail_labels[model_name] = detail
            status = ctk.CTkLabel(
                item,
                text="",
                width=128,
                font=self._font("mono", 10, "bold"),
                text_color=MUTED,
            )
            status.grid(row=0, column=2, rowspan=2, padx=(10, 8))
            self.model_status_labels[model_name] = status
            button = self._button(
                item,
                text="Скачать",
                command=lambda name=model_name: self.download_model(name),
                width=108,
                height=32,
                fg_color=AMBER,
                hover_color=AMBER_HOVER,
                text_color=BG,
                border_color=AMBER,
            )
            button.grid(row=0, column=3, rowspan=2, padx=(0, 12), pady=12)
            self.download_buttons[model_name] = button

        report_heading_row = len(QUALITY_OPTIONS)
        ctk.CTkLabel(
            models_panel,
            text="AI-отчёты недоступны на macOS" if MACOS_REPORTS_UNAVAILABLE else "Модель AI-отчёта",
            font=self._font("display", 15, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=report_heading_row, column=0, sticky="ew", padx=8, pady=(18, 5))

        for offset, model in enumerate(self.report_model_manager.models, start=1):
            item = ctk.CTkFrame(
                models_panel,
                fg_color=CARD_2,
                border_color=BORDER,
                border_width=1,
                corner_radius=4,
            )
            item.grid(row=report_heading_row + offset, column=0, sticky="ew", padx=6, pady=5)
            item.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                item,
                text=f"{model.name}  ·  {model.badge}",
                font=self._font("body", 12, "bold"),
                text_color=AMBER if model.badge == "Recommended" else TEXT,
                anchor="w",
            ).grid(row=0, column=0, columnspan=4, sticky="ew", padx=12, pady=(10, 2))
            ctk.CTkLabel(
                item,
                text=f"{model.description}\n{model.quality_note}",
                font=self._font("body", 9),
                text_color=MUTED,
                anchor="w",
                justify="left",
                wraplength=430,
            ).grid(row=1, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 6))
            status = ctk.CTkLabel(
                item,
                text="",
                font=self._font("mono", 9, "bold"),
                text_color=MUTED,
                anchor="w",
            )
            status.grid(row=2, column=0, sticky="ew", padx=(12, 6), pady=(0, 10))
            self.report_model_status_labels[model.model_id] = status
            primary = self._button(
                item,
                text="Скачать",
                command=lambda model_id=model.model_id: self.handle_report_model_primary(model_id),
                width=88,
                height=30,
                fg_color=AMBER,
                hover_color=AMBER_HOVER,
                text_color=BG,
                border_color=AMBER,
            )
            primary.grid(row=2, column=1, padx=4, pady=(0, 10))
            self.report_model_primary_buttons[model.model_id] = primary
            select = self._button(
                item,
                text="Выбрать",
                command=lambda model_id=model.model_id: self.select_report_model(model_id),
                width=76,
                height=30,
            )
            select.grid(row=2, column=2, padx=4, pady=(0, 10))
            self.report_model_select_buttons[model.model_id] = select
            delete = self._button(
                item,
                text="Удалить",
                command=lambda model_id=model.model_id: self.delete_report_model(model_id),
                width=72,
                height=30,
                fg_color="transparent",
                text_color=MUTED,
            )
            delete.grid(row=2, column=3, padx=(4, 12), pady=(0, 10))
            self.report_model_delete_buttons[model.model_id] = delete

        ready_panel = ctk.CTkFrame(view, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=6)
        ready_panel.grid(row=1, column=1, sticky="nsew", padx=(10, 24), pady=(0, 22))
        ready_panel.grid_columnconfigure(0, weight=1)
        ready_panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            ready_panel,
            text="Состояние системы",
            font=self._font("display", 15, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 10))
        self.ready_text = ctk.CTkTextbox(
            ready_panel,
            fg_color=BG,
            text_color=MUTED,
            border_color=BORDER,
            border_width=1,
            corner_radius=6,
            font=self._font("mono", 10),
        )
        self.ready_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

    def show_work_view(self) -> None:
        self.active_view = "work"
        self.service_view.grid_forget()
        self.work_view.grid(row=0, column=0, sticky="nsew")
        self.service_nav_button.configure(fg_color="transparent", text_color=TEXT, border_color=BORDER)

    def show_service_view(self) -> None:
        self.active_view = "service"
        self.work_view.grid_forget()
        self.service_view.grid(row=0, column=0, sticky="nsew")
        self.service_nav_button.configure(fg_color=CARD_2, text_color=TEXT, border_color=BORDER)
        self.refresh_environment()

    def _apply_source_density(self, mode: str) -> None:
        if mode == "initial":
            intro_pady = (64, 18)
            frame_pady = (0, 18)
            waveform_height = 72
            signal_pady = (18, 0)
            file_pady = (8, 0)
            meta_pady = (5, 16)
            button_pady = (0, 24)
        elif mode == "ready":
            intro_pady = (2, 10)
            frame_pady = (0, 10)
            waveform_height = 34
            signal_pady = (10, 0)
            file_pady = (0, 0)
            meta_pady = (1, 8)
            button_pady = (0, 12)
        else:
            intro_pady = (4, 14)
            frame_pady = (0, 12)
            waveform_height = 48
            signal_pady = (14, 0)
            file_pady = (2, 0)
            meta_pady = (2, 12)
            button_pady = (0, 18)

        self.intro_frame.grid_configure(pady=intro_pady)
        self.drop_frame.grid_configure(pady=frame_pady)
        self.waveform.configure(height=round(waveform_height * UI_SCALE))
        self.drop_signal.grid_configure(pady=signal_pady)
        self.file_label.grid_configure(pady=file_pady)
        self.file_meta_label.grid_configure(pady=meta_pady)
        self.choose_button.grid_configure(pady=button_pady)

    def render_ui_state(self, state: UIState, detail: str = "") -> None:
        """Render presentation only; process and result fields remain authoritative."""

        self.ui_state = state
        if detail:
            self.error_detail = detail

        self.settings_panel.grid_forget()
        self.status_panel.grid_forget()
        self.stage_frame.grid_forget()
        self.progress.grid_forget()
        self.result_frame.grid_forget()
        self.report_action_button.grid_forget()
        self.open_results_button.grid_forget()
        self.start_button.grid_forget()
        self.log_toggle_button.grid_forget()
        self.status_step_label.grid_forget()
        self.log_box.grid_forget()
        self.log_is_open = False
        self.status_panel.configure(border_color=BORDER)
        self.status_icon.configure(text="●", font=self._font("body", 16, "bold"))
        self.status_label.configure(font=self._font("display", 20, "bold"))

        is_initial = state is UIState.INITIAL
        is_processing = state in {
            UIState.TRANSCRIBING,
            UIState.REPORT_STARTING,
            UIState.REPORT_GENERATING,
        }
        if is_initial:
            self._apply_source_density("initial")
            self.file_label.configure(text="Перетащите аудио или видео", text_color=TEXT)
            self.file_meta_label.configure(text="или выберите файл с компьютера")
            self.drop_signal.configure(text="Аудио или видео", text_color=MUTED)
            self.drop_frame.configure(border_color=BORDER, border_width=1)
            self.choose_button.configure(
                text="Выбрать файл",
                fg_color=AMBER,
                hover_color=AMBER_HOVER,
                text_color=BG,
                border_color=AMBER,
            )
        else:
            ready_with_report = state is UIState.READY and self.report_action == "open" and self.report_output_path
            self._apply_source_density("ready" if ready_with_report else "default")
            self.drop_frame.configure(border_color=BORDER, border_width=1)
            self.choose_button.configure(
                text="Заменить",
                fg_color="transparent",
                hover_color=BORDER,
                text_color=TEXT,
                border_color=BORDER,
            )

        if is_processing:
            self.choose_button.grid_forget()
        else:
            self.choose_button.grid(row=4, column=0)

        if state is UIState.FILE_SELECTED:
            self.settings_panel.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 12))
            self.start_button.grid(row=0, column=3, rowspan=2, sticky="ew", padx=(10, 20), pady=16)
            self.drop_signal.configure(text="● Файл готов", text_color=AMBER)
            self.drop_frame.configure(border_color="#4B4432")
            return

        if state is UIState.INITIAL:
            return

        self.status_panel.grid(row=3, column=0, sticky="ew", padx=4, pady=(0, 4))
        title = ""
        description = detail
        icon_color = AMBER

        if state is UIState.TRANSCRIBING:
            self.settings_panel.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 12))
            self.drop_signal.configure(text="● В работе", text_color=AMBER)
            title = "Расшифровываю запись"
            description = description or "Окно можно оставить открытым."
            self.status_step_label.configure(text="Шаг 1 из 2")
            self.status_step_label.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(16, 0))
            self.transcription_stage_label.configure(text="●  Расшифровка", text_color=AMBER)
            self.stage_arrow_label.configure(text_color=DIM)
            self.report_stage_label.configure(text="AI-отчёт", text_color=MUTED)
            self.stage_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 8))
            self.progress.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        elif state is UIState.REPORT_STARTING:
            self.drop_signal.configure(text="● TXT готов", text_color=GOOD)
            title = "Расшифровка готова"
            description = "TXT сохранён. Запускаю AI-отчёт…"
            self.status_step_label.configure(text="Шаг 2 из 2")
            self.status_step_label.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(16, 0))
            self.transcription_stage_label.configure(text="✓  Расшифровка", text_color=GOOD)
            self.stage_arrow_label.configure(text_color=GOOD)
            self.report_stage_label.configure(text="●  AI-отчёт", text_color=AMBER)
            self.stage_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 8))
            self.progress.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        elif state is UIState.REPORT_GENERATING:
            self.drop_signal.configure(text="● AI-отчёт", text_color=AMBER)
            title = "Создаю AI-отчёт"
            description = "Транскрипция уже сохранена. Окно можно оставить открытым."
            self.status_step_label.configure(text="Шаг 2 из 2")
            self.status_step_label.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(16, 0))
            self.transcription_stage_label.configure(text="✓  Расшифровка", text_color=GOOD)
            self.stage_arrow_label.configure(text_color=GOOD)
            self.report_stage_label.configure(text="●  AI-отчёт", text_color=AMBER)
            self.stage_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 8))
            self.progress.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        elif state is UIState.CPU_FALLBACK:
            self.drop_signal.configure(text="● TXT готов", text_color=WARN)
            title = "AI-отчёт можно создать на процессоре"
            description = "Быстрый режим недоступен. Этот вариант займёт заметно больше времени."
            icon_color = WARN
            self.result_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))
            self.report_action_button.configure(
                fg_color=AMBER,
                hover_color=AMBER_HOVER,
                text_color=BG,
                border_color=AMBER,
            )
            self.report_action_button.grid(row=1, column=0, sticky="w")
            self.open_results_button.configure(
                text="Показать в папке",
                command=lambda: self.open_folder(OUTPUT_DIR),
                fg_color="transparent",
                hover_color=BORDER,
                text_color=TEXT,
                border_color=BORDER,
            )
            self.open_results_button.grid(row=1, column=1, sticky="e", padx=(10, 0))
        elif state is UIState.READY:
            self.drop_signal.configure(text="● Готово", text_color=GOOD)
            title = "Готово"
            description = (
                "Расшифровка и AI-отчёт созданы"
                if self.report_action == "open" and self.report_output_path
                else "Результаты созданы и сохранены на этом компьютере"
            )
            icon_color = GOOD
            self.status_icon.configure(text="✓", font=self._font("body", 20, "bold"))
            self.status_label.configure(font=self._font("display", 24, "bold"))
            self.status_panel.configure(border_color="#31503D")
            self.result_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))
            if self.report_action == "open" and self.report_output_path:
                self.report_action_button.configure(
                    text="Открыть AI-отчёт",
                    fg_color=AMBER,
                    hover_color=AMBER_HOVER,
                    text_color=BG,
                    border_color=AMBER,
                )
                self.report_action_button.grid(row=1, column=0, sticky="w")
                self.open_results_button.configure(
                    text="Показать в папке",
                    command=lambda: self.open_folder(OUTPUT_DIR),
                    fg_color="transparent",
                    hover_color=BORDER,
                    text_color=TEXT,
                    border_color=BORDER,
                )
                self.open_results_button.grid(row=1, column=1, sticky="e", padx=(10, 0))
            else:
                self.open_results_button.configure(
                    text="Показать в папке",
                    command=lambda: self.open_folder(OUTPUT_DIR),
                    fg_color=AMBER,
                    hover_color=AMBER_HOVER,
                    text_color=BG,
                    border_color=AMBER,
                )
                self.open_results_button.grid(row=1, column=0, sticky="w")
        elif state is UIState.TRANSCRIPTION_ERROR:
            self.drop_signal.configure(text="● Ошибка", text_color=ERROR)
            title = "Не удалось расшифровать файл"
            description = "Попробуйте ещё раз или выберите другую запись."
            icon_color = ERROR
            self.status_icon.configure(text="!", font=self._font("body", 18, "bold"))
            self.status_panel.configure(border_color="#563139")
            self.report_action = "retry_transcription"
            self.report_action_button.configure(
                text="Повторить расшифровку",
                fg_color=AMBER,
                hover_color=AMBER_HOVER,
                text_color=BG,
                border_color=AMBER,
            )
            self.result_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))
            self.report_action_button.grid(row=1, column=0, sticky="w")
            self.open_results_button.configure(
                text="Выбрать другой файл",
                command=self.choose_file,
                fg_color="transparent",
                hover_color=BORDER,
                text_color=TEXT,
                border_color=BORDER,
            )
            self.open_results_button.grid(row=1, column=1, sticky="e", padx=(10, 0))
            self.log_toggle_button.grid(row=0, column=2, rowspan=2, padx=(12, 0))
        elif state is UIState.REPORT_ERROR:
            self.drop_signal.configure(text="● TXT сохранён", text_color=ERROR)
            title = "AI-отчёт не создан"
            description = "Транскрипция сохранена и доступна в папке результатов."
            icon_color = ERROR
            self.status_icon.configure(text="!", font=self._font("body", 18, "bold"))
            self.status_panel.configure(border_color="#563139")
            self.result_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))
            if self.report_action == "retry_cpu":
                self.report_action_button.grid(row=1, column=0, sticky="w")
            self.open_results_button.configure(
                text="Показать транскрипцию",
                command=lambda: self.open_folder(OUTPUT_DIR),
                fg_color="transparent" if self.report_action == "retry_cpu" else AMBER,
                hover_color=BORDER if self.report_action == "retry_cpu" else AMBER_HOVER,
                text_color=TEXT if self.report_action == "retry_cpu" else BG,
                border_color=BORDER if self.report_action == "retry_cpu" else AMBER,
            )
            self.open_results_button.grid(
                row=1,
                column=1 if self.report_action == "retry_cpu" else 0,
                sticky="e" if self.report_action == "retry_cpu" else "w",
                padx=(10, 0) if self.report_action == "retry_cpu" else 0,
            )
            self.log_toggle_button.grid(row=0, column=2, rowspan=2, padx=(12, 0))

        self.status_icon.configure(text_color=icon_color)
        self.status_label.configure(text=title, text_color=TEXT)
        self.status_detail_label.configure(text=description)
        self._draw_waveform()

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=INPUT_DIR,
            title="Выберите аудио или видео",
            filetypes=MEDIA_FILTER,
        )
        if path:
            self.import_or_select_file(Path(path))

    def handle_drop(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        if paths:
            self.import_or_select_file(Path(paths[0]))

    def import_or_select_file(self, path: Path) -> None:
        if self.active_process or self.import_in_progress:
            self.show_error("Сейчас приложение занято. Дождитесь завершения текущей операции.")
            return
        try:
            resolved = path.expanduser().resolve()
        except OSError as exc:
            self.show_error(f"Не удалось открыть выбранный файл.\n\nПричина: {exc}")
            return

        if not resolved.exists() or not resolved.is_file():
            self.show_error(f"Файл не найден:\n{resolved}")
            return
        if not is_supported_media_file(resolved):
            supported = ", ".join(sorted(suffix.removeprefix(".").upper() for suffix in MEDIA_SUFFIXES))
            self.show_error(
                f"Этот формат не поддерживается:\n{resolved.name}\n\n"
                f"Поддерживаются: {supported}."
            )
            return
        if is_inside_input(resolved):
            self.set_selected_file(resolved)
            return

        target = INPUT_DIR / resolved.name
        if target.exists():
            self.show_error(
                "В папке исходников уже есть файл с таким именем:\n"
                f"{target}\n\nНичего не перезаписано. Переименуйте исходный файл и добавьте его снова."
            )
            return
        self.start_import(resolved, target)

    def start_import(self, source: Path, target: Path) -> None:
        self.import_in_progress = True
        self.set_import_busy(True)
        self.set_status("Копирую файл в папку исходников. Оригинал останется на месте.")
        self.append_log(f"Импорт: {source} -> {target}")
        threading.Thread(target=self._copy_file_to_input, args=(source, target), daemon=True).start()

    def _copy_file_to_input(self, source: Path, target: Path) -> None:
        temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.importing")
        copied = 0
        try:
            total = source.stat().st_size
            with source.open("rb") as source_file, temp.open("xb") as target_file:
                while chunk := source_file.read(1024 * 1024):
                    target_file.write(chunk)
                    copied += len(chunk)
                    self.import_queue.put(("progress", copied, total))
            shutil.copystat(source, temp)
            publish_staged_file(temp, target)
            temp.unlink(missing_ok=True)
            self.import_queue.put(("done", target))
        except Exception as exc:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass
            self.import_queue.put(("error", str(exc)))

    def poll_import_queue(self) -> None:
        try:
            while True:
                item = self.import_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, copied, total = item
                    progress = f"{int(copied * 100 / total)}%" if total else format_bytes(copied)
                    self.set_status(f"Копирование файла: {progress}")
                elif kind == "done":
                    _, target = item
                    self.import_in_progress = False
                    self.set_import_busy(False)
                    self.set_selected_file(Path(target))
                    self.set_status("Файл скопирован и готов к расшифровке.")
                    self.append_log(f"Импорт завершён: {target}")
                elif kind == "error":
                    _, error = item
                    self.import_in_progress = False
                    self.set_import_busy(False)
                    self.show_error(
                        "Не удалось скопировать файл.\n\n"
                        f"Причина: {error}\n\nОригинальный файл не изменён."
                    )
        except queue.Empty:
            pass
        self.after(150, self.poll_import_queue)

    def maybe_offer_legacy_import(self) -> None:
        marker = transcription_data_root() / ".import-offered"
        if marker.exists():
            return
        candidates = legacy_data_candidates()
        if not candidates:
            return
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch(exist_ok=True)
        if messagebox.askyesno(
            "Импорт прежних данных",
            "Найдены прежние input/output или модели. Выбрать папку для копирования? "
            "Исходные файлы останутся на месте; совпадающие файлы будут пропущены.",
        ):
            self.choose_legacy_import(candidates[0])

    def choose_legacy_import(self, initial: Path | None = None) -> None:
        selected = filedialog.askdirectory(
            title="Выберите папку с прежними input/output и моделями",
            initialdir=str(initial or Path.home() / "Documents"),
        )
        if not selected:
            return
        source = Path(selected)
        if not has_legacy_data(source):
            self.show_error("В выбранной папке нет данных Transcriber 9000 для импорта.")
            return
        self.set_status("Копирую прежние данные без удаления и перезаписи…")
        threading.Thread(target=self._legacy_import_worker, args=(source,), daemon=True).start()

    def _legacy_import_worker(self, source: Path) -> None:
        try:
            result = copy_legacy_data(source, transcription_data_root())
            self.legacy_import_queue.put(("done", result))
        except Exception as exc:
            self.legacy_import_queue.put(("error", str(exc)))

    def poll_legacy_import_queue(self) -> None:
        try:
            while True:
                kind, value = self.legacy_import_queue.get_nowait()
                if kind == "done":
                    self.refresh_environment()
                    messagebox.showinfo(
                        "Импорт завершён",
                        f"Скопировано файлов: {value.copied}. Пропущено совпадений: {value.skipped}. "
                        "Исходные файлы не изменены.",
                    )
                else:
                    self.show_error(f"Импорт не завершён: {value}")
        except queue.Empty:
            pass
        self.after(200, self.poll_legacy_import_queue)

    def set_import_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.choose_button.configure(state=state)
        self.start_button.configure(state=state)
        self.drop_signal.configure(
            text="● Копирование" if busy else ("● Файл готов" if self.selected_file else "Аудио или видео"),
            text_color=AMBER if busy or self.selected_file else MUTED,
        )
        self.drop_hint.configure(
            text="Копирую файл. Оригинал останется на месте."
            if busy
            else (
                "Перетащите файл или выберите его с компьютера."
                if getattr(self, "dnd_enabled", DND_ENABLED)
                else "Выберите файл с компьютера."
            ),
            text_color=AMBER if busy else DIM,
        )

    def set_selected_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            self.show_error(f"Файл не найден:\n{resolved}")
            return
        if not is_inside_input(resolved):
            self.show_error(f"Не удалось подготовить файл к обработке:\n{resolved}")
            return
        self.selected_file = resolved
        self.file_label.configure(text=resolved.name)
        suffix = resolved.suffix.lstrip(".").upper() or "ФАЙЛ"
        self.file_meta_label.configure(text=f"{suffix} · {format_bytes(resolved.stat().st_size)}")
        self.hide_report_action()
        self.created_result_paths = []
        self.report_transcript_path = None
        self.report_output_path = None
        self.waveform_request_id += 1
        request_id = self.waveform_request_id
        self.waveform_values = None
        self._draw_waveform()
        threading.Thread(target=self._waveform_worker, args=(resolved, request_id), daemon=True).start()
        self.render_ui_state(UIState.FILE_SELECTED)
        self.append_log(f"Выбран файл: {resolved}")

    def on_quality_change(self, value: str) -> None:
        for key, note in QUALITY_NOTES.items():
            if note == value:
                self.quality_var.set(key)
                break
        self.update_quality_state()

    def selected_formats(self) -> list[str]:
        formats: list[str] = []
        if self.txt_var.get():
            formats.append("txt")
        if self.srt_var.get():
            formats.append("srt")
        return formats

    def start_transcription(self) -> None:
        if self.active_process:
            return
        if self.import_in_progress:
            self.show_error("Дождитесь окончания копирования файла.")
            return
        if not self.selected_file:
            self.show_error("Файл не выбран.\n\nВыберите или перетащите аудио или видео.")
            return
        if not self.selected_file.exists():
            self.show_error("Выбранный файл больше не существует. Выберите его заново.")
            self.selected_file = None
            return

        formats = self.selected_formats()
        if not formats:
            self.show_error("Не выбран формат результата.\n\nОтметьте TXT, SRT или оба формата.")
            return

        quality_key = self.quality_var.get()
        model_name = QUALITY_OPTIONS[quality_key][1]
        model_state = get_model_file_state(model_name)
        if not model_state["installed"]:
            self.show_service_view()
            problem = "повреждена" if model_state["damaged"] else "не установлена"
            self.show_error(f"Модель {model_name} {problem}.\n\nСкачайте её в разделе «Настройки».")
            return

        run_dir = RUNS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = run_dir / "status.txt"
        self.result_json = run_dir / "result.json"
        self.last_status_count = 0

        args = build_transcription_command(
            self.selected_file,
            self.language_var.get(),
            quality_key,
            self.status_file,
            self.result_json,
            formats,
        )

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if os.name == "nt":
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            self.active_process = subprocess.Popen(
                args,
                cwd=APP_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                start_new_session=os.name != "nt",
                env=env,
            )
            self.active_process_kind = "transcription"
            self._start_pipe_capture(self.active_process)
        except OSError as exc:
            self.show_transcription_error(f"Не удалось запустить обработчик: {exc}")
            return

        self.set_busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.render_ui_state(UIState.TRANSCRIBING, "Подготавливаю распознавание…")
        self.append_log(f"Старт: {self.selected_file}")

    def poll_process(self) -> None:
        if self.active_process_kind == "transcription":
            self.read_status_lines()
        process = self.active_process
        if process and process.poll() is not None:
            exit_code = process.returncode
            process_kind = self.active_process_kind
            for pipe_thread in self.active_pipe_threads:
                pipe_thread.join(timeout=2.0)
            process_stdout = "".join(self.active_stdout_chunks)
            process_stderr = "".join(self.active_stderr_chunks)
            self.active_process = None
            self.active_process_kind = None
            self.active_pipe_threads = []
            self.active_stdout_chunks = []
            self.active_stderr_chunks = []
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)
            self.set_busy(False)
            if process_kind == "transcription":
                if process_stderr.strip():
                    self.append_log(process_stderr.strip())
                self.read_status_lines()
                self.finish_transcription(exit_code)
            elif process_kind == "report":
                self.finish_report(exit_code, process_stdout, process_stderr)
        self.after(500, self.poll_process)

    @staticmethod
    def _drain_pipe(stream, chunks: list[str]) -> None:
        if stream is None:
            return
        try:
            value = stream.read()
            if value:
                chunks.append(value)
        finally:
            stream.close()

    def _start_pipe_capture(self, process: subprocess.Popen) -> None:
        self.active_stdout_chunks = []
        self.active_stderr_chunks = []
        self.active_pipe_threads = [
            threading.Thread(
                target=Transcriber9000App._drain_pipe,
                args=(getattr(process, "stdout", None), self.active_stdout_chunks),
                daemon=True,
            ),
            threading.Thread(
                target=Transcriber9000App._drain_pipe,
                args=(getattr(process, "stderr", None), self.active_stderr_chunks),
                daemon=True,
            ),
        ]
        for pipe_thread in self.active_pipe_threads:
            pipe_thread.start()

    def read_status_lines(self) -> None:
        if not self.status_file or not self.status_file.exists():
            return
        try:
            lines = self.status_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[self.last_status_count :]:
            clean = line.removeprefix("STATUS:").strip()
            if clean:
                self.set_status(friendly_transcription_status(clean))
                self.append_log(clean)
        self.last_status_count = len(lines)

    def finish_transcription(self, exit_code: int) -> None:
        if not self.result_json or not self.result_json.exists():
            self.show_transcription_error(
                f"Обработчик завершился с кодом {exit_code}, но не записал результат."
            )
            return
        try:
            payload = json.loads(self.result_json.read_text(encoding="utf-8"))
        except Exception as exc:
            self.show_transcription_error(f"Не удалось прочитать результат обработки: {exc}")
            return

        if not payload.get("success"):
            self.show_transcription_error(
                str(payload.get("error") or f"Обработчик завершился с кодом {exit_code}.")
            )
            return

        created = payload.get("created_files", [])
        self.created_result_paths = [Path(path).resolve() for path in created]
        self.append_log("Созданы файлы:")
        for path in self.created_result_paths:
            self.append_log(str(path))
        if self.log_is_open:
            self.toggle_log()
        self.render_result_files()
        self.refresh_environment()

        transcript = first_txt_result(self.created_result_paths)
        if transcript is not None:
            self.render_ui_state(UIState.REPORT_STARTING)
            self.prepare_report_for_transcript(transcript)
        else:
            self.hide_report_action()
            self.render_ui_state(UIState.READY)

    def render_result_files(self) -> None:
        paths = list(self.created_result_paths)
        if self.report_output_path and self.report_output_path not in paths:
            paths.append(self.report_output_path)
        labels = {
            ".txt": "Расшифровка (TXT)",
            ".srt": "Субтитры (SRT)",
            ".md": "AI-отчёт (Markdown)",
        }
        names = "\n".join(
            f"✓  {labels.get(path.suffix.lower(), 'Файл')}   ·   {path.name}" for path in paths
        )
        self.result_label.configure(text=names)

    def hide_report_action(self) -> None:
        self.report_action = None
        if hasattr(self, "report_action_button"):
            self.report_action_button.grid_forget()

    def show_report_action(self, text: str, action: str) -> None:
        self.report_action = action
        self.report_action_button.configure(text=text, state="normal")

    def prepare_report_for_transcript(self, transcript: Path) -> None:
        self.report_transcript_path = transcript.resolve()
        self.report_output_path = None
        self.hide_report_action()
        if MACOS_REPORTS_UNAVAILABLE:
            self.append_log("AI-отчёты недоступны на macOS в этом релиз-кандидате.")
            self.render_ui_state(UIState.READY)
            self.status_detail_label.configure(
                text="TXT сохранён. AI-отчёты пока недоступны на macOS."
            )
            return
        try:
            existing_report = expected_report_path(self.report_transcript_path)
        except (OSError, ValueError, ReportPipelineError) as exc:
            self.append_log(f"AI-отчёт недоступен: {exc}")
            self.render_ui_state(UIState.REPORT_ERROR, str(exc))
            return

        if existing_report.exists():
            self.report_output_path = existing_report.resolve()
            self.render_result_files()
            self.show_report_action("Открыть AI-отчёт", "open")
            self.append_log(f"AI-отчёт уже существует: {self.report_output_path}")
            self.render_ui_state(UIState.READY)
            return

        if active_report_model_path() is None:
            self.show_report_action("Установить AI-модель", "open_model_settings")
            self.append_log("AI-отчёт не запущен: AI-модель не выбрана или не установлена.")
            self.render_ui_state(
                UIState.REPORT_ERROR,
                "Для AI-отчёта установите и выберите модель в Настройках. Транскрипция уже сохранена.",
            )
            return

        if report_runtime_available("cuda"):
            self.start_report("cuda")
            return

        if report_runtime_available("cpu"):
            self.show_report_action("Создать AI-отчёт на CPU", "start_cpu")
            self.append_log("CUDA path для AI-отчёта недоступен. Доступен медленный CPU fallback.")
            self.render_ui_state(UIState.CPU_FALLBACK)
            return

        self.append_log("AI-отчёт не запущен: не найден готовый CUDA или CPU runtime.")
        self.render_ui_state(UIState.REPORT_ERROR, "Runtime AI-отчёта не подготовлен.")

    def handle_report_action(self) -> None:
        if self.report_action == "open" and self.report_output_path:
            self.open_file(self.report_output_path)
        elif self.report_action in {"start_cpu", "retry_cpu"}:
            self.start_report("cpu")
        elif self.report_action == "retry_transcription":
            self.start_transcription()
        elif self.report_action == "open_model_settings":
            self.show_service_view()

    def start_report(self, device: str) -> None:
        if self.active_process or not self.report_transcript_path:
            return
        if not report_runtime_available(device):
            self.append_log(f"Не найден готовый {device.upper()} runtime для AI-отчёта.")
            self.hide_report_action()
            self.render_ui_state(UIState.REPORT_ERROR, f"Недоступен {device.upper()} runtime.")
            return

        try:
            args = build_report_command(self.report_transcript_path, device)
        except ReportModelError as exc:
            self.finish_report_error(device, str(exc))
            return
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if os.name == "nt":
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        env = build_report_environment(device)
        try:
            self.active_process = subprocess.Popen(
                args,
                cwd=APP_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                start_new_session=os.name != "nt",
                env=env,
            )
            self.active_process_kind = "report"
            self.active_report_device = device
            Transcriber9000App._start_pipe_capture(self, self.active_process)
        except OSError as exc:
            self.finish_report_error(device, f"Не удалось запустить report pipeline: {exc}")
            return

        self.hide_report_action()
        self.set_busy(True, operation="report")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        device_label = "CUDA" if device == "cuda" else "CPU"
        self.render_ui_state(UIState.REPORT_GENERATING)
        self.append_log(f"AI-отчёт: запуск {device_label} для {self.report_transcript_path.name}")

    def finish_report(self, exit_code: int, stdout: str, stderr: str) -> None:
        device = self.active_report_device or "cuda"
        self.active_report_device = None
        if exit_code != 0:
            detail = stderr.strip() or stdout.strip() or f"report pipeline завершился с кодом {exit_code}"
            self.finish_report_error(device, detail)
            return
        try:
            payload = json.loads(stdout)
            output_value = payload.get("output_path")
            if not isinstance(output_value, str) or not output_value.strip():
                raise ValueError("в результате отсутствует output_path")
            output_path = Path(output_value).resolve()
            if not output_path.is_file():
                raise ValueError(f"файл отчёта не найден: {output_path}")
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            self.finish_report_error(device, f"Не удалось прочитать результат report pipeline: {exc}")
            return

        self.report_output_path = output_path
        self.render_result_files()
        self.show_report_action("Открыть AI-отчёт", "open")
        self.append_log(f"AI-отчёт создан: {output_path}")
        self.render_ui_state(UIState.READY)

    def finish_report_error(self, device: str, detail: str) -> None:
        self.active_report_device = None
        self.append_log("Ошибка AI-отчёта: " + detail.replace("\n", " "))
        if device == "cuda" and report_runtime_available("cpu"):
            self.show_report_action("Повторить на CPU", "retry_cpu")
        else:
            self.hide_report_action()
        self.render_ui_state(UIState.REPORT_ERROR, detail)

    def refresh_environment(self) -> None:
        status = check_environment()
        checks = list(status["checks"])
        if is_frozen():
            checks = [check for check in checks if check["name"] != "venv python"]
            checks.append({"name": "packaged runtime", "ok": True, "detail": str(Path(sys.executable).resolve())})
        checks_ok = all(check["ok"] for check in checks)
        self.ready_badge.configure(
            text="● Готово к работе" if checks_ok else "● Требуется настройка",
            fg_color="transparent",
            text_color=GOOD if checks_ok else WARN,
        )
        lines = [
            f"Приложение: {status['app']}",
            f"Папка: {status['app_dir']}",
            f"Устройство: {status['device_label']}",
            "",
            "Проверки:",
        ]
        for check in checks:
            marker = "OK" if check["ok"] else "Нужно исправить"
            lines.append(f"- {marker}: {check['name']} - {check['detail']}")
        lines.extend(["", "Модели:"])
        for model in status["models"]:
            marker = "установлена" if model["installed"] else "не установлена"
            lines.append(f"- {model['model']}: {marker}, {format_bytes(model['bytes'])}")
        self.ready_text.delete("1.0", "end")
        self.ready_text.insert("1.0", "\n".join(lines))
        self.update_model_rows(status["models"])
        self.update_report_model_rows()
        self.update_quality_state()

    def update_model_rows(self, models: list[dict]) -> None:
        for model in models:
            name = model["model"]
            installed = model["installed"]
            damaged = model.get("damaged", False)
            bytes_count = int(model["bytes"])
            label = self.model_status_labels.get(name)
            button = self.download_buttons.get(name)
            detail = self.model_detail_labels.get(name)
            if label:
                if installed:
                    text = "Установлена\n" + format_bytes(bytes_count)
                elif damaged:
                    text = "Повреждена\n" + format_bytes(bytes_count)
                else:
                    text = f"Не установлена\n~{model['size_mb']} MB"
                label.configure(text=text, text_color=GOOD if installed else WARN)
            if button:
                button.configure(
                    text="Скачать заново" if installed or damaged else "Скачать",
                    state="normal",
                    fg_color=AMBER,
                    text_color=BG,
                    border_color=AMBER,
                )
            if detail:
                detail.configure(text=f"{model['summary']} — {model['recommendation']}")

    def update_quality_state(self) -> None:
        quality_key = self.quality_var.get()
        model_name = QUALITY_OPTIONS[quality_key][1]
        model_state = get_model_file_state(model_name)
        self.quality_state.configure(
            text=QUALITY_NOTES[quality_key],
            text_color=GOOD if model_state["installed"] else WARN,
        )

    def update_report_model_rows(self) -> None:
        for status in self.report_model_manager.statuses():
            model_id = status.model.model_id
            busy = self.report_model_busy.get(model_id)
            label = self.report_model_status_labels.get(model_id)
            primary = self.report_model_primary_buttons.get(model_id)
            select = self.report_model_select_buttons.get(model_id)
            delete = self.report_model_delete_buttons.get(model_id)
            if busy:
                state_text = "Скачивается…" if busy == "download" else "Проверяется…"
            elif status.active:
                state_text = "Активна"
            elif status.state == "installed":
                state_text = "Установлена"
            elif status.state == "unverified":
                state_text = "Требует проверки"
            elif status.state == "corrupted":
                state_text = "Повреждена"
            else:
                state_text = "Не установлена"
            if label:
                label.configure(
                    text="Недоступно на macOS" if MACOS_REPORTS_UNAVAILABLE else f"{state_text} · {format_bytes(status.bytes_count or status.model.size_bytes)}",
                    text_color=GOOD if status.installed else (AMBER if busy else WARN),
                )
            if primary:
                if busy == "download":
                    primary.configure(text="Отмена", state="normal")
                elif busy == "verify":
                    primary.configure(text="Проверка", state="disabled")
                elif status.state in {"installed", "unverified"}:
                    primary.configure(text="Проверить", state="normal")
                else:
                    primary.configure(text="Скачать", state="normal")
            if select:
                select.configure(
                    text="Выбрана" if status.active else "Выбрать",
                    state="disabled" if busy or status.active or not status.installed else "normal",
                )
            if delete:
                delete.configure(
                    state="disabled" if busy or status.state == "not_installed" else "normal"
                )
            if MACOS_REPORTS_UNAVAILABLE:
                for button in (primary, select, delete):
                    if button:
                        button.configure(state="disabled")

    def handle_report_model_primary(self, model_id: str) -> None:
        if MACOS_REPORTS_UNAVAILABLE:
            return
        busy = self.report_model_busy.get(model_id)
        if busy == "download":
            event = self.report_model_cancel_events.get(model_id)
            if event is not None:
                event.set()
            button = self.report_model_primary_buttons.get(model_id)
            if button:
                button.configure(text="Отмена…", state="disabled")
            return
        if busy:
            return
        status = self.report_model_manager.status(model_id)
        operation = "verify" if status.state in {"installed", "unverified"} else "download"
        cancel_event = threading.Event()
        self.report_model_cancel_events[model_id] = cancel_event
        self.report_model_busy[model_id] = operation
        self.update_report_model_rows()
        threading.Thread(
            target=self._report_model_worker,
            args=(model_id, operation, cancel_event),
            daemon=True,
        ).start()

    def _report_model_worker(
        self,
        model_id: str,
        operation: str,
        cancel_event: threading.Event,
    ) -> None:
        def progress(done: int, total: int) -> None:
            self.report_model_queue.put(("progress", model_id, done, total))

        try:
            if operation == "download":
                self.report_model_manager.download(
                    model_id,
                    progress=progress,
                    cancel_event=cancel_event,
                )
            else:
                self.report_model_manager.verify(model_id, progress=progress)
            self.report_model_queue.put(("done", model_id, operation))
        except ReportModelDownloadCancelled:
            self.report_model_queue.put(("cancelled", model_id))
        except Exception as exc:
            self.report_model_queue.put(("error", model_id, str(exc)))

    def poll_report_model_queue(self) -> None:
        try:
            while True:
                item = self.report_model_queue.get_nowait()
                kind = item[0]
                model_id = item[1]
                if kind == "progress":
                    _, _, done, total = item
                    button = self.report_model_primary_buttons.get(model_id)
                    if button:
                        button.configure(text=f"{int(done * 100 / total)}%" if total else format_bytes(done))
                elif kind == "done":
                    _, _, operation = item
                    self.report_model_busy.pop(model_id, None)
                    self.report_model_cancel_events.pop(model_id, None)
                    action = "скачана и проверена" if operation == "download" else "проверена"
                    self.append_log(f"AI-модель {self.report_model_manager.model(model_id).name} {action}.")
                    self.refresh_environment()
                elif kind == "cancelled":
                    self.report_model_busy.pop(model_id, None)
                    self.report_model_cancel_events.pop(model_id, None)
                    self.append_log("Скачивание AI-модели отменено.")
                    self.update_report_model_rows()
                elif kind == "error":
                    _, _, error = item
                    self.report_model_busy.pop(model_id, None)
                    self.report_model_cancel_events.pop(model_id, None)
                    self.update_report_model_rows()
                    self.show_error(f"Операция с AI-моделью не выполнена.\n\nПричина: {error}")
        except queue.Empty:
            pass
        self.after(200, self.poll_report_model_queue)

    def select_report_model(self, model_id: str) -> None:
        if MACOS_REPORTS_UNAVAILABLE:
            return
        try:
            self.report_model_manager.select(model_id)
        except ReportModelError as exc:
            self.show_error(str(exc))
            return
        self.append_log(f"Выбрана AI-модель: {self.report_model_manager.model(model_id).name}")
        self.refresh_environment()

    def delete_report_model(self, model_id: str) -> None:
        if MACOS_REPORTS_UNAVAILABLE:
            return
        if self.active_process_kind == "report" and self.active_process is not None:
            self.show_error("Нельзя удалить AI-модель, пока создаётся отчёт.")
            return
        model = self.report_model_manager.model(model_id)
        if not messagebox.askyesno("Удалить AI-модель", f"Удалить скачанную модель {model.name}?"):
            return
        try:
            self.report_model_manager.delete(model_id)
        except ReportModelError as exc:
            self.show_error(str(exc))
            return
        self.append_log(f"AI-модель удалена: {model.name}")
        self.refresh_environment()

    def download_model(self, model_name: str) -> None:
        model_state = get_model_file_state(model_name)
        size_mb = MODEL_INFO[model_name]["size_mb"]
        replacement = " Существующий файл будет заменён только после проверки SHA-256." if model_state["bytes"] else ""
        if not messagebox.askyesno(
            "Загрузка модели Whisper",
            f"Скачать модель {model_name} (около {size_mb} MB)?{replacement}\n\nЗагрузка использует сеть; медиа останется локально.",
        ):
            return

        button = self.download_buttons.get(model_name)
        if button:
            button.configure(text="Скачивается", state="disabled")
        self.append_log(f"Скачивание модели {model_name}.")
        threading.Thread(target=self._download_worker, args=(model_name,), daemon=True).start()

    def _download_worker(self, model_name: str) -> None:
        url = MODEL_DOWNLOAD_URLS[model_name]
        expected_hash = url.rstrip("/").split("/")[-2]
        target = CACHE_DIR / f"{model_name}.pt"
        temp = CACHE_DIR / f"{model_name}.{uuid.uuid4().hex}.pt.download"
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            prune_stale_whisper_downloads(CACHE_DIR, (model_name,))
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                with temp.open("wb") as file:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        file.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        self.download_queue.put(("progress", model_name, done, total))
            actual_hash = digest.hexdigest()
            if expected_hash and actual_hash.lower() != expected_hash.lower():
                raise ValueError("контрольная сумма модели не совпала")
            temp.replace(target)
            self.download_queue.put(("done", model_name))
        except Exception as exc:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass
            self.download_queue.put(("error", model_name, str(exc)))

    def poll_download_queue(self) -> None:
        try:
            while True:
                item = self.download_queue.get_nowait()
                kind = item[0]
                model_name = item[1]
                button = self.download_buttons.get(model_name)
                if kind == "progress":
                    _, _, done, total = item
                    if button:
                        button.configure(text=f"{int(done * 100 / total)}%" if total else format_bytes(done))
                elif kind == "done":
                    self.append_log(f"Модель {model_name} скачана.")
                    self.refresh_environment()
                elif kind == "error":
                    _, _, error = item
                    if button:
                        button.configure(text="Скачать", state="normal")
                    self.show_error(f"Не удалось скачать модель {model_name}.\n\nПричина: {error}")
        except queue.Empty:
            pass
        self.after(300, self.poll_download_queue)

    def set_busy(self, busy: bool, operation: str = "transcription") -> None:
        state = "disabled" if busy else "normal"
        if busy and operation == "report":
            button_text = "AI-отчёт создаётся…"
        elif busy:
            button_text = "Расшифровка идёт…"
        else:
            button_text = "Начать обработку"
        self.start_button.configure(state=state, text=button_text)
        self.quality_menu.configure(state=state)
        self.language_segment.configure(state=state)
        self.txt_checkbox.configure(state=state)
        self.srt_checkbox.configure(state=state)
        self.choose_button.configure(state=state)

    def set_status(self, text: str) -> None:
        self.status_detail_label.configure(text=text)

    def append_log(self, text: str) -> None:
        self.log_box.insert("end", text.rstrip() + "\n")
        self.log_box.see("end")

    def toggle_log(self) -> None:
        self.log_is_open = not self.log_is_open
        if self.log_is_open:
            self.log_box.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 16))
            self.log_toggle_button.configure(text="Скрыть детали")
        else:
            self.log_box.grid_forget()
            self.log_toggle_button.configure(text="Подробности")

    def show_transcription_error(self, detail: str) -> None:
        self.append_log("Ошибка расшифровки: " + detail.replace("\n", " "))
        self.render_result_files()
        self.render_ui_state(UIState.TRANSCRIPTION_ERROR, detail)

    def show_error(self, text: str) -> None:
        self.set_status("Ошибка. Подробности показаны в сообщении.")
        self.append_log("Ошибка: " + text.replace("\n", " "))
        messagebox.showerror("Ошибка", text)

    @staticmethod
    def open_folder(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            os.startfile(path)  # type: ignore[attr-defined]

    @staticmethod
    def open_file(path: Path) -> None:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            os.startfile(path)  # type: ignore[attr-defined]

    def _waveform_worker(self, path: Path, request_id: int) -> None:
        if not FFMPEG_EXE.exists():
            self.waveform_queue.put(("error", request_id, "ffmpeg не найден"))
            return

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        args = [
            str(FFMPEG_EXE),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "200",
            "-f",
            "s16le",
            "pipe:1",
        ]
        try:
            completed = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                check=False,
            )
            if completed.returncode != 0 or len(completed.stdout) < 2:
                detail = completed.stderr.decode("utf-8", errors="replace").strip()
                self.waveform_queue.put(("error", request_id, detail or "аудиодорожка не найдена"))
                return

            raw = completed.stdout[: len(completed.stdout) - (len(completed.stdout) % 2)]
            samples = array("h")
            samples.frombytes(raw)
            if sys.byteorder != "little":
                samples.byteswap()
            if not samples:
                self.waveform_queue.put(("error", request_id, "аудиодорожка пуста"))
                return

            bin_count = 96
            sample_count = len(samples)
            peaks: list[int] = []
            for index in range(bin_count):
                start = index * sample_count // bin_count
                end = max(start + 1, (index + 1) * sample_count // bin_count)
                chunk = samples[start:end]
                peaks.append(max((abs(value) for value in chunk), default=0))

            nonzero = sorted(value for value in peaks if value > 0)
            if not nonzero:
                values = [0.0] * bin_count
            else:
                reference_index = min(len(nonzero) - 1, int(len(nonzero) * 0.9))
                reference = max(nonzero[reference_index], 1)
                values = [min(1.0, value / reference) for value in peaks]
            self.waveform_queue.put(("done", request_id, values))
        except Exception as exc:
            self.waveform_queue.put(("error", request_id, str(exc)))

    def poll_waveform_queue(self) -> None:
        try:
            while True:
                item = self.waveform_queue.get_nowait()
                kind, request_id = item[0], item[1]
                if request_id != self.waveform_request_id:
                    continue
                if kind == "done":
                    self.waveform_values = item[2]
                    self._draw_waveform()
                elif kind == "error":
                    self.waveform_values = []
                    self._draw_waveform()
                    self.append_log(f"Форма звука недоступна: {item[2]}")
        except queue.Empty:
            pass
        self.after(150, self.poll_waveform_queue)

    def _draw_waveform(self, _event=None) -> None:
        self.waveform.delete("all")
        width = max(self.waveform.winfo_width(), 120)
        height = max(self.waveform.winfo_height(), round(28 * UI_SCALE))
        center = height / 2

        if self.ui_state is UIState.READY:
            waveform_color = GOOD
        elif self.ui_state in {UIState.TRANSCRIPTION_ERROR, UIState.REPORT_ERROR}:
            waveform_color = ERROR
        elif self.ui_state in {
            UIState.TRANSCRIBING,
            UIState.REPORT_STARTING,
            UIState.REPORT_GENERATING,
        }:
            waveform_color = AMBER
        else:
            waveform_color = DIM

        if not self.selected_file:
            self.waveform.create_line(0, center, width, center, fill=BORDER, width=1)
            return

        if self.waveform_values is None:
            self.waveform.create_line(0, center, width, center, fill=BORDER, width=1)
            self.waveform.create_text(
                width / 2,
                center,
                text="Анализирую звук…",
                fill=DIM,
                font=(self.fonts.mono, 9, "bold"),
            )
            return

        if not self.waveform_values or not any(self.waveform_values):
            self.waveform.create_line(0, center, width, center, fill=BORDER, width=1)
            self.waveform.create_text(
                width / 2,
                center,
                text="Аудиодорожка не найдена",
                fill=DIM,
                font=(self.fonts.mono, 9, "bold"),
            )
            return

        gap = width / (len(self.waveform_values) + 1)
        usable_height = max(height - 10, 8)
        for index, value in enumerate(self.waveform_values, start=1):
            x = index * gap
            bar_height = max(2.0, value * usable_height)
            self.waveform.create_line(
                x,
                center - bar_height / 2,
                x,
                center + bar_height / 2,
                fill=waveform_color,
                width=2,
            )

    def _register_drop_targets(self, *widgets) -> None:
        for widget in widgets:
            candidates = [widget]
            for attribute in ("_canvas", "_label"):
                inner = getattr(widget, attribute, None)
                if inner is not None:
                    candidates.append(inner)
            for candidate in candidates:
                try:
                    candidate.drop_target_register(DND_FILES)
                    candidate.dnd_bind("<<Drop>>", self.handle_drop)
                except (AttributeError, tk.TclError):
                    continue

    def on_close(self) -> None:
        for cancel_event in getattr(self, "report_model_cancel_events", {}).values():
            cancel_event.set()
        if self.active_process and self.active_process.poll() is None:
            process_kind = self.active_process_kind
            operation = "AI-отчёт" if process_kind == "report" else "расшифровка"
            should_stop = messagebox.askyesno(
                f"{operation.capitalize()} ещё выполняется",
                f"Остановить текущую операцию «{operation}» и закрыть приложение?",
            )
            if not should_stop:
                return
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(self.active_process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        check=False,
                    )
                else:
                    os.killpg(self.active_process.pid, signal.SIGTERM)
            except OSError:
                pass
        self.destroy()


def run_smoke_test() -> int:
    status = check_environment()
    try:
        import customtkinter  # noqa: F401
    except Exception as exc:
        print("GUI_SMOKE_TEST_FAILED")
        print(f"missing: customtkinter ({exc})")
        return 1
    print("GUI_SMOKE_TEST_OK")
    print(f"app: {APP_TITLE}")
    print(f"dnd: {'enabled' if DND_ENABLED else 'disabled'}")
    print(f"device: {status['device']} ({status['device_label']})")
    print("models: " + (", ".join(status["installed_models"]) or "none"))
    return 0


def main() -> int:
    if "--smoke-test" in sys.argv:
        return run_smoke_test()
    app = Transcriber9000App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
