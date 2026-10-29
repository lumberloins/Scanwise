"""
GS1 Application Identifier (AI) Parser & Validator for Healthcare.
Parses GTINs, Lot numbers, Expiration dates (with DD=00 rule), Serial numbers,
and performs Modulo 10 check digit validation and heuristic lookahead fallback
for missing FNC1 delimiters before fixed-length date AIs.
"""
import re
import datetime
import calendar

# GS1 Application Identifiers definition table
GS1_AIS = {
    "00": {"name": "SSCC (Serial Shipping Container Code)", "type": "fixed", "length": 18, "is_date": False},
    "01": {"name": "GTIN (Global Trade Item Number)", "type": "fixed", "length": 14, "is_date": False},
    "02": {"name": "GTIN of Contained Trade Items", "type": "fixed", "length": 14, "is_date": False},
    "20": {"name": "Internal Product Variant", "type": "fixed", "length": 2, "is_date": False},
    "22": {"name": "Consumer Product Variant", "type": "variable", "max_length": 20, "is_date": False},
    "37": {"name": "Count of Trade Items", "type": "variable", "max_length": 8, "is_date": False},
    "241": {"name": "Customer Part Number", "type": "variable", "max_length": 30, "is_date": False},
    "250": {"name": "Secondary Serial Number", "type": "variable", "max_length": 30, "is_date": False},
    "10": {"name": "Batch / Lot Number", "type": "variable", "max_length": 20, "is_date": False},
    "11": {"name": "Production Date", "type": "fixed", "length": 6, "is_date": True},
    "13": {"name": "Packaging Date", "type": "fixed", "length": 6, "is_date": True},
    "15": {"name": "Best Before Date", "type": "fixed", "length": 6, "is_date": True},
    "17": {"name": "Expiration Date", "type": "fixed", "length": 6, "is_date": True},
    "21": {"name": "Serial Number", "type": "variable", "max_length": 20, "is_date": False},
    "30": {"name": "Variable Count", "type": "variable", "max_length": 8, "is_date": False},
    "240": {"name": "Additional Product Identification", "type": "variable", "max_length": 30, "is_date": False},
    "8005": {"name": "Price Per Unit of Measure", "type": "fixed", "length": 6, "is_date": False},
}

def validate_gtin_checksum(gtin_str):
    """
    Validates GTIN-14 Modulo 10 check digit.
    """
    if not gtin_str or not gtin_str.isdigit():
        return False

    padded = gtin_str.zfill(14)
    if len(padded) != 14:
        return False

    digits = [int(d) for d in padded]
    checksum_digit = digits[-1]
    body = digits[:-1]

    total = 0
    weight = 3
    for d in reversed(body):
        total += d * weight
        weight = 1 if weight == 3 else 3

    calculated_check = (10 - (total % 10)) % 10
    return calculated_check == checksum_digit

def validate_sscc_checksum(sscc):
    """Mod-10 check for the 18-digit SSCC (same weighting as GTIN)."""
    if not sscc or len(sscc) != 18 or not sscc.isdigit():
        return False
    digits = [int(d) for d in sscc]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - total % 10) % 10 == digits[-1]


def looks_like_gs1(payload):
    """Strong signal of GS1 element string without an AIM ID: leading FNC1 or a clean parse starting with 00/01/02."""
    if not payload:
        return False
    if payload.startswith("\x1d"):
        return True
    if payload[:2] not in ("00", "01", "02"):
        return False
    res = parse_gs1_barcode(payload)
    return res["valid"]


def parse_gs1_date(date_str):
    """
    Parses YYMMDD date string with DD=00 rule support.
    """
    if not date_str or len(date_str) != 6 or not date_str.isdigit():
        return {"raw": date_str, "formatted": None, "valid": False, "expired": False, "error": "Invalid date length or non-numeric."}

    yy = int(date_str[0:2])
    mm = int(date_str[2:4])
    dd = int(date_str[4:6])

    year = 2000 + yy if yy < 50 else 1900 + yy

    if mm < 1 or mm > 12:
        return {"raw": date_str, "formatted": None, "valid": False, "expired": False, "error": f"Invalid month '{mm}'."}

    try:
        if dd == 0:
            last_day = calendar.monthrange(year, mm)[1]
            dt = datetime.date(year, mm, last_day)
            formatted = dt.isoformat()
            rule_applied = "Last day of month (DD=00)"
        else:
            dt = datetime.date(year, mm, dd)
            formatted = dt.isoformat()
            rule_applied = "Exact date"
    except ValueError as e:
        return {"raw": date_str, "formatted": None, "valid": False, "expired": False, "error": str(e)}

    today = datetime.date.today()
    is_expired = dt < today

    return {
        "raw": date_str,
        "formatted": formatted,
        "valid": True,
        "expired": is_expired,
        "rule": rule_applied
    }

def is_valid_yymmdd(s):
    """Checks if a 6-character string forms a plausible YYMMDD date."""
    if len(s) != 6 or not s.isdigit():
        return False
    mm = int(s[2:4])
    dd = int(s[4:6])
    return 1 <= mm <= 12 and 0 <= dd <= 31

def parse_gs1_barcode(payload):
    """
    Parses a GS1 barcode payload string into extracted Application Identifiers,
    supporting heuristic lookahead parsing when FNC1 delimiters are missing before fixed-length date AIs.
    """
    if not payload:
        return {"valid": False, "elements": [], "error": "Empty payload."}

    working = payload.replace('<GS>', '\x1d')

    elements = []
    i = 0
    length = len(working)
    parsing_error = None
    heuristic_applied = False

    while i < length:
        if working[i] == '\x1d':
            i += 1
            continue

        matched_ai = None
        ai_meta = None
        for ai_len in [4, 3, 2]:
            if i + ai_len <= length:
                candidate = working[i:i+ai_len]
                if candidate in GS1_AIS:
                    matched_ai = candidate
                    ai_meta = GS1_AIS[candidate]
                    break

        if not matched_ai:
            parsing_error = f"Unrecognized AI starting at index {i}: '{working[i:i+4]}'"
            break

        i += len(matched_ai)
        val_start = i

        if ai_meta["type"] == "fixed":
            fixed_len = ai_meta["length"]
            if i + fixed_len > length:
                fixed_len = length - i
            val = working[i:i+fixed_len]
            i += fixed_len
        else:
            # Variable length: read until next '\x1d' (GS) or end of string.
            # HEURISTIC LOOKAHEAD FALLBACK: If no '\x1d' is present, check if a fixed-length date AI
            # (like '17', '11', '13', '15') appears later followed by a valid YYMMDD date.
            val_chars = []
            if '\x1d' in working[i:]:
                while i < length and working[i] != '\x1d':
                    val_chars.append(working[i])
                    i += 1
            else:
                # Search remaining string for a known date AI ('17', '11', '13', '15')
                remaining = working[i:]
                found_date_marker = False
                for date_ai in ["17", "11", "13", "15"]:
                    # Find occurrences of date_ai in remaining
                    search_idx = 0
                    while True:
                        pos = remaining.find(date_ai, search_idx)
                        if pos == -1:
                            break
                        # Check if the 6 characters immediately following date_ai form a valid YYMMDD date
                        potential_date = remaining[pos + len(date_ai): pos + len(date_ai) + 6]
                        if is_valid_yymmdd(potential_date):
                            # Found the boundary! Everything from current i up to pos belongs to this variable AI
                            val_chars = list(remaining[:pos])
                            i += pos
                            found_date_marker = True
                            heuristic_applied = True
                            break
                        search_idx = pos + 1
                    if found_date_marker:
                        break

                if not found_date_marker:
                    # Default: consume until end of string
                    while i < length:
                        val_chars.append(working[i])
                        i += 1

            val = "".join(val_chars)

        element_result = {
            "ai": matched_ai,
            "name": ai_meta["name"],
            "raw_value": val,
            "formatted_value": val
        }

        if ai_meta["type"] == "variable" and len(val) > ai_meta["max_length"]:
            element_result["too_long"] = True
        if ai_meta["type"] == "fixed" and len(val) != ai_meta["length"]:
            element_result["truncated"] = True

        if matched_ai in ("00", "01", "02"):
            element_result["check_digit_valid"] = validate_gtin_checksum(val) if matched_ai != "00" else validate_sscc_checksum(val)
        elif ai_meta["is_date"]:
            date_res = parse_gs1_date(val)
            element_result["date_info"] = date_res
            element_result["formatted_value"] = date_res.get("formatted") or val

        elements.append(element_result)

    return {
        "valid": len(elements) > 0 and not parsing_error,
        "elements": elements,
        "heuristic_applied": heuristic_applied,
        "error": parsing_error
    }
