from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ISS_PATH = PROJECT_ROOT / "packaging" / "transcriber9000.iss"
VERSION_PATH = PROJECT_ROOT / "packaging" / "version.iss"
BUILD_PATH = PROJECT_ROOT / "packaging" / "build_installer.ps1"
PORTABLE_BUILD_PATH = PROJECT_ROOT / "packaging" / "build_portable.ps1"
SPEC_PATH = PROJECT_ROOT / "packaging" / "transcriber9000.spec"
NOTICES_PATH = PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"
RELEASE_PATH = PROJECT_ROOT / "RELEASE_1.0.0-rc.1.md"


class InstallerPackagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.iss = ISS_PATH.read_text(encoding="utf-8")
        self.version = VERSION_PATH.read_text(encoding="utf-8")
        self.build = BUILD_PATH.read_text(encoding="utf-8")
        self.portable_build = PORTABLE_BUILD_PATH.read_text(encoding="utf-8")
        self.spec = SPEC_PATH.read_text(encoding="utf-8")
        self.notices = NOTICES_PATH.read_text(encoding="utf-8")

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

    def test_license_bundle_is_required_and_frozen(self) -> None:
        self.assertIn('"LICENSES\\README.md"', self.build)
        self.assertIn('project_root / "LICENSES"', self.spec)
        for component in ("FFmpeg", "Python", "PyTorch", "CUDA", "MSVC"):
            self.assertIn(component, self.notices)

    def test_msvc_files_do_not_come_from_system32(self) -> None:
        self.assertNotIn("System32", self.portable_build)
        self.assertIn(".release-input\\msvc-redist-x64", self.portable_build)
        self.assertIn("expectedMsvcFiles", self.portable_build)

    def test_ffmpeg_is_pinned_to_btbn_lgpl_build(self) -> None:
        self.assertIn("autobuild-2026-09-07-15-39", self.notices)
        self.assertIn("FFmpeg-BtbN-n8.1.2-51", self.notices)
        self.assertNotIn("Gyan", self.notices)
        self.assertIn("expectedFfmpegSha256", self.portable_build)
        self.assertIn("931223B06750580BB8DF494AD10F074D8390F76EF3E1C25E1CEC97135AA6C3FC", self.portable_build)
        self.assertIn('"--enable-gpl"', self.portable_build)
        self.assertIn('"--enable-nonfree"', self.portable_build)

    def test_release_metadata_records_support_boundaries(self) -> None:
        release = RELEASE_PATH.read_text(encoding="utf-8")
        for statement in (
            "Windows 11 x64: verified",
            "Windows 10 x64: unverified",
            "RTX 3060 CUDA: verified",
            "CPU fallback: supported",
            "Models: downloaded separately",
            "Unsigned controlled RC",
        ):
            self.assertIn(statement, release)


if __name__ == "__main__":
    unittest.main()
