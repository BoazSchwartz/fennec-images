GENERAL CONVENTIONS
-------------------
General rules that apply to all projects by this author.
Project-specific rules live in CLAUDE.md alongside the codebase.

CORE RULES
----------
- Keep code compact and practical
- No long comments or long docstrings
- Prefer short one-line comments only on important logic lines
- Do not use the characters "->" in strings or log messages -- they crash certain display contexts
- Do not add decorative comment separators
- Variable naming style:
  - signal_inp, signal_out
  - table_inp, table_error
  - path_dir_inp, path_dir_out
  - vol_inp, vol_out
- Do not change existing code unless explicitly asked
- Keep function signatures stable unless explicitly asked
- Reuse existing project structure and conventions

CODING STYLE
------------
- Prefer clear helper functions over large monolithic functions
- Keep helpers local to the file when they are specific to it
- Avoid unnecessary abstractions
- Avoid adding dependencies unless clearly justified
- Print concise progress and useful numbers
- Return simple outputs, usually True/False for run success when appropriate

MAGIC STRINGS POLICY
--------------------
Any string used as a cross-file identifier (key names, file name bases, step names,
directory names, column headers referenced in more than one file) must be defined as a named
constant or class attribute in a central config module.
Never write a string literal that is part of a cross-file protocol more than once.
Reference it by name everywhere: Config.KEY_NAME, not 'key_name'.
UI display strings (labels, headings) belong in a dedicated strings class, not hardcoded in UI files.
See CLAUDE.md for the project-specific config classes.

OVERRIDE POLICY
---------------
File conflict resolution must use a centralized policy module, not custom inline logic.
Three standard policies: SKIP (do not write if destination exists),
OVERRIDE (replace existing), BAK (rename existing to name_bak_TIMESTAMP before writing).
Apply the policy before any local file write where conflicts may occur.
For remote files use a dedicated bak-name helper rather than inline timestamp logic.
The policy choice should always be surfaced to the user before any operation runs.
See CLAUDE.md for the project-specific implementation class.

GUI TERMINOLOGY
----------------
Quick reference for GUI vocabulary used throughout this document.
- Widget: any single GUI element (a button, label, entry, etc.)
- Frame: a plain container widget with no visual decoration, used to group/layout other widgets
- LabelFrame: a bordered frame with a title, used to visually group related controls
- Notebook: the tabbed container widget; each page inside it is a Tab
- PanedWindow: a container split into two or more resizable panes
- Sash: the thin draggable divider between two adjacent panes in a PanedWindow; dragging it
  grows the pane on one side and shrinks the pane on the other by the same amount
- Scrollbar: the widget for scrolling a list/table; its draggable part is the thumb (or
  slider), the channel it moves in is the track
- Treeview: the table/tree widget used for tabular data (also used here for flat tables,
  not just trees)
- Column heading: the label at the top of one Treeview column; the full top row across all
  columns is the header row
- Column border: the vertical line between two columns; dragging it is column resizing,
  which changes that column's width
- Combobox: a dropdown selector (readonly = pick from list only, editable = can also type
  a value)
- Spinbox: a numeric entry field with small up/down arrows to step the value
- Anchor: how content aligns within its allotted space (e.g. anchor='w' = left-aligned,
  'e' = right-aligned, 'center' = centered)
- Geometry manager: the layout system that places widgets on screen; this codebase uses
  pack (stack widgets edge-to-edge along one side) and grid (row/column layout)
- Mixin class: a class that adds one tab's functionality (its _build_*_tab method and
  handlers) into the main app window class via multiple inheritance

GUI LAYOUT CONVENTIONS
----------------------
Each tab is implemented as a mixin class with a _build_*_tab() method
and _append_*_log() / _clear_*_log() helpers. The mixin is inherited by the main window;
its methods share self with the main window class.

Standard tab layout:
- Outer vertical PanedWindow: top content area (weight=3) + bottom log pane (weight=1)
- Top content uses a horizontal PanedWindow with 2-4 vertical panes
- Rightmost pane holds action buttons and a policy selector
- Bottom log pane has a header row with title and Clear button, then a fixed-font Text widget
- Log widgets guard against early calls with: if not hasattr(self, '_txt_*_log'): return

Treeview conventions:
- All columns (headings and cell content) are left-aligned: anchor='w'
- Exactly one column must carry stretch=True; it must be the last (rightmost) column.
  All other columns use stretch=False with an explicit width.
  Never place stretch=True on a non-last column: the stretch column snaps back when
  dragged directly, and columns to its right appear to move the wrong border instead.
  The primary content column (name, path, filename) should be placed last so it fills
  remaining space naturally.
- Scrollbars: vertical always present, horizontal added when content may overflow

Label conventions:
- Do not use ":" at the end of labels or field titles (e.g. "SSH Key", not "SSH Key:")
- The adjacent input widget makes the purpose clear; a colon is redundant

Pane and widget conventions:
- Use ttk.LabelFrame to group related content within a pane
- Navigation entries (path selector, prefix display) sit above the content list in each pane
- Metadata sub-pane sits below the file list inside the same LabelFrame, using a nested
  vertical PanedWindow (list weight=3, metadata weight=1)
- Background operations go through a _start_background() helper for stop-button support
- GUI updates from background threads use self.after(0, lambda: ...) to stay on the main thread
- State (last-used dirs, selections) is stored in self._state dict and auto-saved on close

tk.PanedWindow sash API (IMPORTANT -- avoid sashpos):
- All paned windows in these projects use tk.PanedWindow (not ttk.Panedwindow).
- tk.PanedWindow does NOT have a sashpos() method. Calling pw.sashpos() falls through
  __getattr__ to a Tcl call that raises TclError. If caught silently (except Exception),
  reads always return None and writes silently do nothing -- a hard-to-diagnose failure.
- Use the correct Python methods:
    Read sash position:  x, y = pw.sash_coord(index)
      vertical PanedWindow:   use y (sash moves up/down)
      horizontal PanedWindow: use x (sash moves left/right)
    Write sash position: pw.sash_place(index, x, y)
      vertical PanedWindow:   pw.sash_place(index, 0, pixel_y)
      horizontal PanedWindow: pw.sash_place(index, pixel_x, 0)
- To save as a fraction: frac = y / pw.winfo_height()  (or x / pw.winfo_width())
- To restore: pw.sash_place(0, 0, int(frac * pw.winfo_height()))
- Never write generic except Exception: pass around sash calls -- it hides TclError silently.

MD FILES CONVENTIONS
--------------------
- No markdown formatting (no **, *, backtick, #, etc.)
- Section headers in CAPS
- Underline headers with ---------------
- No long blank lines between sections
