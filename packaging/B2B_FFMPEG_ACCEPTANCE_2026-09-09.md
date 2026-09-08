# Milestone B.2b pinned LGPL FFmpeg acceptance — 2026-09-09

## Artifact and compliance checks

- BtbN release tag: `autobuild-2026-09-07-15-39`.
- Variant: `win64-lgpl` (`ffmpeg-n8.1.2-51-g7ba069f4f1-win64-lgpl-8.1.zip`).
- Staged, portable and installed `ffmpeg.exe` SHA-256:
  `931223B06750580BB8DF494AD10F074D8390F76EF3E1C25E1CEC97135AA6C3FC`.
- Reported configuration contains neither `--enable-gpl` nor
  `--enable-nonfree`: PASS.
- New LGPL license is frozen into the payload; old Gyan license directory is
  absent: PASS.

## Verification

- Media regression through the unchanged transcription worker:
  short WAV → TXT PASS; MP3 → TXT PASS; short MP4 derived from an existing
  WebM fixture → TXT PASS.
- Deterministic suite: 145 tests PASS.
- Portable rebuild: PASS.
- Installer rebuild: PASS.
- Silent per-user install: PASS.
- Installed GUI remained alive after five seconds: PASS.
- Installed frozen-worker transcription using bundled Whisper `base.pt`,
  bundled BtbN FFmpeg and redirected worker I/O: PASS (`exit 0`, 70-byte TXT).

No LLM/report acceptance was run. No GUI, model manager, report logic or
transcription logic was changed.

## Release artifacts

- Setup: `dist/installer/Transcriber 9000 Setup.exe`, `2774028850` bytes,
  SHA-256 `F37E5F58FE82CDF55006E0986CD7D3B361DADDB6AD78B3D64C04D05EE9EDE5C9`.
- FFmpeg source/reference package:
  `dist/source/Transcriber9000-ffmpeg-n8.1.2-51-lgpl-source-reference.zip`,
  `16903611` bytes, SHA-256
  `07936124CA8583C09074163AA3974A9EAD4EE3B4F21CF374A703E9A73C501A74`.
