#!/usr/bin/env python3
"""Add Mini PiTFT ratings to alien_speak.py, preserving its existing persona.

Run this from your speech-scripts directory:
    python add_sphinx_display.py
A dated backup is created before the script is changed.
"""

import argparse
import ast
from datetime import datetime
from pathlib import Path
import shutil
import stat
import tempfile

HELPER_SOURCE = '"""Drawing-score display for the rectangular Adafruit 1.14-inch Mini PiTFT.\n\nHardware configuration follows Adafruit\'s Mini PiTFT Python examples:\nhttps://learn.adafruit.com/adafruit-mini-pitft-135x240-color-tft-add-on-for-raspberry-pi/python-stats\n"""\n\nimport math\nimport re\nimport sys\nfrom pathlib import Path\n\nRATING_PATTERN = re.compile(\n    r"\\bI rate this drawing\\s+(zero|one|two|three|four|five|[0-5])\\s+out of\\s+(?:5|five)\\b",\n    re.IGNORECASE,\n)\nNUMBER_WORDS = dict(zip((\'zero\', \'one\', \'two\', \'three\', \'four\', \'five\'), range(6)))\n\n\ndef extract_rating(reply):\n    match = RATING_PATTERN.search(reply)\n    if match is None:\n        return None\n    token = match.group(1).lower()\n    return int(token) if token.isdigit() else NUMBER_WORDS[token]\n\n\ndef load_font(size):\n    from PIL import ImageFont\n    for name in (\n        \'/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf\',\n        \'/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf\',\n    ):\n        if Path(name).is_file():\n            return ImageFont.truetype(name, size)\n    return ImageFont.load_default()\n\n\ndef render_screen(rating=None, status=\'Listening\'):\n    """Make a landscape 240x135 image; also usable for previews without a Pi."""\n    from PIL import Image, ImageDraw\n    image = Image.new(\'RGB\', (240, 135), \'#10131c\')\n    draw = ImageDraw.Draw(image)\n    draw.text((10, 4), \'SPHINX\', font=load_font(17), fill=\'#e6c16c\')\n    draw.line((10, 29, 230, 29), fill=\'#343a4d\')\n    if rating is None:\n        draw.text((10, 37), \'AWAITING ART\', font=load_font(22), fill=\'white\')\n        draw.text((10, 75), \'Hold up your drawing.\', font=load_font(13), fill=\'#b1b7c8\')\n        draw.text((10, 94), \'Say: check my drawing\', font=load_font(13), fill=\'#b1b7c8\')\n    else:\n        draw.text((10, 32), \'DRAWING\', font=load_font(15), fill=\'#b1b7c8\')\n        draw.text((146, 27), f\'{rating}/5\', font=load_font(34), fill=\'white\')\n        for index in range(5):\n            points = []\n            for vertex in range(10):\n                angle = -math.pi / 2 + vertex * math.pi / 5\n                radius = 10 if vertex % 2 == 0 else 4.5\n                points.append((25 + index * 43 + math.cos(angle) * radius,\n                               81 + math.sin(angle) * radius))\n            color = \'#e6c16c\' if index < rating else \'#343a4d\'\n            draw.polygon(points, fill=color)\n        passed = rating >= 3\n        draw.text((10, 98), \'PASSED\' if passed else \'TRY AGAIN\',\n                  font=load_font(13), fill=\'#8ae3af\' if passed else \'#f09d86\')\n    draw.text((10, 119), str(status)[:30].upper(), font=load_font(10), fill=\'#b1b7c8\')\n    return image\n\n\nclass MiniPiTFT:\n    def __init__(self):\n        self.display = None\n        self.rating = None\n        self.status = \'Starting\'\n        self.spi = None\n        self.cs = None\n        self.dc = None\n        self.backlight = None\n        try:\n            if not Path(\'/dev/spidev0.0\').exists():\n                raise RuntimeError(\n                    \'/dev/spidev0.0 is unavailable. Enable SPI, or check whether \'\n                    \'a PiTFT console/kernel driver already controls the screen.\'\n                )\n            import board\n            import digitalio\n            from adafruit_rgb_display import st7789\n            self.spi = board.SPI()\n            self.cs = digitalio.DigitalInOut(board.CE0)\n            self.dc = digitalio.DigitalInOut(board.D25)\n            self.display = st7789.ST7789(\n                self.spi, cs=self.cs, dc=self.dc, rst=None,\n                baudrate=24000000, width=135, height=240,\n                x_offset=53, y_offset=40,\n            )\n            self.backlight = digitalio.DigitalInOut(board.D22)\n            self.backlight.switch_to_output(value=True)\n            self.refresh()\n        except Exception as error:\n            print(f\'Mini PiTFT disabled: {error}\', file=sys.stderr)\n            self.close()\n\n    def refresh(self):\n        if self.display is None:\n            return\n        try:\n            self.display.image(render_screen(self.rating, self.status), rotation=90)\n        except Exception as error:\n            print(f\'Mini PiTFT update failed: {error}\', file=sys.stderr)\n            self.close()\n\n    def set_status(self, status):\n        # Keep the last rating visible through Speaking and Listening updates.\n        self.status = status\n        self.refresh()\n\n    def show_reply(self, reply):\n        if reply.lstrip().startswith(\'I am the Sphinx\'):\n            self.rating = None\n        score = extract_rating(reply)\n        if score is not None:\n            self.rating = score\n        self.refresh()\n\n    def close(self):\n        self.display = None\n        for device in (self.backlight, self.dc, self.cs, self.spi):\n            if device is not None:\n                try:\n                    device.deinit()\n                except Exception:\n                    pass\n        self.backlight = self.dc = self.cs = self.spi = None\n'
MARKER = '# SPHINX_MINIPITFT_RATING_V1'
SCORE_PROMPT = """

Drawing ratings for the attached Mini PiTFT screen:
Whenever you judge a clearly visible drawing, begin your spoken response
with exactly: "I rate this drawing N out of 5." Replace N with one digit
from 0 to 5. Then give brief feedback in your Sphinx voice.
This exact spoken sentence also supplies the screen's rating.
Rate only the current drawing trial against its requested object.
Use 0 for unrelated marks, 1 for a weak attempt, 2 for a partly recognizable
attempt, 3 for a recognizable drawing, 4 for a clear drawing with relevant
details, and 5 for an especially clear, detailed drawing. Simple uncolored
sketches can pass. Scores of 3, 4, or 5 pass the drawing trial; scores below
3 require a retry. Do not advance to the next trial after a score below 3.
If there is no clear drawing visible or no usable camera image, ask for a
clearer view and do not give a numeric rating. Do not rate spoken riddle
answers. Never supply an example rating sentence while explaining the game.
"""


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f'Cannot safely find this section exactly once: {old.strip()!r}')
    return source.replace(old, new, 1)


def patched_source(source):
    ast.parse(source)
    if MARKER in source:
        return source
    tree = ast.parse(source)
    if not any(isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == 'FRIENDLY_PROMPT'
        for target in node.targets
    ) for node in tree.body):
        raise ValueError('FRIENDLY_PROMPT was not found. No changes were made.')
    source = replace_once(source, 'if hasattr(sys.stdout, "reconfigure"):',
                          'from sphinx_display import MiniPiTFT\n\nif hasattr(sys.stdout, "reconfigure"):')
    source = replace_once(source, 'app = Flask(__name__)',
                          MARKER + '\nmini_screen = None\n'
                          + 'FRIENDLY_PROMPT += ' + repr(SCORE_PROMPT)
                          + '\n\napp = Flask(__name__)')
    source = replace_once(source, '        status = new_status\n',
                          '        status = new_status\n'
                          + '    if mini_screen is not None:\n'
                          + '        mini_screen.set_status(new_status)\n')
    source = replace_once(source, '    def say(self, text: str) -> float:\n',
                          '    def say(self, text: str) -> float:\n'
                          + '        if mini_screen is not None:\n'
                          + '            mini_screen.show_reply(text)\n')
    source = replace_once(source, '    args = parser.parse_args()\n',
                          '    args = parser.parse_args()\n\n'
                          + '    global mini_screen\n'
                          + '    mini_screen = MiniPiTFT()\n'
                          + '    atexit.register(mini_screen.close)\n')
    compile(source, 'alien_speak.py', 'exec')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path, default=Path('alien_speak.py'))
    args = parser.parse_args()
    target = args.script.resolve()
    if not target.is_file():
        raise SystemExit('Run this from speech-scripts, beside alien_speak.py.')
    source = target.read_text(encoding='utf-8')
    try:
        result = patched_source(source)
    except (ValueError, SyntaxError) as error:
        raise SystemExit(f'{error} Your existing script was not changed.') from error
    helper_path = target.parent / 'sphinx_display.py'
    if helper_path.exists() and helper_path.read_text(encoding='utf-8') != HELPER_SOURCE:
        raise SystemExit('sphinx_display.py already exists with different content. No changes were made.')
    if result == source:
        helper_path.write_text(HELPER_SOURCE, encoding='utf-8')
        print('Mini PiTFT integration is already installed.')
        return
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = target.with_name(f'{target.stem}.before_pitft_{stamp}.py')
    shutil.copy2(target, backup)
    helper_path.write_text(HELPER_SOURCE, encoding='utf-8')
    # Preserve script permissions while replacing the file atomically.
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                                     prefix='sphinx-install-', delete=False) as temporary:
        temporary.write(result)
        temporary_path = Path(temporary.name)
    temporary_path.chmod(stat.S_IMODE(target.stat().st_mode))
    temporary_path.replace(target)
    print(f'Installed. Original script saved as {backup.name}')
    print('Run: python alien_speak.py --no-fisheye')
    print('For a standalone display test: python -c "from sphinx_display import MiniPiTFT; '
          'd=MiniPiTFT(); d.show_reply(\"I rate this drawing 4 out of 5.\"); d.set_status(\"Speaking\")"')


if __name__ == '__main__':
    main()
