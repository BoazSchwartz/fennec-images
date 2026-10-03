"""Page templates and the paging algorithm.

Slot rectangles are stored as fractions of the *full page* [x, y, w, h],
so the browser preview and the PDF renderer draw exactly the same thing.
"""
from __future__ import annotations

import itertools
import math
import random
from typing import Any

from .model import Album, PAGE_SIZES_MM

Rect = tuple[float, float, float, float]   # x, y, w, h  (fractions of the page)

MARGIN_MM = 9.0
GUTTER_MM = 4.0
CAPTION_MM = 7.0          # strip under the content for the event name / page number
COVER_BAND = 0.24         # fraction of the cover page used by the title band


# ----------------------------------------------------------- geometry
def _split_v(rect: Rect, fracs: list[float], gap: float) -> list[Rect]:
    """Split rect into columns (left→right)."""
    x, y, w, h = rect
    total_gap = gap * (len(fracs) - 1)
    usable = w - total_gap
    out, cx = [], x
    for f in fracs:
        cw = usable * f
        out.append((cx, y, cw, h))
        cx += cw + gap
    return out


def _split_h(rect: Rect, fracs: list[float], gap: float) -> list[Rect]:
    """Split rect into rows (top→bottom)."""
    x, y, w, h = rect
    total_gap = gap * (len(fracs) - 1)
    usable = h - total_gap
    out, cy = [], y
    for f in fracs:
        ch = usable * f
        out.append((x, cy, w, ch))
        cy += ch + gap
    return out


def _grid(rect: Rect, cols: int, rows: int, gx: float, gy: float) -> list[Rect]:
    out = []
    for row in _split_h(rect, [1 / rows] * rows, gy):
        out.extend(_split_v(row, [1 / cols] * cols, gx))
    return out


class PageGeometry:
    def __init__(self, page_size: str):
        self.page_w_mm, self.page_h_mm = PAGE_SIZES_MM[page_size]
        self.aspect = self.page_w_mm / self.page_h_mm
        self.mx = MARGIN_MM / self.page_w_mm
        self.my = MARGIN_MM / self.page_h_mm
        self.gx = GUTTER_MM / self.page_w_mm
        self.gy = GUTTER_MM / self.page_h_mm
        self.caption_h = CAPTION_MM / self.page_h_mm
        # content box leaves room for the caption strip at the bottom
        self.content: Rect = (self.mx, self.my, 1 - 2 * self.mx, 1 - 2 * self.my - self.caption_h)
        self.templates = self._build_templates()

    def slot_aspect(self, r: Rect) -> float:
        return (r[2] * self.page_w_mm) / (r[3] * self.page_h_mm)

    # ------------------------------------------------------- templates
    def _build_templates(self) -> dict[str, dict[str, Any]]:
        c, gx, gy = self.content, self.gx, self.gy
        portrait_page = self.aspect < 1.0
        t: dict[str, list[Rect]] = {}

        # one photo
        t["hero-bleed"] = [(0.0, 0.0, 1.0, 1.0)]
        fx, fy = c[0] + c[2] * 0.08, c[1] + c[3] * 0.06
        t["hero-framed"] = [(fx, fy, c[2] * 0.84, c[3] * 0.88)]
        t["hero-wide"] = [c]

        # two photos
        t["two-equal"] = _split_v(c, [0.5, 0.5], gx)
        t["two-big-left"] = _split_v(c, [0.64, 0.36], gx)
        t["two-big-right"] = _split_v(c, [0.36, 0.64], gx)
        if portrait_page:
            t["two-stack"] = _split_h(c, [0.5, 0.5], gy)
            t["two-stack-big-top"] = _split_h(c, [0.64, 0.36], gy)

        # three photos
        left, right = _split_v(c, [0.62, 0.38], gx)
        t["three-big-left"] = [left] + _split_h(right, [0.5, 0.5], gy)
        left, right = _split_v(c, [0.38, 0.62], gx)
        t["three-big-right"] = _split_h(left, [0.5, 0.5], gy) + [right]
        top, bottom = _split_h(c, [0.62, 0.38], gy)
        t["three-big-top"] = [top] + _split_v(bottom, [0.5, 0.5], gx)
        top, bottom = _split_h(c, [0.38, 0.62], gy)
        t["three-big-bottom"] = _split_v(top, [0.5, 0.5], gx) + [bottom]
        if not portrait_page:
            t["three-columns"] = _split_v(c, [1 / 3] * 3, gx)
        else:
            t["three-rows"] = _split_h(c, [1 / 3] * 3, gy)

        # four photos
        t["four-grid"] = _grid(c, 2, 2, gx, gy)
        left, right = _split_v(c, [0.64, 0.36], gx)
        t["four-big-left"] = [left] + _split_h(right, [1 / 3] * 3, gy)
        top, bottom = _split_h(c, [0.64, 0.36], gy)
        t["four-big-top"] = [top] + _split_v(bottom, [1 / 3] * 3, gx)
        left, right = _split_v(c, [0.5, 0.5], gx)
        t["four-two-columns"] = _split_h(left, [0.6, 0.4], gy) + _split_h(right, [0.4, 0.6], gy)

        # five photos
        left, right = _split_v(c, [0.58, 0.42], gx)
        t["five-big-left"] = [left] + _grid(right, 2, 2, gx, gy)
        top, bottom = _split_h(c, [0.6, 0.4], gy)
        t["five-big-top"] = [top] + _split_v(bottom, [0.25] * 4, gx)
        top, bottom = _split_h(c, [0.58, 0.42], gy)
        t["five-mosaic"] = _split_v(top, [0.62, 0.38], gx) + _split_v(bottom, [1 / 3] * 3, gx)

        # six photos
        t["six-grid"] = _grid(c, 3, 2, gx, gy)
        left, right = _split_v(c, [0.42, 0.58], gx)
        top, bottom = _split_h(right, [0.5, 0.5], gy)
        t["six-mosaic"] = [left] + _split_v(top, [0.5, 0.5], gx) + _split_v(bottom, [1 / 3] * 3, gx)

        out: dict[str, dict[str, Any]] = {}
        for name, rects in t.items():
            out[name] = {
                "slots": rects,
                "count": len(rects),
                "full_bleed": name == "hero-bleed",
                "aspects": [self.slot_aspect(r) for r in rects],
                "areas": [r[2] * r[3] for r in rects],
            }
        return out

    def templates_with(self, count: int) -> list[str]:
        return [n for n, tpl in self.templates.items() if tpl["count"] == count]

    # ------------------------------------------------------------ cover
    def cover_slots(self) -> list[Rect]:
        return [(0.0, 0.0, 1.0, 1.0 - COVER_BAND)]


# ------------------------------------------------------------ assignment
def assign_photos(geom: PageGeometry, template: str, photos: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    """Order photos into the template's slots. Returns (ordered photos, cost)."""
    tpl = geom.templates[template]
    n = len(photos)
    if n != tpl["count"]:
        raise ValueError(f"template {template} wants {tpl['count']} photos, got {n}")
    aspects, areas = tpl["aspects"], tpl["areas"]
    max_area = max(areas)
    best_perm, best_cost = None, math.inf
    for perm in itertools.permutations(range(n)):
        cost = 0.0
        for slot_i, photo_i in enumerate(perm):
            p = photos[photo_i]
            crop = abs(math.log((p["width"] / max(p["height"], 1)) / aspects[slot_i]))
            cost += crop * 1.0
            cost -= p["score"] * (areas[slot_i] / max_area) * 1.6
        if cost < best_cost:
            best_cost, best_perm = cost, perm
    assert best_perm is not None
    return [photos[i] for i in best_perm], best_cost


def choose_template(
    geom: PageGeometry, photos: list[dict[str, Any]], rng: random.Random, avoid: set[str], allow_bleed: bool = True
) -> tuple[str, list[dict[str, Any]]]:
    names = geom.templates_with(len(photos))
    if not allow_bleed:
        names = [n for n in names if not geom.templates[n]["full_bleed"]]
    best = None
    for name in names:
        ordered, cost = assign_photos(geom, name, photos)
        if name in avoid:
            cost += 1.5
        cost += rng.uniform(0, 0.6)          # variety
        if best is None or cost < best[0]:
            best = (cost, name, ordered)
    assert best is not None
    return best[1], best[2]


# ---------------------------------------------------------------- paging
def _chunk_sizes(n: int, hero_flags: list[bool], rng: random.Random) -> list[int]:
    """Decide how many photos go on each page for one event."""
    sizes: list[int] = []
    i, last, last2 = 0, 0, 0
    base_w = {1: 0.5, 2: 1.0, 3: 1.2, 4: 1.0, 5: 0.7, 6: 0.55}
    while i < n:
        left = n - i
        opts = list(range(1, min(6, left) + 1))
        weights = []
        for k in opts:
            w = base_w[k]
            if k == 1:
                w = 2.2 if hero_flags[i] else 0.12
            elif hero_flags[i] and k <= 3:
                w *= 1.3          # a hero also looks good as the big slot of a small page
            if k == last:
                w *= 0.2          # never the same page size twice in a row
            if k == last2:
                w *= 0.6
            # alternate dense and sparse: after a busy page prefer a calm one
            if last >= 4 and k >= 4:
                w *= 0.3
            if last <= 2 and k <= 2 and last:
                w *= 0.5
            rem = left - k
            if rem > 0 and hero_flags[i + k]:
                w *= 1.6          # let the next page open with a hero shot
            if rem == 1 and not hero_flags[n - 1]:
                w *= 0.15
            if rem == 2:
                w *= 0.8
            weights.append(w)
        k = rng.choices(opts, weights)[0]
        sizes.append(k)
        i += k
        last2, last = last, k
    return sizes


def build_pages(album: Album, chosen_ids: list[str], seed: int | None = None) -> list[dict[str, Any]]:
    """Create cover + photo pages for the chosen photos (in order)."""
    geom = PageGeometry(album.page_size)
    rng = random.Random(seed if seed is not None else album.seed)
    photos = [album.photos[pid] for pid in chosen_ids]
    if not photos:
        return []
    scores = sorted((p["score"] for p in photos), reverse=True)
    hero_cut = scores[max(0, int(len(scores) * 0.2) - 1)] if len(scores) > 4 else 1.1

    pages: list[dict[str, Any]] = []

    # cover: the best landscape-ish photo overall
    cover_photo = max(photos, key=lambda p: p["score"] + (0.15 if p["width"] >= p["height"] else 0))
    pages.append(
        {
            "index": 0,
            "kind": "cover",
            "template": "cover",
            "event_id": None,
            "slots": [{"photo_id": cover_photo["id"], "rect": list(geom.cover_slots()[0])}],
            "caption": "",
        }
    )

    # photo pages, event by event (the cover photo is not repeated inside)
    by_event: dict[int, list[dict[str, Any]]] = {}
    for p in photos:
        if p["id"] == cover_photo["id"] and len(photos) > 1:
            continue
        by_event.setdefault(p["event_id"], []).append(p)
    recent: list[str] = []          # last few templates, to avoid repetition
    for eid in sorted(by_event):
        ev_photos = by_event[eid]
        heroes = [p["score"] >= hero_cut for p in ev_photos]
        sizes = _chunk_sizes(len(ev_photos), heroes, rng)
        pos = 0
        event = album.event(eid)
        caption = event["name"] if event else ""
        for k in sizes:
            chunk = ev_photos[pos : pos + k]
            pos += k
            template, ordered = choose_template(geom, chunk, rng, avoid=set(recent))
            tpl = geom.templates[template]
            pages.append(
                {
                    "index": len(pages),
                    "kind": "photos",
                    "template": template,
                    "event_id": eid,
                    "slots": [{"photo_id": p["id"], "rect": list(r)} for p, r in zip(ordered, tpl["slots"])],
                    "caption": caption,
                }
            )
            recent = (recent + [template])[-3:]
    return pages


def relayout_page(album: Album, page: dict[str, Any], template: str | None = None, seed: int | None = None) -> None:
    """Change a page's template (next one with the same count, or the given one)."""
    if page["kind"] != "photos":
        return
    geom = PageGeometry(album.page_size)
    ids = [s["photo_id"] for s in page["slots"] if s.get("photo_id")]
    photos = [album.photos[i] for i in ids]
    names = geom.templates_with(len(photos))
    if template is None or template not in names:
        cur = names.index(page["template"]) if page["template"] in names else -1
        template = names[(cur + 1) % len(names)]
    ordered, _ = assign_photos(geom, template, photos)
    tpl = geom.templates[template]
    page["template"] = template
    page["slots"] = [{"photo_id": p["id"], "rect": list(r)} for p, r in zip(ordered, tpl["slots"])]


def reassign_page(album: Album, page: dict[str, Any]) -> None:
    """Keep the template but re-order photos into the slots that fit them best."""
    if page["kind"] != "photos":
        return
    geom = PageGeometry(album.page_size)
    ids = [s["photo_id"] for s in page["slots"] if s.get("photo_id")]
    photos = [album.photos[i] for i in ids]
    ordered, _ = assign_photos(geom, page["template"], photos)
    tpl = geom.templates[page["template"]]
    page["slots"] = [{"photo_id": p["id"], "rect": list(r)} for p, r in zip(ordered, tpl["slots"])]


def template_names(album: Album, count: int) -> list[str]:
    return PageGeometry(album.page_size).templates_with(count)
