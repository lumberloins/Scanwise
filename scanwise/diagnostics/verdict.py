"""
Findings & Verdict Engine.

`build_findings()` returns *every* issue with severity, category, evidence and
two wordings: `detail` for engineers, `tech_hint` for onsite techs.
`generate_verdict()` picks the headline from the findings.
"""

SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}

# Headline priority among findings of equal severity (earlier wins).
PRIORITY = [
    "scan_interrupted", "timing_jitter", "layout_mismatch", "caps_lock", "rogue_control_in_data",
    "harmful_framing_char", "literal_fnc1", "profile_mismatch", "mangled_data", "invalid_check_digit",
    "missing_gs1_separator", "gs1_symbology_mismatch", "unknown_gs1_ai", "invalid_gs1_value", "invalid_date",
    "possible_missing_gs1_separator", "gs1_parse_error", "function_keys", "unknown_keys",
    "no_suffix", "double_suffix", "expired", "manual_typing", "ctrl_mode_shortcuts", "leading_fnc1",
    "iso15434", "gs1_order", "unnecessary_gs", "gs1_detected", "control_char_mode",
]


def _f(fid, severity, category, title, detail, tech_hint=None, evidence=None):
    return {"id": fid, "severity": severity, "category": category, "title": title,
            "detail": detail, "tech_hint": tech_hint or detail, "evidence": evidence or {}}


def _gs1_findings(gs1, det, symbology):
    out = []
    els = gs1.get("elements", [])
    label = lambda e: f"({e['ai']}) {e['title']}"  # noqa: E731

    if det.get("symbology_mismatch"):
        out.append(_f("gs1_symbology_mismatch", "warning", "BARCODE_DATA_FAULT",
                      f"GS1 data in a non-GS1 symbol ({symbology.get('aim_id')} {symbology.get('symbology_name')})",
                      "The data is structured as GS1 fields, but the AIM ID says the symbol was not encoded in GS1 mode "
                      "(no FNC1 in first position). Applications that check the AIM ID will not treat it as GS1.",
                      "This label carries GS1 data but wasn't printed as a GS1 barcode. Many systems will reject it; "
                      "the label is the problem, not the scanner."))

    for m in gs1.get("missing_separators", []):
        e = els[m["element"]] if m["element"] < len(els) else None
        nxt = f"({m['next_ai']})" if m.get("next_ai") else "the next field"
        if m["definite"]:
            out.append(_f("missing_gs1_separator", "warning", "BARCODE_DATA_FAULT",
                          f"Missing GS separator after {label(e) if e else '(' + m['after_ai'] + ')'}",
                          f"{m.get('reason', '')}. Without a GS the field boundary is ambiguous; ScanWise split it as "
                          f"({m['after_ai']}) {m['value']!r} then {nxt}. If every label shows this, the scanner is "
                          "stripping FNC1; if only this label does, the label is encoded wrong.",
                          f"A GS1 separator is missing after the {e['title'] if e else 'field'}. If other labels scan fine, "
                          "this label is bad; if all do this, the scanner is stripping separators.",
                          {"element": m["element"], "after_ai": m["after_ai"], "next_ai": m.get("next_ai")}))
        else:
            out.append(_f("possible_missing_gs1_separator", "warning", "BARCODE_DATA_FAULT",
                          f"Possible missing GS inside {label(e) if e else '(' + m['after_ai'] + ')'}",
                          f"{m.get('reason', '')}, a valid {nxt}. If that's a separate field, the GS after "
                          f"({m['after_ai']}) {m['value']!r} is missing and the expiry/ID will be read as part of the value.",
                          f"The {e['title'] if e else 'field'} may have swallowed the next field: check the printed label.",
                          {"element": m["element"], "next_ai": m.get("next_ai"), "next_value": m.get("next_value")}))

    for e in els:
        if e["unknown"]:
            out.append(_f("unknown_gs1_ai", "warning", "BARCODE_DATA_FAULT", f"Unknown GS1 AI at position {e['start']}",
                          f"{e['issues'][0]}. Either an AI ScanWise doesn't know, or earlier data is corrupt.",
                          "The barcode contains a field this tool doesn't recognise.", {"element": e["index"]}))
            continue
        if e.get("check_digit_valid") is False:
            out.append(_f("invalid_check_digit", "error", "BARCODE_DATA_FAULT", f"Invalid check digit in {label(e)}",
                          f"{e['value']} fails the GS1 mod-10 check.",
                          "The barcode label itself is bad (wrong check digit). The scanner is fine.", {"element": e["index"]}))
        di = e.get("date_info")
        if di and not di.get("valid"):
            out.append(_f("invalid_date", "warning", "BARCODE_DATA_FAULT", f"Invalid date in {label(e)}",
                          di.get("error", ""), "The date encoded in the barcode is invalid.", {"element": e["index"]}))
        elif di and di.get("expired") and e["ai"] in ("17", "7003"):
            out.append(_f("expired", "info", "BARCODE_DATA_FAULT", "Product is expired",
                          f"Expiration {e['formatted_value']} is in the past.", "This product is past its expiration date."))
        other = [i for i in e["issues"] if "check digit" not in i and not i.startswith("Invalid") and not i.startswith("too long")
                 and not i.startswith("Date must")]
        if other and not e.get("boundary_guessed"):
            out.append(_f("invalid_gs1_value", "warning", "BARCODE_DATA_FAULT", f"Invalid value in {label(e)}",
                          "; ".join(other), f"The {e['title']} field is not formatted the way GS1 requires.",
                          {"element": e["index"], "value": e["value"]}))

    if gs1.get("unnecessary_separators"):
        names = ", ".join(f"({els[i]['ai']})" for i in gs1["unnecessary_separators"])
        out.append(_f("unnecessary_gs", "info", "INFO", "GS after a predefined-length field",
                      f"A GS follows {names}. GS1 allows it but doesn't require it; strict parsers accept it."))

    if len(els) > 1:
        order = " → ".join(f"({e['ai']})" for e in els)
        if not gs1.get("typical_order", True):
            out.append(_f("gs1_order", "info", "INFO", f"Primary key is not the first GS1 field ({els[0]['ai']} first)",
                          f"Received order: {order}. GS1 allows any order; only variable-length fields need a GS after "
                          "them. If an application rejects this label, its parser is order-dependent: an application "
                          "issue, not the scanner or the label.",
                          f"Fields arrived in this order: {order}. That's valid GS1. If the EMR rejects it, the EMR's "
                          "barcode parsing is order-dependent."))
    if det.get("confidence") == "structure":
        out.append(_f("gs1_detected", "info", "INFO", "GS1 data detected without a GS1 AIM ID",
                      f"Recognised as GS1 because it {det.get('reason')}. Enable AIM ID transmission on the scanner to make "
                      "this unambiguous for EMRs."))
    return out


def build_findings(framing, anomalies, gs1, timing, decode=None, client=None, gs1_detection=None, symbology=None):
    framing, anomalies, timing = framing or {}, anomalies or {}, timing or {}
    summary = (decode or {}).get("summary", {})
    client = client or {}
    out = []

    if client.get("interrupted"):
        out.append(_f("scan_interrupted", "error", "ENVIRONMENT_FAULT",
                      "Scan interrupted: browser lost focus mid-scan",
                      f"The page lost focus during the scan ({client.get('interruption_reason', 'blur')}). In Ctrl-ASCII mode, "
                      "DC4 (Ctrl+T), SO (Ctrl+N) and ETB (Ctrl+W) trigger browser shortcuts, so the remaining keystrokes went elsewhere.",
                      "The scanner sent a key combination that switched windows. Ask engineering to review the scanner's control-character setting."))

    if timing.get("jitter_detected"):
        out.append(_f("timing_jitter", "error", "ENVIRONMENT_FAULT",
                      "Keystroke timing gaps mid-scan (VDI/RDP latency)",
                      timing.get("description", ""),
                      "Characters arrived with long pauses. On Citrix/RDP, increase the scanner's inter-character delay.",
                      {"spikes": timing.get("spikes", [])}))

    if summary.get("layout_mismatch_count"):
        ex = summary.get("layout_mismatch_examples", [])
        out.append(_f("layout_mismatch", "error", "ENVIRONMENT_FAULT",
                      "Host keyboard layout doesn't match the scanner's keyboard-country setting",
                      f"{summary['layout_mismatch_count']} key(s) produced different characters on this host than the US decode "
                      "of the physical keys. Set the scanner's keyboard country to match the PC, or switch the PC layout.",
                      "Scanner and PC keyboard language don't match, so some characters come out wrong.", {"examples": ex}))

    if summary.get("caps_lock_suspected"):
        out.append(_f("caps_lock", "warning", "ENVIRONMENT_FAULT", "Letter case inverted: Caps Lock appears to be on",
                      "The browser reported the opposite case for letters the scanner typed.",
                      "Turn Caps Lock off and scan again."))

    rogue = anomalies.get("rogue_in_data") or []
    if rogue:
        names = sorted({c["abbr"] for c in rogue if c.get("abbr")})
        out.append(_f("rogue_control_in_data", "error", "SCANNER_CONFIG_FAULT",
                      f"Control character(s) inside the barcode data: {', '.join(names)}",
                      "Non-printable characters appear between the prefix and suffix. Unless the barcode itself encodes them, "
                      "the scanner is injecting them (data editing / substitution rules or control-character mapping).",
                      "The scanner is inserting hidden characters into the data.",
                      {"indices": [c["index"] for c in rogue]}))

    harmful_framing = anomalies.get("harmful_in_framing") or []
    if harmful_framing:
        names = sorted({c["abbr"] for c in harmful_framing if c.get("abbr")})
        out.append(_f("harmful_framing_char", "error" if any(c["severity"] == "bad" for c in harmful_framing) else "warning",
                      "SCANNER_CONFIG_FAULT", f"Prefix/suffix contains {', '.join(names)}",
                      "The scanner's prefix or suffix includes characters EMR text fields don't accept.",
                      f"The scanner adds {', '.join(names)} before or after the data. Re-program the prefix/suffix.",
                      {"indices": [c["index"] for c in harmful_framing]}))

    if anomalies.get("literal_fnc1_brackets"):
        out.append(_f("literal_fnc1", "error", "SCANNER_CONFIG_FAULT", "FNC1 transmitted as literal ']' characters",
                      "Found ']' immediately before a GS1 AI. The scanner is sending FNC1 as text instead of GS (0x1D).",
                      "Scanner GS1 separator setting is wrong. Program it to send GS (ASCII 29) for FNC1."))

    if framing.get("profile_matched") is False:
        out.append(_f("profile_mismatch", "error", "SCANNER_CONFIG_FAULT",
                      f"Framing doesn't match {framing.get('profile_name')}",
                      " ".join(framing.get("profile_reasons", [])),
                      f"{' '.join(framing.get('profile_reasons', []))} Program the scanner for {framing.get('profile_name')}: "
                      f"prefix {framing.get('expected_prefix_words')}, suffix {framing.get('expected_suffix_words')}."))

    if anomalies.get("mangled_data"):
        out.append(_f("mangled_data", "error", "BARCODE_DATA_FAULT", "Mangled characters (U+FFFD or C1 controls)",
                      "The stream contains replacement or C1 control characters: data was corrupted before reaching the page."))

    if gs1:
        out.extend(_gs1_findings(gs1, gs1_detection or {}, symbology or {}))

    if summary.get("tokens"):
        out.append(_f("function_keys", "warning", "SCANNER_CONFIG_FAULT",
                      f"Scanner pressed non-character keys: {', '.join(summary['tokens'][:8])}",
                      "These keys carry no character. Usually the scanner's function-key mapping or a prefix/suffix "
                      "programmed as a key (e.g. PageDown) instead of a character.",
                      "The scanner presses extra keys (like F-keys or PageDown) that can trigger EMR shortcuts."))

    if summary.get("unknown_keys"):
        out.append(_f("unknown_keys", "warning", "SCANNER_CONFIG_FAULT", "Unrecognized key codes",
                      f"Key codes not in the US table: {', '.join(map(str, summary['unknown_keys'][:8]))}."))

    suffix = framing.get("suffix_detected", "")
    if framing and not suffix and framing.get("clean_payload"):
        out.append(_f("no_suffix", "warning", "SCANNER_CONFIG_FAULT", "No suffix (no Enter or Tab after the data)",
                      "The scan ends without a terminator, so EMR fields won't submit or advance automatically.",
                      "The scanner doesn't press Enter or Tab after the barcode. Most EMRs need one."))
    elif suffix and len(suffix) >= 2 and len(set(suffix)) == 1:
        out.append(_f("double_suffix", "warning", "SCANNER_CONFIG_FAULT", "Repeated suffix character",
                      f"Suffix is {framing.get('suffix_words')}; repeated terminators can submit forms twice.",
                      "The scanner presses Enter/Tab more than once after the barcode."))

    if timing.get("deltas") and timing.get("is_scanner_speed") is False:
        out.append(_f("manual_typing", "info", "INFO", "Input speed looks like manual typing",
                      timing.get("description", ""), "This looked like typing, not a scan."))

    mode = summary.get("control_char_mode")
    if mode in ("ctrl_ascii", "mixed"):
        out.append(_f("ctrl_mode_shortcuts", "info", "INFO",
                      "Scanner uses Ctrl+key emulation for control characters",
                      "In this mode ETB/DC4/SO (Ctrl+W/T/N) collide with browser shortcuts. Use fullscreen keyboard lock "
                      "or the native agent to capture them safely."))
    if mode and mode != "none_observed":
        out.append(_f("control_char_mode", "info", "INFO", f"Control-character method: {mode}",
                      f"Control characters were produced via: {summary.get('control_methods')}."))

    if anomalies.get("leading_fnc1"):
        out.append(_f("leading_fnc1", "info", "INFO", "Leading GS (FNC1 in first position) transmitted",
                      "The scanner transmits the symbology's leading FNC1 as GS. Some EMRs don't expect it."))
    if anomalies.get("iso15434"):
        iso = anomalies["iso15434"]
        out.append(_f("iso15434", "info", "INFO", f"ISO/IEC 15434 envelope, format {iso['format']}",
                      f"{iso['format_name']}. RS/GS/EOT separators inside the envelope are expected."
                      + ("" if iso["terminated"] else " Envelope is NOT terminated with RS EOT.")))

    order = {fid: i for i, fid in enumerate(PRIORITY)}
    out.sort(key=lambda f: (SEVERITY_RANK[f["severity"]], order.get(f["id"], 99)))
    return out


def generate_verdict(framing_res, anomalies_res, gs1_res, timing_res, decode=None, client=None, findings=None):
    if findings is None:
        findings = build_findings(framing_res, anomalies_res, gs1_res, timing_res, decode, client)
    top = next((f for f in findings if f["severity"] in ("error", "warning")), None)
    if not top:
        return {
            "category": "PASS",
            "level": "success",
            "headline": "Scanner and Barcode Validated Successfully",
            "recommendation": "Framing, characters and barcode data are all correct. The scanner is not the cause.",
        }
    return {
        "category": top["category"],
        "level": top["severity"],
        "headline": top["title"],
        "recommendation": top["tech_hint"],
        "finding_id": top["id"],
    }
