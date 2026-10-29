"""
Character catalogue for scanner output.

Every code point a scanner can inject gets a short badge abbreviation, a full
name, a category, and a severity, so the UI can render *all* non-printable
characters (every C0 control, DEL, C1 controls, and invisible Unicode).

Categories:
  printable      0x20-0x7E
  gs1_delimiter  GS (0x1D), the FNC1 separator in GS1 data
  terminator     CR, LF, TAB, the usual scanner suffixes
  separator      FS, RS, US, EOT, legitimate in ISO/IEC 15434 envelopes ([)>RS06GS...RSEOT)
  framing        STX, ETX, used as scanner preamble/postamble
  control        every other C0 control and DEL
  c1_control     0x80-0x9F
  invisible      NBSP, zero-width chars, BOM, soft hyphen
  replacement    U+FFFD, the decoder hit undecodable data
  extended       any other non-ASCII printable character

Severity: ok | info | warn | bad. "safe" means ok or info.
"""
import unicodedata

C0 = [
    ("NUL", "Null"), ("SOH", "Start of Heading"), ("STX", "Start of Text"),
    ("ETX", "End of Text"), ("EOT", "End of Transmission"), ("ENQ", "Enquiry"),
    ("ACK", "Acknowledge"), ("BEL", "Bell"), ("BS", "Backspace"),
    ("TAB", "Horizontal Tab"), ("LF", "Line Feed"), ("VT", "Vertical Tab"),
    ("FF", "Form Feed"), ("CR", "Carriage Return"), ("SO", "Shift Out"),
    ("SI", "Shift In"), ("DLE", "Data Link Escape"), ("DC1", "Device Control 1 (XON)"),
    ("DC2", "Device Control 2"), ("DC3", "Device Control 3 (XOFF)"), ("DC4", "Device Control 4"),
    ("NAK", "Negative Acknowledge"), ("SYN", "Synchronous Idle"), ("ETB", "End of Transmission Block"),
    ("CAN", "Cancel"), ("EM", "End of Medium"), ("SUB", "Substitute"),
    ("ESC", "Escape"), ("FS", "File Separator"), ("GS", "Group Separator (GS1 FNC1)"),
    ("RS", "Record Separator"), ("US", "Unit Separator"),
]

C1_ABBR = [
    "PAD", "HOP", "BPH", "NBH", "IND", "NEL", "SSA", "ESA", "HTS", "HTJ", "VTS", "PLD",
    "PLU", "RI", "SS2", "SS3", "DCS", "PU1", "PU2", "STS", "CCH", "MW", "SPA", "EPA",
    "SOS", "SGCI", "SCI", "CSI", "ST", "OSC", "PM", "APC",
]

DESCRIPTIONS = {
    0x00: "Rogue zero byte. Truncates strings in many EMR fields and terminal buffers.",
    0x02: "Common scanner preamble. EMR text fields usually reject or ignore it.",
    0x03: "Common scanner postamble. EMR text fields usually reject or ignore it.",
    0x04: "Ends an ISO/IEC 15434 message envelope. Fine inside [)>...EOT, suspicious elsewhere.",
    0x07: "Bell. Beeps the host and is never valid barcode data.",
    0x08: "Backspace. Deletes the previous character in the target field.",
    0x09: "Tab suffix. Moves focus to the next field (used by some EMR workflows).",
    0x0A: "Line Feed suffix. Part of CR+LF on many scanners.",
    0x0B: "Vertical Tab. Not valid barcode data.",
    0x0C: "Form Feed. Not valid barcode data; often a mis-programmed suffix.",
    0x0D: "Carriage Return, i.e. the Enter key. The most common scanner suffix.",
    0x0E: "Shift Out. As Ctrl+N it opens a new browser window in wedge mode.",
    0x14: "Device Control 4. As Ctrl+T it opens a new browser tab in wedge mode.",
    0x17: "End of Transmission Block. As Ctrl+W it closes the browser tab in wedge mode.",
    0x1B: "Escape. Cancels dialogs or opens menus in EMR applications.",
    0x1C: "File Separator. Used by some HIBC / ISO 15434 formats.",
    0x1D: "Group Separator: the transmitted form of GS1 FNC1. Required between variable-length AIs.",
    0x1E: "Record Separator. Used in ISO/IEC 15434 envelopes ([)>RS06...).",
    0x1F: "Unit Separator.",
    0x7F: "Delete.",
    0xA0: "Non-breaking space. Looks like a space but won't match one.",
    0xAD: "Soft hyphen. Invisible in most fields.",
    0x200B: "Zero-width space. Invisible.",
    0x200C: "Zero-width non-joiner. Invisible.",
    0x200D: "Zero-width joiner. Invisible.",
    0xFEFF: "Byte-order mark / zero-width no-break space. Invisible.",
    0xFFFD: "Unicode replacement character: data was mangled before it reached the page.",
}

INVISIBLE = {0xA0: "NBSP", 0xAD: "SHY", 0x200B: "ZWSP", 0x200C: "ZWNJ", 0x200D: "ZWJ",
             0x2060: "WJ", 0xFEFF: "BOM"}

_CATEGORY_SEVERITY = {
    "printable": "ok", "gs1_delimiter": "ok", "terminator": "info", "separator": "info",
    "extended": "info", "framing": "warn", "invisible": "warn",
    "control": "bad", "c1_control": "bad", "replacement": "bad",
}


def _category(cp):
    if 0x20 <= cp <= 0x7E:
        return "printable"
    if cp == 0x1D:
        return "gs1_delimiter"
    if cp in (0x09, 0x0A, 0x0D):
        return "terminator"
    if cp in (0x04, 0x1C, 0x1E, 0x1F):
        return "separator"
    if cp in (0x02, 0x03):
        return "framing"
    if cp < 0x20 or cp == 0x7F:
        return "control"
    if 0x80 <= cp <= 0x9F:
        return "c1_control"
    if cp == 0xFFFD:
        return "replacement"
    if cp in INVISIBLE or unicodedata.category(chr(cp)) in ("Cf", "Zs", "Cc"):
        return "invisible"
    return "extended"


def describe_char(cp):
    """Return badge/name/category/severity info for one code point."""
    if isinstance(cp, str):
        cp = ord(cp)
    cat = _category(cp)
    if cp < 0x20:
        abbr, name = C0[cp]
    elif cp == 0x7F:
        abbr, name = "DEL", "Delete"
    elif 0x80 <= cp <= 0x9F:
        abbr, name = C1_ABBR[cp - 0x80], f"C1 control 0x{cp:02X}"
    elif cat == "printable":
        abbr, name = None, "Space" if cp == 0x20 else f"'{chr(cp)}'"
    elif cp in INVISIBLE:
        abbr, name = INVISIBLE[cp], unicodedata.name(chr(cp), f"U+{cp:04X}").title()
    elif cat == "replacement":
        abbr, name = "U+FFFD", "Replacement Character"
    elif cat == "invisible":
        abbr, name = f"U+{cp:04X}", unicodedata.name(chr(cp), f"U+{cp:04X}").title()
    else:
        abbr, name = None, unicodedata.name(chr(cp), f"U+{cp:04X}").title()
    severity = _CATEGORY_SEVERITY[cat]
    return {
        "abbr": abbr,
        "symbol": f"[{abbr}]" if abbr else chr(cp),
        "name": name,
        "category": cat,
        "severity": severity,
        "safe": severity in ("ok", "info"),
        "visible": cat in ("printable", "extended"),
        "desc": DESCRIPTIONS.get(cp, ""),
        "code": cp,
        "hex": f"{cp:02X}" if cp <= 0xFF else f"U+{cp:04X}",
    }


def get_char_info(code_or_char):
    """Backward-compatible alias of describe_char (accepts int or str)."""
    if isinstance(code_or_char, str):
        if not code_or_char:
            return None
        return describe_char(code_or_char[0])
    return describe_char(int(code_or_char))


def visualize(text):
    """Plain-text rendering with every non-visible character as <ABBR>. Never use as HTML."""
    out = []
    for ch in text:
        info = describe_char(ch)
        out.append(ch if info["visible"] else f"<{info['abbr']}>")
    return "".join(out)


def inspect_payload(text):
    """Per-character inspection of a string."""
    results = []
    has_hidden = has_harmful = False
    for i, ch in enumerate(text):
        info = describe_char(ch)
        if not info["visible"]:
            has_hidden = True
        if not info["safe"]:
            has_harmful = True
        results.append({
            "index": i,
            "char": ch,
            "ascii": info["code"],
            "hex": info["hex"],
            "symbol": info["symbol"],
            "abbr": info["abbr"],
            "name": info["name"],
            "category": info["category"],
            "severity": info["severity"],
            "is_safe": info["safe"],
            "description": info["desc"],
        })
    return {"characters": results, "has_hidden_controls": has_hidden, "has_harmful_controls": has_harmful}
