from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import runtime_paths


class RuntimePathTests(unittest.TestCase):
    def test_user_models_and_settings_are_under_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environ = {"LOCALAPPDATA": temporary}
            root = Path(temporary).resolve() / "Transcriber 9000"
            self.assertEqual(runtime_paths.user_data_root(environ), root)
            self.assertEqual(runtime_paths.report_models_directory(environ), root / "models")
            self.assertEqual(runtime_paths.report_model_settings_path(environ), root / "settings.json")

    def test_frozen_root_is_executable_directory(self) -> None:
        executable = Path(r"C:\Portable Folder\Транскрибатор\Transcriber 9000.exe")
        with (
            mock.patch.object(runtime_paths.sys, "frozen", True, create=True),
            mock.patch.object(runtime_paths.sys, "executable", str(executable)),
        ):
            self.assertEqual(runtime_paths.application_root(), executable.resolve().parent)


if __name__ == "__main__":
    unittest.main()
