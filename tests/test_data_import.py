from __future__ import annotations

import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import data_import
from data_import import copy_legacy_data, has_legacy_data
import safe_file_ops


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

    def test_prunes_only_old_uuid_named_staging_files_inside_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            destination = base / "app-support"
            input_dir = destination / "input"
            model_dir = destination / ".cache" / "whisper"
            input_dir.mkdir(parents=True)
            model_dir.mkdir(parents=True)

            now = 1_700_000_000.0
            stale = input_dir / f".interview.wav.{'a' * 32}.importing"
            stale_model = model_dir / f".tiny.pt.{'b' * 32}.importing"
            fresh = input_dir / f".recent.wav.{'c' * 32}.importing"
            unrelated = input_dir / ".interview.wav.not-a-uuid.importing"
            completed = input_dir / "interview.wav"
            outside_dir = base / "unrelated"
            outside_dir.mkdir()
            outside = outside_dir / f".private.wav.{'d' * 32}.importing"

            for path in (stale, stale_model, fresh, unrelated, completed, outside):
                path.write_bytes(b"original")
            for path in (stale, stale_model, unrelated, completed, outside):
                os.utime(path, (now - 7_200, now - 7_200))
            os.utime(fresh, (now - 30, now - 30))

            removed = data_import.prune_stale_legacy_imports(destination, now=now)
            self.assertEqual(removed, 2)
            self.assertFalse(stale.exists())
            self.assertFalse(stale_model.exists())
            for path in (fresh, unrelated, completed, outside):
                self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(data_import.prune_stale_legacy_imports(destination, now=now), 0)

    def test_import_works_when_hard_links_are_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "old"
            new = root / "new"
            (old / "input").mkdir(parents=True)
            (old / "input" / "meeting.wav").write_bytes(b"portable audio")

            operation = "rename" if os.name == "nt" else "link"
            with mock.patch.object(
                safe_file_ops.os,
                operation,
                side_effect=OSError(errno.EOPNOTSUPP, "filesystem does not support operation"),
            ):
                result = copy_legacy_data(old, new)
            self.assertEqual((result.copied, result.skipped), (1, 0))
            self.assertEqual((new / "input" / "meeting.wav").read_bytes(), b"portable audio")
            self.assertEqual((old / "input" / "meeting.wav").read_bytes(), b"portable audio")


if __name__ == "__main__":
    unittest.main()
