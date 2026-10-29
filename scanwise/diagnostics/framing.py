"""
Scanner Framing Detector & EMR Profile Matcher.

Detects the prefix and suffix the scanner wraps around barcode data without
requiring a profile, then checks the result against every known profile.

  prefix = leading control run (e.g. STX) + longest known profile prefix
  suffix = trailing run of terminators/controls (CR, LF, Tab, ETX, FF, ...),
           or a longer profile suffix if one matches
  body   = what's left (the AIM ID, if any, is still at the front of body)

A leading GS (FNC1 in first position) is never counted as prefix.

Profile options:
  expected_prefix            text the EMR expects before the data
  prefix_case_insensitive    match the prefix in any letter case
  expected_suffix            the suffix the EMR expects ("" = none)
  accepted_suffixes          every suffix the EMR accepts (default: just expected_suffix)
  optional_terminators       alternatively: expected_suffix may be followed by any mix of these
                             characters, or none (Epic: \\ then optionally CR / LF / Tab)

Visible suffix text (Epic's closing \\) is only split off when that profile's
prefix was found, so data that merely ends in the same character is left alone.

Epic wraps the data in backslashes (\\data\\ = \\ + data + \\): prefix \\, suffix \\.

Scanners differ in where they put the AIM ID: before the data (prefix, AIM,
data) or before the custom prefix (AIM, prefix, data). Both are recognised;
`aim_at` gives the AIM ID's position when it comes first.

If no known prefix matches but a registered AIM ID (e.g. ]d2) follows some
leading text, that text is treated as an (unrecognized) prefix, so the data
after it is still parsed as a barcode.
"""
from scanwise.parsers.aim_codes import AIM_REGISTRY
from scanwise.parsers.ascii_chars import describe_char, visualize

_MAX_UNKNOWN_PREFIX = 24

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


def _known_prefix_at(rest, known):
    return next((rest[:len(exp)] for exp, ci in known
                 if (rest[:len(exp)].casefold() == exp.casefold() if ci else rest.startswith(exp))), "")


def detect_framing(text, profiles):
    """Return (prefix, body, suffix, aim_at). body starts with the AIM ID, if any."""
    prefix_ctrl = ""
    i = 0
    while i < len(text) and text[i] != "\x1d" and describe_char(text[i])["category"] in _PREFIX_CATEGORIES:
        i += 1
    prefix_ctrl = text[:i]
    rest = text[i:]

    known = sorted({(p["expected_prefix"], bool(p.get("prefix_case_insensitive")))
                    for p in profiles.values() if p.get("expected_prefix")}, key=lambda k: len(k[0]), reverse=True)
    aim_at = None
    profile_prefix = _known_prefix_at(rest, known)
    known_prefix = profile_prefix
    if not profile_prefix and rest[:3] in AIM_REGISTRY:
        # AIM ID sent ahead of the custom prefix: "]d2\data\0100..."
        after = _known_prefix_at(rest[3:], known)
        if after:
            aim_at, profile_prefix = len(prefix_ctrl), after
            known_prefix = after
    if not profile_prefix:
        profile_prefix = _prefix_before_aim(rest)
    prefix = prefix_ctrl + profile_prefix
    if aim_at is not None:
        rest = rest[:3] + rest[3 + len(profile_prefix):]
    else:
        rest = text[len(prefix):]

    j = len(rest)
    while j > 0 and describe_char(rest[j - 1])["category"] in _SUFFIX_CATEGORIES:
        j -= 1
    suffix = rest[j:]
    for p in profiles.values():
        exp = p.get("expected_suffix", "")
        if exp and len(exp) > len(suffix) and rest.endswith(exp):
            suffix = exp
    # Closing text of the profile whose prefix was found (Epic: "\\data\\" = \\ + data + \\).
    if known_prefix:
        for p in profiles.values():
            text = _visible_part(p.get("expected_suffix", ""))
            if (text and p.get("expected_prefix") and prefix_matches(p, known_prefix)
                    and rest[:j].endswith(text) and len(rest[:j]) > len(text)):
                suffix = rest[j - len(text):]
                break
    body = rest[:len(rest) - len(suffix)] if suffix else rest
    return prefix, body, suffix, aim_at


def _prefix_before_aim(rest):
    """Leading text followed by a registered AIM ID, e.g. 'HOSP]d2...' -> 'HOSP'."""
    for pos in range(1, min(len(rest) - 2, _MAX_UNKNOWN_PREFIX + 1)):
        if rest[pos] == "]" and rest[pos:pos + 3] in AIM_REGISTRY:
            lead = rest[:pos]
            if all(describe_char(c)["visible"] for c in lead):
                return lead
            return ""
    return ""


def accepted_suffixes(profile):
    return list(profile.get("accepted_suffixes") or [profile.get("expected_suffix", "")])


def _visible_part(s):
    """Leading visible text of a suffix, e.g. '\\\\\r' -> '\\\\'."""
    out = ""
    for c in s:
        if not describe_char(c)["visible"]:
            break
        out += c
    return out


def split_suffix(suffix):
    """(visible text, trailing terminators/controls), e.g. '\\\\\r' -> ('\\\\', '\r')."""
    text = _visible_part(suffix)
    return text, suffix[len(text):]


def suffix_ok(profile, suffix):
    chars = profile.get("optional_terminators")
    if chars is not None:
        exp = profile.get("expected_suffix", "")
        return suffix.startswith(exp) and all(c in chars for c in suffix[len(exp):])
    return suffix in accepted_suffixes(profile)


def suffix_optional(profile):
    """True if the profile works without an Enter/Tab-style terminator."""
    if profile.get("optional_terminators") is not None:
        return True
    return any(not split_suffix(s)[1] for s in accepted_suffixes(profile))


def prefix_matches(profile, prefix):
    exp = profile.get("expected_prefix", "")
    return prefix.casefold() == exp.casefold() if profile.get("prefix_case_insensitive") else prefix == exp


def describe_expected_suffix(profile):
    chars = profile.get("optional_terminators")
    if chars is not None:
        terms = ', '.join(describe_framing_part(c) for c in chars)
        exp = profile.get("expected_suffix", "")
        return f"{describe_framing_part(exp)}, optionally followed by {terms}" if exp else f"optional (none, or any mix of {terms})"
    acc = accepted_suffixes(profile)
    if len(acc) == 1:
        return describe_framing_part(acc[0])
    others = [describe_framing_part(s) for s in acc if s]
    head = "None required" if "" in acc else describe_framing_part(acc[0])
    return f"{head} ({', '.join(others)} also accepted)" if "" in acc else " or ".join(others)


def match_profile(profile, prefix, suffix):
    exp_p = profile.get("expected_prefix", "")
    exp_s = profile.get("expected_suffix", "")
    reasons = []
    if profile.get("pass_through"):
        return {"match": True, "reasons": ["Pass-through profile accepts any framing."]}
    if not prefix_matches(profile, prefix):
        if not exp_p:
            reasons.append(f"Unexpected prefix {describe_framing_part(prefix)}; expected none.")
        elif not prefix:
            reasons.append(f"Missing prefix {describe_framing_part(exp_p)}.")
        else:
            reasons.append(f"Prefix is {describe_framing_part(prefix)}; expected {describe_framing_part(exp_p)}.")
    if not suffix_ok(profile, suffix):
        if profile.get("optional_terminators") is not None or len(accepted_suffixes(profile)) > 1:
            reasons.append(f"Suffix is {describe_framing_part(suffix)}; expected {describe_expected_suffix(profile)}.")
        elif not exp_s:
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

    prefix, body, suffix, aim_at = detect_framing(raw_input or "", profiles)

    results = []
    for pid, p in profiles.items():
        r = match_profile(p, prefix, suffix)
        results.append({"id": pid, "name": p.get("name", pid), "match": r["match"],
                        "reasons": r["reasons"], "pass_through": bool(p.get("pass_through"))})
    matched = [r for r in results if r["match"] and not r["pass_through"]]

    expected = None
    if profile:
        expected = next((r for r in results if r["id"] == profile.get("id")), None)

    # A missing suffix is only a fault if the EMR in question needs one.
    # With nothing selected or matched there is no basis to demand one: no suffix is then informational.
    judged = [profile] if profile and not profile.get("pass_through") else [profiles[r["id"]] for r in matched]
    suffix_required = bool(judged) and not any(suffix_optional(p) for p in judged)
    known_prefix = any(prefix_matches(p, prefix[len(prefix) - len(p.get("expected_prefix", "")):])
                       for p in profiles.values() if p.get("expected_prefix"))

    return {
        "profile_id": profile.get("id") if profile else None,
        "profile_name": profile.get("name") if profile else None,
        "profile_matched": expected["match"] if expected else None,
        "profile_reasons": expected["reasons"] if expected else [],
        "expected_prefix_words": describe_framing_part(profile.get("expected_prefix", "")) if profile else None,
        "expected_suffix_words": describe_expected_suffix(profile) if profile else None,
        "suffix_required": suffix_required,
        "prefix_unrecognized": bool(prefix) and not known_prefix and any(describe_char(c)["visible"] for c in prefix),
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
        "aim_at": aim_at,
        "suffix_length": len(suffix),
        "profile_results": results,
        "matched_profiles": [r["id"] for r in matched],
    }
