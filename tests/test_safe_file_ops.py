from __future__ import annotations

import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import safe_file_ops


class SafeFilePromotionTests(unittest.TestCase):
    def test_publish_keeps_bytes_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "staged.importing"
            target = root / "meeting.wav"
            staged.write_bytes(b"new audio")
            safe_file_ops.publish_staged_file(staged, target)
            self.assertEqual(target.read_bytes(), b"new audio")
            if os.name == "nt":
                self.assertFalse(staged.exists())
            else:
                self.assertTrue(staged.exists())

            retry = root / "retry.importing"
            retry.write_bytes(b"other audio")
            with self.assertRaises(FileExistsError):
                safe_file_ops.publish_staged_file(retry, target)
            self.assertEqual(target.read_bytes(), b"new audio")
            self.assertEqual(retry.read_bytes(), b"other audio")

    def _unsupported_promotion(self):
        method = "rename" if os.name == "nt" else "link"
        return mock.patch.object(
            safe_file_ops.os,
            method,
            side_effect=OSError(errno.EOPNOTSUPP, "no hard links / no rename"),
        )

    def test_fallback_on_filesystem_without_hard_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "staged.importing"
            target = root / "meeting.wav"
            staged.write_bytes(b"portable input")
            with self._unsupported_promotion():
                safe_file_ops.publish_staged_file(staged, target)
            self.assertEqual(target.read_bytes(), b"portable input")
            self.assertTrue(staged.exists())

    def test_fallback_does_not_replace_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "staged.importing"
            target = root / "meeting.wav"
            staged.write_bytes(b"new")
            target.write_bytes(b"precious existing file")
            with self._unsupported_promotion():
                with self.assertRaises(FileExistsError):
                    safe_file_ops.publish_staged_file(staged, target)
            self.assertEqual(target.read_bytes(), b"precious existing file")
            self.assertEqual(staged.read_bytes(), b"new")

    def test_fallback_removes_partial_destination_after_copy_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "staged.importing"
            target = root / "meeting.wav"
            staged.write_bytes(b"original")
            with self._unsupported_promotion(), mock.patch.object(
                safe_file_ops.shutil,
                "copyfileobj",
                side_effect=OSError(errno.ENOSPC, "disk full"),
            ):
                with self.assertRaises(OSError):
                    safe_file_ops.publish_staged_file(staged, target)
            self.assertFalse(target.exists())
            self.assertEqual(staged.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
