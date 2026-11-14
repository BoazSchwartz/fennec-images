"""The classification of a folder, saved in the folder itself: <folder>\\fennec_images\\
classification.xlsx (ClassifySheet), one row per file with its class and the text read.
Rewritten whole on every save; read back on load for files the local cache does not hold.
No tkinter."""
from __future__ import annotations

import json
import os
from datetime import datetime

from fennec_images.config import ClassifySheet as _SH


def sheet_path(path_dir: str) -> str:
    return os.path.join(path_dir, _SH.DIR_OUT, _SH.FILE_XLSX)


def _clean(v):
    """A string openpyxl can store: control characters become spaces."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    return ILLEGAL_CHARACTERS_RE.sub(' ', v) if isinstance(v, str) else v


def write_sheet(path_dir: str, rows: list) -> str:
    """rows: the tab's row dicts (name, size, mtime, kind, res). The file is the app's own
    output, so it is replaced (Override); written to a temp file first. Returns its path."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = _SH.SHEET
    ws.append(_SH.COLUMNS)
    for r in sorted(rows, key=lambda r: r['name'].lower()):
        res = r['res']
        vals = [r['name'], r['size'], datetime.fromtimestamp(r['mtime']).strftime('%Y-%m-%d %H:%M'),
                r['kind']]
        if res:
            vals += [res.cls, res.conf, 'yes' if res.manual else '', res.method, res.words,
                     len(res.faces), _SH.PEOPLE_SEP.join(res.people), res.reason,
                     json.dumps(res.scores) if res.scores else '', res.text]
        ws.append([_clean(v) for v in vals])
        for c in ws[ws.max_row]:
            if isinstance(c.value, str) and c.value.startswith('='):
                c.data_type = 's'          # OCR text starting with '=' stays text
    for i, col in enumerate(_SH.COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = _SH.WIDTHS.get(col, 12)
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = ws.dimensions
    path = sheet_path(path_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    wb.save(tmp)
    os.replace(tmp, path)
    return path


def read_sheet(path_dir: str) -> dict:
    """{name: {'size': int, 'res': dict of Result fields}} of the classified rows; {} when
    there is no sheet or it cannot be read."""
    path = sheet_path(path_dir)
    if not os.path.isfile(path):
        return {}
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return {}
    out = {}
    try:
        ws = wb[_SH.SHEET] if _SH.SHEET in wb.sheetnames else wb.active
        it = ws.iter_rows(values_only=True)
        head = [str(h or '') for h in next(it, ())]
        if _SH.COL_NAME not in head or _SH.COL_CLASS not in head:
            return {}
        for vals in it:
            d = dict(zip(head, vals))
            name, cls = d.get(_SH.COL_NAME), d.get(_SH.COL_CLASS)
            if not name or not cls:
                continue
            try:
                scores = json.loads(d.get(_SH.COL_SCORES) or '{}')
            except ValueError:
                scores = {}
            text = str(d.get(_SH.COL_TEXT) or '')
            people = [p for p in str(d.get(_SH.COL_PEOPLE) or '').split(_SH.PEOPLE_SEP) if p]
            # The sheet has no face embeddings, so the face pass is marked not done (+faces)
            out[str(name)] = {'size': int(d.get(_SH.COL_SIZE) or -1), 'res': {
                'path': os.path.join(path_dir, str(name)), 'cls': str(cls),
                'conf': float(d.get(_SH.COL_CONF) or 0.0), 'kind': str(d.get(_SH.COL_KIND) or ''),
                'method': str(d.get(_SH.COL_METHOD) or '').replace(_SH.METHOD_FACES, ''),
                'words': int(d.get(_SH.COL_WORDS) or 0),
                'scores': scores, 'reason': str(d.get(_SH.COL_REASON) or ''), 'text': text,
                'manual': d.get(_SH.COL_MANUAL) == 'yes', 'people': people,
                'text_full': bool(text.strip()) and len(text) < _SH.TEXT_MAX}}
    except (ValueError, TypeError):
        return out
    finally:
        wb.close()
    return out
