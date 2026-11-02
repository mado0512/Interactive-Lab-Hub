#!/usr/bin/env python3
"""
Part J: the snore recorder. Listen through the USB microphone and keep a WAV file
whenever the room gets loud enough to be snoring.

    python snore_monitor.py                    # listen until Ctrl-C
    python snore_monitor.py --list             # show the input devices and mics, then quit
    python snore_monitor.py --calibrate 10     # judge "loud" from a 10 s read of the room
    python snore_monitor.py --threshold -25    # a fixed, louder trigger
    python snore_monitor.py --duration 60 -v   # a one-minute test run with a live meter
    python snore_monitor.py --source alc        # pick a mic by name fragment

Which microphone
----------------
By default this opens the PulseAudio (PipeWire) device and asks it for a USB capture
source, so on a Pi with pipewire running you get the plugged-in USB mic without any
arguments. That matters: on this Pi, grabbing the USB mic straight from ALSA gave
6-20% dropped audio because PipeWire owns the device, while the Pulse path dropped
none. Use --source to choose the mic, --device <index|name> to bypass Pulse entirely
(e.g. --device hw:3,0 style indexes from --list), and note that --source only applies
to the Pulse device.

How "loud" is measured
----------------------
The microphone reports numbers, not decibels of sound pressure, so everything here is
in dBFS: 0 dBFS is the loudest the mic can report, and a quiet bedroom sits around
-45 dBFS. That number shifts with the mic's gain, so the useful trigger is always
relative to the room's own floor. Two ways to set it:

  --calibrate N   listen N seconds, then trigger at (median floor + --margin). Best default.
  --threshold X   trigger at a fixed X dBFS. Good once you know your room.

If you have a real reference (a phone SPL meter or a 94 dB calibrator), pass
--spl-offset: the gap between a known SPL and what this mic reads for it. Then
--threshold is read in dB SPL instead, and reports show both.

Each snore is written as a mono 16-bit WAV in snores/, plus one JSON line per file in
snore_log.jsonl. A trigger must clear the threshold for --min-trigger seconds before
recording starts, and recording continues until the room has been quiet for --hold
seconds, so one snore is one file instead of twenty. Audio from --preroll seconds
before the trigger is included, so the file starts at the sound, not after it.

For a night shift, run it detached, as in Lab 5's overnight.py:

    nohup python snore_monitor.py --calibrate 15 >> snore_console.log 2>&1 &

Running all night
-----------------
Eight hours is fine on this Pi: memory stays flat (about 60 MB), it burns under 2% CPU, and
a 48 kHz mono recording costs about 96 KB/s, so eight hours of non-stop sound is roughly
3 GB - check `df -h` before a long run.

Two things can still go wrong while you sleep, so both are handled rather than hoped away.
A stream that dies (PipeWire restarting, the USB mic re-enumerating) used to leave the
script running and silently recording nothing, so a watchdog reopens the stream after
--stall-timeout seconds with no audio at all; a quiet room is normal, a dead stream is not.
And because a WAV a second fills a card, recording pauses when free space drops below
--min-free-mb. Both events are written to the log, so the morning report can say so.

The panel
---------
On a terminal the script draws a small fixed panel: the level bar with the threshold
marked on it, the clip being written, the night's totals, and the last few events. Two
keys work at any time - `q` quits (a clip in progress is saved) and `m` saves a clip now,
from the last --preroll seconds when nothing is recording. When the output is redirected,
or with -v or -q, it falls back to plain lines so nohup logs stay readable; --no-tui
forces that.
"""
import argparse
import collections
import curses
import datetime
import json
import math
import os
import pathlib
import queue
import signal
import shutil
import subprocess
import sys
import time
import wave

import numpy as np
import sounddevice as sd

FULL_SCALE = 32768.0          # int16 samples run -32768..32767
SILENCE_DB = -120.0           # the floor we report instead of -inf
BLOCK_SECONDS = 0.1           # 100 ms per analysis window
LOW_BAND_HZ = 1000.0          # "snoring lives down here" for the optional band gate

stop = False                  # flipped by Ctrl-C / SIGTERM


def to_db(rms):
    """int16 RMS amplitude -> dBFS, floored so a dead-silent block is not -inf."""
    if rms <= 0:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * math.log10(rms / FULL_SCALE))


def db_bar(level, width=30, low=-70.0, high=-6.0, marker=None):
    """A crude ASCII level meter, plus a tick where the trigger sits.

    The window is -70..-6 dBFS rather than -120..0: that is where a room actually
    lives, and 64 dB across the bar means a cell is worth ~2 dB instead of ~4.
    """
    frac = (level - low) / (high - low)
    filled = int(round(min(1.0, max(0.0, frac)) * width))
    cells = ["#"] * filled + ["."] * (width - filled)
    if marker is not None:
        pos = int(round((marker - low) / (high - low) * (width - 1)))
        if 0 <= pos < width:
            cells[pos] = "|"
    return "[" + "".join(cells) + "]"


def meter_range(threshold):
    """Display window for the bar, keeping the threshold visible with room either side."""
    return min(-70.0, threshold - 10.0), max(-6.0, threshold + 10.0)


def shown_level(level, spl_offset):
    """dBFS, plus the SPL estimate when we have one."""
    if spl_offset is None:
        return f"{level:6.1f} dBFS"
    return f"{level:6.1f} dBFS / {level + spl_offset:5.1f} dB SPL"


def pulse_sources():
    """Capture sources known to PulseAudio/PipeWire, or [] when it is not running."""
    try:
        out = subprocess.run(["pactl", "list", "short", "sources"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    names = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and not parts[1].endswith(".monitor"):
            names.append(parts[1])
    return names


def list_devices():
    print("input devices:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"  {i}: {d['name']}  ({d['max_input_channels']} ch, "
                  f"{int(d['default_samplerate'])} Hz)")
    print("\npass the number, or any piece of the name, to --device")
    sources = pulse_sources()
    if sources:
        print("\npulse sources (pick one with --source):")
        for name in sources:
            print(f"  {name}")
    return 0


def pick_device(spec):
    """Resolve --device (index or name fragment), or choose a USB mic by default."""
    inputs = [(i, d) for i, d in enumerate(sd.query_devices())
              if d["max_input_channels"] > 0]
    if not inputs:
        raise SystemExit("no input devices found; is the microphone plugged in?")

    if spec is not None:
        if spec.lstrip("-").isdigit():
            idx = int(spec)
            match = [kv for kv in inputs if kv[0] == idx]
            if not match:
                raise SystemExit(f"device {idx} is not an input device; try --list")
            return match[0][0]
        hits = [kv for kv in inputs if spec.lower() in kv[1]["name"].lower()]
        if not hits:
            raise SystemExit(f"no input device matches {spec!r}; try --list")
        if len(hits) > 1:
            names = ", ".join(f"{i}: {d['name']}" for i, d in hits)
            raise SystemExit(f"{spec!r} is ambiguous ({names}); pass a device index")
        return hits[0][0]

    # Prefer the PulseAudio device: it shares the USB mic properly with the rest of
    # the system and does not drop audio the way direct hw access can on a Pi.
    def score(d):
        name = d["name"].lower()
        s = 0
        if name.strip() == "pulse":
            s -= 100
        elif "pulse" in name:
            s -= 90
        elif name.strip() == "default":
            s -= 80
        if "pnp" in name or "mic" in name:
            s -= 20
        if "usb" in name:
            s -= 10
        if "web cam" in name or "webcam" in name or "camera" in name:
            s += 10
        return s

    return min(inputs, key=lambda kv: (score(kv[1]), kv[0]))[0]


def choose_source(spec):
    """Pick the Pulse capture source (the actual mic). None means "let Pulse decide"."""
    sources = pulse_sources()
    if spec is not None and spec.strip().lower() in ("", "default", "none"):
        return None

    if spec is None:                       # auto: a plugged-in USB mic if there is one
        def score(name):
            low = name.lower()
            s = 0
            if "pnp" in low or "mic" in low:
                s -= 20
            if "usb" in low:
                s -= 10
            if "web cam" in low or "webcam" in low:
                s += 10
            return s

        usb = [n for n in sources if "usb" in n.lower()]
        return sorted(usb, key=lambda n: (score(n), n))[0] if usb else None

    if spec in sources:
        return spec
    hits = [n for n in sources if spec.lower() in n.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        known = "\n  ".join(sources) if sources else "(pactl listed none)"
        raise SystemExit(f"no pulse source matches {spec!r}; known sources:\n  {known}")
    raise SystemExit("source %r is ambiguous: %s" % (spec, ", ".join(hits)))


def pick_rate(device, wanted):
    """Return the first sample rate this mic actually accepts."""
    seen, rates = set(), []
    for r in ([wanted] if wanted else []) + [48000, 44100, 32000, 22050, 16000, 8000]:
        if r and r not in seen:
            seen.add(r)
            rates.append(r)
    for r in rates:
        try:
            sd.check_input_settings(device=device, channels=1, samplerate=r,
                                    dtype="int16")
            return r
        except Exception:
            continue
    raise SystemExit(f"device {device} accepts none of {rates} Hz for mono capture")


def block_rms(block):
    return float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))


def low_band_ratio(block, rate):
    """Share of block energy below LOW_BAND_HZ (snoring and breathing are low)."""
    windowed = block.astype(np.float64) * np.hanning(len(block))
    power = np.abs(np.fft.rfft(windowed)) ** 2
    freqs = np.fft.rfftfreq(len(block), 1.0 / rate)
    total = power.sum()
    if total <= 0:
        return 0.0
    return float(power[freqs < LOW_BAND_HZ].sum() / total)


def measure_floor(device, rate, seconds, block):
    """Median level of the room while we listen, used by --calibrate."""
    levels = []
    with sd.InputStream(device=device, channels=1, samplerate=rate, dtype="int16",
                        blocksize=block, latency="high") as stream:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            data, _ = stream.read(block)
            levels.append(to_db(block_rms(data.reshape(-1))))
    if not levels:
        raise SystemExit("could not measure the room")
    return float(np.median(levels))


class Clip:
    """A WAV file written as the sound arrives, so a crash still leaves audio."""

    def __init__(self, path, rate):
        self.path = path
        self.rate = rate
        self.frames = 0
        self.peak_db = SILENCE_DB
        self.level_sum = 0.0
        self.levels = 0
        self.wav = wave.open(str(path), "wb")
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)
        self.wav.setframerate(rate)

    def write(self, block):
        self.wav.writeframes(np.ascontiguousarray(block).tobytes())
        self.frames += block.size
        level = to_db(block_rms(block))
        self.peak_db = max(self.peak_db, level)
        self.level_sum += level
        self.levels += 1

    @property
    def seconds(self):
        return self.frames / self.rate

    @property
    def mean_db(self):
        return self.level_sum / self.levels if self.levels else SILENCE_DB

    def close(self):
        self.wav.close()


class SnoreMachine:
    """The audio decision logic: blocks in, clips out.

    This is the single place that decides what counts as a snore - loud enough, for
    long enough, with the preroll kept, one clip per event - so every tool that
    shares it (snore_monitor, night_watch) cannot drift apart. No UI, no logging, no
    signals: it returns events and lets the caller narrate them.
    """

    def __init__(self, rate, outdir, threshold, preroll=1.5, min_trigger=0.3,
                 hold=3.0, max_len=300.0, min_save=0.5, low_band=None,
                 min_free_mb=500.0, free_mb=None):
        self.rate = rate
        self.outdir = pathlib.Path(outdir)
        self.threshold = threshold
        self.min_trigger = min_trigger
        self.hold = hold
        self.max_len = max_len
        self.min_save = min_save
        self.low_band = low_band
        self.min_free_mb = min_free_mb
        self.free_mb = free_mb or (lambda p: shutil.disk_usage(p).free / 1e6)
        # A trigger that needs 3 s of sound must keep 3 s of preroll to include its start.
        self.keep_seconds = max(preroll, min_trigger + 0.2)
        self._block = None
        self.preroll = collections.deque(maxlen=1)
        self.clip = None
        self.above = self.below = 0.0
        self.level = SILENCE_DB

    def _open(self):
        stamp = datetime.datetime.now()
        clip = Clip(self.outdir / f"snore_{stamp:%Y%m%d-%H%M%S}.wav", self.rate)
        clip.started = time.time()
        return clip

    def feed(self, chunk):
        """Take one block, return (level, events).

        Events are ('start', clip), ('close', clip), ('short', clip) or
        ('disk', free_mb). 'close' means a finished clip worth keeping; 'short' means
        it was already deleted.
        """
        if chunk.size != self._block:            # keep the preroll window in seconds
            self._block = chunk.size
            self.preroll = collections.deque(
                self.preroll,
                maxlen=max(1, int(math.ceil(self.keep_seconds * self.rate / chunk.size))))

        level = self.level = to_db(block_rms(chunk))
        self.preroll.append(chunk)
        loud = level >= self.threshold
        if loud and self.low_band is not None:
            loud = low_band_ratio(chunk, self.rate) >= self.low_band
        events = []

        if self.clip is None:
            if not loud:
                self.above = 0.0
                return level, events
            self.above += chunk.size / self.rate
            if self.above < self.min_trigger:     # a bang is not a snore
                return level, events
            free = self.free_mb(self.outdir)      # a WAV a second fills a card
            if free < self.min_free_mb:
                self.above = 0.0
                events.append(("disk", free))
                return level, events
            self.clip = self._open()
            for pre in self.preroll:              # include the sound's beginning
                self.clip.write(pre)
            self.below = 0.0
            events.append(("start", self.clip))
            return level, events

        self.clip.write(chunk)
        if loud:
            self.below = 0.0
        else:
            self.below += chunk.size / self.rate
        if self.below >= self.hold or self.clip.seconds >= self.max_len:
            events.append(self._close())
        return level, events

    def _close(self):
        clip, self.clip = self.clip, None
        clip.close()
        self.above = self.below = 0.0
        if clip.seconds >= self.min_save:
            return ("close", clip)
        clip.path.unlink(missing_ok=True)
        return ("short", clip)

    def save_now(self):
        """End the current clip, or bag the preroll when nothing was recording."""
        if self.clip is None:
            if not self.preroll:
                return None
            clip = self._open()
            for pre in self.preroll:
                clip.write(pre)
        else:
            clip = self.clip
        clip.close()
        self.clip = None
        self.above = self.below = 0.0
        return clip


class PlainUI:
    """Line-at-a-time output: works in a terminal and in a nohup log alike."""

    is_tui = False

    def __init__(self, args, threshold, spl_offset):
        self.args = args
        self.spl_offset = spl_offset
        self.threshold = threshold
        self.low, self.high = meter_range(threshold)
        self.meter_tty = sys.stdout.isatty() and not args.quiet
        self.show_meter = args.verbose or self.meter_tty
        self.last_draw = 0.0

    def event(self, msg):
        """Print an event line without it landing on top of the live meter.

        The meter redraws itself with \\r and never ends its line, so a bare print()
        would append to it; clear the line first, then start a fresh one.
        """
        print(("\r\033[K" if self.meter_tty else "") + msg, flush=True)

    def update(self, level, clip_secs, peak_db, saved, restarts, rec_secs, now):
        if not self.show_meter or now - self.last_draw < 0.5:
            return
        self.last_draw = now
        state = "REC " if clip_secs is not None else "    "
        line = (f"{datetime.datetime.now():%H:%M:%S} {state}"
                f"{db_bar(level, low=self.low, high=self.high, marker=self.threshold)} "
                f"{shown_level(level, self.spl_offset)}")
        if self.meter_tty and not self.args.verbose:
            print("\r" + line, end="", flush=True)
        else:
            print(line, flush=True)

    def poll_keys(self):
        return ()

    def close(self):
        if self.meter_tty and self.show_meter:
            print()


class CursesUI:
    """A fixed panel: level against the threshold, the clip being written, the night's
    totals, and the last few events. Keys: q quits, m saves a clip now."""

    is_tui = True

    def __init__(self, threshold, spl_offset, device_name, source_name):
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        self.stdscr.nodelay(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.colour = curses.has_colors()
        if self.colour:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
        self.threshold = threshold
        self.spl_offset = spl_offset
        self.low, self.high = meter_range(threshold)
        self.device_name = device_name
        self.source_name = source_name
        self.events = collections.deque(maxlen=8)
        self.last_draw = 0.0
        self.closed = False

    def _put(self, y, x, text, attr=0):
        """addstr that survives a small window and never leaves stale characters.

        Lines are padded to the full width: new events shift the list down one row, so
        a shorter line replacing a longer one would otherwise leave the old tail on
        screen. Padding makes the panel independent of how curses diffs the screen.
        """
        height, width = self.stdscr.getmaxyx()
        if y < 0 or y >= height or x < 0 or x >= width or not text:
            return
        room = max(0, width - x - 1)
        try:
            self.stdscr.addstr(y, x, text[:room].ljust(room), attr)
        except curses.error:
            pass

    def event(self, msg):
        self.events.appendleft(f"{datetime.datetime.now():%H:%M:%S} {msg}")

    def update(self, level, clip_secs, peak_db, saved, restarts, rec_secs, now):
        recording = clip_secs is not None
        if now - self.last_draw < (0.1 if recording else 0.25):
            return
        self.last_draw = now
        height, width = self.stdscr.getmaxyx()
        bar_w = max(12, min(44, width - 42))

        self.stdscr.erase()
        self._put(0, 0, " snore monitor ".ljust(width - 1), curses.A_REVERSE)
        self._put(1, 1, f"mic  {self.device_name}")
        self._put(2, 1, f"src  {self.source_name}")

        bar = db_bar(level, width=bar_w, low=self.low, high=self.high,
                     marker=self.threshold)
        attr = curses.color_pair(1) if (self.colour and recording) else 0
        self._put(4, 1, "level")
        self._put(4, 7, bar, attr)
        self._put(4, 9 + bar_w, shown_level(level, self.spl_offset))

        trigger_attr = curses.color_pair(3) if self.colour else 0
        self._put(5, 7, f"trigger {shown_level(self.threshold, self.spl_offset)}   "
                        f"peak {shown_level(peak_db, self.spl_offset)}", trigger_attr)

        state = f"REC  {clip_secs:6.1f} s" if recording else "idle, listening"
        self._put(6, 1, "state")
        self._put(6, 7, state, curses.color_pair(2) if (self.colour and recording) else 0)

        self._put(7, 1, "night")
        self._put(7, 7, f"{saved} file(s)  ·  {rec_secs / 60:5.1f} min recorded  ·  "
                        f"{restarts} restart(s)")

        self._put(8, 0, "-" * (width - 1))
        self._put(9, 1, "events", curses.A_BOLD)
        for i, line in enumerate(list(self.events)[:max(0, height - 11)]):
            self._put(10 + i, 1, line)

        self._put(height - 1, 0, " q quit   m save now ".ljust(width - 1), curses.A_REVERSE)
        self.stdscr.refresh()

    def poll_keys(self):
        keys = []
        while True:
            try:
                ch = self.stdscr.getch()
            except curses.error:
                break
            if ch == -1:
                break
            if ch in (ord("q"), ord("Q"), 3):
                keys.append("quit")
            elif ch in (ord("m"), ord("M")):
                keys.append("save")
        return keys

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.stdscr.keypad(False)
            curses.nocbreak()
            curses.echo()
            curses.curs_set(1)
        except Exception:
            pass
        try:
            curses.endwin()
        except Exception:
            pass


def main():
    global stop
    parser = argparse.ArgumentParser(
        description="Record a WAV whenever the microphone hears something loud enough.")
    parser.add_argument("--device", help="input device index or name fragment (see --list)")
    parser.add_argument("--source", help="Pulse capture source, i.e. which mic; a name "
                                         "fragment works too (default: a USB mic)")
    parser.add_argument("--list", action="store_true", help="list input devices and mics, then exit")
    parser.add_argument("--threshold", type=float, default=-32.0,
                        help="trigger level in dBFS, or dB SPL with --spl-offset "
                             "(default -32)")
    parser.add_argument("--calibrate", type=float, metavar="SECONDS",
                        help="set the trigger from the room: median floor + --margin")
    parser.add_argument("--margin", type=float, default=15.0,
                        help="how far above the room floor counts as loud, for "
                             "--calibrate (default 15 dB)")
    parser.add_argument("--spl-offset", type=float,
                        help="dB SPL minus this mic's dBFS reading, to work in real SPL")
    parser.add_argument("--rate", type=int, help="sample rate (default: whatever the mic likes)")
    parser.add_argument("--preroll", type=float, default=1.5,
                        help="seconds of audio kept before the trigger (default 1.5)")
    parser.add_argument("--min-trigger", type=float, default=0.3,
                        help="seconds above the threshold before recording starts "
                             "(default 0.3)")
    parser.add_argument("--hold", type=float, default=3.0,
                        help="seconds of quiet that end a recording (default 3)")
    parser.add_argument("--max-len", type=float, default=300.0,
                        help="longest single file, in seconds (default 300)")
    parser.add_argument("--stall-timeout", type=float, default=15.0,
                        help="reopen the stream after this many seconds with no audio "
                             "at all (default 15)")
    parser.add_argument("--min-free-mb", type=float, default=500.0,
                        help="pause recording when the disk has less than this free "
                             "(default 500 MB)")
    parser.add_argument("--min-save", type=float, default=0.5,
                        help="discard files shorter than this, e.g. a single cough "
                             "(default 0.5)")
    parser.add_argument("--low-band", type=float, metavar="RATIO",
                        help="only trigger if this share of the energy is below 1 kHz, "
                             "e.g. 0.6, to ignore clanks and alarms")
    parser.add_argument("--dir", default="snores", help="where WAV files go (default snores/)")
    parser.add_argument("--log", default="snore_log.jsonl",
                        help="append one JSON line per saved file (default snore_log.jsonl)")
    parser.add_argument("--duration", type=float, help="stop after this many seconds")
    parser.add_argument("-v", "--verbose", action="store_true", help="print a live level meter")
    parser.add_argument("-q", "--quiet", action="store_true", help="no level meter")
    parser.add_argument("--no-tui", action="store_true",
                        help="plain lines even in a terminal (useful for recording a session)")
    args = parser.parse_args()

    if args.list:
        return list_devices()

    device = pick_device(args.device)
    info = sd.query_devices(device)
    rate = pick_rate(device, args.rate)
    block = max(1, int(round(rate * BLOCK_SECONDS)))

    print(f"device {device}: {info['name']}", flush=True)
    print(f"capturing mono int16 at {rate} Hz, {block / rate * 1000:.0f} ms blocks", flush=True)

    source = None
    if "pulse" in info["name"].lower() or info["name"].strip() == "default":
        source = choose_source(args.source)
        if source:
            os.environ["PULSE_SOURCE"] = source     # must precede the stream open
            print(f"pulse source: {source}", flush=True)
        else:
            print("pulse source: system default", flush=True)
    elif args.source:
        print("note: --source only applies to the pulse device; ignoring it", flush=True)

    if args.calibrate:
        print(f"listening to the room for {args.calibrate:g} s to set the trigger...",
              flush=True)
        floor = measure_floor(device, rate, args.calibrate, block)
        threshold = min(-6.0, floor + args.margin)
        print(f"room floor {floor:.1f} dBFS, trigger {threshold:.1f} dBFS "
              f"(floor + {args.margin:g} dB)", flush=True)
    else:
        threshold = args.threshold
        if args.spl_offset is not None:
            threshold -= args.spl_offset      # dB SPL -> dBFS for the comparison

    def shown(level):
        return shown_level(level, args.spl_offset)

    unit = "dB SPL" if args.spl_offset is not None else "dBFS"
    print(f"trigger: {threshold if args.spl_offset is None else threshold + args.spl_offset:g} "
          f"{unit}, sustained {args.min_trigger:g} s; quiet for {args.hold:g} s ends a file",
          flush=True)

    outdir = pathlib.Path(args.dir)
    outdir.mkdir(parents=True, exist_ok=True)
    logfile = open(args.log, "a")

    audio_q = queue.Queue(maxsize=int(rate / block * 30))   # 30 s of slack
    dropped = collections.Counter()

    def callback(indata, frames, time_info, status):
        if status:
            dropped[str(status)] += 1        # count overflows; never raise in here
        try:
            audio_q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            dropped["queue full"] += 1

    machine = SnoreMachine(rate, outdir, threshold, preroll=args.preroll,
                           min_trigger=args.min_trigger, hold=args.hold,
                           max_len=args.max_len, min_save=args.min_save,
                           low_band=args.low_band, min_free_mb=args.min_free_mb)
    saved = blips = 0
    loudest = SILENCE_DB
    # A full-screen panel needs a real terminal; redirected output, -v and -q stay
    # line-based so nohup logs and copy-paste sessions keep working.
    ui = None
    if sys.stdout.isatty() and not (args.no_tui or args.verbose or args.quiet):
        try:
            ui = CursesUI(threshold, args.spl_offset, info["name"],
                          source or "system default")
        except Exception as e:
            try:
                curses.endwin()
            except Exception:
                pass
            print(f"could not start the panel ({e}); using plain output", flush=True)
    if ui is None:
        ui = PlainUI(args, threshold, args.spl_offset)
    event = ui.event
    if ui.is_tui:            # plain mode already printed the banner above
        event(f"listening; files go to {outdir}/")
        event(f"trigger {shown(threshold)}, quiet {args.hold:g} s ends a clip")

    last_beat = time.monotonic()
    deadline = time.monotonic() + args.duration if args.duration else None
    rec_done = 0.0

    def on_signal(signum, frame):
        global stop
        stop = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    def save_event(c, manual=False):
        nonlocal saved, loudest
        entry = {
            "event": "snore",
            "start": datetime.datetime.fromtimestamp(c.started).isoformat(timespec="seconds"),
            "end": datetime.datetime.now().isoformat(timespec="seconds"),
            "dur": round(c.seconds, 2),
            "peak_dbfs": round(c.peak_db, 1),
            "mean_dbfs": round(c.mean_db, 1),
            "file": str(c.path),
        }
        if args.spl_offset is not None:
            entry["peak_spl"] = round(c.peak_db + args.spl_offset, 1)
        if manual:
            entry["manual"] = True
        logfile.write(json.dumps(entry) + "\n")
        logfile.flush()
        saved += 1
        loudest = max(loudest, c.peak_db)
        event(f"saved{' (manual)' if manual else ''} {c.path.name}  "
              f"{c.seconds:5.1f} s  peak {shown(c.peak_db)}")

    def open_stream():
        return sd.InputStream(device=device, channels=1, samplerate=rate,
                              dtype="int16", blocksize=block, latency="high",
                              callback=callback)

    def write_log(entry):
        logfile.write(json.dumps(entry) + "\n")
        logfile.flush()

    stream = None
    try:
        try:
            stream = open_stream()
            stream.start()
        except sd.PortAudioError as e:
            raise SystemExit(f"could not open device {device} ({info['name']}): {e}\n"
                             "another program may be holding the mic; try --device pulse "
                             "or --list to pick a free one")

        last_audio = time.monotonic()
        restarts = skipped_disk = 0
        while not stop:
            if deadline and time.monotonic() >= deadline:
                break
            try:
                chunk = audio_q.get(timeout=0.2)
                last_audio = time.monotonic()
            except queue.Empty:
                # A silent room still delivers blocks, so no audio at all means the
                # stream died (PipeWire restarted, the mic re-enumerated). Reopening
                # matters: otherwise the script runs all night and records nothing.
                if time.monotonic() - last_audio < args.stall_timeout:
                    continue
                stamp = datetime.datetime.now().isoformat(timespec="seconds")
                event(f"{stamp} no audio for {args.stall_timeout:g} s, reopening the stream")
                partial = machine.save_now()         # keep the part we did capture
                if partial is not None:
                    rec_done += partial.seconds
                    if partial.seconds >= args.min_save:
                        save_event(partial)
                    else:
                        partial.path.unlink(missing_ok=True)
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                while not audio_q.empty():           # drop stale blocks
                    try:
                        audio_q.get_nowait()
                    except queue.Empty:
                        break
                while not stop:
                    try:
                        stream = open_stream()
                        stream.start()
                        break
                    except Exception as e:
                        event(f"{datetime.datetime.now():%H:%M:%S} reopen failed ({e}), "
                              "retrying in 5 s")
                        time.sleep(5)
                restarts += 1
                write_log({"event": "restart", "t": stamp, "n": restarts})
                last_audio = time.monotonic()
                continue

            level, outcomes = machine.feed(chunk)
            for kind, payload in outcomes:
                if kind == "start":
                    event(f"loud {shown(level)} -> recording")
                elif kind == "close":
                    rec_done += payload.seconds
                    save_event(payload)
                elif kind == "short":
                    rec_done += payload.seconds
                    blips += 1
                elif kind == "disk":
                    skipped_disk += 1
                    if skipped_disk == 1 or skipped_disk % 300 == 0:
                        event(f"only {payload:.0f} MB free, not recording "
                              f"(--min-free-mb {args.min_free_mb:g})")
                        write_log({"event": "disk_full",
                                   "t": datetime.datetime.now().isoformat(timespec="seconds"),
                                   "free_mb": round(payload)})

            now = time.monotonic()
            loudest = max(loudest, level)
            live = machine.clip
            ui.update(level, live.seconds if live is not None else None, loudest, saved,
                      restarts, rec_done + (live.seconds if live is not None else 0.0), now)

            for action in ui.poll_keys():
                if action == "quit":
                    stop = True
                elif action == "save":
                    clip = machine.save_now()          # close now, or bag the preroll
                    if clip is not None:
                        rec_done += clip.seconds
                        if clip.seconds > 0:
                            save_event(clip, manual=True)
                        else:
                            clip.path.unlink(missing_ok=True)

            if not ui.is_tui and now - last_beat > 600 and clip is None:
                last_beat = now
                event(f"{datetime.datetime.now():%H:%M:%S} still listening, "
                      f"{saved} file(s) so far, {restarts} restart(s)")
    finally:
        clip = machine.save_now()                # Ctrl-C mid-snore: keep what we have
        if clip is not None:
            if clip.seconds >= args.min_save:
                save_event(clip)
            else:
                clip.path.unlink(missing_ok=True)
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        ui.close()
        logfile.close()

    print(f"stopped: {saved} file(s) saved, {blips} too short to keep", flush=True)
    if saved:
        print(f"loudest moment {shown(loudest)}", flush=True)
    for reason, n in dropped.items():
        print(f"warning: {reason} x{n} (audio may have gaps)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
