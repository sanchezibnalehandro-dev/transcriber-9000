#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
app="${1:-dist/Transcriber 9000.app}"
test -d "$app"
codesign --verify --deep --strict --verbose=2 "$app"
codesign -dv --verbose=4 "$app" 2>&1 | grep -q 'Signature=adhoc'
test "$(lipo -archs "$app/Contents/MacOS/Transcriber 9000")" = arm64

count=0
while IFS= read -r -d '' candidate; do
  if file -b "$candidate" | grep -q 'Mach-O'; then
    if ! lipo -archs "$candidate" | grep -Eq '(^| )arm64( |$)'; then
      echo "Missing arm64 slice: $candidate" >&2
      lipo -archs "$candidate" >&2
      exit 1
    fi
    count=$((count + 1))
  fi
done < <(find "$app" -type f -print0)
test "$count" -gt 0
echo "Mach-O files with arm64 slice: $count"

ffmpeg="$app/Contents/Frameworks/tools/ffmpeg/bin/ffmpeg"
if [ ! -x "$ffmpeg" ]; then
  ffmpeg="$app/Contents/Resources/tools/ffmpeg/bin/ffmpeg"
fi
test -x "$ffmpeg"
"$ffmpeg" -version | head -n 1
otool -L "$ffmpeg"
echo "App KiB: $(du -sk "$app" | awk '{print $1}')"
