from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ISS_PATH = PROJECT_ROOT / "packaging" / "transcriber9000.iss"
VERSION_PATH = PROJECT_ROOT / "packaging" / "version.iss"
BUILD_PATH = PROJECT_ROOT / "packaging" / "build_installer.ps1"


class InstallerPackagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.iss = ISS_PATH.read_text(encoding="utf-8")
        self.version = VERSION_PATH.read_text(encoding="utf-8")
        self.build = BUILD_PATH.read_text(encoding="utf-8")

    def test_per_user_install_and_shortcuts(self) -> None:
        self.assertIn("DefaultDirName={localappdata}\\Programs\\{#AppName}", self.iss)
        self.assertIn("PrivilegesRequired=lowest", self.iss)
        self.assertIn('Name: "{group}\\{#AppName}"', self.iss)
        self.assertIn('Name: "desktopicon"', self.iss)
        self.assertIn("Flags: unchecked", self.iss)

    def test_user_results_are_retained_on_uninstall(self) -> None:
        self.assertIn('Name: "{app}\\input"; Flags: uninsneveruninstall', self.iss)
        self.assertIn('Name: "{app}\\output"; Flags: uninsneveruninstall', self.iss)
        self.assertNotIn("{localappdata}\\Transcriber 9000", self.iss)
        self.assertNotRegex(self.iss.casefold(), r"uninsdelete[^\n]*(models|input|output)")
        self.assertIn('Type: filesandordirs; Name: "{app}\\.cache\\transcriber"', self.iss)
        self.assertIn('Type: dirifempty; Name: "{app}\\.cache"', self.iss)

    def test_payload_excludes_gguf_and_build_rejects_it(self) -> None:
        self.assertIn('Excludes: "input\\*,output\\*,*.gguf"', self.iss)
        self.assertIn('-Filter "*.gguf"', self.build)
        self.assertIn("Portable payload contains a junction", self.build)

    def test_runtime_assets_are_required(self) -> None:
        for relative_path in (
            ".cache\\llama-helper-cpu\\release\\llama-helper.exe",
            ".cache\\llama-helper-cuda\\release\\llama-helper.exe",
            ".cache\\whisper\\base.pt",
            "tools\\ffmpeg\\bin\\ffmpeg.exe",
            "resources\\report_models.json",
        ):
            self.assertIn(f'"{relative_path}"', self.build)

    def test_version_metadata_is_complete(self) -> None:
        for name in ("AppName", "AppVersion", "AppVersionNumeric", "AppPublisher", "AppExeName"):
            self.assertRegex(self.version, re.compile(rf'^#define {name} ".+"$', re.MULTILINE))
        self.assertIn("VersionInfoVersion={#AppVersionNumeric}", self.iss)
        self.assertIn("VersionInfoProductVersion={#AppVersionNumeric}", self.iss)


if __name__ == "__main__":
    unittest.main()
