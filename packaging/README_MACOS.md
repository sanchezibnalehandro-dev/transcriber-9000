# Transcriber 9000 for macOS Apple Silicon

This release candidate contains the Python runtime, Tk, Whisper, PyTorch and FFmpeg. No Python, pip, Homebrew or FFmpeg installation is needed on the user's Mac. Whisper models are downloaded separately from **Settings**, after confirmation; source media stays local.

Download the `Transcriber9000-macOS-arm64` artifact from the successful [GitHub Actions run](https://github.com/sanchezibnalehandro-dev/transcriber-9000/actions), unzip it, and move `Transcriber 9000.app` to Applications if desired. The artifact also includes this file, FFmpeg's corresponding source archive and a build manifest. A GitHub login with repository access may be required.

The app has only an ad-hoc signature. It has no Apple Developer ID signature or notarization. Gatekeeper may block its first launch. Use Finder's **Open** context menu for this specific app and review the warning before choosing to open it; do not turn off Gatekeeper system-wide. Signing and notarization are later work.

The app creates `~/Library/Application Support/Transcriber 9000/input`, `output` and `.cache/whisper`. It copies files selected outside `input` into that folder, leaving originals in place. Results keep the source file name and are never silently overwritten. Settings offers optional import from an older portable folder; on first launch the prompt appears only if older data was detected. Imported files are copied, and collisions are skipped.

Local AI reports are unavailable on macOS in this candidate. TXT and SRT transcription remain available. This release targets arm64 only; Intel and universal2, Developer ID signing, notarization, and macOS AI-report backend are outside M0–M2.

The CI run verifies a real short Whisper tiny transcription, the packaged worker, FFmpeg, arm64 slices and ad-hoc signing. A separate Mac user test is still needed for Finder launch, Gatekeeper, visible GUI, drag-and-drop, media variety, long recordings and model downloads.
