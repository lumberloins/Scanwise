"""
HID keyboard-wedge decoder.

Turns canonical key events (see BUILD_PLAN.md section 3) into *units*. A unit
is either a character the scanner injected (kind "char") or a non-character
key such as F5 or PageDown (kind "token"). Each unit records *how* it was
produced (`via`), which keys made it, and its timing.

via values:
  key           printable key, optionally with Shift
  enter_key     Enter / NumpadEnter (CR)
  named_key     Tab, Backspace, Escape, Delete
  ctrl          Ctrl+key control-character emulation (e.g. Ctrl+] = GS)
  alt_numpad    Alt held + numpad digits (e.g. Alt+0029 = GS)
  function_key  F-keys, arrows, paging keys (no character)
  combo         other modifier combinations with no character meaning
  unknown       key code not in the US table
"""
from scanwise.capture.keymap import (
    CTRL_SYMBOLS, FUNCTION_KEYS, MODIFIERS, NAMED_KEYS, NUMPAD_DIGITS, PRINTABLE,
)

CONTROL_VIA = ("enter_key", "named_key", "ctrl", "alt_numpad")


def _alt_numpad_char(digits):
    """Windows Alt-code semantics: leading 0 = Windows-1252, otherwise CP437 (OEM)."""
    n = int(digits) % 256
    codepage = "cp1252" if digits.startswith("0") and len(digits) > 1 else "cp437"
    if n < 0x80:
        return chr(n), codepage
    try:
        return bytes([n]).decode(codepage), codepage
    except UnicodeDecodeError:
        return chr(n), codepage


def _combo_name(mods, code):
    parts = [m.capitalize() for m in ("ctrl", "alt", "shift", "meta") if mods.get(m)]
    return "+".join(parts + [code])


class _Decoder:
    def __init__(self):
        self.mods = {"shift": False, "ctrl": False, "alt": False, "meta": False}
        self.units = []
        self.alt = None          # pending Alt+numpad sequence
        self.open = {}           # code -> unit index awaiting key-up (for dwell)
        self.unknown = []
        self.notes = []

    def emit(self, kind, idx, ev, via, combo, ch=None, token=None, **extra):
        unit = {
            "index": len(self.units),
            "kind": kind,
            "char": ch,
            "code_point": ord(ch) if ch is not None else None,
            "token": token,
            "via": via,
            "keys": combo,
            "event_indices": [idx] if isinstance(idx, int) else list(idx),
            "t": ev.get("t", 0.0),
            "dwell_ms": None,
            "repeat": bool(ev.get("repeat")),
            "host_key": ev.get("key"),
            "layout_mismatch": False,
            "caps_lock_suspected": False,
        }
        unit.update(extra)
        self.units.append(unit)
        return unit

    def flush_alt(self, ev_idx=None, incomplete=False):
        seq, self.alt = self.alt, None
        if not seq or not seq["digits"]:
            return
        ch, codepage = _alt_numpad_char(seq["digits"])
        idxs = seq["events"] + ([ev_idx] if ev_idx is not None else [])
        u = self.emit("char", idxs, {"t": seq["t"]}, "alt_numpad", f"Alt+{seq['digits']}",
                      ch=ch, alt_code=seq["digits"], codepage=codepage)
        if incomplete:
            u["incomplete"] = True
            self.notes.append(f"Alt+{seq['digits']} never saw Alt released (stream ended mid-sequence).")

    def down(self, i, ev):
        code = ev.get("code") or ""
        if ev.get("mods"):
            for k in self.mods:
                self.mods[k] = bool(ev["mods"].get(k, False))

        if code in MODIFIERS:
            self.mods[MODIFIERS[code]] = True
            if MODIFIERS[code] == "alt" and self.alt is None:
                self.alt = {"digits": "", "events": [i], "t": ev.get("t", 0.0)}
            return

        m = self.mods
        # Alt + numpad digit: accumulate, commit on Alt release.
        if m["alt"] and not m["ctrl"] and code in NUMPAD_DIGITS:
            if self.alt is None:
                self.alt = {"digits": "", "events": [], "t": ev.get("t", 0.0)}
            if not self.alt["digits"]:
                self.alt["t"] = ev.get("t", 0.0)
            self.alt["digits"] += NUMPAD_DIGITS[code]
            self.alt["events"].append(i)
            return
        if self.alt is not None and self.alt["digits"]:
            # A non-numpad key interrupted the Alt sequence; commit what we have.
            self.flush_alt()

        unit = None
        if m["ctrl"] and not m["alt"] and not m["meta"]:
            letter = code[3:] if code.startswith("Key") and len(code) == 4 else None
            if letter:
                unit = self.emit("char", i, ev, "ctrl", _combo_name(m, code), ch=chr(ord(letter) - 64))
            elif (code, m["shift"]) in CTRL_SYMBOLS:
                unit = self.emit("char", i, ev, "ctrl", _combo_name(m, code), ch=chr(CTRL_SYMBOLS[(code, m["shift"])]))
            elif code in NAMED_KEYS:
                unit = self.emit("char", i, ev, "enter_key" if NAMED_KEYS[code] == 0x0D else "named_key",
                                 _combo_name(m, code), ch=chr(NAMED_KEYS[code]))
            else:
                unit = self.emit("token", i, ev, "combo", _combo_name(m, code), token=_combo_name(m, code))
        elif code in NAMED_KEYS:
            via = "enter_key" if NAMED_KEYS[code] == 0x0D else "named_key"
            unit = self.emit("char", i, ev, via, _combo_name(m, code), ch=chr(NAMED_KEYS[code]))
        elif m["alt"] or m["meta"] or (m["ctrl"] and m["alt"]):
            # AltGr (Ctrl+Alt) or Alt/Meta combos: trust the host-produced key if printable.
            host = ev.get("key")
            if m["ctrl"] and m["alt"] and host and len(host) == 1:
                unit = self.emit("char", i, ev, "key", _combo_name(m, code), ch=host, altgr=True)
            else:
                unit = self.emit("token", i, ev, "combo", _combo_name(m, code), token=_combo_name(m, code))
        elif code in PRINTABLE:
            ch = PRINTABLE[code][1 if m["shift"] else 0]
            unit = self.emit("char", i, ev, "key", _combo_name(m, code), ch=ch)
            host = ev.get("key")
            if host is not None and len(host) == 1 and host != ch:
                unit["layout_mismatch"] = True
                if ch.isalpha() and host == ch.swapcase():
                    unit["caps_lock_suspected"] = True
        elif code in FUNCTION_KEYS:
            unit = self.emit("token", i, ev, "function_key", _combo_name(m, code), token=code)
        else:
            unit = self.emit("token", i, ev, "unknown", _combo_name(m, code) or "(no code)",
                             token=code or ev.get("key") or "?")
            self.unknown.append(code or ev.get("key"))

        if unit is not None and code:
            self.open[code] = unit["index"]

    def up(self, i, ev):
        code = ev.get("code") or ""
        if code in MODIFIERS:
            name = MODIFIERS[code]
            self.mods[name] = False
            if name == "alt":
                self.flush_alt(i)
            return
        if code in self.open:
            u = self.units[self.open.pop(code)]
            u["dwell_ms"] = round(ev.get("t", 0.0) - u["t"], 3)
            u["event_indices"].append(i)


def decode_events(events):
    """Decode canonical key events into units plus a summary."""
    d = _Decoder()
    for i, ev in enumerate(events or []):
        if ev.get("type") == "up":
            d.up(i, ev)
        else:
            d.down(i, ev)
    if d.alt is not None:
        d.flush_alt(incomplete=True)

    units = d.units
    text = "".join(u["char"] for u in units if u["kind"] == "char")

    via_counts = {}
    for u in units:
        via_counts[u["via"]] = via_counts.get(u["via"], 0) + 1

    control_methods = {}
    for u in units:
        if u["kind"] == "char" and (ord(u["char"]) < 0x20 or ord(u["char"]) == 0x7F):
            control_methods[u["via"]] = control_methods.get(u["via"], 0) + 1

    # Characters that only Ctrl or Alt emulation can carry (no dedicated key).
    emulated = {k: v for k, v in control_methods.items() if k in ("ctrl", "alt_numpad")}
    if "ctrl" in emulated and "alt_numpad" in emulated:
        mode = "mixed"
    elif "ctrl" in emulated:
        mode = "ctrl_ascii"
    elif "alt_numpad" in emulated:
        mode = "alt_numpad"
    elif control_methods:
        mode = "keys_only"
    else:
        mode = "none_observed"

    mismatches = [u for u in units if u["layout_mismatch"]]
    return {
        "units": units,
        "text": text,
        "summary": {
            "event_count": len(events or []),
            "key_down_count": sum(1 for e in (events or []) if e.get("type") != "up"),
            "unit_count": len(units),
            "char_count": sum(1 for u in units if u["kind"] == "char"),
            "token_count": sum(1 for u in units if u["kind"] == "token"),
            "via_counts": via_counts,
            "control_methods": control_methods,
            "control_char_mode": mode,
            "layout_mismatch_count": len(mismatches),
            "caps_lock_suspected": any(u["caps_lock_suspected"] for u in units),
            "layout_mismatch_examples": [
                {"index": u["index"], "keys": u["keys"], "expected": u["char"], "host_produced": u["host_key"]}
                for u in mismatches[:10]
            ],
            "unknown_keys": d.unknown,
            "tokens": [u["token"] for u in units if u["kind"] == "token"],
            "notes": d.notes,
        },
    }
