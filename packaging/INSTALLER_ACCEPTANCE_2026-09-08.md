# Milestone B.1 installer acceptance — 2026-09-08

Installer artifact:

- path: `dist/installer/Transcriber 9000 Setup.exe`;
- size: `2761105967` bytes (`2633.20 MiB`);
- SHA-256: `F286AB62944A21B6CB66926118E44854FDECD9DCBAADE4A4D994614CCD2048A2`;
- display version: `1.0.0-rc.1`;
- Windows file/product version: `1.0.0.0`.

Acceptance flow:

1. Silent per-user install to
   `%LOCALAPPDATA%\Programs\Transcriber 9000`: PASS.
2. Installed GUI launch: PASS.
3. Model manager showed both existing choices: Qwen 3.5 9B Q4_K_M as
   Recommended and Qwen 3.5 4B Q4_K_M as Lightweight: PASS.
4. Real transcription smoke using the bundled Whisper `base.pt`, ffmpeg and
   frozen worker dispatch: PASS (`exit 0`); the short WAV produced a 70-byte
   UTF-8 TXT result.
5. Uninstall: PASS after a targeted fix to remove the generated
   `.cache/transcriber` runtime subtree. EXE, CPU/CUDA helpers, Whisper model,
   ffmpeg, uninstaller, Start Menu shortcut and uninstall registry entry were
   removed.
6. Retention: PASS. Installed `input` and `output` remained with the acceptance
   WAV, TXT and logs. `%LOCALAPPDATA%\Transcriber 9000` remained. Both GGUF
   files retained their expected catalog sizes and SHA-256 values:
   `13C16F426047E2DE38CD075BDADE4A7BCBC8C774384876F677740CDA65F8A983`
   (4B) and
   `D784CE9EDA1A5A7B51E8F705A9E6310844BF4F173654D115823C775FDEA56D43`
   (9B).

No LLM semantic acceptance was run. Signing, SBOM, offline model bundles and
expanded GPU testing remain outside Milestone B.1.
