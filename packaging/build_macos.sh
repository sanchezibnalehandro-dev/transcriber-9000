#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
test "$(uname -m)" = arm64

ffmpeg_version=8.1.2
ffmpeg_sha=464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c
build_root="${RUNNER_TEMP:?}/transcriber-macos-build"
stage_root="$PWD/.release-staging-macos"
python_env="$build_root/python-env"
mkdir -p "$build_root" "$stage_root/tools/ffmpeg/bin" "$stage_root/licenses"

python3 -m venv "$python_env"
source "$python_env/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements-macos.txt
python -c 'import tkinter, torch, whisper, customtkinter, tkinterdnd2, PyInstaller; print("macOS build imports OK")'

archive="$build_root/ffmpeg-$ffmpeg_version.tar.xz"
curl --fail --location --retry 3 --output "$archive" "https://ffmpeg.org/releases/ffmpeg-$ffmpeg_version.tar.xz"
actual_sha="$(shasum -a 256 "$archive" | awk '{print $1}')"
test "$actual_sha" = "$ffmpeg_sha"
tar -xf "$archive" -C "$build_root"
pushd "$build_root/ffmpeg-$ffmpeg_version" >/dev/null
./configure \
  --prefix="$build_root/ffmpeg-install" \
  --disable-doc --disable-ffplay --disable-ffprobe \
  --disable-gpl --disable-nonfree --disable-autodetect \
  --enable-static --disable-shared
make -j3
make install
popd >/dev/null

cp "$build_root/ffmpeg-install/bin/ffmpeg" "$stage_root/tools/ffmpeg/bin/ffmpeg"
chmod 755 "$stage_root/tools/ffmpeg/bin/ffmpeg"
test "$(lipo -archs "$stage_root/tools/ffmpeg/bin/ffmpeg")" = arm64
ffmpeg_config="$("$stage_root/tools/ffmpeg/bin/ffmpeg" -buildconf 2>&1)"
if grep -E -- '--enable-(gpl|nonfree)' <<<"$ffmpeg_config"; then
  echo 'FFmpeg GPL/nonfree configuration is not permitted' >&2
  exit 1
fi
mkdir -p "$stage_root/licenses/FFmpeg-8.1.2" "$stage_root/licenses/python-packages"
cp "$build_root/ffmpeg-$ffmpeg_version/COPYING.LGPLv2.1" "$stage_root/licenses/FFmpeg-8.1.2/"
cp -R LICENSES/. "$stage_root/licenses/"

STAGE_LICENSES="$stage_root/licenses/python-packages" python - <<'PY'
import importlib.metadata as metadata
import os
import re
import shutil
from pathlib import Path

root = Path(os.environ["STAGE_LICENSES"])
for distribution in metadata.distributions():
    name = re.sub(r"[^A-Za-z0-9._-]", "_", distribution.metadata.get("Name", "unknown"))
    version = re.sub(r"[^A-Za-z0-9._-]", "_", distribution.version)
    for item in distribution.files or ():
        path = Path(item)
        if not ("license" in str(path).lower() or path.name.upper().startswith(("COPYING", "NOTICE"))):
            continue
        source = Path(distribution.locate_file(item))
        if source.is_file() and source.stat().st_size < 5_000_000:
            destination = root / f"{name}-{version}" / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
PY

python -m PyInstaller --clean --noconfirm packaging/transcriber9000_macos.spec
app="dist/Transcriber 9000.app"
test -d "$app"
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict --verbose=2 "$app"
codesign -dv --verbose=4 "$app" 2>&1 | grep -q 'Signature=adhoc'

manifest="dist/build-manifest.txt"
{
  echo "Transcriber 9000 macOS arm64 CI build"
  echo "OS: $(sw_vers -productVersion)"
  echo "Architecture: $(uname -m)"
  echo "Python: $(python --version 2>&1)"
  echo "FFmpeg source: https://ffmpeg.org/releases/ffmpeg-$ffmpeg_version.tar.xz"
  echo "FFmpeg source SHA-256: $actual_sha"
  echo "FFmpeg executable SHA-256: $(shasum -a 256 "$stage_root/tools/ffmpeg/bin/ffmpeg" | awk '{print $1}')"
  echo 'FFmpeg configuration:'
  printf '%s\n' "$ffmpeg_config"
  echo 'FFmpeg linked libraries:'
  otool -L "$stage_root/tools/ffmpeg/bin/ffmpeg"
  echo 'Installed Python packages:'
  python -m pip freeze
} > "$manifest"

echo "App KiB: $(du -sk "$app" | awk '{print $1}')" | tee -a "$manifest"
echo "App executable: $(file -b "$app/Contents/MacOS/Transcriber 9000")" | tee -a "$manifest"
