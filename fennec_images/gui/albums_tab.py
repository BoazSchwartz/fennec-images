"""Albums tab -- the fennec_album pipeline (scan, events, select, enhance, layout, PDF) behind
buttons: the build settings and the album's events (left), the actions (right), the log
(bottom). The browser editor (fennec_album/server.py) runs on a daemon thread of the app."""
from __future__ import annotations

import contextlib
import os
import socket
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from fennec_images import config
from fennec_images.gui import common as cm

_UI = config.UIStrings
_SC = config.SashConfig
_IS = config.ImagesState

_COLS = ('count', 'date', 'name')
_LABELS = {'count': _UI.COL_COUNT, 'date': _UI.COL_DATE, 'name': _UI.COL_EVENT}
_WIDTHS = {'count': 70, 'date': 150, 'name': 300}
_PORT0 = 8765


class _QueueWriter:
    """stdout of the pipeline, line by line into the app's log queue ('\\r' progress too)."""

    def __init__(self, q):
        self.q, self.buf = q, ''

    def write(self, s):
        self.buf += s.replace('\r', '\n')
        while '\n' in self.buf:
            line, self.buf = self.buf.split('\n', 1)
            if line.strip():
                self.q.put(f'[ALBUM] {line.strip()}\n')

    def flush(self):
        pass


class AlbumsTabMixin:

    def _build_albums_tab(self) -> None:
        f = self._tab_albums
        self._alb_servers: dict = {}         # album dir: port of its running editor
        self._alb_busy = False
        self._pw_alb_vert = ttk.PanedWindow(f, orient='vertical')
        self._pw_alb_vert.pack(fill='both', expand=True, padx=6, pady=6)
        self._pw_alb_horiz = ttk.PanedWindow(self._pw_alb_vert, orient='horizontal')
        self._pw_alb_vert.add(self._pw_alb_horiz, weight=3)

        left = ttk.Frame(self._pw_alb_horiz)
        self._pw_alb_horiz.add(left, weight=3)
        self._build_albums_settings(left)
        ev = ttk.LabelFrame(left, text=_UI.SEC_ALBUM_EVENTS, padding=4)
        ev.pack(fill='both', expand=True, pady=(6, 0))
        self._tv_alb = cm.build_tree(ev, _COLS, _LABELS, _WIDTHS)

        right = ttk.LabelFrame(self._pw_alb_horiz, text=_UI.SEC_ACTIONS, padding=8)
        self._pw_alb_horiz.add(right, weight=1)
        self._alb_buttons = []
        for text, cmd, style in ((_UI.BTN_BUILD, self._alb_build, 'Action.TButton'),
                                 (_UI.BTN_LOAD, self._alb_load, 'TButton'),
                                 (_UI.BTN_EDITOR, self._alb_editor, 'TButton'),
                                 (_UI.BTN_EXPORT, self._alb_export, 'TButton'),
                                 (_UI.BTN_RELAYOUT, self._alb_relayout, 'TButton'),
                                 (_UI.BTN_OPEN_FOLDER, self._alb_open_folder, 'TButton')):
            b = ttk.Button(right, text=text, command=cmd, style=style)
            b.pack(fill='x', pady=(0, 6))
            self._alb_buttons.append(b)
        self._pb_alb = ttk.Progressbar(right, mode='indeterminate')
        self._pb_alb.pack(fill='x', pady=(6, 0))

        log_frame = ttk.Frame(self._pw_alb_vert)
        self._pw_alb_vert.add(log_frame, weight=1)
        self._txt_alb_log = cm.build_log_pane(log_frame)
        self.register_log_widget(self._txt_alb_log)
        label = _UI.TAB_ALBUMS.strip()
        self.register_sash(_SC.KEY_ALBUMS_LOG, self._pw_alb_vert, 'vert', f, label=label)
        self.register_sash(_SC.KEY_ALBUMS_HORIZ, self._pw_alb_horiz, 'horiz', f, label=label)
        self.register_colwidths(_IS.KEY_ALBUM_COLS, self._tv_alb, label=label)

    def _build_albums_settings(self, parent) -> None:
        from fennec_album.model import PAGE_SIZES_MM
        lf = ttk.LabelFrame(parent, text=_UI.SEC_ALBUM_BUILD, padding=8)
        lf.pack(fill='x')
        lf.columnconfigure(1, weight=1)
        s = self._state
        self._var_alb_src = tk.StringVar(value=s.get(_IS.KEY_ALBUM_SOURCE, ''))
        self._var_alb_out = tk.StringVar(value=s.get(_IS.KEY_ALBUM_OUT, ''))
        for r, (lbl, var) in enumerate(((_UI.LBL_SOURCE, self._var_alb_src),
                                        (_UI.LBL_ALBUM_DIR, self._var_alb_out))):
            ttk.Label(lf, text=lbl).grid(row=r, column=0, sticky='w', padx=(0, 6), pady=2)
            cm.path_entry(lf, var).grid(row=r, column=1, sticky='ew', pady=2)
            ttk.Button(lf, text=_UI.BTN_BROWSE, command=lambda v=var, t=lbl: self._alb_browse(v, t)).grid(
                row=r, column=2, padx=(4, 0), pady=2)

        row = ttk.Frame(lf)
        row.grid(row=2, column=0, columnspan=3, sticky='w', pady=(6, 0))
        self._var_alb_count = tk.StringVar(value=str(s.get(_IS.KEY_ALBUM_COUNT, 60)))
        self._var_alb_title = tk.StringVar()
        self._var_alb_page = tk.StringVar(value=s.get(_IS.KEY_ALBUM_PAGE, 'a4-landscape'))
        ttk.Label(row, text=_UI.LBL_COUNT).pack(side='left')
        ttk.Spinbox(row, from_=4, to=500, textvariable=self._var_alb_count, width=6).pack(side='left', padx=(4, 12))
        ttk.Label(row, text=_UI.LBL_TITLE).pack(side='left')
        ttk.Entry(row, textvariable=self._var_alb_title, width=24).pack(side='left', padx=(4, 12))
        ttk.Label(row, text=_UI.LBL_PAGE).pack(side='left')
        ttk.Combobox(row, textvariable=self._var_alb_page, values=sorted(PAGE_SIZES_MM),
                     state='readonly', width=14).pack(side='left', padx=(4, 0))

        row = ttk.Frame(lf)
        row.grid(row=3, column=0, columnspan=3, sticky='w', pady=(6, 0))
        self._var_alb_gap = tk.StringVar(value='3')
        self._var_alb_jump = tk.StringVar(value='3')
        self._var_alb_div = tk.StringVar(value='0.55')
        self._var_alb_enh = tk.BooleanVar(value=True)
        self._var_alb_geo = tk.BooleanVar(value=False)
        for lbl, var in ((_UI.LBL_GAP, self._var_alb_gap), (_UI.LBL_JUMP, self._var_alb_jump),
                         (_UI.LBL_DIVERSITY, self._var_alb_div)):
            ttk.Label(row, text=lbl).pack(side='left')
            ttk.Entry(row, textvariable=var, width=6).pack(side='left', padx=(4, 12))
        ttk.Checkbutton(row, text=_UI.CHK_ENHANCE, variable=self._var_alb_enh).pack(side='left')
        ttk.Checkbutton(row, text=_UI.CHK_GEOCODE, variable=self._var_alb_geo).pack(side='left', padx=(8, 0))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _alb_browse(self, var, title) -> None:
        start = var.get() or self._var_project_root.get() or os.path.expanduser('~')
        path = filedialog.askdirectory(title=title, initialdir=start, parent=self)
        if path:
            var.set(os.path.normpath(path))

    def _alb_remember(self) -> None:
        s = self._state
        s[_IS.KEY_ALBUM_SOURCE] = self._var_alb_src.get().strip()
        s[_IS.KEY_ALBUM_OUT] = self._var_alb_out.get().strip()
        s[_IS.KEY_ALBUM_PAGE] = self._var_alb_page.get()
        try:
            s[_IS.KEY_ALBUM_COUNT] = int(self._var_alb_count.get())
        except ValueError:
            pass

    def _alb_out_dir(self, must_exist: bool = True) -> str:
        for var in (self._var_alb_src, self._var_alb_out):     # a pasted "C:\..." keeps its quotes
            var.set(cm.clean_path(var.get()))
        out = self._var_alb_out.get()
        if not out:
            messagebox.showinfo(_UI.TAB_ALBUMS.strip(), 'Choose the album folder first.', parent=self)
            return ''
        if not os.path.isabs(out):                 # would land under the app's working folder
            messagebox.showinfo(_UI.TAB_ALBUMS.strip(), f'The album folder must be a full path:\n{out}',
                                parent=self)
            return ''
        if must_exist and not os.path.isfile(os.path.join(out, 'album.json')):
            messagebox.showinfo(_UI.TAB_ALBUMS.strip(), f'No album.json in\n{out}\n\nBuild the album first.',
                                parent=self)
            return ''
        return out

    def _alb_busy_set(self, busy: bool) -> None:
        self._alb_busy = busy
        for b in self._alb_buttons:
            b.configure(state='disabled' if busy else 'normal')
        if busy:
            self._pb_alb.start(12)
        else:
            self._pb_alb.stop()

    def _alb_task(self, title: str, fn) -> None:
        """Run fn() in the background with the pipeline's prints going to the log."""
        if self._alb_busy:
            return
        self._alb_busy_set(True)
        self._append_log(f'[ALBUM] {title} ...\n')

        def work():
            album = None
            try:
                with contextlib.redirect_stdout(_QueueWriter(self._log_queue)):
                    album = fn()
            except SystemExit as exc:          # the pipeline reports user errors this way
                self._log_queue.put(f'[ALBUM] {exc}\n')
            except Exception as exc:
                self._log_queue.put(f'[ERROR] {title}: {type(exc).__name__}: {exc}\n')
            self.after(0, lambda a=album: self._alb_task_done(a))

        self._start_background(work)

    def _alb_task_done(self, album) -> None:
        self._alb_busy_set(False)
        if album is not None:
            self._alb_show(album)

    def _alb_show(self, album) -> None:
        tv = self._tv_alb
        tv.delete(*tv.get_children())
        for i, e in enumerate(album.events):
            tv.insert('', tk.END, values=(e.get('count', ''), (e.get('start') or '')[:16].replace('T', ' '),
                                          e.get('name', '')),
                      tags=('row_even' if i % 2 == 0 else 'row_odd',))
        self._append_log(f'[ALBUM] "{album.title}": {len(album.pages)} pages, {len(album.events)} events, '
                         f'{len(album.used_photo_ids())} photos used of {len(album.photos)}\n')

    # ── Actions ───────────────────────────────────────────────────────────────

    def _alb_build(self) -> None:
        out = self._alb_out_dir(must_exist=False)
        src = self._var_alb_src.get()
        if not out:
            return
        if not os.path.isdir(src):
            messagebox.showinfo(_UI.BTN_BUILD, 'Choose the photos folder first.', parent=self)
            return
        try:
            count = int(self._var_alb_count.get())
            gap, jump = float(self._var_alb_gap.get()), float(self._var_alb_jump.get())
            div = float(self._var_alb_div.get())
        except ValueError:
            messagebox.showerror(_UI.BTN_BUILD, 'Photos, gap, jump and diversity must be numbers.', parent=self)
            return
        if os.path.isfile(os.path.join(out, 'album.json')) and not messagebox.askyesno(
                _UI.BTN_BUILD, f'An album already exists in\n{out}\n\nBuild it again (its edits are lost)?',
                parent=self):
            return
        self._alb_remember()
        title = self._var_alb_title.get().strip() or None
        page, enh, geo = self._var_alb_page.get(), self._var_alb_enh.get(), self._var_alb_geo.get()

        def fn():
            from fennec_album.pipeline import build_album
            return build_album(src, out, count, title=title, page_size=page, gap_hours=gap,
                               jump_km=jump, enhance=enh, geocode=geo, diversity=div,
                               workers=max(1, (os.cpu_count() or 4) - 1))

        self._alb_task(_UI.BTN_BUILD, fn)

    def _alb_load(self) -> None:
        out = self._alb_out_dir()
        if out:
            from fennec_album.model import Album
            self._alb_remember()
            try:
                self._alb_show(Album.load(out))
            except Exception as exc:
                self._append_log(f'[ERROR] Load album: {exc}\n')

    def _alb_export(self) -> None:
        out = self._alb_out_dir()
        if not out:
            return

        def fn():
            from fennec_album.model import Album
            from fennec_album.render import export_pdf
            album = Album.load(out)
            pdf = os.path.join(out, 'album.pdf')
            export_pdf(album, pdf, dpi=300, progress=lambda i, n: print(f'page {i}/{n}') if i == n or i % 5 == 0 else None)
            print(f'Wrote {pdf} ({os.path.getsize(pdf) / 1e6:.1f} MB)')
            return album

        self._alb_task(_UI.BTN_EXPORT, fn)

    def _alb_relayout(self) -> None:
        out = self._alb_out_dir()
        if not out:
            return

        def fn():
            import random
            from fennec_album.model import Album
            from fennec_album.pipeline import relayout_album
            return relayout_album(Album.load(out), seed=random.randint(1, 10_000))

        self._alb_task(_UI.BTN_RELAYOUT, fn)

    def _alb_editor(self) -> None:
        out = self._alb_out_dir()
        if not out:
            return
        port = self._alb_servers.get(out)
        if port is None:
            port = _free_port(_PORT0 + len(self._alb_servers))
            self._alb_servers[out] = port

            def run():
                from fennec_album.server import serve
                try:
                    serve(out, port=port, open_browser=False)     # blocks for the app's lifetime
                except Exception as exc:
                    self._log_queue.put(f'[ERROR] Editor: {exc}\n')
                    self._alb_servers.pop(out, None)

            threading.Thread(target=run, daemon=True).start()
            self.after(700, lambda: webbrowser.open(f'http://127.0.0.1:{port}/'))
        else:
            webbrowser.open(f'http://127.0.0.1:{port}/')
        self._append_log(f'[ALBUM] editor at http://127.0.0.1:{port}/ (runs while the app is open)\n')

    def _alb_open_folder(self) -> None:
        out = cm.clean_path(self._var_alb_out.get())
        if out and os.path.isdir(out):
            cm.open_path(out)


def _free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start
