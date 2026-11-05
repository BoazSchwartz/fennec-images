"""Classify tab -- a folder's files with checkboxes, size and class (left), the actions and a
preview (right), the log (bottom). The classification itself is fennec_images/src/classify.py
and runs on this machine: CLIP (optional, local onnx) + Tesseract OCR + keyword rules."""
from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from fennec_images import config
from fennec_images.gui import common as cm
from fennec_images.src import classify as cl
from fennec_images.src import clip_model, override
from fennec_images.src import extract_text as xt

_UI = config.UIStrings
_ST = config.StyleConfig
_SC = config.SashConfig
_IS = config.ImagesState
_C = config.ClassifyClasses
_P = config.OverridePolicy

_COLS = ('sel', 'size', 'cls', 'conf', 'text', 'name')
_LABELS = {'sel': _UI.COL_SEL, 'size': _UI.COL_SIZE, 'cls': _UI.COL_CLASS,
           'conf': _UI.COL_SCORE, 'text': _UI.COL_TEXT, 'name': _UI.COL_NAME}
_WIDTHS = {'sel': 34, 'size': 80, 'cls': 130, 'conf': 60, 'text': 220, 'name': 400}
_TEXT_CELL = 160                    # characters of the text read shown in the Text cell
_NOT_DONE = 'Not classified'
_WORKERS = max(2, min(6, (os.cpu_count() or 4) - 1))
_PREVIEW_MAX = 520


class ClassifyTabMixin:

    def _build_classify_tab(self) -> None:
        f = self._tab_classify
        self._cls_rows: dict = {}           # iid: {'path','name','size','kind','res'}
        self._cls_checked: set = set()
        self._cls_sort = ('name', False)
        self._cls_cache = cl.load_cache()
        self._cls_clf = None                # (use_model, use_ocr, Classifier) reused across runs
        self._cls_stop = threading.Event()
        self._cls_running = False
        self._cls_photo = None              # keeps the preview image alive

        top = ttk.Frame(f)
        top.pack(fill='x', padx=6, pady=(6, 2))
        ttk.Label(top, text=_UI.LBL_DIR).pack(side='left')
        self._var_cls_dir = tk.StringVar(value=self._state.get(_IS.KEY_CLASSIFY_DIR, ''))
        ent = ttk.Entry(top, textvariable=self._var_cls_dir)
        ent.pack(side='left', fill='x', expand=True, padx=(6, 4))
        ent.bind('<Return>', lambda _e: self._cls_load())
        ttk.Button(top, text=_UI.BTN_BROWSE, command=self._cls_browse).pack(side='left', padx=(0, 4))
        ttk.Button(top, text=_UI.BTN_RELOAD, command=self._cls_load).pack(side='left')

        self._pw_cls_vert = ttk.PanedWindow(f, orient='vertical')
        self._pw_cls_vert.pack(fill='both', expand=True, padx=6, pady=(2, 6))
        self._pw_cls_horiz = ttk.PanedWindow(self._pw_cls_vert, orient='horizontal')
        self._pw_cls_vert.add(self._pw_cls_horiz, weight=3)
        self._build_classify_files()
        self._build_classify_actions()

        log_frame = ttk.Frame(self._pw_cls_vert)
        self._pw_cls_vert.add(log_frame, weight=1)
        self._txt_cls_log = cm.build_log_pane(log_frame)
        self.register_log_widget(self._txt_cls_log)

        label = _UI.TAB_CLASSIFY.strip()
        self.register_sash(_SC.KEY_CLASSIFY_LOG, self._pw_cls_vert, 'vert', f, label=label)
        self.register_sash(_SC.KEY_CLASSIFY_HORIZ, self._pw_cls_horiz, 'horiz', f, label=label)
        self.register_colwidths(_IS.KEY_CLASSIFY_COLS, self._tv_cls, label=label)
        self._tv_cls.bind('<ButtonPress-1>', self._cls_on_click, add='+')
        self._tv_cls.bind('<<TreeviewSelect>>', self._cls_on_select)
        self._tv_cls.bind('<Double-1>', self._cls_on_double)

    def _build_classify_files(self) -> None:
        lf = ttk.LabelFrame(self._pw_cls_horiz, text=_UI.SEC_FILES, padding=4)
        self._pw_cls_horiz.add(lf, weight=3)
        bar = ttk.Frame(lf)
        bar.pack(fill='x', pady=(0, 4))
        ttk.Button(bar, text=_UI.BTN_ALL, width=5, command=self._cls_check_all).pack(side='left')
        ttk.Button(bar, text=_UI.BTN_NONE, width=5, command=self._cls_check_none).pack(side='left', padx=(4, 12))
        ttk.Label(bar, text=_UI.LBL_FILTER).pack(side='left')
        self._var_cls_filter = tk.StringVar(value=_UI.LBL_ALL_CLASSES)
        cb = ttk.Combobox(bar, textvariable=self._var_cls_filter, state='readonly', width=16,
                          values=[_UI.LBL_ALL_CLASSES] + _C.ALL + [_NOT_DONE])
        cb.pack(side='left', padx=(4, 12))
        cb.bind('<<ComboboxSelected>>', lambda _e: self._cls_render())
        self._lbl_cls_count = ttk.Label(bar, text='')
        self._lbl_cls_count.pack(side='right')
        self._tv_cls = cm.build_tree(lf, _COLS, _LABELS, _WIDTHS, sort_cmd=self._cls_sort_by)

    def _build_classify_actions(self) -> None:
        right = ttk.PanedWindow(self._pw_cls_horiz, orient='vertical')
        self._pw_cls_horiz.add(right, weight=2)
        self._pw_cls_right = right
        lf = ttk.LabelFrame(right, text=_UI.SEC_ACTIONS, padding=8)
        right.add(lf, weight=0)

        row = ttk.Frame(lf)
        row.pack(fill='x')
        self._btn_cls_run = ttk.Button(row, text=_UI.BTN_CLASSIFY, style='Action.TButton',
                                       command=self._cls_run)
        self._btn_cls_run.pack(side='left')
        self._btn_cls_stop = ttk.Button(row, text=_UI.BTN_STOP, command=self._cls_stop.set,
                                        state='disabled')
        self._btn_cls_stop.pack(side='left', padx=(6, 0))
        self._pb_cls = ttk.Progressbar(row, mode='determinate', length=140)
        self._pb_cls.pack(side='left', padx=(10, 0), fill='x', expand=True)

        opts = ttk.Frame(lf)
        opts.pack(fill='x', pady=(8, 0))
        self._var_cls_model = tk.BooleanVar(value=self._state.get(_IS.KEY_USE_MODEL, True))
        self._var_cls_ocr = tk.BooleanVar(value=self._state.get(_IS.KEY_USE_OCR, True))
        self._var_cls_nocache = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text=_UI.CHK_USE_MODEL, variable=self._var_cls_model).pack(side='left')
        ttk.Checkbutton(opts, text=_UI.CHK_USE_OCR, variable=self._var_cls_ocr).pack(side='left', padx=8)
        ttk.Checkbutton(opts, text=_UI.CHK_RECLASSIFY, variable=self._var_cls_nocache).pack(side='left')

        st = ttk.Frame(lf)
        st.pack(fill='x', pady=(6, 0))
        self._lbl_cls_model = ttk.Label(st, foreground='gray')
        self._lbl_cls_model.pack(side='left')
        self._btn_cls_download = ttk.Button(st, text=_UI.BTN_DOWNLOAD_MODEL, command=self._cls_download)
        self._btn_cls_download.pack(side='right')
        self._lbl_cls_ocr = ttk.Label(lf, foreground='gray',
                                      text=_UI.LBL_OCR_ON if xt.tesseract_exe() else _UI.LBL_OCR_OFF)
        self._lbl_cls_ocr.pack(anchor='w')
        self._cls_model_status()

        ttk.Separator(lf).pack(fill='x', pady=8)
        row = ttk.Frame(lf)
        row.pack(fill='x')
        self._var_cls_set = tk.StringVar(value=_C.TRIP)
        ttk.Combobox(row, textvariable=self._var_cls_set, values=_C.ALL, state='readonly',
                     width=16).pack(side='left')
        ttk.Button(row, text=_UI.BTN_SET_CLASS, command=self._cls_set_class).pack(side='left', padx=(6, 0))
        ttk.Button(row, text=_UI.BTN_OPEN, command=self._cls_open).pack(side='right')

        row = ttk.Frame(lf)
        row.pack(fill='x', pady=(8, 0))
        ttk.Button(row, text=_UI.BTN_COPY, command=self._cls_copy).pack(side='left')
        ttk.Label(row, text=_UI.LBL_POLICY).pack(side='left', padx=(10, 4))
        self._var_cls_policy = tk.StringVar(value=self._state.get(_IS.KEY_POLICY, _P.DEFAULT))
        ttk.Combobox(row, textvariable=self._var_cls_policy, values=_P.ALL, state='readonly',
                     width=9).pack(side='left')

        pv = ttk.LabelFrame(right, text=_UI.SEC_PREVIEW, padding=4)
        right.add(pv, weight=1)
        self._lbl_cls_preview = ttk.Label(pv, anchor='center')
        self._lbl_cls_preview.pack(fill='both', expand=True)
        self._txt_cls_info = tk.Text(pv, height=7, wrap='word', state='disabled', relief='flat',
                                     background='#fafafa')
        self._txt_cls_info.pack(fill='x', side='bottom')
        self.register_sash(_IS.KEY_CLASSIFY_PREVIEW, right, 'vert', self._tab_classify)

    # ── Folder ────────────────────────────────────────────────────────────────

    def _cls_browse(self) -> None:
        start = self._var_cls_dir.get() or self._var_project_root.get() or os.path.expanduser('~')
        path = filedialog.askdirectory(title=_UI.LBL_DIR, initialdir=start, parent=self)
        if path:
            self._var_cls_dir.set(os.path.normpath(path))
            self._cls_load()

    def _cls_load(self) -> None:
        path_dir = self._var_cls_dir.get().strip()
        if not path_dir:
            return
        if not os.path.isdir(path_dir):
            self._append_log(f'[CLASSIFY] Not a folder: {path_dir}\n')
            return
        self._state[_IS.KEY_CLASSIFY_DIR] = path_dir
        rows = cl.list_files(path_dir)
        self._cls_rows = {}
        for i, r in enumerate(rows):
            r['res'] = cl.cached(self._cls_cache, r['path'])
            self._cls_rows[str(i)] = r
        self._cls_checked = set()
        n_done = sum(1 for r in rows if r['res'])
        kinds = {}
        for r in rows:
            kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
        self._append_log(f'[CLASSIFY] {path_dir}: {len(rows)} files '
                         f'({", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))}), '
                         f'{n_done} already classified\n')
        self._cls_render()

    # ── Table ─────────────────────────────────────────────────────────────────

    def _cls_values(self, iid: str) -> tuple:
        r = self._cls_rows[iid]
        res = r['res']
        return (cm.CHK_ON if iid in self._cls_checked else cm.CHK_OFF, cl.fmt_size(r['size']),
                res.cls if res else '', f'{res.conf:.2f}' if res else '',
                _one_line(res.text)[:_TEXT_CELL] if res else '', r['name'])

    def _cls_sort_key(self, col: str):
        def key(iid):
            r = self._cls_rows[iid]
            res = r['res']
            if col == 'size':
                return r['size']
            if col == 'cls':
                return (res.cls if res else '~', r['name'].lower())
            if col == 'conf':
                return res.conf if res else -1.0
            if col == 'text':
                return (not (res and res.text.strip()), _one_line(res.text).lower() if res else '')
            return r['name'].lower()
        return key

    def _cls_render(self) -> None:
        tv = self._tv_cls
        tv.delete(*tv.get_children())
        flt = self._var_cls_filter.get()
        col, rev = self._cls_sort
        iids = sorted(self._cls_rows, key=self._cls_sort_key(col), reverse=rev)
        shown = 0
        for iid in iids:
            res = self._cls_rows[iid]['res']
            if flt == _NOT_DONE and res:
                continue
            if flt not in (_UI.LBL_ALL_CLASSES, _NOT_DONE) and (not res or res.cls != flt):
                continue
            tv.insert('', tk.END, iid=iid, values=self._cls_values(iid),
                      tags=('row_even' if shown % 2 == 0 else 'row_odd',))
            shown += 1
        for c in _COLS:
            arrow = (' ▼' if rev else ' ▲') if c == col else ''
            tv.heading(c, text=_LABELS[c] + arrow)
        self._cls_update_count()

    def _cls_update_count(self) -> None:
        shown = len(self._tv_cls.get_children())
        self._lbl_cls_count.configure(
            text=f'{shown} / {len(self._cls_rows)} files, {len(self._cls_checked)} checked')

    def _cls_refresh_row(self, iid: str) -> None:
        if self._tv_cls.exists(iid):
            self._tv_cls.item(iid, values=self._cls_values(iid))

    def _cls_sort_by(self, col: str) -> None:
        if col == 'sel':
            return
        cur, rev = self._cls_sort
        self._cls_sort = (col, not rev if cur == col else False)
        self._cls_render()

    def _cls_on_click(self, event):
        tv = self._tv_cls
        if tv.identify_region(event.x, event.y) != 'cell' or tv.identify_column(event.x) != '#1':
            return None
        iid = tv.identify_row(event.y)
        if not iid:
            return None
        self._cls_checked.symmetric_difference_update({iid})
        self._cls_refresh_row(iid)
        self._cls_update_count()
        return 'break'

    def _cls_check_all(self) -> None:
        self._cls_checked |= set(self._tv_cls.get_children())
        for iid in self._tv_cls.get_children():
            self._cls_refresh_row(iid)
        self._cls_update_count()

    def _cls_check_none(self) -> None:
        self._cls_checked.clear()
        for iid in self._tv_cls.get_children():
            self._cls_refresh_row(iid)
        self._cls_update_count()

    def _cls_targets(self) -> list:
        """The checked rows, or the selected ones when nothing is checked."""
        iids = [i for i in self._cls_rows if i in self._cls_checked]
        return iids or list(self._tv_cls.selection())

    # ── Preview ───────────────────────────────────────────────────────────────

    def _cls_on_select(self, _event=None) -> None:
        sel = self._tv_cls.selection()
        if not sel:
            return
        r = self._cls_rows[sel[0]]
        res = r['res']
        info = [r['name'], f'{cl.fmt_size(r["size"])}   {r["kind"]}']
        if res:
            info.append(f'{res.cls}  ({res.conf:.2f}, {res.method})')
            info.append(res.reason)
            if res.text.strip():
                info += ['', ' '.join(res.text.split())[:400]]
        cm.set_text(self._txt_cls_info, '\n'.join(info))
        self._cls_photo = None
        self._lbl_cls_preview.configure(image='', text='')
        try:
            im = self._cls_preview_image(r)
        except Exception as exc:
            self._lbl_cls_preview.configure(text=f'(no preview: {exc})')
            return
        if im is None:
            self._lbl_cls_preview.configure(text='(no preview)')
            return
        w = max(120, min(_PREVIEW_MAX, self._lbl_cls_preview.winfo_width() - 8))
        h = max(120, min(_PREVIEW_MAX, self._lbl_cls_preview.winfo_height() - 8))
        im.thumbnail((w, h))
        self._cls_photo = ImageTk.PhotoImage(im)
        self._lbl_cls_preview.configure(image=self._cls_photo)

    def _cls_preview_image(self, r: dict):
        if r['kind'] == 'image':
            return xt.open_image(r['path'])
        if r['path'].lower().endswith('.pdf'):
            import fitz
            with fitz.open(r['path']) as doc:
                pix = doc[0].get_pixmap(dpi=60)
                return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        return None

    # ── Classify ──────────────────────────────────────────────────────────────

    def _cls_model_status(self) -> None:
        ready = clip_model.model_ready()
        self._lbl_cls_model.configure(text=_UI.LBL_MODEL_ON if ready else _UI.LBL_MODEL_OFF)
        self._btn_cls_download.configure(state='disabled' if ready else 'normal')

    def _cls_download(self) -> None:
        self._btn_cls_download.configure(state='disabled')

        def work():
            try:
                clip_model.download_model(log=self._log_queue.put)
            except Exception as exc:
                self._log_queue.put(f'[ERROR] Model download failed: {exc}\n')
            self.after(0, self._cls_model_status)

        self._start_background(work)

    def _cls_set_running(self, running: bool) -> None:
        self._cls_running = running
        self._btn_cls_run.configure(state='disabled' if running else 'normal')
        self._btn_cls_stop.configure(state='normal' if running else 'disabled')

    def _cls_run(self) -> None:
        if self._cls_running:
            return
        iids = self._cls_targets()
        if not iids:
            messagebox.showinfo(_UI.BTN_CLASSIFY, 'Check the files to classify first.', parent=self)
            return
        use_model, use_ocr = self._var_cls_model.get(), self._var_cls_ocr.get()
        self._state[_IS.KEY_USE_MODEL], self._state[_IS.KEY_USE_OCR] = use_model, use_ocr
        nocache = self._var_cls_nocache.get()
        jobs = [(iid, self._cls_rows[iid]['path']) for iid in iids]
        others = [r['res'] for i, r in self._cls_rows.items() if r['res'] and i not in set(iids)]
        cache = dict(self._cls_cache)
        self._cls_stop.clear()
        self._cls_set_running(True)
        self._pb_cls.configure(maximum=len(jobs), value=0)
        self._append_log(f'[CLASSIFY] {len(jobs)} file(s), model {"on" if use_model else "off"}, '
                         f'OCR {"on" if use_ocr else "off"}{", cache ignored" if nocache else ""}\n')

        def work():
            clf = self._cls_classifier(use_model, use_ocr)
            done, todo = [], []
            for iid, path in jobs:
                res = None if nocache else cl.cached(cache, path)
                if res and not res.manual and use_model and clf.clip is not None and 'clip' not in res.method:
                    res = None            # made without the model, which is here now
                (done.append((iid, res)) if res else todo.append((iid, path)))
            self.after(0, lambda n=len(done): self._cls_progress(n))
            with ThreadPoolExecutor(_WORKERS) as ex:
                futs = {ex.submit(clf.classify, p): iid for iid, p in todo}
                for fut in as_completed(futs):
                    if self._cls_stop.is_set():
                        for f2 in futs:
                            f2.cancel()
                        break
                    res = fut.result()
                    done.append((futs[fut], res))
                    self.after(0, lambda i=futs[fut], r=res: self._cls_one_done(i, r))
            n_smooth = cl.smooth_by_events([r for _i, r in done] + others)
            self.after(0, lambda d=done, n=n_smooth: self._cls_run_done(d, n))

        self._start_background(work)

    def _cls_classifier(self, use_model: bool, use_ocr: bool):
        if self._cls_clf and self._cls_clf[:2] == (use_model, use_ocr):
            return self._cls_clf[2]
        clf = cl.Classifier(use_model, use_ocr, log=self._log_queue.put)
        self._cls_clf = (use_model, use_ocr, clf)
        return clf

    def _cls_progress(self, n: int) -> None:
        self._pb_cls.configure(value=self._pb_cls['value'] + n)

    def _cls_one_done(self, iid: str, res) -> None:
        if iid in self._cls_rows:
            self._cls_rows[iid]['res'] = res
            self._cls_refresh_row(iid)
        self._cls_progress(1)
        if res.cls == _C.UNKNOWN:
            self._append_log(f'[CLASSIFY] {os.path.basename(res.path)}: {res.reason}\n')

    def _cls_run_done(self, done: list, n_smooth: int) -> None:
        for iid, res in done:
            if iid in self._cls_rows:
                self._cls_rows[iid]['res'] = res
            cl.remember(self._cls_cache, res)
        for r in self._cls_rows.values():          # smoothing may have moved earlier results too
            if r['res']:
                cl.remember(self._cls_cache, r['res'])
        self._cls_save_cache()
        self._cls_set_running(False)
        self._cls_render()
        counts = {}
        for _i, res in done:
            counts[res.cls] = counts.get(res.cls, 0) + 1
        stopped = ' (stopped)' if self._cls_stop.is_set() else ''
        self._append_log(f'[CLASSIFY] done{stopped}: {len(done)} file(s) -- '
                         + ', '.join(f'{c} {counts[c]}' for c in _C.ALL if c in counts)
                         + (f'; {n_smooth} photo(s) moved to their event\'s class' if n_smooth else '') + '\n')

    def _cls_save_cache(self) -> None:
        try:
            cl.save_cache(self._cls_cache)
        except OSError as exc:
            self._append_log(f'[ERROR] Cannot save the class cache: {exc}\n')

    # ── Text popup ────────────────────────────────────────────────────────────

    def _cls_on_double(self, event):
        tv = self._tv_cls
        iid = tv.identify_row(event.y)
        if not iid or tv.identify_region(event.x, event.y) != 'cell':
            return None
        if tv.identify_column(event.x) == f'#{_COLS.index("text") + 1}':
            self._cls_show_text(iid)
        else:
            self._cls_open()
        return 'break'

    def _cls_show_text(self, iid: str) -> None:
        """A window with all the text of the file; the cache keeps only a snippet, so a
        truncated or missing text is read again from the file on a background thread."""
        r = self._cls_rows[iid]
        res = r['res']
        text = res.text if res else ''
        win = tk.Toplevel(self)
        win.title(f'{_UI.TITLE_TEXT} -- {r["name"]}')
        win.geometry('720x520')
        win.transient(self)
        bar = ttk.Frame(win, padding=(6, 6, 6, 0))
        bar.pack(fill='x')
        lbl = ttk.Label(bar, foreground='gray')
        lbl.pack(side='left')
        ttk.Button(bar, text=_UI.BTN_CLOSE, command=win.destroy).pack(side='right')
        frame = ttk.Frame(win, padding=6)
        frame.pack(fill='both', expand=True)
        txt = tk.Text(frame, wrap='word', state='disabled', font=('Segoe UI', 11))
        vsb = ttk.Scrollbar(frame, orient='vertical', command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        txt.pack(side='left', fill='both', expand=True)

        def copy():
            self.clipboard_clear()
            self.clipboard_append(txt.get('1.0', 'end-1c'))

        ttk.Button(bar, text=_UI.BTN_COPY_TEXT, command=copy).pack(side='right', padx=(0, 6))
        win.bind('<Escape>', lambda _e: win.destroy())

        def show(body: str, note: str = '') -> None:
            if not win.winfo_exists():
                return
            cm.set_text(txt, body.strip() or _UI.LBL_TEXT_NONE)
            n = len(body.split())
            lbl.configure(text=note or f'{n} words, {len(body)} characters')

        if text and len(text) < cl.TEXT_SNIPPET:
            show(text)
            return
        show(text, _UI.LBL_TEXT_READING)
        path, kind, use_ocr = r['path'], r['kind'], self._var_cls_ocr.get()

        def work():
            try:
                if kind == 'image':
                    full, _n = xt.ocr_image(xt.open_image(path)) if use_ocr else ('', 0)
                else:
                    full, _n, _m = xt.read_document(path, use_ocr)
            except Exception as exc:
                self._log_queue.put(f'[ERROR] Cannot read the text of {r["name"]}: {exc}\n')
                full = ''
            self.after(0, lambda: show(full or text))

        self._start_background(work)

    # ── Manual class, open, copy ──────────────────────────────────────────────

    def _cls_set_class(self) -> None:
        iids = self._cls_targets()
        cls = self._var_cls_set.get()
        if not iids or not cls:
            return
        for iid in iids:
            r = self._cls_rows[iid]
            res = r['res'] or cl.Result(r['path'], kind=r['kind'])
            res.cls, res.conf, res.manual = cls, 1.0, True
            res.method = 'manual'
            r['res'] = res
            cl.remember(self._cls_cache, res)
            self._cls_refresh_row(iid)
        self._cls_save_cache()
        self._append_log(f'[CLASSIFY] {len(iids)} file(s) set to {cls}\n')

    def _cls_open(self) -> None:
        sel = self._tv_cls.selection()
        if sel:
            try:
                cm.open_path(self._cls_rows[sel[0]]['path'])
            except OSError as exc:
                self._append_log(f'[ERROR] {exc}\n')

    def _cls_copy(self) -> None:
        iids = [i for i in self._cls_targets() if self._cls_rows[i]['res']]
        if not iids:
            messagebox.showinfo(_UI.BTN_COPY, 'Check classified files first.', parent=self)
            return
        policy = self._var_cls_policy.get()
        self._state[_IS.KEY_POLICY] = policy
        base = self._var_cls_dir.get().strip()
        if not messagebox.askyesno(_UI.BTN_COPY, f'Copy {len(iids)} file(s) into class folders under\n'
                                   f'{base}\n\nIf a file exists: {policy}', parent=self):
            return
        jobs = [(self._cls_rows[i]['path'], self._cls_rows[i]['res'].cls) for i in iids]

        def work():
            n_copy = n_skip = 0
            for path, cls in jobs:
                try:
                    dst_dir = os.path.join(base, cls)
                    os.makedirs(dst_dir, exist_ok=True)
                    dst = os.path.join(dst_dir, os.path.basename(path))
                    if override.prepare(dst, policy):
                        shutil.copy2(path, dst)
                        n_copy += 1
                    else:
                        n_skip += 1
                except OSError as exc:
                    self._log_queue.put(f'[ERROR] {os.path.basename(path)}: {exc}\n')
            self._log_queue.put(f'[COPY] {n_copy} copied, {n_skip} skipped (exists) into {base}\n')

        self._start_background(work)


def _one_line(text: str) -> str:
    return ' '.join((text or '').split())
