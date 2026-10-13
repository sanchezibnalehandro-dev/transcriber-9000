# macOS Apple Silicon M0–M2 verification

## M0 audit and baseline

- Base: `work/crossplatform-20261013` at `45f957345a8a81713a29f01ba7a7a6d2c47d3d67`.
- Local Windows baseline before changes: Python 3.12.14, `python -m unittest discover -s tests -v`, **145 tests, OK**. This did not exercise macOS or a frozen macOS GUI.
- `runtime_paths.py` originally treated the executable directory as the resource and writable root. `transcriber_core.py` wrote `input`, `output`, and Whisper cache beside the code and required `ffmpeg.exe`; `transcriber_app.py` used `os.startfile`, Windows font/scaling defaults, frozen worker subprocesses, and TkDND. The Windows PyInstaller spec requires Windows FFmpeg and llama helpers. The macOS build therefore needs its own spec and user-data paths.
- The report catalog and product documents recommend Qwen 3.5 9B and allow 4B as a lighter option. `report_pipeline.py` still exposes unused `EXPECTED_MODEL_*` constants pinned to 4B, with a matching metadata test. The report CLI receives a selected model path, so these constants do not select the model. This discrepancy is recorded here; the report backend and its tests are not changed in M0–M2.
- The existing 145 tests include historical `report_engine` tests. Passing them does not mean the evidence pipeline is used in production.

## M1 local and CI checks

- Local Windows Python 3.12.14 after M1: `python -m unittest discover -s tests -v`, **151 tests, OK**. `git diff --check`, Python compilation and `bash -n` on packaging scripts also passed.
- PR CI initially found two runner differences: temporary path aliases (`/var` versus `/private/var`, and Windows short paths) and a Windows report-model test that assumed a same-size rewrite always changes its timestamp. The path assertions now compare resolved paths, and the test sets a changed timestamp explicitly; report backend behavior was not modified.
- The macOS runner exposes a 682×288 virtual screen. The real-window geometry assertion is skipped there when the screen is smaller than the configured window; the other UI state tests still run. This is not a manual visual check of the macOS GUI.

## M2 release candidate evidence

- [Final GitHub Actions run 38419877194](https://github.com/sanchezibnalehandro-dev/transcriber-9000/actions/runs/38419877194), commit `7ce18e8`: Windows regression and macOS arm64 jobs both **success**. Windows ran all 151 deterministic tests and the worker environment check. The macOS job ran 27 targeted tests, **OK (skipped=1)**; the only skip was real-window geometry on the runner's 682×288 virtual screen.
- A separate real end-to-end smoke used macOS `say` to make speech, FFmpeg 8.1.2 to convert it, and checksum-verified Whisper tiny in the frozen worker. It produced nonempty TXT (`This is a transcription smoke test 123.`) and SRT; the JSON result reported success.
- `codesign --verify --deep --strict` passed for the built app and the ZIP-extracted app; the signature was ad-hoc. All 107 Mach-O files had an arm64 slice. FFmpeg's `otool -L` linked only macOS system libraries. The app contained 2,862 regular files, totaling 535,880,637 bytes; `du -sk` reported 529,804 KiB. The app tree SHA-256 was `478d5b22e2390bd9878be96325be0d2532f7d24b614f96771b06497e77d69000`, equal before packaging and after extraction.
- The inner distributable ZIP was 184,356,816 bytes with SHA-256 `ae06ebc357ac25c73f2c58382994b7658f3316072f2784a687f3f5521f6b9a06`. `unzip -t`, source-archive hash validation, extracted-app signature/architecture checks, tree digest comparison and extracted-worker environment check passed. The [Actions artifact](https://github.com/sanchezibnalehandro-dev/transcriber-9000/actions/runs/38419877194/artifacts/11825369113) contains this ZIP and its `.sha256` sidecar. The artifact service reports 182,405,759 bytes for its outer compressed download.
- FFmpeg source `ffmpeg-8.1.2.tar.xz` was fetched from `ffmpeg.org` with pinned SHA-256 `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`; its matching source archive, configuration, LGPL notice, component notices and build manifest are in the distributable ZIP.

CI verification is not a manual test on a user's Mac.

## Manual Mac checks still required

Cold launch from Finder, Gatekeeper behavior, drag-and-drop, file picker, model download and cancellation, Russian audio/video, long recording, visible GUI layout/scaling, writable data paths, and output creation on a separate Apple Silicon Mac.
