"""Classify tab -- a folder's files with checkboxes, size, class and people (left), the actions
and a preview (right), the log (bottom). The classification itself is
fennec_images/src/classify.py and runs on this machine: CLIP (optional, local onnx) + Tesseract
OCR + keyword rules; the people are src/faces.py (YuNet + SFace, named in Tag People)."""
from __future__ import annotations

import os
import shutil
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from fennec_images import config
from fennec_images.gui import common as cm
from fennec_images.src import classify as cl
from fennec_images.src import class_sheet as sh
from fennec_images.src import clip_model, override
from fennec_images.src import extract_text as xt
from fennec_images.src import faces as fc

_UI = config.UIStrings
_ST = config.StyleConfig
_SC = config.SashConfig
_IS = config.ImagesState
_C = config.ClassifyClasses
_P = config.OverridePolicy
_FM = config.FaceModel
_SH = config.ClassifySheet

_COLS = ('sel', 'size', 'cls', 'conf', 'people', 'text', 'name')
_LABELS = {'sel': _UI.COL_SEL, 'size': _UI.COL_SIZE, 'cls': _UI.COL_CLASS,
           'conf': _UI.COL_SCORE, 'people': _UI.COL_PEOPLE, 'text': _UI.COL_TEXT,
           'name': _UI.COL_NAME}
_WIDTHS = {'sel': 34, 'size': 80, 'cls': 130, 'conf': 60, 'people': 140, 'text': 220, 'name': 400}
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
        self._cls_dir = ''                  # the folder loaded, where its sheet is written
        self._cls_people = fc.load_people()  # name: the faces tagged, shared with the classifier
        self._cls_facer = None              # the face models of Tag People, loaded once
        self._cls_run_stat: dict = {}       # t0, total, done, cache of the run (the status line)

        top = ttk.Frame(f)
        top.pack(fill='x', padx=6, pady=(6, 2))
        ttk.Label(top, text=_UI.LBL_DIR).pack(side='left')
        self._var_cls_dir = tk.StringVar(value=self._state.get(_IS.KEY_CLASSIFY_DIR, ''))
        ent = cm.path_entry(top, self._var_cls_dir)
        ent.pack(side='left', fill='x', expand=True, padx=(6, 4))
        ent.bind('<Return>', lambda _e: self._cls_load())
        ttk.Button(top, text=_UI.BTN_BROWSE, command=self._cls_browse).pack(side='left', padx=(0, 4))
        ttk.Button(top, text=_UI.BTN_RELOAD, command=self._cls_load).pack(side='left')
        self._var_cls_subdirs = tk.BooleanVar(value=self._state.get(_IS.KEY_CLASSIFY_SUBDIRS, True))
        ttk.Checkbutton(top, text=_UI.CHK_SUBDIRS, variable=self._var_cls_subdirs,
                        command=self._cls_load).pack(side='left', padx=(8, 0))

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
                          values=self._cls_filter_values())
        cb.pack(side='left', padx=(4, 12))
        cb.bind('<<ComboboxSelected>>', lambda _e: self._cls_render())
        self._cb_cls_filter = cb
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
        self._lbl_cls_status = ttk.Label(lf, text='', foreground='gray')     # the run's progress
        self._lbl_cls_status.pack(anchor='w', pady=(6, 0))
        self._pb_cls = ttk.Progressbar(lf, mode='determinate')
        self._pb_cls.pack(fill='x', pady=(2, 0))

        opts = ttk.Frame(lf)
        opts.pack(fill='x', pady=(8, 0))
        self._var_cls_model = tk.BooleanVar(value=self._state.get(_IS.KEY_USE_MODEL, True))
        self._var_cls_ocr = tk.BooleanVar(value=self._state.get(_IS.KEY_USE_OCR, True))
        self._var_cls_people = tk.BooleanVar(value=self._state.get(_IS.KEY_FIND_PEOPLE, True))
        self._var_cls_nocache = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text=_UI.CHK_USE_MODEL, variable=self._var_cls_model).pack(side='left')
        ttk.Checkbutton(opts, text=_UI.CHK_USE_OCR, variable=self._var_cls_ocr).pack(side='left', padx=8)
        ttk.Checkbutton(opts, text=_UI.CHK_FIND_PEOPLE, variable=self._var_cls_people).pack(side='left', padx=(0, 8))
        ttk.Checkbutton(opts, text=_UI.CHK_RECLASSIFY, variable=self._var_cls_nocache).pack(side='left')

        st = ttk.Frame(lf)
        st.pack(fill='x', pady=(6, 0))
        self._lbl_cls_model = ttk.Label(st, foreground='gray')
        self._lbl_cls_model.pack(side='left')
        self._btn_cls_download = ttk.Button(st, text=_UI.BTN_DOWNLOAD_MODEL, command=self._cls_download)
        self._btn_cls_download.pack(side='right')
        self._lbl_cls_faces = ttk.Label(lf, foreground='gray')
        self._lbl_cls_faces.pack(anchor='w')
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
        ttk.Button(row, text=_UI.BTN_TAG_PEOPLE, command=self._cls_tag_people).pack(side='left', padx=(12, 0))
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
        path_dir = cm.clean_path(self._var_cls_dir.get())
        if not path_dir:
            return
        self._var_cls_dir.set(path_dir)
        if not os.path.isdir(path_dir):
            self._append_log(f'[CLASSIFY] Not a folder: {path_dir}\n')
            return
        subdirs = self._var_cls_subdirs.get()
        self._state[_IS.KEY_CLASSIFY_DIR] = path_dir
        self._state[_IS.KEY_CLASSIFY_SUBDIRS] = subdirs
        self._cls_dir = path_dir
        rows = cl.list_files(path_dir, recursive=subdirs)
        sheets = {path_dir: sh.read_sheet(path_dir)}
        self._cls_rows = {}
        n_sheet = 0
        for i, r in enumerate(rows):
            r['res'] = cl.cached(self._cls_cache, r['path'])
            got = sheets[path_dir].get(r['name'])
            sub = os.path.dirname(r['path'])
            if r['res'] is None and not got and sub != path_dir:     # the subfolder's own sheet
                if sub not in sheets:
                    sheets[sub] = sh.read_sheet(sub)
                got = sheets[sub].get(os.path.basename(r['path']))
            if r['res'] is None and got and got['size'] == r['size']:
                r['res'] = cl.Result(**got['res'])          # classified elsewhere, or cache lost
                cl.remember(self._cls_cache, r['res'])
                n_sheet += 1
            self._cls_rows[str(i)] = r
        for r in rows:                      # names tagged since the run apply at once
            if r['res'] and r['res'].faces:
                r['res'].people = fc.name_faces(r['res'].faces, self._cls_people)
        if n_sheet:
            self._cls_save_cache()
        self._cls_checked = set()
        n_done = sum(1 for r in rows if r['res'])
        kinds = {}
        for r in rows:
            kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
        n_dirs = len({os.path.dirname(r['path']) for r in rows})
        self._append_log(f'[CLASSIFY] {path_dir}: {len(rows)} files '
                         + (f'in {n_dirs} folders ' if n_dirs > 1 else '') +
                         f'({", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))}), '
                         f'{n_done} already classified'
                         + (f' ({n_sheet} from the folder sheets)' if n_sheet else '') + '\n')
        self._cls_render()

    # ── Table ─────────────────────────────────────────────────────────────────

    def _cls_values(self, iid: str) -> tuple:
        r = self._cls_rows[iid]
        res = r['res']
        return (cm.CHK_ON if iid in self._cls_checked else cm.CHK_OFF, cl.fmt_size(r['size']),
                res.cls if res else '', f'{res.conf:.2f}' if res else '', _people_cell(res),
                _one_line(res.text)[:_TEXT_CELL] if res else '', r['name'])

    def _cls_filter_values(self) -> list:
        """The Show filter: the classes, then the people tagged."""
        return [_UI.LBL_ALL_CLASSES] + _C.ALL + [_NOT_DONE, _UI.LBL_UNKNOWN_FACES] + sorted(self._cls_people)

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
            if col == 'people':
                return (not (res and (res.people or res.faces)), _people_cell(res).lower())
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
            if flt == _UI.LBL_UNKNOWN_FACES and not (res and any(not f.get('name') for f in res.faces)):
                continue
            if flt in self._cls_people and not (res and flt in res.people):
                continue
            if flt not in (_UI.LBL_ALL_CLASSES, _NOT_DONE, _UI.LBL_UNKNOWN_FACES) \
                    and flt not in self._cls_people and (not res or res.cls != flt):
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
            if res.faces or res.people:
                info.append(f'{_UI.COL_PEOPLE}: {_people_cell(res)}')
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
        ready, faces = clip_model.model_ready(), fc.model_ready()
        self._lbl_cls_model.configure(text=_UI.LBL_MODEL_ON if ready else _UI.LBL_MODEL_OFF)
        self._lbl_cls_faces.configure(text=_UI.LBL_FACES_ON if faces else _UI.LBL_FACES_OFF)
        self._btn_cls_download.configure(state='disabled' if ready and faces else 'normal')

    def _cls_download(self) -> None:
        self._btn_cls_download.configure(state='disabled')

        def work():
            for mod in (clip_model, fc):
                try:
                    mod.download_model(log=self._log_queue.put)
                except Exception as exc:
                    self._log_queue.put(f'[ERROR] Model download failed: {exc}\n')
            self.after(0, self._cls_model_status)

        self._start_background(work)

    def _cls_status(self, text: str) -> None:
        self._lbl_cls_status.configure(text=text)

    def _cls_status_progress(self) -> None:
        s = self._cls_run_stat
        extra = _UI.STATUS_FROM_CACHE.format(n=s['cache']) if s.get('cache') else ''
        self._cls_status(_UI.STATUS_PROGRESS.format(
            done=s['done'], total=s['total'], pct=100 * s['done'] // max(1, s['total']), extra=extra))

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
        use_faces = self._var_cls_people.get()
        self._state[_IS.KEY_USE_MODEL], self._state[_IS.KEY_USE_OCR] = use_model, use_ocr
        self._state[_IS.KEY_FIND_PEOPLE] = use_faces
        nocache = self._var_cls_nocache.get()
        jobs = [(iid, self._cls_rows[iid]['path']) for iid in iids]
        others = [r['res'] for i, r in self._cls_rows.items() if r['res'] and i not in set(iids)]
        cache = dict(self._cls_cache)
        self._cls_stop.clear()
        self._cls_set_running(True)
        self._pb_cls.configure(maximum=len(jobs), value=0)
        self._cls_run_stat = {'t0': time.time(), 'total': len(jobs), 'done': 0, 'cache': 0}
        self._cls_status(_UI.STATUS_LOADING)
        self._append_log(f'[CLASSIFY] {len(jobs)} file(s), model {"on" if use_model else "off"}, '
                         f'OCR {"on" if use_ocr else "off"}, people {"on" if use_faces else "off"}'
                         f'{", cache ignored" if nocache else ""}\n')

        def work():
            clf = self._cls_classifier(use_model, use_ocr, use_faces)
            done, todo = [], []
            for iid, path in jobs:
                res = None if nocache else cl.cached(cache, path)
                if res and not res.manual and use_model and clf.clip is not None and 'clip' not in res.method:
                    res = None            # made without the model, which is here now
                if res is None:
                    todo.append((iid, clf.classify, path))
                elif clf.faces is not None and res.kind == 'image' and cl.METHOD_FACES not in res.method:
                    todo.append((iid, clf.find_people, res))     # only the face pass is missing
                else:
                    done.append((iid, res))
            self._cls_run_stat['cache'] = len(done)
            self.after(0, lambda n=len(done): self._cls_progress(n))
            with ThreadPoolExecutor(_WORKERS) as ex:
                futs = {ex.submit(fn, arg): iid for iid, fn, arg in todo}
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

    def _cls_classifier(self, use_model: bool, use_ocr: bool, use_faces: bool = False):
        if self._cls_clf and self._cls_clf[:3] == (use_model, use_ocr, use_faces):
            return self._cls_clf[3]
        clf = cl.Classifier(use_model, use_ocr, log=self._log_queue.put, use_faces=use_faces,
                            people=self._cls_people)
        self._cls_clf = (use_model, use_ocr, use_faces, clf)
        return clf

    def _cls_progress(self, n: int) -> None:
        self._pb_cls.configure(value=self._pb_cls['value'] + n)
        self._cls_run_stat['done'] = self._cls_run_stat.get('done', 0) + n
        self._cls_status_progress()

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
        self._cls_save_sheet(log=True)
        counts = {}
        for _i, res in done:
            counts[res.cls] = counts.get(res.cls, 0) + 1
        stopped = ' (stopped)' if self._cls_stop.is_set() else ''
        s = self._cls_run_stat
        self._cls_status((_UI.STATUS_STOPPED if stopped else _UI.STATUS_DONE).format(
            done=len(done), total=s.get('total', len(done)), secs=time.time() - s.get('t0', time.time()),
            extra=_UI.STATUS_SMOOTHED.format(n=n_smooth) if n_smooth else ''))
        self._append_log(f'[CLASSIFY] done{stopped}: {len(done)} file(s) -- '
                         + ', '.join(f'{c} {counts[c]}' for c in _C.ALL if c in counts)
                         + (f'; {n_smooth} photo(s) moved to their event\'s class' if n_smooth else '') + '\n')

    def _cls_save_cache(self) -> None:
        try:
            cl.save_cache(self._cls_cache)
        except OSError as exc:
            self._append_log(f'[ERROR] Cannot save the class cache: {exc}\n')

    def _cls_save_sheet(self, log: bool = False) -> None:
        """The folder's classes and texts into <folder>\\fennec_images\\classification.xlsx."""
        if not self._cls_dir or not os.path.isdir(self._cls_dir):
            return
        try:
            path = sh.write_sheet(self._cls_dir, list(self._cls_rows.values()))
        except Exception as exc:                    # PermissionError when Excel has it open
            self._append_log(f'[ERROR] Cannot write {sh.sheet_path(self._cls_dir)}: {exc}\n')
            return
        if log:
            n = sum(1 for r in self._cls_rows.values() if r['res'])
            self._append_log(f'[CLASSIFY] {n} classified file(s) saved to {path}\n')

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
        """A window with all the text of the file. A text not known to be complete (missing, or
        an old cache entry's 600-char snippet) is read again on a background thread and stored
        back into the cache and the folder sheet."""
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

        if res and res.text_full:
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
            self.after(0, lambda: done(full))

        def done(full: str) -> None:
            show(full or text)
            if res and full.strip() and r.get('res') is res:
                res.text, res.text_full = full[:cl.TEXT_MAX], len(full) <= cl.TEXT_MAX
                cl.remember(self._cls_cache, res)
                self._cls_save_cache()
                self._cls_refresh_row(iid)
                self._cls_save_sheet()

        self._start_background(work)

    # ── People ────────────────────────────────────────────────────────────────

    def _cls_face_finder(self):
        if self._cls_clf and self._cls_clf[3].faces is not None:
            return self._cls_clf[3].faces
        if self._cls_facer is None:
            self._cls_facer = fc.FaceFinder()
        return self._cls_facer

    def _cls_tag_people(self) -> None:
        """A window with the faces of the selected image, a name box under each; Save keeps
        the named faces in people.json and matches every loaded photo against them."""
        sel = self._tv_cls.selection()
        iids = list(sel) or self._cls_targets()
        if not iids:
            messagebox.showinfo(_UI.BTN_TAG_PEOPLE, 'Select an image first.', parent=self)
            return
        r = self._cls_rows[iids[0]]
        res = r['res']
        if r['kind'] != 'image' or not res:
            messagebox.showinfo(_UI.BTN_TAG_PEOPLE, 'Classify the image first.', parent=self)
            return
        if not fc.model_ready():
            messagebox.showinfo(_UI.BTN_TAG_PEOPLE, 'Download the face models first (Download Models).',
                                parent=self)
            return
        iid, path = iids[0], r['path']
        win = tk.Toplevel(self)
        win.title(f'{_UI.TITLE_TAG} -- {r["name"]}')
        win.transient(self)
        ttk.Label(win, text=_UI.LBL_TAG_HINT, foreground='gray', padding=(8, 6, 8, 0)).pack(anchor='w')
        lbl = ttk.Label(win, text=_UI.LBL_TAG_FINDING, padding=(8, 2))
        lbl.pack(anchor='w')
        grid = ttk.Frame(win, padding=8)
        grid.pack(fill='both', expand=True)
        bar = ttk.Frame(win, padding=(8, 0, 8, 8))
        bar.pack(fill='x')
        btn_save = ttk.Button(bar, text=_UI.BTN_SAVE, state='disabled')
        btn_save.pack(side='right')
        ttk.Button(bar, text=_UI.BTN_CLOSE, command=win.destroy).pack(side='right', padx=(0, 6))
        win.bind('<Escape>', lambda _e: win.destroy())
        crops, boxes = [], []           # PhotoImages kept alive; (face, name var) per face

        def build(faces: list) -> None:
            if not win.winfo_exists():
                return
            lbl.configure(text=_UI.LBL_TAG_NONE if not faces else '')
            im = xt.open_image(path)
            names = sorted(self._cls_people)
            for i, f in enumerate(faces):
                x, y, w, h = f['box']
                m = int(_FM.CROP_MARGIN * max(w, h))
                crop = im.crop((max(0, x - m), max(0, y - m), min(im.width, x + w + m), min(im.height, y + h + m)))
                crop.thumbnail((_FM.CROP_PX, _FM.CROP_PX))
                photo = ImageTk.PhotoImage(crop)
                crops.append(photo)
                cell = ttk.Frame(grid, padding=4)
                cell.grid(row=i // 4, column=i % 4, sticky='n')
                ttk.Label(cell, image=photo).pack()
                var = tk.StringVar(value=f.get('name', ''))
                ttk.Combobox(cell, textvariable=var, values=names, width=14).pack(pady=(4, 0))
                ttk.Label(cell, foreground='gray', text=(f'{f["sim"]:.2f}' if f.get('name') else '')).pack()
                boxes.append((f, var))
            btn_save.configure(state='normal' if faces else 'disabled')

        def save() -> None:
            for f, var in boxes:
                name = var.get().strip()
                if name:
                    fc.add_face(self._cls_people, name, f, path)
                elif f.get('name'):
                    fc.forget_face(self._cls_people, path, f['box'])
                f['name'] = name
            try:
                fc.save_people(self._cls_people)
            except OSError as exc:
                self._append_log(f'[ERROR] Cannot save {fc.people_file()}: {exc}\n')
            self._append_log(f'[PEOPLE] {r["name"]}: {len([1 for _f, v in boxes if v.get().strip()])} '
                             f'face(s) named of {len(boxes)}\n')
            win.destroy()
            self._cls_rematch()

        btn_save.configure(command=save)
        if res.faces:
            build(res.faces)
            return

        def work():                     # a result from before the face models: find them now
            try:
                faces = self._cls_face_finder().find(xt.open_image(path))
            except Exception as exc:
                self._log_queue.put(f'[ERROR] Cannot find the faces of {r["name"]}: {exc}\n')
                faces = []
            fc.name_faces(faces, self._cls_people)
            self.after(0, lambda: found(faces))

        def found(faces: list) -> None:
            if r.get('res') is res:
                res.faces, res.people = faces, sorted({f['name'] for f in faces if f['name']})
                if cl.METHOD_FACES not in res.method:
                    res.method += cl.METHOD_FACES
                cl.remember(self._cls_cache, res)
                self._cls_refresh_row(iid)
            build(faces)

        self._start_background(work)

    def _cls_rematch(self) -> None:
        """Every loaded photo's faces against the people tagged (instant: the embeddings are
        in the results); the table, the cache and the folder sheet follow."""
        counts = {}
        for iid, r in self._cls_rows.items():
            res = r['res']
            if res and res.faces:
                res.people = fc.name_faces(res.faces, self._cls_people)
                for n in res.people:
                    counts[n] = counts.get(n, 0) + 1
                cl.remember(self._cls_cache, res)
                self._cls_refresh_row(iid)
        self._cb_cls_filter.configure(values=self._cls_filter_values())
        if self._var_cls_filter.get() not in self._cls_filter_values():
            self._var_cls_filter.set(_UI.LBL_ALL_CLASSES)
        self._cls_save_cache()
        self._cls_save_sheet()
        self._append_log('[PEOPLE] ' + (', '.join(f'{n} in {c} photo(s)' for n, c in sorted(counts.items()))
                                        or 'no one matched') + '\n')

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
        self._cls_save_sheet()
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
        base = self._cls_dir
        if not messagebox.askyesno(_UI.BTN_COPY, f'Copy {len(iids)} file(s) into class folders under\n'
                                   f'{base}\n\nIf a file exists: {policy}', parent=self):
            return
        jobs = [(self._cls_rows[i]['path'], self._cls_rows[i]['name'], self._cls_rows[i]['res'].cls)
                for i in iids]

        def work():
            n_copy = n_skip = 0
            for path, name, cls in jobs:
                try:
                    dst = os.path.join(base, cls, name)      # a subfolder's file keeps its subfolder
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
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


def _people_cell(res) -> str:
    """'Dana, Noam +1' (the names, then the strangers), '2 faces' when no one is known."""
    if not res or not (res.faces or res.people):
        return ''
    unknown = sum(1 for f in res.faces if not f.get('name'))
    if not res.people:
        return _UI.FMT_FACES.format(n=unknown)
    return _SH.PEOPLE_SEP.join(res.people) + (_UI.FMT_FACES_MORE.format(n=unknown) if unknown else '')
