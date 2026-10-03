"""Export the album to a print-ready PDF (reportlab) and page previews (PIL)."""
from __future__ import annotations

import io
import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .enhance import crop_box, process_photo
from .layout import CAPTION_MM, COVER_BAND, MARGIN_MM
from .model import Album

FONT_DIR = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
TITLE_FONT_CANDIDATES = ["georgia.ttf", "Georgia.ttf", "times.ttf", "DejaVuSerif.ttf"]
TEXT_FONT_CANDIDATES = ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
LIGHT_FONT_CANDIDATES = ["segoeuil.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]


def _find_font(candidates: list[str]) -> str | None:
    for name in candidates:
        for d in (FONT_DIR, "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


def _register_fonts() -> tuple[str, str, str]:
    """Register TTFs with reportlab; returns (title, text, light) font names."""
    names = []
    for key, cands, fallback in (
        ("AlbumTitle", TITLE_FONT_CANDIDATES, "Times-Roman"),
        ("AlbumText", TEXT_FONT_CANDIDATES, "Helvetica"),
        ("AlbumLight", LIGHT_FONT_CANDIDATES, "Helvetica"),
    ):
        path = _find_font(cands)
        if path:
            try:
                if key not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(key, path))
                names.append(key)
                continue
            except Exception:
                pass
        names.append(fallback)
    return names[0], names[1], names[2]


def processed_path(album: Album, pid: str) -> str:
    return os.path.join(album.out_dir, "photos", f"{pid}.jpg")


def ensure_processed(album: Album, pid: str) -> str:
    """Make sure the enhanced full-size version of a photo exists."""
    dst = processed_path(album, pid)
    if not os.path.exists(dst):
        p = album.photos[pid]
        settings = album.settings or {}
        process_photo(p["path"], dst, enhance=settings.get("enhance", True), strength=settings.get("enhance_strength", 1.0))
    return dst


def _slot_image(album: Album, slot: dict[str, Any], rect_mm: tuple[float, float, float, float], dpi: int) -> Image.Image:
    """Crop + resize the slot's photo to the slot's physical size at `dpi`."""
    pid = slot["photo_id"]
    photo = album.photos[pid]
    src = ensure_processed(album, pid)
    w_mm, h_mm = rect_mm[2], rect_mm[3]
    aspect = w_mm / h_mm
    with Image.open(src) as im:
        im = im.convert("RGB")
        box = crop_box(im.width, im.height, aspect, tuple(photo.get("focus", [0.5, 0.5])))
        im = im.crop(box)
        target_w = int(round(w_mm / 25.4 * dpi))
        target_h = int(round(h_mm / 25.4 * dpi))
        if im.width > target_w:
            im = im.resize((target_w, target_h), Image.LANCZOS)
        return im


def _rect_mm(album: Album, rect: list[float], bleed_mm: float) -> tuple[float, float, float, float]:
    """Page-fraction rect -> (x, y, w, h) in mm from the top-left, with bleed
    applied on edges that touch the page edge."""
    pw, ph = album.page_size_mm()
    x, y, w, h = rect[0] * pw, rect[1] * ph, rect[2] * pw, rect[3] * ph
    eps = 0.01
    if bleed_mm > 0:
        if rect[0] <= eps:
            x -= bleed_mm
            w += bleed_mm
        if rect[1] <= eps:
            y -= bleed_mm
            h += bleed_mm
        if rect[0] + rect[2] >= 1 - eps:
            w += bleed_mm
        if rect[1] + rect[3] >= 1 - eps:
            h += bleed_mm
    return x, y, w, h


# ------------------------------------------------------------------- PDF
def export_pdf(album: Album, pdf_path: str, dpi: int = 300, bleed_mm: float = 0.0, progress=None) -> str:
    title_font, text_font, light_font = _register_fonts()
    pw, ph = album.page_size_mm()
    page_w_pt = (pw + 2 * bleed_mm) * mm
    page_h_pt = (ph + 2 * bleed_mm) * mm
    c = canvas.Canvas(pdf_path, pagesize=(page_w_pt, page_h_pt))
    c.setTitle(album.title)
    c.setAuthor("fennec-album")

    def place(im: Image.Image, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> None:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92, subsampling=0)
        buf.seek(0)
        from reportlab.lib.utils import ImageReader

        # reportlab's origin is bottom-left; our y is from the top (bleed offset included)
        x_pt = (x_mm + bleed_mm) * mm
        y_pt = page_h_pt - (y_mm + bleed_mm + h_mm) * mm
        c.drawImage(ImageReader(buf), x_pt, y_pt, w_mm * mm, h_mm * mm)

    total = len(album.pages)
    for i, page in enumerate(album.pages):
        if progress:
            progress(i + 1, total)
        if page["kind"] == "cover":
            slot = page["slots"][0]
            if slot.get("photo_id"):
                r = _rect_mm(album, slot["rect"], bleed_mm)
                place(_slot_image(album, slot, r, dpi), *r)
            # title band (white strip across the bottom of the cover)
            band_h = ph * COVER_BAND
            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, page_w_pt, (band_h + bleed_mm) * mm, stroke=0, fill=1)
            c.setFillColorRGB(0.12, 0.12, 0.12)
            size = max(16, min(40, int(pw / 7)))
            c.setFont(title_font, size)
            c.drawCentredString(page_w_pt / 2, (bleed_mm + band_h * 0.52) * mm, album.title)
            if album.subtitle:
                c.setFillColorRGB(0.4, 0.4, 0.4)
                c.setFont(light_font, max(9, size * 0.42))
                c.drawCentredString(page_w_pt / 2, (bleed_mm + band_h * 0.27) * mm, album.subtitle)
        else:
            for slot in page["slots"]:
                if not slot.get("photo_id"):
                    continue
                r = _rect_mm(album, slot["rect"], bleed_mm)
                place(_slot_image(album, slot, r, dpi), *r)
            # caption strip: event name (left) + page number (right)
            if page["template"] != "hero-bleed":
                c.setFont(light_font, 8.5)
                c.setFillColorRGB(0.45, 0.45, 0.45)
                y_pt = (bleed_mm + MARGIN_MM * 0.55) * mm
                if page.get("caption"):
                    c.drawString((MARGIN_MM + bleed_mm) * mm, y_pt, page["caption"])
                c.drawRightString(page_w_pt - (MARGIN_MM + bleed_mm) * mm, y_pt, str(page["index"]))
        c.showPage()
    c.save()
    return pdf_path


# -------------------------------------------------------------- previews
def render_page_preview(album: Album, page: dict[str, Any], width_px: int = 1200) -> Image.Image:
    """Rasterise a page (used for PNG export / quick checks)."""
    pw, ph = album.page_size_mm()
    W = width_px
    H = int(round(W * ph / pw))
    dpi = W / (pw / 25.4)
    canvas_im = Image.new("RGB", (W, H), "white")
    for slot in page["slots"]:
        if not slot.get("photo_id"):
            continue
        r = _rect_mm(album, slot["rect"], 0.0)
        im = _slot_image(album, slot, r, int(dpi))
        box = (int(r[0] / pw * W), int(r[1] / ph * H), int((r[0] + r[2]) / pw * W), int((r[1] + r[3]) / ph * H))
        im = im.resize((max(1, box[2] - box[0]), max(1, box[3] - box[1])), Image.LANCZOS)
        canvas_im.paste(im, (box[0], box[1]))
    draw = ImageDraw.Draw(canvas_im)
    try:
        font_path = _find_font(TITLE_FONT_CANDIDATES if page["kind"] == "cover" else LIGHT_FONT_CANDIDATES)
        font = ImageFont.truetype(font_path, int(W / 22) if page["kind"] == "cover" else int(W / 110)) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    if page["kind"] == "cover":
        band_y = int(H * (1 - COVER_BAND))
        draw.rectangle([0, band_y, W, H], fill="white")
        tw = draw.textlength(album.title, font=font)
        draw.text(((W - tw) / 2, band_y + (H - band_y) * 0.22), album.title, fill=(30, 30, 30), font=font)
        if album.subtitle:
            try:
                sub_font = ImageFont.truetype(_find_font(LIGHT_FONT_CANDIDATES), int(W / 55))
            except Exception:
                sub_font = ImageFont.load_default()
            sw = draw.textlength(album.subtitle, font=sub_font)
            draw.text(((W - sw) / 2, band_y + (H - band_y) * 0.62), album.subtitle, fill=(110, 110, 110), font=sub_font)
    elif page["template"] != "hero-bleed":
        y = H - int(H * (MARGIN_MM * 0.9 / ph))
        if page.get("caption"):
            draw.text((int(W * MARGIN_MM / pw), y), page["caption"], fill=(110, 110, 110), font=font)
        num = str(page["index"])
        draw.text((W - int(W * MARGIN_MM / pw) - draw.textlength(num, font=font), y), num, fill=(110, 110, 110), font=font)
    return canvas_im


def export_previews(album: Album, out_dir: str, width_px: int = 1200) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for page in album.pages:
        p = os.path.join(out_dir, f"page_{page['index']:03d}.jpg")
        render_page_preview(album, page, width_px).save(p, "JPEG", quality=88)
        paths.append(p)
    return paths
