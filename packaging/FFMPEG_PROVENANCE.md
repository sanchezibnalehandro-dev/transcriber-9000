# Pinned BtbN FFmpeg LGPL provenance

## Exact binary artifact

- BtbN repository: `https://github.com/BtbN/FFmpeg-Builds`
- Release tag: `autobuild-2026-09-07-15-39`
- Release/tag commit: `93ce3b03f579014264943946c11b96ea6d7f57ec`
- Variant: `win64-lgpl` with Windows 8.1 compatibility
- Archive: `ffmpeg-n8.1.2-51-g7ba069f4f1-win64-lgpl-8.1.zip`
- Release asset id: `549007162`
- Archive size: `146107160` bytes
- Archive SHA-256: `232464B6F9F1D55FA42C1B0E7AE1C9CA5A19272BA61229E8B32A93751055E135`
- Pinned download: `https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-07-15-39/ffmpeg-n8.1.2-51-g7ba069f4f1-win64-lgpl-8.1.zip`
- `ffmpeg.exe` size: `113987584` bytes
- `ffmpeg.exe` SHA-256: `931223B06750580BB8DF494AD10F074D8390F76EF3E1C25E1CEC97135AA6C3FC`

`build_portable.ps1` takes this exact extracted executable from `.release-input`,
verifies its SHA-256 and reported version, rejects GPL/nonfree configuration,
and then stages it. The ignored development copy under `tools/ffmpeg/bin` was
replaced with the same binary for local media regression.

## Reported version and configuration

```text
ffmpeg version n8.1.2-51-g7ba069f4f1-20260907 Copyright (c) 2000-2026 the FFmpeg developers
built with gcc 15.2.0 (crosstool-NG 1.28.0.23_185f348)
configuration: --prefix=/ffbuild/prefix --pkg-config-flags=--static --pkg-config=pkg-config --cross-prefix=x86_64-w64-mingw32- --arch=x86_64 --target-os=mingw32 --enable-version3 --disable-debug --disable-w32threads --enable-pthreads --enable-iconv --enable-zlib --enable-libxml2 --enable-libvmaf --enable-fontconfig --enable-libharfbuzz --enable-libfreetype --enable-libfribidi --enable-vulkan --enable-libshaderc --enable-libvorbis --disable-libxcb --disable-xlib --disable-libpulse --enable-gmp --enable-lzma --enable-liblcevc-dec --enable-opencl --enable-amf --enable-libaom --disable-avisynth --enable-chromaprint --enable-libdav1d --disable-libdavs2 --disable-libdvdread --disable-libdvdnav --disable-libfdk-aac --enable-ffnvcodec --enable-cuda-llvm --disable-frei0r --enable-libgme --enable-libkvazaar --enable-libaribb24 --enable-libaribcaption --enable-libass --enable-libbluray --enable-libjxl --enable-libmp3lame --enable-libopus --enable-libplacebo --enable-librist --enable-libssh --enable-libtheora --enable-libvpx --enable-libwebp --enable-libzmq --enable-lv2 --enable-libvpl --enable-openal --enable-liboapv --enable-libopencore-amrnb --enable-libopencore-amrwb --enable-libopenh264 --enable-libopenjpeg --enable-libopenmpt --enable-librav1e --disable-librubberband --enable-schannel --enable-sdl2 --enable-libsnappy --enable-libsoxr --enable-libsrt --enable-libsvtav1 --enable-libtwolame --enable-libuavs3d --disable-libdrm --enable-vaapi --disable-libvidstab --enable-libvvenc --disable-whisper --disable-libx264 --disable-libx265 --disable-libxavs2 --disable-libxvid --enable-libzimg --enable-libzvbi --extra-cflags=-DLIBTWOLAME_STATIC --extra-cxxflags= --extra-libs=-lgomp --extra-ldflags=-pthread --extra-ldexeflags= --cc=x86_64-w64-mingw32-gcc --cxx=x86_64-w64-mingw32-g++ --ar=x86_64-w64-mingw32-gcc-ar --ranlib=x86_64-w64-mingw32-gcc-ranlib --nm=x86_64-w64-mingw32-gcc-nm --extra-version=20260907
libavutil      60. 26.102 / 60. 26.102
libavcodec     62. 28.102 / 62. 28.102
libavformat    62. 12.102 / 62. 12.102
libavdevice    62.  3.102 / 62.  3.102
libavfilter    11. 14.102 / 11. 14.102
libswscale      9.  5.102 /  9.  5.102
libswresample   6.  3.102 /  6.  3.102
```

The exact output contains neither `--enable-gpl` nor `--enable-nonfree`. It
does contain `--enable-version3`. The archive's `LICENSE.txt` is the GNU Lesser
General Public License version 3 and is bundled at
`LICENSES/FFmpeg-BtbN-n8.1.2-51/LICENSE.txt`.

## Exact source and build recipe

- FFmpeg source commit: `7ba069f4f11d126f52a740156dbab6476a8a865a`
- FFmpeg source: `https://github.com/FFmpeg/FFmpeg/commit/7ba069f4f11d126f52a740156dbab6476a8a865a`
- FFmpeg source snapshot SHA-256: `6EB57FB4DE774031A491919A90DC74BBDF617D38BFEACBEF492586CA2184DDC9`
- BtbN build recipe commit: `93ce3b03f579014264943946c11b96ea6d7f57ec`
- BtbN recipe tree: `https://github.com/BtbN/FFmpeg-Builds/tree/93ce3b03f579014264943946c11b96ea6d7f57ec`
- BtbN recipe snapshot SHA-256: `4A6CE62551016D7C2A2E80F80FC6E5016E6F402B778A7D3280152334C76EFC42`
- Recipe invocation represented by the asset: `./build.sh win64 lgpl 8.1`

The recipe snapshot includes the pinned package recipes and patches used to
obtain external-library sources. `packaging/FFMPEG_SOURCE_PACKAGE.txt` is the
publication manifest. The release build creates
`dist/source/Transcriber9000-ffmpeg-n8.1.2-51-lgpl-source-reference.zip`; it
must remain available beside the Setup download.

- Source/reference package size: `16903611` bytes
- Source/reference package SHA-256: `07936124CA8583C09074163AA3974A9EAD4EE3B4F21CF374A703E9A73C501A74`

## Compliance decision

**PASS for the requested GPL-blocker replacement.** The Gyan GPL build is no
longer staged or bundled, and the pinned BtbN artifact does not enable GPL or
nonfree mode. Public distribution still carries the normal LGPL obligation to
provide the matching source and license; this release satisfies the minimum
operational requirement only when the documented source/reference package is
published and retained beside Setup.
