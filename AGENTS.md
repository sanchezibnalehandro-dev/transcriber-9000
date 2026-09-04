# AGENTS.md

## Project Structure

- `transcriber_app.py` is the Windows GUI and user interaction layer.
- `transcriber_core.py` is the transcription engine and command-line worker.
- Keep GUI concerns out of the core where practical.
- Preserve the local-only processing model unless the project owner explicitly changes that requirement.

## Transcription Rules

- Take source audio and video only from `input`.
- Save all generated results to `output`.
- Use the installed local Whisper environment in `.venv`; do not send audio or video to external services.
- Treat Russian as the primary transcription language.
- Transcribe speech as-is; do not translate it to another language.
- Create plain text output in `TXT` format by default.
- Create `SRT` files with timestamps when requested.
- Preserve the original source filename in each result filename.
- Do not silently overwrite existing results; explain the conflict first.
- Do not delete, move, or modify source files.
- If an error occurs, explain the cause before proposing fixes.
- After each transcription, show the list of created files with full paths.
- Before large changes, show a short plan first.
