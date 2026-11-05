"""Small tkinter helpers shared by the app's tabs: the checkbox glyphs, the log pane every tab
ends with, a checkbox table with All/None, opening a file with its own program."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from fennec_images import config

_ST = config.StyleConfig
_UI = config.UIStrings

CHK_ON = '☑'
CHK_OFF = '☐'


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
