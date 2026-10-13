from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import data_import
from data_import import copy_legacy_data, has_legacy_data


class DataImportTests(unittest.TestCase):
    def test_empty_folder_has_no_legacy_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(has_legacy_data(Path(temporary)))

    def test_clean_macos_install_has_no_import_offer_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "Applications" / "Transcriber 9000.app" / "Contents" / "MacOS" / "Transcriber 9000"
            with (
                mock.patch.object(data_import.sys, "platform", "darwin"),
                mock.patch.object(data_import.sys, "frozen", True, create=True),
                mock.patch.object(data_import.sys, "executable", str(executable)),
                mock.patch.object(data_import.Path, "home", return_value=root),
                mock.patch.object(data_import, "transcription_data_root", return_value=root / "new-data"),
            ):
                self.assertEqual(data_import.legacy_data_candidates(), ())

    def test_import_copies_without_overwriting_or_removing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "old"
            new = root / "new"
            (old / "input").mkdir(parents=True)
            (old / "output").mkdir()
            (old / ".cache" / "whisper").mkdir(parents=True)
            (new / "output").mkdir(parents=True)
            (old / "input" / "meeting.wav").write_bytes(b"audio")
            (old / "output" / "meeting.txt").write_text("old", encoding="utf-8")
            (old / ".cache" / "whisper" / "tiny.pt").write_bytes(b"model")
            (new / "output" / "meeting.txt").write_text("existing", encoding="utf-8")

            result = copy_legacy_data(old, new)

            self.assertEqual((result.copied, result.skipped), (2, 1))
            self.assertEqual((new / "output" / "meeting.txt").read_text(encoding="utf-8"), "existing")
            self.assertEqual((new / "input" / "meeting.wav").read_bytes(), b"audio")
            self.assertEqual((new / ".cache" / "whisper" / "tiny.pt").read_bytes(), b"model")
            self.assertEqual((old / "output" / "meeting.txt").read_text(encoding="utf-8"), "old")


if __name__ == "__main__":
    unittest.main()
