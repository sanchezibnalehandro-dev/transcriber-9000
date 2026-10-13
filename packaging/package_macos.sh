#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
app="dist/Transcriber 9000.app"
source_archive="${RUNNER_TEMP:?}/transcriber-macos-build/ffmpeg-8.1.2.tar.xz"
package_dir="dist/macOS-arm64"
zip_path="dist/Transcriber9000-macOS-arm64.zip"
test -d "$app" && test -f "$source_archive"
bash packaging/verify_macos.sh "$app"
app_digest="$(python3 packaging/app_tree_hash.py "$app")"
echo "App tree: $app_digest" | tee -a dist/build-manifest.txt
mkdir -p "$package_dir"
ditto "$app" "$package_dir/Transcriber 9000.app"
cp packaging/README_MACOS.md "$package_dir/README_MACOS.md"
cp packaging/MACOS_THIRD_PARTY_NOTICES.md "$package_dir/MACOS_THIRD_PARTY_NOTICES.md"
cp dist/build-manifest.txt "$package_dir/build-manifest.txt"
cp "$source_archive" "$package_dir/ffmpeg-8.1.2.tar.xz"

ditto -c -k --sequesterRsrc --keepParent "$package_dir" "$zip_path"
unzip -t "$zip_path" >/dev/null
zip_sha="$(shasum -a 256 "$zip_path" | awk '{print $1}')"
zip_bytes="$(stat -f %z "$zip_path")"
echo "ZIP bytes: $zip_bytes"
echo "ZIP SHA-256: $zip_sha"
printf '%s  %s\n' "$zip_sha" "$(basename "$zip_path")" > dist/Transcriber9000-macOS-arm64.zip.sha256

unpacked="${RUNNER_TEMP}/transcriber-unpacked"
mkdir -p "$unpacked"
ditto -x -k "$zip_path" "$unpacked"
test -f "$unpacked/macOS-arm64/ffmpeg-8.1.2.tar.xz"
test "$(shasum -a 256 "$unpacked/macOS-arm64/ffmpeg-8.1.2.tar.xz" | awk '{print $1}')" = 464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c
bash packaging/verify_macos.sh "$unpacked/macOS-arm64/Transcriber 9000.app"
test "$app_digest" = "$(python3 packaging/app_tree_hash.py "$unpacked/macOS-arm64/Transcriber 9000.app")"
"$unpacked/macOS-arm64/Transcriber 9000.app/Contents/MacOS/Transcriber 9000" --worker transcription --env-check > "${RUNNER_TEMP}/transcriber-unpacked-env.json"
python3 -m json.tool "${RUNNER_TEMP}/transcriber-unpacked-env.json" >/dev/null
echo 'UNPACKED_APP_VERIFY_OK'
