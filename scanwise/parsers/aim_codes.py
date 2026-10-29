"""
AIM Symbology Identifiers Dictionary & Matcher.
Interprets standard 3-character AIM identifiers (e.g., ]C1, ]d2, ]A0) transmitted
by barcode scanners configured to transmit AIM Code IDs.
"""

def _a(name, standard, is_gs1, use):
    return {"name": name, "standard": standard, "is_gs1": is_gs1, "healthcare_use": use}


# Modifier meanings per ISO/IEC 15424 and the symbology specs. For 2D codes,
# "FNC1 in first position" is what makes the data a GS1 element string.
AIM_REGISTRY = {
    "]A0": _a("Code 39", "ISO/IEC 16388", False, "Legacy laboratory racks, patient property tags."),
    "]A1": _a("Code 39 (check digit verified)", "ISO/IEC 16388", False, "Legacy lab tubes."),
    "]A3": _a("Code 39 (check digit verified, not sent)", "ISO/IEC 16388", False, "Legacy lab tubes."),
    "]A4": _a("Code 39 Full ASCII", "ISO/IEC 16388", False, "Legacy lab tubes."),
    "]C0": _a("Code 128", "ISO/IEC 15417", False, "Patient wristbands, specimen tubes, internal orders."),
    "]C1": _a("GS1-128 (FNC1 in first position)", "ISO/IEC 15417 / GS1", True, "Pharmaceutical cases, supply chain labels."),
    "]C2": _a("Code 128 (FNC1 in second position)", "ISO/IEC 15417", False, "AIM application-specific data."),
    "]C4": _a("Code 128 (ISBT 128 concatenation)", "ISO/IEC 15417 / ISBT 128", False, "Blood bags, tissue labels."),
    "]d1": _a("Data Matrix", "ISO/IEC 16022", False, "Instrument marking, direct part marking."),
    "]d2": _a("GS1 DataMatrix (FNC1 in first position)", "ISO/IEC 16022 / GS1", True, "FDA UDI, DSCSA unit-dose."),
    "]d3": _a("Data Matrix (FNC1 in second position)", "ISO/IEC 16022", False, "AIM application-specific data."),
    "]d4": _a("Data Matrix (ECI)", "ISO/IEC 16022", False, "Extended character sets."),
    "]d5": _a("GS1 DataMatrix (FNC1 in first position, ECI)", "ISO/IEC 16022 / GS1", True, "GS1 data with ECI."),
    "]d6": _a("Data Matrix (FNC1 in second position, ECI)", "ISO/IEC 16022", False, "AIM application-specific data."),
    "]e0": _a("GS1 DataBar", "ISO/IEC 24724", True, "Unit-dose vials, syringes, small packages."),
    "]e1": _a("GS1 Composite component", "ISO/IEC 24723", True, "2D component of a composite symbol."),
    "]E0": _a("EAN-13 / UPC-A / UPC-E", "ISO/IEC 15420", False, "Retail packaging (GTIN only, no AIs)."),
    "]E3": _a("EAN/UPC with add-on", "ISO/IEC 15420", False, "Retail packaging with supplement."),
    "]E4": _a("EAN-8", "ISO/IEC 15420", False, "Small retail packages (GTIN-8 only)."),
    "]F0": _a("Codabar", "ANSI/AIM BC3", False, "Legacy blood bank, library/archive."),
    "]G0": _a("Code 93", "ANSI/AIM BC5", False, "Internal asset tracking."),
    "]I0": _a("Interleaved 2 of 5", "ISO/IEC 16390", False, "Shipping cartons."),
    "]I1": _a("Interleaved 2 of 5 (check digit verified)", "ISO/IEC 16390", False, "ITF-14 shipping cartons."),
    "]L0": _a("PDF417", "ISO/IEC 15438", False, "IDs, pharmacy scripts."),
    "]L1": _a("PDF417 (ECI)", "ISO/IEC 15438", False, "IDs with extended character sets."),
    "]L2": _a("PDF417 (basic channel)", "ISO/IEC 15438", False, "Legacy readers."),
    "]Q0": _a("QR Code Model 1", "ISO/IEC 18004", False, "Legacy QR."),
    "]Q1": _a("QR Code", "ISO/IEC 18004", False, "Patient portal links, vaccine records, asset tags."),
    "]Q2": _a("QR Code (ECI)", "ISO/IEC 18004", False, "QR with extended character sets."),
    "]Q3": _a("GS1 QR Code (FNC1 in first position)", "ISO/IEC 18004 / GS1", True, "GS1 product and device labeling."),
    "]Q4": _a("GS1 QR Code (FNC1 in first position, ECI)", "ISO/IEC 18004 / GS1", True, "GS1 data with ECI."),
    "]Q5": _a("QR Code (FNC1 in second position)", "ISO/IEC 18004", False, "AIM application-specific data."),
    "]Q6": _a("QR Code (FNC1 in second position, ECI)", "ISO/IEC 18004", False, "AIM application-specific data."),
    "]z0": _a("Aztec Code", "ISO/IEC 24778", False, "Patient wristbands, lab slides."),
    "]z1": _a("GS1 Aztec (FNC1 in first position)", "ISO/IEC 24778 / GS1", True, "GS1 healthcare data in Aztec."),
    "]z2": _a("Aztec (FNC1 in second position)", "ISO/IEC 24778", False, "AIM application-specific data."),
    "]z3": _a("Aztec (ECI)", "ISO/IEC 24778", False, "Extended character sets."),
    "]z4": _a("GS1 Aztec (FNC1 in first position, ECI)", "ISO/IEC 24778 / GS1", True, "GS1 data with ECI."),
    "]z5": _a("Aztec (FNC1 in second position, ECI)", "ISO/IEC 24778", False, "AIM application-specific data."),
    "]J1": _a("GS1 DotCode", "AIM ISS DotCode / GS1", True, "High-speed printed GS1 data."),
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
