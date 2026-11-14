"""Classify the files of a folder -- photos by what happened (trip / party) or where (home,
restaurant, car, street, nature, work, else everyday), images with text and documents by what
they say (advertisement / school message / notification / document); and the people in the
photos (faces.py, optional). Everything runs on this machine. No tkinter.

Images:
  1. CLIP zero-shot (clip_model.py, optional) scores the photo groups (ClassifyClasses.GROUPS)
     and text.
  2. Tesseract counts the words it is CONFIDENT about -- a photo yields a few noisy
     fragments, a flyer or a screenshot dozens of real words.
  3. Text image = many confident words, or CLIP says text and there are some words.
     Then the words decide the text class (ClassifyRules.KEYWORDS), CLIP breaking ties.
     Otherwise the best of trip / party / other.
  Without CLIP: faces, sky and greenery (heuristic_photo) stand in for step 1 (trip / party /
  other only).
  4. With the face models: every face's embedding (Result.faces) and the names of the people
     it matches (Result.people); the method gets METHOD_FACES.
Documents (pdf, docx, html, txt, xlsx): their text, classified by the words.

Results are cached per (path, size, mtime) in ImagesConfig.path_dir_local, so a re-run is
instant and a manual Set Class survives a reload."""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from dataclasses import asdict, dataclass, field

import numpy as np

from fennec_images.config import (ClassifyClasses as _C, ClassifyFiles as _CF,
                                  ClassifyOcr as _OCR, ClassifyRules as _R, ClassifySheet as _SH,
                                  ClipModel as _CM, ImagesConfig as _IC)
from fennec_images.src import extract_text as xt
from fennec_images.src import faces as fc

TEXT_MAX = _SH.TEXT_MAX         # the text kept (cache and folder sheet), not a snippet
METHOD_FACES = _SH.METHOD_FACES


@dataclass
class Result:
    path: str
    cls: str = ''
    conf: float = 0.0
    kind: str = ''               # image / document / other
    method: str = ''             # clip+ocr, heuristic+ocr, pdf-text, manual ...
    words: int = 0
    scores: dict = field(default_factory=dict)
    reason: str = ''
    text: str = ''
    manual: bool = False
    text_full: bool = False      # text is all the file's text (old cache entries kept 600 chars)
    faces: list = field(default_factory=list)    # faces.FaceFinder.find, each with its 'name'
    people: list = field(default_factory=list)   # the names matched, sorted


def _cut(text: str) -> tuple[str, bool]:
    return text[:TEXT_MAX], bool(text.strip()) and len(text) <= TEXT_MAX


def file_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _CF.IMAGE_EXTS:
        return 'image'
    if ext in (_CF.PDF_EXTS | _CF.DOCX_EXTS | _CF.HTML_EXTS | _CF.TEXT_EXTS | _CF.XLSX_EXTS):
        return 'document'
    return 'other'


def list_files(path_dir: str, recursive: bool = False) -> list[dict]:
    """The folder's files, sorted by name; recursive: its subfolders' too, named by their
    path under path_dir ('sub\a.jpg'), without the album folders (ALBUM_MARK), the output
    folder and the class folders of Copy to Class Folders (these only at the top: a deeper
    'Home' or 'Work' is the user's own)."""
    rows = []
    skip_top = {_SH.DIR_OUT.lower()} | {c.lower() for c in _C.ALL}
    for dirpath, dirs, files in os.walk(path_dir):
        skip = skip_top if dirpath == path_dir else {_SH.DIR_OUT.lower()}
        dirs[:] = sorted(d for d in dirs if d.lower() not in skip
                         and not os.path.isfile(os.path.join(dirpath, d, _CF.ALBUM_MARK)))
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            rows.append({'path': path, 'name': os.path.relpath(path, path_dir), 'size': st.st_size,
                         'mtime': st.st_mtime, 'kind': file_kind(path)})
        if not recursive:
            break
    rows.sort(key=lambda r: r['name'].lower())
    return rows


def fmt_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return str(n)


# ── Words ─────────────────────────────────────────────────────────────────────

def keyword_scores(text: str) -> dict:
    low = text.lower()
    kw = {cls: sum(low.count(k.lower()) for k in kws) for cls, kws in _R.KEYWORDS.items()}
    for cls, pats in _R.PATTERNS.items():
        kw[cls] = kw.get(cls, 0) + min(_R.PATTERN_CAP, sum(len(re.findall(p, low)) for p in pats))
    return kw


def text_class(text: str, words: int, clip_prior: dict | None = None) -> tuple[str, float, str]:
    """(class, confidence, reason) of a text-bearing file."""
    kw = keyword_scores(text)
    total = sum(kw.values())
    score = {c: float(kw.get(c, 0)) for c in _C.TEXTS}
    if clip_prior:
        for c, p in clip_prior.items():
            score[c] += 2.0 * p                 # worth two keyword hits at full confidence
    if total == 0 and not clip_prior:
        cls = _C.DOCUMENT if words >= _R.DOC_LONG_WORDS else _C.NOTICE
        return cls, 0.35, f'no keyword, {words} words'
    cls = max(score, key=score.get)
    s = sorted(score.values(), reverse=True)
    conf = 0.5 + 0.5 * (s[0] - s[1]) / (s[0] + 1e-6)
    hits = ', '.join(f'{c} {n}' for c, n in kw.items() if n)
    return cls, round(min(conf, 0.99), 2), f'keywords: {hits or "none"}'


# ── Images without the model ─────────────────────────────────────────────────

_FACE = None


def _faces(gray: np.ndarray) -> int:
    global _FACE
    try:
        import cv2
    except ImportError:
        return 0
    if _FACE is None:
        _FACE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    return len(_FACE.detectMultiScale(gray, 1.15, 5, minSize=(24, 24)))


def heuristic_photo(im) -> dict:
    """Rough trip / party / other probabilities from faces, sky and greenery."""
    small = im.copy()
    small.thumbnail((640, 640))
    rgb = np.asarray(small, dtype=np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    top = rgb[: rgb.shape[0] // 3]
    sky = float(np.mean((top[..., 2] > top[..., 0] + 0.05) & (top[..., 2] > 0.45)))
    green = float(np.mean((g > r + 0.04) & (g > b + 0.02)))
    bright = float(np.mean(0.299 * r + 0.587 * g + 0.114 * b))
    gray = (np.asarray(small.convert('L'))).astype(np.uint8)
    n_faces = _faces(gray)
    outdoor = min(1.0, 1.5 * sky + green)
    trip = 0.2 + 0.8 * outdoor
    party = 0.2 + 0.25 * min(n_faces, 4) + (0.2 if bright < 0.35 else 0.0) - 0.3 * outdoor
    other = 0.45 if n_faces == 0 and outdoor < 0.25 else 0.15
    v = np.clip(np.array([trip, party, other]), 0.01, None)
    v /= v.sum()
    return {'trip': float(v[0]), 'party': float(v[1]), 'other': float(v[2]), 'faces': n_faces}


# ── The classifier ───────────────────────────────────────────────────────────

class Classifier:
    def __init__(self, use_model: bool = True, use_ocr: bool = True, log=print,
                 use_faces: bool = False, people: dict | None = None):
        self.log = log
        self.use_ocr = use_ocr and bool(xt.tesseract_exe())
        self.clip = None
        self.faces = None
        self.people = people if people is not None else {}     # shared with the tab, live
        self._lock = threading.Lock()
        if use_faces:
            if fc.model_ready():
                try:
                    self.faces = fc.FaceFinder()
                except Exception as exc:
                    log(f'[MODEL] could not load the face models, no people: {exc}\n')
            else:
                log('[MODEL] face models not downloaded, no people (Download Models to enable)\n')
        if use_model:
            from fennec_images.src import clip_model
            if clip_model.model_ready():
                try:
                    self.clip = clip_model.ClipZeroShot()
                except Exception as exc:
                    log(f'[MODEL] could not load CLIP, heuristics only: {exc}\n')
            else:
                log('[MODEL] CLIP not downloaded, heuristics only (Download Model to enable)\n')

    def classify(self, path: str) -> Result:
        kind = file_kind(path)
        try:
            if kind == 'image':
                return self._image(path)
            if kind == 'document':
                return self._document(path)
        except Exception as exc:
            return Result(path, _C.UNKNOWN, 0.0, kind, 'error', reason=f'{type(exc).__name__}: {exc}')
        return Result(path, _C.UNKNOWN, 0.0, kind, 'none', reason='file type not read')

    def _document(self, path: str) -> Result:
        text, words, method = xt.read_document(path, self.use_ocr)
        if not text.strip():
            return Result(path, _C.UNKNOWN, 0.0, 'document', method, reason='no text')
        cls, conf, why = text_class(text, words)
        text, full = _cut(text)
        return Result(path, cls, conf, 'document', method, words, reason=why, text=text,
                      text_full=full)

    def find_people(self, res: Result) -> Result:
        """The face pass alone, for a result classified before the face models were here."""
        if self.faces is not None and res.kind == 'image':
            try:
                self._faces(res, xt.open_image(res.path))
            except Exception as exc:
                res.reason += f'; faces: {type(exc).__name__}: {exc}'
        return res

    def _faces(self, res: Result, im) -> None:
        res.faces = self.faces.find(im)
        res.people = fc.name_faces(res.faces, self.people)
        if METHOD_FACES not in res.method:
            res.method += METHOD_FACES

    def _image(self, path: str) -> Result:
        im = xt.open_image(path)
        res = self._image_class(path, im)
        if self.faces is not None:
            self._faces(res, im)
        return res

    def _image_class(self, path: str, im) -> Result:
        if self.clip is not None:
            with self._lock:                    # one onnx session, many OCR threads
                emb = self.clip.embed_image(im)
                probs = self.clip.group_probs(emb, _CM.PROMPTS)
                prior = self.clip.group_probs(emb, _CM.PROMPTS_TEXT)
            method = 'clip'
        else:
            probs = heuristic_photo(im)
            probs['text'] = 0.0
            prior = None
            method = 'heuristic'
        text, words = '', 0
        # OCR every image the model does not rule out; it is what tells real text apart
        if self.use_ocr and (self.clip is None or probs['text'] > 0.15):
            text, words = xt.ocr_image(im)
            method += '+ocr'
        text, full = _cut(text)
        scores = {k: round(v, 3) for k, v in probs.items()}
        p_text = probs['text']
        is_text = words >= _OCR.WORDS_TEXT_SURE or p_text >= _OCR.CLIP_TEXT_SURE or \
            (p_text >= _OCR.CLIP_TEXT_MAYBE and (words >= _OCR.WORDS_TEXT_MAYBE or not self.use_ocr))
        if is_text:
            cls, conf, why = text_class(text, words, prior)
            conf = round(min(0.99, 0.5 * conf + 0.5 * max(p_text, min(1.0, words / 40))), 2)
            return Result(path, cls, conf, 'image', method, words, scores,
                          f'text image ({words} words, text p={p_text:.2f}); {why}', text,
                          text_full=full)
        photo = _C.GROUPS
        sub = {k: probs[k] for k in photo if k in probs}      # heuristics score three groups
        tot = sum(sub.values()) or 1.0
        best = max(sub, key=sub.get)
        why = ', '.join(f'{k} {v / tot:.2f}' for k, v in sub.items())
        return Result(path, photo[best], round(sub[best] / tot, 2), 'image', method, words, scores,
                      f'photo ({why}; {words} words)', text, text_full=full)


# ── Events ────────────────────────────────────────────────────────────────────

_NAME_TS = re.compile(r'(20\d\d)-?(\d\d)-?(\d\d)[ _-]?(\d\d)(\d\d)(\d\d)')


def file_time(path: str) -> float:
    """When the file was made: the timestamp in its name (WhatsApp / phone exports), the
    EXIF capture time, or the file's mtime -- in that order."""
    m = _NAME_TS.search(os.path.basename(path))
    if m:
        try:
            return datetime(*map(int, m.groups())).timestamp()
        except ValueError:
            pass
    if file_kind(path) == 'image':
        try:
            from PIL import Image
            with Image.open(path) as im:
                exif = im.getexif()
                v = exif.get_ifd(0x8769).get(36867) or exif.get(306)     # DateTimeOriginal, DateTime
            if v:
                return datetime.strptime(str(v).strip()[:19], '%Y:%m:%d %H:%M:%S').timestamp()
        except Exception:
            pass
    return os.path.getmtime(path)


def _photo_share(r: Result, key: str) -> float:
    tot = sum(r.scores.get(k, 0.0) for k in _C.GROUPS) or 1.0
    return r.scores.get(key, 0.0) / tot


def smooth_by_events(results: list) -> int:
    """Photos taken together share their event's class when their own call is weak. Returns
    how many changed. Manual classes and text images are never touched."""
    labels = {'trip': _C.TRIP, 'party': _C.PARTY}
    photos = sorted(((file_time(r.path), r) for r in results
                     if r.kind == 'image' and not r.manual and r.cls in _C.PHOTOS and r.scores),
                    key=lambda tr: tr[0])
    events, cur, last = [], [], None
    for t, r in photos:
        if cur and t - last > _R.EVENT_GAP_H * 3600:
            events.append(cur)
            cur = []
        cur.append(r)
        last = t
    if cur:
        events.append(cur)
    changed = 0
    for ev in events:
        if len(ev) < _R.EVENT_MIN:
            continue
        mass = {k: sum(_photo_share(r, k) for r in ev) for k in labels}
        win, lose = sorted(mass, key=mass.get, reverse=True)
        if mass[win] < _R.EVENT_DOMINANCE * mass[lose] or mass[win] < 0.3 * len(ev):
            continue
        label = labels[win]
        for r in ev:
            if r.cls == label:
                continue
            if r.conf < (_R.EVENT_OWN_CONF if r.cls in _C.EVENTS else _R.EVENT_OTHER_CONF):
                r.reason += f'; event of {len(ev)} photos is a {label.lower()} (was {r.cls} {r.conf:.2f})'
                r.cls = label
                r.method += '+event'
                changed += 1
    return changed


# ── Cache ─────────────────────────────────────────────────────────────────────

def _cache_file():
    return _IC.path_dir_local / _IC.FILE_CLASS_CACHE


def _key(path: str) -> str:
    st = os.stat(path)
    return f'{os.path.normcase(os.path.abspath(path))}|{st.st_size}|{int(st.st_mtime)}'


def load_cache() -> dict:
    try:
        return json.loads(_cache_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_cache(cache: dict) -> None:
    f = _cache_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix('.tmp')
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding='utf-8')
    os.replace(tmp, f)


def cached(cache: dict, path: str) -> Result | None:
    try:
        d = cache.get(_key(path))
    except OSError:
        return None
    return Result(**d) if d else None


def remember(cache: dict, res: Result) -> None:
    try:
        cache[_key(res.path)] = asdict(res)
    except OSError:
        pass
