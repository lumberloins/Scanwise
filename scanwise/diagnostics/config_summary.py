"""
Tech-facing scanner configuration summary.

Answers the onsite tech's question: "how is this scanner configured?", in
plain words: prefix, suffix, AIM IDs, GS1 separators, which profiles match.
"""

from scanwise.diagnostics.framing import describe_framing_part, split_suffix

CONTROL_MODE_WORDS = {
    "ctrl_ascii": "Ctrl+key combinations (Ctrl-ASCII mode)",
    "alt_numpad": "Alt+numpad codes (keypad emulation)",
    "mixed": "a mix of Ctrl+key and Alt+numpad",
    "keys_only": "dedicated keys only (Enter/Tab)",
    "none_observed": "none sent",
}


def build_config_summary(framing, symbology, gs1, anomalies, decode=None):
    summary = (decode or {}).get("summary", {})
    has_aim = bool(symbology.get("has_aim_id"))

    if not gs1:
        gs1_status, gs1_words = "not_gs1", "Not a GS1 barcode"
    elif gs1.get("heuristic_applied"):
        gs1_status, gs1_words = "missing", "Missing: a GS separator is missing between fields"
    elif gs1.get("possible_missing_separator"):
        gs1_status, gs1_words = "possible_missing", "Check: a field may be missing its GS separator"
    elif anomalies.get("gs_count") and gs1.get("separators"):
        n = len(gs1["separators"])
        gs1_status, gs1_words = "present", f"Present ({n} GS separator{'s' if n != 1 else ''})"
    else:
        gs1_status, gs1_words = "not_needed", "None needed (no variable-length field before another field)"
    is_gs1 = bool(gs1)

    matched = [r for r in framing.get("profile_results", []) if r["match"] and not r.get("pass_through")]
    prefix_words = framing.get("prefix_words", "None")
    suffix_words = framing.get("suffix_words", "None")
    aim_words = f"On ({symbology.get('aim_id')} = {symbology.get('symbology_name')})" if has_aim else "Off"

    if matched and not framing.get("prefix_detected"):
        # Profiles without a prefix match any generic scanner with that suffix: say what it does.
        configured_for = f"No prefix, {suffix_words} after each scan (matches {' / '.join(r['name'] for r in matched)})"
    elif matched:
        # Spell out the framing, including whether an Enter/Tab follows: where it is optional (Epic) the tech
        # still needs to know which one this scanner sends.
        text, terms = split_suffix(framing.get("suffix_detected", ""))
        parts = [f"{prefix_words} before the data"]
        if text:
            parts.append(f"{describe_framing_part(text)} after it")
        parts.append(f"then {describe_framing_part(terms)}" if terms else "no Enter or Tab")
        configured_for = f"{' / '.join(r['name'] for r in matched)}: {', '.join(parts)}"
    elif not framing.get("prefix_detected") and not framing.get("suffix_detected"):
        configured_for = "No prefix or suffix (raw data only)"
    else:
        configured_for = f"No matching profile (prefix: {prefix_words}, suffix: {suffix_words})"

    sentence = (f"Prefix: {prefix_words.lower() if prefix_words == 'None' else prefix_words}. "
                f"Suffix: {suffix_words.lower() if suffix_words == 'None' else suffix_words}. "
                f"AIM IDs {'on' if has_aim else 'off'}.")

    return {
        "configured_for": configured_for,
        "matched_profiles": [r["id"] for r in matched],
        "profile_checks": [
            {"id": r["id"], "name": r["name"], "match": r["match"], "reasons": r["reasons"]}
            for r in framing.get("profile_results", []) if not r.get("pass_through")
        ],
        "prefix": {"raw": framing.get("prefix_detected", ""), "words": prefix_words},
        "suffix": {"raw": framing.get("suffix_detected", ""), "words": suffix_words},
        "aim": {"enabled": has_aim, "id": symbology.get("aim_id"), "symbology": symbology.get("symbology_name"),
                "words": aim_words},
        "gs1_separators": {"status": gs1_status, "words": gs1_words},
        "gs1": {
            "is_gs1": is_gs1,
            "form": gs1.get("form") if gs1 else None,
            "order": gs1.get("order", []) if gs1 else [],
            "typical_order": gs1.get("typical_order", True) if gs1 else True,
        },
        "control_chars": {
            "mode": summary.get("control_char_mode", "unknown" if not decode else "none_observed"),
            "words": CONTROL_MODE_WORDS.get(summary.get("control_char_mode"), "unknown (raw text input)"),
        },
        "sentence": sentence,
    }
