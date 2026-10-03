"""Generate a synthetic photo library for testing the album tool.

Creates JPEGs with EXIF capture dates and GPS, grouped into several
"events" on different days/places, including burst duplicates, a few
blurry shots and a few under-exposed ones.

  py -3 tools/make_demo_photos.py demo_photos --count 90 --seed 3
"""
from __future__ import annotations

import argparse
import math
import os
import random
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFilter
from PIL.TiffImagePlugin import IFDRational

PLACES = {
    "beach": (32.0853, 34.7818),
    "old city": (31.7767, 35.2345),
    "mountain": (32.7940, 34.9896),
    "park": (32.0700, 34.8240),
}
PALETTES = [
    [(255, 196, 120), (255, 120, 90), (80, 60, 120)],      # sunset
    [(135, 206, 250), (255, 255, 255), (60, 120, 60)],     # clear day
    [(40, 40, 70), (90, 90, 140), (230, 230, 120)],        # night
    [(200, 220, 240), (180, 180, 180), (120, 90, 60)],     # overcast
    [(255, 240, 200), (120, 190, 240), (230, 140, 60)],    # bright beach
]
SIZES = [(1600, 1200), (1200, 1600), (1800, 1200), (1200, 1800), (1600, 900), (1400, 1400)]


def _deg_to_dms(value: float):
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = (value - d - m / 60) * 3600
    return (IFDRational(d, 1), IFDRational(m, 1), IFDRational(int(s * 100), 100))


def make_exif(dt: datetime, lat: float, lon: float) -> bytes:
    exif = Image.Exif()
    stamp = dt.strftime("%Y:%m:%d %H:%M:%S")
    exif[0x0132] = stamp
    sub = exif.get_ifd(0x8769)
    sub[0x9003] = stamp
    sub[0x9004] = stamp
    gps = exif.get_ifd(0x8825)
    gps[1] = "N" if lat >= 0 else "S"
    gps[2] = _deg_to_dms(lat)
    gps[3] = "E" if lon >= 0 else "W"
    gps[4] = _deg_to_dms(lon)
    return exif.tobytes()


def draw_scene(size: tuple[int, int], palette, rng: random.Random, variant: float = 0.0) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    top, mid, ground = palette
    # sky gradient
    for y in range(h):
        t = y / h
        c = tuple(int(top[i] * (1 - t) + mid[i] * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    # sun / moon
    sx, sy, sr = int(w * (0.2 + 0.6 * rng.random() + variant * 0.02)), int(h * (0.15 + 0.3 * rng.random())), int(min(w, h) * (0.05 + 0.08 * rng.random()))
    d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 245, 200))
    # mountains / skyline
    horizon = int(h * (0.55 + 0.15 * rng.random()))
    pts = [(0, h)]
    x = 0
    while x < w:
        x += rng.randint(int(w * 0.05), int(w * 0.2))
        pts.append((min(x, w), horizon - rng.randint(0, int(h * 0.25))))
    pts.append((w, h))
    dark = tuple(max(0, int(c * 0.55)) for c in ground)
    d.polygon(pts, fill=dark)
    d.rectangle([0, horizon, w, h], fill=ground)
    # some foreground objects (trees / people / buildings)
    for _ in range(rng.randint(3, 10)):
        ox = int(rng.random() * w + variant * 15)
        oy = rng.randint(horizon, h - 10)
        ow, oh = rng.randint(int(w * 0.02), int(w * 0.08)), rng.randint(int(h * 0.05), int(h * 0.3))
        col = tuple(rng.randint(20, 235) for _ in range(3))
        if rng.random() < 0.5:
            d.rectangle([ox, oy - oh, ox + ow, oy], fill=col)
        else:
            d.ellipse([ox, oy - oh, ox + ow, oy], fill=col)
    # texture noise
    noise = Image.effect_noise(size, rng.randint(8, 30)).convert("RGB")
    img = Image.blend(img, noise, 0.08)
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--count", type=int, default=90)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)

    # events: (day offset, hour, place, #photos)
    events = [
        (0, 9, "beach", 0.22),
        (0, 18, "beach", 0.10),
        (1, 10, "old city", 0.28),
        (2, 8, "mountain", 0.25),
        (4, 16, "park", 0.15),
    ]
    base = datetime(2025, 8, 14, 0, 0, 0)
    n_made = 0
    for ei, (day, hour, place, share) in enumerate(events):
        n = max(3, int(round(a.count * share)))
        palette = PALETTES[ei % len(PALETTES)]
        lat0, lon0 = PLACES[place]
        t = base + timedelta(days=day, hours=hour)
        i = 0
        while i < n:
            size = rng.choice(SIZES)
            scene_seed = rng.random()
            scene_rng = random.Random(scene_seed)
            burst = rng.random() < 0.25
            shots = rng.randint(2, 4) if burst else 1
            for s in range(shots):
                if i >= n:
                    break
                img = draw_scene(size, palette, random.Random(scene_seed), variant=s * 1.0)
                kind = ""
                if rng.random() < 0.08:
                    img = img.filter(ImageFilter.GaussianBlur(5))
                    kind = "_blurry"
                elif rng.random() < 0.08:
                    img = img.point(lambda v: int(v * 0.35))
                    kind = "_dark"
                lat = lat0 + rng.uniform(-0.004, 0.004)
                lon = lon0 + rng.uniform(-0.004, 0.004)
                t += timedelta(seconds=rng.randint(3, 20) if s > 0 else rng.randint(60, 900))
                name = f"IMG_{n_made + 1:04d}{kind}.jpg"
                img.save(os.path.join(a.out, name), "JPEG", quality=90, exif=make_exif(t, lat, lon))
                n_made += 1
                i += 1
    print(f"wrote {n_made} photos to {a.out}")


if __name__ == "__main__":
    main()
