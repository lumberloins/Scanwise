"""
PHI redaction for exported scans.

Wristbands and labels can carry PHI (MRN, name, date of birth). A redacted
export keeps everything engineering needs to diagnose a scanner (every control
character, the order of keys, timing, modifiers, how each character was
produced, AIM IDs, GS1 AI codes, prefix/suffix confirmed by an EMR profile) and
replaces every other visible data character at the key-event level:

    A-Z -> X    a-z -> x    0-9 -> 0    other letters -> x

Punctuation and spaces are kept (they are structure, not identity). Because
values are replaced, GS1 check digits and dates in a redacted file will not
validate; the field layout and separators are preserved.
"""
import copy

from scanwise.analysis import analyze

_KEEP_PARTS = {"ai", "separator", "fnc1"}


def _replacement(ch):
    if ch.isdigit():
        return "0"
    if ch.isalpha():
        return "X" if ch.isupper() else "x"
    return None   # punctuation / space: keep


def _code_for(ch, old_code):
    if ch == "0":
        return "Numpad0" if (old_code or "").startswith("Numpad") else "Digit0"
    return "KeyX"


def redact_events(key_events, profiles=None, profile_id=None):
    """Return (redacted_events, redacted_char_count)."""
    events = copy.deepcopy(key_events or [])
    res = analyze(key_events=events, profiles=profiles, profile_id=profile_id)
    keep_framing = bool(res["config"].get("matched_profiles"))
    count = 0
    for u in res["units"]:
        if u["kind"] != "char" or not u.get("visible"):
            continue
        if u.get("region") == "aim" or u.get("gs1_part") in _KEEP_PARTS:
            continue
        if u.get("region") in ("prefix", "suffix") and keep_framing:
            continue
        new = _replacement(u["char"])
        if new is None:
            continue
        count += 1
        idxs = u["event_indices"]
        if u["via"] == "alt_numpad":
            # Rewrite the numpad digits so the Alt code produces the replacement.
            digit_evs = [events[i] for i in idxs if (events[i].get("code") or "").startswith("Numpad")]
            downs = [e for e in digit_evs if e.get("type") != "up"]
            digits = str(ord(new)).zfill(max(len(downs), 2))
            pos = -1
            for e in digit_evs:
                if e.get("type") != "up":
                    pos += 1
                d = digits[min(pos, len(digits) - 1)] if pos >= 0 else digits[0]
                e["code"], e["key"] = f"Numpad{d}", d
            continue
        for i in idxs:
            e = events[i]
            if e.get("code"):
                e["code"] = _code_for(new, e["code"])
            if isinstance(e.get("key"), str) and len(e["key"]) == 1:
                e["key"] = new if e.get("type") != "up" or e["key"] == u["char"] else new.lower()
    return events, count
