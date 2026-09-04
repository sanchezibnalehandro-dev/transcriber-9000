from __future__ import annotations

from array import array
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

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
            self.TkdndVersion = TkinterDnD._require(self)

    DND_ENABLED = True
except Exception:
    DND_FILES = ""
    TranscriberWindow = ctk.CTk
    DND_ENABLED = False


BG = "#0B0D0F"
PANEL = "#111416"
CARD = "#171A1D"
CARD_2 = "#1E2226"
BORDER = "#34393E"
TEXT = "#F2EFE7"
MUTED = "#8B9298"
DIM = "#626970"
AMBER = "#FFB000"
AMBER_HOVER = "#D99500"
GOOD = "#78D6A3"
WARN = "#FFCA62"

UI_SCALE = 1.25
WINDOW_SIZE = "1340x900"
MIN_WINDOW_SIZE = (1200, 820)
RUNS_DIR = APP_DIR / ".cache" / "transcriber" / "runs"

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


class Transcriber9000App(TranscriberWindow):
    """Desktop shell for the local Whisper transcription workflow."""

    def __init__(self) -> None:
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
        super().__init__()

        self.title(APP_TITLE)
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)

        self.selected_file: Path | None = None
        self.active_process: subprocess.Popen | None = None
        self.status_file: Path | None = None
        self.result_json: Path | None = None
        self.last_status_count = 0
        self.import_in_progress = False
        self.log_is_open = False
        self.active_view = "work"
        self.waveform_values: list[float] | None = None
        self.waveform_request_id = 0

        self.download_queue: queue.Queue[tuple] = queue.Queue()
        self.import_queue: queue.Queue[tuple] = queue.Queue()
        self.waveform_queue: queue.Queue[tuple] = queue.Queue()
        self.download_buttons: dict[str, ctk.CTkButton] = {}
        self.model_status_labels: dict[str, ctk.CTkLabel] = {}
        self.model_detail_labels: dict[str, ctk.CTkLabel] = {}

        self.language_var = ctk.StringVar(value="ru")
        self.quality_var = ctk.StringVar(value="balanced")
        self.txt_var = ctk.BooleanVar(value=True)
        self.srt_var = ctk.BooleanVar(value=False)

        self._build_layout()

        dpi_scaling = max(ctk.ScalingTracker.get_window_dpi_scaling(self), 1.0)
        ctk.set_widget_scaling(UI_SCALE / dpi_scaling)
        ctk.set_window_scaling(UI_SCALE / dpi_scaling)
        self.minsize(*MIN_WINDOW_SIZE)
        self.geometry(WINDOW_SIZE)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_environment()
        self.after(500, self.poll_process)
        self.after(300, self.poll_download_queue)
        self.after(150, self.poll_import_queue)
        self.after(150, self.poll_waveform_queue)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(20, 14))
        header.grid_columnconfigure(1, weight=1)

        brand = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        brand.grid(row=0, column=0, rowspan=2, sticky="w")
        ctk.CTkLabel(
            brand,
            text="ТРАНСКРИБАТОР / 9000",
            font=ctk.CTkFont("Bahnschrift", 31, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")

        header_actions = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        header_actions.grid(row=0, column=1, sticky="e")
        self.ready_badge = ctk.CTkLabel(
            header_actions,
            text="Проверка системы",
            fg_color=CARD,
            corner_radius=4,
            padx=14,
            pady=7,
            text_color=MUTED,
            font=ctk.CTkFont("Consolas", 11, "bold"),
        )
        self.ready_badge.grid(row=0, column=0, padx=(0, 12))
        self.work_nav_button = self._button(
            header_actions,
            text="Работа",
            command=self.show_work_view,
            width=96,
            fg_color=AMBER,
            text_color=BG,
            border_color=AMBER,
        )
        self.work_nav_button.grid(row=0, column=1, padx=(0, 8))
        self.service_nav_button = self._button(
            header_actions,
            text="Сервис",
            command=self.show_service_view,
            width=96,
        )
        self.service_nav_button.grid(row=0, column=2)

        ctk.CTkLabel(
            header,
            text="Приватная расшифровка аудио и видео — файлы остаются на этом компьютере",
            font=ctk.CTkFont("Segoe UI Variable", 12),
            text_color=MUTED,
        ).grid(row=1, column=1, sticky="e", pady=(8, 0))

        self.view_host = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.view_host.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 26))
        self.view_host.grid_columnconfigure(0, weight=1)
        self.view_host.grid_rowconfigure(0, weight=1)

        self.work_view = ctk.CTkFrame(
            self.view_host,
            fg_color=PANEL,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        self.service_view = ctk.CTkFrame(
            self.view_host,
            fg_color=PANEL,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        self._build_work_view()
        self._build_service_view()
        self.show_work_view()

    def _button(self, master, **kwargs):
        defaults = {
            "height": 34,
            "corner_radius": 4,
            "fg_color": CARD_2,
            "hover_color": BORDER,
            "text_color": TEXT,
            "border_width": 1,
            "border_color": BORDER,
            "font": ctk.CTkFont("Segoe UI Variable", 12, "bold"),
        }
        defaults.update(kwargs)
        button = ctk.CTkButton(master, **defaults)
        self._add_focus_ring(button, defaults["border_color"])
        return button

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
        view.grid_columnconfigure(0, weight=3)
        view.grid_columnconfigure(1, weight=2)
        view.grid_rowconfigure(1, weight=1)

        intro = ctk.CTkFrame(view, fg_color="transparent", corner_radius=0)
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(20, 14))
        intro.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            intro,
            text="НОВАЯ РАСШИФРОВКА",
            font=ctk.CTkFont("Bahnschrift", 23, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            intro,
            text="Три шага до готового текста",
            font=ctk.CTkFont("Segoe UI Variable", 12),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self._button(
            intro,
            text="Открыть исходники",
            command=lambda: self.open_folder(INPUT_DIR),
            width=138,
            height=32,
        ).grid(row=0, column=1, rowspan=2, padx=(10, 8))
        self._button(
            intro,
            text="Открыть результаты",
            command=lambda: self.open_folder(OUTPUT_DIR),
            width=152,
            height=32,
        ).grid(row=0, column=2, rowspan=2)

        left = ctk.CTkFrame(view, fg_color="transparent", corner_radius=0)
        left.grid(row=1, column=0, sticky="nsew", padx=(24, 10), pady=(0, 22))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        self.drop_frame = ctk.CTkFrame(
            left,
            fg_color=CARD_2,
            border_color=AMBER,
            border_width=2,
            corner_radius=6,
        )
        self.drop_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.drop_frame.grid_columnconfigure(0, weight=1)

        step_one = ctk.CTkFrame(self.drop_frame, fg_color="transparent", corner_radius=0)
        step_one.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        step_one.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            step_one,
            text="01",
            width=34,
            height=26,
            fg_color=AMBER,
            text_color=BG,
            corner_radius=3,
            font=ctk.CTkFont("Consolas", 12, "bold"),
        ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(
            step_one,
            text="ИСТОЧНИК",
            font=ctk.CTkFont("Bahnschrift", 16, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=1, sticky="w")
        self.drop_signal = ctk.CTkLabel(
            step_one,
            text="● ОЖИДАНИЕ",
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=MUTED,
        )
        self.drop_signal.grid(row=0, column=2, sticky="e")

        self.waveform = tk.Canvas(
            self.drop_frame,
            height=round(68 * UI_SCALE),
            bg=CARD_2,
            highlightthickness=0,
            bd=0,
        )
        self.waveform.grid(row=1, column=0, sticky="ew", padx=20, pady=(6, 4))
        self.waveform.bind("<Configure>", self._draw_waveform)

        self.file_label = ctk.CTkLabel(
            self.drop_frame,
            text="ПЕРЕТАЩИТЕ АУДИО ИЛИ ВИДЕО СЮДА",
            font=ctk.CTkFont("Segoe UI Variable", 17, "bold"),
            text_color=TEXT,
        )
        self.file_label.grid(row=2, column=0, sticky="ew", padx=20, pady=(2, 0))
        self.file_meta_label = ctk.CTkLabel(
            self.drop_frame,
            text="Файл будет скопирован в папку исходников. Оригинал останется на месте.",
            font=ctk.CTkFont("Segoe UI Variable", 12),
            text_color=MUTED,
        )
        self.file_meta_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(2, 10))
        self.choose_button = self._button(
            self.drop_frame,
            text="Выбрать файл",
            command=self.choose_file,
            width=180,
            height=40,
            border_color=MUTED,
        )
        self.choose_button.grid(row=4, column=0, pady=(0, 14))
        self.drop_hint = ctk.CTkLabel(
            self.drop_frame,
            text=(
                "ПЕРЕТАСКИВАНИЕ ВКЛЮЧЕНО · ФАЙЛ БУДЕТ СКОПИРОВАН В ПАПКУ ИСХОДНИКОВ"
                if DND_ENABLED
                else "ПЕРЕТАСКИВАНИЕ НЕДОСТУПНО · ИСПОЛЬЗУЙТЕ КНОПКУ"
            ),
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=DIM,
        )
        self.drop_hint.grid(row=5, column=0, sticky="e", padx=20, pady=(0, 9))

        if DND_ENABLED:
            self._register_drop_targets(
                self.drop_frame,
                self.waveform,
                self.file_label,
                self.file_meta_label,
                self.choose_button,
                self.drop_hint,
            )

        self._build_status_panel(left)
        self._build_settings_panel(view)

    def _build_status_panel(self, master) -> None:
        status = ctk.CTkFrame(master, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=6)
        status.grid(row=1, column=0, sticky="nsew")
        status.grid_columnconfigure(0, weight=1)
        status.grid_rowconfigure(3, weight=1)

        status_head = ctk.CTkFrame(status, fg_color="transparent", corner_radius=0)
        status_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        status_head.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(
            status_head,
            text="Готов к работе. Выберите или перетащите файл.",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont("Segoe UI Variable", 12, "bold"),
        )
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.log_toggle_button = self._button(
            status_head,
            text="Показать журнал",
            command=self.toggle_log,
            width=126,
            height=28,
            fg_color="transparent",
            text_color=MUTED,
            font=ctk.CTkFont("Consolas", 10),
        )
        self.log_toggle_button.grid(row=0, column=1, padx=(12, 0))

        self.progress = ctk.CTkProgressBar(
            status,
            height=5,
            corner_radius=0,
            progress_color=AMBER,
            fg_color=CARD_2,
        )
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        self.result_frame = ctk.CTkFrame(
            status,
            fg_color="#13231B",
            corner_radius=4,
            border_width=1,
            border_color="#29563D",
        )
        self.result_frame.grid_columnconfigure(0, weight=1)
        self.result_label = ctk.CTkLabel(
            self.result_frame,
            text="",
            anchor="w",
            justify="left",
            text_color=GOOD,
            font=ctk.CTkFont("Consolas", 10),
        )
        self.result_label.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        self._button(
            self.result_frame,
            text="Открыть результаты",
            command=lambda: self.open_folder(OUTPUT_DIR),
            width=138,
            height=30,
            fg_color=GOOD,
            hover_color="#59B783",
            text_color=BG,
            border_color=GOOD,
        ).grid(row=0, column=1, padx=(8, 10), pady=8)

        self.log_box = ctk.CTkTextbox(
            status,
            height=112,
            fg_color=BG,
            text_color=MUTED,
            border_color=BORDER,
            border_width=1,
            corner_radius=4,
            font=ctk.CTkFont("Consolas", 10),
        )
        self.append_log("Журнал системы готов.")

    def _build_settings_panel(self, master) -> None:
        settings = ctk.CTkFrame(master, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=6)
        settings.grid(row=1, column=1, sticky="nsew", padx=(10, 24), pady=(0, 22))
        settings.grid_columnconfigure(0, weight=1)

        self._step_heading(settings, 0, "02", "ПАРАМЕТРЫ")
        ctk.CTkLabel(
            settings,
            text="Язык речи",
            height=20,
            font=ctk.CTkFont("Segoe UI Variable", 12, "bold"),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 4))
        self.language_segment = ctk.CTkSegmentedButton(
            settings,
            values=["русский", "авто"],
            command=lambda value: self.language_var.set("ru" if value == "русский" else "auto"),
            height=32,
            selected_color=AMBER,
            selected_hover_color=AMBER_HOVER,
            text_color=TEXT,
            unselected_color=CARD_2,
            unselected_hover_color=BORDER,
            font=ctk.CTkFont("Segoe UI Variable", 11, "bold"),
        )
        self.language_segment.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        self.language_segment.set("русский")

        ctk.CTkLabel(
            settings,
            text="Режим качества",
            height=20,
            font=ctk.CTkFont("Segoe UI Variable", 12, "bold"),
            text_color=MUTED,
        ).grid(row=3, column=0, sticky="w", padx=20, pady=(0, 4))
        self.quality_menu = ctk.CTkOptionMenu(
            settings,
            values=[QUALITY_NOTES[key] for key in QUALITY_OPTIONS],
            command=self.on_quality_change,
            height=32,
            corner_radius=4,
            fg_color=CARD_2,
            button_color=AMBER,
            button_hover_color=AMBER_HOVER,
            text_color=TEXT,
            font=ctk.CTkFont("Segoe UI Variable", 11),
        )
        self.quality_menu.grid(row=4, column=0, sticky="ew", padx=20)
        self.quality_menu.set(QUALITY_NOTES[self.quality_var.get()])
        self.quality_state = ctk.CTkLabel(
            settings,
            text="",
            height=20,
            text_color=DIM,
            font=ctk.CTkFont("Consolas", 10),
            anchor="w",
        )
        self.quality_state.grid(row=5, column=0, sticky="ew", padx=20, pady=(3, 10))

        ctk.CTkLabel(
            settings,
            text="Формат результата",
            height=20,
            font=ctk.CTkFont("Segoe UI Variable", 12, "bold"),
            text_color=MUTED,
        ).grid(row=6, column=0, sticky="w", padx=20, pady=(0, 5))
        self.txt_checkbox = ctk.CTkCheckBox(
            settings,
            text=FORMAT_OPTIONS["txt"],
            variable=self.txt_var,
            height=20,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=3,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            border_color=MUTED,
            text_color=TEXT,
        )
        self.txt_checkbox.grid(row=7, column=0, sticky="w", padx=20, pady=(0, 6))
        self.srt_checkbox = ctk.CTkCheckBox(
            settings,
            text=FORMAT_OPTIONS["srt"],
            variable=self.srt_var,
            height=20,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=3,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            border_color=MUTED,
            text_color=TEXT,
        )
        self.srt_checkbox.grid(row=8, column=0, sticky="w", padx=20, pady=(0, 10))

        ctk.CTkFrame(settings, height=1, fg_color=BORDER, corner_radius=0).grid(
            row=9, column=0, sticky="ew", padx=20, pady=(0, 10)
        )
        self._step_heading(settings, 10, "03", "ЗАПУСК", top_padding=0)
        self.start_button = self._button(
            settings,
            text="Запустить расшифровку",
            command=self.start_transcription,
            height=44,
            fg_color=AMBER,
            hover_color=AMBER_HOVER,
            text_color=BG,
            border_color=AMBER,
            font=ctk.CTkFont("Segoe UI Variable", 14, "bold"),
        )
        self.start_button.grid(row=11, column=0, sticky="ew", padx=20, pady=(0, 8))
        ctk.CTkLabel(
            settings,
            text="ОБРАБОТКА ВЫПОЛНЯЕТСЯ ЛОКАЛЬНО",
            height=20,
            font=ctk.CTkFont("Consolas", 9),
            text_color=DIM,
        ).grid(row=12, column=0, pady=(0, 8))

    @staticmethod
    def _step_heading(master, row: int, number: str, title: str, top_padding: int = 12) -> None:
        frame = ctk.CTkFrame(master, fg_color="transparent", corner_radius=0)
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=(top_padding, 10 if top_padding else 8))
        ctk.CTkLabel(
            frame,
            text=number,
            width=34,
            height=26,
            fg_color=CARD_2,
            text_color=AMBER,
            corner_radius=3,
            font=ctk.CTkFont("Consolas", 12, "bold"),
        ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont("Bahnschrift", 16, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=1, sticky="w")

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
            text="СЕРВИСНЫЙ ОТСЕК",
            font=ctk.CTkFont("Bahnschrift", 23, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            heading,
            text="Модели распознавания и состояние локальной системы",
            font=ctk.CTkFont("Segoe UI Variable", 12),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self._button(
            heading,
            text="Проверить систему",
            command=self.refresh_environment,
            width=140,
            height=32,
        ).grid(row=0, column=1, rowspan=2)

        models_panel = ctk.CTkScrollableFrame(
            view,
            fg_color=CARD,
            border_color=BORDER,
            border_width=1,
            corner_radius=6,
            label_text="МОДЕЛИ WHISPER",
            label_font=ctk.CTkFont("Bahnschrift", 15, "bold"),
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
                font=ctk.CTkFont("Bahnschrift", 19, "bold"),
                text_color=AMBER,
            ).grid(row=0, column=0, rowspan=2, padx=12, pady=12)
            ctk.CTkLabel(
                item,
                text=quality_label,
                font=ctk.CTkFont("Segoe UI Variable", 12, "bold"),
                text_color=TEXT,
            ).grid(row=0, column=1, sticky="w", pady=(11, 1))
            detail = ctk.CTkLabel(
                item,
                text=info["summary"],
                font=ctk.CTkFont("Segoe UI Variable", 10),
                text_color=MUTED,
                anchor="w",
            )
            detail.grid(row=1, column=1, sticky="ew", pady=(0, 11))
            self.model_detail_labels[model_name] = detail
            status = ctk.CTkLabel(
                item,
                text="",
                width=128,
                font=ctk.CTkFont("Consolas", 10, "bold"),
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

        ready_panel = ctk.CTkFrame(view, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=6)
        ready_panel.grid(row=1, column=1, sticky="nsew", padx=(10, 24), pady=(0, 22))
        ready_panel.grid_columnconfigure(0, weight=1)
        ready_panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            ready_panel,
            text="ДИАГНОСТИКА",
            font=ctk.CTkFont("Bahnschrift", 15, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 10))
        self.ready_text = ctk.CTkTextbox(
            ready_panel,
            fg_color=BG,
            text_color=MUTED,
            border_color=BORDER,
            border_width=1,
            corner_radius=4,
            font=ctk.CTkFont("Consolas", 10),
        )
        self.ready_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

    def show_work_view(self) -> None:
        self.active_view = "work"
        self.service_view.grid_forget()
        self.work_view.grid(row=0, column=0, sticky="nsew")
        self.work_nav_button.configure(fg_color=AMBER, text_color=BG, border_color=AMBER)
        self.service_nav_button.configure(fg_color=CARD_2, text_color=TEXT, border_color=BORDER)

    def show_service_view(self) -> None:
        self.active_view = "service"
        self.work_view.grid_forget()
        self.service_view.grid(row=0, column=0, sticky="nsew")
        self.work_nav_button.configure(fg_color=CARD_2, text_color=TEXT, border_color=BORDER)
        self.service_nav_button.configure(fg_color=AMBER, text_color=BG, border_color=AMBER)
        self.refresh_environment()

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
            if target.exists():
                raise FileExistsError(f"В папке исходников уже есть файл: {target}")
            temp.rename(target)
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

    def set_import_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.choose_button.configure(state=state)
        self.start_button.configure(state=state)
        self.drop_signal.configure(
            text="● ИМПОРТ" if busy else ("● ФАЙЛ ГОТОВ" if self.selected_file else "● ОЖИДАНИЕ"),
            text_color=AMBER if busy or self.selected_file else MUTED,
        )
        self.drop_hint.configure(
            text="КОПИРУЮ ФАЙЛ — ОРИГИНАЛ ОСТАНЕТСЯ НА МЕСТЕ"
            if busy
            else (
                "ПЕРЕТАСКИВАНИЕ ВКЛЮЧЕНО · ФАЙЛ БУДЕТ СКОПИРОВАН В ПАПКУ ИСХОДНИКОВ"
                if DND_ENABLED
                else "ПЕРЕТАСКИВАНИЕ НЕДОСТУПНО · ИСПОЛЬЗУЙТЕ КНОПКУ"
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
        self.drop_signal.configure(text="● ФАЙЛ ГОТОВ", text_color=AMBER)
        self.result_frame.grid_forget()
        self.waveform_request_id += 1
        request_id = self.waveform_request_id
        self.waveform_values = None
        self._draw_waveform()
        threading.Thread(target=self._waveform_worker, args=(resolved, request_id), daemon=True).start()
        self.set_status("Файл выбран. Настройте параметры и запустите расшифровку.")
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
            self.show_error(f"Модель {model_name} {problem}.\n\nСкачайте её в разделе «Сервис».")
            return

        run_dir = RUNS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = run_dir / "status.txt"
        self.result_json = run_dir / "result.json"
        self.last_status_count = 0

        python_exe = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
        args = [
            str(python_exe),
            "-X",
            "utf8",
            str(APP_DIR / "transcriber_core.py"),
            "--transcribe-once",
            str(self.selected_file),
            "--language",
            self.language_var.get(),
            "--quality",
            quality_key,
            "--status-file",
            str(self.status_file),
            "--result-json",
            str(self.result_json),
            "--formats",
            *formats,
        ]

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            self.active_process = subprocess.Popen(
                args,
                cwd=APP_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                env=env,
            )
        except OSError as exc:
            self.show_error(f"Не удалось запустить обработчик.\n\nПричина: {exc}")
            return

        self.set_busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.set_status("Запускаю локальный Whisper.")
        self.append_log(f"Старт: {self.selected_file}")

    def poll_process(self) -> None:
        self.read_status_lines()
        if self.active_process and self.active_process.poll() is not None:
            exit_code = self.active_process.returncode
            self.active_process = None
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)
            self.set_busy(False)
            self.read_status_lines()
            self.finish_transcription(exit_code)
        self.after(500, self.poll_process)

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
                self.set_status(clean)
                self.append_log(clean)
        self.last_status_count = len(lines)

    def finish_transcription(self, exit_code: int) -> None:
        if not self.result_json or not self.result_json.exists():
            self.show_error(f"Обработчик завершился с кодом {exit_code}, но не записал результат.")
            return
        try:
            payload = json.loads(self.result_json.read_text(encoding="utf-8"))
        except Exception as exc:
            self.show_error(f"Не удалось прочитать результат обработки.\n\nПричина: {exc}")
            return

        if not payload.get("success"):
            self.show_error(str(payload.get("error") or f"Обработчик завершился с кодом {exit_code}."))
            return

        created = payload.get("created_files", [])
        self.set_status("Расшифровка успешно завершена.")
        self.append_log("Созданы файлы:")
        for path in created:
            self.append_log(str(path))
        if self.log_is_open:
            self.toggle_log()
        names = "\n".join(f"• {Path(path).name}" for path in created)
        self.result_label.configure(text="ГОТОВО · СОЗДАННЫЕ ФАЙЛЫ\n" + names)
        self.result_frame.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.drop_signal.configure(text="● ЗАВЕРШЕНО", text_color=GOOD)
        self.refresh_environment()

    def refresh_environment(self) -> None:
        status = check_environment()
        checks_ok = all(check["ok"] for check in status["checks"])
        self.ready_badge.configure(
            text=status["device_label"] if checks_ok else "Нужна настройка",
            fg_color="#13231B" if checks_ok else "#2B2111",
            text_color=GOOD if checks_ok else WARN,
        )
        lines = [
            f"Приложение: {status['app']}",
            f"Папка: {status['app_dir']}",
            f"Устройство: {status['device_label']}",
            "",
            "Проверки:",
        ]
        for check in status["checks"]:
            marker = "OK" if check["ok"] else "Нужно исправить"
            lines.append(f"- {marker}: {check['name']} - {check['detail']}")
        lines.extend(["", "Модели:"])
        for model in status["models"]:
            marker = "установлена" if model["installed"] else "не установлена"
            lines.append(f"- {model['model']}: {marker}, {format_bytes(model['bytes'])}")
        self.ready_text.delete("1.0", "end")
        self.ready_text.insert("1.0", "\n".join(lines))
        self.update_model_rows(status["models"])
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
                    text="Готово" if installed else ("Скачать заново" if damaged else "Скачать"),
                    state="disabled" if installed else "normal",
                    fg_color=BORDER if installed else AMBER,
                    text_color=MUTED if installed else BG,
                    border_color=BORDER if installed else AMBER,
                )
            if detail:
                detail.configure(text=f"{model['summary']} — {model['recommendation']}")

    def update_quality_state(self) -> None:
        model_name = QUALITY_OPTIONS[self.quality_var.get()][1]
        model_state = get_model_file_state(model_name)
        if model_state["installed"]:
            state = "модель установлена"
        elif model_state["damaged"]:
            state = "модель повреждена"
        else:
            state = "модель не установлена"
        self.quality_state.configure(
            text=f"{model_name}: {state}",
            text_color=GOOD if model_state["installed"] else WARN,
        )

    def download_model(self, model_name: str) -> None:
        target = CACHE_DIR / f"{model_name}.pt"
        model_state = get_model_file_state(model_name)
        if model_state["installed"]:
            self.refresh_environment()
            return
        if model_state["damaged"]:
            ok = messagebox.askyesno(
                "Скачать заново",
                f"Файл модели {model_name} выглядит неполным или повреждённым.\n\nЗаменить его?",
            )
            if not ok:
                return
            try:
                target.unlink()
            except OSError as exc:
                self.show_error(f"Не удалось удалить повреждённую модель.\n\nПричина: {exc}")
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
        temp = CACHE_DIR / f"{model_name}.pt.download"
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if temp.exists():
                temp.unlink()
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

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.start_button.configure(state=state, text="Расшифровка идёт…" if busy else "Запустить расшифровку")
        self.quality_menu.configure(state=state)
        self.language_segment.configure(state=state)
        self.txt_checkbox.configure(state=state)
        self.srt_checkbox.configure(state=state)
        self.choose_button.configure(state=state)
        self.drop_signal.configure(
            text="● В РАБОТЕ" if busy else ("● ФАЙЛ ГОТОВ" if self.selected_file else "● ОЖИДАНИЕ"),
            text_color=AMBER if busy or self.selected_file else MUTED,
        )
        if busy:
            self.result_frame.grid_forget()

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def append_log(self, text: str) -> None:
        self.log_box.insert("end", text.rstrip() + "\n")
        self.log_box.see("end")

    def toggle_log(self) -> None:
        self.log_is_open = not self.log_is_open
        if self.log_is_open:
            self.log_box.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 14))
            self.log_toggle_button.configure(text="Скрыть журнал")
        else:
            self.log_box.grid_forget()
            self.log_toggle_button.configure(text="Показать журнал")

    def show_error(self, text: str) -> None:
        self.set_status("Ошибка. Подробности показаны в сообщении.")
        self.append_log("Ошибка: " + text.replace("\n", " "))
        messagebox.showerror("Ошибка", text)

    @staticmethod
    def open_folder(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
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
        height = max(self.waveform.winfo_height(), round(68 * UI_SCALE))
        center = height / 2

        if not self.selected_file:
            self.waveform.create_line(0, center, width, center, fill=BORDER, width=1)
            return

        if self.waveform_values is None:
            self.waveform.create_line(0, center, width, center, fill=BORDER, width=1)
            self.waveform.create_text(
                width / 2,
                center,
                text="АНАЛИЗИРУЮ ЗВУК…",
                fill=DIM,
                font=("Consolas", 9, "bold"),
            )
            return

        if not self.waveform_values or not any(self.waveform_values):
            self.waveform.create_line(0, center, width, center, fill=BORDER, width=1)
            self.waveform.create_text(
                width / 2,
                center,
                text="АУДИОДОРОЖКА НЕ НАЙДЕНА",
                fill=DIM,
                font=("Consolas", 9, "bold"),
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
                fill=AMBER,
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
        if self.active_process and self.active_process.poll() is None:
            should_stop = messagebox.askyesno(
                "Расшифровка ещё идёт",
                "Остановить текущую расшифровку и закрыть приложение?",
            )
            if not should_stop:
                return
            try:
                self.active_process.terminate()
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
