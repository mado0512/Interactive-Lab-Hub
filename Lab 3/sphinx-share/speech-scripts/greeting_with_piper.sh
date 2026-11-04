#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PATH="$SCRIPT_DIR/../.venv/bin:$PATH"
VOICES_DIR="${VOICES_DIR:-$SCRIPT_DIR/../voices}"
AUDIO_DEVICE="${AUDIO_DEVICE:-plughw:CARD=UACDemoV10,DEV=0}"

python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --length-scale 1.4 \
  --volume 0.6 \
  --output-raw \
  -- "Greetings! Shifeng!" \
  | aplay -D "$AUDIO_DEVICE" -r 22050 -f S16_LE -t raw -