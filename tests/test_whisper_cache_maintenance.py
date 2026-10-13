from __future__ import annotations

import hashlib
import io
import os
import queue
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import transcriber_app as gui
from whisper_cache_maintenance import prune_stale_whisper_downloads


class WhisperDownloadCleanupTests(unittest.TestCase):
    def test_removes_old_uuid_partials_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            now = time.time()
            stale = cache / f"tiny.{'a' * 32}.pt.download"
            fresh = cache / f"tiny.{'b' * 32}.pt.download"
            other_model = cache / f"base.{'c' * 32}.pt.download"
            installed = cache / "tiny.pt"
            arbitrary = cache / "important.txt"
            for p in (stale, fresh, other_model, installed, arbitrary):
                p.write_bytes(b"keep or remove")
            old_time = now - 7200
            for p in (stale, other_model):
                os.utime(p, (old_time, old_time))

            count = prune_stale_whisper_downloads(cache, ["tiny"], now=now)
            self.assertEqual(count, 1)
            self.assertFalse(stale.exists())
            for p in (fresh, other_model, installed, arbitrary):
                self.assertTrue(p.exists(), p.name)

    def test_no_folder_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "not-created"
            self.assertEqual(prune_stale_whisper_downloads(missing, ["tiny"]), 0)

    def test_worker_cleans_stale_partial_and_installs_sha_verified_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            stale = cache / f"tiny.{'c' * 32}.pt.download"
            stale.write_bytes(b"interrupted earlier download")
            old_time = time.time() - 7200
            os.utime(stale, (old_time, old_time))
            body = b"mock-whisper-model"
            digest = hashlib.sha256(body).hexdigest()
            response = io.BytesIO(body)
            response.headers = {"Content-Length": str(len(body))}
            harness = SimpleNamespace(download_queue=queue.Queue())

            with (
                mock.patch.object(gui, "CACHE_DIR", cache),
                mock.patch.dict(gui.MODEL_DOWNLOAD_URLS, {"tiny": f"https://example.test/{digest}/tiny.pt"}),
                mock.patch.object(gui.urllib.request, "urlopen", return_value=response),
            ):
                gui.Transcriber9000App._download_worker(harness, "tiny")

            self.assertFalse(stale.exists())
            self.assertEqual((cache / "tiny.pt").read_bytes(), body)
            events = list(harness.download_queue.queue)
            self.assertEqual(events[-1], ("done", "tiny"))
            self.assertFalse(list(cache.glob("*.pt.download")))

    def test_corrupt_model_is_not_installed_and_temp_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            body = b"corrupt"
            response = io.BytesIO(body)
            response.headers = {"Content-Length": str(len(body))}
            harness = SimpleNamespace(download_queue=queue.Queue())
            with (
                mock.patch.object(gui, "CACHE_DIR", cache),
                mock.patch.dict(gui.MODEL_DOWNLOAD_URLS, {"tiny": f"https://example.test/{'a' * 64}/tiny.pt"}),
                mock.patch.object(gui.urllib.request, "urlopen", return_value=response),
            ):
                gui.Transcriber9000App._download_worker(harness, "tiny")
            self.assertFalse((cache / "tiny.pt").exists())
            self.assertFalse(list(cache.glob("*.pt.download")))
            self.assertEqual(harness.download_queue.get_nowait()[0], "progress")
            self.assertEqual(harness.download_queue.get_nowait()[0], "error")


if __name__ == "__main__":
    unittest.main()
