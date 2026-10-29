"""
GS1 element-string parser and validator.

Parses element strings in ANY order, as GS1 permits, from three input forms:
  raw           01...17...10...<GS>21...   (what a scanner transmits)
  hri           (01)...(17)...(10)...      (human-readable, some scanners can output it)
  digital_link  https://id.example/01/.../10/...?17=...

Rules applied (GS1 General Specifications 7.8):
  * An element whose AI is in the predefined-length table needs no GS after it.
  * Every other element must be followed by GS unless it is last, including
    fixed-length ones such as (422).
  * Variable-length values run to the next GS or the end of the data.

Missing-separator diagnostics:
  * definite: a value is longer than its AI allows (it swallowed the next
    field), or a non-predefined AI is followed by more data without GS. The
    value is re-split at the most plausible point; the guessed boundary is marked.
  * possible: the data parses, but a variable field contains what looks like a
    strongly validated AI, e.g. lot "LOT1" + "17" + a valid date.
"""
import calendar
import datetime
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from scanwise.parsers.gs1_ai import AIS, CSET64, CSET82, lookup

GS = "\x1d"

# AIs that make a split convincing when they validate (check digit or date).
STRONG_AIS = {"00", "01", "02", "11", "12", "13", "15", "16", "17", "7003", "8017", "8018"}
# Primary keys. Any field order is valid GS1, but order-dependent application
# parsers most often break when the primary key isn't first.
PRIMARY_KEYS = {"00", "01", "02", "253", "255", "401", "402", "414", "417", "8003", "8004", "8006", "8013", "8017", "8018"}


# --------------------------------------------------------------------- checks

def mod10_valid(digits):
    """GS1 mod-10 check digit (weights 3,1 from the right, excluding the check digit)."""
    if not digits or not digits.isdigit() or len(digits) < 2:
        return False
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def validate_gtin_checksum(gtin_str):
    """Validate a GTIN-8/12/13/14 check digit (padded to 14)."""
    if not gtin_str or not gtin_str.isdigit() or len(gtin_str) > 14:
        return False
    return mod10_valid(gtin_str.zfill(14))


def validate_sscc_checksum(sscc):
    return bool(sscc) and len(sscc) == 18 and mod10_valid(sscc)


def gs1_year(yy, today=None):
    """GS1 century rule (GenSpecs 7.12): the year lies within -49..+50 of the current year."""
    today = today or datetime.date.today()
    cur = today.year % 100
    century = today.year - cur
    diff = yy - cur
    if 51 <= diff <= 99:
        century -= 100
    elif -99 <= diff <= -50:
        century += 100
    return century + yy


def parse_gs1_date(date_str, allow_zero_day=True, today=None):
    """Parse YYMMDD, with the DD=00 'last day of month' rule."""
    if not date_str or len(date_str) != 6 or not date_str.isdigit():
        return {"raw": date_str, "formatted": None, "valid": False, "expired": False,
                "error": "Date must be 6 digits (YYMMDD)."}
    yy, mm, dd = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:6])
    year = gs1_year(yy, today)
    if not 1 <= mm <= 12:
        return {"raw": date_str, "formatted": None, "valid": False, "expired": False, "error": f"Invalid month '{mm:02d}'."}
    try:
        if dd == 0:
            if not allow_zero_day:
                raise ValueError("day 00 is not allowed for this AI")
            dt = datetime.date(year, mm, calendar.monthrange(year, mm)[1])
            rule = "Last day of month (DD=00)"
        else:
            dt = datetime.date(year, mm, dd)
            rule = "Exact date"
    except ValueError as e:
        return {"raw": date_str, "formatted": None, "valid": False, "expired": False, "error": f"Invalid date: {e}."}
    return {"raw": date_str, "formatted": dt.isoformat(), "valid": True,
            "expired": dt < (today or datetime.date.today()), "rule": rule}


def is_valid_yymmdd(s):
    return parse_gs1_date(s)["valid"]


def _datetime_valid(s):
    """YYMMDDHHMM (7003, 4324, 4325)."""
    if len(s) != 10 or not s.isdigit() or not parse_gs1_date(s[:6], allow_zero_day=False)["valid"]:
        return False
    return int(s[6:8]) <= 23 and int(s[8:10]) <= 59


# --------------------------------------------------------------------- element validation

def validate_value(entry, value):
    """Validate one element value against its AI spec. Returns (issues, extras)."""
    issues, extras = [], {}
    if len(value) < entry["min_length"]:
        issues.append(f"too short: {len(value)} chars, needs at least {entry['min_length']}")
    if len(value) > entry["max_length"]:
        issues.append(f"too long: {len(value)} chars, maximum {entry['max_length']}")
    pos = 0
    comps = entry["components"]
    for i, comp in enumerate(comps):
        part = value[pos:] if i == len(comps) - 1 else value[pos:pos + comp["max"]]
        pos += len(part)
        if comp["kind"] == "N" and part and not part.isdigit():
            issues.append(f"must be numeric, got {part!r}")
        elif comp["kind"] == "X":
            bad = sorted({c for c in part if c not in CSET82})
            if bad:
                issues.append("characters not allowed in GS1 data: " + " ".join(repr(c) for c in bad))
        elif comp["kind"] == "Z":
            bad = sorted({c for c in part if c not in CSET64})
            if bad:
                issues.append("characters not allowed (base64url only): " + " ".join(repr(c) for c in bad))
        if comp["check"] and part.isdigit() and len(part) == comp["max"]:
            extras["check_digit_valid"] = mod10_valid(part)
            if not extras["check_digit_valid"]:
                issues.append("check digit is wrong")
        if comp["date"]:
            d = parse_gs1_date(part, allow_zero_day=entry["ai"] in ("11", "12", "13", "15", "16", "17"))
            extras["date_info"] = d
            if not d["valid"]:
                issues.append(d["error"])
        if comp["datetime"]:
            extras["datetime_valid"] = _datetime_valid(part)
            if not extras["datetime_valid"]:
                issues.append("invalid date/time (YYMMDDHHMM)")
    if entry["ai"] == "8003" and len(value) >= 14 and value[:14].isdigit():
        extras["check_digit_valid"] = mod10_valid(value[1:14])
        if not extras["check_digit_valid"]:
            issues.append("GRAI check digit is wrong")
    return issues, extras


def _format(entry, value, extras):
    if (extras.get("date_info") or {}).get("formatted"):
        return extras["date_info"]["formatted"]
    if entry["ai"] in ("7003", "4324", "4325") and extras.get("datetime_valid"):
        d = parse_gs1_date(value[:6], allow_zero_day=False)["formatted"]
        return f"{d} {value[6:8]}:{value[8:10]}"
    dec = entry.get("decimals")
    if dec is not None and value.isdigit():
        iso = entry["spec"].startswith("N3+")
        digits = value[3:] if iso else value
        num = digits
        if dec:
            num = digits.rjust(dec + 1, "0")
            num = f"{num[:-dec]}.{num[-dec:]}"
        num = num.lstrip("0") or "0"
        if num.startswith("."):
            num = "0" + num
        return f"{value[:3]} {num}" if iso else num
    return value


def _element(entry, value, start, value_start, end, terminator, index):
    issues, extras = validate_value(entry, value)
    el = {
        "index": index, "ai": entry["ai"], "name": entry["title"], "title": entry["title"], "spec": entry["spec"],
        "value": value, "raw_value": value, "start": start, "value_start": value_start, "end": end,
        "terminator": terminator, "predefined_length": entry["predefined"],
        "fixed_length": entry["fixed_length"] is not None, "unknown": False, "boundary_guessed": False,
        "issues": issues,
    }
    el.update(extras)
    el["formatted_value"] = _format(entry, value, extras)
    if len(value) > entry["max_length"]:
        el["too_long"] = True
    if entry["fixed_length"] is not None and len(value) < entry["fixed_length"]:
        el["truncated"] = True
    return el


def _unknown(text, i, j, base, index, terminator):
    return {"index": index, "ai": text[i:i + 2], "name": "Unknown AI", "title": "Unknown AI", "spec": "?",
            "value": text[i + 2:j], "raw_value": text[i + 2:j], "formatted_value": text[i + 2:j],
            "start": base + i, "value_start": base + i + 2, "end": base + j, "terminator": terminator,
            "predefined_length": False, "fixed_length": False, "unknown": True, "boundary_guessed": False,
            "issues": [f"no GS1 AI starts with {text[i:i + 4]!r}"]}


# --------------------------------------------------------------------- raw element string

def _strict(text, base=0):
    """Parse strictly per spec; positions are offset by `base`. Returns (elements, separator positions)."""
    elements, seps = [], []
    i, n = 0, len(text)
    while i < n:
        if text[i] == GS:
            seps.append(base + i)
            if elements:
                last = elements[-1]
                if last["terminator"] == "pending":
                    last["terminator"] = "gs"
                elif last["predefined_length"]:
                    last["gs_unnecessary"] = True
            i += 1
            continue
        if elements and elements[-1]["terminator"] == "pending":
            elements[-1]["terminator"] = "missing_gs"   # non-predefined AI, next AI follows without GS
        entry = lookup(text, i)
        if entry is None:
            j = text.find(GS, i)
            j = n if j == -1 else j
            elements.append(_unknown(text, i, j, base, len(elements), "gs" if j < n else "end"))
            i = j
            continue
        vstart = i + len(entry["ai"])
        if entry["fixed_length"] is not None:
            j = min(n, vstart + entry["fixed_length"])
            gs_at = text.find(GS, vstart, j)
            if gs_at != -1:
                j = gs_at
        else:
            j = text.find(GS, vstart)
            j = n if j == -1 else j
        if j >= n:
            term = "end"
        elif entry["predefined"]:
            term = "predefined"
        else:
            term = "pending"   # becomes "gs" or "missing_gs" on the next iteration
        elements.append(_element(entry, text[vstart:j], base + i, base + vstart, base + j, term, len(elements)))
        i = j
    if elements and elements[-1]["terminator"] == "pending":
        elements[-1]["terminator"] = "end"
    return elements, seps


def _clean(elements):
    return all(not e["unknown"] and not e["issues"] for e in elements)


def _strong(el):
    return el["ai"] in STRONG_AIS and not el["issues"] and bool(
        el.get("check_digit_valid") or (el.get("date_info") or {}).get("valid") or el.get("datetime_valid"))


def _best_split(value, entry, value_start, require_strong):
    """Where does `value` most plausibly end if a GS was omitted? Returns (cut, tail elements) or None."""
    best = None
    for cut in range(1, min(len(value) - 1, entry["max_length"]) + 1):
        tail, _ = _strict(value[cut:], value_start + cut)
        if not tail or not _clean(tail):
            continue
        first_strong = _strong(tail[0])
        if require_strong and not first_strong:
            continue
        score = (first_strong, sum(1 for t in tail if _strong(t)), -len(tail), cut)
        if best is None or score > best[0]:
            best = (score, cut, tail)
    return (best[1], best[2]) if best else None


def _renumber(elements):
    for k, e in enumerate(elements):
        e["index"] = k
    return elements


def _parse_raw(payload):
    base = 1 if payload.startswith(GS) else 0        # FNC1 in first position
    text = payload[base:]
    elements, seps = _strict(text, base)
    missing = []

    # Definite: a value too long for its AI swallowed the next field.
    for _ in range(20):
        target = next((e for e in elements if e.get("too_long") and not e["boundary_guessed"] and not e.get("unsplittable")), None)
        if target is None:
            break
        entry = AIS[target["ai"]]
        split = _best_split(target["value"], entry, target["value_start"], require_strong=False)
        if not split:
            target["unsplittable"] = True   # nothing plausible; stop retrying this one
            continue
        cut, tail = split
        head = _element(entry, target["value"][:cut], target["start"], target["value_start"],
                        target["value_start"] + cut, "missing_gs", target["index"])
        head["boundary_guessed"] = True
        tail[-1]["terminator"] = target["terminator"]
        elements = _renumber(elements[:target["index"]] + [head] + tail + elements[target["index"] + 1:])
        missing.append({"after_ai": head["ai"], "element": head["index"], "definite": True,
                        "reason": f"({head['ai']}) value was longer than allowed",
                        "value": head["value"], "next_ai": tail[0]["ai"], "next_value": tail[0]["value"]})

    # Definite: a non-predefined AI followed directly by the next AI.
    for e in elements:
        if e["terminator"] == "missing_gs" and not e["boundary_guessed"]:
            nxt = elements[e["index"] + 1] if e["index"] + 1 < len(elements) else None
            missing.append({"after_ai": e["ai"], "element": e["index"], "definite": True,
                            "reason": f"({e['ai']}) is not a predefined-length AI, so it must be followed by GS",
                            "value": e["value"], "next_ai": nxt and nxt["ai"], "next_value": nxt and nxt["value"]})

    # Possible: a variable field hides a strongly validated AI (lot "LOT1" + "17" + valid date).
    flagged = {m["element"] for m in missing}
    for e in elements:
        if e["unknown"] or e["fixed_length"] or e["index"] in flagged or e["boundary_guessed"]:
            continue
        split = _best_split(e["value"], AIS[e["ai"]], e["value_start"], require_strong=True)
        if split:
            cut, tail = split
            missing.append({"after_ai": e["ai"], "element": e["index"], "definite": False,
                            "reason": f"({e['ai']}) value contains what looks like ({tail[0]['ai']}) {tail[0]['value']}",
                            "value": e["value"][:cut], "next_ai": tail[0]["ai"], "next_value": tail[0]["value"]})
    return elements, seps, missing, bool(base)


# --------------------------------------------------------------------- HRI and Digital Link

_HRI_AI = re.compile(r"\((\d{2,4})\)")


def _parse_hri(payload):
    marks = list(_HRI_AI.finditer(payload))
    elements = []
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(payload)
        ai, value = m.group(1), payload[m.end():end]
        entry = AIS.get(ai)
        if entry is None:
            el = _unknown(ai + value, 0, len(ai) + len(value), 0, len(elements), "hri")
            el.update({"ai": ai, "start": m.start(), "value_start": m.end(), "end": end,
                       "issues": [f"unknown AI ({ai})"]})
        else:
            el = _element(entry, value, m.start(), m.end(), end, "hri", len(elements))
        elements.append(el)
    return elements


def _parse_digital_link(payload):
    parts = urlsplit(payload)
    segs = [unquote(s) for s in parts.path.split("/") if s]
    pairs = []
    # The GS1 path is the trailing run of AI/value pairs; anything before it is a site prefix.
    k = len(segs) - 2
    while k >= 0 and segs[k].isdigit() and segs[k] in AIS:
        pairs.insert(0, (segs[k], segs[k + 1]))
        k -= 2
    pairs += [(key, v) for key, v in parse_qsl(parts.query, keep_blank_values=True) if key.isdigit()]
    return [_element(AIS[ai], v, None, None, None, "url", i)
            for i, (ai, v) in enumerate((ai, v) for ai, v in pairs if ai in AIS)]


# --------------------------------------------------------------------- public API

def parse_gs1(payload):
    """Parse a GS1 payload in any supported form."""
    empty = {"valid": False, "form": None, "elements": [], "error": "Empty payload.", "missing_separators": [],
             "separators": [], "order": [], "heuristic_applied": False, "possible_missing_separator": False,
             "unnecessary_separators": [], "leading_fnc1": False, "typical_order": True}
    if not payload:
        return empty
    seps, missing, leading = [], [], False
    if re.match(r"^https?://", payload, re.I):
        form, elements = "digital_link", _parse_digital_link(payload)
    elif _HRI_AI.match(payload):
        form, elements = "hri", _parse_hri(payload)
    else:
        form = "raw"
        elements, seps, missing, leading = _parse_raw(payload)

    unknown = [e for e in elements if e["unknown"]]
    bad = [e for e in elements if e["issues"] and not e["unknown"]]
    if not elements:
        error = "No GS1 elements found."
    elif unknown:
        error = f"Unknown AI at position {unknown[0]['start']}: {unknown[0]['ai']}…"
    elif bad:
        error = f"AI ({bad[0]['ai']}) {bad[0]['issues'][0]}"
    else:
        error = None

    order = [e["ai"] for e in elements]
    has_key = any(ai in PRIMARY_KEYS for ai in order)
    return {
        "valid": bool(elements) and not unknown and not bad and not any(m["definite"] for m in missing),
        "form": form,
        "leading_fnc1": leading,
        "elements": elements,
        "error": error,
        "separators": seps,
        "missing_separators": missing,
        "unnecessary_separators": [e["index"] for e in elements if e.get("gs_unnecessary")],
        "order": order,
        "typical_order": not has_key or order[0] in PRIMARY_KEYS,   # primary key first
        "heuristic_applied": any(m["definite"] for m in missing),
        "possible_missing_separator": any(not m["definite"] for m in missing),
    }


def parse_gs1_barcode(payload):
    """Backward-compatible alias (also accepts literal '<GS>' markers)."""
    return parse_gs1(payload.replace("<GS>", GS) if payload else payload)


def detect_gs1(payload, symbology=None):
    """Decide whether a payload is GS1 data. Returns (parse result or None, detection info)."""
    symbology = symbology or {}
    no = lambda reason: (None, {"is_gs1": False, "confidence": "none", "reason": reason})  # noqa: E731
    yes = lambda p, conf, reason: (p, {"is_gs1": True, "confidence": conf, "reason": reason})  # noqa: E731
    if not payload:
        return no("empty")
    if symbology.get("is_gs1"):
        return yes(parse_gs1(payload), "aim", f"AIM ID {symbology.get('aim_id')} declares GS1 data")

    p = parse_gs1(payload)
    els = p["elements"]
    if p["form"] == "digital_link":
        keys = {"00", "01", "253", "255", "401", "402", "414", "417", "8003", "8004", "8006", "8010", "8013", "8017", "8018"}
        return yes(p, "structure", "GS1 Digital Link URI") if any(e["ai"] in keys for e in els) else no("URL without a GS1 primary key")
    if p["form"] == "hri":
        return yes(p, "structure", "bracketed (human-readable) AIs") if els and not any(e["unknown"] for e in els) else no("bracketed text, not GS1 AIs")
    if p["leading_fnc1"]:
        return yes(p, "structure", "starts with GS (FNC1 in first position)")
    if not els or any(e["unknown"] for e in els):
        return no("does not parse as GS1")
    strong = sum(1 for e in els if _strong(e))
    if len(els) >= 2 and strong >= 1:
        return yes(p, "structure", f"parses as {len(els)} GS1 fields, {strong} with a valid check digit or date")
    if len(els) == 1 and els[0]["ai"] in ("00", "01", "02") and strong:
        return yes(p, "structure", f"a single ({els[0]['ai']}) with a valid check digit")
    if GS in payload and len(els) >= 2:
        return yes(p, "structure", "GS-separated GS1 fields")
    return no("not enough evidence of GS1 structure")


def looks_like_gs1(payload):
    return detect_gs1(payload)[1]["is_gs1"]
