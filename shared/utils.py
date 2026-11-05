from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from shared.config import AppConfig


def date_in_range(value: str, date_from: str, date_to: str) -> bool:
    """Is an ISO 'YYYY-MM-DD' cell inside the From/To range a tab is filtered by?

    Both bounds are inclusive and either may be empty (no bound on that side). The
    dates are ISO, so a plain string compare orders them. A row with no date is OUT
    as soon as a bound is set: it cannot be shown to be in the range being worked."""
    date_from, date_to = (date_from or '').strip(), (date_to or '').strip()
    if not date_from and not date_to:
        return True
    value = str(value or '').strip()
    if not value:
        return False
    if date_from and value < date_from:
        return False
    if date_to and value > date_to:
        return False
    return True


def _to_float(v) -> float:
    try:
        return float(v) if v not in (None, '') else 0.0
    except (ValueError, TypeError):
        return 0.0


def assign_id_nums(records, field: str, width: int) -> bool:
    """Give every record a short sequential id ('000013') in `field`, continuing from
    the highest one already used.

    Idempotent, and numbers are never reused: an item the user has referred to by its
    number keeps it for good, even after the rows around it are deleted. `records` is
    any iterable of dicts (a list, or a dict's .values()). Returns True if anything was
    filled, so the caller can re-save."""
    records = list(records)
    used = []
    for rec in records:
        try:
            used.append(int(str(rec.get(field, '') or '').strip() or 0))
        except ValueError:
            used.append(0)
    nxt = max(used, default=0) + 1
    changed = False
    for rec in records:
        if not str(rec.get(field, '') or '').strip():
            rec[field] = f'{nxt:0{width}d}'
            nxt += 1
            changed = True
    return changed


class Logger:

    def __init__(self, log_dir: Path | str, prefix: str = 'fennec') -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._log_dir / f"{prefix}_{datetime.now().strftime('%Y-%m-%d')}.log"
        self._file = open(log_file, 'a', encoding='utf-8')

    def log(self, text: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        self._file.write(f'{ts}  {text.rstrip(chr(10))}\n')
        self._file.flush()

    def close(self) -> None:
        try:
            self._file.close()
        except Exception:
            pass


def python_gui_exe() -> str:
    """The WINDOWLESS interpreter beside the running one (pythonw.exe), for spawning
    the app without a black console box.

    DETACHED_PROCESS is not enough on its own: a detached python.exe still opens a
    console window of its own (measured -- GetConsoleWindow() comes back non-zero and
    visible), which is what a silent restart used to flash up. pythonw.exe is
    GUI-subsystem, so it can never have one. Falls back to the running interpreter when
    it is not there (a non-Windows or embedded install).
    """
    exe = Path(sys.executable)
    gui = exe.with_name(AppConfig.PYTHON_GUI_EXE)
    return str(gui) if gui.is_file() else sys.executable


def set_app_id(app_id: str) -> None:
    """Take the taskbar button back from python.exe, so the window wears our own
    icon. Must run BEFORE any window exists, or Windows ignores it."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError, ImportError):
        pass    # not Windows, or an id it will not take: the window still gets its icon


def set_window_icon(window, path_file_icon) -> None:
    """Give a window its .ico: the title bar (top left), every Toplevel it raises,
    and the taskbar button.

    iconbitmap alone leaves the taskbar building its button from whichever large
    entry Tk picked and rescaling it to 24 px, which softens the letter; loading
    the 24 px and 16 px entries the .ico already carries into the big/small slots
    makes both a straight copy. Has to run before the mainloop -- the taskbar keeps
    the bitmap it built when the button first appeared.

    Never fatal: a missing icon file just leaves the window with Tk's own.
    """
    path_file_icon = Path(path_file_icon)
    if not path_file_icon.is_file():
        return
    icon = str(path_file_icon)
    try:
        # default= hands the same icon to every Toplevel raised later as well
        window.iconbitmap(icon, default=icon)
    except Exception:
        pass
    if os.name != 'nt':
        return
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.LoadImageW.restype = ctypes.c_void_p
        u32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u32.SendMessageW.restype = ctypes.c_void_p
        u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_void_p]
        u32.GetParent.restype = ctypes.c_void_p
        u32.GetParent.argtypes = [ctypes.c_void_p]
        window.update_idletasks()
        hwnd = u32.GetParent(window.winfo_id()) or window.winfo_id()
        kept = []
        for slot, side in ((1, 24), (0, 16)):        # ICON_BIG, ICON_SMALL
            handle = u32.LoadImageW(None, icon, 1, side, side, 0x0010)   # LR_LOADFROMFILE
            if handle:
                u32.SendMessageW(hwnd, 0x0080, ctypes.c_void_p(slot),
                                 ctypes.c_void_p(handle))
                kept.append(handle)
        window._window_icons = kept      # the handles have to outlive this call
    except Exception:
        pass
