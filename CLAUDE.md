CONTRIBUTING.MD
---------------
See CLAUDE_GENERAL.md for the author's general coding rules, coding style, GUI terminology/
layout conventions, and MD file conventions that apply to ALL projects. Do not repeat that
general content here.

REPO INTENT
-----------
Fennec Images: a desktop GUI over the household's photo and message folders.
- Classify tab: sort a folder's files (a WhatsApp export, typically) into photos by what
  happened (Trip / Party / Other photo) and text-bearing images and documents by what they say
  (Advertisement / School message / Notification / Document). Everything runs on this machine.
- Albums tab: the fennec_album pipeline (scan, events, select, enhance, layout, PDF) behind
  buttons. fennec_album/ and album.py predate the GUI and still work as a CLI (README.md).
- Prompts and General tabs: the same tabs as in C:\vc\fennec\fennec-bookkeeping.

REPO STRUCTURE
--------------
```
fennec-images/
    CLAUDE.md  CLAUDE_GENERAL.md  README.md  requirements.txt  album.py
    docs/prompts.csv        the development log the Prompts tab works from
    log/                    gitignored; claude_prompt.txt, launch_images.log
    assets/                 fennec-images.ico (scripts/make_icons.py draws it, light green F)
    scripts/                make_icons.py, make_shortcuts.vbs
    shared/                 copied from fennec-bookkeeping/shared -- keep in step with it
    fennec_album/           the album engine (CLI + browser editor), untouched by the GUI work
    fennec_images/
        config.py           ALL constants of the app + re-export of shared.config classes
        gui/run.py          entry point (puts the repo root and .venv on sys.path)
        gui/app.py          ImagesApp: the notebook, tab order, state hooks
        gui/app_base.py     AppBaseMixin, copied from bookkeeping personal/gui/app_base.py
        gui/common.py       log pane, tree builder, open_path
        gui/classify_tab.py ClassifyTabMixin
        gui/albums_tab.py   AlbumsTabMixin
        gui/general_tab.py  GeneralTabMixin, copied from bookkeeping personal/gui
        gui/run_images.bat + gui/run_gui.vbs   the launchers
        src/classify.py     the classifier, event smoothing, the result cache (no tkinter)
        src/clip_model.py   CLIP zero-shot on onnxruntime, own BPE tokenizer (no torch)
        src/extract_text.py OCR (tesseract.exe), pdf, docx, html, txt, xlsx text
        src/override.py     the OVERRIDE POLICY (Skip / Override / Bak)
        log/                daily log files (gitignored)
```

SHARED LAYER (copied from fennec-bookkeeping)
---------------------------------------------
shared/ (config, utils, layout_profiles, prompts_log, prompts_tab) and gui/app_base.py,
gui/general_tab.py are COPIES of the bookkeeping repo's files, changed only where that repo
names its two apps (icons, launch logs, the prompt texts, categories, the model list). Their
behavior -- Screen profiles, sash and column-width persistence, restart modes, the Prompts tab
with its Code/Chat runs and the RIGHT-CLICK New request from anywhere -- is documented in
C:\vc\fennec\fennec-bookkeeping\CLAUDE.md and is not repeated here. A fix there is a fix here.
The right-click is bound by PromptsTabMixin._bind_prompts_right_click (bind_all), so every new
tab and dialog gets it for free; a widget with its own Button-3 binding keeps its menu.

RUNNING
-------
Desktop shortcut "Fennec Images.lnk" (rewritten by run_images.bat on every launch), or
  py -3 fennec_images\gui\run.py
The .bat uses <repo>\.venv when it exists, otherwise the py launcher (Python 3.11 here has
every package of requirements.txt). State: %APPDATA%\fennec_images\state.json.

CLASSIFY TAB
------------
Layout: Folder entry + Browse/Reload on top; left Files table (checkbox, Size, Class, Conf.,
Text, Name; All/None; a Show filter by class); right Actions (Classify Checked, Stop, model/OCR
switches, Download Model, Set Class, Open File, Copy to Class Folders + If exists policy) over
a Preview (image or pdf page 1, plus the class, the reason and the text read); log at the
bottom. Actions work on the CHECKED rows, or the selected ones when none is checked.
Text column: the text read, on one line. Double-click on it opens a window with all the text
(Copy, Close, Esc). The cache keeps only TEXT_SNIPPET (600) characters, so when the cached
text is that long or missing, the window re-reads the file (OCR / document text) on a
background thread. A double-click on any other column opens the file.
How a file is classified (src/classify.py):
- Image: CLIP scores four groups (trip / party / other / text, ClipModel.PROMPTS, each group
  the best of several prompts, then a softmax). Tesseract runs unless CLIP rules text out
  (p_text <= 0.15), and only words of confidence >= ClassifyOcr.MIN_CONF count. A text image
  is: words >= WORDS_TEXT_SURE, or p_text >= CLIP_TEXT_SURE (stylized Hebrew flyers OCR badly),
  or p_text >= CLIP_TEXT_MAYBE with words >= WORDS_TEXT_MAYBE. Otherwise the best photo group.
- Text class: ClassifyRules.KEYWORDS (substring counts, Hebrew first) + PATTERNS (time, date,
  price, percent; capped) + for images a CLIP prior over ClipModel.PROMPTS_TEXT (worth two
  keyword hits). Advertisement = commercial; Notification = an event/date/change announcement
  (community events, seminars); School message = school/kindergarten/parents; Document = forms,
  receipts, contracts, long text.
- Documents (pdf docx html txt xlsx): their text, same rules. A pdf with no text layer has its
  first ClassifyFiles.PDF_OCR_PAGES pages OCR'd.
- Event smoothing (smooth_by_events, after every run, over the whole folder): photos within
  ClassifyRules.EVENT_GAP_H of each other form an event; when trip or party dominates it, its
  weak members (Trip/Party below EVENT_OWN_CONF, Other below EVENT_OTHER_CONF) take that class.
  File time = timestamp in the name (WhatsApp 'YYYY-MM-DD HHMMSS_'), else EXIF, else mtime.
- Without the model: heuristic_photo (faces via OpenCV Haar, sky, greenery) and OCR words.
- Set Class marks a result manual: smoothing and later runs never change it.
- Cache: %LOCALAPPDATA%\fennec_images\classify_cache.json keyed by path|size|mtime. A cached
  result made without CLIP is redone when the model is available. "Ignore cache" redoes all.
- Model: Xenova/clip-vit-base-patch32 quantized onnx (~150 MB) in
  %LOCALAPPDATA%\fennec_images\models, fetched once by Download Model; inference is local, about
  40 ms an image. The tokenizer was checked against CLIP's ids ('a photo of a cat').
- Speed: the 148 files of the 2026-10-29 WhatsApp test folder take ~10 s (6 OCR threads; the
  onnx session is shared under a lock).
- Copy to Class Folders copies into <folder>\<class>\ through src/override.prepare.

ALBUMS TAB
----------
Build settings (photos folder, album folder, count, title, page size, gap hours, jump km,
diversity, enhance, geocode) and the loaded album's events on the left; Build / Load / Open
Editor / Export PDF / Re-layout / Open Folder on the right. Pipeline calls run on a background
thread with their prints redirected into the log (_QueueWriter); the pipeline reports user
errors by SystemExit, which is caught. Open Editor starts fennec_album.server.serve on a daemon
thread (first free port from 8765), one per album folder, alive while the app is open.

CONFIG MODULE
-------------
fennec_images/config.py: ImagesConfig (identity, local dir), ImagesState (state.json keys),
SashConfig (adds the tabs' sash keys), ClassifyClasses, ClassifyFiles, ClassifyOcr, ClipModel,
ClassifyRules, UIStrings(CommonUIStrings), OverridePolicy; plus the shared classes re-exported.
Thresholds and keyword lists live there, never inline.
