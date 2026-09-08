# Milestone A portable build

This directory builds one windowed PyInstaller `onedir` application. The same
frozen executable dispatches the existing transcription and report workers;
there is no packaged `python.exe` command or second worker application.

## Build inputs

- Windows x64 and Python 3.12 in a clean build environment;
- runtime dependencies from `requirements.txt`;
- pinned build dependencies from `requirements-build.txt`;
- Rust stable with the `x86_64-pc-windows-gnullvm` target;
- LLVM-MinGW UCRT 22 and the CUDA 12.4 toolkit used by the accepted RTX 3060 helper;
- local Whisper `base.pt` and the pinned BtbN `win64-lgpl` FFmpeg artifact at
  `.release-input/ffmpeg-n8.1.2-51-g7ba069f4f1-win64-lgpl-8.1/`;
- the accepted CUDA helper copied as the physical file
  `.release-input/llama-helper-cuda-sm86.exe`.
- app-local MSVC runtime DLLs prepared from the pinned, Authenticode-verified
  official Microsoft `VC_redist.x64.exe`; `System32` is not a build source.

The accepted CUDA helper is 193364992 bytes and has SHA-256
`0E985621C2F90636728D28C45C55129C4E017BB09F0CFA0293C627147F2A32FF`.
The build refuses a different binary. `nvcuda.dll` is never staged; it must be
provided by the installed NVIDIA driver.

The accepted FFmpeg executable is from BtbN release
`autobuild-2026-09-07-15-39`, reports
`n8.1.2-51-g7ba069f4f1-20260907`, and has SHA-256
`931223B06750580BB8DF494AD10F074D8390F76EF3E1C25E1CEC97135AA6C3FC`.
The build refuses another binary or a configuration containing
`--enable-gpl`/`--enable-nonfree`. See `FFMPEG_PROVENANCE.md`.

## Sequence

```powershell
python -m pip install -r requirements.txt -r requirements-build.txt
rustup target add x86_64-pc-windows-gnullvm
./packaging/build_cpu_helper.ps1
./packaging/prepare_msvc_redist.ps1 -Dark C:\path\to\wix314\dark.exe
./packaging/build_portable.ps1
```

`build_portable.ps1` copies every ignored/native input into
`.release-staging` before PyInstaller runs. The resulting
`dist/Transcriber 9000` therefore contains ordinary files rather than the
development checkout's junctions. It also creates writable `input`, `output`,
and `.cache/transcriber/runs` directories.

`prepare_msvc_redist.ps1` verifies Microsoft VC Redistributable 14.44.35211.0,
extracts the permitted app-local DLLs, and pins their hashes. See
`MSVC_REDIST_PROVENANCE.md`. The `LICENSES` directory and
`THIRD_PARTY_NOTICES.md` are frozen into the payload.

The normal portable payload intentionally contains no GGUF. Report models and
the persisted active selection live under
`%LOCALAPPDATA%/Transcriber 9000`. See `README_PORTABLE.txt` in the built folder.

## Milestone B.1 Windows installer

Inno Setup 6 packages the proven portable directory without rebuilding or
changing application semantics:

```powershell
./packaging/build_installer.ps1
```

The result is `dist/installer/Transcriber 9000 Setup.exe`. It installs per-user
to `%LOCALAPPDATA%/Programs/Transcriber 9000`, creates a Start Menu shortcut,
and offers an unchecked Desktop shortcut task. The build fails if the portable
payload is missing a required helper/runtime asset, contains a GGUF, or contains
a junction.

The uninstaller removes installed application/runtime files. It does not touch
the model manager data under `%LOCALAPPDATA%/Transcriber 9000`; installed
`input` and `output` directories are marked `uninsneveruninstall` so user files
and results remain after uninstall.
