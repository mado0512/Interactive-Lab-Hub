import math
import random
import shutil
import subprocess
import time
from datetime import datetime

import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789


cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)
backlight = digitalio.DigitalInOut(board.D22)
button_a = digitalio.DigitalInOut(board.D23)
button_b = digitalio.DigitalInOut(board.D24)

backlight.switch_to_output(value=True)
button_a.switch_to_input(pull=digitalio.Pull.UP)
button_b.switch_to_input(pull=digitalio.Pull.UP)

disp = st7789.ST7789(
    board.SPI(),
    cs=cs_pin,
    dc=dc_pin,
    rst=None,
    baudrate=64_000_000,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)

width, height = 240, 135
scale = 3
image = Image.new("RGB", (width * scale, height * scale))
draw = ImageDraw.Draw(image)

font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
font_number = ImageFont.truetype(bold_path, 9 * scale)
font_time = ImageFont.truetype(bold_path, 15 * scale)
font_date = ImageFont.truetype(font_path, 7 * scale)
font_label = ImageFont.truetype(font_path, 6 * scale)
speech_command = shutil.which("espeak-ng") or shutil.which("espeak")

paused = False
sound_enabled = True
paused_time = datetime.now()
paused_since = None
last_button_time = 0.0
last_spoken_minute = None


def speak_time(now):
    if not sound_enabled or not speech_command:
        return
    try:
        subprocess.Popen(
            [speech_command, "-a", "200", "-s", "145", f"The time is {now.strftime('%I:%M %p')}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def speak_stop_message():
    if not sound_enabled or not speech_command:
        return
    try:
        subprocess.Popen(
            [speech_command, "-a", "200", "-s", "145", "Detected doom scrolling, time stopped moving!"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def point(cx, cy, radius, angle):
    radians = math.radians(angle - 90)
    return cx + math.cos(radians) * radius, cy + math.sin(radians) * radius


def centered_text(text, center_x, top, font, fill):
    bounds = draw.textbbox((0, 0), text, font=font)
    draw.text((center_x - (bounds[2] - bounds[0]) / 2, top), text, font=font, fill=fill)


def stop_hand_offset(stop_elapsed):
    if not paused:
        return 0.0

    opening_pulls = (
        (0.05, 0.55, 0.90), (0.18, 0.48, 0.72), (0.31, 0.42, 0.58),
        (0.44, 0.36, 0.46), (0.56, 0.31, 0.36), (0.67, 0.28, 0.28),
    )
    pull = next((item for item in opening_pulls if item[0] <= stop_elapsed <= item[0] + item[1]), None)
    if pull is None and stop_elapsed >= 1.0:
        index = int(stop_elapsed - 1.0)
        reach = 0.30 + 0.10 * math.sin(index * 0.85) + 0.04 * math.sin(index * 2.7)
        if index % 9 == 0:
            reach += 0.16
        pull = (1.0 + index, 0.62, max(0.18, reach))
    if pull is None:
        return 0.0
    start, duration, reach = pull
    progress = max(0.0, min(1.0, (stop_elapsed - start) / duration))
    return 6.0 * reach * math.sin(math.pi * progress)


def draw_clock(now, stop_elapsed):
    s = scale
    dark = (25, 27, 31)
    red = (214, 43, 43)
    draw.rectangle((0, 0, width * s, height * s), fill=(10, 12, 17))
    draw.ellipse((2 * s, 2 * s, 132 * s, 132 * s), fill=(20, 23, 30))

    cx, cy, radius = 67 * s, 67 * s, 53 * s
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=(247, 245, 239), outline=(43, 43, 43), width=3 * s,
    )

    for tick_index in range(60):
        outer = point(cx, cy, radius - 4 * s, tick_index * 6)
        inner_radius = radius - (8 * s if tick_index % 5 == 0 else 6 * s)
        inner = point(cx, cy, inner_radius, tick_index * 6)
        draw.line((*outer, *inner), fill=dark, width=2 * s if tick_index % 5 == 0 else s)

    for number in range(1, 13):
        x, y = point(cx, cy, radius - 15 * s, number * 30)
        bounds = draw.textbbox((0, 0), str(number), font=font_number)
        draw.text(
            (x - (bounds[2] - bounds[0]) / 2, y - (bounds[3] - bounds[1]) / 2 - s),
            str(number), font=font_number, fill=dark,
        )

    hour_angle = (now.hour % 12 + now.minute / 60) * 30
    minute_angle = (now.minute + now.second / 60) * 6
    second_angle = (now.second + now.microsecond / 1_000_000) * 6
    for angle, hand_radius, hand_width, color in (
        (hour_angle, 26 * s, 4 * s, dark),
        (minute_angle, 38 * s, 3 * s, dark),
        (second_angle + stop_hand_offset(stop_elapsed), 43 * s, 2 * s, red),
    ):
        draw.line((cx, cy, *point(cx, cy, hand_radius, angle)), fill=color, width=hand_width)

    draw.ellipse((cx - 4 * s, cy - 4 * s, cx + 4 * s, cy + 4 * s), fill=(35, 38, 43))
    draw.ellipse((cx - s, cy - s, cx + s, cy + s), fill=red)

    centered_text("REAL TIME", 188 * s, 32 * s, font_label, (155, 164, 177))
    centered_text(now.strftime("%H:%M:%S"), 188 * s, 45 * s, font_time, (238, 242, 248))
    centered_text(now.strftime("%Y-%m-%d"), 188 * s, 66 * s, font_date, (155, 164, 177))
    centered_text("STOPPED" if paused else "RUNNING", 188 * s, 94 * s, font_label, red if paused else (105, 115, 130))
    centered_text("SOUND ON" if sound_enabled else "SOUND OFF", 188 * s, 103 * s, font_label, (105, 115, 130))
    if paused:
        centered_text(f"OUT OF SYNC  {int(stop_elapsed // 60):02d}:{int(stop_elapsed % 60):02d}", 188 * s, 84 * s, font_label, (255, 180, 180))
    centered_text("A stop/resume   B sound", 188 * s, 115 * s, font_label, (105, 115, 130))

    if paused:
        for line_y in range(0, height * s, 3 * s):
            draw.rectangle((0, line_y, width * s, line_y + s - 1), fill=(5, 6, 9))
        random.seed(int(stop_elapsed * 12))
        for _ in range(90):
            draw.point(
                (random.randrange(width * s), random.randrange(height * s)),
                fill=random.choice(((90, 100, 115), (120, 70, 75), (35, 55, 70))),
            )
        draw.rectangle((0, 0, width * s - 1, height * s - 1), outline=(2, 3, 5), width=3 * s)
        draw.rectangle((4 * s, 4 * s, width * s - 5 * s, height * s - 5 * s), outline=(70, 76, 85), width=s)

    disp.image(image.resize((width, height), Image.Resampling.LANCZOS), 90)


try:
    while True:
        current_time = time.monotonic()
        if current_time - last_button_time > 0.25:
            if not button_a.value:
                paused = not paused
                paused_since = time.monotonic() if paused else None
                if not paused:
                    last_spoken_minute = None
                else:
                    speak_stop_message()
                last_button_time = current_time
            elif not button_b.value:
                sound_enabled = not sound_enabled
                last_button_time = current_time

        if paused:
            stop_elapsed = time.monotonic() - paused_since
            display_time = paused_time
        else:
            paused_time = datetime.now()
            display_time = paused_time
            stop_elapsed = 0.0
            spoken_minute = paused_time.strftime("%Y-%m-%d %H:%M")
            if spoken_minute != last_spoken_minute:
                speak_time(paused_time)
                last_spoken_minute = spoken_minute

        draw_clock(display_time, stop_elapsed)
        time.sleep(0.05)
finally:
    backlight.value = False
