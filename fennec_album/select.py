"""Pick the N most interesting photos for the album.

Steps:
1. Within each event, group near-duplicates (burst shots, re-takes) using the
   perceptual hash, the colour signature and capture time.
2. Give every event a quota that grows with the square root of its number of
   distinct moments, so big events get more pages but small ones still appear.
3. Inside each event pick greedily by score with a diversity penalty so the
   chosen photos are spread across the event in time and look different.
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from .model import Photo
from .scan import hamming

DUP_HAMMING_STRICT = 8      # looks the same regardless of time
DUP_HAMMING_LOOSE = 16      # fairly similar, and taken within a couple of minutes
DUP_SECONDS = 150


def _dt(p: Photo) -> datetime | None:
    return datetime.fromisoformat(p.ts) if p.ts else None


def _sig_distance(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 1.0
    return float(np.abs(np.asarray(a) - np.asarray(b)).sum() / 2.0)  # 0 identical .. 1 disjoint


# ------------------------------------------------------------- duplicates
def group_duplicates(photos: list[Photo], sigs: dict[str, list[float]]) -> int:
    """Union-find near-duplicate grouping; sets photo.group_id. Returns #groups."""
    parent = list(range(len(photos)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    by_event: dict[int, list[int]] = {}
    for idx, p in enumerate(photos):
        by_event.setdefault(p.event_id, []).append(idx)

    for idxs in by_event.values():
        for a_i in range(len(idxs)):
            ia = idxs[a_i]
            pa, da = photos[ia], _dt(photos[ia])
            for b_i in range(a_i + 1, len(idxs)):
                ib = idxs[b_i]
                pb, db = photos[ib], _dt(photos[ib])
                hd = hamming(pa.dhash, pb.dhash)
                if hd <= DUP_HAMMING_STRICT and _sig_distance(sigs.get(pa.id), sigs.get(pb.id)) < 0.35:
                    union(ia, ib)
                    continue
                if hd <= DUP_HAMMING_LOOSE and da and db and abs((da - db).total_seconds()) <= DUP_SECONDS:
                    if _sig_distance(sigs.get(pa.id), sigs.get(pb.id)) < 0.25:
                        union(ia, ib)

    roots: dict[int, int] = {}
    for idx, p in enumerate(photos):
        r = find(idx)
        p.group_id = roots.setdefault(r, len(roots))
    return len(roots)


# -------------------------------------------------------------- allocation
def allocate_quotas(event_groups: dict[int, int], target: int) -> dict[int, int]:
    """Number of photos per event. event_groups: event id -> #distinct groups."""
    if not event_groups or target <= 0:
        return {e: 0 for e in event_groups}
    weights = {e: math.sqrt(n) for e, n in event_groups.items()}
    total_w = sum(weights.values())
    raw = {e: target * w / total_w for e, w in weights.items()}
    quota = {e: min(event_groups[e], int(math.floor(r))) for e, r in raw.items()}
    # make sure every event is represented when the budget allows
    if target >= len(event_groups):
        for e in quota:
            if quota[e] == 0 and event_groups[e] > 0:
                quota[e] = 1
    # distribute the remainder by largest fractional part, respecting capacity
    remaining = target - sum(quota.values())
    order = sorted(raw, key=lambda e: raw[e] - math.floor(raw[e]), reverse=True)
    while remaining > 0:
        progressed = False
        for e in order:
            if remaining <= 0:
                break
            if quota[e] < event_groups[e]:
                quota[e] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    while remaining < 0:   # over-allocated by the "at least one" rule
        e = max(quota, key=lambda k: quota[k])
        if quota[e] <= 1:
            break
        quota[e] -= 1
        remaining += 1
    return quota


# --------------------------------------------------------------- selection
def _similarity(a: Photo, b: Photo, sigs: dict[str, list[float]], span_s: float) -> float:
    """0..1 how redundant b is given a is already chosen."""
    hd = hamming(a.dhash, b.dhash) / 64.0
    visual = 1.0 - min(1.0, hd / 0.45)
    color = 1.0 - min(1.0, _sig_distance(sigs.get(a.id), sigs.get(b.id)) / 0.5)
    da, db = _dt(a), _dt(b)
    if da and db and span_s > 0:
        temporal = 1.0 - min(1.0, abs((da - db).total_seconds()) / max(span_s * 0.25, 600.0))
    else:
        temporal = 0.0
    return max(0.0, 0.45 * visual + 0.25 * color + 0.30 * temporal)


def pick_from_event(photos: list[Photo], quota: int, sigs: dict[str, list[float]], diversity: float = 0.55) -> list[Photo]:
    if quota <= 0 or not photos:
        return []
    # best photo of each duplicate group is the candidate
    best_of_group: dict[int, Photo] = {}
    for p in photos:
        cur = best_of_group.get(p.group_id)
        if cur is None or p.score > cur.score:
            best_of_group[p.group_id] = p
    cands = sorted(best_of_group.values(), key=lambda p: p.score, reverse=True)
    dts = [d for d in (_dt(p) for p in photos) if d]
    span = (max(dts) - min(dts)).total_seconds() if len(dts) > 1 else 0.0

    chosen: list[Photo] = [cands[0]]
    cands[0].pick_reason = "best in event"
    rest = cands[1:]
    while len(chosen) < quota and rest:
        best_i, best_v = -1, -1e9
        for i, c in enumerate(rest):
            redundancy = max(_similarity(s, c, sigs, span) for s in chosen)
            v = c.score - diversity * redundancy
            if v > best_v:
                best_i, best_v = i, v
        pick = rest.pop(best_i)
        pick.pick_reason = f"score {pick.score:.2f}, distinct moment"
        chosen.append(pick)
    chosen.sort(key=lambda p: (p.ts or "", p.filename))
    return chosen


def select_photos(photos: list[Photo], sigs: dict[str, list[float]], target: int, diversity: float = 0.55) -> list[Photo]:
    """Mark photo.chosen for the selected photos and return them in time order."""
    for p in photos:
        p.chosen = False
        p.pick_reason = ""
    group_duplicates(photos, sigs)
    by_event: dict[int, list[Photo]] = {}
    for p in photos:
        by_event.setdefault(p.event_id, []).append(p)
    event_groups = {e: len({p.group_id for p in ps}) for e, ps in by_event.items()}
    target = min(target, sum(event_groups.values()))
    quotas = allocate_quotas(event_groups, target)
    chosen: list[Photo] = []
    for e in sorted(by_event):
        picked = pick_from_event(by_event[e], quotas.get(e, 0), sigs, diversity=diversity)
        for p in picked:
            p.chosen = True
        chosen.extend(picked)
    chosen.sort(key=lambda p: (p.ts or "", p.filename))
    return chosen


def rank_candidates(photos: list[dict], target_event: int, exclude: set[str]) -> list[dict]:
    """Candidates for replacing a slot (photo dicts as stored in album.json):
    same event first (best score first), then the rest of the library in time order."""
    same = [p for p in photos if p["event_id"] == target_event and p["id"] not in exclude]
    other = [p for p in photos if p["event_id"] != target_event and p["id"] not in exclude]
    same.sort(key=lambda p: p["score"], reverse=True)
    other.sort(key=lambda p: (p.get("ts") or "", p["filename"]))
    return same + other
