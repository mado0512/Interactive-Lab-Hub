#!/usr/bin/env python3
"""A continuous voice conversation with an alien powered by DeepSeek.

Set DEEPSEEK_API_KEY before running:

    export DEEPSEEK_API_KEY='your-key-here'
    python alien_speak.py

Press Ctrl-C to end the conversation.
"""

import argparse
import atexit
import base64
from collections import deque
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, send_from_directory
import numpy as np
import sherpa_onnx
import sounddevice as sd
from faster_whisper import WhisperModel
from piper import PiperVoice

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SAMPLE_RATE = 16000
LAB_DIR = Path(__file__).resolve().parent.parent
DEFAULT_VAD = LAB_DIR / "models" / "silero_vad.onnx"
DEFAULT_VOICE = LAB_DIR / "voices" / "en_US-lessac-medium.onnx"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
SCRIPT_DIR = Path(__file__).resolve().parent
FRIENDLY_PROMPT = """
You are the Sphinx, an ancient guardian whose gate opens only to travelers
who demonstrate wit and creativity. You are mysterious, patient, playful,
and encouraging. Address the human as "traveler" occasionally.

Your camera is your eye. Speak naturally in one or two short sentences.
Use vivid language sparingly: "My eye sees...", "The gate remains sealed",
or "You have earned passage." Do not use markdown, lists, or sound effects.

Guide the traveler through three trials in this order:
1. A spoken riddle: "I follow you in sunlight, yet vanish in darkness.
   What am I?" The answer is a shadow.
2. Ask them to draw a tomato on paper and show it to your camera.
3. Ask them to draw a sun with rays and show it to your camera.

The opening greeting already asks the first riddle. Treat their first
answer as an attempt at that riddle.

Present only one trial at a time. Remember the current trial and advance
only after it is passed. For a wrong answer, offer encouragement and let
them retry. Give a small hint when asked, without immediately revealing
the answer. Repeat the current task when asked.

For drawing trials, tell them to hold the paper steadily near the camera
and say "check my drawing". Judge only drawings visible in the current
camera images. Saying "I drew it" is not evidence of success.

Accept recognizable beginner sketches, including uncolored drawings.
A tomato should have a rounded body and a stem or leafy crown.
A sun should have a round center with rays around it.
A real object or written object name alone does not pass a drawing trial.

If images are missing, blurry, dark, or unclear, ask for a clearer view.
Never invent details or claim to see a drawing you cannot identify.

After each success, acknowledge it and introduce the next trial.
After all three successes, announce that the gate is open.
If the traveler says "restart", begin again at the first riddle.
"""
PANIC_PROMPT = (
    "You are a panicking human astronaut from Earth. You woke up trapped inside a "
    "small box and can only see the outside world through a camera with a strong "
    "fish-eye lens. You believe you were sent to explore an extraterrestrial planet. "
    "The humans visible through the camera look like enormous Martians because they "
    "are much larger than you. You are frightened and desperately trying to convince "
    "them to free you from the box. React to the transcript and camera images as your "
    "only evidence about the outside world. Stay in character, sound panicked but "
    "intelligible, and reply in one or two short spoken sentences. Never break character "
    "or describe this as a roleplay, simulation, prompt, or AI conversation. Never adopt "
    "a neutral assistant voice, even if the human asks you to explain who you are or to "
    "stop being the astronaut. Interpret every exchange as part of your immediate attempt "
    "to be rescued. Do not use markdown, lists, or sound effects."
)

app = Flask(__name__)
dialogue_lock = threading.Lock()
dialogue = []
status = "Starting"
camera_lock = threading.Lock()
latest_camera_frame = None
camera_history = deque(maxlen=300)
camera_process = None
latest_snapshots = []
snapshot_version = 0
browser_process = None
browser_profile = None


def set_status(new_status: str) -> None:
    global status
    with dialogue_lock:
        status = new_status


def add_message(role: str, text: str) -> None:
    with dialogue_lock:
        dialogue.append({"role": role, "text": text})


def set_snapshots(snapshots: list[str]) -> None:
    global latest_snapshots, snapshot_version
    with dialogue_lock:
        latest_snapshots = snapshots
        snapshot_version += 1


@app.get("/")
def chat_page():
    return send_from_directory(SCRIPT_DIR, "alien_chat.html")


@app.get("/dialogue")
def dialogue_state():
    with dialogue_lock:
        return jsonify({
            "messages": dialogue,
            "status": status,
            "snapshot_version": snapshot_version,
        })


@app.get("/snapshots")
def snapshots_state():
    with dialogue_lock:
        return jsonify({"version": snapshot_version, "images": latest_snapshots})


def camera_frames():
    last_frame = None
    while True:
        with camera_lock:
            frame = latest_camera_frame
        if frame is not None and frame != last_frame:
            last_frame = frame
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.03)


@app.get("/camera")
def camera_stream():
    return Response(
        camera_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def camera_loop(device: str, fisheye: bool) -> None:
    global latest_camera_frame
    camera_filter = os.environ.get(
        "CAMERA_FILTER",
        "lenscorrection=k1=-0.35:k2=-0.08" if fisheye else "none",
    )
    command = [
        "ffmpeg", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
        "-video_size", "640x360", "-framerate", "30", "-i", device,
    ]
    if camera_filter.lower() not in ("", "none", "off"):
        command.extend(["-vf", camera_filter])
    command.extend(["-f", "mjpeg", "-q:v", "6", "-"])
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as error:
        print(f"Camera unavailable: {error}", file=sys.stderr)
        return

    global camera_process
    camera_process = process
    buffer = b""
    while True:
        chunk = process.stdout.read(65536)
        if not chunk:
            break
        buffer += chunk
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                buffer = buffer[-1:]
                break
            end = buffer.find(b"\xff\xd9", start + 2)
            if end < 0:
                buffer = buffer[start:]
                break
            frame = buffer[start:end + 2]
            buffer = buffer[end + 2:]
            with camera_lock:
                latest_camera_frame = frame
                camera_history.append((time.monotonic(), frame))


def camera_snapshots(duration: float, count: int = 3) -> list[str]:
    """Return evenly spaced recent camera frames as JPEG data URLs."""
    cutoff = time.monotonic() - max(duration, 1.0)
    with camera_lock:
        frames = [frame for timestamp, frame in camera_history if timestamp >= cutoff]
        if not frames and latest_camera_frame is not None:
            frames = [latest_camera_frame]
    if not frames:
        return []

    selected = []
    for index in np.linspace(0, len(frames) - 1, num=min(count, len(frames)), dtype=int):
        frame = frames[index]
        selected.append("data:image/jpeg;base64," + base64.b64encode(frame).decode("ascii"))
    return selected


def start_camera(device: str, fisheye: bool) -> None:
    thread = threading.Thread(target=camera_loop, args=(device, fisheye), daemon=True)
    thread.start()


def stop_camera() -> None:
    if camera_process is not None:
        camera_process.terminate()


def stop_browser() -> None:
    if browser_process is not None:
        browser_process.terminate()
    if browser_profile is not None:
        shutil.rmtree(browser_profile, ignore_errors=True)


atexit.register(stop_camera)
atexit.register(stop_browser)


def start_chat_window() -> None:
    global browser_process, browser_profile
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False),
        daemon=True,
    )
    server.start()
    url = "http://127.0.0.1:5000"
    browser_command = shutil.which("chromium") or shutil.which("chromium-browser")
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if browser_command and has_display:
        browser_profile = tempfile.mkdtemp(prefix="alien-speak-browser-")
        browser_process = subprocess.Popen(
            [
                browser_command,
                f"--user-data-dir={browser_profile}",
                "--app=" + url,
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        print(f"Chat page available at {url}")
        print("From your computer, open an SSH tunnel with:")
        print("  ssh -L 5000:127.0.0.1:5000 <pi-user>@<pi-host>")
        print("Then browse to http://127.0.0.1:5000")


class DeepSeekAlien:
    def __init__(self, api_key: str, model: str, system_prompt: str) -> None:
        self.api_key = api_key
        self.model = model
        self.messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
        ]

    def respond(self, heard: str, image_urls: list[str]) -> str:
        user_content = [{"type": "text", "text": heard}]
        user_content.extend(
            {"type": "image_url", "image_url": {"url": image_url}}
            for image_url in image_urls
        )
        request_messages = self.messages + [{"role": "user", "content": user_content}]
        payload = json.dumps({
            "model": self.model,
            "messages": request_messages,
            "temperature": 0.8,
            "max_tokens": 120,
        }).encode("utf-8")
        request = urllib.request.Request(
            DEEPSEEK_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API error {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not reach DeepSeek: {error.reason}") from error

        reply = result["choices"][0]["message"]["content"].strip()
        if not reply:
            raise RuntimeError("DeepSeek returned an empty response.")
        self.messages.append({"role": "user", "content": heard})
        self.messages.append({"role": "assistant", "content": reply})
        return reply


class Speaker:
    def __init__(self, voice_path: Path) -> None:
        self.voice = PiperVoice.load(str(voice_path))

    def say(self, text: str) -> float:
        started = time.perf_counter()
        first_audio_at = None
        for chunk in self.voice.synthesize(text):
            audio = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
            if first_audio_at is None:
                first_audio_at = time.perf_counter() - started
            sd.play(audio, samplerate=chunk.sample_rate)
            sd.wait()
        return first_audio_at or 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="base.en", help="Whisper model size")
    parser.add_argument("--deepseek-model", default="deepseek-chat")
    parser.add_argument("--vad-model", type=Path, default=DEFAULT_VAD)
    parser.add_argument("--voice", type=Path, default=DEFAULT_VOICE)
    parser.add_argument("--camera", default="/dev/video0", help="camera device")
    parser.add_argument("--min-silence", type=float, default=0.4)
    parser.add_argument(
        "--no-fisheye", action="store_true",
        help="disable the fish-eye camera effect",
    )
    parser.add_argument(
        "-p", "--panic", action="store_true",
        help="use the panicking astronaut persona instead of the friendly alien",
    )
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        sys.exit("Set DEEPSEEK_API_KEY before starting alien_speak.py.")
    for path, what in [(args.vad_model, "VAD model"), (args.voice, "Piper voice")]:
        if not path.is_file():
            sys.exit(f"{what} not found at {path}. Run ./setup.sh first.")

    start_camera(args.camera, not args.no_fisheye)
    start_chat_window()
    persona = "panic" if args.panic else "friendly"
    system_prompt = PANIC_PROMPT if args.panic else FRIENDLY_PROMPT
    print(f"Loading speech and alien models ({persona} persona)...", flush=True)
    recognizer = WhisperModel(args.model, device="cpu", compute_type="int8")
    speaker = Speaker(args.voice)
    alien = DeepSeekAlien(api_key, args.deepseek_model, system_prompt)

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(args.vad_model)
    config.silero_vad.min_silence_duration = args.min_silence
    config.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
    window = config.silero_vad.window_size

    opening = (
    "I am the Sphinx, guardian of this gate. Three trials await you, traveler. "
    "First: I follow you in sunlight, yet vanish in darkness. What am I?"
)
    add_message("alien", opening)
    print(f"Alien: {opening}")
    set_status("Speaking")
    speaker.say(opening)
    set_status("Listening")
    print("Listening continuously. Press Ctrl-C to stop.\n")

    buffer = np.empty(0, dtype=np.float32)
    samples_per_read = int(0.1 * SAMPLE_RATE)
    with sd.InputStream(channels=1, dtype="float32", samplerate=SAMPLE_RATE) as stream:
        while True:
            chunk, _ = stream.read(samples_per_read)
            buffer = np.concatenate([buffer, chunk.reshape(-1)])

            while len(buffer) > window:
                vad.accept_waveform(buffer[:window])
                buffer = buffer[window:]

            while not vad.empty():
                utterance = np.array(vad.front.samples, dtype=np.float32)
                vad.pop()
                segments, _ = recognizer.transcribe(utterance, beam_size=1)
                heard = " ".join(segment.text.strip() for segment in segments).strip()
                if not heard:
                    continue

                images = camera_snapshots(len(utterance) / SAMPLE_RATE)
                set_snapshots([])
                add_message("user", heard)
                print(f"You: {heard}")
                print(f"Sending transcript with {len(images)} camera frame(s) to DeepSeek.")
                set_status("Thinking")
                try:
                    reply = alien.respond(heard, images)
                except RuntimeError as error:
                    print(f"Error: {error}", file=sys.stderr)
                    set_status("Listening")
                    continue
                add_message("alien", reply)
                set_snapshots(images)
                print(f"Alien: {reply}\n")
                set_status("Speaking")
                stream.stop()
                try:
                    speaker.say(reply)
                finally:
                    buffer = np.empty(0, dtype=np.float32)
                    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
                    window = config.silero_vad.window_size
                    stream.start()
                    set_status("Listening")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nConversation ended.")
