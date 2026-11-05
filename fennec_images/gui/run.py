import sys
from pathlib import Path

# parents[2] is the REPO root (fennec_images/gui/run.py -> gui -> fennec_images -> repo).
# It is what must be on sys.path so `fennec_images.*` and `shared.*` import, and the single
# shared .venv lives there too.
_root = Path(__file__).parents[2]
_venv_lib = _root / '.venv' / 'Lib' / 'site-packages'
if _venv_lib.exists() and str(_venv_lib) not in sys.path:
    sys.path.insert(0, str(_venv_lib))
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fennec_images.gui.app import ImagesApp

if __name__ == '__main__':
    app = ImagesApp()
    app.mainloop()
