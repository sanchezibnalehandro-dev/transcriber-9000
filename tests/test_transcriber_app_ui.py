from __future__ import annotations

import queue
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import transcriber_app as gui


class FakeWidget:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}
        self.mapped = False
        self.grid_options: dict[str, object] = {}

    def configure(self, **kwargs) -> None:
        self.options.update(kwargs)

    def cget(self, key: str):
        return self.options.get(key)

    def grid(self, **kwargs) -> None:
        self.mapped = True
        self.grid_options = kwargs

    def grid_configure(self, **kwargs) -> None:
        self.grid_options.update(kwargs)

    def grid_forget(self) -> None:
        self.mapped = False


class VisualHarness:
    WIDGET_NAMES = (
        "settings_panel",
        "intro_frame",
        "status_panel",
        "stage_frame",
        "progress",
        "result_frame",
        "report_action_button",
        "open_results_button",
        "start_button",
        "log_toggle_button",
        "log_box",
        "file_label",
        "file_meta_label",
        "drop_signal",
        "drop_frame",
        "waveform",
        "choose_button",
        "transcription_stage_label",
        "stage_arrow_label",
        "report_stage_label",
        "status_icon",
        "status_label",
        "status_detail_label",
        "status_step_label",
    )

    def __init__(self) -> None:
        for name in self.WIDGET_NAMES:
            setattr(self, name, FakeWidget())
        self.stage_arrow_label.configure(text="→")
        self.ui_state = gui.UIState.INITIAL
        self.error_detail = ""
        self.log_is_open = False
        self.report_action: str | None = None
        self.report_output_path: Path | None = None
        self.selected_file: Path | None = Path("meeting.wav")
        self.waveform_draws = 0

    def _draw_waveform(self) -> None:
        self.waveform_draws += 1

    def _font(self, _role: str, size: int, weight: str = "normal") -> tuple[str, int, str]:
        return ("Test Font", size, weight)

    def _apply_source_density(self, mode: str) -> None:
        gui.Transcriber9000App._apply_source_density(self, mode)

    def choose_file(self) -> None:
        pass

    def start_transcription(self) -> None:
        pass

    def handle_report_action(self) -> None:
        pass

    def open_folder(self, _path: Path) -> None:
        pass

    def render(self, state: gui.UIState, detail: str = "") -> None:
        gui.Transcriber9000App.render_ui_state(self, state, detail)


class FontResolutionTests(unittest.TestCase):
    def test_preferred_windows_fonts_are_used_when_available(self) -> None:
        families = gui.choose_font_families(
            ["Arial", "Segoe UI", "Segoe UI Variable", "Bahnschrift"],
            "System Default",
            "System Fixed",
        )
        self.assertEqual(families.body, "Segoe UI Variable")
        self.assertEqual(families.display, "Bahnschrift")
        self.assertEqual(families.mono, "System Fixed")

    def test_body_and_display_fall_back_without_optional_fonts(self) -> None:
        families = gui.choose_font_families(["Segoe UI"], "System Default", "System Fixed")
        self.assertEqual(families.body, "Segoe UI")
        self.assertEqual(families.display, "Segoe UI")

    def test_tk_default_is_final_fallback(self) -> None:
        families = gui.choose_font_families(["Arial"], "Tk Body", "Tk Mono")
        self.assertEqual(families.body, "Tk Body")
        self.assertEqual(families.display, "Tk Body")
        self.assertEqual(families.mono, "Tk Mono")


class StateMatrixTests(unittest.TestCase):
    def test_initial_has_only_file_primary_action(self) -> None:
        view = VisualHarness()
        view.selected_file = None
        view.render(gui.UIState.INITIAL)
        self.assertTrue(view.choose_button.mapped)
        self.assertEqual(view.choose_button.cget("text"), "Выбрать файл")
        self.assertFalse(view.settings_panel.mapped)
        self.assertFalse(view.status_panel.mapped)

    def test_file_selected_exposes_processing_controls(self) -> None:
        view = VisualHarness()
        view.render(gui.UIState.FILE_SELECTED)
        self.assertTrue(view.settings_panel.mapped)
        self.assertTrue(view.start_button.mapped)
        self.assertEqual(view.start_button.grid_options["column"], 3)
        self.assertFalse(view.status_panel.mapped)

    def test_transcription_is_locked_to_progress_state(self) -> None:
        view = VisualHarness()
        view.render(gui.UIState.TRANSCRIBING)
        self.assertTrue(view.status_panel.mapped)
        self.assertTrue(view.stage_frame.mapped)
        self.assertTrue(view.progress.mapped)
        self.assertFalse(view.choose_button.mapped)
        self.assertFalse(view.start_button.mapped)
        self.assertEqual(view.status_label.cget("text"), "Расшифровываю запись")
        self.assertEqual(view.status_step_label.cget("text"), "Шаг 1 из 2")
        self.assertIn("→", str(view.stage_arrow_label.cget("text")))

    def test_report_starting_and_generating_are_distinct_presentations(self) -> None:
        view = VisualHarness()
        view.render(gui.UIState.REPORT_STARTING)
        self.assertEqual(view.status_label.cget("text"), "Расшифровка готова")
        self.assertIn("TXT сохранён", str(view.status_detail_label.cget("text")))
        view.render(gui.UIState.REPORT_GENERATING)
        self.assertEqual(view.status_label.cget("text"), "Создаю AI-отчёт")
        self.assertEqual(view.status_step_label.cget("text"), "Шаг 2 из 2")
        self.assertIn("Транскрипция уже сохранена", str(view.status_detail_label.cget("text")))

    def test_cpu_fallback_is_explicit_and_warns_about_latency(self) -> None:
        view = VisualHarness()
        view.report_action = "start_cpu"
        view.render(gui.UIState.CPU_FALLBACK)
        self.assertTrue(view.report_action_button.mapped)
        self.assertIn("заметно больше времени", str(view.status_detail_label.cget("text")))

    def test_ready_prioritizes_report_when_markdown_exists(self) -> None:
        view = VisualHarness()
        view.report_action = "open"
        view.report_output_path = Path("meeting--product-meeting.md")
        view.render(gui.UIState.READY)
        self.assertTrue(view.report_action_button.mapped)
        self.assertTrue(view.open_results_button.mapped)
        self.assertEqual(view.status_label.cget("text"), "Готово")
        self.assertEqual(view.report_action_button.cget("text"), "Открыть AI-отчёт")
        self.assertEqual(
            view.status_detail_label.cget("text"),
            "Расшифровка и AI-отчёт созданы",
        )
        self.assertEqual(view.waveform.cget("height"), round(34 * gui.UI_SCALE))

    def test_srt_only_ready_has_no_report_action(self) -> None:
        view = VisualHarness()
        view.report_action = None
        view.report_output_path = None
        view.render(gui.UIState.READY)
        self.assertFalse(view.report_action_button.mapped)
        self.assertTrue(view.open_results_button.mapped)
        self.assertEqual(view.open_results_button.cget("text"), "Показать в папке")

    def test_transcription_error_has_retry_replace_and_details(self) -> None:
        view = VisualHarness()
        view.render(gui.UIState.TRANSCRIPTION_ERROR, "decoder failed")
        self.assertEqual(view.report_action, "retry_transcription")
        self.assertTrue(view.report_action_button.mapped)
        self.assertTrue(view.open_results_button.mapped)
        self.assertTrue(view.log_toggle_button.mapped)

    def test_report_error_only_offers_cpu_when_runtime_selected_it(self) -> None:
        view = VisualHarness()
        view.report_action = None
        view.render(gui.UIState.REPORT_ERROR, "helper failed")
        self.assertFalse(view.report_action_button.mapped)
        self.assertTrue(view.open_results_button.mapped)

        view.report_action = "retry_cpu"
        view.render(gui.UIState.REPORT_ERROR, "helper failed")
        self.assertTrue(view.report_action_button.mapped)

    def test_renderer_does_not_require_process_state(self) -> None:
        view = VisualHarness()
        for state in gui.UIState:
            view.render(state)
        self.assertEqual(view.waveform_draws, len(gui.UIState) - 2)


class LayoutContractTests(unittest.TestCase):
    def test_window_geometry_contract(self) -> None:
        self.assertEqual(gui.WINDOW_SIZE, "1080x720")
        self.assertEqual(gui.MIN_WINDOW_SIZE, (960, 640))

    def test_real_window_states_fit_default_and_minimum_geometry(self) -> None:
        app = gui.Transcriber9000App()
        try:
            if sys.platform == "darwin" and (
                app.winfo_screenwidth() < round(1080 * gui.UI_SCALE)
                or app.winfo_screenheight() < round(720 * gui.UI_SCALE)
            ):
                self.skipTest("macOS CI virtual screen is smaller than the app window")
            app.selected_file = gui.INPUT_DIR / "layout-smoke.wav"
            app.file_label.configure(text="layout-smoke.wav")
            app.file_meta_label.configure(text="WAV · 1.0 MB")
            app.created_result_paths = [gui.OUTPUT_DIR / "layout-smoke.txt"]
            app.report_output_path = gui.OUTPUT_DIR / "layout-smoke--product-meeting.md"
            app.report_action = "open"
            app.result_label.configure(
                text="Транскрипция · layout-smoke.txt\nAI-отчёт · layout-smoke--product-meeting.md"
            )

            for width, height in ((1080, 720), gui.MIN_WINDOW_SIZE):
                app.geometry(f"{width}x{height}")
                app.update()
                self.assertEqual(
                    (app.winfo_width(), app.winfo_height()),
                    (round(width * gui.UI_SCALE), round(height * gui.UI_SCALE)),
                )
                for state in gui.UIState:
                    if state is gui.UIState.CPU_FALLBACK:
                        app.report_action = "start_cpu"
                    elif state is gui.UIState.REPORT_ERROR:
                        app.report_action = "retry_cpu"
                    elif state is gui.UIState.READY:
                        app.report_action = "open"
                    app.render_ui_state(state, "layout smoke")
                    app.update_idletasks()
                    host_width = app.work_view.winfo_width()
                    host_height = app.work_view.winfo_height()
                    for widget in (app.drop_frame, app.settings_panel, app.status_panel):
                        if widget.winfo_ismapped():
                            self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), host_width + 2)
                            self.assertLessEqual(widget.winfo_y() + widget.winfo_height(), host_height + 2)

            physical_minimum = tk.Tk.minsize(app)
            self.assertEqual(physical_minimum, tuple(round(value * gui.UI_SCALE) for value in gui.MIN_WINDOW_SIZE))
            self.assertTrue(app.choose_button._canvas.bind("<Return>"))
            self.assertTrue(app.choose_button._canvas.bind("<space>"))
        finally:
            app.destroy()


class StatusCopyTests(unittest.TestCase):
    def test_core_status_is_mapped_to_user_copy(self) -> None:
        self.assertEqual(gui.friendly_transcription_status("Загружаю модель base"), "Подготавливаю распознавание…")
        self.assertIn("Распознаю речь", gui.friendly_transcription_status("Распознаю фрагмент 1"))
        self.assertEqual(gui.friendly_transcription_status("Сохраняю TXT"), "Сохраняю транскрипцию…")

class MediaImportFallbackTests(unittest.TestCase):
    def test_gui_import_copies_media_with_no_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "external.wav"
            target = root / "input" / "external.wav"
            target.parent.mkdir()
            source.write_bytes(b"media from outside")
            harness = SimpleNamespace(import_queue=queue.Queue())

            gui.Transcriber9000App._copy_file_to_input(harness, source, target)

            self.assertEqual(target.read_bytes(), b"media from outside")
            self.assertEqual(source.read_bytes(), b"media from outside")
            messages = list(harness.import_queue.queue)
            self.assertEqual(messages[-1], ("done", target))


if __name__ == "__main__":
    unittest.main()
