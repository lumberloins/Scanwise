"""
US keyboard map keyed by W3C UI Events KeyboardEvent.code (physical key).

HID barcode scanners send physical key positions (HID usages). The scanner's
"keyboard country" setting decides which positions it presses for each
character; the factory default is US. Decoding against the US table recovers
what the scanner intended, independent of the host's keyboard layout.
"""

# code -> (unshifted, shifted)
PRINTABLE = {
    "Backquote": ("`", "~"),
    "Digit1": ("1", "!"), "Digit2": ("2", "@"), "Digit3": ("3", "#"),
    "Digit4": ("4", "$"), "Digit5": ("5", "%"), "Digit6": ("6", "^"),
    "Digit7": ("7", "&"), "Digit8": ("8", "*"), "Digit9": ("9", "("),
    "Digit0": ("0", ")"),
    "Minus": ("-", "_"), "Equal": ("=", "+"),
    "BracketLeft": ("[", "{"), "BracketRight": ("]", "}"), "Backslash": ("\\", "|"),
    "Semicolon": (";", ":"), "Quote": ("'", '"'),
    "Comma": (",", "<"), "Period": (".", ">"), "Slash": ("/", "?"),
    "Space": (" ", " "),
    "IntlBackslash": ("\\", "|"),
    "NumpadDivide": ("/", "/"), "NumpadMultiply": ("*", "*"),
    "NumpadSubtract": ("-", "-"), "NumpadAdd": ("+", "+"),
    "NumpadDecimal": (".", "."),
}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    PRINTABLE[f"Key{_c}"] = (_c.lower(), _c)
for _d in "0123456789":
    PRINTABLE[f"Numpad{_d}"] = (_d, _d)

NUMPAD_DIGITS = {f"Numpad{d}": d for d in "0123456789"}

# Keys that map directly to a single control byte.
NAMED_KEYS = {
    "Enter": 0x0D,
    "NumpadEnter": 0x0D,
    "Tab": 0x09,
    "Backspace": 0x08,
    "Escape": 0x1B,
    "Delete": 0x7F,
}

# Keys that produce no byte. They are kept as visible tokens because some
# scanners map control characters to them ("function key mapping").
FUNCTION_KEYS = {f"F{n}" for n in range(1, 25)} | {
    "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    "PageUp", "PageDown", "Home", "End", "Insert",
    "PrintScreen", "ScrollLock", "Pause", "ContextMenu", "NumLock", "CapsLock",
}

MODIFIERS = {
    "ShiftLeft": "shift", "ShiftRight": "shift",
    "ControlLeft": "ctrl", "ControlRight": "ctrl",
    "AltLeft": "alt", "AltRight": "alt",
    "MetaLeft": "meta", "MetaRight": "meta", "OSLeft": "meta", "OSRight": "meta",
}

# Ctrl + key -> control byte. Ctrl+letter is handled arithmetically.
CTRL_SYMBOLS = {
    # (code, shifted) -> byte
    ("BracketLeft", False): 0x1B,   # Ctrl+[  ESC
    ("Backslash", False): 0x1C,     # Ctrl+\  FS
    ("BracketRight", False): 0x1D,  # Ctrl+]  GS
    ("Digit6", True): 0x1E,         # Ctrl+^  RS
    ("Digit6", False): 0x1E,        # many hosts accept Ctrl+6 for RS
    ("Minus", True): 0x1F,          # Ctrl+_  US
    ("Minus", False): 0x1F,         # Ctrl+-  US on many hosts
    ("Digit2", True): 0x00,         # Ctrl+@  NUL
    ("Digit2", False): 0x00,        # Ctrl+2  NUL
    ("Space", False): 0x00,         # Ctrl+Space NUL
    ("Space", True): 0x00,
    ("Slash", True): 0x7F,          # Ctrl+?  DEL (traditional terminal mapping)
}
