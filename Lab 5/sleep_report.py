#!/usr/bin/env python3
"""
Part I, the morning reveal: read night_log.jsonl, turn it into percentages and a sleep
score, print a templated report, put four lines on the Mini PiTFT, and have the local Qwen
say a short morning note through the speaker (3-4 plain sentences, grounded in the log).

    python3 sleep_report.py                          # newest logs/*/night_log.jsonl
    python3 sleep_report.py --log logs/2026-10-29_2245/night_log.jsonl
    python3 sleep_report.py --explain                # show how the score was computed
    python3 sleep_report.py --json                   # stats as JSON, for other tools
    python3 sleep_report.py --no-display --image /tmp/panel.png   # just the rendered panel
    python3 sleep_report.py --hold -1                # leave the panel up until Ctrl-C
    python3 sleep_report.py --screen none --hold 0   # draw over the boot screen, no handover
    python3 sleep_report.py --no-narrate --no-speak   # pure numbers, no model, no audio
    python3 sleep_report.py --self-test              # synthetic night + assertions

Why a second morning tool next to morning.py
--------------------------------------------
morning.py asks Qwen for three warm sentences and nothing else: no score, no percentages, no
panel. This script splits the job in two, because the two halves have different rules:

  * the numbers are arithmetic - the same log in always gives the same score and the same
    panel, with no model anywhere near them. A score that moves because the language model
    felt poetic is not a measurement;
  * the sentences are Qwen's - 3-4 plain sentences said out loud through the speakers - but
    every quantity in them has to exist in this night's log, or the sentence is dropped
    back to the template's own wording (see "The note a model says out loud").

What it measures, and over what
-------------------------------
The *sleeping period* is the union of the handoff windows (`"event": "handoff"` until the
next `"event": "handoff_end"`), not the first to last line in the file. A test run at
20:04 and a real night at 22:45 live in the same JSONL; only the windows where the device
actually held the night count. Sessions without an end (the log is still being written, or
the process was killed) are closed at the last thing they logged. With no handoff lines at
all - overnight.py / mouth_open.py logs - the whole file is one window.

Every reading is turned into an interval and clipped to those windows:

  * a mouth entry carries `held_s`, so it is [t, t + held_s] - night_watch writes a state
    when it *ends*, and `t` is when it started;
  * a snore entry carries `dur` and is independent of the camera, so it is its own
    interval and may overlap a mouth state;
  * old change-only logs (overnight.py) have no duration, so a reading lasts until the
    next one, which is the only honest guess for a sampler that logs on change.

The percentages are time, not counts: a six-second snore does not weigh the same as a
half-hour one. `snoring`, `mouth open` and `out of bed` are reported separately because
they are not exclusive - a person can snore with the mouth shut (daytime experiment E says
so), and MAR is never evidence of snoring. Old logs say `nobody` where night_watch now
says `user_leave`; both mean "not in front of the camera", and both are counted as out of
bed. A camera that cannot see (`camera_unknown`, `camera_off`) is *not* out of bed: that
is counted apart, as a blind spot, because guessing would put a story in the morning
report that the log never contained.

The score
---------
10 minus four penalties, each a rate with a cap, so no single signal can own the number:

    possible snoring   0.15 per percentage point, cap 4.0
    mouth open         0.06 per percentage point, cap 2.5
    out of bed         0.15 per percentage point, cap 2.5
    fragmentation      0.04 per snore event,       cap 1.0

Snoring is weighted hardest because it is the thing the device can actually hear, and
fragmentation (many separate events) is a small separate correction, since ten 20-second
events are a worse night than one 200-second event with the same total time.
The worst possible night still scores 0, never negative, and `--explain` prints every
penalty, so a disagreement is with the weights, not with a black box. The weights are the
only tunable thing here - change them in WEIGHTS, and the self-test still holds.

The four lines on the panel
---------------------------
    Your sleep score was 6/10.
    Time spent snoring: 21%
    Time spent with mouth open: 45%
    Time spent out of bed: 8%

The Mini PiTFT is the Adafruit 1.14in 240x135 ST7789 wired as in Lab 2 (CS to GPIO5, DC
to GPIO25, backlight GPIO22), driven through Blinka:

    uv pip install adafruit-blinka==8.64.0 adafruit-circuitpython-rgb-display lgpio

(Blinka 10 wants gpiod on the Pi 5; 8.64.0 is the version the boot screen already uses and
it drives the panel through lgpio, which is why it is pinned here.)

If the modules are missing, or there is no panel on the header, the script prints the same
four lines instead of failing - the report is still worth having. Text is auto-fitted: the
longest line ("Time spent with mouth open: 45%") decides the font size, so it never
clips. `--image` renders the panel to a PNG with no hardware at all, which is how you
check the layout after changing it.

The note a model says out loud
-------------------------------
The score, the percentages and the four panel lines are arithmetic and never touch a model.
The *words* do: after the report is computed, the local Qwen writes a 3-4 sentence morning
note, and Piper reads it through the speakers.

    python3 sleep_report.py                      # qwen writes, the speaker says it
    python3 sleep_report.py --no-narrate         # the script's own three sentences
    python3 sleep_report.py --no-speak           # words on screen, silence
    python3 sleep_report.py --model qwen3:0.6b   # a different voice for the words

What the model is given: the numbers (FACTS), a slice of the night log picked by meaning
(handover lines, the longest clips - not just the tail, which is what morning.py does), the
printed report, and a plain draft note that is already true. Its job is to say the draft the
way a person would, not to find new facts.

What it is not allowed to do, because a 0.8b model asked about breathing will otherwise
write "the noise was so loud it didn't bother me" about a 0.7% snoring night:

  * invent a quantity - every percentage, duration ("almost an hour" for 2h11m), clip
    count, score and clock time it states must exist in this night's numbers, and be within
    a small tolerance (a rounded "7 hours" for 7h24m is fine, 2h11m is not);
  * diagnose - apnea, desaturation, syndrome, "sleep study" and friends are one-hit vetoes
    ("not a diagnosis" is allowed: that is the honest disclaimer, not a claim).

A rejected note is not thrown away silently: stderr shows the phrase that failed and what
the model said, and the report falls back to the template's own three sentences, which are
also what `--no-narrate` prints. Same idea as the score: the sentence that reaches the
person must be one the log can back up.

The words come out of the Lab 3 speaker: Piper synthesises the note with
voices/en_US-lessac-medium.onnx (the voice quiet_coyote_night already uses, ~8 s for four
sentences here), then `ffplay` plays the WAV, with `espeak-ng` as the ugly fallback if the
Piper voice is missing. `--no-speak` keeps it silent, `--voice`/`--length-scale` change how
it sounds, `--narrative-wav /tmp/n.wav` keeps the file. The audio starts before the panel
is taken and keeps playing while the panel holds - a `--hold 0` still waits for the last
sentence, because cutting the reveal in half would waste the whole night.

Somebody else already owns the panel
------------------------------------
On this machine the boot screen (`/home/pi/screen_boot_script.py`, systemd unit
`piscreen.service`) has been drawing on the ST7789 since boot. Two processes writing the
same SPI bus is a race that looks like flickering garbage, so the report takes the panel
politely:

    1. find the owner  - `systemctl is-active piscreen.service`, else a matching process
    2. pause it        - `sudo -n systemctl stop piscreen.service` (a SIGTERM would do
                         nothing: the unit is Restart=always, and systemd would bring it
                         back three seconds later, mid-draw)
    3. draw, then hold - `--hold` seconds (default 120; -1 = until Ctrl-C, 0 = flash)
    4. give it back    - `systemctl start`, or relaunch the same argv for a plain process,
                         from a `finally:` block and from SIGTERM/SIGINT/SIGHUP handlers

`--screen none` skips all of this and draws over the boot screen, which is only sensible
if the boot screen has been stopped by hand. If this script is ever SIGKILLed the panel
stays dark; `sudo systemctl start piscreen` puts the boot screen back. Ctrl-C does not
have that problem.

Honesty
-------
This device sees loud low-frequency sound and an open mouth. It cannot see airflow, blood
oxygen or apnea, so the report says "possible snoring" and never diagnoses anything. A
quiet night is also a result: `--json` on a night with nothing in it is still valid output,
and the report says the night was quiet instead of inventing an event.
"""
import argparse
import dataclasses
import datetime
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

# --------------------------------------------------------------------------- reading

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PANEL_W, PANEL_H = 240, 135                 # landscape, as rotated in Lab 2

OPEN_STATES = {"open"}
CLOSED_STATES = {"closed"}
AWAY_STATES = {"user_leave", "nobody"}      # "nobody" is the pre-night_watch vocabulary
UNSEEN_STATES = {"unknown", "off"}          # camera broken vs. camera never turned on


def parse_ts(text):
    """ISO seconds -> POSIX seconds. Naive local time, same clock the log was written on."""
    return datetime.datetime.fromisoformat(text).timestamp()


def iso(ts):
    return datetime.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def clock(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def human_span(seconds):
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def load(path):
    """JSONL in, list of dicts out.

    Junk is skipped with a note instead of a traceback: a half-written last line is normal
    when the night was killed with Ctrl-C, and a log with one bad timestamp should still
    produce a report for the other seven hours.
    """
    entries = []
    with open(path, encoding="utf-8", errors="replace") as fp:
        for number, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                parse_ts(entry["t"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                print(f"skipping unreadable line {number} of {path}", file=sys.stderr)
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def default_log():
    """night_log.jsonl if it is here, else the newest logs/*/night_log.jsonl."""
    here = pathlib.Path("night_log.jsonl")
    if here.exists():
        return here
    candidates = sorted(pathlib.Path("logs").glob("*/night_log.jsonl"),
                        key=lambda p: p.stat().st_mtime)
    if candidates:
        return candidates[-1]
    raise SystemExit("no night_log.jsonl here and nothing under logs/*/ - pass --log")


# ------------------------------------------------------------------------ intervals

def merge(intervals):
    """Overlapping or touching (start, end) pairs -> sorted, disjoint ones."""
    out = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [(s, e) for s, e in out]


def total(intervals):
    return sum(end - start for start, end in intervals)


def clip(intervals, windows):
    """Keep the parts of `intervals` that happened inside the handoff windows."""
    out = []
    for start, end in intervals:
        for w_start, w_end in windows:
            a, b = max(start, w_start), min(end, w_end)
            if b > a:
                out.append((a, b))
    return merge(out)


def end_of(entry):
    """Best guess at when a line stopped being true: explicit duration, else unknown."""
    for key in ("held_s", "dur"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return parse_ts(entry["t"]) + float(value)
    return None


def sessions(entries, min_session=0.0):
    """The handoff windows, merged. Falls back to the whole file for handoff-less logs."""
    windows, opened = [], None
    for entry in entries:                          # file order: handoff lines are appended live
        event = entry.get("event")
        if event == "handoff":
            if opened is not None:                 # two starts, no stop in between
                windows.append((opened, parse_ts(entry["t"])))
            opened = parse_ts(entry["t"])
        elif event == "handoff_end" and opened is not None:
            windows.append((opened, parse_ts(entry["t"])))
            opened = None

    if not windows and opened is None:             # no handoff vocabulary at all
        starts = [parse_ts(e["t"]) for e in entries]
        ends = [end_of(e) for e in entries if end_of(e) is not None]
        last = max(ends + starts)
        windows = [(min(starts), last)]
    elif opened is not None:                       # still running / killed: close at last activity
        ends = [end_of(e) for e in entries if end_of(e) is not None]
        windows.append((opened, max(ends + [opened])))

    kept = [(s, e) for s, e in merge(windows) if e - s >= min_session]
    dropped = len(merge(windows)) - len(kept)
    if dropped:
        print(f"ignoring {dropped} session(s) shorter than {min_session:g}s", file=sys.stderr)
    return kept


def classify(entry):
    """One line -> what the person was doing, in five honest buckets."""
    mouth = str(entry.get("mouth") or "").strip().lower()
    if mouth in OPEN_STATES:
        return "open"
    if mouth in CLOSED_STATES:
        return "closed"
    if mouth in AWAY_STATES:
        return "away"
    if mouth in UNSEEN_STATES:
        return "unseen"
    reading = str(entry.get("reading") or "").strip().lower()
    for prefix, kind in (("mouth_open", "open"), ("mouth open", "open"),
                         ("mouth_closed", "closed"), ("mouth closed", "closed"),
                         ("user_leave", "away"), ("nobody", "away"),
                         ("camera_unknown", "unseen"), ("camera_off", "unseen")):
        if reading.startswith(prefix):
            return kind
    if entry.get("snoring"):
        return "open"
    return "unknown_mouth"       # e.g. "person supine" from an overnight.py-only log


def is_snore(entry):
    return entry.get("event") == "snore" or str(entry.get("reading") or "").startswith("snore_event")


def timeline(entries, windows):
    """Clip the log to the night and give every line a duration.

    Returns (mouth_segments, snore_intervals): mouth segments are (start, end, kind),
    snore intervals are (start, end). A line without its own duration borrows time from
    the next line in the same window - that is how change-only logs get percentages.
    """
    segments, snores = [], []
    for w_start, w_end in windows:
        inside = sorted((e for e in entries
                         if w_start <= parse_ts(e["t"]) <= w_end),
                        key=lambda e: parse_ts(e["t"]))
        for index, entry in enumerate(inside):
            start = parse_ts(entry["t"])
            if is_snore(entry):
                end = end_of(entry) or start
                a, b = max(start, w_start), min(max(end, start), w_end)
                if b > a:
                    snores.append((a, b))
                continue
            end = end_of(entry)
            if end is None:                        # change-only log: held until the next line
                end = parse_ts(inside[index + 1]["t"]) if index + 1 < len(inside) else w_end
            a, b = max(start, w_start), min(end, w_end)
            if b > a:
                segments.append((a, b, classify(entry)))

    # A held interval can be overlapped by the line after it (an `alive` heartbeat repeats
    # the current state while the state's own interval is still open). The newer reading
    # wins, so no second gets counted twice - the buckets would otherwise add up to >100%.
    segments.sort(key=lambda seg: seg[0])
    trimmed = []
    for index, (start, end, kind) in enumerate(segments):
        if index + 1 < len(segments):
            end = min(end, segments[index + 1][0])
        if end > start:
            trimmed.append((start, end, kind))
    return trimmed, merge(snores)


# --------------------------------------------------------------------------- numbers

WEIGHTS = {                      # points per percentage point (or per event), and the cap
    "snoring": (0.15, 4.0),
    "mouth_open": (0.06, 2.5),
    "out_of_bed": (0.15, 2.5),
    "fragmentation": (0.04, 1.0),  # per snore event
}


@dataclasses.dataclass
class Stats:
    log: str
    windows: list
    sleep_s: float
    segments: list
    snores: list
    snore_events: int
    peak_mar: float | None
    loudest_dbfs: float | None
    loudest_at: str | None
    longest: dict

    # -- time per bucket
    def seconds(self, *kinds):
        return total([(s, e) for s, e, k in self.segments if k in kinds])

    def pct(self, seconds):
        return 100.0 * seconds / self.sleep_s if self.sleep_s else 0.0

    @property
    def snore_s(self):
        return total(self.snores)

    @property
    def open_s(self):
        return self.seconds("open")

    @property
    def closed_s(self):
        return self.seconds("closed")

    @property
    def away_s(self):
        return self.seconds("away")

    @property
    def unseen_s(self):
        return self.seconds("unseen")

    @property
    def unknown_s(self):
        return self.seconds("unknown_mouth")

    @property
    def snore_pct(self):
        return self.pct(self.snore_s)

    @property
    def open_pct(self):
        return self.pct(self.open_s)

    @property
    def closed_pct(self):
        return self.pct(self.closed_s)

    @property
    def away_pct(self):
        return self.pct(self.away_s)

    @property
    def unseen_pct(self):
        return self.pct(self.unseen_s)

    @property
    def unknown_pct(self):
        return self.pct(self.unknown_s)

    # -- score
    def penalties(self):
        """One (weight key, label, amount as printed, raw value) per penalty, in order."""
        return [
            ("snoring", "possible snoring", f"{self.snore_pct:.1f}%", self.snore_pct),
            ("mouth_open", "mouth open", f"{self.open_pct:.1f}%", self.open_pct),
            ("out_of_bed", "out of bed", f"{self.away_pct:.1f}%", self.away_pct),
            ("fragmentation", "fragmentation", f"{self.snore_events} events",
             self.snore_events),
        ]

    def penalty_points(self):
        return [(label, amount, min(WEIGHTS[key][1], WEIGHTS[key][0] * value))
                for key, label, amount, value in self.penalties()]

    @property
    def raw_score(self):
        """10 minus every penalty, clamped to 0..10, before any rounding."""
        return max(0.0, min(10.0, 10.0 - sum(p for _, _, p in self.penalty_points())))

    @property
    def score(self):
        """0..10 to one decimal, as printed next to the verdict."""
        return round(self.raw_score, 1)

    @property
    def score_int(self):
        """Whole number for the panel and the report - rounded from the raw score, so
        rounding twice (9.45 -> 9.5 -> 10) cannot flatter a night."""
        return int(min(10, self.raw_score + 0.5))

    def as_dict(self):
        return {
            "log": self.log,
            "sessions": len(self.windows),
            "sleep_seconds": round(self.sleep_s, 1),
            "score": self.score,
            "score_int": self.score_int,
            "snore_pct": round(self.snore_pct, 2),
            "open_pct": round(self.open_pct, 2),
            "closed_pct": round(self.closed_pct, 2),
            "away_pct": round(self.away_pct, 2),
            "unseen_pct": round(self.unseen_pct, 2),
            "unknown_pct": round(self.unknown_pct, 2),
            "snore_events": self.snore_events,
            "snore_seconds": round(self.snore_s, 1),
            "peak_mar": self.peak_mar,
            "loudest_dbfs": self.loudest_dbfs,
            "longest": self.longest,
        }


def longest_of(segments, kind):
    win = [seg for seg in segments if seg[2] == kind]
    return max(win, key=lambda seg: seg[1] - seg[0]) if win else None


def analyze(entries, log_path="-", min_session=0.0):
    windows = sessions(entries, min_session=min_session)
    if not windows:
        raise SystemExit("this log has no usable session (try --min-session 0)")

    segments, snores = timeline(entries, windows)
    if not segments and not snores:
        raise SystemExit("the log has no readings inside its sessions - nothing to report")

    def in_windows(entry):
        ts = parse_ts(entry["t"])
        return any(s <= ts <= e for s, e in windows)

    inside = [e for e in entries if in_windows(e)]

    mars = [e["mar"] for e in inside if isinstance(e.get("mar"), (int, float))]
    snore_lines = [e for e in inside if is_snore(e)]
    loudest = max((e for e in snore_lines if isinstance(e.get("peak_dbfs"), (int, float))),
                  key=lambda e: e["peak_dbfs"], default=None)

    longest = {}
    for kind in ("open", "away", "closed"):
        seg = longest_of(segments, kind)
        if seg:
            longest[kind] = {"seconds": round(seg[1] - seg[0], 1), "at": clock(seg[0])}
    if snores:
        seg = max(snores, key=lambda s: s[1] - s[0])
        longest["snore"] = {"seconds": round(seg[1] - seg[0], 1), "at": clock(seg[0])}

    return Stats(
        log=str(log_path),
        windows=windows,
        sleep_s=total(windows),
        segments=segments,
        snores=snores,
        snore_events=len(snore_lines),
        peak_mar=round(max(mars), 2) if mars else None,
        loudest_dbfs=round(loudest["peak_dbfs"], 1) if loudest else None,
        loudest_at=clock(parse_ts(loudest["t"])) if loudest else None,
        longest=longest,
    )


def verdict(score):
    if score >= 9:
        return "a quiet night"
    if score >= 7:
        return "a decent night"
    if score >= 5:
        return "a restless night"
    if score >= 3:
        return "a rough night"
    return "a hard night"


def highlights(stats):
    """One deterministic sentence out of the longest stretches - no model involved."""
    parts = []
    names = (("snore", "snoring"), ("open", "mouth open"), ("away", "out of bed"))
    for key, label in names:
        hit = stats.longest.get(key)
        if hit:
            parts.append(f"{label} for {human_span(hit['seconds'])} from {hit['at']}")
    if not parts:
        return "Nothing stood out: the log holds no snoring and no mouth state at all."
    return "Longest stretch: " + ", ".join(parts) + "."


def caveat(stats):
    """What this device could not see, spelled out so the morning cannot invent it."""
    notes = []
    if stats.unseen_pct >= 5:
        notes.append(f"the camera saw nothing for {stats.unseen_pct:.0f}% of the night, "
                     f"so those minutes are unknown, not quiet")
    if stats.unknown_pct >= 5:
        notes.append(f"{stats.unknown_pct:.0f}% of the night has no mouth reading")
    if not stats.snores:
        notes.append("no low-frequency event crossed the threshold all night")
    if stats.away_pct >= 25:
        notes.append(f"you were out of view {human_span(stats.away_s)}, "
                     f"so this is only part of your sleep")
    return "; ".join(notes) or "the camera had the bed in view for the whole night"


# ---------------------------------------------------------------------------- report

DEFAULT_TEMPLATE = """\
Sleep report · {date}
{span} · {duration} in {sessions_text}

  score              {score}/10   ({verdict})
  possible snoring   {snore_pct:5.1f}%   {snore_events} event(s), {snore_min}
  mouth open         {open_pct:5.1f}%   {open_min}
  mouth closed       {closed_pct:5.1f}%
  out of bed         {away_pct:5.1f}%   {away_min}
  camera blind spot  {unseen_pct:5.1f}%   {unseen_min}

{highlights}
{scoring}
{caveat}

{narrative}

Not a diagnosis: this device hears loud low-frequency sound and sees an open mouth.
It cannot see airflow or blood oxygen, so "possible snoring" is as far as it goes.
"""


def template_path():
    for candidate in (pathlib.Path("sleep_report_template.txt"),
                      SCRIPT_DIR / "sleep_report_template.txt"):
        if candidate.exists():
            return candidate
    return None


def strip_comments(text):
    """Drop '#' lines: a template file documents itself without leaking into the report."""
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#")).strip()


def read_template(args):
    """--template string, then --template-file, then sleep_report_template.txt, then built-in."""
    if args.template:
        text = args.template
    elif args.template_file:
        text = pathlib.Path(args.template_file).read_text(encoding="utf-8")
    else:
        found = template_path()
        text = found.read_text(encoding="utf-8") if found else DEFAULT_TEMPLATE
    return strip_comments(text)


def fields(stats, narrative="", source=""):
    """Every placeholder a template may use. `narrative` is the spoken morning note."""
    first, last = stats.windows[0][0], stats.windows[-1][1]
    same_day = iso(first)[:10] == iso(last)[:10]
    return {
        "date": iso(first)[:10] + ("" if same_day else f" -> {iso(last)[:10]}"),
        "span": f"{clock(first)} -> {clock(last)}",
        "start": clock(first),
        "end": clock(last),
        "duration": human_span(stats.sleep_s),
        "hours": stats.sleep_s / 3600.0,
        "sessions": len(stats.windows),
        "sessions_text": f"{len(stats.windows)} session"
                         + ("" if len(stats.windows) == 1 else "s"),
        "score": stats.score_int,
        "score_exact": f"{stats.score:.1f}",
        "verdict": verdict(stats.score),
        "snore_pct": stats.snore_pct,
        "open_pct": stats.open_pct,
        "closed_pct": stats.closed_pct,
        "away_pct": stats.away_pct,
        "unseen_pct": stats.unseen_pct,
        "unknown_pct": stats.unknown_pct,
        "snore_min": human_span(stats.snore_s),
        "open_min": human_span(stats.open_s),
        "away_min": human_span(stats.away_s),
        "unseen_min": human_span(stats.unseen_s),
        "in_bed_pct": max(0.0, 100.0 - stats.away_pct),
        "snore_events": stats.snore_events,
        "snore_peak_dbfs": stats.loudest_dbfs if stats.loudest_dbfs is not None else "n/a",
        "snore_peak_at": stats.loudest_at or "n/a",
        "peak_mar": stats.peak_mar if stats.peak_mar is not None else "n/a",
        "highlights": highlights(stats),
        "caveat": f"Worth knowing: {caveat(stats)}.",
        "scoring": "Score = 10 - (0.15/pt snoring, cap 4) - (0.06/pt mouth open, cap 2.5)"
                   " - (0.15/pt out of bed, cap 2.5) - (0.04/event, cap 1).",
        "narrative": narrative,
        "narrative_source": source,
        "log": stats.log,
    }


def render_report(stats, template, narrative="", source=""):
    template = strip_comments(template)
    try:
        return template.format(**fields(stats, narrative, source))
    except KeyError as missing:
        raise SystemExit(f"template uses unknown field {missing}; "
                         f"available: {', '.join(sorted(fields(stats)))}")


def explain(stats):
    lines = [f"score {stats.score}/10  (10 minus the penalties below)"]
    for key, label, amount, value in stats.penalties():
        rate, cap = WEIGHTS[key]
        points = min(cap, rate * value)
        unit = "per event" if key == "fragmentation" else "per point"
        lines.append(f"  {label:<17} {amount:>12}   -{points:4.2f}   "
                     f"({rate} {unit}, cap {cap})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- words

VOICE_MODEL = "en_US-lessac-medium"          # the voice quiet_coyote_night already uses
VOICE_DIR = SCRIPT_DIR / "voices"

# A diagnosis is the one thing this device must never produce, and a small model asked to
# talk about breathing will reach for it sooner or later. One hit and its words are dropped.
# "not a diagnosis" is allowed on purpose: that is the honest disclaimer, not a claim.
DIAGNOSIS = re.compile(r"apnoea|apnea|desaturat|sleep disorder|syndrome|sleep study|"
                       r"\bdiagnos(?:e|ed|ing)\b|medical advice", re.I)

# Two more ways a small model spoils the moment: it claims to know whether the person was
# awake (it cannot - it saw a bed), and it repeats the instructions back at the reader
# ("I never say they were awake"). Both are rejected like an invented number.
OVERREACH = re.compile(r"\bawake\b|\bi (?:never|didn'?t|cannot|can'?t) "
                       r"(?:know|tell|say|see)\b|\bnever say\b", re.I)

NARRATIVE_RULES = """\
Write 3 or 4 short sentences, 70 words at most, in everyday English a tired person can
follow. Address the person as "you", and sound like a device that was in the room all
night - not like a chart.

How to build it:
1. Open with the score as "X out of 10" and how much of the night you watched.
2. Say the one thing that mattered most, with its number copied exactly from FACTS.
3. Say one limit on the picture, only if FACTS gives one (time out of bed, or time the
   camera saw nothing).
4. Close with what it means in plain words for this morning.

Never state or hint that the person was awake, or that they woke up: only a camera and a
microphone watched the bed. The score is theirs, so write "your score".

Every number must be one that FACTS gives, written the same way: no new sums, no "about an
hour" when FACTS says 2h11m, no "ten minutes" unless FACTS says ten minutes. Copy the phrase
that carries a number ("out of view for 2h11m") instead of paraphrasing the quantity. Do not call
the night quiet when FACTS shows snoring clips or an open mouth. "Possible snoring" is the
strongest claim allowed: no apnea, no conditions, no causes, no medical advice. No lists,
no headings, no emoji, no quotation marks around the answer.
"""


def facts_block(stats):
    """The numbers spelled out for the prompt: the only facts the model may use."""
    first, last = stats.windows[0][0], stats.windows[-1][1]
    lines = [
        f"Night: {clock(first)} to {clock(last)} ({human_span(stats.sleep_s)}, "
        f"{len(stats.windows)} session(s))",
        f"Score: {stats.score_int}/10 ({verdict(stats.score)})",
        f"Possible snoring: {stats.snore_pct:.1f}% of the night "
        f"({human_span(stats.snore_s)}), {stats.snore_events} clips",
        f"Mouth open: {stats.open_pct:.1f}% ({human_span(stats.open_s)})",
        f"Mouth closed: {stats.closed_pct:.1f}%",
        f"Out of bed or out of view: {stats.away_pct:.1f}% ({human_span(stats.away_s)})",
        f"Camera could not see: {stats.unseen_pct:.1f}% ({human_span(stats.unseen_s)})",
    ]
    if stats.loudest_dbfs is not None:
        lines.append(f"Loudest clip: {stats.loudest_dbfs} dBFS at {stats.loudest_at}")
    for key, label in (("snore", "Longest snoring stretch"),
                       ("open", "Longest mouth open"),
                       ("away", "Longest out of bed")):
        hit = stats.longest.get(key)
        if hit:
            lines.append(f"{label}: {human_span(hit['seconds'])} from {hit['at']}")
    return "\n".join(lines)


def digest(entries, windows, limit=40):
    """A small, honest slice of the log: starts, ends, the longest snores, first and last.

    A real night is thousands of lines; the prompt has to stay small, so the selection is
    by meaning (handover lines, longest clips) instead of just taking the tail, which is
    what morning.py does and why it can miss the interesting part of the night.
    """
    def inside(entry):
        when = parse_ts(entry["t"])
        return any(start <= when <= end for start, end in windows)

    rows = sorted(((parse_ts(e["t"]), e) for e in entries
                   if inside(e) and not e.get("alive")), key=lambda row: row[0])
    if not rows:
        return []

    chosen = set(range(min(4, len(rows))))                    # how the night started
    chosen |= set(range(max(0, len(rows) - 4), len(rows)))    # and how it ended
    for index, (_when, entry) in enumerate(rows):
        if entry.get("event") in ("handoff", "handoff_end"):
            chosen.add(index)
    loudest = sorted(((i, e) for i, (_when, e) in enumerate(rows) if is_snore(e)),
                     key=lambda pair: -(pair[1].get("dur") or 0))[:8]
    chosen |= {index for index, _entry in loudest}

    picked = [rows[i] for i in sorted(chosen)][:limit]
    return [f'{clock(when)} {entry.get("reading", "")}'.strip() for when, entry in picked]


def build_prompt(stats, report_text, log_lines, draft):
    """Log first, numbers second, the template's own wording third - then the style rules.

    The draft note is the anchor: it is short, true, and already in the template's voice.
    The model's job is to say it the way a person would, not to go looking for new facts.
    """
    return f"""You are the small bedside device that watched this night. In the morning you tell
the person who slept there what you noticed. Warm, plain, personal, second person "you".
Use only the facts below and invent nothing.

FACTS
{facts_block(stats)}

WHAT THE LOG SAYS (selected lines, oldest first)
{chr(10).join(log_lines) if log_lines else "(the log holds no readings)"}

THE REPORT ALREADY PRINTED (same numbers; do not contradict it)
{report_text.strip()}

A PLAIN NOTE THAT IS ALREADY TRUE (rewrite it warmly; keep every number; keep it 3-4
sentences; you may reorder and rephrase, but add no new fact)
{draft}

{NARRATIVE_RULES}"""


def fallback_narrative(stats):
    """What the device says when Qwen is not there: true, plain, three sentences."""
    first, last = stats.windows[0][0], stats.windows[-1][1]
    parts = [f"Your score was {stats.score_int} out of 10 for {human_span(stats.sleep_s)} "
             f"of watching, from {clock(first)} to {clock(last)}."]
    if stats.snore_s >= 1:
        parts.append(f"Possible snoring covered about {stats.snore_pct:.0f}% of the night in "
                     f"{stats.snore_events} clips, and your mouth was open "
                     f"{stats.open_pct:.0f}% of the time.")
    else:
        parts.append(f"No snoring crossed the threshold, and your mouth was open "
                     f"{stats.open_pct:.0f}% of the time.")
    if stats.away_pct >= 1:
        parts.append(f"You were out of view for {human_span(stats.away_s)}, so that part of "
                     f"the night is not in this picture.")
    elif stats.unseen_pct >= 1:
        parts.append(f"The camera saw nothing for {stats.unseen_pct:.0f}% of the night, so "
                     f"those minutes are unknown rather than quiet.")
    else:
        parts.append("The bed was in view the whole night.")
    return " ".join(parts)


def clean_narrative(text):
    """One paragraph, 3-4 sentences: small models add headings, bullets and asterisks."""
    text = re.sub(r"</?think>", " ", text or "", flags=re.I)
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", text, flags=re.M)
    text = " ".join(text.split())
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    unique, seen = [], set()
    for sentence in sentences:              # small models like to repeat the first sentence
        key = re.sub(r"\W+", "", sentence.lower())
        if key and key not in seen:
            seen.add(key)
            unique.append(sentence)
    if not unique:
        return ""
    out = " ".join(unique[:4])
    if out[-1] not in ".!?":
        out += "."
    return out


DIGIT_CLAIMS = (
    ("percent", r"(\d+(?:\.\d+)?)\s*(?:%|percent)", 1.0),
    ("seconds", r"(?<![\w:.])(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours?)\b", 3600.0),
    ("seconds", r"(?<![\w:.])(\d+(?:\.\d+)?)\s*(?:m|mins?|minutes?)\b", 60.0),
    ("seconds", r"(?<![\w:.])(\d+(?:\.\d+)?)\s*(?:s|secs?|seconds?)\b", 1.0),
    ("score", r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*10\b", 1.0),
    ("events", r"(\d+)\s*(?:clips?|events?|times?)\b", 1.0),
)

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
                "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
                "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
QUANTITY = r"(\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + r"|an?)"
UNIT = r"(hour|minute|second)"
WORD_SCORE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\s+(?:out of|/)\s*ten\b", re.I)
WORD_NUMBER = re.compile(r"\b" + QUANTITY + r"\s+"
                         r"(?:(?:short|long|quick|brief|little|small)\s+)?"
                         r"(?:and a half\s+)?"
                         r"(hour|minute|second|clip|event|time|percent)s?\b", re.I)
HALF_A_UNIT = re.compile(r"\bhalf\s+(?:an?\s+)?" + UNIT + r"s?\b", re.I)
# "two and a half hours" / "two hours and a half" / "seven hours and a quarter"
FRACTION_THEN_UNIT = re.compile(r"\b" + QUANTITY + r"\s+and\s+(?:a\s+)?(half|quarter)\s+"
                                + UNIT + r"s?\b", re.I)
UNIT_THEN_FRACTION = re.compile(r"\b" + QUANTITY + r"\s+" + UNIT + r"s?\s+and\s+(?:a\s+)?"
                                r"(half|quarter)\b", re.I)
FRACTIONS = {"half": 0.5, "quarter": 0.25}
COMPOUND_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h|hrs?|hours?)\s*(?:and\s+)?"
                               r"(\d+(?:\.\d+)?)\s*(?:m|mins?|minutes?)\b", re.I)


def word_value(token):
    token = token.lower()
    if token in ("a", "an"):
        return 1.0
    return float(NUMBER_WORDS[token]) if token in NUMBER_WORDS else float(token)


def unit_seconds(unit):
    unit = unit.lower()
    return 3600.0 if unit.startswith("hour") else 60.0 if unit.startswith("minute") else 1.0


def rounded_durations(seconds):
    """The ways a writer may honestly round one span: "7h24m" -> 7h, 24m, 444m, 7.4h.

    Without this, "seven hours" for 7h24m would be rejected and the model would fall back
    for a harmless rounding; with it, "two and a half hours" for 2h11m is still caught.
    """
    hours, minutes = int(seconds // 3600), int((seconds % 3600) // 60)
    forms = {hours * 3600, minutes * 60, round(seconds / 3600, 1) * 3600,
             round(seconds / 60) * 60}
    return {form for form in forms if form > 0}


def allowed_quantities(stats):
    """Percentages, durations, counts and clock times the night actually holds."""
    exact = {stats.sleep_s, stats.snore_s, stats.open_s, stats.away_s,
             stats.unseen_s, stats.closed_s}
    exact |= {hit["seconds"] for hit in stats.longest.values()}
    durations = set(exact)
    for seconds in exact:
        durations |= rounded_durations(seconds)
    clocks = {clock(bound)[:5] for window in stats.windows for bound in window}
    for seg in stats.segments:
        clocks.add(clock(seg[0])[:5])
    for seg in stats.snores:
        clocks.add(clock(seg[0])[:5])
    return {"percent": [stats.snore_pct, stats.open_pct, stats.closed_pct, stats.away_pct,
                        stats.unseen_pct, stats.unknown_pct, 0.0, 100.0],
            "seconds": [d for d in durations if d > 0],
            "score": [float(stats.score_int), stats.score],
            "events": [float(stats.snore_events)],
            "clock": sorted(clocks)}


def claims(text):
    """Every quantity the text asserts, as (kind, value, phrase). Overlapping forms are
    consumed as they are read, so "two hours and a half" is one claim, not two."""
    found = []

    for match in COMPOUND_DURATION.finditer(text):
        found.append(("seconds", float(match.group(1)) * 3600 + float(match.group(2)) * 60,
                      match.group(0).strip()))
    text = COMPOUND_DURATION.sub(" ", text)

    for pattern, unit_first in ((UNIT_THEN_FRACTION, True), (FRACTION_THEN_UNIT, False)):
        for match in pattern.finditer(text):
            count = word_value(match.group(1))
            fraction = FRACTIONS[match.group(3 if unit_first else 2).lower()]
            unit = match.group(2 if unit_first else 3)
            found.append(("seconds", (count + fraction) * unit_seconds(unit),
                          match.group(0).strip()))
        text = pattern.sub(" ", text)

    for match in HALF_A_UNIT.finditer(text):
        found.append(("seconds", 0.5 * unit_seconds(match.group(1)), match.group(0).strip()))
    text = HALF_A_UNIT.sub(" ", text)

    for kind, pattern, factor in DIGIT_CLAIMS:
        for match in re.finditer(pattern, text, re.I):
            found.append((kind, float(match.group(1)) * factor, match.group(0).strip()))

    for match in WORD_NUMBER.finditer(text):
        if not match.group(1):
            continue                             # a bare "minutes" claims no quantity
        word, unit = match.group(1).lower(), match.group(2).lower()
        count = word_value(word)                   # digits, "two", or "a"/"an"
        kind = "events" if unit in ("clip", "event", "time") else \
            "percent" if unit == "percent" else "seconds"
        found.append((kind, count * unit_seconds(unit), match.group(0).strip()))

    for match in WORD_SCORE.finditer(text):
        found.append(("score", float(NUMBER_WORDS[match.group(1).lower()]),
                      match.group(0).strip()))

    for stamp in re.findall(r"\b((?:[01]?\d|2[0-3]):[0-5]\d)\b", text):
        found.append(("clock", stamp.zfill(5), stamp))
    return found


def unsupported_claims(text, stats):
    """The phrases in `text` that this night cannot back up. Empty list = grounded."""
    allowed = allowed_quantities(stats)
    bad = []
    for kind, value, phrase in claims(text):
        if kind == "clock":
            if value not in allowed["clock"]:
                bad.append(phrase)
            continue
        tolerance = {"percent": 0.6, "events": 0.5, "score": 0.5}.get(
            kind, max(60.0, 0.03 * value))
        if not any(abs(value - other) <= tolerance for other in allowed[kind]):
            bad.append(phrase)
    return list(dict.fromkeys(bad))            # keep the first wording of each made-up claim


def ask_qwen(prompt, model, timeout):
    """POST to the local Ollama. None on any failure: the report is worth printing offline."""
    import requests
    try:
        answer = requests.post("http://localhost:11434/api/generate", json={
            "model": model,
            "prompt": prompt,
            "think": False,                 # reasoning tokens are not wanted in a 70-word note
            "stream": False,
            "options": {"num_ctx": 4096, "temperature": 0.3, "num_predict": 160},
        }, timeout=timeout)
        answer.raise_for_status()
        return answer.json().get("response", "")
    except Exception as error:              # noqa: BLE001 - any failure means "no words"
        print(f"qwen unavailable ({type(error).__name__}: {error}); "
              f"using the template wording", file=sys.stderr)
        return None


def narrate(stats, report_text, entries, args):
    """(text, source). Qwen's version if it is available, grounded and clean; else ours."""
    fallback = fallback_narrative(stats)
    if args.no_narrate:
        return fallback, "template"

    prompt = build_prompt(stats, report_text, digest(entries, stats.windows), fallback)
    print(f"asking {args.model} for the morning note (offline, on this Pi) ...",
          file=sys.stderr)
    text = clean_narrative(ask_qwen(prompt, args.model, args.model_timeout))
    if not text:
        return fallback, "template"
    if DIAGNOSIS.search(text):
        print(f'qwen reached for a diagnosis ("{DIAGNOSIS.search(text).group(0)}"); '
              f'using the template wording', file=sys.stderr)
        return fallback, "template"
    if OVERREACH.search(text):
        print(f'qwen overreached ("{OVERREACH.search(text).group(0)}"); '
              f'using the template wording', file=sys.stderr)
        return fallback, "template"
    unsupported = unsupported_claims(text, stats)
    if unsupported:
        print("qwen claimed " + ", ".join(f'"{phrase}"' for phrase in unsupported[:4])
              + " which this night's log cannot back up; using the template wording\n"
              + f"  rejected: {text}", file=sys.stderr)
        return fallback, "template"
    return text, f"qwen {args.model}"


# --------------------------------------------------------------------------- speaker

def synthesize(text, wav, voice, voice_dir, length_scale=1.05):
    """Write the sentence to a WAV: Piper first (natural), eSpeak as the ugly fallback."""
    wav = pathlib.Path(wav)
    text_file = wav.with_suffix(".txt")
    text_file.write_text(text + "\n", encoding="utf-8")
    onnx = pathlib.Path(voice_dir) / f"{voice}.onnx"
    commands = []
    if onnx.is_file():
        commands.append(([sys.executable, "-m", "piper", "-m", str(onnx), "-f", str(wav),
                          "-i", str(text_file), "--length-scale", str(length_scale),
                          "--sentence-silence", "0.25"], f"piper {voice}"))
    for exe in ("espeak-ng", "espeak"):
        if shutil.which(exe):
            commands.append(([exe, "-s", "150", "-w", str(wav), text], exe))
    try:
        for cmd, name in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=300)
            except (OSError, subprocess.SubprocessError) as error:
                print(f"{name} could not run: {error}", file=sys.stderr)
                continue
            if result.returncode == 0 and wav.is_file() and wav.stat().st_size > 0:
                return wav, name
            detail = (result.stderr or result.stdout or b"").decode(errors="replace").strip()
            print(f"{name} failed: {detail.splitlines()[-1] if detail else 'no output'}",
                  file=sys.stderr)
    finally:
        text_file.unlink(missing_ok=True)
    return None, None


def start_speech(text, args):
    """Say the morning note. Returns the ffplay handle so the panel can stay up while it talks."""
    if not args.speak:
        return None
    wav = (pathlib.Path(args.narrative_wav) if args.narrative_wav else
           pathlib.Path(tempfile.gettempdir()) / f"sleep_report_{os.getpid()}.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav, engine = synthesize(text, wav, args.voice, args.voice_dir, args.length_scale)
    if wav is None:
        print("nothing on this machine could speak the report; the text is above",
              file=sys.stderr)
        return None
    print(f"speaking the report ({engine})", file=sys.stderr)
    try:
        return subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "error",
                                 str(wav)], stdin=subprocess.DEVNULL)
    except OSError as error:
        print(f"could not play the report: {error}", file=sys.stderr)
        return None


def stop_speech(player, grace=10.0):
    if player is None or player.poll() is not None:
        return
    player.terminate()
    try:
        player.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        player.kill()
        player.wait()


# --------------------------------------------------------------------------- display

def display_lines(stats):
    """The four lines the panel shows. Keep the wording stable: it is the promise."""
    return [
        f"Your sleep score was {stats.score_int}/10.",
        f"Time spent snoring: {stats.snore_pct:.0f}%",
        f"Time spent with mouth open: {stats.open_pct:.0f}%",
        f"Time spent out of bed: {stats.away_pct:.0f}%",
    ]


def _font(size):
    from PIL import ImageFont
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)     # Pillow >= 10
    except TypeError:
        return ImageFont.load_default()


PANEL_MARGIN = 4


def fit_text(lines, size=(PANEL_W, PANEL_H), margin=PANEL_MARGIN):
    """Largest font in which every line fits the panel; the self-test checks this.

    The longest line ("Time spent with mouth open: 45%") decides the size, because one
    clipped line on a 135 px tall panel is a bug you only see at 3 a.m.
    """
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", size))
    usable_w, usable_h = size[0] - 2 * margin, size[1] - 2 * margin
    for px in range(28, 6, -1):
        font = _font(px)
        widest, tallest = 0.0, 0.0
        for text in lines:
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            widest = max(widest, right - left)
            tallest = max(tallest, bottom - top)
        line_h = tallest * 1.18
        if widest <= usable_w and line_h * len(lines) <= usable_h:
            return font, line_h
    font = _font(7)                      # absurdly long template: smallest we have
    _left, top, _right, bottom = draw.textbbox((0, 0), "Ag", font=font)
    return font, (bottom - top) * 1.18


def render_image(lines, colors=None, size=(PANEL_W, PANEL_H)):
    """Black panel, four centered lines, font shrunk until the longest line fits."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, (0, 0, 0))
    draw = ImageDraw.Draw(image)
    colors = colors or [None] * len(lines)
    font, line_h = fit_text(lines, size)

    block = line_h * len(lines)
    y = (size[1] - block) / 2 + line_h / 2
    for text, color in zip(lines, colors):
        draw.text((size[0] / 2, y), text, font=font, anchor="mm",
                  fill=color or (255, 255, 255))
        y += line_h
    return image


def line_colors(stats):
    """Only the score line is colored: green is reassuring, red is honest."""
    color = (90, 230, 120) if stats.score_int >= 8 else \
            (255, 210, 70) if stats.score_int >= 5 else (255, 120, 110)
    return [color] + [None] * 3


class MiniPiTFT:
    """Adafruit 1.14in 240x135 ST7789 on the Pi 5, wired as in Lab 2.

    CS on GPIO5, DC on GPIO25, backlight on GPIO22, SPI0 (spidev0.0 must exist beyond
    the header's CE0: Lab 2 moves CS off CE0 for exactly that reason).
    """

    def __init__(self, rotation=90, baudrate=64_000_000):
        import board
        import digitalio
        import adafruit_rgb_display.st7789 as st7789

        self.disp = st7789.ST7789(
            board.SPI(),
            cs=digitalio.DigitalInOut(board.D5),
            dc=digitalio.DigitalInOut(board.D25),
            rst=None,
            baudrate=baudrate,
            width=135, height=240, x_offset=53, y_offset=40,
        )
        self.rotation = rotation
        self.backlight = digitalio.DigitalInOut(board.D22)
        self.backlight.switch_to_output(value=True)

    def show(self, image):
        self.disp.image(image, self.rotation)

    def off(self):
        self.backlight.value = False


# --------------------------------------------------------------------- display owner

DEFAULT_SCREEN_UNIT = "piscreen.service"          # the boot screen on this machine
DEFAULT_SCREEN_PATTERN = (r"screen_boot_script|screen_clock|stats\.py|image_to_pitft|"
                          r"il9341|st7789")
HOLD_DEFAULT = 120.0


def run(cmd, timeout=20):
    """Run a command and never raise: a missing tool is an answer, not a crash."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def proc_cmdline(pid):
    try:
        raw = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [part.decode(errors="replace") for part in raw.split(b"\0") if part]


def proc_alive(pid):
    """A zombie still has a /proc entry; it cannot be drawing on anything anymore."""
    try:
        state = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return state != "Z"


def pids_matching(pattern):
    regex = re.compile(pattern)
    me = os.getpid()
    return [int(entry.name) for entry in pathlib.Path("/proc").iterdir()
            if entry.name.isdigit() and int(entry.name) != me
            and regex.search(" ".join(proc_cmdline(entry.name)))]


class ScreenOwner:
    """Whatever is drawing on the panel before we arrive, and how to put it back.

    kind "systemd": the right verb is `systemctl stop` - killing the process is pointless
    when the unit says Restart=always, systemd would restart it in the middle of our draw.
    kind "process": the loop is not under systemd, so stop it and relaunch the same argv
    afterwards, detached, from the directory it was running in.
    """

    def __init__(self, kind, target, detail, argv=None, cwd=None):
        self.kind = kind
        self.target = target
        self.detail = detail
        self.argv = argv or []
        self.cwd = cwd

    def __str__(self):
        return self.detail

    def pause(self):
        if self.kind == "systemd":
            answer = run(["sudo", "-n", "systemctl", "stop", self.target])
            okay = bool(answer) and answer.returncode == 0
            print(("paused " if okay else "could not pause ") + self.detail
                  + ("" if okay else f" ({self._why(answer)}); drawing anyway"),
                  file=sys.stderr)
            return okay
        if not self._signal(signal.SIGTERM):
            return False
        for _ in range(50):                       # give it 5 s to close the SPI bus
            if not proc_alive(self.target):
                break
            time.sleep(0.1)
        if proc_alive(self.target):
            self._signal(signal.SIGKILL)
        print(f"paused {self.detail}", file=sys.stderr)
        return True

    def resume(self):
        if self.kind == "systemd":
            answer = run(["sudo", "-n", "systemctl", "start", self.target])
            okay = bool(answer) and answer.returncode == 0
            print(("restored " if okay else "could not restore ") + self.detail
                  + ("" if okay else f" ({self._why(answer)}); "
                     f"run `sudo systemctl start {self.target}`"),
                  file=sys.stderr)
            return okay
        if not self.argv:
            return False
        try:
            subprocess.Popen(self.argv, cwd=self.cwd or "/", stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError as error:
            print(f"could not restore {self.detail}: {error}; run it by hand",
                  file=sys.stderr)
            return False
        print(f"restored {self.detail}", file=sys.stderr)
        return True

    @staticmethod
    def _why(answer):
        if answer is None:
            return "the command could not be run"
        text = (answer.stderr or answer.stdout or "").strip().splitlines()
        return text[-1] if text else f"exit {answer.returncode}"

    def _signal(self, number):
        try:
            os.kill(int(self.target), number)
        except OSError as error:
            print(f"could not signal {self.detail}: {error}", file=sys.stderr)
            return False
        return True


def find_screen_owner(unit=DEFAULT_SCREEN_UNIT, pattern=DEFAULT_SCREEN_PATTERN, exclude=0):
    """The systemd unit first (it is the boot screen here), then any matching process."""
    if unit:
        answer = run(["systemctl", "is-active", unit])
        state = (answer.stdout or "").strip() if answer else ""
        if state == "active":
            return ScreenOwner("systemd", unit, f"systemd unit {unit}")

    for pid in pids_matching(pattern):
        if pid == exclude:
            continue
        argv = proc_cmdline(pid)
        try:
            cwd = str(pathlib.Path(f"/proc/{pid}/cwd").resolve())
        except OSError:
            cwd = "/"
        return ScreenOwner("process", str(pid), f"process {pid} ({' '.join(argv)})",
                           argv=argv, cwd=cwd)
    return None


def install_exit_handlers():
    """Ctrl-C, a closed terminal and `kill` must all put the boot screen back."""
    for signal_name in ("SIGINT", "SIGTERM", "SIGHUP"):
        number = getattr(signal, signal_name, None)
        if number is not None:
            signal.signal(number, lambda *_: sys.exit(0))


def open_display(mode):
    """auto: try, and say why not. on: no display is an error."""
    try:
        return MiniPiTFT()
    except Exception as error:                      # ImportError, no SPI, no panel
        reason = f"{type(error).__name__}: {error}"
        hint = ("install with `uv pip install adafruit-blinka==8.64.0 "
                "adafruit-circuitpython-rgb-display lgpio`")
        if mode == "on":
            raise SystemExit(f"Mini PiTFT not available ({reason}); {hint}")
        print(f"Mini PiTFT not available ({reason}); {hint}\n"
              f"printing the panel text instead", file=sys.stderr)
        return None


def hold_panel(seconds, player=None):
    """Keep our picture on the panel; the owner comes back when this returns.

    The spoken note is allowed to outlast `--hold 0`: giving the panel back before the
    sentence has finished would cut the reveal in half.
    """
    if seconds < 0:
        print("holding the panel until Ctrl-C", file=sys.stderr)
    elif seconds > 0:
        print(f"holding the panel for {human_span(seconds)}", file=sys.stderr)
    deadline = None if seconds < 0 else time.monotonic() + max(0.0, seconds)
    try:
        while True:
            talking = player is not None and player.poll() is None
            if deadline is not None and time.monotonic() >= deadline and not talking:
                return
            time.sleep(0.1)
    except KeyboardInterrupt:
        return


def show(lines, stats, args, player=None):
    """Panel first, then the same text on stdout - the words never differ, only the medium.

    Order matters: the boot screen holds GPIO22 and the SPI chip-select, so it has to stop
    *before* Blinka can open the panel ("GPIO busy" is what happens the other way round).
    The owner is restarted in a `finally:`, so Ctrl-C leaves the Pi as it found it.
    """
    image = render_image(lines, line_colors(stats))
    if args.image:
        image.save(args.image)
        print(f"panel image written to {args.image}", file=sys.stderr)

    owner = None
    if not args.no_display and args.screen == "auto":
        owner = find_screen_owner(args.screen_unit, args.screen_pattern)
        if owner is None:
            print("no display owner is running; the panel is ours", file=sys.stderr)
        else:
            owner.pause()
            time.sleep(0.3)            # let its last frame finish and the bus go quiet

    display = None
    try:
        if not args.no_display:
            display = open_display(args.display)
        if display is not None:
            display.show(image)
            print("panel updated", file=sys.stderr)
            hold_panel(args.hold, player)
    finally:
        if owner:
            owner.resume()

    if display is None:
        print("Mini PiTFT:")
        for line in lines:
            print(f"  {line}")


# -------------------------------------------------------------------------- self test

def self_test():
    """A synthetic night with known percentages, plus the two log vocabularies."""
    import tempfile

    def entry_line(ts, **kw):
        return json.dumps({"t": f"2026-10-29T{ts}", **kw})

    def mouth(ts, state, held):
        mar = None if state in ("user_leave", "unknown") else 0.4
        return json.dumps({"t": f"2026-10-29T{ts}", "reading": f"{state} for {held}s",
                           "mouth": state, "mar": mar, "snoring": state == "open",
                           "threshold": 0.25, "held_s": held})

    night = [
        entry_line("22:00:00", reading="night watch started", event="handoff"),
        mouth("22:00:00", "closed", 600),
        mouth("22:10:00", "open", 300),
        mouth("22:15:00", "closed", 600),
        mouth("22:25:00", "user_leave", 180),
        mouth("22:28:00", "closed", 1320),
        mouth("22:50:00", "unknown", 120),
        mouth("22:52:00", "closed", 480),
        json.dumps({"t": "2026-10-29T22:12:00", "reading": "snore_event 1m",
                    "event": "snore", "dur": 60, "peak_dbfs": -31.0, "mouth": "open",
                    "mar": 0.41}),
        json.dumps({"t": "2026-10-29T22:40:00", "reading": "snore_event 2m",
                    "event": "snore", "dur": 120, "peak_dbfs": -28.5, "mouth": "closed",
                    "mar": 0.02}),
        entry_line("23:00:00", reading="night watch stopped", event="handoff_end"),
        # outside the window: a test run before the night, must not count
        entry_line("19:00:00", reading="night watch started", event="handoff"),
        mouth("19:00:00", "open", 300),
        entry_line("19:05:00", reading="night watch stopped", event="handoff_end"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "night_log.jsonl"
        path.write_text("\n".join(night) + "\n", encoding="utf-8")
        stats = analyze(load(path), path)

        # two handoff windows: the 1 h night and the 5 min test run before it
        assert len(stats.windows) == 2 and round(stats.sleep_s) == 3900, stats.sleep_s
        assert round(stats.open_pct, 2) == round(100 * 600 / 3900, 2), stats.open_pct
        assert round(stats.away_pct, 2) == round(100 * 180 / 3900, 2)
        assert round(stats.unseen_pct, 2) == round(100 * 120 / 3900, 2)
        assert round(stats.snore_pct, 2) == round(100 * 180 / 3900, 2)
        assert stats.snore_events == 2
        assert stats.peak_mar == 0.41 and stats.loudest_dbfs == -28.5
        assert round(stats.open_s) == 600 and round(stats.away_s) == 180

        # --min-session drops the rehearsal, and the percentages follow
        real = analyze(load(path), path, min_session=600)
        assert len(real.windows) == 1 and round(real.sleep_s) == 3600
        assert round(real.open_s) == 300 and round(real.open_pct, 2) == round(100 * 300 / 3600, 2)
        assert round(real.snore_pct, 2) == 5.0
        assert (real.open_pct + real.closed_pct + real.away_pct + real.unseen_pct
                + real.unknown_pct) <= 100.5

        # the score is the documented formula, rounded; caps hold at the extremes
        expected = 10 - (0.15 * stats.snore_pct + 0.06 * stats.open_pct
                         + 0.15 * stats.away_pct + 0.04 * 2)
        assert abs(stats.score - round(max(0.0, expected), 1)) < 0.05, (stats.score, expected)
        assert 0 <= stats.score_int <= 10
        # by hand, for the 1 h night: 0.75 + 0.5 + 0.75 + 0.08 = 2.08 -> 7.92 -> 7.9 / 8
        assert (real.score, real.score_int) == (7.9, 8), (real.score, real.score_int)

        # the four panel lines must fit even at the worst case, 100% everywhere
        worst = ["Your sleep score was 10/10.", "Time spent snoring: 100%",
                 "Time spent with mouth open: 100%", "Time spent out of bed: 100%"]
        worst_font, _ = fit_text(worst)
        assert worst_font.size >= 10, worst_font.size

        lines = display_lines(stats)
        assert len(lines) == 4
        assert lines[0].startswith("Your sleep score was ") and lines[0].endswith("/10.")
        assert lines[1].startswith("Time spent snoring: ") and lines[1].endswith("%")
        assert "mouth open" in lines[2] and "out of bed" in lines[3]

        report = render_report(stats, DEFAULT_TEMPLATE)
        for needle in (f"{stats.score_int}/10", "possible snoring", "Not a diagnosis"):
            assert needle in report, needle
        assert render_report(stats, "# a comment\n{score}/10") == f"{stats.score_int}/10"

        image = render_image(lines, line_colors(stats), size=(PANEL_W, PANEL_H))
        assert image.size == (PANEL_W, PANEL_H) and image.getpixel((0, 0)) == (0, 0, 0)

        # the panel layout: every line fits at the size the fitter picked
        from PIL import Image, ImageDraw
        draw = ImageDraw.Draw(Image.new("RGB", (PANEL_W, PANEL_H)))
        font, line_h = fit_text(lines)
        widths = [draw.textbbox((0, 0), text, font=font)[2] for text in lines]
        assert max(widths) <= PANEL_W - 2 * PANEL_MARGIN, max(widths)
        assert line_h * len(lines) <= PANEL_H - 2 * PANEL_MARGIN, line_h
        # template errors are caught with a helpful message
        try:
            render_report(stats, "{nope}")
        except SystemExit as error:
            assert "unknown field" in str(error)
        else:
            raise AssertionError("template with an unknown field should fail")

        # old change-only logs (overnight.py) get durations from the next line
        legacy = pathlib.Path(tmp) / "legacy.jsonl"
        legacy.write_text("\n".join([
            entry_line("21:00:00", reading="nobody"),
            entry_line("21:10:00", reading="person supine"),
            entry_line("21:20:00", reading="nobody"),
        ]) + "\n", encoding="utf-8")
        old = analyze(load(legacy), legacy)
        assert round(old.sleep_s) == 1200, old.sleep_s
        assert round(old.away_pct, 1) == 50.0, old.away_pct
        assert round(old.unknown_pct, 1) == 50.0, old.unknown_pct   # "person supine"
        assert old.snore_events == 0 and old.score_int == 8   # half the log: out of view

        # an `alive` heartbeat repeats the state it last saw; it must not double count
        beat_path = pathlib.Path(tmp) / "alive.jsonl"
        beat_path.write_text("\n".join([
            entry_line("23:00:00", reading="night watch started", event="handoff"),
            mouth("23:00:00", "closed", 1200),
            json.dumps({"t": "2026-10-29T23:05:00", "alive": True, "mouth": "closed"}),
            json.dumps({"t": "2026-10-29T23:10:00", "alive": True, "mouth": "closed"}),
            entry_line("23:20:00", reading="night watch stopped", event="handoff_end"),
        ]) + "\n", encoding="utf-8")
        beat = analyze(load(beat_path), beat_path)
        assert round(beat.sleep_s) == 1200
        assert round(beat.closed_pct, 1) == 100.0, beat.closed_pct
        mouth_total = beat.open_pct + beat.closed_pct + beat.away_pct + beat.unseen_pct \
            + beat.unknown_pct
        assert mouth_total <= 100.5, mouth_total

        # the display owner: pause a plain process, then put the same command back
        victim = subprocess.Popen(["sleep", "308.25"])
        revived = []
        try:
            owner = find_screen_owner(unit="", pattern=r"sleep\s+308\.25")
            assert owner is not None and owner.kind == "process", owner
            assert owner.pause() is True
            assert victim.wait(timeout=5) is not None      # it really stopped
            assert pids_matching(r"sleep\s+308\.25") == []
            assert owner.resume() is True
            time.sleep(0.5)
            revived = pids_matching(r"sleep\s+308\.25")
            assert revived, "the owner should be running again"
        finally:
            victim.poll()
            for pid in pids_matching(r"sleep\s+308\.25"):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        # a command that is not installed is an answer, not a traceback
        assert run(["definitely-not-a-command"]) is None

        # --- the spoken note: deterministic fallback, cleanup, and the grounding gate
        draft = fallback_narrative(stats)
        assert draft.count(".") >= 3, draft
        assert f"{stats.score_int} out of 10" in draft
        assert "diagnos" not in draft.lower()

        # 3-4 sentences, no model furniture, always ends with punctuation
        messy = "**Here you go:**\n- Your score was 6 out of 10.\n- One. Two. Three. Four. Five."
        cleaned = clean_narrative(messy)
        assert cleaned.startswith("Here you go:"), cleaned
        assert cleaned.count(". ") <= 3 and cleaned.endswith("."), cleaned
        assert clean_narrative("") == ""
        once = clean_narrative("Your score was 6 out of 10. Your score was 6 out of 10. "
                               "You were out of view for 2h11m.")
        assert once.count("6 out of 10") == 1, once        # no repeated sentences

        # grounding: numbers from the night pass, invented ones do not
        good = (f"Your score was {stats.score_int} out of 10 after "
                f"{human_span(stats.sleep_s)} of watching, with possible snoring about "
                f"{stats.snore_pct:.0f}% of the night in {stats.snore_events} clips, and "
                f"your mouth open {stats.open_pct:.0f}% of the time. You were out of view "
                f"for {human_span(stats.away_s)}.")
        assert unsupported_claims(good, stats) == [], unsupported_claims(good, stats)
        # NB: a quantity gate cannot know *which* fact a number belongs to, so it only
        # rejects numbers the night does not contain at all (the real 7h24m night did
        # catch "almost an hour" for 2h11m, because 1 h is not in that night's numbers).
        for bad, phrase in (("You were out of view for almost three hours.", "three hours"),
                            ("Your mouth was open for twenty minutes.", "twenty minutes"),
                            ("You snored in five clips.", "five clips"),
                            (f"Your score was {stats.score_int + 1} out of 10.",
                             f"{stats.score_int + 1} out of 10"),
                            ("I watched from 23:10 to 04:00.", "23:10")):
            assert phrase in unsupported_claims(bad, stats), (bad, unsupported_claims(bad, stats))

        # the prompt carries the log, the numbers and the template's own draft
        lines = digest(entries=load(path), windows=stats.windows)
        assert 0 < len(lines) <= 40, len(lines)
        assert any("night watch started" in line for line in lines), lines[:3]
        prompt = build_prompt(stats, "REPORT-BODY", lines, draft)
        assert "REPORT-BODY" in prompt and draft in prompt and "FACTS" in prompt
        assert f"{stats.score_int}/10" in prompt and lines[0] in prompt
        assert "3 or 4 short sentences" in prompt

    print("self-test passed: percentages, score, template, panel layout and "
          "display handover all agree")


# ----------------------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Score a night_log.jsonl and put the summary on the Mini PiTFT.")
    parser.add_argument("--log", help="night_log.jsonl (default: newest under logs/)")
    parser.add_argument("--template", help="report template string, str.format style")
    parser.add_argument("--template-file", help="read the template from this file")
    parser.add_argument("--min-session", type=float, default=0.0,
                        help="ignore handoff windows shorter than this many seconds")
    parser.add_argument("--explain", action="store_true", help="print the score breakdown")
    parser.add_argument("--json", action="store_true", help="print the stats as JSON")
    parser.add_argument("--image", help="write the rendered panel to this PNG")
    parser.add_argument("--display", choices=("auto", "on"), default="auto",
                        help="auto: fall back to text if the panel is missing (default)")
    parser.add_argument("--no-display", action="store_true", help="never touch the panel")
    parser.add_argument("--hold", type=float, default=HOLD_DEFAULT,
                        help=f"keep the panel up this many seconds (default {HOLD_DEFAULT:g}); "
                             f"-1 = until Ctrl-C, 0 = draw and give it back")
    parser.add_argument("--screen", choices=("auto", "none"), default="auto",
                        help="auto: pause whatever is drawing on the panel (the boot "
                             "screen) and restart it when done (default); none: draw over it")
    parser.add_argument("--screen-unit", default=DEFAULT_SCREEN_UNIT,
                        help=f"systemd unit to take the panel from (default "
                             f"{DEFAULT_SCREEN_UNIT}; empty string = processes only)")
    parser.add_argument("--screen-pattern", default=DEFAULT_SCREEN_PATTERN,
                        help="regex for a non-systemd process drawing on the panel")
    parser.add_argument("--model", default="qwen3.5:0.8b",
                        help="Ollama model for the spoken note (default qwen3.5:0.8b)")
    parser.add_argument("--model-timeout", type=float, default=600,
                        help="seconds to wait for the model (default 600)")
    parser.add_argument("--no-narrate", action="store_true",
                        help="skip the model: print the template's own wording instead")
    parser.add_argument("--speak", action=argparse.BooleanOptionalAction, default=True,
                        help="read the note out loud through the speakers (default on)")
    parser.add_argument("--voice", default=VOICE_MODEL,
                        help=f"Piper voice in --voice-dir (default {VOICE_MODEL})")
    parser.add_argument("--voice-dir", default=str(VOICE_DIR),
                        help=f"where the Piper .onnx lives (default {VOICE_DIR})")
    parser.add_argument("--length-scale", type=float, default=1.05,
                        help="Piper pace: 1.0 normal, 1.1 slower (default 1.05)")
    parser.add_argument("--narrative-wav",
                        help="keep the spoken note as this WAV (default: a temp file)")
    parser.add_argument("--self-test", action="store_true", help="run the built-in checks")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0
    install_exit_handlers()            # Ctrl-C or `kill` must return the panel

    path = pathlib.Path(args.log) if args.log else default_log()
    if not path.exists():
        raise SystemExit(f"no such log: {path}")
    entries = load(path)
    if not entries:
        raise SystemExit(f"{path} holds no readings - nothing to report")

    print(f"reading {path}", file=sys.stderr)
    stats = analyze(entries, path, min_session=args.min_session)

    # Two passes over one template: the first (numbers only) is the context Qwen reads, the
    # second is the report the person sees and the machine says out loud.
    template = read_template(args)
    draft = render_report(stats, template).rstrip()
    narrative, source = narrate(stats, draft, entries, args)
    report = render_report(stats, template, narrative, source).rstrip()

    print(report)
    if args.explain:
        print("\n" + explain(stats))
    if args.json:
        payload = stats.as_dict()
        payload.update({"narrative": narrative, "narrative_source": source})
        print(json.dumps(payload, indent=2))

    player = start_speech(narrative, args)
    print()
    try:
        show(display_lines(stats), stats, args, player)
    finally:
        stop_speech(player)
    return 0


if __name__ == "__main__":
    sys.exit(main())
