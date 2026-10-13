# macOS Apple Silicon M0–M2 verification

## M0 audit and baseline

- Base: `work/crossplatform-20261013` at `45f957345a8a81713a29f01ba7a7a6d2c47d3d67`.
- Local Windows baseline before changes: Python 3.12.14, `python -m unittest discover -s tests -v`, **145 tests, OK**. This did not exercise macOS or a frozen macOS GUI.
- `runtime_paths.py` originally treated the executable directory as the resource and writable root. `transcriber_core.py` wrote `input`, `output`, and Whisper cache beside the code and required `ffmpeg.exe`; `transcriber_app.py` used `os.startfile`, Windows font/scaling defaults, frozen worker subprocesses, and TkDND. The Windows PyInstaller spec requires Windows FFmpeg and llama helpers. The macOS build therefore needs its own spec and user-data paths.
- The report catalog and product documents recommend Qwen 3.5 9B and allow 4B as a lighter option. `report_pipeline.py` still exposes unused `EXPECTED_MODEL_*` constants pinned to 4B, with a matching metadata test. The report CLI receives a selected model path, so these constants do not select the model. This discrepancy is recorded here; the report backend and its tests are not changed in M0–M2.
- The existing 145 tests include historical `report_engine` tests. Passing them does not mean the evidence pipeline is used in production.

## M1/M2 evidence

Record exact local and GitHub Actions commands, counts, failures, skipped checks, artifact sizes and hashes here before release. CI verification is not a manual test on a user's Mac.

## Manual Mac checks still required

Cold launch from Finder, Gatekeeper behavior, drag-and-drop, file picker, model download and cancellation, Russian audio/video, long recording, visible GUI layout/scaling, writable data paths, and output creation on a separate Apple Silicon Mac.
