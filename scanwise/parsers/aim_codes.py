"""
AIM Symbology Identifiers Dictionary & Matcher.
Interprets standard 3-character AIM identifiers (e.g., ]C1, ]d2, ]A0) transmitted
by barcode scanners configured to transmit AIM Code IDs.
"""

AIM_REGISTRY = {
    "]A0": {"name": "Code 39", "standard": "ISO/IEC 16388", "is_gs1": False, "healthcare_use": "Legacy laboratory racks, patient property tags."},
    "]A1": {"name": "Code 39 with Full ASCII", "standard": "ISO/IEC 16388", "is_gs1": False, "healthcare_use": "Legacy lab tubes."},
    "]C0": {"name": "Code 128", "standard": "ISO/IEC 15417", "is_gs1": False, "healthcare_use": "Patient wristbands, specimen tubes, internal orders."},
    "]C1": {"name": "GS1-128 (Code 128 w/ FNC1)", "standard": "ISO/IEC 15417 / GS1 General Specs", "is_gs1": True, "healthcare_use": "Bulk pharmaceuticals, blood bags (ISBT 128), case labels."},
    "]C2": {"name": "Code 128 with AIM Concatenation", "standard": "ISO/IEC 15417", "is_gs1": False, "healthcare_use": "Composite healthcare labels."},
    "]d1": {"name": "DataMatrix (ECC 200)", "standard": "ISO/IEC 16022", "is_gs1": False, "healthcare_use": "Surgical instrument marking, direct part marking."},
    "]d2": {"name": "GS1 DataMatrix", "standard": "ISO/IEC 16022 / GS1 General Specs", "is_gs1": True, "healthcare_use": "FDA UDI medical device marking, DSCSA pharmaceutical unit-dose."},
    "]e0": {"name": "GS1 DataBar (Omnidirectional / Stacked)", "standard": "ISO/IEC 24724", "is_gs1": True, "healthcare_use": "Small pharmaceutical vials, syringes, unit-dose packages."},
    "]e1": {"name": "GS1 DataBar Expanded", "standard": "ISO/IEC 24724", "is_gs1": True, "healthcare_use": "Variable weight/measure pharmaceutical items."},
    "]E0": {"name": "UPC-A / EAN-13", "standard": "ISO/IEC 15420", "is_gs1": True, "healthcare_use": "Retail hospital over-the-counter medications."},
    "]E4": {"name": "EAN-8", "standard": "ISO/IEC 15420", "is_gs1": True, "healthcare_use": "Small retail medical packages."},
    "]F0": {"name": "Codabar", "standard": "ANSI/AIM BC3", "is_gs1": False, "healthcare_use": "Legacy blood bank catalog numbers, library/archive."},
    "]G0": {"name": "Code 93", "standard": "ANSI/AIM BC5", "is_gs1": False, "healthcare_use": "Internal inventory asset tracking."},
    "]I0": {"name": "Interleaved 2 of 5 (ITF)", "standard": "ISO/IEC 16390", "is_gs1": False, "healthcare_use": "Outer shipping cartons, cardboard case boxes."},
    "]L0": {"name": "PDF417", "standard": "ISO/IEC 15438", "is_gs1": False, "healthcare_use": "State driver licenses, military medical IDs, pharmacy scripts."},
    "]Q0": {"name": "QR Code", "standard": "ISO/IEC 18004", "is_gs1": False, "healthcare_use": "Patient portal links, vaccine records, equipment asset tags."},
    "]Q1": {"name": "GS1 QR Code", "standard": "ISO/IEC 18004 / GS1 General Specs", "is_gs1": True, "healthcare_use": "Modern pharmaceutical and medical device labeling."},
    "]z0": {"name": "Aztec Code", "standard": "ISO/IEC 24778", "is_gs1": False, "healthcare_use": "Patient ID wristbands, lab specimen microscope slides."},
    "]z1": {"name": "Aztec Code (with GS1 FNC1)", "standard": "ISO/IEC 24778", "is_gs1": True, "healthcare_use": "Advanced healthcare mobile scans."},
}

def parse_aim_identifier(raw_input_str):
    """
    Checks if a raw input string starts with an AIM symbology identifier (e.g. ']C1', ']d2').
    Returns a dict with symbology metadata and the stripped payload, or defaults if not present.
    """
    if not raw_input_str or len(raw_input_str) < 3:
        return {
            "has_aim_id": False,
            "aim_id": None,
            "symbology_name": "Unknown / Raw",
            "standard": "N/A",
            "is_gs1": False,
            "healthcare_use": "Unidentified symbology format.",
            "clean_payload": raw_input_str
        }

    prefix = raw_input_str[:3]
    if prefix.startswith("]") and prefix in AIM_REGISTRY:
        info = AIM_REGISTRY[prefix]
        return {
            "has_aim_id": True,
            "aim_id": prefix,
            "symbology_name": info["name"],
            "standard": info["standard"],
            "is_gs1": info["is_gs1"],
            "healthcare_use": info["healthcare_use"],
            "clean_payload": raw_input_str[3:]
        }
    
    # Check for general starting bracket even if not in registry
    if raw_input_str.startswith("]"):
        return {
            "has_aim_id": True,
            "aim_id": prefix,
            "symbology_name": f"Custom / Unrecognized AIM ({prefix})",
            "standard": "Unknown",
            "is_gs1": False,
            "healthcare_use": "Custom configured scanner symbology.",
            "clean_payload": raw_input_str[3:]
        }

    return {
        "has_aim_id": False,
        "aim_id": None,
        "symbology_name": "Standard / Non-AIM",
        "standard": "N/A",
        "is_gs1": False,
        "healthcare_use": "Standard barcode without AIM header enabled.",
        "clean_payload": raw_input_str
    }
