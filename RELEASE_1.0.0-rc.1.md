# Transcriber 9000 1.0.0-rc.1 release metadata

## Identity

- Publisher: `sanchez_ai`.
- Support/contact: [sanchezibnalehandro@gmail.com](mailto:sanchezibnalehandro@gmail.com).
- Source base checkpoint: `44cc99660b92046827a315c7aef39be91b95d2e6`.
- Current compliance checkpoint: `ed6baa6`.
- Final release source checkpoint: **PENDING** because this metadata update is
  intentionally uncommitted.
- Version: `1.0.0-rc.1` (`1.0.0.0` Windows file/product version).

## Artifact

- Setup path: `dist/installer/Transcriber 9000 Setup.exe`
- Setup SHA-256: `117EF78C70E992DE9D27BACE59EA9C39825AA6DB5EA2EB5708F4B7089DE42B98`
- Setup size: `2774028924` bytes (`2645.52 MiB`)
- FFmpeg source/reference package:
  `dist/source/Transcriber9000-ffmpeg-n8.1.2-51-lgpl-source-reference.zip`
  (`16903611` bytes; SHA-256
  `07936124CA8583C09074163AA3974A9EAD4EE3B4F21CF374A703E9A73C501A74`).
- Signing: Unsigned controlled RC. Microsoft Defender SmartScreen may show an
  unknown/unrecognized publisher warning; recipients must be told the expected
  SHA-256 through a trusted channel.

## Supported and verified scope

- Windows 11 x64: verified.
- Windows 10 x64: unverified.
- RTX 3060 CUDA: verified.
- CPU fallback: supported.
- Models: downloaded separately through the model manager; no GGUF is bundled.
- Clean Windows VM: pending external-RC acceptance.

## Release gate

The former Gyan GPL build blocker is removed by the pinned BtbN `win64-lgpl`
runtime. Publish the source/reference package named in
`packaging/FFMPEG_PROVENANCE.md` beside Setup. Controlled external release is
still pending a clean Windows 11 x64 VM acceptance. Publisher and support
metadata are complete for this controlled RC.
