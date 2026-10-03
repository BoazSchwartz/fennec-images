#!/usr/bin/env python3
"""fennec-album: turn a folder of photos into a printable photo album.

  py -3 album.py build  <photos_dir> --out <album_dir> --count 60 [--title "..."]
  py -3 album.py serve  <album_dir>                 # view + edit in the browser
  py -3 album.py export <album_dir> [--pdf out.pdf] # print-ready PDF
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fennec_album.model import Album, PAGE_SIZES_MM  # noqa: E402


def cmd_build(a: argparse.Namespace) -> None:
    from fennec_album.pipeline import build_album

    album = build_album(
        a.source,
        a.out,
        a.count,
        title=a.title,
        page_size=a.page,
        gap_hours=a.gap_hours,
        jump_km=a.jump_km,
        seed=a.seed,
        enhance=not a.no_enhance,
        enhance_strength=a.enhance_strength,
        geocode=a.geocode,
        diversity=a.diversity,
        workers=a.workers,
    )
    if a.pdf:
        cmd_export(argparse.Namespace(album=album.out_dir, pdf=a.pdf, dpi=300, bleed=0.0, previews=None))
    if a.serve:
        from fennec_album.server import serve

        serve(album.out_dir, port=a.port, open_browser=True)
    else:
        print(f"\nNext:  py -3 album.py serve \"{album.out_dir}\"   (edit in the browser)")
        print(f"       py -3 album.py export \"{album.out_dir}\"  (write the PDF)")


def cmd_serve(a: argparse.Namespace) -> None:
    from fennec_album.server import serve

    serve(a.album, port=a.port, open_browser=not a.no_browser)


def cmd_export(a: argparse.Namespace) -> None:
    from fennec_album.render import export_pdf, export_previews

    album = Album.load(a.album)
    pdf = a.pdf or os.path.join(album.out_dir, "album.pdf")
    n = len(album.pages)

    def progress(i: int, total: int) -> None:
        sys.stdout.write(f"\r  page {i}/{total}")
        sys.stdout.flush()

    export_pdf(album, pdf, dpi=a.dpi, bleed_mm=a.bleed, progress=progress)
    size_mb = os.path.getsize(pdf) / 1e6
    print(f"\nWrote {pdf}  ({n} pages, {size_mb:.1f} MB, {a.dpi} dpi" + (f", {a.bleed} mm bleed" if a.bleed else "") + ")")
    if a.previews:
        paths = export_previews(album, a.previews)
        print(f"Wrote {len(paths)} page previews to {a.previews}")


def cmd_relayout(a: argparse.Namespace) -> None:
    from fennec_album.pipeline import relayout_album

    album = relayout_album(Album.load(a.album), seed=a.seed)
    print(f"Re-laid out {len(album.pages)} pages (seed {album.seed})")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="album", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="scan photos, pick the best, enhance and lay out pages")
    b.add_argument("source", help="directory of images (searched recursively)")
    b.add_argument("--out", required=True, help="album project directory to create")
    b.add_argument("--count", type=int, required=True, help="how many photos the album should contain")
    b.add_argument("--title", help="album title (default: folder name)")
    b.add_argument("--page", default="a4-landscape", choices=sorted(PAGE_SIZES_MM), help="page size")
    b.add_argument("--gap-hours", type=float, default=3.0, help="time gap that starts a new event")
    b.add_argument("--jump-km", type=float, default=3.0, help="GPS jump that starts a new event")
    b.add_argument("--diversity", type=float, default=0.55, help="0 = pure quality, 1 = maximum variety")
    b.add_argument("--seed", type=int, default=7, help="random seed for the page rhythm")
    b.add_argument("--no-enhance", action="store_true", help="skip auto brightness/contrast/sharpening")
    b.add_argument("--enhance-strength", type=float, default=1.0, help="0..1.5, how strong the auto enhancement is")
    b.add_argument("--geocode", action="store_true", help="name places via OpenStreetMap (needs network)")
    b.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    b.add_argument("--pdf", help="also export a PDF to this path right away")
    b.add_argument("--serve", action="store_true", help="open the editor when done")
    b.add_argument("--port", type=int, default=8765)
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="open the album viewer/editor in the browser")
    s.add_argument("album", help="album project directory")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_serve)

    e = sub.add_parser("export", help="write a print-ready PDF")
    e.add_argument("album", help="album project directory")
    e.add_argument("--pdf", help="output path (default: <album>/album.pdf)")
    e.add_argument("--dpi", type=int, default=300)
    e.add_argument("--bleed", type=float, default=0.0, help="bleed in mm added around the page (e.g. 3)")
    e.add_argument("--previews", help="also write JPEG previews of each page to this directory")
    e.set_defaults(func=cmd_export)

    r = sub.add_parser("relayout", help="rebuild all pages with a new rhythm, keeping the photos")
    r.add_argument("album")
    r.add_argument("--seed", type=int)
    r.set_defaults(func=cmd_relayout)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
