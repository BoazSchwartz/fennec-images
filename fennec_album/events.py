"""Group photos into events (by time gaps + location) and places (by GPS).

An event is a run of photos with no big time gap and no big jump in
location. Places are GPS clusters; a place can host several events
(e.g. three visits to the same beach on different days).
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime

from .model import Event, Photo

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _dt(p: Photo) -> datetime | None:
    return datetime.fromisoformat(p.ts) if p.ts else None


# ------------------------------------------------------------------ places
def cluster_places(photos: list[Photo], radius_km: float = 1.5) -> dict[str, int]:
    """Greedy centroid clustering of GPS positions. Returns photo id -> place id."""
    centers: list[list[float]] = []   # [lat, lon, n]
    assignment: dict[str, int] = {}
    for p in photos:
        if p.lat is None or p.lon is None:
            continue
        best, best_d = -1, 1e9
        for i, (clat, clon, _n) in enumerate(centers):
            d = haversine_km(p.lat, p.lon, clat, clon)
            if d < best_d:
                best, best_d = i, d
        if best >= 0 and best_d <= radius_km:
            c = centers[best]
            c[0] = (c[0] * c[2] + p.lat) / (c[2] + 1)
            c[1] = (c[1] * c[2] + p.lon) / (c[2] + 1)
            c[2] += 1
            assignment[p.id] = best
        else:
            centers.append([p.lat, p.lon, 1])
            assignment[p.id] = len(centers) - 1
    return assignment


# ------------------------------------------------------------------ events
def split_events(photos: list[Photo], gap_hours: float = 3.0, jump_km: float = 3.0) -> list[list[Photo]]:
    """Split time-sorted photos into runs separated by big gaps or jumps."""
    ordered = sorted(photos, key=lambda p: (p.ts or "", p.filename))
    events: list[list[Photo]] = []
    current: list[Photo] = []
    last_dt: datetime | None = None
    last_pos: tuple[float, float] | None = None
    for p in ordered:
        dt = _dt(p)
        new_event = False
        if current:
            if dt and last_dt and (dt - last_dt).total_seconds() > gap_hours * 3600:
                new_event = True
            if p.lat is not None and last_pos is not None:
                if haversine_km(p.lat, p.lon, *last_pos) > jump_km:
                    new_event = True
        if new_event:
            events.append(current)
            current = []
        current.append(p)
        if dt:
            last_dt = dt
        if p.lat is not None:
            last_pos = (p.lat, p.lon)
    if current:
        events.append(current)

    # Merge tiny single-photo events into their neighbour when it is close in time
    merged: list[list[Photo]] = []
    for ev in events:
        if merged and len(ev) == 1:
            prev = merged[-1]
            a, b = _dt(prev[-1]), _dt(ev[0])
            if a and b and (b - a).total_seconds() <= gap_hours * 2 * 3600:
                prev.extend(ev)
                continue
        merged.append(ev)
    return merged


def _day_part(hour: int) -> str:
    if hour < 6:
        return "Night"
    if hour < 12:
        return "Morning"
    if hour < 17:
        return "Afternoon"
    if hour < 21:
        return "Evening"
    return "Night"


def _fmt_date(d: datetime) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def date_range_label(start: datetime | None, end: datetime | None) -> str:
    if not start:
        return "Undated"
    if not end or start.date() == end.date():
        return _fmt_date(start)
    if start.year == end.year and start.month == end.month:
        return f"{MONTHS[start.month - 1]} {start.day}–{end.day}, {start.year}"
    if start.year == end.year:
        return f"{MONTHS[start.month - 1]} {start.day} – {MONTHS[end.month - 1]} {end.day}, {start.year}"
    return f"{_fmt_date(start)} – {_fmt_date(end)}"


def build_events(
    photos: list[Photo],
    gap_hours: float = 3.0,
    jump_km: float = 3.0,
    place_radius_km: float = 1.5,
    geocode: bool = False,
    cache_dir: str | None = None,
) -> list[Event]:
    place_of = cluster_places(photos, radius_km=place_radius_km)
    runs = split_events(photos, gap_hours=gap_hours, jump_km=jump_km)

    # name places (optionally via reverse geocoding)
    acc: dict[int, list[float]] = {}   # place id -> [sum lat, sum lon, n]
    for p in photos:
        pid = place_of.get(p.id)
        if pid is None:
            continue
        a = acc.setdefault(pid, [0.0, 0.0, 0.0])
        a[0] += p.lat
        a[1] += p.lon
        a[2] += 1
    place_centers: dict[int, tuple[float, float]] = {pid: (a[0] / a[2], a[1] / a[2]) for pid, a in acc.items()}
    place_names: dict[int, str] = {}
    if geocode and place_centers:
        geocoder = ReverseGeocoder(cache_dir)
        for pid, (lat, lon) in place_centers.items():
            name = geocoder.lookup(lat, lon)
            if name:
                place_names[pid] = name

    events: list[Event] = []
    for i, run in enumerate(runs):
        dts = [d for d in (_dt(p) for p in run) if d]
        start, end = (min(dts), max(dts)) if dts else (None, None)
        places = Counter(place_of[p.id] for p in run if p.id in place_of)
        place_id = places.most_common(1)[0][0] if places else None
        place_name = place_names.get(place_id) if place_id is not None else None
        if place_name:
            where = place_name
        elif place_id is not None:
            where = f"Place {place_id + 1}"
        else:
            hours = [d.hour for d in dts]
            where = _day_part(int(sorted(hours)[len(hours) // 2])) if hours else ""
        label = date_range_label(start, end)
        name = f"{label} · {where}" if where else label
        lat = lon = None
        if place_id is not None:
            lat, lon = place_centers[place_id]
        events.append(
            Event(
                id=i,
                name=name,
                start=start.isoformat() if start else None,
                end=end.isoformat() if end else None,
                place_id=place_id,
                count=len(run),
                lat=lat,
                lon=lon,
                place_name=place_name,
            )
        )
        for p in run:
            p.event_id = i
    return events


# ---------------------------------------------------------------- geocoding
class ReverseGeocoder:
    """Opt-in reverse geocoding through OpenStreetMap Nominatim (needs network).

    Results are cached on disk; requests are throttled to 1/s per their policy.
    """

    URL = "https://nominatim.openstreetmap.org/reverse"

    def __init__(self, cache_dir: str | None):
        self.cache_path = os.path.join(cache_dir, "geocode.json") if cache_dir else None
        self.cache: dict[str, str] = {}
        if self.cache_path and os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as fh:
                    self.cache = json.load(fh)
            except Exception:
                self.cache = {}
        self._last = 0.0

    def lookup(self, lat: float, lon: float) -> str | None:
        key = f"{lat:.3f},{lon:.3f}"
        if key in self.cache:
            return self.cache[key]
        wait = 1.1 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        q = urllib.parse.urlencode({"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2", "zoom": 14})
        req = urllib.request.Request(f"{self.URL}?{q}", headers={"User-Agent": "fennec-album/1.0 (photo album tool)"})
        name = None
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
            addr = data.get("address", {})
            parts = []
            for k in ("attraction", "tourism", "leisure", "neighbourhood", "suburb", "village", "town", "city", "county"):
                if addr.get(k) and addr[k] not in parts:
                    parts.append(addr[k])
                if len(parts) >= 2:
                    break
            if addr.get("country") and len(parts) < 2:
                parts.append(addr["country"])
            name = ", ".join(parts) if parts else data.get("name")
        except Exception as exc:
            print(f"  ! geocoding failed for {key}: {exc}")
        self._last = time.time()
        if name:
            self.cache[key] = name
            if self.cache_path:
                os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
                with open(self.cache_path, "w", encoding="utf-8") as fh:
                    json.dump(self.cache, fh, indent=1, ensure_ascii=False)
        return name
