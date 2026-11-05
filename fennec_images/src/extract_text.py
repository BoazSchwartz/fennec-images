"""Text out of any file the Classify tab lists: OCR for images (Tesseract exe, no pytesseract),
the text layer of a pdf (OCR of its first pages when it has none), docx, html and plain text.
No tkinter. Every reader returns (text, n_confident_words, method)."""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageOps

from fennec_images.config import ClassifyFiles as _CF, ClassifyOcr as _OCR

try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except Exception:
    pass

_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0      # CREATE_NO_WINDOW: no console flash


def tesseract_exe() -> str:
    for p in _OCR.EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return shutil.which('tesseract') or ''


def open_image(path: str) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im.convert('RGB')


def ocr_image(im: Image.Image) -> tuple[str, int]:
    """(text, number of words Tesseract is confident about). Uses the TSV output so the
    noise a photo produces (low-confidence fragments) can be told apart from real text."""
    exe = tesseract_exe()
    if not exe:
        return '', 0
    w, h = im.size
    scale = _OCR.MAX_SIDE / max(w, h)
    if scale < 1:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    fd, tmp = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        im.convert('L').save(tmp)
        res = subprocess.run([exe, tmp, 'stdout', '-l', _OCR.LANGS, 'tsv'], capture_output=True,
                             timeout=_OCR.TIMEOUT_S, creationflags=_NO_WINDOW)
    except (subprocess.SubprocessError, OSError):
        return '', 0
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return _parse_tsv(res.stdout.decode('utf-8', errors='replace'))


def _parse_tsv(tsv: str) -> tuple[str, int]:
    lines, n_good = {}, 0
    for row in csv.DictReader(io.StringIO(tsv), delimiter='\t', quoting=csv.QUOTE_NONE):
        word = (row.get('text') or '').strip()
        try:
            conf = float(row.get('conf') or -1)
        except ValueError:
            conf = -1
        if not word or conf < _OCR.MIN_CONF:
            continue
        if sum(ch.isalnum() for ch in word) >= 2:
            n_good += 1
        key = (row.get('block_num'), row.get('par_num'), row.get('line_num'))
        lines.setdefault(key, []).append(word)
    return '\n'.join(' '.join(ws) for ws in lines.values()), n_good


def _count_words(text: str) -> int:
    return sum(1 for w in text.split() if sum(ch.isalnum() for ch in w) >= 2)


def read_pdf(path: str, use_ocr: bool = True) -> tuple[str, int, str]:
    import fitz  # pymupdf
    with fitz.open(path) as doc:
        text = '\n'.join(page.get_text() for page in doc)
        if len(text.strip()) >= _CF.PDF_MIN_TEXT or not use_ocr:
            return text, _count_words(text), 'pdf-text'
        parts, n = [], 0
        for page in list(doc)[:_CF.PDF_OCR_PAGES]:
            pix = page.get_pixmap(dpi=_CF.PDF_OCR_DPI)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            t, k = ocr_image(im)
            parts.append(t)
            n += k
        return '\n'.join(parts), n, 'pdf-ocr'


def read_docx(path: str) -> tuple[str, int, str]:
    import docx  # python-docx
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for r in t.rows:
            parts.append(' '.join(c.text for c in r.cells))
    text = '\n'.join(parts)
    return text, _count_words(text), 'docx'


class _HtmlText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def read_html(path: str) -> tuple[str, int, str]:
    p = _HtmlText()
    p.feed(Path(path).read_text(encoding='utf-8', errors='replace'))
    text = '\n'.join(p.parts)
    return text, _count_words(text), 'html'


def read_plain(path: str) -> tuple[str, int, str]:
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    return text, _count_words(text), 'text'


def read_xlsx(path: str) -> tuple[str, int, str]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            parts.append(' '.join(str(c) for c in row if c not in (None, '')))
    text = '\n'.join(parts)
    return text, _count_words(text), 'xlsx'


def read_document(path: str, use_ocr: bool = True) -> tuple[str, int, str]:
    """Any non-image file. ('', 0, 'none') when the type is not readable."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _CF.PDF_EXTS:
        return read_pdf(path, use_ocr)
    if ext in _CF.DOCX_EXTS:
        return read_docx(path)
    if ext in _CF.HTML_EXTS:
        return read_html(path)
    if ext in _CF.TEXT_EXTS:
        return read_plain(path)
    if ext in _CF.XLSX_EXTS:
        return read_xlsx(path)
    return '', 0, 'none'
