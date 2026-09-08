from __future__ import annotations

import io
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import transcriber_entry


class WorkerDispatchTests(unittest.TestCase):
    def test_transcription_worker_forwards_arguments_without_gui(self) -> None:
        worker_main = mock.Mock(return_value=7)
        with mock.patch.dict(sys.modules, {"transcriber_core": SimpleNamespace(main=worker_main)}):
            result = transcriber_entry.run_worker("transcription", ["--env-check"])
        self.assertEqual(result, 7)
        worker_main.assert_called_once_with(["--env-check"])

    def test_report_worker_preserves_machine_readable_stdout(self) -> None:
        def report_main(_argv: list[str]) -> int:
            print('{"output_path": "C:/готово.md"}')
            return 0

        output = io.StringIO()
        module = SimpleNamespace(ReportPipelineError=RuntimeError, main=report_main)
        with (
            mock.patch.dict(sys.modules, {"report_pipeline": module}),
            mock.patch.object(transcriber_entry.sys, "stdout", output),
        ):
            result = transcriber_entry.run_worker("report", ["--model", "model.gguf"])
        self.assertEqual(result, 0)
        self.assertIn("готово.md", output.getvalue())

    def test_worker_flag_is_removed_before_dispatch(self) -> None:
        with mock.patch.object(transcriber_entry, "run_worker", return_value=0) as run_worker:
            result = transcriber_entry.main(["--worker", "report", "--device", "cpu"])
        self.assertEqual(result, 0)
        run_worker.assert_called_once_with("report", ["--device", "cpu"])


if __name__ == "__main__":
    unittest.main()
