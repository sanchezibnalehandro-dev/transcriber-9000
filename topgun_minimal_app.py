from __future__ import annotations

import json
import hashlib
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

from topgun_razbor import (
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

    class TopgunWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)

    DND_ENABLED = True
except Exception:
    DND_FILES = ""
    TopgunWindow = ctk.CTk
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
ERROR = "#FF756B"
RED = AMBER
BLUE = AMBER
UI_SCALE = 1.25
WINDOW_SIZE = "1340x900"
MIN_WINDOW_SIZE = (1200, 820)

MEDIA_FILTER = (
    ("Аудио и видео", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.mp4 *.mov *.mkv *.avi *.webm"),
    ("Все файлы", "*.*"),
)
MEDIA_SUFFIXES = frozenset({".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".mov", ".mkv", ".avi", ".webm"})

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


class TopgunApp(TopgunWindow):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x760")
        self.minsize(1020, 700)
        self.configure(fg_color=BG)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        self.selected_file: Path | None = None
        self.active_process: subprocess.Popen | None = None
        self.status_file: Path | None = None
        self.result_json: Path | None = None
        self.last_status_count = 0
        self.download_queue: queue.Queue[tuple] = queue.Queue()
        self.import_queue: queue.Queue[tuple] = queue.Queue()
        self.import_in_progress = False
        self.download_buttons: dict[str, ctk.CTkButton] = {}
        self.model_status_labels: dict[str, ctk.CTkLabel] = {}
        self.model_detail_labels: dict[str, ctk.CTkLabel] = {}

        self.language_var = ctk.StringVar(value="ru")
        self.quality_var = ctk.StringVar(value="balanced")
        self.txt_var = ctk.BooleanVar(value=True)
        self.srt_var = ctk.BooleanVar(value=False)

        self._build_layout()
        self.refresh_environment()
        self.after(500, self.poll_process)
        self.after(300, self.poll_download_queue)
        self.after(150, self.poll_import_queue)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 12))
        header.grid_columnconfigure(1, weight=1)

        brand = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        brand.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            brand,
            text="ТРАНСКРИБАТОР /",
            font=ctk.CTkFont("Arial Narrow", 24, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            brand,
            text="9000",
            font=ctk.CTkFont("Arial Narrow", 48, "bold"),
            text_color=TEXT,
        ).grid(row=1, column=0, sticky="w")
        accent = ctk.CTkFrame(brand, fg_color=RED, height=3, width=78, corner_radius=0)
        accent.grid(row=2, column=0, sticky="w", pady=(4, 0))
        ctk.CTkFrame(brand, fg_color=BLUE, height=3, width=78, corner_radius=0).grid(row=2, column=0, padx=(86, 0), sticky="w", pady=(4, 0))

        ctk.CTkLabel(
            header,
            text="Локальная транскрибация аудио и видео. Исходники остаются на этом компьютере.",
            font=ctk.CTkFont("Segoe UI", 14),
            text_color=MUTED,
        ).grid(row=1, column=1, sticky="e", padx=(20, 0))

        header_actions = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        header_actions.grid(row=0, column=1, sticky="e")
        self.ready_badge = ctk.CTkLabel(
            header_actions,
            text="Проверяю готовность",
            fg_color=CARD,
            corner_radius=6,
            padx=14,
            pady=7,
            text_color=MUTED,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
        )
        self.ready_badge.grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(
            header_actions,
            text="Открыть input",
            command=lambda: self.open_folder(INPUT_DIR),
            width=120,
            fg_color=CARD_2,
            hover_color=BORDER,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            header_actions,
            text="Открыть output",
            command=lambda: self.open_folder(OUTPUT_DIR),
            width=126,
            fg_color=CARD_2,
            hover_color=BORDER,
        ).grid(row=0, column=2)

        self.tabs = ctk.CTkTabview(
            self,
            fg_color=PANEL,
            segmented_button_fg_color=CARD,
            segmented_button_selected_color=RED,
            segmented_button_selected_hover_color="#B80000",
            segmented_button_unselected_color=CARD,
            segmented_button_unselected_hover_color=BORDER,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 24))
        self.transcribe_tab = self.tabs.add("Расшифровка")
        self.models_tab = self.tabs.add("Модели")
        self.ready_tab = self.tabs.add("Готовность")
        self._build_transcribe_tab()
        self._build_models_tab()
        self._build_ready_tab()

    def _build_transcribe_tab(self) -> None:
        tab = self.transcribe_tab
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=2)
        tab.grid_rowconfigure(1, weight=1)

        self.drop_frame = ctk.CTkFrame(tab, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
        self.drop_frame.grid(row=0, column=0, sticky="nsew", padx=(18, 10), pady=(18, 12))
        self.drop_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.drop_frame,
            text="ФАЙЛ ДЛЯ РАСШИФРОВКИ",
            font=ctk.CTkFont("Arial Narrow", 22, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 4))
        self.file_label = ctk.CTkLabel(
            self.drop_frame,
            text="Файл не выбран",
            font=ctk.CTkFont("Segoe UI", 14),
            text_color=MUTED,
            anchor="w",
        )
        self.file_label.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 12))
        ctk.CTkButton(
            self.drop_frame,
            text="Выбрать аудио или видео",
            command=self.choose_file,
            height=42,
            fg_color=RED,
            hover_color="#B80000",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
        ).grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 18))
        self.drop_hint = ctk.CTkLabel(
            self.drop_frame,
            text="Можно перетащить файл сюда" if DND_ENABLED else "Выбор файла доступен кнопкой выше",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=DIM,
        )
        self.drop_hint.grid(row=3, column=0, sticky="w", padx=22, pady=(0, 18))

        if DND_ENABLED:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self.handle_drop)

        settings = ctk.CTkFrame(tab, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
        settings.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 18), pady=(18, 18))
        settings.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(settings, text="НАСТРОЙКИ", font=ctk.CTkFont("Arial Narrow", 24, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 10))

        ctk.CTkLabel(settings, text="Язык", font=ctk.CTkFont("Segoe UI", 13, "bold"), text_color=MUTED).grid(row=1, column=0, sticky="w", padx=20, pady=(4, 6))
        self.language_segment = ctk.CTkSegmentedButton(
            settings,
            values=["русский", "авто"],
            command=lambda value: self.language_var.set("ru" if value == "русский" else "auto"),
            selected_color=BLUE,
            selected_hover_color="#00538B",
        )
        self.language_segment.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        self.language_segment.set("русский")

        ctk.CTkLabel(settings, text="Качество", font=ctk.CTkFont("Segoe UI", 13, "bold"), text_color=MUTED).grid(row=3, column=0, sticky="w", padx=20, pady=(0, 6))
        self.quality_menu = ctk.CTkOptionMenu(
            settings,
            values=[QUALITY_NOTES[key] for key in QUALITY_OPTIONS],
            command=self.on_quality_change,
            fg_color=CARD_2,
            button_color=RED,
            button_hover_color="#B80000",
        )
        self.quality_menu.grid(row=4, column=0, sticky="ew", padx=20)
        self.quality_menu.set(QUALITY_NOTES[self.quality_var.get()])
        self.quality_state = ctk.CTkLabel(settings, text="", text_color=DIM, font=ctk.CTkFont("Segoe UI", 12), anchor="w")
        self.quality_state.grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 16))

        ctk.CTkLabel(settings, text="Результат", font=ctk.CTkFont("Segoe UI", 13, "bold"), text_color=MUTED).grid(row=6, column=0, sticky="w", padx=20, pady=(0, 6))
        ctk.CTkCheckBox(settings, text=FORMAT_OPTIONS["txt"], variable=self.txt_var, checkbox_width=20, checkbox_height=20, fg_color=RED, hover_color="#B80000").grid(row=7, column=0, sticky="w", padx=20, pady=(0, 8))
        ctk.CTkCheckBox(settings, text=FORMAT_OPTIONS["srt"], variable=self.srt_var, checkbox_width=20, checkbox_height=20, fg_color=RED, hover_color="#B80000").grid(row=8, column=0, sticky="w", padx=20, pady=(0, 18))

        self.start_button = ctk.CTkButton(
            settings,
            text="Запустить расшифровку",
            command=self.start_transcription,
            height=48,
            fg_color=RED,
            hover_color="#B80000",
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
        )
        self.start_button.grid(row=9, column=0, sticky="ew", padx=20, pady=(4, 12))
        ctk.CTkButton(
            settings,
            text="Проверить готовность",
            command=self.refresh_environment,
            height=38,
            fg_color=CARD_2,
            hover_color=BORDER,
        ).grid(row=10, column=0, sticky="ew", padx=20, pady=(0, 18))

        status = ctk.CTkFrame(tab, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
        status.grid(row=1, column=0, sticky="nsew", padx=(18, 10), pady=(0, 18))
        status.grid_columnconfigure(0, weight=1)
        status.grid_rowconfigure(2, weight=1)

        self.status_label = ctk.CTkLabel(
            status,
            text="Готово. Выберите файл из папки input.",
            fg_color="#0D1421",
            corner_radius=6,
            text_color=TEXT,
            anchor="w",
            padx=14,
            pady=10,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        self.progress = ctk.CTkProgressBar(status, progress_color=BLUE)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.log_box = ctk.CTkTextbox(status, fg_color="#080A0E", text_color=MUTED, border_color=BORDER, border_width=1, corner_radius=6)
        self.log_box.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.append_log("Журнал обработки появится здесь.")

    def _build_models_tab(self) -> None:
        tab = self.models_tab
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tab,
            text="МОДЕЛИ WHISPER",
            font=ctk.CTkFont("Arial Narrow", 30, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 4))
        ctk.CTkLabel(
            tab,
            text="Скачивание моделей - единственный сетевой шаг. Аудио и видео не отправляются наружу.",
            font=ctk.CTkFont("Segoe UI", 13),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 14))

        for row, (quality_key, (quality_label, model_name)) in enumerate(QUALITY_OPTIONS.items(), start=2):
            info = MODEL_INFO[model_name]
            item = ctk.CTkFrame(tab, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
            item.grid(row=row, column=0, sticky="ew", padx=22, pady=6)
            item.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(item, text=model_name, width=94, font=ctk.CTkFont("Arial Narrow", 24, "bold"), text_color=TEXT).grid(row=0, column=0, rowspan=2, padx=16, pady=14)
            ctk.CTkLabel(item, text=quality_label, font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color=TEXT).grid(row=0, column=1, sticky="w", pady=(14, 2))
            detail = ctk.CTkLabel(item, text=info["summary"], font=ctk.CTkFont("Segoe UI", 12), text_color=MUTED, anchor="w")
            detail.grid(row=1, column=1, sticky="ew", pady=(0, 14))
            self.model_detail_labels[model_name] = detail

            status = ctk.CTkLabel(item, text="", width=150, font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=MUTED)
            status.grid(row=0, column=2, rowspan=2, padx=(10, 8))
            self.model_status_labels[model_name] = status

            button = ctk.CTkButton(
                item,
                text="Скачать",
                width=120,
                fg_color=BLUE,
                hover_color="#00538B",
                command=lambda name=model_name: self.download_model(name),
            )
            button.grid(row=0, column=3, rowspan=2, padx=(0, 16), pady=14)
            self.download_buttons[model_name] = button

    def _build_ready_tab(self) -> None:
        tab = self.ready_tab
        tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tab, text="ГОТОВНОСТЬ", font=ctk.CTkFont("Arial Narrow", 30, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 8))
        self.ready_text = ctk.CTkTextbox(tab, fg_color="#080A0E", text_color=MUTED, border_color=BORDER, border_width=1, corner_radius=8)
        self.ready_text.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 18))
        tab.grid_rowconfigure(1, weight=1)

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=INPUT_DIR,
            title="Выберите аудио или видео — файл будет скопирован в input",
            filetypes=MEDIA_FILTER,
        )
        if path:
            self.import_or_select_file(Path(path))

    def handle_drop(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        if paths:
            self.import_or_select_file(Path(paths[0]))

    def import_or_select_file(self, path: Path) -> None:
        """Select an input file or safely import one copy into the input folder."""
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
                f"Выберите аудио или видео: {supported}."
            )
            return
        if is_inside_input(resolved):
            self.set_selected_file(resolved)
            return

        target = INPUT_DIR / resolved.name
        if target.exists():
            self.show_error(
                "В папке input уже есть файл с таким именем:\n"
                f"{target}\n\nНичего не перезаписано. Переименуйте исходный файл и добавьте его снова."
            )
            return
        self.start_import(resolved, target)

    def start_import(self, source: Path, target: Path) -> None:
        if self.import_in_progress:
            self.show_error("Сейчас уже копируется другой файл. Дождитесь завершения импорта.")
            return
        self.import_in_progress = True
        self.set_import_busy(True)
        self.set_status("Копирую файл в input. Оригинал останется на месте.")
        self.append_log(f"Импорт в input: {source} -> {target}")
        threading.Thread(target=self._copy_file_to_input, args=(source, target), daemon=True).start()

    def _copy_file_to_input(self, source: Path, target: Path) -> None:
        temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.importing")
        copied = 0
        total = source.stat().st_size
        try:
            with source.open("rb") as source_file, temp.open("xb") as target_file:
                while chunk := source_file.read(1024 * 1024):
                    target_file.write(chunk)
                    copied += len(chunk)
                    self.import_queue.put(("progress", copied, total))
            shutil.copystat(source, temp)
            if target.exists():
                raise FileExistsError(f"В папке input уже есть файл: {target}")
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
                    self.set_status(f"Копирование в input: {progress}")
                elif kind == "done":
                    _, target = item
                    self.import_in_progress = False
                    self.set_import_busy(False)
                    self.set_selected_file(Path(target))
                    self.set_status("Файл скопирован в input и готов к расшифровке.")
                    self.append_log(f"Импорт завершён: {target}")
                elif kind == "error":
                    _, error = item
                    self.import_in_progress = False
                    self.set_import_busy(False)
                    self.show_error(
                        "Не удалось скопировать файл в input.\n\n"
                        f"Причина: {error}\n\nОригинальный файл не изменён."
                    )
        except queue.Empty:
            pass
        self.after(150, self.poll_import_queue)

    def set_import_busy(self, busy: bool) -> None:
        if not hasattr(self, "choose_button"):
            return
        state = "disabled" if busy else "normal"
        self.choose_button.configure(state=state)
        self.start_button.configure(state=state if busy else "normal")
        if busy:
            self.drop_signal.configure(text="● ИМПОРТ", text_color=AMBER)
            self.drop_hint.configure(text="КОПИРУЕМ В INPUT — ОРИГИНАЛ ОСТАНЕТСЯ НА МЕСТЕ", text_color=AMBER)
        else:
            self.drop_signal.configure(
                text="● ФАЙЛ ГОТОВ" if self.selected_file else "● ОЖИДАНИЕ",
                text_color=AMBER if self.selected_file else MUTED,
            )
            self.drop_hint.configure(
                text="ПЕРЕТАСКИВАНИЕ ВКЛЮЧЕНО · ФАЙЛ БУДЕТ СКОПИРОВАН В INPUT",
                text_color=DIM,
            )

    def set_selected_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            self.show_error(f"Файл не найден:\n{resolved}")
            return
        if not is_inside_input(resolved):
            self.show_error(f"Выбран файл не из папки input:\n{resolved}\n\nПоложите файл в:\n{INPUT_DIR}")
            return
        self.selected_file = resolved
        self.file_label.configure(text=resolved.name)
        if hasattr(self, "file_meta_label"):
            suffix = resolved.suffix.lstrip(".").upper() or "ФАЙЛ"
            self.file_meta_label.configure(text=f"{suffix} · {format_bytes(resolved.stat().st_size)} · папка input")
            self.drop_signal.configure(text="● ФАЙЛ ГОТОВ", text_color=AMBER)
            self.result_frame.grid_forget()
            self._draw_waveform()
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
            self.show_error("Дождитесь окончания копирования файла в input.")
            return
        if not self.selected_file:
            self.show_error("Файл не выбран.\n\nНажмите «Выбрать аудио или видео» и выберите файл из папки input.")
            return
        formats = self.selected_formats()
        if not formats:
            self.show_error("Не выбран формат результата.\n\nОтметьте TXT, SRT или оба формата.")
            return

        quality_key = self.quality_var.get()
        model_name = QUALITY_OPTIONS[quality_key][1]
        model_state = get_model_file_state(model_name)
        if not model_state["installed"]:
            if hasattr(self, "show_service_view"):
                self.show_service_view()
            else:
                self.tabs.set("Модели")
            problem = "повреждена" if model_state["damaged"] else "не установлена"
            self.show_error(f"Модель {model_name} {problem}.\n\nОткройте раздел «Сервис» и скачайте её.")
            return

        run_dir = APP_DIR / ".cache" / "topgun_razbor" / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = run_dir / "status.txt"
        self.result_json = run_dir / "result.json"
        self.last_status_count = 0

        python_exe = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
        args = [
            str(python_exe),
            "-X",
            "utf8",
            str(APP_DIR / "topgun_razbor.py"),
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
        self.active_process = subprocess.Popen(
            args,
            cwd=APP_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            env=env,
        )
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
        if self.result_json and self.result_json.exists():
            try:
                payload = json.loads(self.result_json.read_text(encoding="utf-8"))
            except Exception as exc:
                self.show_error(f"Не удалось прочитать результат обработки.\n\nПричина: {exc}")
                return
            if payload.get("success"):
                created = payload.get("created_files", [])
                self.set_status("Расшифровка успешно завершена.")
                self.append_log("Созданы файлы:")
                for path in created:
                    self.append_log(str(path))
                if hasattr(self, "result_frame"):
                    if self.log_is_open:
                        self.toggle_log()
                    names = "\n".join(f"• {Path(path).name}" for path in created)
                    self.result_label.configure(text="ГОТОВО · СОЗДАННЫЕ ФАЙЛЫ\n" + names)
                    self.result_frame.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
                    self.drop_signal.configure(text="● ЗАВЕРШЕНО", text_color=GOOD)
                messagebox.showinfo("Готово", "Расшифровка успешно завершена.\n\n" + "\n".join(created))
                self.refresh_environment()
                return
            self.show_error(str(payload.get("error") or f"Python завершился с кодом {exit_code}."))
            return
        self.show_error(f"Python завершился с кодом {exit_code}, но не записал JSON-результат.")

    def refresh_environment(self) -> None:
        status = check_environment()
        checks_ok = all(check["ok"] for check in status["checks"])
        self.ready_badge.configure(
            text=f"{status['device_label']}" if checks_ok else "Нужна настройка",
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
        lines.append("")
        lines.append("Модели:")
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
            bytes_count = int(model["bytes"])
            label = self.model_status_labels.get(name)
            button = self.download_buttons.get(name)
            detail = self.model_detail_labels.get(name)
            if label:
                damaged = model.get("damaged", False)
                label.configure(
                    text=("Установлена\n" + format_bytes(bytes_count)) if installed else (("Повреждена\n" + format_bytes(bytes_count)) if damaged else f"Не установлена\n~{model['size_mb']} MB"),
                    text_color=GOOD if installed else WARN,
                )
            if button:
                button.configure(
                    text="Готово" if installed else ("Скачать заново" if model.get("damaged", False) else "Скачать"),
                    state="disabled" if installed else "normal",
                    fg_color=BORDER if installed else AMBER,
                    text_color=MUTED if installed else BG,
                    border_color=BORDER if installed else AMBER,
                )
            if detail:
                detail.configure(text=f"{model['summary']} - {model['recommendation']}")

    def update_quality_state(self) -> None:
        quality_key = self.quality_var.get()
        model_name = QUALITY_OPTIONS[quality_key][1]
        model_state = get_model_file_state(model_name)
        installed = model_state["installed"]
        if installed:
            state = "модель установлена"
        elif model_state["damaged"]:
            state = "модель повреждена"
        else:
            state = "модель не установлена"
        self.quality_state.configure(text=f"{model_name}: {state}", text_color=GOOD if installed else WARN)

    def download_model(self, model_name: str) -> None:
        target = CACHE_DIR / f"{model_name}.pt"
        model_state = get_model_file_state(model_name)
        if model_state["installed"]:
            self.refresh_environment()
            return
        if model_state["damaged"]:
            ok = messagebox.askyesno(
                "Скачать заново",
                f"Файл модели {model_name} выглядит неполным или повреждённым.\n\nЗаменить его новой загрузкой?",
            )
            if not ok:
                return
            try:
                target.unlink()
            except OSError as exc:
                self.show_error(f"Не удалось убрать повреждённую модель {model_name}.\n\nПричина: {exc}")
                return
        button = self.download_buttons.get(model_name)
        if button:
            button.configure(text="Скачивается", state="disabled")
        self.append_log(f"Скачивание модели {model_name}.")
        worker = threading.Thread(target=self._download_worker, args=(model_name,), daemon=True)
        worker.start()

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
                        if total:
                            button.configure(text=f"{int(done * 100 / total)}%")
                        else:
                            button.configure(text=format_bytes(done))
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
        self.start_button.configure(
            state=state,
            text="Расшифровка идёт…" if busy else "Запустить расшифровку",
        )
        self.quality_menu.configure(state=state)
        if hasattr(self, "language_segment"):
            self.language_segment.configure(state=state)
        if hasattr(self, "txt_checkbox"):
            self.txt_checkbox.configure(state=state)
            self.srt_checkbox.configure(state=state)
            self.choose_button.configure(state=state)
            self.drop_signal.configure(
                text="● В РАБОТЕ" if busy else ("● ФАЙЛ ГОТОВ" if self.selected_file else "● ОЖИДАНИЕ"),
                text_color=AMBER if self.selected_file else MUTED,
            )
            if busy:
                self.result_frame.grid_forget()

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def append_log(self, text: str) -> None:
        self.log_box.insert("end", text.rstrip() + "\n")
        self.log_box.see("end")

    def show_error(self, text: str) -> None:
        self.set_status("Ошибка. Подробности показаны в сообщении.")
        self.append_log("Ошибка: " + text.replace("\n", " "))
        messagebox.showerror("Ошибка", text)

    def open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]


class Transcriber9000App(TopgunApp):
    """Studio-style shell around the existing local transcription workflow."""

    def __init__(self):
        # Keep a deliberate 125% app scale while neutralizing the duplicate
        # CustomTkinter multiplier applied by Windows high-DPI displays.
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
        self.log_is_open = False
        self.active_view = "work"
        super().__init__()
        # Tk registers the monitor scale while creating the root. Apply the
        # requested app scale after neutralizing that duplicate multiplier.
        dpi_scaling = max(ctk.ScalingTracker.get_window_dpi_scaling(self), 1.0)
        ctk.set_widget_scaling(UI_SCALE / dpi_scaling)
        ctk.set_window_scaling(UI_SCALE / dpi_scaling)
        self.minsize(*MIN_WINDOW_SIZE)
        self.geometry(WINDOW_SIZE)

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
            text="LOCAL SPEECH UNIT",
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=AMBER,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            brand,
            text="ТРАНСКРИБАТОР / 9000",
            font=ctk.CTkFont("Bahnschrift", 31, "bold"),
            text_color=TEXT,
        ).grid(row=1, column=0, sticky="w", pady=(1, 0))

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
        self.work_nav_button = self._studio_button(
            header_actions,
            text="Работа",
            command=self.show_work_view,
            width=96,
            fg_color=AMBER,
            text_color=BG,
            border_color=AMBER,
        )
        self.work_nav_button.grid(row=0, column=1, padx=(0, 8))
        self.service_nav_button = self._studio_button(
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

    def _studio_button(self, master, **kwargs):
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
        self._studio_button(
            intro,
            text="Открыть input",
            command=lambda: self.open_folder(INPUT_DIR),
            width=112,
            height=32,
        ).grid(row=0, column=1, rowspan=2, padx=(10, 8))
        self._studio_button(
            intro,
            text="Открыть output",
            command=lambda: self.open_folder(OUTPUT_DIR),
            width=122,
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
        self.step_one_marker = ctk.CTkLabel(
            step_one,
            text="01",
            width=34,
            height=26,
            fg_color=AMBER,
            text_color=BG,
            corner_radius=3,
            font=ctk.CTkFont("Consolas", 12, "bold"),
        )
        self.step_one_marker.grid(row=0, column=0, padx=(0, 10))
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
            text="Мы безопасно скопируем файл в input. Оригинал останется на месте.",
            font=ctk.CTkFont("Segoe UI Variable", 12),
            text_color=MUTED,
        )
        self.file_meta_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(2, 10))
        self.choose_button = self._studio_button(
            self.drop_frame,
            text="Выбрать файл для импорта",
            command=self.choose_file,
            width=205,
            height=40,
            border_color=MUTED,
        )
        self.choose_button.grid(row=4, column=0, pady=(0, 14))
        self.drop_hint = ctk.CTkLabel(
            self.drop_frame,
            text=(
                "ПЕРЕТАСКИВАНИЕ ВКЛЮЧЕНО · ФАЙЛ БУДЕТ СКОПИРОВАН В INPUT"
                if DND_ENABLED
                else "ВЫБОР ДОСТУПЕН ПО КНОПКЕ"
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
            text="Готов к работе. Выберите файл из папки input.",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont("Segoe UI Variable", 12, "bold"),
        )
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.log_toggle_button = self._studio_button(
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
        self._studio_button(
            self.result_frame,
            text="Открыть output",
            command=lambda: self.open_folder(OUTPUT_DIR),
            width=116,
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
        self.start_button = self._studio_button(
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
        self._studio_button(
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
            button = self._studio_button(
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

    def toggle_log(self) -> None:
        self.log_is_open = not self.log_is_open
        if self.log_is_open:
            self.log_box.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 14))
            self.log_toggle_button.configure(text="Скрыть журнал")
        else:
            self.log_box.grid_forget()
            self.log_toggle_button.configure(text="Показать журнал")

    def _draw_waveform(self, _event=None) -> None:
        self.waveform.delete("all")
        width = max(self.waveform.winfo_width(), 120)
        height = max(self.waveform.winfo_height(), round(68 * UI_SCALE))
        center = height / 2
        bars = (8, 16, 25, 14, 34, 46, 22, 12, 28, 41, 54, 31, 17, 38, 24, 11, 20, 35, 18, 9, 27, 14)
        gap = width / (len(bars) + 1)
        color = AMBER if self.selected_file else BORDER
        self.waveform.create_line(0, center, width, center, fill=CARD_2, width=1)
        for index, bar_height in enumerate(bars, start=1):
            x = index * gap
            scaled = min(bar_height, height - 8)
            self.waveform.create_line(x, center - scaled / 2, x, center + scaled / 2, fill=color, width=2)

    def _register_drop_targets(self, *widgets) -> None:
        """Register the visible source area and its child controls as DnD targets."""
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


def run_smoke_test() -> int:
    status = check_environment()
    missing_ui = []
    try:
        import customtkinter  # noqa: F401
    except Exception as exc:
        missing_ui.append(f"customtkinter ({exc})")
    if missing_ui:
        print("GUI_V2_SMOKE_TEST_FAILED")
        for item in missing_ui:
            print(f"missing: {item}")
        return 1
    print("GUI_V2_SMOKE_TEST_OK")
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
