"""Drawing-score display for the rectangular Adafruit 1.14-inch Mini PiTFT.

Hardware configuration follows Adafruit's Mini PiTFT Python examples:
https://learn.adafruit.com/adafruit-mini-pitft-135x240-color-tft-add-on-for-raspberry-pi/python-stats
"""

import math
import re
import sys
from pathlib import Path

RATING_PATTERN = re.compile(
    r"\bI rate this drawing\s+(zero|one|two|three|four|five|[0-5])\s+out of\s+(?:5|five)\b",
    re.IGNORECASE,
)
NUMBER_WORDS = dict(zip(('zero', 'one', 'two', 'three', 'four', 'five'), range(6)))


def extract_rating(reply):
    match = RATING_PATTERN.search(reply)
    if match is None:
        return None
    token = match.group(1).lower()
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def load_font(size):
    from PIL import ImageFont
    for name in (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    ):
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def render_screen(rating=None, status='Listening'):
    """Make a landscape 240x135 image; also usable for previews without a Pi."""
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (240, 135), '#10131c')
    draw = ImageDraw.Draw(image)
    draw.text((10, 4), 'SPHINX', font=load_font(17), fill='#e6c16c')
    draw.line((10, 29, 230, 29), fill='#343a4d')
    if rating is None:
        draw.text((10, 37), 'AWAITING ART', font=load_font(22), fill='white')
        draw.text((10, 75), 'Hold up your drawing.', font=load_font(13), fill='#b1b7c8')
        draw.text((10, 94), 'Say: check my drawing', font=load_font(13), fill='#b1b7c8')
    else:
        draw.text((10, 32), 'DRAWING', font=load_font(15), fill='#b1b7c8')
        draw.text((146, 27), f'{rating}/5', font=load_font(34), fill='white')
        for index in range(5):
            points = []
            for vertex in range(10):
                angle = -math.pi / 2 + vertex * math.pi / 5
                radius = 10 if vertex % 2 == 0 else 4.5
                points.append((25 + index * 43 + math.cos(angle) * radius,
                               81 + math.sin(angle) * radius))
            color = '#e6c16c' if index < rating else '#343a4d'
            draw.polygon(points, fill=color)
        passed = rating >= 3
        draw.text((10, 98), 'PASSED' if passed else 'TRY AGAIN',
                  font=load_font(13), fill='#8ae3af' if passed else '#f09d86')
    draw.text((10, 119), str(status)[:30].upper(), font=load_font(10), fill='#b1b7c8')
    return image


class MiniPiTFT:
    def __init__(self):
        self.display = None
        self.rating = None
        self.status = 'Starting'
        self.spi = None
        self.cs = None
        self.dc = None
        self.backlight = None
        try:
            if not Path('/dev/spidev0.0').exists():
                raise RuntimeError(
                    '/dev/spidev0.0 is unavailable. Enable SPI, or check whether '
                    'a PiTFT console/kernel driver already controls the screen.'
                )
            import board
            import digitalio
            from adafruit_rgb_display import st7789
            self.spi = board.SPI()
            self.cs = digitalio.DigitalInOut(board.D5)
            self.dc = digitalio.DigitalInOut(board.D25)
            self.display = st7789.ST7789(
                self.spi, cs=self.cs, dc=self.dc, rst=None,
                baudrate=24000000, width=135, height=240,
                x_offset=53, y_offset=40,
            )
            self.backlight = digitalio.DigitalInOut(board.D22)
            self.backlight.switch_to_output(value=True)
            self.refresh()
        except Exception as error:
            print(f'Mini PiTFT disabled: {error}', file=sys.stderr)
            self.close()

    def refresh(self):
        if self.display is None:
            return
        try:
            self.display.image(render_screen(self.rating, self.status), rotation=90)
        except Exception as error:
            print(f'Mini PiTFT update failed: {error}', file=sys.stderr)
            self.close()

    def set_status(self, status):
        # Keep the last rating visible through Speaking and Listening updates.
        self.status = status
        self.refresh()

    def show_reply(self, reply):
        if reply.lstrip().startswith('I am the Sphinx'):
            self.rating = None
        score = extract_rating(reply)
        if score is not None:
            self.rating = score
        self.refresh()

    def close(self):
        self.display = None
        for device in (self.backlight, self.dc, self.cs, self.spi):
            if device is not None:
                try:
                    device.deinit()
                except Exception:
                    pass
        self.backlight = self.dc = self.cs = self.spi = None
