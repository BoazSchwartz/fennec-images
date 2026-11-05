"""The General tab's Screen setting, as pure state.json logic -- no tkinter.

Both apps remember their geometry as FLAT keys in state.json (font_size, every
*_frac sash fraction, every *_col_widths dict). A profile is a copy of exactly those
keys kept under config.LayoutProfiles.KEY_STATE, one per screen, and this module is
the two moves between the two shapes:

    capture(state, keys, name)   the flat keys as they are now, into that profile
    apply(state, keys, name)     that profile back onto the flat keys

so nothing else in either app has to know a profile exists: it goes on reading and
writing the same flat keys it always did. Which keys those are is the app's answer
(it knows its own tables and sashes), and it is passed in.

A key the chosen profile has no value for is REMOVED from the flat state rather than
left as the other profile's: a screen that was never shaped starts from the app's own
defaults and is shaped by dragging, which is all it takes to define one.
"""
from __future__ import annotations

from shared.config import LayoutProfiles as _LP


def profile_names() -> list:
    return list(_LP.NAMES)


def active_name(state: dict) -> str:
    name = str(state.get(_LP.KEY_ACTIVE, '') or '')
    return name if name in _LP.NAMES else _LP.DEFAULT


def font_default(name: str) -> int:
    return int(_LP.FONT_DEFAULT.get(name, _LP.FONT_DEFAULT[_LP.DEFAULT]))


def window_default(name: str) -> str:
    return _LP.WINDOW_DEFAULT.get(name, _LP.WINDOW_DEFAULT[_LP.DEFAULT])


def _profiles(state: dict) -> dict:
    saved = state.get(_LP.KEY_STATE)
    if not isinstance(saved, dict):
        saved = {}
        state[_LP.KEY_STATE] = saved
    for name in list(saved):
        if name not in _LP.NAMES or not isinstance(saved[name], dict):
            saved.pop(name)          # a renamed profile cannot resurrect stale geometry
    return saved


def normalize(state: dict, keys) -> str:
    """Make sure the state holds profiles and say which one is active.

    A state written BEFORE the Screen setting existed has its geometry in the flat keys
    only; that arrangement becomes the active profile, so an app upgraded into this
    opens exactly as it was left."""
    profiles = _profiles(state)
    name = active_name(state)
    state[_LP.KEY_ACTIVE] = name
    if name not in profiles:
        profiles[name] = {k: state[k] for k in keys if k in state}
    return name


def capture(state: dict, keys, name: str = '') -> None:
    """The flat geometry keys as they stand now, into the named (default: active) profile."""
    profiles = _profiles(state)
    name = name if name in _LP.NAMES else active_name(state)
    profiles[name] = {k: state[k] for k in keys if k in state}


def apply(state: dict, keys, name: str) -> dict:
    """Put the named profile onto the flat keys and make it the active one.

    Returns the profile applied. Font size and window size are filled from the screen's
    own defaults when the profile has none, since those two decide how the app OPENS and
    there is nothing to fall back on."""
    profiles = _profiles(state)
    name = name if name in _LP.NAMES else _LP.DEFAULT
    geom = profiles.get(name) or {}
    for key in keys:
        if key in geom:
            state[key] = geom[key]
        else:
            state.pop(key, None)
    state.setdefault(_LP.KEY_FONT_SIZE, font_default(name))
    state.setdefault(_LP.KEY_WINDOW, window_default(name))
    state[_LP.KEY_ACTIVE] = name
    return geom
