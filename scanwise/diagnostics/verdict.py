"""
Rule-Based Verdict & Fault Categorization Engine.
Synthesizes parser results, framing analysis, anomalies, and timing into
clear technician verdicts (PASS, SCANNER_FAULT, BARCODE_FAULT, ENVIRONMENT_FAULT).
"""

def generate_verdict(framing_res, anomalies_res, gs1_res, timing_res):
    """
    Evaluates all diagnostic subsystems and returns a decisive technician verdict.
    """
    # 1. Check for Environment / VDI Jitter Fault
    if timing_res.get("jitter_detected"):
        return {
            "category": "ENVIRONMENT_FAULT",
            "level": "error",
            "headline": "Virtual Desktop (Citrix/RDP) Latency Jitter Detected",
            "recommendation": "Keystroke arrival spikes indicate virtual channel lag. Adjust scanner inter-character delay settings in the scanner configuration manual."
        }

    # 2. Check for Harmful Rogue Control Characters
    if anomalies_res.get("has_harmful_controls"):
        return {
            "category": "SCANNER_CONFIG_FAULT",
            "level": "error",
            "headline": "Rogue Command Characters Detected in Stream",
            "recommendation": "The scanner is transmitting non-printable ASCII control codes (e.g. NUL, ESC, ETX). Re-flash scanner to factory defaults or re-configure USB HID keyboard wedge mode."
        }

    # 3. Check for Literal Bracketed FNC1 Transmissions (e.g. ]10, ]17)
    if anomalies_res.get("literal_fnc1_brackets"):
        return {
            "category": "SCANNER_CONFIG_FAULT",
            "level": "error",
            "headline": "Scanner Configuration Fault: FNC1 Transmitted as Literal Brackets (]10 / ]17)",
            "recommendation": "The scanner is outputting literal ']' brackets instead of ASCII 29 (<GS>) for FNC1 field separators. Re-configure the scanner's GS1 wedge settings to transmit ASCII 29 ('\\x1d') for FNC1."
        }

    # 4. Check for EMR Framing Mismatch
    if not framing_res.get("profile_matched"):
        profile_name = framing_res.get("profile_name", "Selected EMR")
        return {
            "category": "SCANNER_CONFIG_FAULT",
            "level": "error",
            "headline": f"Missing or Incorrect EMR Framing ({profile_name})",
            "recommendation": f"The scanner is not prepending/appending the required prefix/suffix for {profile_name}. Scan the programming bar codes to set prefix and suffix."
        }

    # 5. Check for Barcode / GS1 Data Faults
    if anomalies_res.get("missing_gs1_delimiter"):
        return {
            "category": "BARCODE_DATA_FAULT",
            "level": "warning",
            "headline": "Barcode Format Warning: Missing FNC1 / GS Separator",
            "recommendation": "The scanner is operating correctly, but the physical barcode label is missing the mandatory FNC1/GS separator between variable-length fields."
        }

    if gs1_res and not gs1_res.get("valid") and gs1_res.get("error"):
        return {
            "category": "BARCODE_DATA_FAULT",
            "level": "warning",
            "headline": "GS1 Application Identifier Parsing Error",
            "recommendation": "The barcode structure contains invalid application identifiers or corrupted data formatting."
        }

    # 6. All Checks Passed!
    return {
        "category": "PASS",
        "level": "success",
        "headline": "Scanner and Barcode Validated Successfully",
        "recommendation": "The scanner configuration, EMR framing, and barcode payload are fully correct. The scanner is not the cause of the clinical workflow failure."
    }
