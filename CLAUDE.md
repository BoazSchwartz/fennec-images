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
    fennec_album/           the album engine (CLI + browser editor); the GUI only added scan.find_images' exclude
    fennec_images/
        config.py           ALL constants of the app + re-export of shared.config classes
        gui/run.py          entry point (puts the repo root and .venv on sys.path)
        gui/app.py          ImagesApp: the notebook, tab order, state hooks
        gui/app_base.py     AppBaseMixin, copied from bookkeeping personal/gui/app_base.py
        gui/common.py       log pane, tree builder, path_entry (a bidi-safe folder entry), open_path
        gui/classify_tab.py ClassifyTabMixin
        gui/albums_tab.py   AlbumsTabMixin
        gui/general_tab.py  GeneralTabMixin, copied from bookkeeping personal/gui
        gui/run_images.bat + gui/run_gui.vbs   the launchers
        src/classify.py     the classifier, event smoothing, the result cache (no tkinter)
        src/clip_model.py   CLIP zero-shot on onnxruntime, own BPE tokenizer (no torch)
        src/extract_text.py OCR (tesseract.exe), pdf, docx, html, txt, xlsx text
        src/faces.py        people: YuNet face detection + SFace embeddings via cv2, people.json (no tkinter)
        src/override.py     the OVERRIDE POLICY (Skip / Override / Bak)
        src/class_sheet.py  the folder's classification.xlsx (write / read back, no tkinter)
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
Differences from the bookkeeping copy, to carry over or keep: PromptsLog.CATEGORIES is
app / classify / albums with CATEGORY_DEFAULT = 'app' (prompts_log.tab_category files a
right-click on the Classify or Albums tab under its own category, any other tab under 'app';
CATEGORY_DEFAULT = '' keeps the bookkeeping '<name> Tab' categories); the Prompts log pane
has a Copy button (the whole log text onto the clipboard) beside Clear.

RUNNING
-------
Desktop shortcut "Fennec Images.lnk" (rewritten by run_images.bat on every launch), or
  py -3 fennec_images\gui\run.py
The .bat uses <repo>\.venv when it exists, otherwise the py launcher (Python 3.11 here has
every package of requirements.txt). State: %APPDATA%\fennec_images\state.json.

CLASSIFY TAB
------------
Layout: Folder entry + Browse/Reload + Subfolders on top; left Files table (checkbox, Size, Class, Conf.,
People, Text, Name; All/None; a Show filter by class, Not classified, Unknown faces or a person
tagged); right Actions (Classify Checked, Stop, a status line over the progress bar, the
model/OCR/people switches, Download Models, Set Class, Tag People, Open File, Copy to Class
Folders + If exists policy) over a Preview (image or pdf page 1, plus the class, the reason,
the people and the text read); log at the bottom. Actions work on the CHECKED rows, or the
selected ones when none is checked.
Status line (UIStrings.STATUS_*): 'loading the models…', then 'completed n/x files (xx%), k
from the cache' as results land, then 'done: n/x files in s.s s, m moved to their event' (or
'stopped: ...'); it counts files, not only images, since documents are classified too.
Path entries: every folder entry (here and the Albums tab's two) is common.path_entry: the
tab's StringVar keeps the plain path, the entry shows it through its own variable with a
left-to-right mark (U+200E) around each Hebrew run (common.ltr_display), because Tk's bidi
rendering otherwise pulls the backslashes and digits next to Hebrew into the Hebrew run
('2010 שונות\2009_12_25' showed as '2010 שונות 25_12_2009\') and the path looks cut; a path
wider than the box shows whole in a tooltip. clean_path strips the marks (a copy out of the
entry carries them). The Files table and the log still render such names reordered.
Text column: the text read, on one line. Double-click on it opens a window with all the text
(Copy, Close, Esc). Results keep the whole text (up to ClassifySheet.TEXT_MAX = 32000, the
Excel cell limit) and Result.text_full says it is complete; when it is not (no text read, or
an old cache entry's 600-char snippet) the window re-reads the file (OCR / document text) on a
background thread and stores the full text back. A double-click on any other column opens it.
Subfolders (state classify_subdirs, on by default): the folder and ALL its subfolders are
listed (classify.list_files recursive), each file named by its path under the folder
('sub\a.jpg'); skipped are the app's output folders (fennec_images, the class folders) and
album folders (holding album.json). Event smoothing then runs over all of them together.
A path pasted with quotes (Explorer's Copy as path) is cleaned by common.clean_path, here and
in the Albums tab's two folders.
Folder sheet: the folder's classes and texts are saved IN the folder, in
<folder>\fennec_images\classification.xlsx (ClassifySheet: Name, Size, Modified, Kind, Class,
Conf., Manual, Method, Words, Reason, Scores, Text), one row per file, rewritten whole after
every Classify run, Set Class and full-text read (the app's own file: always replaced; an
Excel holding it open gives a logged error). On load, files the cache lacks take their result
from the sheet when name and size match, so a folder carries its classification with it.
Classes (ClassifyClasses): photos Trip, Party (EVENTS: what happened), Home, Restaurant, Car,
Street, Nature, Work (SCENES: where), Other photo; texts Advertisement, School message,
Notification, Document; Unreadable. GROUPS maps the score keys ('trip', 'home' ...) of
Result.scores / ClipModel.PROMPTS to the labels. The scene classes need CLIP: the heuristics
know trip / party / other only.
How a file is classified (src/classify.py):
- Image: CLIP scores the photo groups + text (ClipModel.PROMPTS, each group
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
  weak members (Trip/Party below EVENT_OWN_CONF, any other photo class below EVENT_OTHER_CONF)
  take that class.
  File time = timestamp in the name (WhatsApp 'YYYY-MM-DD HHMMSS_'), else EXIF, else mtime.
- Without the model: heuristic_photo (faces via OpenCV Haar, sky, greenery) and OCR words.
- Set Class marks a result manual: smoothing and later runs never change it.
- Cache: %LOCALAPPDATA%\fennec_images\classify_cache.json keyed by path|size|mtime. A cached
  result made without CLIP is redone when the model is available. "Ignore cache" redoes all.
- Model: Xenova/clip-vit-base-patch32 quantized onnx (~150 MB) in
  %LOCALAPPDATA%\fennec_images\models, fetched once by Download Models; inference is local, about
  40 ms an image. The tokenizer was checked against CLIP's ids ('a photo of a cat').
- People (src/faces.py, FaceModel): OpenCV's YuNet detector + SFace recognizer, two onnx files
  of the opencv_zoo (0.2 + 37 MB, same Download Models button, models\opencv-face), run by
  cv2 on the CPU under a lock, ~60 ms a photo reduced to MAX_SIDE. With Find people on, every
  image result keeps its faces (box, score, 128-number embedding; Result.faces, method +faces)
  and the names matched (Result.people); a cached result lacking the pass gets it alone
  (Classifier.find_people), without CLIP or OCR again. Tag People opens the selected image's
  faces with a name box each; Save stores the named embeddings in
  %LOCALAPPDATA%\fennec_images\people.json (name: faces, each with its source photo and box;
  re-tagging the same face replaces, an emptied name removes) and re-matches every loaded photo
  at once (cosine similarity >= FaceModel.MATCH_SIM to any stored face of a name). The names
  are matched again on every load, so a tag made in one folder names the person everywhere.
  The sheet holds the names and the face count only (no embeddings), so a result restored from
  it is marked without the face pass. The People cell: 'Dana, Noam +1' (names, then strangers)
  or '2 face(s)'.
- Speed: the 148 files of the 2026-10-29 WhatsApp test folder take ~10 s (6 OCR threads; the
  onnx session is shared under a lock).
- Copy to Class Folders copies into <folder>\<class>\<subfolder path>\ through
  src/override.prepare.
- With Subfolders the sheet is the top folder's (Name = the path under it); a file it lacks
  is looked up in its own subfolder's sheet, by its bare name. The class folders (Trip, Home,
  Work ...) are skipped only at the top level, where Copy to Class Folders makes them; a
  deeper folder of that name is the user's own.

ALBUMS TAB
----------
Build settings (photos folder, album folder, count, title, page size, gap hours, jump km,
diversity, enhance, geocode) and the loaded album's events on the left; Build / Load / Open
Editor / Export PDF / Re-layout / Open Folder on the right. Pipeline calls run on a background
thread with their prints redirected into the log (_QueueWriter); the pipeline reports user
errors by SystemExit, which is caught. Open Editor starts fennec_album.server.serve on a daemon
thread (first free port from 8765), one per album folder, alive while the app is open.
The photos folder is always read with all its subfolders (scan.find_images walks it; the log
says how many folders), except the album folder itself when it sits inside it (its cache holds
thousands of thumbnails). Both folders are cleaned of pasted quotes and the album folder must
be a full path: a quoted one used to resolve under the app's working folder and fail
(WinError 123). The 2010 test folder (625 photos in 61 subfolders) builds in ~25 s.

CONFIG MODULE
-------------
fennec_images/config.py: ImagesConfig (identity, local dir), ImagesState (state.json keys),
SashConfig (adds the tabs' sash keys), ClassifyClasses, ClassifyFiles, ClassifySheet,
ClassifyOcr, ClipModel, FaceModel,
ClassifyRules, UIStrings(CommonUIStrings), OverridePolicy; plus the shared classes re-exported.
Thresholds and keyword lists live there, never inline.
