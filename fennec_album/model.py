"""Data model for an album project.

Everything is stored as plain dicts/lists so it round-trips to album.json and
to the browser UI without translation.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any

ALBUM_FILE = "album.json"

# Page sizes in millimetres (width, height)
PAGE_SIZES_MM = {
    "a4-landscape": (297.0, 210.0),
    "a4-portrait": (210.0, 297.0),
    "letter-landscape": (279.4, 215.9),
    "letter-portrait": (215.9, 279.4),
    "square-8in": (203.2, 203.2),
    "square-10in": (254.0, 254.0),
    "a3-landscape": (420.0, 297.0),
}


@dataclass
class Photo:
    id: str
    path: str
    filename: str
    ts: str | None = None            # ISO timestamp of capture
    ts_source: str = "none"          # exif | filename | mtime | none
    lat: float | None = None
    lon: float | None = None
    width: int = 0
    height: int = 0
    dhash: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    score: float = 0.0               # 0..1 "interestingness"
    event_id: int = -1
    group_id: int = -1               # near-duplicate group within the event
    focus: list[float] = field(default_factory=lambda: [0.5, 0.5])
    chosen: bool = False
    pick_reason: str = ""

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0


@dataclass
class Event:
    id: int
    name: str
    start: str | None
    end: str | None
    place_id: int | None
    count: int
    lat: float | None = None
    lon: float | None = None
    place_name: str | None = None


@dataclass
class Slot:
    photo_id: str | None = None


@dataclass
class Page:
    index: int
    kind: str                        # cover | photos
    template: str
    event_id: int | None
    slots: list[dict[str, Any]]
    caption: str = ""


@dataclass
class Album:
    title: str
    subtitle: str
    page_size: str
    source_dir: str
    out_dir: str
    count: int
    seed: int
    photos: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ io
    def save(self, out_dir: str | None = None) -> str:
        out_dir = out_dir or self.out_dir
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, ALBUM_FILE)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=1, ensure_ascii=False)
        return path

    @staticmethod
    def load(out_dir: str) -> "Album":
        path = os.path.join(out_dir, ALBUM_FILE)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        album = Album(**data)
        album.out_dir = out_dir
        return album

    # ------------------------------------------------------------- helpers
    def photo(self, pid: str) -> dict[str, Any]:
        return self.photos[pid]

    def event(self, eid: int) -> dict[str, Any] | None:
        for e in self.events:
            if e["id"] == eid:
                return e
        return None

    def used_photo_ids(self) -> set[str]:
        used: set[str] = set()
        for page in self.pages:
            for slot in page["slots"]:
                if slot.get("photo_id"):
                    used.add(slot["photo_id"])
        return used

    def page_size_mm(self) -> tuple[float, float]:
        return PAGE_SIZES_MM[self.page_size]


def photo_to_dict(p: Photo) -> dict[str, Any]:
    d = asdict(p)
    d["aspect"] = p.aspect
    return d
