# fennec-album

Turn a folder of photos into a printable photo album: scan, group into
events, pick the best shots, auto-enhance, lay out pages, review/edit in
the browser, export a print-ready PDF.

```
py -3 -m pip install -r requirements.txt

py -3 album.py build  "D:\Photos\Italy 2025" --out .\italy_album --count 60 --title "Italy 2025"
py -3 album.py serve  .\italy_album            # opens http://127.0.0.1:8765/
py -3 album.py export .\italy_album --bleed 3  # writes italy_album\album.pdf
```

## What `build` does

1. **Scan** every image under the folder (jpg, png, webp, tiff, heic with
   `pillow-heif`). Reads the EXIF capture date and GPS, fixes orientation,
   writes thumbnails to `<album>/cache/`.
2. **Group into events.** Photos are sorted by time and split where there is
   a gap of more than `--gap-hours` (default 3) or a GPS jump of more than
   `--jump-km` (default 3). GPS positions are clustered into places; with
   `--geocode` places are named via OpenStreetMap (needs network), otherwise
   they are "Place 1", "Place 2"… and the event name is the date plus the
   place or time of day. Rename events in the editor.
3. **Select `--count` photos.** Each photo gets an interest score from
   sharpness, detail, colourfulness, entropy, contrast, exposure and
   resolution. Burst shots / re-takes are folded into one "moment" using a
   perceptual hash, a colour signature and capture time. Each event gets a
   quota that grows with the square root of its number of moments (big events
   get more pages, tiny ones still appear), and within an event photos are
   picked greedily by score with a diversity penalty (`--diversity`) so the
   picks are spread over time and don't look alike.
4. **Enhance** the chosen photos: level stretch, gamma lift for dark shots,
   gentle contrast curve for flat ones, a touch of saturation, print
   sharpening (`--no-enhance` / `--enhance-strength`). Full-size results go to
   `<album>/photos/`. A focus point is detected per photo so crops keep the
   interesting part.
5. **Lay out pages.** A cover with a title band, then pages per event with a
   varied rhythm: 1 to 6 photos per page from ~25 templates (full-bleed hero,
   big-left + stack, mosaics, grids…). The highest-scoring photo of a page
   goes in the biggest slot and photos are matched to slots by aspect ratio.
   Page sizes: `--page a4-landscape | a4-portrait | letter-* | square-8in |
   square-10in | a3-landscape`.

Everything is saved to `<album>/album.json`.

## The editor (`serve`)

* ← / → or the filmstrip to move between pages.
* Click a photo to select it. The right panel shows unused photos from the
  same event (tab "All unused" for the whole library); click one to replace.
* **Set focus**, then click on the photo where the crop should be centred.
* **Swap**: click another photo on any page to exchange them.
* **Remove** a photo from a page (the page re-flows), **Add mode** to add a
  candidate to the page (up to 6).
* **Shuffle layout** / template dropdown to change a page's layout;
  **Re-layout all** rebuilds every page with a new rhythm.
* Edit the caption field and **Rename event** to rename an event everywhere.
* Title / subtitle fields at the top. **Export PDF** writes
  `<album>/album.pdf`.

## Export

`export` writes a PDF at `--dpi` (300 default) with vector text and
embedded photos cropped exactly as shown in the editor. `--bleed 3` adds a
3 mm bleed on every side for professional printing. `--previews DIR` also
writes a JPEG of every page.

## Testing

`py -3 tools/make_demo_photos.py demo_photos --count 90` writes a synthetic
library (EXIF dates + GPS, bursts, blurry and dark shots) to try the tool on.

## Layout of the code

```
album.py                 CLI
fennec_album/scan.py     discovery, EXIF, metrics, perceptual hash, scoring
fennec_album/events.py   event splitting, place clustering, geocoding
fennec_album/select.py   duplicate folding, quotas, diverse greedy pick
fennec_album/enhance.py  auto-enhance, saliency, focus point, cropping
fennec_album/layout.py   page templates, slot assignment, page rhythm
fennec_album/render.py   PDF export (reportlab) and JPEG previews
fennec_album/server.py   local editor API (stdlib http.server)
fennec_album/static/viewer.html  the editor UI
fennec_album/pipeline.py build orchestration
```
