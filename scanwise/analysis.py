"""
End-to-end scan analysis pipeline shared by the API and tests.

Input is either canonical key events (preferred) or a legacy raw string.
"""
import datetime

from scanwise.capture.decoder import decode_events
from scanwise.diagnostics.anomalies import detect_anomalies, region_of
from scanwise.diagnostics.config_summary import build_config_summary
from scanwise.diagnostics.framing import extract_framing
from scanwise.diagnostics.timing import analyze_timings
from scanwise.diagnostics.verdict import build_findings, generate_verdict
from scanwise.parsers.aim_codes import parse_aim_identifier
from scanwise.parsers.ascii_chars import describe_char, visualize
from scanwise.parsers.gs1_parser import detect_gs1


def _units_from_text(text, timings):
    units = []
    for i, ch in enumerate(text):
        units.append({"index": i, "kind": "char", "char": ch, "code_point": ord(ch), "token": None,
                      "via": "raw", "keys": None, "event_indices": [],
                      "t": timings[i] if timings and i < len(timings) else None,
                      "dwell_ms": None, "repeat": False, "host_key": None,
                      "layout_mismatch": False, "caps_lock_suspected": False})
    return units


def _tag_gs1(units, gs1, offset):
    """Mark each character with the GS1 field it belongs to (raw and bracketed forms)."""
    if not gs1 or gs1.get("form") not in ("raw", "hri"):
        return
    spans = [(e["start"], e["value_start"], e["end"], e["index"]) for e in gs1["elements"] if e.get("start") is not None]
    seps = set(gs1.get("separators") or [])
    for u in units:
        if u["kind"] != "char" or u.get("region") != "data":
            continue
        p = u["char_index"] - offset
        if p == 0 and gs1.get("leading_fnc1"):
            u["gs1_part"] = "fnc1"
            continue
        if p in seps:
            u["gs1_part"] = "separator"
            u["gs1_after"] = max((i for (st, vs, en, i) in spans if en <= p), default=None)
            continue
        for st, vs, en, i in spans:
            if st <= p < en:
                u["gs1_element"] = i
                u["gs1_part"] = "ai" if p < vs else "value"
                break


def analyze(key_events=None, raw_input=None, profiles=None, profile_id=None, keystroke_timings=None, client=None):
    profiles = profiles or {}
    decode = None
    if key_events:
        decode = decode_events(key_events)
        text = decode["text"]
        units = decode["units"]
    else:
        text = raw_input or ""
        units = _units_from_text(text, keystroke_timings)

    expected = profiles.get(profile_id) if profile_id and profile_id != "auto" else None
    framing = extract_framing(text, expected, profiles)
    symbology = parse_aim_identifier(framing["clean_payload"])
    aim_len = 3 if symbology["has_aim_id"] else 0
    payload = symbology["clean_payload"]

    gs1, gs1_detection = detect_gs1(payload, symbology)
    gs1_detection["symbology_mismatch"] = bool(gs1 and symbology["has_aim_id"] and not symbology["is_gs1"])

    anomalies = detect_anomalies(text, framing, aim_len)

    char_units = [u for u in units if u["kind"] == "char"]
    times = [u["t"] for u in char_units if u["t"] is not None]
    if len(times) != len(char_units):
        times = list(keystroke_timings or [])
    timing = analyze_timings(times, [u["dwell_ms"] for u in char_units])

    findings = build_findings(framing, anomalies, gs1, timing, decode, client, gs1_detection, symbology)
    verdict = generate_verdict(framing, anomalies, gs1, timing, findings=findings)
    config = build_config_summary(framing, symbology, gs1, anomalies, decode)

    # Enrich units with character info, region and per-unit delta.
    body_len = len(framing["clean_payload"]) - aim_len
    char_pos = 0
    prev_t = None
    for u in units:
        if u["kind"] == "char":
            info = describe_char(u["char"])
            u.update({"abbr": info["abbr"], "name": info["name"], "category": info["category"],
                      "severity": info["severity"], "hex": info["hex"], "visible": info["visible"],
                      "description": info["desc"], "char_index": char_pos,
                      "region": region_of(char_pos, framing["prefix_length"], aim_len, body_len, framing.get("aim_at"))})
            char_pos += 1
        else:
            u.update({"abbr": u["token"], "name": f"Key: {u['token']}", "category": "token",
                      "severity": "warn", "hex": None, "visible": False, "description": "", "char_index": None,
                      "region": "token"})
        u["delta_ms"] = round(u["t"] - prev_t, 3) if (u["t"] is not None and prev_t is not None) else None
        if u["t"] is not None:
            prev_t = u["t"]

    _tag_gs1(units, gs1, framing["prefix_length"] + aim_len)

    utf8 = text.encode("utf-8")
    return {
        "status": "success",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_mode": "key_events" if key_events else "raw_text",
        "text": text,
        "text_hex": " ".join(f"{b:02x}" for b in utf8),
        "units": units,
        "decode": decode["summary"] if decode else None,
        "verdict": verdict,
        "findings": findings,
        "config": config,
        "framing": framing,
        "symbology": symbology,
        "gs1_data": gs1,
        "gs1_detection": gs1_detection,
        "anomalies": anomalies,
        "timing": timing,
        "client": client or {},
        "raw_dump": {"ascii": visualize(text), "hex": " ".join(f"{ord(c):02x}" for c in text)},
    }
