#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PATH="$SCRIPT_DIR/../.venv/bin:$PATH"

AUDIO_DEVICE="${AUDIO_DEVICE:-plughw:CARD=UACDemoV10,DEV=0}"
MIC_DEVICE="${MIC_DEVICE:-plughw:CARD=Device,DEV=0}"
VOICES_DIR="${VOICES_DIR:-$SCRIPT_DIR/../voices}"
QUESTION="${1:-What is your phone number?}"
RECORDING="${RECORDING:-$SCRIPT_DIR/numerical_answer.wav}"
TRANSCRIPT="${TRANSCRIPT:-${RECORDING%.wav}.txt}"

echo "$QUESTION"
python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --length-scale 1.2 \
  --volume 0.8 \
  --output-raw \
  -- "$QUESTION Please answer with a number now." \
  | aplay -D "$AUDIO_DEVICE" -r 22050 -f S16_LE -t raw -

echo "Recording for up to 7 seconds..."
set +e
timeout --signal=INT 7s arecord \
  -D "$MIC_DEVICE" -f S16_LE -r 16000 -c 1 "$RECORDING"
record_status=$?
set -e

if [[ $record_status -ne 0 && $record_status -ne 124 && $record_status -ne 130 ]]; then
  echo "Recording failed with status $record_status." >&2
  exit "$record_status"
fi

echo "Transcribing with base.en..."
transcription_output=$(python3 "$SCRIPT_DIR/transcribe.py" "$RECORDING" --model base.en)
printf '%s\n' "$transcription_output" | tee "$TRANSCRIPT"

user_response=$(printf '%s\n' "$transcription_output" | awk 'NF { print; exit }')
if [[ -z "$user_response" ]]; then
  echo "No spoken answer was detected." >&2
  exit 1
fi

confirmation="Did I hear it right? you said $user_response"
python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --length-scale 1.2 \
  --volume 0.8 \
  --output-raw \
  -- "$confirmation" \
  | aplay -D "$AUDIO_DEVICE" -r 22050 -f S16_LE -t raw -

echo "Recording saved to: $RECORDING"
echo "Transcript saved to: $TRANSCRIPT"