"""
ASCII Control Character Definitions & Safety Categorization for Barcode Scanners.
Classifies ASCII codes 0x00 through 0x7F into categories:
- gs1_delimiter (e.g. ASCII 29 <GS> / FNC1)
- line_terminator (CR, LF, TAB)
- harmful_control (NUL, ETX, ESC, BEL, SUB, etc.)
- printable (Standard alphanumeric and punctuation)
"""

ASCII_CATEGORIES = {
    # 0x00 - 0x1F: Control Characters
    0: {"symbol": "[NUL]", "name": "Null (Zero Byte)", "category": "harmful_control", "safe": False, "desc": "Rogue zero byte. Often crashes terminal buffers or corrupts EMR string fields."},
    1: {"symbol": "[SOH]", "name": "Start of Heading", "category": "harmful_control", "safe": False, "desc": "Communications control character."},
    2: {"symbol": "[STX]", "name": "Start of Text", "category": "harmful_control", "safe": False, "desc": "Text transmission start code."},
    3: {"symbol": "[ETX]", "name": "End of Text", "category": "harmful_control", "safe": False, "desc": "Abrupt termination control code."},
    4: {"symbol": "[EOT]", "name": "End of Transmission", "category": "harmful_control", "safe": False, "desc": "Transmission end code."},
    5: {"symbol": "[ENQ]", "name": "Enquiry", "category": "harmful_control", "safe": False, "desc": "Request response code."},
    6: {"symbol": "[ACK]", "name": "Acknowledge", "category": "harmful_control", "safe": False, "desc": "Positive acknowledgment."},
    7: {"symbol": "[BEL]", "name": "Bell", "category": "harmful_control", "safe": False, "desc": "Audible alert code. Can cause unexpected beeps on technician workstations."},
    8: {"symbol": "[BS]", "name": "Backspace", "category": "harmful_control", "safe": False, "desc": "Deletes preceding character in wedge input."},
    9: {"symbol": "[TAB]", "name": "Tab", "category": "line_terminator", "safe": True, "desc": "Horizontal tab. Used by some EMRs for field navigation."},
    10: {"symbol": "[LF]", "name": "Line Feed", "category": "line_terminator", "safe": True, "desc": "New line feed character."},
    11: {"symbol": "[VT]", "name": "Vertical Tab", "category": "harmful_control", "safe": False, "desc": "Vertical tabulation."},
    12: {"symbol": "[FF]", "name": "Form Feed", "category": "harmful_control", "safe": False, "desc": "Printer / screen form feed."},
    13: {"symbol": "[CR]", "name": "Carriage Return", "category": "line_terminator", "safe": True, "desc": "Standard line terminator / enter key suffix."},
    14: {"symbol": "[SO]", "name": "Shift Out", "category": "harmful_control", "safe": False, "desc": "Code extension."},
    15: {"symbol": "[SI]", "name": "Shift In", "category": "harmful_control", "safe": False, "desc": "Resume normal characters."},
    16: {"symbol": "[DLE]", "name": "Data Link Escape", "category": "harmful_control", "safe": False, "desc": "Data transmission escape."},
    17: {"symbol": "[DC1]", "name": "Device Control 1 (XON)", "category": "harmful_control", "safe": False, "desc": "Flow control start."},
    18: {"symbol": "[DC2]", "name": "Device Control 2", "category": "harmful_control", "safe": False, "desc": "Device control code."},
    19: {"symbol": "[DC3]", "name": "Device Control 3 (XOFF)", "category": "harmful_control", "safe": False, "desc": "Flow control stop."},
    20: {"symbol": "[DC4]", "name": "Device Control 4", "category": "harmful_control", "safe": False, "desc": "Device control code."},
    21: {"symbol": "[NAK]", "name": "Negative Acknowledge", "category": "harmful_control", "safe": False, "desc": "Negative response."},
    22: {"symbol": "[SYN]", "name": "Synchronous Idle", "category": "harmful_control", "safe": False, "desc": "Synchronous transmission idle."},
    23: {"symbol": "[ETB]", "name": "End of Transmission Block", "category": "harmful_control", "safe": False, "desc": "Block transmission end."},
    24: {"symbol": "[CAN]", "name": "Cancel", "category": "harmful_control", "safe": False, "desc": "Cancels current operation."},
    25: {"symbol": "[EM]", "name": "End of Medium", "category": "harmful_control", "safe": False, "desc": "Medium end indicator."},
    26: {"symbol": "[SUB]", "name": "Substitute", "category": "harmful_control", "safe": False, "desc": "Substitute character for invalid data."},
    27: {"symbol": "[ESC]", "name": "Escape", "category": "harmful_control", "safe": False, "desc": "Escape sequence starter. Often aborts EMR dialogs or opens menus."},
    28: {"symbol": "[FS]", "name": "File Separator", "category": "harmful_control", "safe": False, "desc": "File separator."},
    29: {"symbol": "[GS]", "name": "Group Separator (FNC1)", "category": "gs1_delimiter", "safe": True, "desc": "Mandatory GS1 FNC1 separator between variable-length Application Identifiers."},
    30: {"symbol": "[RS]", "name": "Record Separator", "category": "harmful_control", "safe": False, "desc": "Record separator."},
    31: {"symbol": "[US]", "name": "Unit Separator", "category": "harmful_control", "safe": False, "desc": "Unit separator."},
    # 0x7F: Delete
    127: {"symbol": "[DEL]", "name": "Delete", "category": "harmful_control", "safe": False, "desc": "Delete character."},
}

def get_char_info(code_or_char):
    """
    Returns safety and category information for an integer ASCII code or character string.
    """
    if isinstance(code_or_char, str):
        if len(code_or_char) == 0:
            return None
        code = ord(code_or_char[0])
    else:
        code = int(code_or_char)

    if code in ASCII_CATEGORIES:
        return ASCII_CATEGORIES[code]
    elif 32 <= code <= 126:
        ch = chr(code)
        return {"symbol": ch, "name": f"Printable '{ch}'", "category": "printable", "safe": True, "desc": "Standard printable ASCII character."}
    else:
        return {"symbol": f"[0x{code:02X}]", "name": f"Extended/Unknown (0x{code:02X})", "category": "harmful_control", "safe": False, "desc": "Non-standard or extended control character."}

def inspect_payload(text):
    """
    Inspects a string payload character by character, identifying control characters,
    delimiters, and anomalies.
    """
    results = []
    has_harmful = False
    has_hidden = False

    for char in text:
        code = ord(char)
        info = get_char_info(code)
        if info["category"] != "printable":
            has_hidden = True
            if not info["safe"]:
                has_harmful = True

        results.append({
            "char": char,
            "ascii": code,
            "hex": f"{code:02X}",
            "symbol": info["symbol"],
            "name": info["name"],
            "category": info["category"],
            "is_safe": info["safe"],
            "description": info["desc"]
        })

    return {
        "characters": results,
        "has_hidden_controls": has_hidden,
        "has_harmful_controls": has_harmful
    }
