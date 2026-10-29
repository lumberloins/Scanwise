"""
Scanner Framing Detector & EMR Profile Matcher.

Detects the prefix and suffix the scanner wraps around barcode data without
requiring a profile, then checks the result against every known profile.

  prefix = leading control run (e.g. STX) + longest known profile prefix
  suffix = trailing run of terminators/controls (CR, LF, Tab, ETX, FF, ...),
           or a longer profile suffix if one matches
  body   = what's left (the AIM ID, if any, is still at the front of body)

A leading GS (FNC1 in first position) is never counted as prefix.
"""
from scanwise.parsers.ascii_chars import describe_char, visualize

_SUFFIX_CATEGORIES = {"terminator", "control", "framing", "c1_control"}
_PREFIX_CATEGORIES = {"control", "framing", "c1_control", "terminator"}


def _hex(s):
    return "".join(f"{ord(c):02x}" for c in s)


def describe_framing_part(s):
    """Human words for a prefix/suffix, e.g. '\\r\\n' -> 'CR + LF'."""
    if not s:
        return "None"
    words, printable = [], ""
    for ch in s:
        info = describe_char(ch)
        if info["visible"]:
            printable += ch
            continue
        if printable:
            words.append(f'"{printable}"')
            printable = ""
        words.append({"CR": "CR (Enter)", "TAB": "Tab"}.get(info["abbr"], info["abbr"]))
    if printable:
        words.append(f'"{printable}"')
    return " + ".join(words)


def detect_framing(text, profiles):
    prefix_ctrl = ""
    i = 0
    while i < len(text) and text[i] != "\x1d" and describe_char(text[i])["category"] in _PREFIX_CATEGORIES:
        i += 1
    prefix_ctrl = text[:i]
    rest = text[i:]

    known_prefixes = sorted({p.get("expected_prefix", "") for p in profiles.values() if p.get("expected_prefix")},
                            key=len, reverse=True)
    profile_prefix = next((p for p in known_prefixes if rest.startswith(p)), "")
    prefix = prefix_ctrl + profile_prefix
    rest = text[len(prefix):]

    j = len(rest)
    while j > 0 and describe_char(rest[j - 1])["category"] in _SUFFIX_CATEGORIES:
        j -= 1
    suffix = rest[j:]
    for p in profiles.values():
        exp = p.get("expected_suffix", "")
        if exp and len(exp) > len(suffix) and rest.endswith(exp):
            suffix = exp
    body = rest[:len(rest) - len(suffix)] if suffix else rest
    return prefix, body, suffix


def match_profile(profile, prefix, suffix):
    exp_p = profile.get("expected_prefix", "")
    exp_s = profile.get("expected_suffix", "")
    reasons = []
    if profile.get("pass_through"):
        return {"match": True, "reasons": ["Pass-through profile accepts any framing."]}
    if prefix != exp_p:
        if not exp_p:
            reasons.append(f"Unexpected prefix {describe_framing_part(prefix)}; expected none.")
        elif not prefix:
            reasons.append(f"Missing prefix {describe_framing_part(exp_p)}.")
        else:
            reasons.append(f"Prefix is {describe_framing_part(prefix)}; expected {describe_framing_part(exp_p)}.")
    if suffix != exp_s:
        if not exp_s:
            reasons.append(f"Unexpected suffix {describe_framing_part(suffix)}; expected none.")
        elif not suffix:
            reasons.append(f"Missing suffix {describe_framing_part(exp_s)}.")
        else:
            reasons.append(f"Suffix is {describe_framing_part(suffix)}; expected {describe_framing_part(exp_s)}.")
    return {"match": not reasons, "reasons": reasons}


def extract_framing(raw_input, profile=None, profiles=None):
    """
    Detect framing and evaluate profiles.

    `profile` is the expected profile (optional). `profiles` is the full profile
    dict; when omitted, only `profile` is used for prefix/suffix hints.
    """
    profiles = dict(profiles or {})
    if profile and profile.get("id") and profile["id"] not in profiles:
        profiles[profile["id"]] = profile

    prefix, body, suffix = detect_framing(raw_input or "", profiles)

    results = []
    for pid, p in profiles.items():
        r = match_profile(p, prefix, suffix)
        results.append({"id": pid, "name": p.get("name", pid), "match": r["match"],
                        "reasons": r["reasons"], "pass_through": bool(p.get("pass_through"))})
    matched = [r for r in results if r["match"] and not r["pass_through"]]

    expected = None
    if profile:
        expected = next((r for r in results if r["id"] == profile.get("id")), None)

    return {
        "profile_id": profile.get("id") if profile else None,
        "profile_name": profile.get("name") if profile else None,
        "profile_matched": expected["match"] if expected else None,
        "profile_reasons": expected["reasons"] if expected else [],
        "expected_prefix_words": describe_framing_part(profile.get("expected_prefix", "")) if profile else None,
        "expected_suffix_words": describe_framing_part(profile.get("expected_suffix", "")) if profile else None,
        "prefix_detected": prefix,
        "suffix_detected": suffix,
        "prefix_display": visualize(prefix),
        "suffix_display": visualize(suffix),
        "prefix_words": describe_framing_part(prefix),
        "suffix_words": describe_framing_part(suffix),
        "clean_payload": body,
        "raw_prefix_hex": _hex(prefix),
        "raw_suffix_hex": _hex(suffix),
        "prefix_length": len(prefix),
        "suffix_length": len(suffix),
        "profile_results": results,
        "matched_profiles": [r["id"] for r in matched],
    }
