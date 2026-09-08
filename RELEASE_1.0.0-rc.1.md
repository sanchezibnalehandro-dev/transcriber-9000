# Transcriber 9000 1.0.0-rc.1 release metadata

## Identity

- Publisher: **REQUIRED — not provided**. The current installer value
  `Transcriber 9000` is a product-name placeholder, not a verified legal
  publisher identity.
- Support/contact: **REQUIRED — not provided**.
- Source base checkpoint: `44cc99660b92046827a315c7aef39be91b95d2e6`.
- Final release source checkpoint: **PENDING** because B.2a changes are
  intentionally uncommitted.
- Version: `1.0.0-rc.1` (`1.0.0.0` Windows file/product version).

## Artifact

- Setup path: `dist/installer/Transcriber 9000 Setup.exe`
- Setup SHA-256: `F37E5F58FE82CDF55006E0986CD7D3B361DADDB6AD78B3D64C04D05EE9EDE5C9`
- Setup size: `2774028850` bytes (`2645.52 MiB`)
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
still pending publisher/contact completion and a clean Windows 11 x64 VM
acceptance.
