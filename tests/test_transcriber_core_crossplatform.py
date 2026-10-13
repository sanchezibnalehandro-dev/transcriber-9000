from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import transcriber_core as core


class TranscriptionContractTests(unittest.TestCase):
    def test_mock_transcription_writes_txt_and_srt_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_dir = root / "input"
            output_dir = root / "output"
            cache_dir = root / "cache"
            input_dir.mkdir()
            output_dir.mkdir()
            cache_dir.mkdir()
            source = input_dir / "встреча.wav"
            source.write_bytes(b"audio")
            model_bytes = b"mock-model"
            (cache_dir / "tiny.pt").write_bytes(model_bytes)
            digest = hashlib.sha256(model_bytes).hexdigest()
            ffmpeg = root / "ffmpeg"
            ffmpeg.write_bytes(b"binary")
            result = {"text": "Привет, мир", "segments": [{"start": 0, "end": 1.5, "text": "Привет, мир"}]}
            whisper = SimpleNamespace(load_model=mock.Mock(return_value=SimpleNamespace(transcribe=mock.Mock(return_value=result))))
            with (
                mock.patch.multiple(core, INPUT_DIR=input_dir, OUTPUT_DIR=output_dir, CACHE_DIR=cache_dir, FFMPEG_EXE=ffmpeg),
                mock.patch.dict(core.MODEL_INFO, {"tiny": {**core.MODEL_INFO["tiny"], "size_mb": 0}}),
                mock.patch.dict(core.MODEL_DOWNLOAD_URLS, {"tiny": f"https://example.test/{digest}/tiny.pt"}),
                mock.patch.dict(sys.modules, {"whisper": whisper}),
                mock.patch.object(core, "get_torch_device_label", return_value=("cpu", "CPU")),
            ):
                paths = core.transcribe_file(core.TranscriptionRequest(source, "ru", "fast", ("txt", "srt")))
                self.assertEqual(len(paths), 2)
                self.assertEqual(paths[0].read_text(encoding="utf-8"), "Привет, мир\n")
                self.assertIn("00:00:01,500", paths[1].read_text(encoding="utf-8"))
                with self.assertRaises(core.UserVisibleError):
                    core.transcribe_file(core.TranscriptionRequest(source, "ru", "fast", ("txt", "srt")))
                self.assertEqual(paths[0].read_text(encoding="utf-8"), "Привет, мир\n")

    def test_srt_writer_refuses_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "meeting.srt"
            target.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                core.write_srt(target, [{"start": 0, "end": 1, "text": "new"}])
            self.assertEqual(target.read_text(encoding="utf-8"), "existing")


if __name__ == "__main__":
    unittest.main()
