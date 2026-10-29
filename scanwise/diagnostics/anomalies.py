"""
Hidden-character and data-integrity inspector.

Classifies every non-visible character by *where* it sits (prefix, data, suffix)
because the same byte means different things in different places: a CR suffix
is normal, a CR in the middle of the data is not.
"""
from scanwise.parsers.ascii_chars import inspect_payload

LITERAL_FNC1_AIS = ("10", "11", "13", "15", "17", "21", "30", "240")
ISO15434_HEADER = "[)>\x1e"


def region_of(index, prefix_len, aim_len, body_len, aim_at=None):
    """aim_at: position of an AIM ID sent ahead of the custom prefix (AIM, prefix, data)."""
    if aim_at is not None and aim_len:
        if aim_at <= index < aim_at + aim_len:
            return "aim"
        if index < prefix_len + aim_len:
            return "prefix"
    if index < prefix_len:
        return "prefix"
    if index < prefix_len + aim_len:
        return "aim"
    if index < prefix_len + aim_len + body_len:
        return "data"
    return "suffix"


def detect_iso15434(payload):
    """Detect an ISO/IEC 15434 envelope: [)> RS <format> GS ... RS EOT."""
    if not payload.startswith(ISO15434_HEADER):
        return None
    fmt = payload[4:6]
    return {
        "format": fmt,
        "format_name": {"05": "GS1 Application Identifiers", "06": "ASC MH10 Data Identifiers (UDI / HIBC / DoD)",
                        "12": "Text Element Identifiers"}.get(fmt, "Other"),
        "terminated": payload.endswith("\x1e\x04"),
    }


def detect_anomalies(text, framing=None, aim_len=0):
    """
    `text` is the full scan. `framing` is the extract_framing() result (optional;
    without it the whole text is treated as data).
    """
    inspection = inspect_payload(text)
    prefix_len = framing["prefix_length"] if framing else 0
    body = framing["clean_payload"] if framing else text
    body_len = len(body) - aim_len
    payload = body[aim_len:]
    iso = detect_iso15434(payload)

    controls = []
    rogue_in_data = []
    for c in inspection["characters"]:
        if c["category"] in ("printable", "extended"):
            continue
        c = dict(c, region=region_of(c["index"], prefix_len, aim_len, body_len, framing.get("aim_at") if framing else None))
        controls.append(c)
        if c["region"] == "data" and c["category"] not in ("gs1_delimiter",):
            if iso and c["category"] == "separator":
                continue
            rogue_in_data.append(c)

    literal_fnc1 = any(f"]{ai}" in payload for ai in LITERAL_FNC1_AIS)

    return {
        "has_hidden_controls": inspection["has_hidden_controls"],
        "has_harmful_controls": inspection["has_harmful_controls"],
        "control_characters": controls,
        "rogue_in_data": rogue_in_data,
        "harmful_in_framing": [c for c in controls if c["region"] in ("prefix", "suffix") and not c["is_safe"]],
        "mangled_data": any(c["category"] in ("replacement", "c1_control") for c in controls),
        "literal_fnc1_brackets": literal_fnc1,
        "leading_fnc1": payload.startswith("\x1d"),
        "iso15434": iso,
        "gs_count": payload.count("\x1d"),
    }
