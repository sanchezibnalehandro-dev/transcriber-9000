#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
app="${1:-dist/Transcriber 9000.app}"
worker="$app/Contents/MacOS/Transcriber 9000"
ffmpeg="$app/Contents/Frameworks/tools/ffmpeg/bin/ffmpeg"
if [ ! -x "$ffmpeg" ]; then
  ffmpeg="$app/Contents/Resources/tools/ffmpeg/bin/ffmpeg"
fi
test -x "$worker" && test -x "$ffmpeg"

export HOME="${RUNNER_TEMP:?}/transcriber-smoke-home"
data="$HOME/Library/Application Support/Transcriber 9000"
mkdir -p "$data/input" "$data/.cache/whisper"

"$worker" --worker transcription --env-check > "${RUNNER_TEMP}/transcriber-env-check.json"
python3 -m json.tool "${RUNNER_TEMP}/transcriber-env-check.json" >/dev/null
say -o "${RUNNER_TEMP}/transcriber-speech.aiff" 'This is a transcription smoke test one two three.'
"$ffmpeg" -hide_banner -loglevel error -y -i "${RUNNER_TEMP}/transcriber-speech.aiff" -ar 16000 -ac 1 "$data/input/smoke.wav"

model="$data/.cache/whisper/tiny.pt"
curl --fail --location --retry 3 --output "$model" \
  https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt
echo '65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9  '"$model" | shasum -a 256 -c -

"$worker" --worker transcription \
  --transcribe-once "$data/input/smoke.wav" \
  --language auto --quality fast --formats txt srt \
  --result-json "${RUNNER_TEMP}/transcriber-result.json" \
  --status-file "${RUNNER_TEMP}/transcriber-status.txt"

python3 - "$data/output/smoke.txt" "$data/output/smoke.srt" "${RUNNER_TEMP}/transcriber-result.json" <<'PY'
import json
import sys
from pathlib import Path

txt, srt, result = map(Path, sys.argv[1:])
assert txt.is_file() and txt.read_text(encoding="utf-8").strip(), "Whisper TXT is empty"
assert srt.is_file() and "-->" in srt.read_text(encoding="utf-8"), "Whisper SRT is empty"
assert json.loads(result.read_text(encoding="utf-8"))["success"] is True
print("REAL_WHISPER_TINY_SMOKE_OK")
print("TXT:", txt.read_text(encoding="utf-8").strip())
PY
