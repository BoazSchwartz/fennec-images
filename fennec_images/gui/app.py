"""ImagesApp -- the Fennec Images desktop app: Classify, Albums, the shared Prompts tab and
General, over AppBaseMixin (the same infrastructure as the Fennec bookkeeping Private app)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from fennec_images import config
from fennec_images.gui.albums_tab import AlbumsTabMixin
from fennec_images.gui.app_base import AppBaseMixin
from fennec_images.gui.classify_tab import ClassifyTabMixin
from fennec_images.gui.general_tab import GeneralTabMixin
from shared.prompts_tab import PromptsTabMixin
from shared.utils import set_app_id

_IC = config.ImagesConfig
_UI = config.UIStrings


class ImagesApp(tk.Tk, AppBaseMixin, ClassifyTabMixin, AlbumsTabMixin, PromptsTabMixin,
                GeneralTabMixin):
    _APP_TITLE = _IC.TITLE
    _APP_STATE_DIR = _IC.STATE_DIR
    _APP_LOG_PREFIX = _IC.LOG_PREFIX
    _APP_DEFAULT_ROOT = ''
    _APP_DOCS_SUBFOLDER = ''
    _APP_DATA_SUBFOLDER = 'app'
    _APP_MAX_RECENT = _IC.MAX_RECENT_PROJECTS
    _APP_ICON_FILE = _IC.ICON_FILE

    def __init__(self) -> None:
        set_app_id(_IC.APP_ID)          # before a window exists, or the icon is ignored
        super().__init__()
        self._base_init()
        self._build()
        self._layout_profile_init()
        self._configure_style()
        self._restore_state()
        self._base_finalize()
        self.after(200, self._refresh_all)

    def _build(self) -> None:
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._tab_classify = ttk.Frame(self._notebook)
        self._tab_albums = ttk.Frame(self._notebook)
        self._tab_prompts = ttk.Frame(self._notebook)
        self._tab_general = ttk.Frame(self._notebook)
        # The work first, then the repo's development log, General always last
        self._notebook.add(self._tab_classify, text=_UI.TAB_CLASSIFY)
        self._notebook.add(self._tab_albums, text=_UI.TAB_ALBUMS)
        self._notebook.add(self._tab_prompts, text=_UI.TAB_PROMPTS)
        self._notebook.add(self._tab_general, text=_UI.TAB_GENERAL)
        self._build_classify_tab()
        self._build_albums_tab()
        self._build_prompts_tab()
        self._build_general_tab()
        self._notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        self._tab_select_hooks[str(self._tab_prompts)] = self._prompts_refresh_if_changed

    def _refresh_all(self) -> None:
        if self._var_cls_dir.get().strip():
            self._cls_load()

    def _save_current_state(self) -> None:
        if hasattr(self, '_var_alb_out'):
            self._alb_remember()
        if hasattr(self, '_var_cls_policy'):
            self._state[config.ImagesState.KEY_POLICY] = self._var_cls_policy.get()
        super()._save_current_state()
