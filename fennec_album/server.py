"""Local web app to view the album and edit it (replace / swap / focus /
layout / captions) and export the PDF. Standard library only."""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .layout import reassign_page, relayout_page, template_names
from .model import Album
from .pipeline import prepare_photo, relayout_album
from .render import export_pdf
from .select import rank_candidates

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")


class AlbumState:
    def __init__(self, out_dir: str):
        self.album = Album.load(out_dir)
        self.lock = threading.Lock()

    def save(self) -> None:
        self.album.save()


def _photo_view(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p["id"],
        "filename": p["filename"],
        "ts": p.get("ts"),
        "width": p["width"],
        "height": p["height"],
        "score": p["score"],
        "event_id": p["event_id"],
        "group_id": p.get("group_id"),
        "focus": p.get("focus", [0.5, 0.5]),
        "chosen": p.get("chosen", False),
    }


def make_handler(state: AlbumState):
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter
            if "/api/" in (args[0] if args else ""):
                return

        # ---------------------------------------------------------- GET
        def do_GET(self):
            url = urlparse(self.path)
            path = url.path
            if path in ("/", "/index.html"):
                return self._file(os.path.join(STATIC, "viewer.html"), "text/html; charset=utf-8")
            if path == "/api/album":
                return self._json(self._album_payload())
            if path == "/api/candidates":
                q = parse_qs(url.query)
                page_i = int(q.get("page", ["0"])[0])
                album = state.album
                page = album.pages[page_i]
                used = album.used_photo_ids()
                eid = page.get("event_id")
                if eid is None and page["slots"]:
                    eid = album.photos[page["slots"][0]["photo_id"]]["event_id"]
                ranked = rank_candidates(list(album.photos.values()), eid if eid is not None else -1, used)
                return self._json({"event_id": eid, "candidates": [_photo_view(p) for p in ranked]})
            if path.startswith("/thumbs/"):
                return self._file(os.path.join(state.album.out_dir, "cache", "thumbs", os.path.basename(path)), "image/jpeg")
            if path.startswith("/display/"):
                return self._file(os.path.join(state.album.out_dir, "cache", "display", os.path.basename(path)), "image/jpeg")
            if path.startswith("/static/"):
                return self._file(os.path.join(STATIC, os.path.basename(path)))
            self.send_error(404)

        # --------------------------------------------------------- POST
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            route = urlparse(self.path).path
            try:
                with state.lock:
                    result = self._mutate(route, body)
                    state.save()
            except Exception as exc:  # report to the UI instead of dying
                return self._json({"error": str(exc)}, status=400)
            return self._json(result)

        def _mutate(self, route: str, body: dict[str, Any]) -> dict[str, Any]:
            album = state.album
            if route == "/api/replace":
                page = album.pages[int(body["page"])]
                slot = page["slots"][int(body["slot"])]
                pid = body["photo_id"]
                if pid not in album.photos:
                    raise ValueError("unknown photo")
                prepare_photo(album, pid)
                slot["photo_id"] = pid
                album.photos[pid]["chosen"] = True
                reassign_page(album, page)
                return self._album_payload()
            if route == "/api/swap":
                a, b = body["a"], body["b"]
                pa, pb = album.pages[int(a["page"])], album.pages[int(b["page"])]
                sa, sb = pa["slots"][int(a["slot"])], pb["slots"][int(b["slot"])]
                sa["photo_id"], sb["photo_id"] = sb["photo_id"], sa["photo_id"]
                return self._album_payload()
            if route == "/api/template":
                page = album.pages[int(body["page"])]
                relayout_page(album, page, template=body.get("template"))
                return self._album_payload()
            if route == "/api/focus":
                p = album.photos[body["photo_id"]]
                p["focus"] = [max(0.0, min(1.0, float(body["fx"]))), max(0.0, min(1.0, float(body["fy"])))]
                p["focus_set"] = True
                return self._album_payload()
            if route == "/api/event":
                ev = album.event(int(body["event_id"]))
                if ev is None:
                    raise ValueError("unknown event")
                ev["name"] = body["name"].strip()
                for page in album.pages:
                    if page.get("event_id") == ev["id"]:
                        page["caption"] = ev["name"]
                return self._album_payload()
            if route == "/api/caption":
                page = album.pages[int(body["page"])]
                page["caption"] = body["caption"]
                return self._album_payload()
            if route == "/api/title":
                album.title = body.get("title", album.title).strip() or album.title
                album.subtitle = body.get("subtitle", album.subtitle).strip()
                return self._album_payload()
            if route == "/api/remove":
                page = album.pages[int(body["page"])]
                if page["kind"] != "photos":
                    raise ValueError("cannot remove the cover photo; replace it instead")
                del page["slots"][int(body["slot"])]
                if not page["slots"]:
                    album.pages.remove(page)
                    for i, pg in enumerate(album.pages):
                        pg["index"] = i
                else:
                    relayout_page(album, page, template=None)
                return self._album_payload()
            if route == "/api/add":
                page = album.pages[int(body["page"])]
                if page["kind"] != "photos":
                    raise ValueError("cannot add to the cover")
                if len(page["slots"]) >= 6:
                    raise ValueError("a page holds at most 6 photos")
                pid = body["photo_id"]
                prepare_photo(album, pid)
                album.photos[pid]["chosen"] = True
                page["slots"].append({"photo_id": pid, "rect": [0, 0, 1, 1]})
                relayout_page(album, page, template=None)
                return self._album_payload()
            if route == "/api/relayout":
                relayout_album(album, seed=int(body["seed"]) if body.get("seed") is not None else None)
                return self._album_payload()
            if route == "/api/export":
                name = body.get("filename") or "album.pdf"
                pdf = os.path.join(album.out_dir, name)
                export_pdf(album, pdf, dpi=int(body.get("dpi", 300)), bleed_mm=float(body.get("bleed_mm", 0)))
                return {"ok": True, "path": pdf}
            raise ValueError(f"unknown route {route}")

        # ------------------------------------------------------ helpers
        def _album_payload(self) -> dict[str, Any]:
            album = state.album
            return {
                "title": album.title,
                "subtitle": album.subtitle,
                "page_size": album.page_size,
                "settings": album.settings,
                "events": album.events,
                "pages": album.pages,
                "photos": {pid: _photo_view(p) for pid, p in album.photos.items()},
                "templates": {n: template_names(album, n) for n in range(1, 7)},
                "out_dir": album.out_dir,
            }

        def _json(self, data: Any, status: int = 200) -> None:
            raw = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _file(self, path: str, ctype: str | None = None) -> None:
            if not os.path.isfile(path):
                return self.send_error(404)
            ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
            with open(path, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if path.endswith(".jpg"):
                self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(out_dir: str, port: int = 8765, open_browser: bool = True) -> None:
    state = AlbumState(out_dir)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    url = f"http://127.0.0.1:{port}/"
    print(f"Album editor running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
