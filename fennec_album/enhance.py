"""Image processing: auto-enhance (levels, brightness, colour, sharpening)
and content-aware cropping around a focus point.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

MAX_OUTPUT_SIDE = 4200   # plenty for 300 dpi on A3


# ---------------------------------------------------------------- enhance
def _luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def auto_enhance(img: Image.Image, strength: float = 1.0) -> Image.Image:
    """Return an enhanced RGB copy. strength 0 = untouched, 1 = default."""
    img = img.convert("RGB")
    if strength <= 0:
        return img
    small = img.copy()
    small.thumbnail((400, 400))
    rgb = np.asarray(small, dtype=np.float32)
    lum = _luminance(rgb)

    # 1. levels: stretch so that 0.3%..99.7% of pixels span the full range
    lo, hi = np.percentile(lum, [0.3, 99.7])
    lo = min(lo, 40.0)                       # never crush more than dark shadows
    hi = max(hi, 215.0)
    if hi - lo < 250:
        scale = 255.0 / max(hi - lo, 1.0)
        lut = np.clip((np.arange(256) - lo) * scale, 0, 255)
        lut = (np.arange(256) * (1 - strength) + lut * strength).astype(np.uint8)
        img = img.point(list(lut) * 3)
        lum = np.clip((lum - lo) * scale, 0, 255)

    # 2. brightness: gamma lift for dark images, slight pull-down for very bright
    mean = float(lum.mean()) / 255.0
    target = 0.47
    gamma = 1.0
    if mean < 0.40:
        gamma = np.log(target) / np.log(max(mean, 0.05))
        gamma = float(np.clip(gamma, 1.0, 1.9))
    elif mean > 0.68:
        gamma = np.log(0.62) / np.log(mean)
        gamma = float(np.clip(gamma, 0.75, 1.0))
    if abs(gamma - 1.0) > 0.02:
        g = 1.0 + (gamma - 1.0) * strength
        lut = (255.0 * (np.arange(256) / 255.0) ** (1.0 / g)).astype(np.uint8)
        img = img.point(list(lut) * 3)

    # 3. gentle contrast S-curve when the image is flat
    contrast = float(lum.std()) / 255.0
    if contrast < 0.19:
        boost = 1.0 + (0.19 - contrast) * 1.6 * strength
        img = ImageEnhance.Contrast(img).enhance(min(boost, 1.25))

    # 4. colour: a touch more saturation, less if already vivid
    rg = rgb[..., 0] - rgb[..., 1]
    yb = 0.5 * (rgb[..., 0] + rgb[..., 1]) - rgb[..., 2]
    colorfulness = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2))
    sat = 1.12 if colorfulness < 25 else (1.06 if colorfulness < 45 else 1.0)
    if sat != 1.0:
        img = ImageEnhance.Color(img).enhance(1.0 + (sat - 1.0) * strength)

    # 5. sharpen for print
    img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=int(55 * strength), threshold=3))
    return img


# ------------------------------------------------------------ smart crop
def saliency_map(img: Image.Image, size: int = 96) -> np.ndarray:
    """Cheap saliency: gradient energy + distance from the mean colour,
    with a mild centre prior. Returns a float array in [0,1] of shape (h, w)."""
    small = img.convert("RGB").copy()
    small.thumbnail((size, size))
    rgb = np.asarray(small, dtype=np.float32)
    gray = _luminance(rgb)
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = np.abs(gray[:, 2:] - gray[:, :-2])
    gy[1:-1, :] = np.abs(gray[2:, :] - gray[:-2, :])
    edges = np.sqrt(gx**2 + gy**2)
    mean_col = rgb.reshape(-1, 3).mean(axis=0)
    col_dist = np.sqrt(((rgb - mean_col) ** 2).sum(axis=-1))
    sal = edges / (edges.max() + 1e-6) + 0.6 * col_dist / (col_dist.max() + 1e-6)
    # blur a little so single pixels do not dominate
    sal_img = Image.fromarray((255 * sal / (sal.max() + 1e-6)).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
    sal = np.asarray(sal_img, dtype=np.float32) / 255.0
    h, w = sal.shape
    ys, xs = np.mgrid[0:h, 0:w]
    center = 1.0 - 0.35 * (((xs / w - 0.5) ** 2 + (ys / h - 0.5) ** 2) / 0.5)
    return sal * center


def find_focus(img: Image.Image, aspect: float | None = None) -> tuple[float, float]:
    """Best focus point (fx, fy in 0..1) for cropping to `aspect` (w/h).
    If aspect is None, uses the saliency centroid."""
    sal = saliency_map(img)
    h, w = sal.shape
    if aspect is None:
        total = sal.sum() + 1e-6
        ys, xs = np.mgrid[0:h, 0:w]
        return float((sal * xs).sum() / total / w), float((sal * ys).sum() / total / h)

    img_aspect = w / h
    if abs(img_aspect - aspect) < 1e-3:
        return 0.5, 0.5
    if aspect < img_aspect:      # crop horizontally -> slide a window along x
        cw, ch = max(1, int(round(h * aspect))), h
        col = sal.sum(axis=0)
        cum = np.concatenate([[0.0], np.cumsum(col)])
        sums = cum[cw:] - cum[:-cw]
        x0 = int(np.argmax(sums))
        return (x0 + cw / 2) / w, 0.5
    cw, ch = w, max(1, int(round(w / aspect)))
    row = sal.sum(axis=1)
    cum = np.concatenate([[0.0], np.cumsum(row)])
    sums = cum[ch:] - cum[:-ch]
    y0 = int(np.argmax(sums))
    return 0.5, (y0 + ch / 2) / h


def crop_box(width: int, height: int, aspect: float, focus: tuple[float, float]) -> tuple[int, int, int, int]:
    """Largest box of the given aspect inside (width, height) centred on focus."""
    img_aspect = width / height
    if img_aspect > aspect:
        ch = height
        cw = int(round(height * aspect))
    else:
        cw = width
        ch = int(round(width / aspect))
    cx = focus[0] * width
    cy = focus[1] * height
    x0 = int(round(min(max(cx - cw / 2, 0), width - cw)))
    y0 = int(round(min(max(cy - ch / 2, 0), height - ch)))
    return x0, y0, x0 + cw, y0 + ch


def crop_to_aspect(img: Image.Image, aspect: float, focus: tuple[float, float]) -> Image.Image:
    return img.crop(crop_box(img.width, img.height, aspect, focus))


# ---------------------------------------------------------------- driver
def process_photo(src_path: str, dst_path: str, enhance: bool = True, strength: float = 1.0) -> tuple[int, int]:
    """Load, fix orientation, enhance, cap size, save JPEG. Returns (w, h)."""
    if os.path.exists(dst_path):
        with Image.open(dst_path) as done:
            return done.size
    with Image.open(src_path) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    if max(img.size) > MAX_OUTPUT_SIDE:
        img.thumbnail((MAX_OUTPUT_SIDE, MAX_OUTPUT_SIDE), Image.LANCZOS)
    if enhance:
        img = auto_enhance(img, strength=strength)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    img.save(dst_path, "JPEG", quality=93, subsampling=0, optimize=True)
    return img.size
