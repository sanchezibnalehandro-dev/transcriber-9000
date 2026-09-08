# Milestone B.2a local acceptance — 2026-09-08

Artifact:

- `dist/installer/Transcriber 9000 Setup.exe`
- size: `2761284049` bytes (`2633.37 MiB`)
- SHA-256: `0F321F145D41F5EADC1A6B4DF890CB00F7A49446842E54D53A371F2BD4F7A926`
- version: `1.0.0-rc.1` / Windows file version `1.0.0.0`
- Authenticode: `NotSigned` (declared controlled-RC limitation)

Verification:

1. Deterministic suite: PASS, 144 tests.
2. Portable rebuild: PASS, 3552 files / 6096028264 bytes / no GGUF.
3. Installed application, helpers, FFmpeg, notices and `LICENSES`: PASS.
4. Installed GUI remained alive after five seconds: PASS. No transcription,
   model, LLM, or E2E run was performed.
5. Installed FFmpeg SHA-256 remained
   `2CE797A0F88D7F067180338FB227F7B1928EA727BD9A4D7A1D022F7C52AF71A3`.
6. Installed MSVC runtime was version `14.44.35211.0` with the pinned official
   Microsoft hashes at both application root and CUDA-helper directory: PASS.
7. Silent uninstall exit 0; application/runtime and `LICENSES` removed: PASS.
8. Installed `input` and `output` marker files retained: PASS.
9. `%LOCALAPPDATA%/Transcriber 9000` marker retained and both pre-existing model
   files retained with unchanged name, length, and modification time: PASS.

This is a local same-machine packaging smoke, not the pending clean Windows 11
x64 VM acceptance. FFmpeg public redistribution remains blocked by the missing
complete Corresponding Source package documented in `FFMPEG_PROVENANCE.md`.
