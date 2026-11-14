"""Small tkinter helpers shared by the app's tabs: the checkbox glyphs, the log pane every tab
ends with, a checkbox table with All/None, the folder-path entry, opening a file with its own
program."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont, ttk

from fennec_images import config

_ST = config.StyleConfig
_UI = config.UIStrings

CHK_ON = '☑'
CHK_OFF = '☐'
LRM = '‎'                        # left-to-right mark
_RTL_RUN = re.compile(r'[֐-ࣿ]+(?: +[֐-ࣿ]+)*')


def build_log_pane(log_frame) -> tk.Text:
    hdr = ttk.Frame(log_frame)
    hdr.pack(fill='x', pady=(2, 0))
    ttk.Label(hdr, text=_UI.HDR_LOG, font=(_ST.FONT_FAMILY, 10, 'bold')).pack(side=tk.LEFT, padx=6)
    txt = tk.Text(log_frame, wrap='word', state='disabled', background=_ST.LOG_BG,
                  foreground=_ST.LOG_FG, font='TkFixedFont', relief='flat', borderwidth=0)
    ttk.Button(hdr, text='Clear', command=lambda: clear_text(txt)).pack(side=tk.RIGHT, padx=6)
    vsb = ttk.Scrollbar(log_frame, orient='vertical', command=txt.yview)
    txt.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill='y')
    txt.pack(fill=tk.BOTH, expand=True, padx=(6, 0), pady=(2, 4))
    return txt


def clear_text(txt) -> None:
    txt.configure(state='normal')
    txt.delete('1.0', tk.END)
    txt.configure(state='disabled')


def set_text(txt, text: str) -> None:
    txt.configure(state='normal')
    txt.delete('1.0', tk.END)
    txt.insert('1.0', text)
    txt.configure(state='disabled')


def build_tree(parent, cols, labels, widths, sort_cmd=None) -> ttk.Treeview:
    """A Treeview with a vertical scrollbar; the LAST column stretches (CLAUDE_GENERAL.md)."""
    frame = ttk.Frame(parent)
    frame.pack(fill=tk.BOTH, expand=True)
    tv = ttk.Treeview(frame, columns=cols, show='headings', selectmode='extended')
    for i, c in enumerate(cols):
        last = i == len(cols) - 1
        tv.heading(c, text=labels[c], anchor='w',
                   command=(lambda col=c: sort_cmd(col)) if sort_cmd else '')
        tv.column(c, width=widths.get(c, 100), anchor='w', stretch=last,
                  minwidth=config.LayoutConfig.MIN_COL_WIDTH if c != 'sel' else 24)
    vsb = ttk.Scrollbar(frame, orient='vertical', command=tv.yview)
    tv.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill='y')
    tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tv.tag_configure('row_even', background=_ST.ROW_EVEN_BG)
    tv.tag_configure('row_odd', background=_ST.ROW_ODD_BG)
    return tv


def restripe(tv) -> None:
    for i, iid in enumerate(tv.get_children('')):
        extra = [t for t in tv.item(iid, 'tags') if t not in ('row_even', 'row_odd')]
        tv.item(iid, tags=tuple(['row_even' if i % 2 == 0 else 'row_odd'] + extra))


def open_path(path: str) -> None:
    if sys.platform == 'win32':
        os.startfile(path)
    else:
        subprocess.Popen(['xdg-open', path])


def clean_path(text: str) -> str:
    """A folder typed or pasted into an entry: Explorer's 'Copy as path' adds quotes, a copy
    out of a path entry carries its direction marks."""
    path = plain_text(text or '').strip().strip('"\'').strip()
    return os.path.normpath(path) if path else ''


def ltr_display(text: str) -> str:
    """The text with a left-to-right mark around each Hebrew / Arabic run, so a mixed path
    shows in its logical order: Tk's bidi rendering otherwise pulls the backslashes and the
    numbers next to the Hebrew into it ('2010 שונות\\2009_12_25' came out as
    '2010 שונות 25_12_2009\\')."""
    return _RTL_RUN.sub(lambda m: LRM + m.group(0) + LRM, text or '')


def plain_text(text: str) -> str:
    return text.replace(LRM, '')


def path_entry(parent, var: tk.StringVar, **kw) -> ttk.Entry:
    """An Entry for a folder path. `var` keeps the plain path, as before; the entry shows it
    through its own variable in logical order (ltr_display), scrolled to its end when set
    from code (Browse, the saved state), and the whole path in a tooltip when it is wider
    than the box."""
    shown = tk.StringVar(master=parent, value=ltr_display(var.get()))
    ent = ttk.Entry(parent, textvariable=shown, **kw)
    busy = [False]

    def from_var(*_a):
        if busy[0]:
            return
        busy[0] = True
        try:
            shown.set(ltr_display(var.get()))
            ent.xview_moveto(1.0)
        finally:
            busy[0] = False

    def from_entry(*_a):                # the user typing or pasting
        if busy[0]:
            return
        busy[0] = True
        try:
            var.set(plain_text(shown.get()))
        finally:
            busy[0] = False

    var.trace_add('write', from_var)
    shown.trace_add('write', from_entry)
    attach_tooltip(ent, lambda: ltr_display(var.get()) if _overflows(ent, shown.get()) else '')
    return ent


def _overflows(ent, text: str) -> bool:
    font = ent.cget('font') or ttk.Style(ent).lookup(ent.winfo_class(), 'font') or 'TkTextFont'
    return tkfont.Font(root=ent, font=font).measure(text) > ent.winfo_width() - 10 if text else False


def attach_tooltip(widget, text_fn) -> None:
    """A hover label with text_fn()'s text, none when it is empty."""
    tip = {'win': None}

    def show(_event=None):
        text = text_fn()
        if tip['win'] is not None or not text:
            return
        win = tk.Toplevel(widget)
        win.wm_overrideredirect(True)
        win.wm_geometry(f'+{widget.winfo_rootx() + 12}+{widget.winfo_rooty() + widget.winfo_height() + 4}')
        tk.Label(win, text=text, justify='left', background='#ffffe0', relief='solid',
                 borderwidth=1, padx=6, pady=3, wraplength=900).pack()
        tip['win'] = win

    def hide(_event=None):
        if tip['win'] is not None:
            tip['win'].destroy()
            tip['win'] = None

    widget.bind('<Enter>', show)
    widget.bind('<Leave>', hide)
    widget.bind('<ButtonPress>', hide)
