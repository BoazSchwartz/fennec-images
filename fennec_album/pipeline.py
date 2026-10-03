"""Orchestration: scan -> events -> select -> enhance -> layout -> save."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

from PIL import Image

from .enhance import find_focus
from .events import build_events, date_range_label
from .layout import PageGeometry, build_pages
from .model import Album, PAGE_SIZES_MM, photo_to_dict
from .render import ensure_processed, processed_path
from .scan import DISPLAY_SIZE, scan_directory
from .select import select_photos


def _progress(label: str):
    start = time.time()

    def cb(i: int, n: int) -> None:
        if i == n or i % 10 == 0:
            sys.stdout.write(f"\r  {label}: {i}/{n}  ({time.time() - start:.0f}s)")
            sys.stdout.flush()
            if i == n:
                sys.stdout.write("\n")

    return cb


def refresh_display(album: Album, pid: str) -> str:
    """Regenerate the on-screen version of a photo from the processed file."""
    src = ensure_processed(album, pid)
    dst = os.path.join(album.out_dir, "cache", "display", f"{pid}.jpg")
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((DISPLAY_SIZE, DISPLAY_SIZE), Image.LANCZOS)
        im.save(dst, "JPEG", quality=86)
    return dst


def prepare_photo(album: Album, pid: str) -> None:
    """Enhance a photo (once) and refresh its display copy + focus point."""
    first_time = not os.path.exists(processed_path(album, pid))
    ensure_processed(album, pid)
    if first_time:
        refresh_display(album, pid)
        p = album.photos[pid]
        if not p.get("focus_set"):
            with Image.open(processed_path(album, pid)) as im:
                fx, fy = find_focus(im)
            p["focus"] = [round(fx, 3), round(fy, 3)]


def build_album(
    source_dir: str,
    out_dir: str,
    count: int,
    title: str | None = None,
    page_size: str = "a4-landscape",
    gap_hours: float = 3.0,
    jump_km: float = 3.0,
    seed: int = 7,
    enhance: bool = True,
    enhance_strength: float = 1.0,
    geocode: bool = False,
    diversity: float = 0.55,
    workers: int = 4,
) -> Album:
    if page_size not in PAGE_SIZES_MM:
        raise SystemExit(f"unknown page size {page_size}; choose from {', '.join(PAGE_SIZES_MM)}")
    out_dir = os.path.abspath(out_dir)
    cache_dir = os.path.join(out_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)

    print(f"Scanning {source_dir} ...")
    photos, sigs = scan_directory(source_dir, cache_dir, workers=workers, progress=_progress("scanned"))
    if not photos:
        raise SystemExit("no readable images found")
    print(f"  {len(photos)} photos, {sum(1 for p in photos if p.ts_source == 'exif')} with EXIF dates, "
          f"{sum(1 for p in photos if p.lat is not None)} with GPS")

    print("Grouping into events ...")
    events = build_events(photos, gap_hours=gap_hours, jump_km=jump_km, geocode=geocode, cache_dir=cache_dir)
    for e in events:
        print(f"  [{e.id:>2}] {e.name:<40} {e.count:>4} photos")

    print(f"Selecting {count} photos ...")
    chosen = select_photos(photos, sigs, count, diversity=diversity)
    n_groups = len({(p.event_id, p.group_id) for p in photos})
    print(f"  {len(chosen)} chosen out of {n_groups} distinct moments ({len(photos) - n_groups} near-duplicates folded)")

    starts = [datetime.fromisoformat(p.ts) for p in photos if p.ts]
    subtitle = date_range_label(min(starts), max(starts)) if starts else ""
    if title is None:
        title = os.path.basename(os.path.normpath(source_dir)).replace("_", " ").replace("-", " ").title() or "Photo Album"

    geom = PageGeometry(page_size)
    album = Album(
        title=title,
        subtitle=subtitle,
        page_size=page_size,
        source_dir=os.path.abspath(source_dir),
        out_dir=out_dir,
        count=count,
        seed=seed,
        photos={p.id: photo_to_dict(p) for p in photos},
        events=[e.__dict__ for e in events],
        pages=[],
        settings={
            "enhance": enhance,
            "enhance_strength": enhance_strength,
            "page_mm": list(PAGE_SIZES_MM[page_size]),
            "margin_mm": geom.mx * geom.page_w_mm,
            "caption_mm": geom.caption_h * geom.page_h_mm,
            "gap_hours": gap_hours,
            "jump_km": jump_km,
            "diversity": diversity,
        },
    )

    print("Enhancing chosen photos ...")
    cb = _progress("processed")
    for i, p in enumerate(chosen, 1):
        prepare_photo(album, p.id)
        cb(i, len(chosen))

    print("Laying out pages ...")
    album.pages = build_pages(album, [p.id for p in chosen], seed=seed)
    print(f"  {len(album.pages)} pages (incl. cover)")
    path = album.save()
    print(f"Saved {path}")
    return album


def relayout_album(album: Album, seed: int | None = None) -> Album:
    """Rebuild all pages from the currently used photos (keeps replacements)."""
    used = []
    for page in album.pages:
        for s in page["slots"]:
            if s.get("photo_id") and s["photo_id"] not in used:
                used.append(s["photo_id"])
    used.sort(key=lambda pid: (album.photos[pid].get("ts") or "", album.photos[pid]["filename"]))
    if seed is not None:
        album.seed = seed
    album.pages = build_pages(album, used, seed=album.seed)
    album.save()
    return album
