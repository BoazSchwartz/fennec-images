"""The OVERRIDE POLICY of CLAUDE_GENERAL.md -- what a local write does when its target exists.
Every file write of the app that may meet an existing file goes through prepare()."""
from __future__ import annotations

import os
from datetime import datetime

from fennec_images.config import OverridePolicy as _P


def bak_name(path: str) -> str:
    stem, ext = os.path.splitext(path)
    return f'{stem}_bak_{datetime.now().strftime("%Y%m%d_%H%M%S")}{ext}'


def prepare(path_dst: str, policy: str) -> bool:
    """Make way for a write to path_dst under the policy. False = do not write (Skip)."""
    if not os.path.exists(path_dst):
        return True
    if policy == _P.OVERRIDE:
        return True
    if policy == _P.BAK:
        os.replace(path_dst, bak_name(path_dst))
        return True
    return False
