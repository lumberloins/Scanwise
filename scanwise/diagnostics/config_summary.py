"""
Tech-facing scanner configuration summary.

Answers the onsite tech's question: "how is this scanner configured?", in
plain words: prefix, suffix, AIM IDs, GS1 separators, which profiles match.
"""

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
    is_gs1 = bool(symbology.get("is_gs1")) or bool(gs1)

    if not is_gs1:
        gs1_status = "not_gs1"
        gs1_words = "Not a GS1 barcode"
    elif gs1 and (gs1.get("heuristic_applied") or any(e.get("too_long") for e in gs1.get("elements", []))):
        gs1_status = "missing"
        gs1_words = "Missing: a GS separator is missing between fields"
    elif anomalies.get("gs_count"):
        gs1_status = "present"
        gs1_words = f"Present ({anomalies['gs_count']} GS separator{'s' if anomalies['gs_count'] != 1 else ''})"
    else:
        gs1_status = "not_needed"
        gs1_words = "None needed (no variable-length field before another field)"

    matched = [r for r in framing.get("profile_results", []) if r["match"] and not r.get("pass_through")]
    prefix_words = framing.get("prefix_words", "None")
    suffix_words = framing.get("suffix_words", "None")
    aim_words = f"On ({symbology.get('aim_id')} = {symbology.get('symbology_name')})" if has_aim else "Off"

    if matched:
        configured_for = " / ".join(r["name"] for r in matched)
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
        "control_chars": {
            "mode": summary.get("control_char_mode", "unknown" if not decode else "none_observed"),
            "words": CONTROL_MODE_WORDS.get(summary.get("control_char_mode"), "unknown (raw text input)"),
        },
        "sentence": sentence,
    }
