"""General tab -- same shape as every other Fennec project (copied from fennec-bookkeeping
personal/gui/general_tab.py): an Application section (Save & Apply / Restart / Open Config,
font size, accent, restart mode, screen) and a Project section (project root Browse…/Recent).
Project-root switches go through a restart."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from fennec_images import config
from shared import layout_profiles as lprof

_UI = config.UIStrings
_ST = config.StyleConfig
_SC = config.SashConfig


class GeneralTabMixin:

    def _build_general_tab(self) -> None:
        # Content over log, like every other tab of the app
        self._pw_general_vert = ttk.PanedWindow(self._tab_general, orient='vertical')
        self._pw_general_vert.pack(fill='both', expand=True, padx=6, pady=(2, 6))

        settings_frame = ttk.Frame(self._pw_general_vert)
        self._pw_general_vert.add(settings_frame, weight=5)

        outer = ttk.Frame(settings_frame, padding=24)
        outer.pack(fill='x', anchor='n')

        app_lf = ttk.LabelFrame(outer, text=_UI.SEC_APPLICATION, padding=12)
        app_lf.pack(fill='x', anchor='n')

        row1 = ttk.Frame(app_lf)
        row1.pack(fill='x', anchor='w', pady=(0, 10))
        ttk.Button(row1, text=_UI.BTN_SAVE_APPLY, style=_ST.STYLE_SAVE_APPLY,
                   command=self._general_save_apply).pack(side='left', padx=(0, 8))
        ttk.Button(row1, text=_UI.BTN_RESTART_APP, style=_ST.STYLE_RESTART_APP,
                   command=self._do_restart).pack(side='left', padx=(0, 8))
        ttk.Button(row1, text=_UI.BTN_OPEN_CONFIG, style=_ST.STYLE_OPEN_CONFIG,
                   command=self._general_open_config).pack(side='left')

        row2 = ttk.Frame(app_lf)
        row2.pack(fill='x', anchor='w')
        ttk.Label(row2, text=_UI.LBL_FONT_SIZE).pack(side='left')
        ttk.Spinbox(row2, from_=config.LayoutConfig.MIN_FONT_SIZE, to=config.LayoutConfig.MAX_FONT_SIZE,
                    increment=1, textvariable=self._var_font_size, width=5).pack(side='left', padx=(4, 16))
        ttk.Label(row2, text=_UI.LBL_ACCENT).pack(side='left')
        ttk.Combobox(row2, textvariable=self._var_accent,
                     values=list(_ST.ACCENT_COLORS.keys()),
                     state='readonly', width=10).pack(side='left', padx=(4, 16))
        ttk.Label(row2, text=_UI.LBL_RESTART_MODE).pack(side='left')
        ttk.Combobox(row2, textvariable=self._var_restart_mode,
                     values=list(config.AppConfig.RESTART_MODES.keys()),
                     state='readonly', width=14).pack(side='left', padx=(4, 16))

        # Which screen the app is arranged for: each choice keeps its own font size,
        # window size, sash positions and column widths (app_base.py, Screen profiles)
        ttk.Label(row2, text=_UI.LBL_SCREEN).pack(side='left')
        cb_screen = ttk.Combobox(row2, textvariable=self._var_layout_profile,
                                 values=lprof.profile_names(), state='readonly', width=13)
        cb_screen.pack(side='left', padx=(4, 0))
        cb_screen.bind('<<ComboboxSelected>>', self._layout_profile_switch)

        proj_lf = ttk.LabelFrame(outer, text=_UI.SEC_PROJECT, padding=12)
        proj_lf.pack(fill='x', anchor='n', pady=(12, 0))
        proj_lf.columnconfigure(1, weight=1)
        ttk.Label(proj_lf, text=_UI.LBL_PROJECT_ROOT).grid(row=0, column=0, sticky='w', padx=(0, 6))
        ttk.Entry(proj_lf, textvariable=self._var_project_root, state='readonly').grid(
            row=0, column=1, sticky='ew', padx=(0, 4))
        ttk.Button(proj_lf, text='Browse…', command=self._project_root_browse).grid(row=0, column=2)

        ttk.Label(proj_lf, text=_UI.LBL_RECENT).grid(row=1, column=0, sticky='w', padx=(0, 6), pady=(6, 0))
        self._var_recent_project = tk.StringVar()
        self._cb_recent_projects = ttk.Combobox(
            proj_lf, textvariable=self._var_recent_project, state='readonly',
            values=self._state.get('recent_project_roots', []))
        self._cb_recent_projects.grid(row=1, column=1, sticky='ew', pady=(6, 0))
        self._cb_recent_projects.bind('<<ComboboxSelected>>', self._project_root_pick_recent)

        ttk.Label(proj_lf,
                  text='The project root holds the app data (<root>\\app) and is where the Classify and '
                       'Albums tabs start browsing.',
                  foreground='gray').grid(row=2, column=0, columnspan=3, sticky='w', pady=(4, 0))

        self._build_general_log()

    def _build_general_log(self) -> None:
        log_frame = ttk.Frame(self._pw_general_vert)
        self._pw_general_vert.add(log_frame, weight=1)

        hdr = ttk.Frame(log_frame)
        hdr.pack(fill='x', pady=(2, 0))
        ttk.Label(hdr, text=_UI.HDR_LOG,
                  font=(_ST.FONT_FAMILY, 10, 'bold')).pack(side='left', padx=6)
        txt = tk.Text(log_frame, wrap='word', state='disabled',
                      background=_ST.LOG_BG, foreground=_ST.LOG_FG,
                      font='TkFixedFont', relief='flat', borderwidth=0)
        ttk.Button(hdr, text='Clear',
                   command=lambda: self._clear_general_log()).pack(side='right', padx=6)
        log_vsb = ttk.Scrollbar(log_frame, orient='vertical', command=txt.yview)
        txt.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side='right', fill='y')
        txt.pack(fill='both', expand=True, padx=(6, 0), pady=(2, 4))
        self._txt_general_log = txt

        self.register_log_widget(txt)
        self.register_sash(_SC.KEY_GENERAL_LOG, self._pw_general_vert, 'vert',
                           self._tab_general, label=_UI.TAB_GENERAL.strip())

    def _clear_general_log(self) -> None:
        self._txt_general_log.configure(state='normal')
        self._txt_general_log.delete('1.0', tk.END)
        self._txt_general_log.configure(state='disabled')

    def _project_root_browse(self) -> None:
        path = filedialog.askdirectory(title='Select project root folder', parent=self)
        if path:
            self._project_root_switch(path)

    def _project_root_pick_recent(self, event=None) -> None:
        path = self._var_recent_project.get()
        if path:
            self._project_root_switch(path)

    def _project_root_switch(self, path: str) -> None:
        if not path or path == self._var_project_root.get():
            return
        if not messagebox.askyesno('Switch Project', f'Restart now to load project:\n{path}?', parent=self):
            return
        self._apply_project_root(path)
        self._cb_recent_projects.configure(values=self._state.get('recent_project_roots', []))
        self._save_current_state()
        self._do_restart()
