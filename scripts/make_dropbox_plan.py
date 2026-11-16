#!/usr/bin/env python3
"""Write docs/dropbox_gcp_albums_plan_<date>.docx -- the plan for cataloguing the Dropbox
photo bank on a Google Cloud VM as the preparation for albums. The document is GENERATED:
change the text in dropbox_plan_text.py (beside this file) and run this again; a revision is a new
dated file beside the old one.

    py -3 scripts\\make_dropbox_plan.py [--date YYYY-MM-DD]

Needs python-docx and PIL (both in requirements.txt already)."""
import argparse
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

from shared.config import RepoPaths

import dropbox_plan_text as T

FILE_STEM = 'dropbox_gcp_albums_plan'
FONT_BODY, FONT_CODE = 'Calibri', 'Consolas'
PT_BODY, PT_CODE, PT_TABLE, PT_H1, PT_H2, PT_TITLE = 10.5, 9.0, 9.5, 15, 12, 19
MARGIN_MM, PAGE_W_MM, PAGE_H_MM = 19.4, 210, 297
TEXT_W_MM = PAGE_W_MM - 2 * MARGIN_MM
STEP_MM = 7.5      # where a numbered step's text starts; wide enough for '10.'
INK, GRAY, SHADE_HEAD, SHADE_CODE = '222222', '666666', 'E7ECF2', 'F2F2F2'
_MARK = re.compile(r'(\*\*.+?\*\*|`.+?`)')


# ---- the figure
def _font(size: int, bold: bool = False):
    for name in (('calibrib.ttf' if bold else 'calibri.ttf'), 'arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _box(d, xy, title, lines, fill, edge, dashed=False):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, radius=16, fill=fill, outline=None if dashed else edge, width=3)
    if dashed:
        for x in range(x0, x1, 26):
            d.line([(x, y0), (min(x + 14, x1), y0)], fill=edge, width=3)
            d.line([(x, y1), (min(x + 14, x1), y1)], fill=edge, width=3)
        for y in range(y0, y1, 26):
            d.line([(x0, y), (x0, min(y + 14, y1))], fill=edge, width=3)
            d.line([(x1, y), (x1, min(y + 14, y1))], fill=edge, width=3)
    f_t, f_l = _font(30, True), _font(25)
    h = 38 + 32 * len(lines)
    y = (y0 + y1 - h) // 2
    d.text(((x0 + x1) // 2, y), title, font=f_t, fill='#' + INK, anchor='ma')
    for i, line in enumerate(lines):
        d.text(((x0 + x1) // 2, y + 40 + 32 * i), line, font=f_l, fill='#444444', anchor='ma')


def _arrow(d, pts, n, color='#333333', dashed=False, at=0.5):
    for a, b in zip(pts, pts[1:]):
        if dashed:
            (ax, ay), (bx, by) = a, b
            steps = max(int((abs(bx - ax) + abs(by - ay)) / 22), 1)
            for i in range(0, steps, 2):
                p = (ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps)
                q = (ax + (bx - ax) * min(i + 1, steps) / steps, ay + (by - ay) * min(i + 1, steps) / steps)
                d.line([p, q], fill=color, width=4)
        else:
            d.line([a, b], fill=color, width=4)
    (ax, ay), (bx, by) = pts[-2], pts[-1]
    ux, uy = (bx - ax), (by - ay)
    n_ = max((ux * ux + uy * uy) ** 0.5, 1)
    ux, uy = ux / n_, uy / n_
    d.polygon([(bx, by), (bx - 22 * ux - 11 * uy, by - 22 * uy + 11 * ux),
               (bx - 22 * ux + 11 * uy, by - 22 * uy - 11 * ux)], fill=color)
    # the number sits on the longest leg
    legs = sorted(zip(pts, pts[1:]), key=lambda s: -(abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1])))
    (ax, ay), (bx, by) = legs[0]
    cx, cy = ax + (bx - ax) * at, ay + (by - ay) * at
    d.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill='white', outline=color, width=3)
    d.text((cx, cy), str(n), font=_font(28, True), fill=color, anchor='mm')


def draw_architecture() -> bytes:
    W, H = 2000, 1060
    im = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(im)
    blue, green, sand, gray = ('#EAF2FB', '#2F6FB0'), ('#EAF5EC', '#3D8B4F'), ('#FBF2E5', '#B9772E'), ('#F4F4F4', '#888888')
    f_c = _font(32, True)
    for xy, title, (fill, edge) in (((30, 30, 530, 620), 'Dropbox (your account)', blue),
                                    ((640, 30, 1340, 790), 'Google Cloud project', green),
                                    ((1450, 30, 1970, 790), 'This PC', sand)):
        d.rounded_rectangle(xy, radius=22, fill=fill, outline=edge, width=4)
        d.text(((xy[0] + xy[2]) // 2, xy[1] + 18), title, font=f_c, fill=edge, anchor='ma')
    white = 'white'
    _box(d, (70, 130, 490, 300), 'Photo bank', ['the originals', 'never changed'], white, blue[1])
    _box(d, (70, 400, 490, 570), 'Dropbox app', ['read-only identity', 'of this system'], white, blue[1])
    _box(d, (690, 130, 1290, 320), 'VM: the catalog job', ['inventory, fetch, analyse,', 'group, publish, power off'], white, green[1])
    _box(d, (690, 420, 970, 590), 'Bucket', ['the catalog'], white, green[1])
    _box(d, (1010, 420, 1290, 590), 'Secret Manager', ['the Dropbox link'], white, green[1])
    _box(d, (1490, 130, 1930, 300), 'Fennec IT', ['builds, starts, stops', 'and deletes the VM'], white, sand[1])
    _box(d, (1490, 420, 1930, 590), 'dropbox_connect.py', ['run once'], white, sand[1])
    _box(d, (1490, 640, 1930, 770), 'Fennec Images', ['Library and Albums'], white, sand[1])
    _box(d, (690, 890, 1290, 1030), 'fennecsig.com Worker', ['later: hears that Dropbox changed'], gray[0], gray[1], dashed=True)
    _arrow(d, [(490, 215), (690, 215)], 1)
    _arrow(d, [(1150, 420), (1150, 320)], 2)
    _arrow(d, [(830, 320), (830, 420)], 3)
    _arrow(d, [(830, 590), (830, 705), (1490, 705)], 4, at=0.62)
    _arrow(d, [(1490, 215), (1290, 215)], 5)
    _arrow(d, [(1490, 505), (1290, 505)], 6)
    _arrow(d, [(280, 620), (280, 840), (1710, 840), (1710, 770)], 7, at=0.3)
    _arrow(d, [(140, 620), (140, 960), (690, 960)], 8, color='#888888', dashed=True, at=0.6)
    out = io.BytesIO()
    im.save(out, 'PNG', optimize=True)
    return out.getvalue()


# ---- docx helpers
def _shade(el, hex_fill: str) -> None:
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_fill)
    el.append(shd)


def _run(par, text, size, bold=False, italic=False, code=False, color=INK, exact=False):
    r = par.add_run(text)
    name = FONT_CODE if code else FONT_BODY
    r.font.name = name
    rpr = r._element.get_or_add_rPr()
    fonts = rpr.find(qn('w:rFonts'))
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        fonts.set(qn(attr), name)
    # a word of code inside a sentence is set a little smaller, so it sits on the line
    r.font.size = Pt(size - (1 if size >= 10 else 0.5) if code and not exact else size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = RGBColor.from_string(color)
    return r


def _rich(par, text, size, bold=False, italic=False, color=INK):
    """**bold** and `code` inside a sentence."""
    for part in _MARK.split(text):
        if not part:
            continue
        if part.startswith('**'):
            _run(par, part[2:-2], size, bold=True, italic=italic, color=color)
        elif part.startswith('`'):
            _run(par, part[1:-1], size, bold=bold, code=True, color=color)
        else:
            _run(par, part, size, bold=bold, italic=italic, color=color)


def _space(par, before=0, after=4, line=1.08, keep=False):
    f = par.paragraph_format
    f.space_before, f.space_after, f.line_spacing = Pt(before), Pt(after), line
    f.keep_with_next = keep


class Doc:
    def __init__(self):
        self.d = Document()
        sec = self.d.sections[0]
        sec.page_width, sec.page_height = Mm(PAGE_W_MM), Mm(PAGE_H_MM)
        sec.left_margin = sec.right_margin = Mm(MARGIN_MM)
        sec.top_margin = sec.bottom_margin = Mm(17.6)
        st = self.d.styles['Normal']
        st.font.name, st.font.size = FONT_BODY, Pt(PT_BODY)
        self._footer(sec)
        self.n_tables = self.n_code = 0

    def _footer(self, sec):
        p = sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = _run(p, '', 9, color=GRAY)
        for kind, text in (('begin', None), (None, 'PAGE'), ('end', None)):
            if kind:
                el = OxmlElement('w:fldChar')
                el.set(qn('w:fldCharType'), kind)
            else:
                el = OxmlElement('w:instrText')
                el.set(qn('xml:space'), 'preserve')
                el.text = text
            r._element.append(el)

    def title(self, text, sub):
        p = self.d.add_paragraph()
        _run(p, text, PT_TITLE, bold=True)
        _space(p, after=2)
        p = self.d.add_paragraph()
        _run(p, sub, 10, color=GRAY)
        _space(p, after=10)

    def h1(self, text):
        p = self.d.add_paragraph(style='Heading 1')
        _run(p, text, PT_H1, bold=True)
        _space(p, before=14, after=5, keep=True)

    def h2(self, text):
        p = self.d.add_paragraph(style='Heading 2')
        _run(p, text, PT_H2, bold=True)
        _space(p, before=9, after=3, keep=True)

    def p(self, text, italic=False, color=INK, after=5, keep=False):
        p = self.d.add_paragraph()
        _rich(p, text, PT_BODY, italic=italic, color=color)
        _space(p, after=after, keep=keep)
        return p

    def _hang(self, mark, text, left_mm=6.5, hang_mm=5.0, after=2.5):
        p = self.d.add_paragraph()
        f = p.paragraph_format
        f.left_indent, f.first_line_indent = Mm(left_mm), Mm(-hang_mm)
        f.tab_stops.add_tab_stop(Mm(left_mm))
        _run(p, mark + '\t', PT_BODY, bold=mark[0].isdigit())
        _rich(p, text, PT_BODY)
        _space(p, after=after)
        return p

    def bullets(self, items):
        for i, it in enumerate(items):
            self._hang('•', it, after=6 if i == len(items) - 1 else 2.5)

    def steps(self, items, start=1):
        """Numbered by hand, so every list starts where it says. An item is a sentence, or
        (sentence, [command lines]), or (sentence, [command lines], sentence after)."""
        for i, it in enumerate(items, start):
            text, cmds, tail = (it, [], '') if isinstance(it, str) else (tuple(it) + ('',))[:3]
            last = i == start + len(items) - 1
            self._hang('%d.' % i, text, left_mm=STEP_MM, hang_mm=STEP_MM - 1, after=6 if last and not cmds else 2.5)
            if cmds:
                self.code(cmds, left_mm=STEP_MM)
            if tail:
                p = self.p(tail, after=3)
                p.paragraph_format.left_indent = Mm(STEP_MM)

    def code(self, lines, left_mm=0.0):
        self.n_code += len(lines)
        for i, line in enumerate(lines):
            p = self.d.add_paragraph()
            _run(p, line, PT_CODE, code=True, exact=True)
            _space(p, before=2 if i == 0 else 0, after=5 if i == len(lines) - 1 else 0, line=1.0)
            p.paragraph_format.left_indent = Mm(left_mm)
            _shade(p._p.get_or_add_pPr(), SHADE_CODE)

    def table(self, head, rows, widths, size=PT_TABLE):
        """widths: relative; scaled to the text width."""
        self.n_tables += 1
        scale = TEXT_W_MM / float(sum(widths))
        t = self.d.add_table(rows=1 + len(rows), cols=len(head))
        t.style = 'Table Grid'
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for r_i, cells in enumerate([head] + list(rows)):
            for c_i, text in enumerate(cells):
                cell = t.cell(r_i, c_i)
                cell.width = Mm(widths[c_i] * scale)
                par = cell.paragraphs[0]
                _rich(par, str(text), size, bold=(r_i == 0))
                _space(par, before=1.5, after=1.5, line=1.0)
                if r_i == 0:
                    _shade(cell._tc.get_or_add_tcPr(), SHADE_HEAD)
        tr_pr = t.rows[0]._tr.get_or_add_trPr()
        rep = OxmlElement('w:tblHeader')
        rep.set(qn('w:val'), 'true')
        tr_pr.append(rep)
        gap = self.d.add_paragraph()
        _space(gap, after=4, line=0.6)

    def figure(self, png: bytes, caption: str):
        p = self.d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(io.BytesIO(png), width=Mm(TEXT_W_MM))
        _space(p, before=4, after=2, keep=True)
        c = self.d.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _rich(c, caption, 9.5, italic=True, color=GRAY)
        _space(c, after=8)


_KINDS = ('h1', 'h2', 'p', 'note', 'bullets', 'steps', 'code', 'table', 'figure')


def build(date: str) -> Path:
    doc = Doc()
    y, m, d = (int(x) for x in date.split('-'))
    doc.title(T.TITLE, T.SUBTITLE % ('%d %s %d' % (d, T.MONTHS[m - 1], y)))
    for block in T.BLOCKS:
        kind, body = block[0], block[1:]
        assert kind in _KINDS, kind
        if kind == 'note':
            doc.p(body[0], italic=True, color=GRAY)
        elif kind == 'figure':
            doc.figure(draw_architecture(), body[0])
        elif kind == 'steps':
            doc.steps(body[0], start=body[1] if len(body) > 1 else 1)
        elif kind == 'table':
            doc.table(*body)
        else:
            getattr(doc, kind)(*body)
    path = RepoPaths.path_dir_docs / ('%s_%s.docx' % (FILE_STEM, date))
    doc.d.core_properties.title = T.TITLE
    doc.d.core_properties.author = 'Fennec Images'
    doc.d.save(str(path))
    print('wrote %s: %d blocks, %d tables, %d command lines' % (path, len(T.BLOCKS), doc.n_tables, doc.n_code))
    return path


def main() -> bool:
    ap = argparse.ArgumentParser(description='Write the Dropbox / GCP / albums plan document.')
    ap.add_argument('--date', default=T.DATE, help='the date in the file name and the title block')
    build(ap.parse_args().date)
    return True


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
