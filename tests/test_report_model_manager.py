from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path

from report_model_manager import (
    ReportModelDownloadCancelled,
    ReportModelError,
    ReportModelManager,
)


class FakeResponse:
    def __init__(self, content: bytes, cancel_event: threading.Event | None = None) -> None:
        self.content = content
        self.offset = 0
        self.cancel_event = cancel_event

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int) -> bytes:
        if self.offset and self.cancel_event is not None:
            self.cancel_event.set()
        chunk = self.content[self.offset : self.offset + min(size, 2)]
        self.offset += len(chunk)
        return chunk


def write_catalog(path: Path, first: bytes, second: bytes = b"second") -> None:
    def entry(model_id: str, filename: str, content: bytes) -> dict:
        revision = "a" * 40 if model_id == "nine" else "b" * 40
        return {
            "id": model_id,
            "name": model_id,
            "badge": "Recommended" if model_id == "nine" else "Lightweight",
            "description": "description",
            "quality_note": "quality",
            "repository": "owner/repo",
            "revision": revision,
            "url": f"https://example.invalid/{revision}/{filename}",
            "filename": filename,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    path.write_text(
        json.dumps(
            {"schema_version": 1, "models": [entry("nine", "nine.gguf", first), entry("four", "four.gguf", second)]}
        ),
        encoding="utf-8",
    )


class ReportModelManagerTests(unittest.TestCase):
    def make_manager(self, root: Path, content: bytes = b"model-data") -> ReportModelManager:
        catalog = root / "catalog.json"
        write_catalog(catalog, content)
        return ReportModelManager(
            catalog_path=catalog,
            models_dir=root / "models",
            settings_path=root / "settings.json",
        )

    def test_download_uses_part_validates_and_selects_first_model(self) -> None:
        content = b"model-data"
        with tempfile.TemporaryDirectory() as temporary:
            manager = self.make_manager(Path(temporary), content)
            progress: list[tuple[int, int]] = []
            target = manager.download(
                "nine",
                progress=lambda done, total: progress.append((done, total)),
                urlopen=lambda *_args, **_kwargs: FakeResponse(content),
            )
            self.assertEqual(target.read_bytes(), content)
            self.assertFalse(manager.part_path("nine").exists())
            self.assertTrue(manager.status("nine").installed)
            self.assertEqual(manager.active_model_id(), "nine")
            self.assertEqual(progress[-1], (len(content), len(content)))

    def test_normal_status_uses_validation_record_without_rehash(self) -> None:
        content = b"model-data"
        with tempfile.TemporaryDirectory() as temporary:
            manager = self.make_manager(Path(temporary), content)
            manager.download("nine", urlopen=lambda *_args, **_kwargs: FakeResponse(content))
            self.assertEqual(manager.status("nine").state, "installed")

    def test_changed_file_requires_full_reverify(self) -> None:
        content = b"model-data"
        with tempfile.TemporaryDirectory() as temporary:
            manager = self.make_manager(Path(temporary), content)
            target = manager.download("nine", urlopen=lambda *_args, **_kwargs: FakeResponse(content))
            target.write_bytes(b"broken-dat")
            self.assertEqual(manager.status("nine").state, "unverified")
            with self.assertRaises(ReportModelError):
                manager.verify("nine")

    def test_cancel_removes_part_and_never_creates_final_file(self) -> None:
        content = b"model-data"
        with tempfile.TemporaryDirectory() as temporary:
            manager = self.make_manager(Path(temporary), content)
            cancelled = threading.Event()
            with self.assertRaises(ReportModelDownloadCancelled):
                manager.download(
                    "nine",
                    cancel_event=cancelled,
                    urlopen=lambda *_args, **_kwargs: FakeResponse(content, cancelled),
                )
            self.assertFalse(manager.part_path("nine").exists())
            self.assertFalse(manager.model_path("nine").exists())

    def test_selection_persists_and_delete_clears_it(self) -> None:
        content = b"model-data"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = self.make_manager(root, content)
            manager.download("nine", urlopen=lambda *_args, **_kwargs: FakeResponse(content))
            reloaded = ReportModelManager(
                catalog_path=root / "catalog.json",
                models_dir=root / "models",
                settings_path=root / "settings.json",
            )
            self.assertEqual(reloaded.active_model_id(), "nine")
            reloaded.delete("nine")
            self.assertIsNone(reloaded.active_model_id())
            self.assertFalse(reloaded.model_path("nine").exists())


if __name__ == "__main__":
    unittest.main()
