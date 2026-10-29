"""Helpers to synthesize canonical key-event streams the way a HID scanner types."""
from scanwise.capture.keymap import MODIFIERS, PRINTABLE

_SHIFTED = {}
_PLAIN = {}


def _build():
    for code, (lo, hi) in PRINTABLE.items():
        if code.startswith("Numpad") or code == "IntlBackslash":
            continue
        _PLAIN.setdefault(lo, code)
        if hi != lo:
            _SHIFTED.setdefault(hi, code)


class KeySeq:
    """Builds events with a fixed inter-key interval. `browser=True` adds key/mods like a browser would."""

    def __init__(self, step=2.0, browser=False):
        if not _PLAIN:
            _build()
        self.t = 0.0
        self.step = step
        self.browser = browser
        self.events = []
        self.mods = {"shift": False, "ctrl": False, "alt": False, "meta": False}

    def _ev(self, typ, code, key=None):
        ev = {"t": round(self.t, 3), "type": typ, "code": code, "src": "test"}
        if self.browser:
            ev["key"] = key
            ev["mods"] = dict(self.mods)
        self.events.append(ev)
        self.t += self.step / 2

    def press(self, code, key=None):
        self._ev("down", code, key)
        self._ev("up", code, key)
        return self

    def mod_down(self, code):
        name = MODIFIERS[code]
        self.mods[name] = True
        self._ev("down", code, code.replace("Left", "").replace("Right", ""))
        return self

    def mod_up(self, code):
        name = MODIFIERS[code]
        self.mods[name] = False
        self._ev("up", code, code.replace("Left", "").replace("Right", ""))
        return self

    def type(self, text):
        for ch in text:
            if ch in _PLAIN:
                self.press(_PLAIN[ch], ch)
            elif ch in _SHIFTED:
                self.mod_down("ShiftLeft").press(_SHIFTED[ch], ch).mod_up("ShiftLeft")
            else:
                raise ValueError(f"cannot type {ch!r}; use ctrl()/alt()/enter()")
        return self

    def enter(self):
        return self.press("Enter", "Enter")

    def tab(self):
        return self.press("Tab", "Tab")

    def ctrl(self, code, shift=False):
        self.mod_down("ControlLeft")
        if shift:
            self.mod_down("ShiftLeft")
        self.press(code, None)
        if shift:
            self.mod_up("ShiftLeft")
        return self.mod_up("ControlLeft")

    def alt(self, digits):
        self.mod_down("AltLeft")
        for d in digits:
            self.press(f"Numpad{d}", d)
        return self.mod_up("AltLeft")
