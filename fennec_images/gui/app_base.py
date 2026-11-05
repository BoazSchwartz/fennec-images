"""App-agnostic GUI infrastructure, copied from fennec-bookkeeping personal/gui/app_base.py.

AppBaseMixin holds everything that is NOT specific to a tab: theme/style, the log queue +
fan-out, background threads, sash-fraction and column-width persistence, state.json I/O,
project-root derivation, the Screen profiles and restart. The concrete app sets the _APP_*
class attributes.

It derives paths from its own location: the log dir is <its parent's parent>/log
(fennec_images/log) and the restart target is <its dir>/_APP_RUN_SCRIPT.

Tabs decouple from this base by REGISTERING what they own:
  - register_log_widget(text_widget)
  - register_sash(state_key, paned_window, orient, tab_frame, label)
  - register_colwidths(state_key, treeview, label)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import queue
import traceback
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Callable, Optional

from fennec_images import config
from shared import layout_profiles as lprof
from shared.utils import Logger, python_gui_exe, set_window_icon

_LC = config.LayoutConfig
_ST = config.StyleConfig


def _darken(hex_color: str, factor: float = 0.75) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return '#{:02x}{:02x}{:02x}'.format(int(r * factor), int(g * factor), int(b * factor))


def _pw_vert_frac(pw, idx: int = 0):
    try:
        h = pw.winfo_height()
        if h < _LC.SASH_MIN_PX:
            return None
        return pw.sashpos(idx) / h
    except Exception:
        return None


def _pw_horiz_frac(pw, idx: int = 0):
    try:
        w = pw.winfo_width()
        if w < _LC.SASH_MIN_PX:
            return None
        return pw.sashpos(idx) / w
    except Exception:
        return None


def _set_vert_frac(pw, frac: float, idx: int = 0) -> None:
    try:
        h = pw.winfo_height()
        if h >= _LC.SASH_MIN_PX:
            pw.sashpos(idx, int(frac * h))
    except Exception:
        pass


def _set_horiz_frac(pw, frac: float, idx: int = 0) -> None:
    try:
        w = pw.winfo_width()
        if w >= _LC.SASH_MIN_PX:
            pw.sashpos(idx, int(frac * w))
    except Exception:
        pass


def _tv_col_widths_frac(tv) -> dict:
    total_w = tv.winfo_width()
    if total_w < 100:
        total_w = sum(tv.column(c, 'width') for c in tv['columns']) or 1
    return {c: tv.column(c, 'width') / total_w for c in tv['columns']}


def _tv_col_widths_px(tv) -> dict:
    """{column_id: width in pixels} -- what a drag actually changes."""
    return {c: tv.column(c, 'width') for c in tv['columns']}


def _col_heading(tv, col: str) -> str:
    """A column's heading as the log should name it, without its sort arrow."""
    return str(tv.heading(col, 'text')).replace('▲', '').replace('▼', '').strip() or col


def _set_tv_col_widths_frac(tv, widths: dict) -> None:
    total_w = tv.winfo_width()
    if total_w < 100:
        return
    for c, w in widths.items():
        try:
            if isinstance(w, float) and 0 < w <= 1.5:
                new_w = max(_LC.MIN_COL_WIDTH, int(w * total_w))
            else:
                new_w = max(_LC.MIN_COL_WIDTH, int(w))
            tv.column(c, width=new_w)
        except Exception:
            pass


class AppBaseMixin:

    # ── Per-app identity (subclass overrides) ─────────────────────────────────
    _APP_TITLE = 'Fennec App'
    _APP_STATE_DIR = 'fennec_app'
    _APP_LOG_PREFIX = 'fennec'
    _APP_DEFAULT_ROOT = ''
    _APP_DOCS_SUBFOLDER = ''         # '' -> docs_root == project root
    _APP_DATA_SUBFOLDER = 'app'
    _APP_RUN_SCRIPT = 'run.py'
    _APP_MAX_RECENT = 10
    _APP_ICON_FILE = ''              # '' -> the window keeps Tk's own icon
    _SASH_RESTORE_DELAY_MS = 600

    # ── Init ──────────────────────────────────────────────────────────────────

    def _base_init(self) -> None:
        """Set up infrastructure primitives. Call from the app __init__ BEFORE
        _build()/_configure_style()/_restore_state()."""
        self.title(self._APP_TITLE)
        if self._APP_ICON_FILE:
            set_window_icon(self, config.RepoPaths.path_dir_assets / self._APP_ICON_FILE)
        self.minsize(900, 600)

        self._log_queue: queue.Queue = queue.Queue()
        self._active_tasks = 0
        self._task_lock = threading.Lock()
        self._pending_sash: dict = {}

        # Registries populated by tabs during their build.
        self._log_widgets_list: list = []
        self._sash_specs: list[dict] = []
        self._colwidth_specs: list[tuple] = []
        self._colwidth_done: set = set()
        self._colwidth_before: dict = {}   # widths at mouse-press, per table
        self._tab_select_hooks: dict = {}

        self._state_file = (Path(os.environ.get('APPDATA', Path.home()))
                            / self._APP_STATE_DIR / 'state.json')
        # parent.parent is the app's own folder, so the daily log file goes to fennec_images/log/
        self._logger = Logger(Path(__file__).parent.parent / 'log', prefix=self._APP_LOG_PREFIX)
        self._state = self._load_state_file()

        self._var_font_size = tk.StringVar(value=str(self._state.get('font_size', 12)))
        self._var_accent = tk.StringVar(value=self._state.get('accent_color', _ST.DEFAULT_ACCENT))
        self._var_restart_mode = tk.StringVar(
            value=self._state.get('restart_mode', config.AppConfig.DEFAULT_RESTART_MODE))
        self._var_data_dir = tk.StringVar(value=self._state.get('data_dir', ''))
        self._var_docs_root = tk.StringVar(value=self._state.get('docs_root', ''))
        self._var_project_root = tk.StringVar(value=self._state.get('project_root', ''))
        # the General tab is built with this var; the geometry it stands for is applied
        # by _layout_profile_init(), once the tabs have registered what they own
        self._var_layout_profile = tk.StringVar(value=lprof.active_name(self._state))
        self._font_bold = tkfont.Font(family=_ST.FONT_FAMILY, size=12, weight='bold')

    # ── Screen profiles ───────────────────────────────────────────────────────

    def _layout_profile_keys(self) -> list:
        """Every state.json key one screen owns -- everything the app remembers about
        SIZE: the font, the window, each registered sash fraction and each registered
        table's column widths. Registered, so this base still names no tab's widgets."""
        keys = [config.LayoutProfiles.KEY_FONT_SIZE, config.LayoutProfiles.KEY_WINDOW]
        keys += [spec['key'] for spec in self._sash_specs]
        keys += [key for key, _tv, _label in self._colwidth_specs]
        return list(dict.fromkeys(keys))

    def _layout_profile_init(self) -> None:
        """Put the active screen's geometry onto the flat state keys. Call from the app
        __init__ AFTER _build() (the tabs register their sashes and tables there) and
        BEFORE _configure_style(), which is the first thing to read the font size."""
        keys = self._layout_profile_keys()
        name = lprof.normalize(self._state, keys)
        lprof.apply(self._state, keys, name)
        self._var_layout_profile.set(name)
        self._var_font_size.set(str(self._state.get(config.LayoutProfiles.KEY_FONT_SIZE,
                                                    lprof.font_default(name))))

    def _layout_profile_switch(self, _event=None) -> None:
        """The Screen dropdown: keep the arrangement as it is now for the screen being
        left, then wear the chosen one -- font, window size, sashes, column widths."""
        name = self._var_layout_profile.get()
        if name not in lprof.profile_names() or name == lprof.active_name(self._state):
            return
        self._save_current_state()          # captures the live geometry into the old screen
        keys = self._layout_profile_keys()
        lprof.apply(self._state, keys, name)
        size = self._state.get(config.LayoutProfiles.KEY_FONT_SIZE, lprof.font_default(name))
        self._var_font_size.set(str(size))
        self._configure_style(size=int(size), accent=self._state.get('accent_color'))
        self._pending_sash = {spec['key']: self._state[spec['key']]
                              for spec in self._sash_specs if spec['key'] in self._state}
        self._layout_profile_window(name)
        self._colwidth_done.clear()
        self.after(_LC.COL_RESTORE_DELAY_MS, self._restore_table_col_widths)
        self.after(self._SASH_RESTORE_DELAY_MS,
                   lambda: self._apply_sash_fracs_for_tab(self._notebook.select()))
        self._append_log(config.UIStrings.MSG_SCREEN_SWITCHED.format(
            name=name, font=size))

    def _layout_profile_window(self, name: str) -> None:
        """Give the window this screen's size. Only on a SWITCH -- start-up still opens
        zoomed, which is what the app did before this setting existed; a zoomed window
        ignores a geometry, so it is taken out of zoom first."""
        size = str(self._state.get(config.LayoutProfiles.KEY_WINDOW, '')
                   or lprof.window_default(name)).split('+')[0]
        try:
            w, h = (int(x) for x in size.lower().split('x'))
        except ValueError:
            return
        w = min(w, self.winfo_screenwidth())
        h = min(h, self.winfo_screenheight())
        try:
            self.state('normal')
            self.geometry(f'{w}x{h}')
        except tk.TclError:
            pass

    def _base_finalize(self) -> None:
        """Call from the app __init__ AFTER the tabs are built and state restored:
        maximize, wire close/poll, and seed a default project root on first run."""
        try:
            self.state('zoomed')
        except tk.TclError:
            try:
                self.attributes('-zoomed', True)
            except tk.TclError:
                pass
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.after(100, self._poll_log_queue)
        if not self._var_project_root.get().strip() and self._APP_DEFAULT_ROOT:
            self._apply_project_root(self._APP_DEFAULT_ROOT, remember=True)

    # ── Style ─────────────────────────────────────────────────────────────────

    def _configure_style(self, size: Optional[int] = None, accent: Optional[str] = None) -> None:
        size = size if size is not None else self._state.get('font_size', 12)
        accent = accent if accent is not None else self._state.get('accent_color', _ST.DEFAULT_ACCENT)

        for fname in ('TkDefaultFont', 'TkTextFont', 'TkFixedFont', 'TkMenuFont'):
            try:
                tkfont.nametofont(fname).configure(size=size)
            except tk.TclError:
                pass

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Sash', gripcount=0)

        color = _ST.ACCENT_COLORS.get(accent)
        _pressed_relief = [('pressed', '!disabled', 'sunken'), ('!pressed', 'raised')]
        _fam = _ST.FONT_FAMILY
        if color:
            dark = _darken(color)
            style.configure('Action.TButton', font=(_fam, size + 1, 'bold'),
                            background=color, foreground='white',
                            borderwidth=2, relief='raised', padding=(6, 4))
            style.map('Action.TButton',
                      background=[('pressed', '!disabled', dark), ('active', color), ('disabled', '#888')],
                      relief=_pressed_relief)
        else:
            style.configure('Action.TButton', font=(_fam, size + 1, 'bold'),
                            borderwidth=2, relief='raised', padding=(6, 4))
            style.map('Action.TButton', relief=_pressed_relief)

        # The General tab's Application row: three buttons of ONE height -- the app's own
        # text size, the same padding, the same 2px border. Save & Apply and Restart App
        # keep the accent (dotted names off Action.TButton), Open Config Folder stays plain.
        _gen_pad = _ST.GENERAL_BTN_PADDING
        style.configure(_ST.STYLE_SAVE_APPLY, font=(_fam, size, 'bold'), padding=_gen_pad)
        style.configure(_ST.STYLE_RESTART_APP, font=(_fam, size, 'bold'), padding=_gen_pad)
        style.configure(_ST.STYLE_OPEN_CONFIG, font=(_fam, size), padding=_gen_pad,
                        borderwidth=2, relief='raised')

        style.configure('Delete.TButton', font=(_fam, size, 'bold'),
                        background='black', foreground='white',
                        borderwidth=2, relief='raised', padding=(4, 3))
        style.map('Delete.TButton',
                  background=[('pressed', '!disabled', '#333'), ('active', '#222'), ('disabled', '#888')],
                  relief=_pressed_relief)

        row_height = max(20, size * 2 + 6)
        style.configure('Treeview', font=(_fam, size), rowheight=row_height)
        style.configure('Treeview.Heading', font=(_fam, size, 'bold'))
        style.configure('TNotebook.Tab', font=(_fam, size))
        style.configure('TLabel', font=(_fam, size))
        style.configure('TButton', font=(_fam, size), borderwidth=2, relief='raised', padding=(4, 3))
        style.map('TButton', relief=_pressed_relief)
        style.configure('TCombobox', font=(_fam, size))
        style.configure('TSpinbox', font=(_fam, size))
        self._font_bold.configure(size=size, family=_fam)

    # ── Project root / data dir ────────────────────────────────────────────────

    def _data_dir_path(self) -> Optional[Path]:
        val = self._var_data_dir.get().strip()
        if val:
            return Path(val)
        docs = self._state.get('docs_root', '').strip()
        return Path(docs) if docs else None

    def _apply_project_root(self, root: str, remember: bool = True) -> None:
        root = root.strip()
        self._var_project_root.set(root)
        self._state['project_root'] = root
        if not root:
            return
        docs_p = root if not self._APP_DOCS_SUBFOLDER else str(Path(root) / self._APP_DOCS_SUBFOLDER)
        data_p = Path(root) / self._APP_DATA_SUBFOLDER
        self._var_docs_root.set(docs_p)
        self._var_data_dir.set(str(data_p))
        self._state['docs_root'] = docs_p
        self._state['data_dir'] = str(data_p)
        try:
            data_p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if remember:
            recents = [r for r in self._state.get('recent_project_roots', []) if r != root]
            recents.insert(0, root)
            self._state['recent_project_roots'] = recents[:self._APP_MAX_RECENT]

    # ── General-tab actions ────────────────────────────────────────────────────

    def _general_save_apply(self) -> None:
        try:
            size = max(_LC.MIN_FONT_SIZE, min(_LC.MAX_FONT_SIZE,
                       int(float(self._var_font_size.get()))))
        except ValueError:
            size = self._state.get('font_size', 12)
        self._var_font_size.set(str(size))
        self._state['font_size'] = size
        self._state['accent_color'] = self._var_accent.get()
        self._state['restart_mode'] = self._var_restart_mode.get()
        self._state['data_dir'] = self._var_data_dir.get()
        self._state['docs_root'] = self._var_docs_root.get()
        self._state['project_root'] = self._var_project_root.get()
        self._configure_style(size=size, accent=self._state['accent_color'])
        self._save_current_state()
        self._append_log('[SAVE] Settings saved.\n')

    def _general_open_config(self) -> None:
        try:
            if sys.platform == 'win32':
                os.startfile(str(self._state_file))
            else:
                subprocess.Popen(['xdg-open', str(self._state_file)])
        except Exception as exc:
            self._append_log(f'[ERROR] Cannot open config: {exc}\n')

    # ── Registration (called by tabs) ──────────────────────────────────────────

    def register_log_widget(self, widget) -> None:
        self._log_widgets_list.append(widget)

    def register_sash(self, key: str, pw, orient: str, tab_frame,
                      label: Optional[str] = None, idx: int = 0) -> None:
        spec = {'key': key, 'pw': pw, 'orient': orient, 'tab_frame': tab_frame,
                'label': label, 'idx': idx}
        self._sash_specs.append(spec)
        self._pending_sash.setdefault(
            key, self._state.get(key) or config.SashConfig.LOG_FRAC)
        pw.bind('<ButtonRelease-1>', lambda _e, sp=spec: self._capture_sash(sp))

    def register_colwidths(self, key: str, tv, label: Optional[str] = None) -> None:
        """Remember a table's column widths under `key`, and watch it being resized.

        The press/release pair is what makes a column DRAG visible: the press
        snapshots the widths, the release compares them, so the change is logged
        (as a sash drag is) and written into self._state right away -- Save & Apply
        and closing the app then persist it like every other setting."""
        self._colwidth_specs.append((key, tv, label))
        tv.bind('<ButtonPress-1>', lambda _e, k=key, t=tv: self._colwidths_snapshot(k, t),
                add='+')
        tv.bind('<ButtonRelease-1>',
                lambda _e, k=key, t=tv, lb=label: self._capture_colwidths(k, t, lb),
                add='+')

    def _colwidths_snapshot(self, key: str, tv) -> None:
        self._colwidth_before[key] = _tv_col_widths_px(tv)

    def _capture_colwidths(self, key: str, tv, label: Optional[str]) -> None:
        """A finished drag on a column border: log what moved, remember the widths."""
        before = self._colwidth_before.pop(key, None)
        widths = _tv_col_widths_px(tv)
        if before is None or widths == before:
            return
        frac = _tv_col_widths_frac(tv)
        if frac:
            self._state[key] = frac
        if not label:
            return
        moved = ', '.join(f'{_col_heading(tv, c)} {w}px'
                          for c, w in widths.items() if before.get(c) != w)
        if moved:
            self._append_log(f'[COLS] {label}: {moved}\n')

    def _capture_sash(self, spec: dict) -> None:
        fn = _pw_vert_frac if spec['orient'] == 'vert' else _pw_horiz_frac
        frac = fn(spec['pw'], spec['idx'])
        if frac is None or not (0 < frac < 1):
            return
        old = self._pending_sash.get(spec['key'])
        self._pending_sash[spec['key']] = frac
        if spec['label'] and (old is None or abs(old - frac) > 0.005):
            self._append_log(f'[PANE] {spec["label"]}: {frac*100:.0f}% / {(1-frac)*100:.0f}%\n')

    # ── Tab switching ──────────────────────────────────────────────────────────

    def _on_tab_changed(self, event=None) -> None:
        selected = self._notebook.select()
        self.after(50, lambda: self._apply_sash_fracs_for_tab(selected))
        hook = self._tab_select_hooks.get(selected)
        if hook:
            self.after(60, hook)

    def _apply_sash_fracs_for_tab(self, tab_id: str) -> None:
        for spec in self._sash_specs:
            if str(spec['tab_frame']) != tab_id:
                continue
            frac = self._pending_sash.get(spec['key']) or config.SashConfig.LOG_FRAC
            if spec['orient'] == 'vert':
                _set_vert_frac(spec['pw'], frac, spec['idx'])
            else:
                _set_horiz_frac(spec['pw'], frac, spec['idx'])

    # ── Background tasks ────────────────────────────────────────────────────────

    def _start_background(self, fn: Callable) -> None:
        """Run fn() on a daemon thread. An exception escaping fn is LOGGED (with its
        traceback) instead of vanishing: these threads have no console in Silent
        restart mode, so an unhandled error used to kill the task with no trace of
        why -- e.g. a long parse batch that just stopped mid-file."""
        with self._task_lock:
            self._active_tasks += 1

        def _wrapped():
            try:
                fn()
            except Exception as exc:
                trace = traceback.format_exc()
                self.after(0, lambda e=exc, t=trace: self._append_log(
                    f'[ERROR] Background task failed: {type(e).__name__}: {e}\n{t}'))
            finally:
                with self._task_lock:
                    self._active_tasks = max(0, self._active_tasks - 1)

        threading.Thread(target=_wrapped, daemon=True).start()

    # ── Log queue ────────────────────────────────────────────────────────────────

    def _poll_log_queue(self) -> None:
        try:
            while True:
                text = self._log_queue.get_nowait()
                self._append_log(text)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _append_log(self, text: str) -> None:
        self._logger.log(text)
        for widget in self._log_widgets_list:
            try:
                widget.configure(state='normal')
                widget.insert(tk.END, text)
                widget.see(tk.END)
                widget.configure(state='disabled')
            except Exception:
                pass

    # ── State persistence ──────────────────────────────────────────────────────

    def _load_state_file(self) -> dict:
        try:
            if self._state_file.exists():
                return json.loads(self._state_file.read_text(encoding='utf-8'))
        except Exception:
            pass
        return {}

    def _restore_state(self) -> None:
        s = self._state
        if 'font_size' in s:
            self._var_font_size.set(str(s['font_size']))
        if 'accent_color' in s:
            self._var_accent.set(s['accent_color'])
        if 'restart_mode' in s:
            self._var_restart_mode.set(s['restart_mode'])
        if 'data_dir' in s:
            self._var_data_dir.set(s['data_dir'])
        if 'docs_root' in s:
            self._var_docs_root.set(s['docs_root'])
        if s.get('project_root'):
            self._apply_project_root(s['project_root'], remember=False)

        self.after(_LC.COL_RESTORE_DELAY_MS, self._restore_table_col_widths)

        for spec in self._sash_specs:
            self._pending_sash[spec['key']] = s.get(spec['key']) or self._pending_sash.get(spec['key'])

        if 'active_tab' in s:
            try:
                self._notebook.select(s['active_tab'])
            except Exception:
                pass
        self.after(self._SASH_RESTORE_DELAY_MS,
                   lambda: self._apply_sash_fracs_for_tab(self._notebook.select()))

    def _restore_table_col_widths(self) -> None:
        """Restore each tree's saved column widths ONCE, when it first becomes sized.
        A hidden tab's tree stays unsized (width < 100) until visited, so we keep
        polling for the not-yet-restored ones -- but never re-apply to a tree already
        done, otherwise the poll would keep overwriting the user's live drag on the
        visible tab (widths would snap back every 200ms)."""
        s = self._state
        done = self._colwidth_done
        pending = [(k, tv) for k, tv, _lb in self._colwidth_specs
                   if k in s and tv is not None and k not in done]
        if not pending:
            return
        remaining = False
        for key, tv in pending:
            if tv.winfo_width() < 100:
                remaining = True
                continue
            _set_tv_col_widths_frac(tv, s[key])
            done.add(key)
        if remaining:
            self.after(200, self._restore_table_col_widths)

    def _save_current_state(self) -> None:
        s = self._state
        try:
            s['window_geometry'] = self.geometry()
            s['active_tab'] = self._notebook.index(self._notebook.select())
        except Exception:
            pass
        try:
            s['font_size'] = max(_LC.MIN_FONT_SIZE,
                                 min(_LC.MAX_FONT_SIZE, int(float(self._var_font_size.get()))))
        except ValueError:
            pass
        s['accent_color'] = self._var_accent.get()
        s['restart_mode'] = self._var_restart_mode.get()
        s['data_dir'] = self._var_data_dir.get()
        s['docs_root'] = self._var_docs_root.get()
        s['project_root'] = self._var_project_root.get()

        for spec in self._sash_specs:
            fn = _pw_vert_frac if spec['orient'] == 'vert' else _pw_horiz_frac
            live = fn(spec['pw'], spec['idx'])
            if live is not None and 0 < live < 1:
                s[spec['key']] = live
                self._pending_sash[spec['key']] = live
            elif spec['key'] in self._pending_sash:
                s[spec['key']] = self._pending_sash[spec['key']]

        for key, tv, _label in self._colwidth_specs:
            if tv is not None:
                widths = _tv_col_widths_frac(tv)
                if widths:
                    s[key] = widths

        # the geometry just collected belongs to the screen it was arranged on
        lprof.capture(s, self._layout_profile_keys())

        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

    def _do_restart(self) -> None:
        self._state['restart_mode'] = self._var_restart_mode.get()
        self._save_current_state()
        cwd = str(Path(__file__).parents[2])   # repo root, where the shared .venv lives
        mode_name = self._var_restart_mode.get()
        if mode_name not in config.AppConfig.RESTART_MODES:
            mode_name = config.AppConfig.DEFAULT_RESTART_MODE
        exe, out = sys.executable, None
        kwargs = {}
        if sys.platform == 'win32':
            flags = 0
            for name in config.AppConfig.RESTART_MODES[mode_name]:
                flags |= getattr(subprocess, name)
            kwargs['creationflags'] = flags
            if mode_name != config.AppConfig.RESTART_MODE_CONSOLE:
                # Detached is not silent by itself -- a console python.exe still opens its
                # own black box -- so the windowless interpreter is what starts the app,
                # with its output kept in the same launch log the .vbs launcher writes.
                exe = python_gui_exe()
                out = self._launch_log_handle()
                if out is not None:
                    kwargs['stdout'] = out
                    kwargs['stderr'] = subprocess.STDOUT
        subprocess.Popen([exe, str(Path(__file__).parent / self._APP_RUN_SCRIPT)], cwd=cwd, **kwargs)
        if out is not None:
            out.close()   # Popen kept its own duplicate of the handle
        self.after(300, self.destroy)

    def _launch_log_handle(self):
        """The launch log opened for append, or None if it cannot be written -- a restart
        with no console must still leave a start-up traceback on disk."""
        try:
            path_dir = config.RepoPaths.path_dir_log
            path_dir.mkdir(parents=True, exist_ok=True)
            return open(path_dir / config.ImagesConfig.LAUNCH_LOG_FILE, 'a', encoding='utf-8')
        except OSError as exc:
            self._append_log(f'[ERROR] Cannot open the launch log: {exc}\n')
            return None

    def _on_close(self) -> None:
        self._save_current_state()
        self._logger.close()
        self.destroy()
