"""Prompts tab -- the repo's development log docs/prompts.csv, worked from either app.

The table lists every request with the csv's own columns; a request's id is its csv row
number, the header not counted -- the same number a prompt names as "csv row N".
Refresh re-reads the file, Add appends a request stamped with the time it was written and
no executed stamp (the mark of a pending one), Edit opens the selected request with all
seven columns editable, Delete drops it (which renumbers every later request, so
prompts.csv.bak is the undo), and Code -- orange, the run that WRITES code -- opens the
run dialog: which pending requests to send, the general prompt (editable), the model,
whether to continue the previous run's context, the permission mode, extra dirs and
extra CLI args.

Chat beside it, purple, is the other half: ChatDialog is a conversation window -- the
transcript in the log pane's own colors, the message box under it -- and the run answers
into that window read-only (ClaudeRun.CHAT_PERMISSION_MODE), so a chat never edits a
file or the prompt log. Every turn after the first resumes the session the first one
opened, which is what continues the chat. Both go through _claude_start; the cfg's
'kind' is what tells them apart.

The run is headless -- claude --print with stream-json output -- spawned on the repo root
with the prompt on stdin, each event rendered into this tab's log pane. The session id is
read off the stream and kept in the app's state file, which is what makes Continue work:
the next run hands it back with --resume. Every run's prompt is written to
log/claude_prompt.txt first (a chat's to log/claude_chat.txt, so the last coding prompt
stays readable beside it), so what was sent is always on disk.

Kept in shared/ because BOTH apps carry this tab over the SAME csv, and because nothing
in it is app-specific: it needs only the infrastructure both apps already have
(_state / _append_log / _log_queue / _start_background). Both apps may show it at once --
every write re-reads the csv first and every table refresh follows the file's mtime, so
the two never overwrite each other.
"""
from __future__ import annotations

import json
import queue
import shlex
import shutil
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from shared import prompts_log as plog
from shared.config import (ClaudeModels, ClaudeRun, CommonUIStrings, LayoutConfig,
                           PromptsLog, PromptsState, RepoPaths, SashConfig, StyleConfig)

_UI = CommonUIStrings
_ST = StyleConfig
_PS = PromptsState

# Table columns: the id first, then the csv's own seven. 'files' is last and the only
# stretching one (GUI LAYOUT CONVENTIONS); 'request' is the widest fixed column.
_COLS = ('id',) + tuple(PromptsLog.HEADERS)
_LABELS = {
    'id': _UI.PRM_COL_ID,
    PromptsLog.COL_REQUESTED: _UI.PRM_COL_REQUESTED,
    PromptsLog.COL_EXECUTED: _UI.PRM_COL_EXECUTED,
    PromptsLog.COL_CATEGORY: _UI.PRM_COL_CATEGORY,
    PromptsLog.COL_REQUEST: _UI.PRM_COL_REQUEST,
    PromptsLog.COL_NOTES: _UI.PRM_COL_NOTES,
    PromptsLog.COL_WORK: _UI.PRM_COL_WORK,
    PromptsLog.COL_FILES: _UI.PRM_COL_FILES,
}
_WIDTHS = {'id': 55, PromptsLog.COL_REQUESTED: 120, PromptsLog.COL_EXECUTED: 120,
           PromptsLog.COL_CATEGORY: 90, PromptsLog.COL_REQUEST: 420,
           PromptsLog.COL_NOTES: 200, PromptsLog.COL_WORK: 320,
           PromptsLog.COL_FILES: 160}
_TAG_PENDING = 'pending'
# What a right-click prefills the request box with: where the click landed, then
# the colon the request itself is written after.
_LOC_SEP = ', '
_LOC_TAIL = ': '
_LOC_TAB = '%s tab'
_LOC_DIALOG = '"%s" dialog'
_LOC_COLUMN = '%s column'
_LOC_BUTTON = '"%s" button'
# Where in a PanedWindow a pane sits, by orientation and position
_LOC_PANES = {'vertical': ('upper pane', 'middle pane', 'lower pane'),
              'horizontal': ('left pane', 'middle pane', 'right pane')}
_SASH_LABEL = 'Prompts log'
# How the log names this table when its columns are resized
_TABLE_LABEL = 'Prompts'
# The run just touched the csv; give the write a moment to land before re-reading
_CSV_SETTLE_MS = 1500

# The Chat window: the transcript over the message box, in the log pane's own colors, so
# an answer reads there the way a run reads in the log below. _KIND_CHAT is what tells
# _claude_start it has no requests to work and that the window, not only the log, is
# where its answer goes.
_KIND_CHAT = 'chat'
_CHAT_W, _CHAT_H, _CHAT_WRAP = 860, 620, 660
_CHAT_POLL_MS = 120         # how often the window drains what the run pushed into it
_TAG_YOU, _TAG_CLAUDE, _TAG_META = 'you', 'claude', 'meta'


def _attach_tooltip(widget, text: str) -> None:
    """A plain hover label; these buttons carry consequences worth spelling out."""
    tip = {'win': None}

    def _show(_event=None):
        if tip['win'] is not None:
            return
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        win = tk.Toplevel(widget)
        win.wm_overrideredirect(True)
        win.wm_geometry(f'+{x}+{y}')
        tk.Label(win, text=text, justify='left', background='#ffffe0',
                 relief='solid', borderwidth=1, padx=6, pady=3).pack()
        tip['win'] = win

    def _hide(_event=None):
        if tip['win'] is not None:
            tip['win'].destroy()
            tip['win'] = None

    widget.bind('<Enter>', _show)
    widget.bind('<Leave>', _hide)
    widget.bind('<ButtonPress>', _hide)


def _pane_position(widget) -> str:
    """Where the widget sits in the nearest PanedWindow above it -- upper/lower for a
    vertical split, left/right for a horizontal one. '' when it is in none."""
    child = widget
    parent = widget.master
    while parent is not None:
        if isinstance(parent, (ttk.PanedWindow, tk.PanedWindow)):
            try:
                panes = [str(x) for x in parent.panes()]
                orient = str(parent.cget('orient'))
                names = _LOC_PANES.get(orient, _LOC_PANES['vertical'])
                i = panes.index(str(child))
                return names[0] if i == 0 else (names[2] if i == len(panes) - 1
                                                else names[1])
            except (tk.TclError, ValueError):
                return ''
        child, parent = parent, parent.master
    return ''


def _labelframe_text(widget) -> str:
    """The title of the nearest LabelFrame above the widget -- the pane's own name
    ('Imports', 'Imported Files', 'Summary'), which beats a position when there is one."""
    parent = widget
    while parent is not None:
        if isinstance(parent, (ttk.LabelFrame, tk.LabelFrame)):
            try:
                return str(parent.cget('text')).strip()
            except tk.TclError:
                return ''
        parent = parent.master
    return ''


def _widget_part(widget, event) -> str:
    """The bit of the pane the click actually landed on: a table's column, a button's
    text, else the kind of widget -- what tells one control from the next."""
    if isinstance(widget, ttk.Treeview):
        try:
            col = widget.identify_column(event.x)
            if col:
                head = str(widget.heading(col, 'text'))
                head = head.replace('▲', '').replace('▼', '').strip()
                if head:
                    return _LOC_COLUMN % head
        except tk.TclError:
            pass
        return ''
    if isinstance(widget, (ttk.Button, tk.Button, ttk.Checkbutton, tk.Checkbutton)):
        try:
            text = str(widget.cget('text')).strip()
            if text:
                return _LOC_BUTTON % text
        except tk.TclError:
            pass
    return ''


def _configure_run_button_styles(widget) -> None:
    """The Code and Chat colors, configured by the tab that owns those two buttons.

    Not in an app's _configure_style: the buttons belong to this shared tab, and both
    apps carry it. Colors ONLY -- the names are dotted off 'TButton', so the font and
    the padding follow whatever the app configured, and a font-size change (which
    reconfigures 'TButton') needs no repaint here.

    The DISABLED shade is each button's own hue washed out, not the shared gray: both
    buttons are disabled for as long as a run goes, which is most of the time they are
    looked at, and a gray pair no longer says which one writes code and which one asks."""
    style = ttk.Style(widget)
    for name, bg, fg, active, pressed, off in (
            (_ST.STYLE_BTN_CODE, _ST.CODE_BTN_BG, _ST.CODE_BTN_FG,
             _ST.CODE_BTN_ACTIVE, _ST.CODE_BTN_PRESSED, _ST.CODE_BTN_DISABLED),
            (_ST.STYLE_BTN_CHAT, _ST.CHAT_BTN_BG, _ST.CHAT_BTN_FG,
             _ST.CHAT_BTN_ACTIVE, _ST.CHAT_BTN_PRESSED, _ST.CHAT_BTN_DISABLED)):
        style.configure(name, background=bg, foreground=fg)
        style.map(name,
                  background=[('pressed', '!disabled', pressed), ('active', active),
                              ('disabled', off)],
                  foreground=[('disabled', _ST.BTN_DISABLED_FG)])


def _click_tab(app, widget) -> str:
    """The tab a click belongs to: the notebook tab holding the widget, or -- for a
    click inside a DIALOG, which is no tab's child -- the tab standing open behind it,
    since that is the tab the dialog was opened from. '' when there is no notebook."""
    notebook = getattr(app, '_notebook', None)
    if notebook is None:
        return ''
    path = str(widget)
    try:
        for tab_id in notebook.tabs():
            if path == tab_id or path.startswith(tab_id + '.'):
                return str(notebook.tab(tab_id, 'text')).strip()
        if widget.winfo_toplevel() is not app:
            return str(notebook.tab(notebook.select(), 'text')).strip()
    except tk.TclError:
        pass
    return ''


def _click_location(app, widget, event) -> str:
    """A readable address of what was right-clicked: the tab, the dialog when the click
    landed in one, the pane, and the column or button inside it -- 'Files tab, upper
    pane, Credit (+) column' or 'Bank tab, "Import File" dialog, "Import" button'.

    Minimal on purpose: it is the opening line of a request, so it has to say where
    without being read twice."""
    parts = []
    tab = _click_tab(app, widget)
    if tab:
        parts.append(_LOC_TAB % tab)
    try:
        top = widget.winfo_toplevel()
        if top is not app:
            title = str(top.title()).strip()
            if title:
                parts.append(_LOC_DIALOG % title)
    except tk.TclError:
        pass
    for part in (_labelframe_text(widget) or _pane_position(widget),
                 _widget_part(widget, event)):
        if part:
            parts.append(part)
    return _LOC_SEP.join(parts)


def _has_own_right_click(widget) -> bool:
    """True when the widget already answers a right-click itself (the Files tab's
    context menu, say) -- that binding wins and no request dialog opens."""
    try:
        return bool(widget.bind('<Button-3>'))
    except tk.TclError:
        return False


def _is_header_click(widget, event) -> bool:
    """True when a right-click landed on a table's HEADER row rather than on a row.
    There is nothing to act on there, so the request dialog wins even over a table
    that carries its own context menu."""
    if not isinstance(widget, ttk.Treeview):
        return False
    try:
        return widget.identify_region(event.x, event.y) in ('heading', 'separator')
    except tk.TclError:
        return False


def _tool_brief(inp) -> str:
    """One readable line for a tool call: its description or its main argument."""
    inp = inp or {}
    for key in ('description', 'file_path', 'pattern', 'path', 'command', 'prompt'):
        if inp.get(key):
            return plog.clip(str(inp[key]), 160)
    return plog.clip(json.dumps(inp, ensure_ascii=False), 160)


class ClaudeRunDialog(tk.Toplevel):
    """The dialog Claude opens: which requests, the general prompt, and how to run.

    result is None on Cancel, else a dict: picked (0-based csv indexes), general,
    model_key, context ('new' or 'continue'), permission_mode, add_dirs, extra_args."""

    def __init__(self, parent, rows: list, state: dict):
        super().__init__(parent)
        self.title(_UI.PRM_DLG_TITLE)
        self.transient(parent)
        self.result = None
        self._default_general = plog.default_general_prompt()
        pend = plog.pending_rows(rows)

        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(1, weight=1)

        self._checks: list = []
        self._build_requests(frm, pend)
        self._build_general(frm, state)
        self._build_options(frm, state)

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, sticky='ew')
        self._lbl_status = ttk.Label(btns, text='')
        self._lbl_status.pack(side=tk.RIGHT)
        btn_start = ttk.Button(btns, text=_UI.PRM_BTN_START, style='Action.TButton',
                               command=self._on_start)
        btn_start.pack(side=tk.LEFT)
        if not pend:
            btn_start.configure(state='disabled')
        ttk.Button(btns, text=_UI.PRM_BTN_CANCEL, command=self.destroy).pack(
            side=tk.LEFT, padx=6)

        self.geometry('%dx%d' % (min(1000, self.winfo_screenwidth() - 80),
                                 min(760, self.winfo_screenheight() - 120)))
        self.minsize(640, 420)
        self.grab_set()

    def _build_requests(self, frm, pend: list) -> None:
        """The pending requests, each with its checkbox; all checked to start with."""
        lf = ttk.LabelFrame(frm, text=_UI.PRM_DLG_REQUESTS)
        lf.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        lf.columnconfigure(0, weight=1)
        if not pend:
            ttk.Label(lf, text=_UI.PRM_DLG_NONE).grid(row=0, column=0, sticky='w',
                                                      padx=6, pady=4)
            return
        canvas = tk.Canvas(lf, height=min(150, 26 * len(pend) + 8), highlightthickness=0)
        sb = ttk.Scrollbar(lf, orient='vertical', command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind('<Configure>',
                   lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky='ew', padx=4, pady=2)
        sb.grid(row=0, column=1, sticky='ns')
        for i, r in pend:
            var = tk.BooleanVar(value=True)
            cat = r[plog.I_CATEGORY].strip() or '-'
            text = '#%d  [%s]  %s' % (i + 1, cat,
                                      plog.clip(r[plog.I_REQUEST], ClaudeRun.REQUEST_CLIP))
            ttk.Checkbutton(inner, text=text, variable=var).pack(anchor='w')
            self._checks.append((var, i))

    def _build_general(self, frm, state: dict) -> None:
        """The general prompt, editable; the request lines are appended after it."""
        lf = ttk.LabelFrame(frm, text=_UI.PRM_DLG_GENERAL)
        lf.grid(row=1, column=0, sticky='nsew', pady=(0, 6))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self._txt_general = tk.Text(lf, wrap='word', height=9, undo=True)
        sb = ttk.Scrollbar(lf, orient='vertical', command=self._txt_general.yview)
        self._txt_general.configure(yscrollcommand=sb.set)
        self._txt_general.grid(row=0, column=0, sticky='nsew', padx=(4, 0), pady=2)
        sb.grid(row=0, column=1, sticky='ns')
        self._txt_general.insert('1.0', state.get(_PS.KEY_CLAUDE_GENERAL)
                                 or self._default_general)
        ttk.Button(lf, text=_UI.PRM_DLG_RESET, command=self._reset_general).grid(
            row=1, column=0, sticky='w', padx=4, pady=(0, 4))

    def _build_options(self, frm, state: dict) -> None:
        """How the run starts: model, context, permissions, then dirs and extra args."""
        opts = ttk.Frame(frm)
        opts.grid(row=2, column=0, sticky='ew', pady=(0, 6))
        opts.columnconfigure(5, weight=1)

        ttk.Label(opts, text=_UI.PRM_DLG_MODEL).grid(row=0, column=0, sticky='w')
        want = (ClaudeModels.entry(state.get(_PS.KEY_CLAUDE_MODEL) or '')
                or ClaudeModels.entry(ClaudeModels.DEFAULT_KEY))
        self._var_model = tk.StringVar(value=want['label'])
        ttk.Combobox(opts, textvariable=self._var_model,
                     values=[m['label'] for m in ClaudeModels.LIST],
                     state='readonly', width=10).grid(row=0, column=1, sticky='w',
                                                      padx=(4, 12))

        ttk.Label(opts, text=_UI.PRM_DLG_CONTEXT).grid(row=0, column=2, sticky='w')
        self._session = (state.get(_PS.KEY_CLAUDE_SESSION) or '').strip()
        ctx_values = [_UI.PRM_DLG_CTX_NEW]
        if self._session:
            ctx_values.append('%s (%s)' % (_UI.PRM_DLG_CTX_CONTINUE, self._session[:8]))
        self._var_ctx = tk.StringVar(value=ctx_values[0])
        cmb_ctx = ttk.Combobox(opts, textvariable=self._var_ctx, values=ctx_values,
                               state='readonly', width=24)
        cmb_ctx.grid(row=0, column=3, sticky='w', padx=(4, 12))
        _attach_tooltip(cmb_ctx, _UI.PRM_TIP_CONTEXT)

        ttk.Label(opts, text=_UI.PRM_DLG_PERMISSIONS).grid(row=0, column=4, sticky='w')
        # an unknown stored mode (an older CLI's list) falls back to the default
        mode = state.get(_PS.KEY_CLAUDE_PERMISSION)
        if mode not in ClaudeRun.PERMISSION_MODES:
            mode = ClaudeRun.DEFAULT_PERMISSION_MODE
        self._var_perm = tk.StringVar(value=mode)
        cmb_perm = ttk.Combobox(opts, textvariable=self._var_perm,
                                values=ClaudeRun.PERMISSION_MODES, state='readonly',
                                width=17)
        cmb_perm.grid(row=0, column=5, sticky='w', padx=(4, 0))
        _attach_tooltip(cmb_perm, _UI.PRM_TIP_PERMISSIONS)

        # dirs outside the repo the run may read; without the project data root every
        # read of the household's files is denied and the run wastes its turns retrying
        ttk.Label(opts, text=_UI.PRM_DLG_ADD_DIRS).grid(row=1, column=0, sticky='w',
                                                        pady=(6, 0))
        dirs = state.get(_PS.KEY_CLAUDE_ADD_DIRS)
        if dirs is None:
            dirs = state.get('project_root', '')
        self._var_dirs = tk.StringVar(value=dirs)
        ent_dirs = ttk.Entry(opts, textvariable=self._var_dirs)
        ent_dirs.grid(row=1, column=1, columnspan=5, sticky='ew', padx=(4, 0), pady=(6, 0))
        _attach_tooltip(ent_dirs, _UI.PRM_TIP_ADD_DIRS)

        ttk.Label(opts, text=_UI.PRM_DLG_EXTRA).grid(row=2, column=0, sticky='w',
                                                     pady=(6, 0))
        self._var_extra = tk.StringVar(value=state.get(_PS.KEY_CLAUDE_EXTRA, ''))
        ttk.Entry(opts, textvariable=self._var_extra).grid(
            row=2, column=1, columnspan=5, sticky='ew', padx=(4, 0), pady=(6, 0))

    def _reset_general(self) -> None:
        self._txt_general.delete('1.0', tk.END)
        self._txt_general.insert('1.0', self._default_general)

    def _on_start(self) -> None:
        picked = [i for var, i in self._checks if var.get()]
        if not picked:
            self._lbl_status.configure(text=_UI.PRM_DLG_NONE)
            return
        label = self._var_model.get()
        model_key = next((m['key'] for m in ClaudeModels.LIST if m['label'] == label),
                         ClaudeModels.DEFAULT_KEY)
        self.result = {
            'picked': picked,
            'general': self._txt_general.get('1.0', tk.END).strip(),
            'model_key': model_key,
            'context': 'new' if self._var_ctx.get() == _UI.PRM_DLG_CTX_NEW else 'continue',
            'permission_mode': self._var_perm.get(),
            'add_dirs': self._var_dirs.get().strip(),
            'extra_args': self._var_extra.get().strip(),
        }
        self.destroy()


class ChatDialog(tk.Toplevel):
    """The window Chat opens: the transcript, the message box and Send.

    Modeless and long-lived, unlike the run dialog: the answer streams into this same
    window while it stands open, and the next message continues the same session, so the
    window IS the conversation. There is no permission mode and no extra args to pick --
    a chat is read-only by construction (ClaudeRun.CHAT_PERMISSION_MODE).

    The run pushes its lines from its own thread into _queue and _drain empties it on the
    main thread -- the shape both apps' log queue already has."""

    def __init__(self, app):
        super().__init__(app)
        self.title(_UI.PRM_CHAT_TITLE)
        self.transient(app)
        self._app = app
        self._queue: queue.Queue = queue.Queue()
        self._after_id = None

        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=3)
        frm.rowconfigure(1, weight=1)

        self._build_transcript(frm)
        self._build_question(frm)
        self._build_options(frm, app._state)
        self._build_buttons(frm)

        self.geometry('%dx%d' % (min(_CHAT_W, self.winfo_screenwidth() - 80),
                                 min(_CHAT_H, self.winfo_screenheight() - 120)))
        self.minsize(560, 380)
        self._txt_question.focus_set()
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.bind('<Destroy>', self._on_destroy, add='+')
        self._after_id = self.after(_CHAT_POLL_MS, self._drain)

    def _build_transcript(self, frm) -> None:
        """The answers, in the log panes' own colors; wrap='word' because an answer is
        prose, not the fixed columns a run prints."""
        lf = ttk.LabelFrame(frm, text=_UI.PRM_CHAT_TRANSCRIPT)
        lf.grid(row=0, column=0, sticky='nsew', pady=(0, 6))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self._txt_chat = tk.Text(lf, state='disabled', wrap='word', font='TkFixedFont',
                                 background=_ST.LOG_BG, foreground=_ST.LOG_FG,
                                 insertbackground=_ST.LOG_FG, relief='flat',
                                 borderwidth=0)
        sb = ttk.Scrollbar(lf, orient='vertical', command=self._txt_chat.yview)
        self._txt_chat.configure(yscrollcommand=sb.set)
        self._txt_chat.grid(row=0, column=0, sticky='nsew', padx=(4, 0), pady=2)
        sb.grid(row=0, column=1, sticky='ns')
        self._txt_chat.tag_configure(_TAG_YOU, foreground=_ST.CHAT_FG_YOU)
        self._txt_chat.tag_configure(_TAG_CLAUDE, foreground=_ST.LOG_FG)
        self._txt_chat.tag_configure(_TAG_META, foreground=_ST.CHAT_FG_META)

    def _build_question(self, frm) -> None:
        """The message box, in the transcript's colors so the window reads as one."""
        lf = ttk.LabelFrame(frm, text=_UI.PRM_CHAT_QUESTION)
        lf.grid(row=1, column=0, sticky='nsew', pady=(0, 6))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self._txt_question = tk.Text(lf, wrap='word', height=5, undo=True,
                                     font='TkFixedFont', background=_ST.LOG_BG,
                                     foreground=_ST.LOG_FG, insertbackground=_ST.LOG_FG,
                                     relief='flat', borderwidth=0)
        sb = ttk.Scrollbar(lf, orient='vertical', command=self._txt_question.yview)
        self._txt_question.configure(yscrollcommand=sb.set)
        self._txt_question.grid(row=0, column=0, sticky='nsew', padx=(4, 0), pady=2)
        sb.grid(row=0, column=1, sticky='ns')
        self._txt_question.bind('<Control-Return>',
                                lambda _e: (self._on_send(), 'break')[1])
        ttk.Label(lf, text=_UI.PRM_CHAT_HINT, wraplength=_CHAT_WRAP,
                  foreground='gray').grid(row=1, column=0, columnspan=2, sticky='w',
                                          padx=4, pady=(0, 4))

    def _build_options(self, frm, state: dict) -> None:
        """Model and context, the only two choices a chat has."""
        opts = ttk.Frame(frm)
        opts.grid(row=2, column=0, sticky='ew', pady=(0, 6))
        ttk.Label(opts, text=_UI.PRM_DLG_MODEL).pack(side=tk.LEFT)
        entry = (ClaudeModels.entry(state.get(_PS.KEY_CLAUDE_MODEL) or '')
                 or ClaudeModels.entry(ClaudeModels.DEFAULT_KEY))
        self._var_model = tk.StringVar(value=entry['label'])
        ttk.Combobox(opts, textvariable=self._var_model,
                     values=[m['label'] for m in ClaudeModels.LIST], state='readonly',
                     width=10).pack(side=tk.LEFT, padx=(4, 12))

        # the session is the one the Code runs use too, so the first message can continue
        # the run that just finished; every later one continues this chat
        ttk.Label(opts, text=_UI.PRM_DLG_CONTEXT).pack(side=tk.LEFT)
        self._var_ctx = tk.StringVar()
        self._cmb_ctx = ttk.Combobox(opts, textvariable=self._var_ctx, state='readonly',
                                     width=24)
        self._cmb_ctx.pack(side=tk.LEFT, padx=(4, 0))
        _attach_tooltip(self._cmb_ctx, _UI.PRM_TIP_CONTEXT)
        self.refresh_context()

    def _build_buttons(self, frm) -> None:
        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, sticky='ew')
        self._lbl_status = ttk.Label(btns, text='')
        self._lbl_status.pack(side=tk.RIGHT)
        self._btn_send = ttk.Button(btns, text=_UI.PRM_BTN_SEND, style='Action.TButton',
                                    command=self._on_send)
        self._btn_send.pack(side=tk.LEFT)
        self._btn_stop = ttk.Button(btns, text=_UI.PRM_BTN_STOP, state='disabled',
                                    command=self._app._prompts_stop)
        self._btn_stop.pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text=_UI.PRM_BTN_CLEAR, command=self._clear).pack(side=tk.LEFT)
        ttk.Button(btns, text=_UI.PRM_BTN_CLOSE, command=self.destroy).pack(
            side=tk.LEFT, padx=6)

    # ── What the run writes into the window ───────────────────────────────────

    def put(self, text: str, tag: str = _TAG_CLAUDE) -> None:
        """Queue a line for the transcript; the run's thread calls this too."""
        self._queue.put((text, tag))

    def _drain(self) -> None:
        self._after_id = None
        try:
            while True:
                try:
                    text, tag = self._queue.get_nowait()
                except queue.Empty:
                    break
                self._txt_chat.configure(state='normal')
                self._txt_chat.insert(tk.END, text, tag)
                self._txt_chat.see(tk.END)
                self._txt_chat.configure(state='disabled')
        except tk.TclError:
            return              # the window went away mid-drain; nothing to reschedule
        self._after_id = self.after(_CHAT_POLL_MS, self._drain)

    def _clear(self) -> None:
        self._txt_chat.configure(state='normal')
        self._txt_chat.delete('1.0', tk.END)
        self._txt_chat.configure(state='disabled')

    def set_running(self, running: bool) -> None:
        """Send is closed while a turn is in flight; Stop is what kills it."""
        try:
            self._btn_send.configure(state='disabled' if running else 'normal')
            self._btn_stop.configure(state='normal' if running else 'disabled')
            self._lbl_status.configure(text=_UI.PRM_CHAT_THINKING if running else '')
        except tk.TclError:
            pass

    def refresh_context(self) -> None:
        """Re-read the session id: after one turn the chat continues on it."""
        session = (self._app._state.get(_PS.KEY_CLAUDE_SESSION) or '').strip()
        values = [_UI.PRM_DLG_CTX_NEW]
        if session:
            values.append('%s (%s)' % (_UI.PRM_DLG_CTX_CONTINUE, session[:8]))
        self._cmb_ctx.configure(values=values)
        if self._var_ctx.get() not in values:
            # the last one: a chat with a session behind it continues by default
            self._var_ctx.set(values[-1])

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if getattr(self._app, '_prompts_chat_dlg', None) is self:
            self._app._prompts_chat_dlg = None

    def _on_send(self) -> None:
        question = self._txt_question.get('1.0', tk.END).strip()
        if not question:
            self._lbl_status.configure(text=_UI.PRM_CHAT_EMPTY)
            return
        label = self._var_model.get()
        model_key = next((m['key'] for m in ClaudeModels.LIST if m['label'] == label),
                         ClaudeModels.DEFAULT_KEY)
        context = 'new' if self._var_ctx.get() == _UI.PRM_DLG_CTX_NEW else 'continue'
        if not self._app._prompts_chat_send(question, model_key, context):
            return              # a run is already going; the message stays in the box
        self.put('\n%s: %s\n\n' % (_UI.PRM_CHAT_YOU, question), _TAG_YOU)
        self._txt_question.delete('1.0', tk.END)


class PromptsTabMixin:
    """The Prompts tab: the development log table and the Claude runs worked from it.

    The host app must provide _tab_prompts (a ttk.Frame in its notebook), _state,
    _append_log, _log_queue, _start_background and _font_bold -- both apps already do.
    Geometry is registered through the Private app's register_* API when the host has
    it, and falls back to the Tax app's _capture_vert_sash otherwise."""

    def _append_prompts_log(self, text: str) -> None:
        if not hasattr(self, '_txt_prompts_log'):
            return
        self._txt_prompts_log.configure(state='normal')
        self._txt_prompts_log.insert(tk.END, text)
        self._txt_prompts_log.see(tk.END)
        self._txt_prompts_log.configure(state='disabled')

    def _clear_prompts_log(self) -> None:
        self._txt_prompts_log.configure(state='normal')
        self._txt_prompts_log.delete('1.0', tk.END)
        self._txt_prompts_log.configure(state='disabled')

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_prompts_tab(self) -> None:
        f = self._tab_prompts
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self._prompts_rows: list = []
        self._prompts_shown: list = []
        self._prompts_mtime = None
        self._prompts_sort = {'col': '', 'rev': False}
        self._prompts_proc = None
        self._prompts_add_dlg = None
        self._prompts_chat_dlg = None    # the one chat window, while it stands open
        self._prompts_chat_run = False   # the run going is a chat, so it echoes into it
        # the modal the New request dialog took the grab from, to hand it back to
        self._prompts_add_grab = None

        pw = ttk.PanedWindow(f, orient='vertical')
        pw.grid(row=0, column=0, sticky='nsew', padx=4, pady=4)
        self._pw_prompts_vert = pw

        top = ttk.Frame(pw)
        pw.add(top, weight=3)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(1, weight=1)
        self._build_prompts_bar(top)
        self._build_prompts_table(top)
        self._build_prompts_log(pw)

        self._register_prompts_geometry()
        self._bind_prompts_right_click()
        self._prompts_refresh(quiet=True)

    def _bind_prompts_right_click(self) -> None:
        """A right-click ANYWHERE in the app -- every tab and every dialog -- opens the
        New request dialog, already naming the place it was clicked.

        Bound with bind_all rather than on the window: a Tk event travels the widget,
        its class, its toplevel and then 'all', so the last of those is the one binding
        that also covers the app's dialogs, each of which is a toplevel of its own. A
        widget that answers a right-click itself keeps it (see _has_own_right_click) --
        a context menu is never taken away, except over a table's HEADER, where there
        is nothing for a menu to act on."""
        self.bind_all('<Button-3>', self._prompts_on_right_click, add='+')

    def _prompts_on_right_click(self, event) -> None:
        widget = event.widget
        if _has_own_right_click(widget) and not _is_header_click(widget, event):
            return
        location = _click_location(self, widget, event)
        self._prompts_add(prefill=(location + _LOC_TAIL) if location else '',
                          category=plog.tab_category(_click_tab(self, widget)))

    def _build_prompts_bar(self, top) -> None:
        """Filter row and the action buttons, one bar."""
        bar = ttk.Frame(top)
        bar.grid(row=0, column=0, sticky='ew', padx=4, pady=(4, 2))

        ttk.Label(bar, text=_UI.PRM_FILTER).pack(side=tk.LEFT)
        self._var_prompts_filter = tk.StringVar()
        ttk.Entry(bar, textvariable=self._var_prompts_filter, width=26).pack(
            side=tk.LEFT, padx=(4, 4))
        self._var_prompts_filter.trace_add('write', lambda *_a: self._prompts_apply())
        ttk.Button(bar, text='✕', width=3,
                   command=lambda: self._var_prompts_filter.set('')).pack(
            side=tk.LEFT, padx=(0, 8))

        self._var_prompts_cat = tk.StringVar(value=_UI.PRM_ALL_CATEGORIES)
        self._cmb_prompts_cat = ttk.Combobox(bar, textvariable=self._var_prompts_cat,
                                             state='readonly', width=14)
        self._cmb_prompts_cat.pack(side=tk.LEFT, padx=(0, 8))
        self._cmb_prompts_cat.bind('<<ComboboxSelected>>',
                                   lambda _e: self._prompts_apply())

        self._var_prompts_state = tk.StringVar(value=_UI.PRM_STATE_ALL)
        cmb_state = ttk.Combobox(bar, textvariable=self._var_prompts_state,
                                 state='readonly', width=8,
                                 values=[_UI.PRM_STATE_ALL, _UI.PRM_STATE_PENDING,
                                         _UI.PRM_STATE_DONE])
        cmb_state.pack(side=tk.LEFT, padx=(0, 8))
        cmb_state.bind('<<ComboboxSelected>>', lambda _e: self._prompts_apply())

        self._lbl_prompts_count = ttk.Label(bar, text='', foreground='gray')
        self._lbl_prompts_count.pack(side=tk.LEFT)

        # Packed right to left, so they read Refresh / Add / Edit / Delete / Chat /
        # Code / Stop. Code is the run that writes code, orange; Chat beside it, light
        # purple, only answers -- the color is what tells the two apart at a glance.
        # DEFERRED to after(0), which is the whole reason the two buttons used to come
        # out plain gray: a ttk style belongs to the THEME that is current when it is
        # configured, and both apps build their tabs BEFORE _configure_style() switches
        # to clam -- so the colors were being written into the theme left behind. An
        # after(0) runs on the event loop, by which time clam is the theme they land in.
        self.after(0, lambda: _configure_run_button_styles(bar))
        self._btn_prompts_stop = ttk.Button(bar, text=_UI.PRM_BTN_STOP,
                                            command=self._prompts_stop, state='disabled')
        self._btn_prompts_stop.pack(side=tk.RIGHT)
        self._btn_prompts_code = ttk.Button(bar, text=_UI.PRM_BTN_CODE,
                                            style=_ST.STYLE_BTN_CODE,
                                            command=self._prompts_code)
        self._btn_prompts_code.pack(side=tk.RIGHT, padx=(0, 6))
        _attach_tooltip(self._btn_prompts_code, _UI.PRM_TIP_CODE)
        self._btn_prompts_chat = ttk.Button(bar, text=_UI.PRM_BTN_CHAT,
                                            style=_ST.STYLE_BTN_CHAT,
                                            command=self._prompts_chat)
        self._btn_prompts_chat.pack(side=tk.RIGHT, padx=(0, 6))
        _attach_tooltip(self._btn_prompts_chat, _UI.PRM_TIP_CHAT)
        btn_del = ttk.Button(bar, text=_UI.PRM_BTN_DELETE, style='Delete.TButton',
                             command=self._prompts_delete)
        btn_del.pack(side=tk.RIGHT, padx=(0, 6))
        _attach_tooltip(btn_del, _UI.PRM_TIP_DELETE)
        btn_edit = ttk.Button(bar, text=_UI.PRM_BTN_EDIT, command=self._prompts_edit)
        btn_edit.pack(side=tk.RIGHT, padx=(0, 6))
        _attach_tooltip(btn_edit, _UI.PRM_TIP_EDIT)
        btn_add = ttk.Button(bar, text=_UI.PRM_BTN_ADD,
                             command=lambda: self._prompts_add())
        btn_add.pack(side=tk.RIGHT, padx=(0, 6))
        _attach_tooltip(btn_add, _UI.PRM_TIP_ADD)
        ttk.Button(bar, text=_UI.PRM_BTN_REFRESH,
                   command=self._prompts_refresh).pack(side=tk.RIGHT, padx=(0, 6))

    def _build_prompts_table(self, top) -> None:
        """The table: the id plus the csv's seven columns, every heading sorting."""
        tbl = ttk.Frame(top)
        tbl.grid(row=1, column=0, sticky='nsew', padx=4, pady=(0, 2))
        tbl.columnconfigure(0, weight=1)
        tbl.rowconfigure(0, weight=1)
        tv = ttk.Treeview(tbl, columns=_COLS, show='headings', selectmode='browse')
        for col in _COLS:
            tv.heading(col, text=_LABELS[col], anchor='w',
                       command=lambda c=col: self._prompts_sort_by(c))
            tv.column(col, anchor='w', width=_WIDTHS[col],
                      stretch=(col == _COLS[-1]), minwidth=LayoutConfig.MIN_COL_WIDTH)
        tv.tag_configure('row_even', background=_ST.ROW_EVEN_BG)
        tv.tag_configure('row_odd', background=_ST.ROW_ODD_BG)
        tv.tag_configure(_TAG_PENDING, background=_ST.PROMPT_PENDING_BG)
        vsb = ttk.Scrollbar(tbl, orient='vertical', command=tv.yview)
        hsb = ttk.Scrollbar(tbl, orient='horizontal', command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tv.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        # a double-click is the Edit button: one dialog opens a request, never two
        tv.bind('<Double-1>', lambda _e: self._prompts_edit())
        self._tv_prompts = tv

    def _build_prompts_log(self, pw) -> None:
        """The log pane, styled as every other tab's."""
        log_frame = ttk.Frame(pw)
        pw.add(log_frame, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        hdr = ttk.Frame(log_frame)
        hdr.grid(row=0, column=0, sticky='ew', padx=4, pady=(4, 0))
        ttk.Label(hdr, text=_UI.PRM_HDR_LOG, font=self._font_bold).pack(side=tk.LEFT)
        self._pb_prompts = ttk.Progressbar(hdr, mode='indeterminate', length=120)
        self._pb_prompts.pack(side=tk.LEFT, padx=(10, 4))
        ttk.Button(hdr, text=_UI.PRM_BTN_CLEAR,
                   command=self._clear_prompts_log).pack(side=tk.RIGHT)

        self._txt_prompts_log = tk.Text(
            log_frame, wrap='word', state='disabled', height=6,
            background=_ST.LOG_BG, foreground=_ST.LOG_FG,
            font='TkFixedFont', relief='flat', borderwidth=0)
        vsb = ttk.Scrollbar(log_frame, orient='vertical',
                            command=self._txt_prompts_log.yview)
        self._txt_prompts_log.configure(yscrollcommand=vsb.set)
        self._txt_prompts_log.grid(row=1, column=0, sticky='nsew', padx=(4, 0), pady=(2, 4))
        vsb.grid(row=1, column=1, sticky='ns')

    def _register_prompts_geometry(self) -> None:
        """Hand the sash, the column widths and the log widget to whichever geometry API
        the host app has: the Private app registers them, the Tax app captures its own."""
        pw, tv = self._pw_prompts_vert, self._tv_prompts
        if hasattr(self, 'register_sash'):
            self.register_log_widget(self._txt_prompts_log)
            self.register_sash(SashConfig.KEY_PROMPTS_LOG, pw, 'vert', self._tab_prompts,
                               label=_SASH_LABEL)
            self.register_colwidths(_PS.KEY_COL_WIDTHS, tv, label=_TABLE_LABEL)
        else:
            pw.bind('<ButtonRelease-1>',
                    lambda _e: self._capture_vert_sash(SashConfig.KEY_PROMPTS_LOG, pw,
                                                       label=_SASH_LABEL))

    # ── Table ─────────────────────────────────────────────────────────────────

    def _prompts_refresh(self, quiet: bool = False) -> None:
        try:
            self._prompts_mtime = RepoPaths.path_file_prompts.stat().st_mtime
        except OSError:
            self._prompts_mtime = None
        self._prompts_rows = plog.read_csv()
        values = [_UI.PRM_ALL_CATEGORIES] + plog.categories(self._prompts_rows)
        self._cmb_prompts_cat.configure(values=values)
        if self._var_prompts_cat.get() not in values:
            self._var_prompts_cat.set(_UI.PRM_ALL_CATEGORIES)
        self._prompts_apply()
        if not quiet:
            self._append_log(f'[PROMPTS] Loaded {len(self._prompts_rows)} requests from '
                             f'{plog.csv_name()}.\n')

    def _prompts_refresh_if_changed(self) -> None:
        """Re-read the csv when its file changed -- a Claude run, or the other app,
        writes into the very same file."""
        try:
            mtime = RepoPaths.path_file_prompts.stat().st_mtime
        except OSError:
            mtime = None
        if mtime != self._prompts_mtime:
            self._prompts_refresh(quiet=True)

    def _prompts_visible_rows(self) -> list:
        """(index, row) of the requests passing the filter, category and state pickers."""
        q = self._var_prompts_filter.get().strip().lower()
        cat = self._var_prompts_cat.get()
        want = self._var_prompts_state.get()
        shown = []
        for i, r in enumerate(self._prompts_rows):
            pending = plog.is_pending(r)
            if cat != _UI.PRM_ALL_CATEGORIES and r[plog.I_CATEGORY].strip() != cat:
                continue
            if want == _UI.PRM_STATE_PENDING and not pending:
                continue
            if want == _UI.PRM_STATE_DONE and pending:
                continue
            # the id is searched with the text, so '#237' finds exactly that request
            if q and q not in ('#%d ' % (i + 1) + ' '.join(r)).lower():
                continue
            shown.append((i, r))
        return shown

    def _prompts_sorted(self, shown: list) -> list:
        col, rev = self._prompts_sort['col'], self._prompts_sort['rev']
        if not col:
            # the default order: the newest request at the top
            return sorted(shown, key=lambda x: (plog.row_key(x[1]), x[0]), reverse=True)
        if col == 'id':
            return sorted(shown, key=lambda x: x[0], reverse=rev)
        idx = _COLS.index(col) - 1   # -1: the id column is not in the csv
        if col in (PromptsLog.COL_REQUESTED, PromptsLog.COL_EXECUTED):
            return sorted(shown, key=lambda x: (plog.stamp_key(x[1][idx]), x[0]), reverse=rev)
        return sorted(shown, key=lambda x: (x[1][idx].strip().lower(), x[0]), reverse=rev)

    def _prompts_apply(self) -> None:
        shown = self._prompts_sorted(self._prompts_visible_rows())
        self._prompts_shown = shown
        tv = self._tv_prompts
        tv.delete(*tv.get_children())
        for n, (i, r) in enumerate(shown):
            tags = [_TAG_PENDING] if plog.is_pending(r) else \
                   ['row_even' if n % 2 == 0 else 'row_odd']
            values = ('#%d' % (i + 1),) + tuple(plog.one_line(c) for c in r)
            tv.insert('', tk.END, iid=str(i), values=values, tags=tuple(tags))
        n_pend = sum(1 for r in self._prompts_rows if plog.is_pending(r))
        self._lbl_prompts_count.configure(text=_UI.PRM_COUNT.format(
            shown=len(shown), total=len(self._prompts_rows), pending=n_pend))
        self._prompts_sort_indicators()

    def _prompts_sort_by(self, col: str) -> None:
        if self._prompts_sort['col'] == col:
            self._prompts_sort['rev'] = not self._prompts_sort['rev']
        else:
            self._prompts_sort = {'col': col, 'rev': False}
        self._prompts_apply()

    def _prompts_sort_indicators(self) -> None:
        for col in _COLS:
            label = _LABELS[col]
            if col == self._prompts_sort['col']:
                label += ' ▼' if self._prompts_sort['rev'] else ' ▲'
            self._tv_prompts.heading(col, text=label)

    # ── Add a request ─────────────────────────────────────────────────────────

    def _prompts_add(self, prefill: str = '', category: str = '') -> None:
        """The New request dialog, deliberately modeless.

        A request is written while looking at what the app actually does, so this window
        takes no grab of its own: every tab stays usable while it stands open. Only one
        is ever open -- a second Add raises the one already there.

        prefill is the place a right-click landed on (see _prompts_on_right_click); the
        box opens with it and the caret after it, so the request is written where it
        says what it is about, and category is the tab it was written from. A dialog
        already open is only raised -- text already typed is never overwritten by a new
        click, and neither is a category already picked."""
        dlg = self._prompts_add_dlg
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify()
            dlg.lift()
            dlg.focus_force()
            self._prompts_take_grab(dlg)
            return
        dlg = tk.Toplevel(self)
        self._prompts_add_dlg = dlg
        dlg.title(_UI.PRM_ADD_TITLE)
        frm = ttk.Frame(dlg, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(1, weight=1)

        ttk.Label(frm, text=_UI.PRM_ADD_HINT, wraplength=560, foreground='gray').grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))
        ttk.Label(frm, text=_UI.PRM_COL_REQUEST).grid(row=1, column=0, sticky='nw')
        txt = tk.Text(frm, wrap='word', width=70, height=10, undo=True)
        txt.grid(row=1, column=1, sticky='nsew', padx=(6, 0), pady=(0, 6))
        if prefill:
            txt.insert('1.0', prefill)
            txt.mark_set(tk.INSERT, tk.END)

        row = ttk.Frame(frm)
        row.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        row.columnconfigure(3, weight=1)
        ttk.Label(row, text=_UI.PRM_COL_CATEGORY).grid(row=0, column=0, sticky='w')
        var_cat = tk.StringVar(value=category)
        # Wide enough for the two-word categories ('Insurances Tab'); width 14 cut them.
        ttk.Combobox(row, textvariable=var_cat, values=plog.dialog_categories(category),
                     width=24).grid(row=0, column=1, padx=(4, 12))
        ttk.Label(row, text=_UI.PRM_COL_NOTES).grid(row=0, column=2, sticky='w')
        var_notes = tk.StringVar()
        ttk.Entry(row, textvariable=var_notes).grid(row=0, column=3, sticky='ew', padx=(4, 0))

        def _close():
            self._prompts_add_dlg = None
            self._prompts_give_grab_back(dlg)
            dlg.destroy()

        def _save():
            text = txt.get('1.0', tk.END).strip()
            if not text:
                return
            # a new request goes at the bottom, where the log is worked from; re-read
            # first so a csv edited meanwhile (a run, or the other app) is not overwritten
            rows = plog.read_csv()
            rows.append(plog.new_row(text, var_cat.get(), var_notes.get()))
            if not self._prompts_write(rows):
                return
            self._append_log(f'[PROMPTS] Added request #{len(rows)} to {plog.csv_name()}.\n')
            _close()
            self._prompts_refresh(quiet=True)

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky='w')
        ttk.Button(btns, text=_UI.PRM_BTN_SAVE, style='Action.TButton',
                   command=_save).pack(side=tk.LEFT)
        ttk.Button(btns, text=_UI.PRM_BTN_CANCEL, command=_close).pack(side=tk.LEFT, padx=6)
        dlg.protocol('WM_DELETE_WINDOW', _close)
        # a modal opened AFTER this one takes the grab back; reclaim it on focus
        dlg.bind('<FocusIn>', lambda _e: self._prompts_take_grab(dlg), add='+')
        self._prompts_take_grab(dlg)
        txt.focus_set()

    def _prompts_take_grab(self, dlg) -> None:
        """Take the Tk grab from the modal dialog holding it, remembering the holder.

        A modal's grab is what decides which window the keyboard reaches: while
        'Import File' stands open, nothing typed lands in this modeless window and a
        request cannot be written from the very place it is about. So the New request
        dialog takes the grab whenever it is opened or focused over one, and hands it
        straight back when it closes -- the dialog underneath is modal to everything
        else again the moment this one is gone. Nothing to do when no modal is up:
        that is the modeless case, and the whole app stays usable."""
        try:
            holder = dlg.grab_current()
            # the dialog itself, or a widget inside it, already holds it
            if holder is None or holder is dlg or str(holder).startswith(str(dlg) + '.'):
                return
            if self._prompts_add_grab is None:
                self._prompts_add_grab = holder
            dlg.grab_set()
        except tk.TclError:
            pass

    def _prompts_give_grab_back(self, dlg) -> None:
        """Return the grab to the modal it was taken from, if that one is still open."""
        prev, self._prompts_add_grab = self._prompts_add_grab, None
        try:
            dlg.grab_release()
            if prev is not None and prev.winfo_exists():
                prev.grab_set()
        except tk.TclError:
            pass

    def _prompts_write(self, rows: list) -> bool:
        """Write the csv, keeping the previous content as prompts.csv.bak. False (with a
        messagebox) when the file could not be replaced -- typically open in Excel."""
        try:
            plog.write_csv(rows)
            return True
        except Exception as exc:
            self._append_log(f'[ERROR] Could not save {plog.csv_name()}: {exc}\n')
            messagebox.showerror(
                'Save Error',
                f'Could not save the prompts log:\n{exc}\n\n'
                f'If {RepoPaths.path_file_prompts.name} is open elsewhere, close it '
                f'and retry.', parent=self)
            return False

    # ── Edit and delete a request ─────────────────────────────────────────────

    def _prompts_selected_index(self, title: str):
        """Csv index of the selected request; None, with a warning, when there is none."""
        iid = self._tv_prompts.focus()
        i = int(iid) if iid else -1
        if not 0 <= i < len(self._prompts_rows):
            messagebox.showwarning(title, _UI.PRM_NO_SELECTION, parent=self)
            return None
        return i

    def _prompts_replace_row(self, i: int, before: list, row) -> bool:
        """Write row into csv line i, or drop the line when row is None.

        Re-reads first, so a csv edited meanwhile (a run writing its answers, or the
        other app) is never overwritten; a row that changed under the dialog is left
        alone."""
        rows = plog.read_csv()
        if i >= len(rows) or rows[i] != before:
            self._append_log(f'[PROMPTS] Request #{i + 1} changed on disk; nothing '
                             f'written. Reloaded.\n')
            self._prompts_refresh(quiet=True)
            return False
        if row is None:
            del rows[i]
        else:
            rows[i] = row
        if not self._prompts_write(rows):
            return False
        self._prompts_refresh(quiet=True)
        return True

    def _prompts_edit(self) -> None:
        self._prompts_refresh_if_changed()
        i = self._prompts_selected_index(_UI.PRM_BTN_EDIT)
        if i is None:
            return
        before = list(self._prompts_rows[i])
        dlg = tk.Toplevel(self)
        dlg.title(_UI.PRM_EDIT_TITLE.format(n=i + 1))
        dlg.transient(self)
        frm = ttk.Frame(dlg, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        # both datetime columns on one row -- they are read together
        var_req_at = tk.StringVar(value=before[plog.I_REQUESTED])
        var_exe_at = tk.StringVar(value=before[plog.I_EXECUTED])
        var_cat = tk.StringVar(value=before[plog.I_CATEGORY])
        var_files = tk.StringVar(value=before[plog.I_FILES])
        row_dt = ttk.Frame(frm)
        row_dt.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        ttk.Label(row_dt, text=_UI.PRM_COL_REQUESTED).pack(side=tk.LEFT)
        ttk.Entry(row_dt, textvariable=var_req_at, width=20).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row_dt, text=_UI.PRM_COL_EXECUTED).pack(side=tk.LEFT)
        ttk.Entry(row_dt, textvariable=var_exe_at, width=20).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row_dt, text=f'({PromptsLog.DATETIME_FORMAT}; empty executed means '
                               f'pending)', foreground='gray').pack(side=tk.LEFT)

        ttk.Label(frm, text=_UI.PRM_COL_CATEGORY).grid(row=1, column=0, sticky='w')
        # Same width as the Add dialog's: the two-word categories must show whole.
        ttk.Combobox(frm, textvariable=var_cat, values=plog.dialog_categories(),
                     width=24).grid(row=1, column=1, sticky='w', padx=(6, 0), pady=(0, 4))

        boxes = {}
        for row_i, (col, height) in enumerate(((PromptsLog.COL_REQUEST, 8),
                                               (PromptsLog.COL_NOTES, 4),
                                               (PromptsLog.COL_WORK, 6)), start=2):
            ttk.Label(frm, text=_LABELS[col]).grid(row=row_i, column=0, sticky='nw')
            txt = tk.Text(frm, wrap='word', width=76, height=height, undo=True)
            txt.insert('1.0', before[PromptsLog.HEADERS.index(col)])
            txt.grid(row=row_i, column=1, sticky='nsew', padx=(6, 0), pady=(0, 4))
            frm.rowconfigure(row_i, weight=1)
            boxes[col] = txt

        ttk.Label(frm, text=_UI.PRM_COL_FILES).grid(row=5, column=0, sticky='w')
        ttk.Entry(frm, textvariable=var_files).grid(row=5, column=1, sticky='ew',
                                                    padx=(6, 0), pady=(0, 6))

        def _save():
            row = [''] * len(PromptsLog.HEADERS)
            row[plog.I_REQUESTED] = var_req_at.get().strip()
            row[plog.I_EXECUTED] = var_exe_at.get().strip()
            row[plog.I_CATEGORY] = var_cat.get().strip()
            row[plog.I_FILES] = var_files.get().strip()
            for col, box in boxes.items():
                row[PromptsLog.HEADERS.index(col)] = box.get('1.0', tk.END).strip()
            dlg.destroy()
            if row == before:
                return
            if self._prompts_replace_row(i, before, row):
                self._append_log(f'[PROMPTS] Edited request #{i + 1} in {plog.csv_name()}.\n')

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, sticky='w')
        ttk.Button(btns, text=_UI.PRM_BTN_SAVE, style='Action.TButton',
                   command=_save).pack(side=tk.LEFT)
        ttk.Button(btns, text=_UI.PRM_BTN_CANCEL, command=dlg.destroy).pack(side=tk.LEFT, padx=6)
        dlg.grab_set()
        boxes[PromptsLog.COL_REQUEST].focus_set()

    def _prompts_delete(self) -> None:
        self._prompts_refresh_if_changed()
        i = self._prompts_selected_index(_UI.PRM_DEL_TITLE)
        if i is None:
            return
        before = list(self._prompts_rows[i])
        if not messagebox.askyesno(
                _UI.PRM_DEL_TITLE,
                _UI.PRM_DEL_ASK.format(n=i + 1, text=plog.clip(before[plog.I_REQUEST], 200)),
                parent=self):
            return
        if self._prompts_replace_row(i, before, None):
            # the ids of the later requests all move down by one; the bak is the undo
            self._append_log(f'[PROMPTS] Deleted request #{i + 1}; later requests are '
                             f'renumbered.\n')

    # ── The Claude run ────────────────────────────────────────────────────────

    def _prompts_set_running(self, running: bool) -> None:
        """One run at a time, whichever button started it: both are closed while it
        goes, and Stop is what ends it."""
        self._btn_prompts_code.configure(state='disabled' if running else 'normal')
        self._btn_prompts_chat.configure(state='disabled' if running else 'normal')
        self._btn_prompts_stop.configure(state='normal' if running else 'disabled')
        if running:
            self._pb_prompts.start(12)
        else:
            self._pb_prompts.stop()

    def _prompts_stop(self) -> None:
        proc = self._prompts_proc
        if proc is None:
            return
        self._append_log('[Claude] stopping the run…\n')
        try:
            proc.terminate()
        except Exception as exc:
            self._append_log(f'[ERROR] Could not stop the run: {exc}\n')

    def _prompts_code(self) -> None:
        """The Code button: the run that works the pending requests and writes them."""
        if self._prompts_proc is not None:
            self._append_log('[Claude] a run is already going; Stop it first.\n')
            return
        self._prompts_refresh_if_changed()
        dlg = ClaudeRunDialog(self, self._prompts_rows, self._state)
        self.wait_window(dlg)
        cfg = dlg.result
        if not cfg:
            return
        # the choices are kept, so the next dialog opens the way this one closed
        self._state[_PS.KEY_CLAUDE_MODEL] = cfg['model_key']
        self._state[_PS.KEY_CLAUDE_PERMISSION] = cfg['permission_mode']
        self._state[_PS.KEY_CLAUDE_ADD_DIRS] = cfg['add_dirs']
        self._state[_PS.KEY_CLAUDE_EXTRA] = cfg['extra_args']
        if cfg['general'] and cfg['general'] != plog.default_general_prompt():
            self._state[_PS.KEY_CLAUDE_GENERAL] = cfg['general']
        else:
            self._state.pop(_PS.KEY_CLAUDE_GENERAL, None)

        chosen = plog.pending_rows(self._prompts_rows, cfg['picked'])
        if not chosen:
            self._append_log('[Claude] no pending request to send.\n')
            return
        # the stamp rides with the requests, so the run knows exactly what to write into
        # the executed column of each row it finishes
        prompt = plog.compose_prompt(cfg['general'] or plog.default_general_prompt(),
                                     chosen, plog.now_stamp())
        self._claude_start(prompt, cfg, len(chosen))

    # ── The chat ──────────────────────────────────────────────────────────────

    def _prompts_chat(self) -> None:
        """The chat window: questions about the repo, answered in it; nothing coded.

        One window only -- a second click raises the one standing open, so the
        conversation is never split in two."""
        dlg = self._prompts_chat_dlg
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify()
            dlg.lift()
            dlg.focus_set()
            return
        self._prompts_chat_dlg = ChatDialog(self)

    def _prompts_chat_send(self, question: str, model_key: str, context: str) -> bool:
        """One turn of the chat. False means nothing was started, so the box keeps the
        message; a chat picks no row, so it re-reads nothing afterwards."""
        dlg = self._prompts_chat_dlg
        if self._prompts_proc is not None:
            self._append_log('[Claude] a run is already going; Stop it first.\n')
            if dlg is not None:
                dlg.put(_UI.PRM_CHAT_BUSY + '\n', _TAG_META)
            return False
        self._state[_PS.KEY_CLAUDE_MODEL] = model_key
        # the read-only mode and no picked rows: the run has nothing to write, and the
        # prompt says so too, so a chat can never edit the log it is asking about
        cfg = {'kind': _KIND_CHAT, 'model_key': model_key, 'context': context,
               'permission_mode': ClaudeRun.CHAT_PERMISSION_MODE}
        if dlg is not None:
            dlg.set_running(True)
        if not self._claude_start(plog.compose_chat(question), cfg, 0):
            if dlg is not None:
                dlg.set_running(False)
            return False
        return True

    def _prompts_chat_echo(self, text: str, tag: str = _TAG_CLAUDE) -> None:
        """Mirror a line of the running chat into its window; any thread may call --
        the window queues what it is handed and drains it on the main thread."""
        dlg = self._prompts_chat_dlg
        if dlg is not None and self._prompts_chat_run:
            dlg.put(text, tag)

    def _prompts_chat_done(self) -> None:
        """The turn ended: Send opens again and the next one resumes this session."""
        dlg = self._prompts_chat_dlg
        if dlg is None or not dlg.winfo_exists():
            return
        dlg.set_running(False)
        dlg.refresh_context()

    def _claude_argv(self, cfg: dict) -> list:
        """The command line of a run, or [] when the CLI is not on PATH / args are bad."""
        exe = shutil.which(ClaudeRun.EXE)
        if not exe:
            self._append_log(f'[ERROR] The {ClaudeRun.EXE} CLI was not found on PATH.\n')
            return []
        entry = (ClaudeModels.entry(cfg['model_key'])
                 or ClaudeModels.entry(ClaudeModels.DEFAULT_KEY))
        argv = [exe, '--print', '--verbose', '--output-format', ClaudeRun.OUTPUT_FORMAT]
        if entry['model']:
            argv += ['--model', entry['model']]
        if cfg['permission_mode']:
            argv += ['--permission-mode', cfg['permission_mode']]
        for d in (cfg.get('add_dirs') or '').split(ClaudeRun.DIR_SEP):
            if d.strip():
                argv += ['--add-dir', d.strip()]
        session = (self._state.get(_PS.KEY_CLAUDE_SESSION) or '').strip()
        if cfg['context'] == 'continue' and session:
            argv += ['--resume', session]
        # a chat's cfg carries neither dirs nor extra args -- it asks about the repo
        if cfg.get('extra_args'):
            try:
                argv += shlex.split(cfg['extra_args'])
            except ValueError as exc:
                self._append_log(f'[ERROR] Extra CLI args could not be parsed: {exc}\n')
                return []
        return argv

    def _claude_start(self, prompt: str, cfg: dict, n_req: int) -> bool:
        """Start the headless run, Code or Chat. False means nothing was started, which
        is what lets the chat window put its Send back and keep the message typed."""
        argv = self._claude_argv(cfg)
        if not argv:
            return False
        # a chat carries no requests, so it names itself and writes its own prompt file
        is_chat = cfg.get('kind') == _KIND_CHAT
        # the prompt on disk first, so what was sent is always readable back
        try:
            RepoPaths.path_dir_log.mkdir(parents=True, exist_ok=True)
            path_file_prompt = RepoPaths.path_dir_log / (
                RepoPaths.FILE_CLAUDE_CHAT if is_chat else RepoPaths.FILE_CLAUDE_PROMPT)
            path_file_prompt.write_text(prompt + '\n', encoding='utf-8')
        except Exception as exc:
            self._append_log(f'[ERROR] Could not write the prompt file: {exc}\n')
            return False

        entry = (ClaudeModels.entry(cfg['model_key'])
                 or ClaudeModels.entry(ClaudeModels.DEFAULT_KEY))
        session = (self._state.get(_PS.KEY_CLAUDE_SESSION) or '').strip()
        ctx = (f'continuing session {session[:8]}'
               if cfg['context'] == 'continue' and session else 'new session')
        dirs = f", dirs {cfg['add_dirs']}" if cfg.get('add_dirs') else ''
        subject = _UI.PRM_CHAT_SUBJECT if is_chat else f'{n_req} request(s)'
        # what _claude_stream_block mirrors into the chat window, and only then
        self._prompts_chat_run = is_chat
        self._append_log(f'[Claude] starting on {subject}, model {entry["label"]}, '
                         f'permissions {cfg["permission_mode"]}, {ctx}{dirs}\n')
        self._append_log(f'[Claude] prompt in {path_file_prompt}\n')
        self._prompts_set_running(True)
        self._start_background(lambda: self._claude_run(argv, prompt, cfg))
        return True

    def _claude_run(self, argv: list, prompt: str, cfg: dict) -> None:
        """The run itself, on a background thread; nothing here touches tkinter."""
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                cwd=str(RepoPaths.path_dir_root), creationflags=flags)
        except OSError as exc:
            self._log_queue.put(f'[Claude] did not start: {exc}\n')
            self.after(0, lambda: self._claude_run_done(cfg))
            return
        self._prompts_proc = proc
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass
        try:
            for line in proc.stdout:
                line = line.strip()
                if line:
                    self._claude_stream_line(line)
        finally:
            rc = proc.wait()
            self._prompts_proc = None
        self._log_queue.put('[Claude] finished\n' if not rc
                            else f'[Claude] finished (exit {rc})\n')
        self.after(0, lambda: self._claude_run_done(cfg))

    def _claude_run_done(self, cfg: dict) -> None:
        """A run ended, however it ended. A CODE run wrote its answers into the csv, so
        the table is re-read and any picked request left pending is named; a CHAT picked
        nothing and wrote nothing, so only its window is put back in order."""
        self._prompts_set_running(False)
        if cfg.get('kind') == _KIND_CHAT:
            self._prompts_chat_run = False
            self._prompts_chat_done()
            return
        self._prompts_refresh_if_changed()
        left = [i + 1 for i in cfg.get('picked') or []
                if i < len(self._prompts_rows) and plog.is_pending(self._prompts_rows[i])]
        if left:
            self._append_log('[Claude] still pending, fields not filled: %s\n'
                             % ', '.join('#%d' % n for n in left))

    def _claude_stream_line(self, line: str) -> None:
        """One stream-json line of the run, rendered into the log. Background thread:
        everything goes through the log queue."""
        try:
            ev = json.loads(line)
        except ValueError:
            self._log_queue.put(f'[Claude] {line}\n')
            return
        kind = ev.get('type')
        if kind == 'system' and ev.get('subtype') == 'init':
            sid = ev.get('session_id') or ''
            if sid:
                self._state[_PS.KEY_CLAUDE_SESSION] = sid
            self._log_queue.put(f'[Claude] session {sid[:8] or "?"}, '
                                f'model {ev.get("model") or "?"}\n')
        elif kind == 'assistant':
            for block in (ev.get('message') or {}).get('content') or []:
                self._claude_stream_block(block)
        elif kind == 'result':
            sid = ev.get('session_id') or ''
            if sid:
                self._state[_PS.KEY_CLAUDE_SESSION] = sid
            msg = ('[Claude] done: %d turn(s), %.0f s'
                   % (ev.get('num_turns') or 0, (ev.get('duration_ms') or 0) / 1000.0))
            if ev.get('is_error'):
                msg += ', with an error'
            self._log_queue.put(msg + '\n')
            self._prompts_chat_echo(msg[len('[Claude] '):] + '\n', _TAG_META)
        # 'user' events are tool results going back in; too noisy for the log

    def _claude_stream_block(self, block: dict) -> None:
        kind = block.get('type')
        if kind == 'thinking' and (block.get('thinking') or '').strip():
            self._log_queue.put(f'[Claude] thinking: {block["thinking"].strip()}\n')
        elif kind == 'text' and (block.get('text') or '').strip():
            self._log_queue.put(f'[Claude] {block["text"].strip()}\n')
            # the answer, into the window the question was asked in
            self._prompts_chat_echo('%s: %s\n' % (_UI.PRM_CHAT_CLAUDE,
                                                  block['text'].strip()))
        elif kind == 'tool_use':
            brief = _tool_brief(block.get('input'))
            self._log_queue.put(f'[Claude] tool {block.get("name") or "?"}: {brief}\n')
            # dim beside the answer: what it read to get there
            self._prompts_chat_echo('  %s: %s\n' % (block.get('name') or '?', brief),
                                    _TAG_META)
            # the run just touched the log itself; show the change as it lands
            if RepoPaths.path_file_prompts.name in brief:
                self.after(_CSV_SETTLE_MS, self._prompts_refresh_if_changed)
