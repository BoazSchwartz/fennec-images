#!/usr/bin/env python3
"""Draw the app icon into assets/ -- the colored plate the app wears (copied from
fennec-bookkeeping scripts/make_icons.py, same drawing, its own plate color).

Run once, or again after changing the drawing; the .ico files are committed, so
nothing at start-up depends on PIL being installed. Both plates carry the same
dark-gray F (Fennec); what tells the Fennec windows apart at a glance on the taskbar
is the PLATE COLOR -- IT green, Business light blue, Personal pink, Digital orange,
Investment violet, and Images a SUNSET: golden, coral, deep rose, run diagonally from the
top-left corner, the golden-hour light of a good photo. The only plate of the family
with more than one hue, so it is never mistaken for another.

Every size is drawn at its own resolution rather than scaled from one big image:
a rounded corner laid straight onto a 16 px grid is a staircase, so the plate is
drawn eight times oversized and reduced once, while the letter is rendered by the
font at the size actually shown, since a 16 px letter reduced from a 256 px one
is a smudge.

    py -3 scripts\make_icons.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont

from shared.config import RepoPaths

# (file name, letter, gradient stops from the top-left corner to the bottom-right)
SUNSET = ((253, 224, 71), (251, 146, 120), (225, 29, 72))   # golden, coral, deep rose
ICONS = (
    (RepoPaths.FILE_ICON_IMAGES, 'F', SUNSET),
)
# The dark gray F every Fennec project wears
LETTER_COLOR = (55, 65, 81, 255)
# every size Windows asks for: title bar at 16, taskbar at 24, alt-tab at 32,
# the desktop at 48, and the same list again scaled for a 125-200 % screen
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
PREVIEW_SIZE = 256
SS = 8               # oversampling used for the plate
RADIUS = 0.22        # corner radius of the rounded square, as a fraction of the side
FONT = 0.74          # letter em size as a fraction of the side
NUDGE_Y = -0.012     # optical centring: a capital sits slightly high


def _letter_font(size: int):
    """The heaviest of the usual Windows faces that is actually installed."""
    for name in ('seguibl.ttf', 'segoeuib.ttf', 'arialbd.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _pad(side: int) -> int:
    """No gap at the sizes where every pixel counts, a hair of one above them."""
    return 0 if side <= 32 else round(side * 0.031)


def _color_at(stops, t: float) -> tuple:
    """The gradient's color at t in 0..1, linear between equally spaced stops."""
    k = min(len(stops) - 2, int(t * (len(stops) - 1)))
    u = t * (len(stops) - 1) - k
    return tuple(round(a + (b - a) * u) for a, b in zip(stops[k], stops[k + 1])) + (255,)


def _plate(side: int, stops) -> Image.Image:
    """The diagonal gradient rounded square, drawn at side*SS and reduced once."""
    n = side * SS
    line = Image.new('RGBA', (2 * n - 1, 1))
    for i in range(2 * n - 1):
        line.putpixel((i, 0), _color_at(stops, i / (2 * n - 2)))
    # a pixel's diagonal position is x + y, so row y is the strip read from y on
    grad = Image.new('RGBA', (n, n))
    strip = line
    for y in range(n):
        grad.paste(strip.crop((y, 0, y + n, 1)), (0, y))
    pad = _pad(side) * SS
    mask = Image.new('L', (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, n - 1 - pad, n - 1 - pad],
                                           radius=round(n * RADIUS), fill=255)
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    img.paste(grad, mask=mask)
    return img.resize((side, side), Image.LANCZOS)


def draw(side: int, letter: str, stops) -> Image.Image:
    """One icon at its own resolution -- never a scaled copy of a bigger one."""
    img = _plate(side, stops)
    pen = ImageDraw.Draw(img)
    font = _letter_font(max(6, round(side * FONT)))
    left, top_, right, bottom_ = pen.textbbox((0, 0), letter, font=font)
    x = round((side - (right - left)) / 2 - left)
    y = round((side - (bottom_ - top_)) / 2 - top_ + side * NUDGE_Y)
    pen.text((x, y), letter, font=font, fill=LETTER_COLOR)
    return img


def run() -> bool:
    RepoPaths.path_dir_assets.mkdir(parents=True, exist_ok=True)
    for name, letter, stops in ICONS:
        path_ico = RepoPaths.path_dir_assets / name
        images = [draw(s, letter, stops) for s in ICO_SIZES]
        # append_images is what puts each hand-drawn size in, instead of PIL scaling one
        images[-1].save(path_ico, format='ICO', sizes=[(s, s) for s in ICO_SIZES],
                        append_images=images[:-1])
        path_png = path_ico.with_name(path_ico.stem + '-preview.png')
        draw(PREVIEW_SIZE, letter, stops).save(path_png)
        print('wrote %s (%d sizes) and %s' % (path_ico, len(ICO_SIZES), path_png.name))
    return True


if __name__ == '__main__':
    run()
