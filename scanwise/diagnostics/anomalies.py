"""
Scanner Wedge Anomaly & Hidden Command Character Detector.
Detects rogue control codes (NUL, ESC, ETX, BEL, SUB), missing GS1 delimiters,
and literal bracketed FNC1 transmissions (e.g. ]10, ]17).
"""
from scanwise.parsers.ascii_chars import inspect_payload

def detect_anomalies(clean_payload, raw_input):
    """
    Scans payload for hidden control characters, mangled data, missing GS1 delimiters,
    and literal bracketed FNC1 transmissions.
    """
    inspection = inspect_payload(raw_input)
    
    # Check for literal bracketed FNC1 transmissions (e.g. ]10, ]17 instead of <GS>)
    literal_fnc1_brackets = ']' in raw_input and any(f']{ai}' in raw_input for ai in ["10", "11", "13", "15", "17", "21", "30", "240"])

    # Check for missing GS1 group separators / FNC1 in composite barcodes
    missing_gs1_delimiter = False
    variable_ais = ["10", "21", "240", "250", "37"]
    
    for ai in variable_ais:
        if ai in clean_payload:
            idx = clean_payload.find(ai)
            if idx != -1:
                after_ai = clean_payload[idx + len(ai):]
                if len(after_ai) > 6 and not '\x1d' in after_ai and not ']' in after_ai and ('17' in after_ai or '21' in after_ai or '11' in after_ai):
                    missing_gs1_delimiter = True

    return {
        "has_hidden_controls": inspection["has_hidden_controls"],
        "has_harmful_controls": inspection["has_harmful_controls"],
        "control_characters": [c for c in inspection["characters"] if c["category"] != "printable"],
        "missing_gs1_delimiter": missing_gs1_delimiter,
        "literal_fnc1_brackets": literal_fnc1_brackets,
        "mangled_data": inspection["has_harmful_controls"]
    }
