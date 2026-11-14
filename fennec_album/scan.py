"""Discover images, read metadata (date / GPS / size) and compute the
image statistics that drive duplicate detection and photo selection.

Everything here works on a downscaled copy of each image so scanning a
few thousand photos stays reasonably quick.
"""
from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Iterable

import numpy as np
from PIL import Image, ImageOps

from .model import Photo

try:  # optional HEIC/HEIF support
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    HEIF = True
except Exception:  # pragma: no cover
    HEIF = False

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
if HEIF:
    IMAGE_EXTS |= {".heic", ".heif"}

ANALYSIS_SIZE = 320      # longest side used for metrics
THUMB_SIZE = 400         # thumbnails shown in the UI
DISPLAY_SIZE = 1800      # on-screen version of a photo

EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_DATETIME_DIGITIZED = 0x9004
EXIF_DATETIME = 0x0132
EXIF_IFD = 0x8769
GPS_IFD = 0x8825

_FILENAME_DATE_RES = [
    re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[-_ T]?(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})"),
    re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})"),
]


# ----------------------------------------------------------------- discovery
def find_images(root: str, exclude: Iterable[str] = ()) -> list[str]:
    """Images of root and all its subfolders, except the excluded dirs (the album being built)."""
    skip = {os.path.normcase(os.path.abspath(d)) for d in exclude}
    paths: list[str] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if os.path.normcase(os.path.abspath(os.path.join(dirpath, d))) not in skip]
        for name in files:
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                paths.append(os.path.join(dirpath, name))
    paths.sort()
    return paths


def photo_id_for(path: str) -> str:
    st = os.stat(path)
    key = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------ metadata
def _parse_exif_datetime(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip().replace("\x00", "")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[: len(fmt) + 2], fmt)
        except ValueError:
            continue
    return None


def _dms_to_deg(dms, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in dms)
    except Exception:
        return None
    deg = d + m / 60.0 + s / 3600.0
    if ref in ("S", "W"):
        deg = -deg
    return deg


def read_metadata(img: Image.Image, path: str) -> dict:
    """Return dict with ts/ts_source/lat/lon."""
    out = {"ts": None, "ts_source": "none", "lat": None, "lon": None}
    try:
        exif = img.getexif()
    except Exception:
        exif = None
    if exif:
        dt = None
        try:
            sub = exif.get_ifd(EXIF_IFD)
            dt = _parse_exif_datetime(sub.get(EXIF_DATETIME_ORIGINAL)) or _parse_exif_datetime(
                sub.get(EXIF_DATETIME_DIGITIZED)
            )
        except Exception:
            pass
        if dt is None:
            dt = _parse_exif_datetime(exif.get(EXIF_DATETIME))
        if dt is not None:
            out["ts"], out["ts_source"] = dt.isoformat(), "exif"
        try:
            gps = exif.get_ifd(GPS_IFD)
            if gps and 2 in gps and 4 in gps:
                lat = _dms_to_deg(gps[2], gps.get(1, "N"))
                lon = _dms_to_deg(gps[4], gps.get(3, "E"))
                if lat is not None and lon is not None and (lat, lon) != (0.0, 0.0):
                    out["lat"], out["lon"] = lat, lon
        except Exception:
            pass

    if out["ts"] is None:
        name = os.path.basename(path)
        for rx in _FILENAME_DATE_RES:
            m = rx.search(name)
            if m:
                parts = [int(x) for x in m.groups()]
                try:
                    dt = datetime(*parts)  # type: ignore[arg-type]
                    out["ts"], out["ts_source"] = dt.isoformat(), "filename"
                    break
                except ValueError:
                    continue
    if out["ts"] is None:
        dt = datetime.fromtimestamp(os.path.getmtime(path))
        out["ts"], out["ts_source"] = dt.isoformat(), "mtime"
    return out


# ------------------------------------------------------------------- metrics
def dhash(gray: np.ndarray, size: int = 8) -> str:
    """Difference hash of a grayscale array -> hex string (size*size bits)."""
    im = Image.fromarray(gray.astype(np.uint8)).resize((size + 1, size), Image.LANCZOS)
    a = np.asarray(im, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:0{size * size // 4}x}"


def hamming(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def color_signature(rgb: np.ndarray) -> list[float]:
    """Tiny 4x4x4 RGB histogram used as a second similarity signal."""
    q = (rgb // 64).astype(np.int32)
    idx = q[..., 0] * 16 + q[..., 1] * 4 + q[..., 2]
    hist = np.bincount(idx.ravel(), minlength=64).astype(np.float64)
    hist /= max(hist.sum(), 1.0)
    return [round(float(x), 5) for x in hist]


def compute_metrics(img: Image.Image) -> tuple[dict[str, float], str, list[float]]:
    """Compute quality/interest statistics on a small RGB copy."""
    small = img.copy()
    small.thumbnail((ANALYSIS_SIZE, ANALYSIS_SIZE), Image.LANCZOS)
    rgb = np.asarray(small.convert("RGB"), dtype=np.float32)
    gray = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]

    # sharpness: variance of a 3x3 Laplacian
    lap = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    sharpness = float(lap.var())

    # edges / detail density
    gx = np.abs(gray[:, 1:] - gray[:, :-1])
    gy = np.abs(gray[1:, :] - gray[:-1, :])
    edge_density = float((gx.mean() + gy.mean()) / 2.0)

    brightness = float(gray.mean() / 255.0)
    contrast = float(gray.std() / 255.0)

    # colourfulness (Hasler & Süsstrunk)
    rg = rgb[..., 0] - rgb[..., 1]
    yb = 0.5 * (rgb[..., 0] + rgb[..., 1]) - rgb[..., 2]
    colorfulness = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))

    # entropy of the luminance histogram
    hist, _ = np.histogram(gray, bins=64, range=(0, 255))
    p = hist / max(hist.sum(), 1)
    p = p[p > 0]
    entropy = float(-(p * np.log2(p)).sum())

    # clipping: fraction of near-black / near-white pixels
    clipped = float(((gray < 6).mean() + (gray > 249).mean()))

    # saliency concentration: does the detail live in a compact region?
    h, w = gray.shape
    sal = np.zeros_like(gray)
    sal[:, :-1] += gx
    sal[:-1, :] += gy
    ys, xs = np.mgrid[0:h, 0:w]
    total = sal.sum() + 1e-6
    cx, cy = float((sal * xs).sum() / total) / w, float((sal * ys).sum() / total) / h
    spread = float(np.sqrt((((xs / w - cx) ** 2 + (ys / h - cy) ** 2) * sal).sum() / total))

    metrics = {
        "sharpness": round(sharpness, 2),
        "edge_density": round(edge_density, 3),
        "brightness": round(brightness, 4),
        "contrast": round(contrast, 4),
        "colorfulness": round(colorfulness, 2),
        "entropy": round(entropy, 3),
        "clipped": round(clipped, 4),
        "focus_x": round(cx, 3),
        "focus_y": round(cy, 3),
        "spread": round(spread, 3),
    }
    return metrics, dhash(gray), color_signature(rgb.astype(np.uint8))


# ---------------------------------------------------------------- scoring
def _rank01(values: np.ndarray) -> np.ndarray:
    """Map values to [0,1] by rank (robust to outliers)."""
    n = len(values)
    if n <= 1:
        return np.ones(n)
    order = values.argsort()
    ranks = np.empty(n)
    ranks[order] = np.arange(n)
    return ranks / (n - 1)


def score_photos(photos: list[Photo]) -> None:
    """Assign photo.score in [0,1] from the metrics, relative to the batch."""
    if not photos:
        return
    m = {k: np.array([p.metrics[k] for p in photos], dtype=np.float64) for k in photos[0].metrics}
    res = np.array([p.width * p.height for p in photos], dtype=np.float64)

    sharp = _rank01(np.log1p(m["sharpness"]))
    detail = _rank01(m["edge_density"])
    color = _rank01(m["colorfulness"])
    entropy = _rank01(m["entropy"])
    contrast = _rank01(m["contrast"])
    resolution = _rank01(np.log1p(res))

    # exposure: prefer mid-tones, penalise very dark / very bright
    b = m["brightness"]
    exposure = 1.0 - np.clip(np.abs(b - 0.48) / 0.4, 0, 1) ** 1.5
    clip_pen = np.clip(m["clipped"] / 0.25, 0, 1)

    score = (
        0.26 * sharp
        + 0.16 * detail
        + 0.16 * color
        + 0.12 * entropy
        + 0.10 * contrast
        + 0.12 * exposure
        + 0.08 * resolution
        - 0.15 * clip_pen
    )
    score = np.clip(score, 0, 1)
    for p, s, in zip(photos, score):
        p.score = round(float(s), 4)


# ------------------------------------------------------------------- driver
def _ensure_dirs(cache_dir: str) -> tuple[str, str]:
    thumbs = os.path.join(cache_dir, "thumbs")
    display = os.path.join(cache_dir, "display")
    os.makedirs(thumbs, exist_ok=True)
    os.makedirs(display, exist_ok=True)
    return thumbs, display


def _scan_one(path: str, thumbs_dir: str, display_dir: str) -> tuple[Photo, list[float]] | None:
    try:
        pid = photo_id_for(path)
        with Image.open(path) as raw:
            meta = read_metadata(raw, path)
            img = ImageOps.exif_transpose(raw)
            img.load()
            w, h = img.size
            metrics, h_dhash, sig = compute_metrics(img)
            thumb_path = os.path.join(thumbs_dir, f"{pid}.jpg")
            if not os.path.exists(thumb_path):
                t = img.convert("RGB")
                t.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
                t.save(thumb_path, "JPEG", quality=82)
            disp_path = os.path.join(display_dir, f"{pid}.jpg")
            if not os.path.exists(disp_path):
                d = img.convert("RGB")
                d.thumbnail((DISPLAY_SIZE, DISPLAY_SIZE), Image.LANCZOS)
                d.save(disp_path, "JPEG", quality=86)
        photo = Photo(
            id=pid,
            path=os.path.abspath(path),
            filename=os.path.basename(path),
            ts=meta["ts"],
            ts_source=meta["ts_source"],
            lat=meta["lat"],
            lon=meta["lon"],
            width=w,
            height=h,
            dhash=h_dhash,
            metrics=metrics,
            focus=[metrics["focus_x"], metrics["focus_y"]],
        )
        return photo, sig
    except Exception as exc:  # unreadable file: skip, but tell the user
        print(f"  ! skipping {path}: {exc}")
        return None


def scan_directory(root: str, cache_dir: str, workers: int = 4, progress=None) -> tuple[list[Photo], dict[str, list[float]]]:
    paths = find_images(root, exclude=[os.path.dirname(os.path.abspath(cache_dir))])
    n_dirs = len({os.path.dirname(p) for p in paths})
    print(f"  {len(paths)} images in {n_dirs} folder(s)")
    thumbs_dir, display_dir = _ensure_dirs(cache_dir)
    photos: list[Photo] = []
    sigs: dict[str, list[float]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, result in enumerate(pool.map(lambda p: _scan_one(p, thumbs_dir, display_dir), paths), 1):
            if progress:
                progress(i, len(paths))
            if result is None:
                continue
            photo, sig = result
            photos.append(photo)
            sigs[photo.id] = sig
    photos.sort(key=lambda p: (p.ts or "", p.filename))
    score_photos(photos)
    return photos, sigs
