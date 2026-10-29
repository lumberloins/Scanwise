package main

import "strconv"

// Linux evdev keycodes -> W3C KeyboardEvent.code. For codes 1-88 these equal
// PC scancode set 1 make codes, so the Windows source reuses this table for
// non-extended scancodes.
var evdevCodes = map[int]string{
	1: "Escape", 2: "Digit1", 3: "Digit2", 4: "Digit3", 5: "Digit4", 6: "Digit5", 7: "Digit6",
	8: "Digit7", 9: "Digit8", 10: "Digit9", 11: "Digit0", 12: "Minus", 13: "Equal", 14: "Backspace",
	15: "Tab", 16: "KeyQ", 17: "KeyW", 18: "KeyE", 19: "KeyR", 20: "KeyT", 21: "KeyY", 22: "KeyU",
	23: "KeyI", 24: "KeyO", 25: "KeyP", 26: "BracketLeft", 27: "BracketRight", 28: "Enter",
	29: "ControlLeft", 30: "KeyA", 31: "KeyS", 32: "KeyD", 33: "KeyF", 34: "KeyG", 35: "KeyH",
	36: "KeyJ", 37: "KeyK", 38: "KeyL", 39: "Semicolon", 40: "Quote", 41: "Backquote",
	42: "ShiftLeft", 43: "Backslash", 44: "KeyZ", 45: "KeyX", 46: "KeyC", 47: "KeyV", 48: "KeyB",
	49: "KeyN", 50: "KeyM", 51: "Comma", 52: "Period", 53: "Slash", 54: "ShiftRight",
	55: "NumpadMultiply", 56: "AltLeft", 57: "Space", 58: "CapsLock", 59: "F1", 60: "F2", 61: "F3",
	62: "F4", 63: "F5", 64: "F6", 65: "F7", 66: "F8", 67: "F9", 68: "F10", 69: "NumLock",
	70: "ScrollLock", 71: "Numpad7", 72: "Numpad8", 73: "Numpad9", 74: "NumpadSubtract",
	75: "Numpad4", 76: "Numpad5", 77: "Numpad6", 78: "NumpadAdd", 79: "Numpad1", 80: "Numpad2",
	81: "Numpad3", 82: "Numpad0", 83: "NumpadDecimal", 86: "IntlBackslash", 87: "F11", 88: "F12",
	// Linux-only numbering for extended keys.
	96: "NumpadEnter", 97: "ControlRight", 98: "NumpadDivide", 99: "PrintScreen", 100: "AltRight",
	102: "Home", 103: "ArrowUp", 104: "PageUp", 105: "ArrowLeft", 106: "ArrowRight", 107: "End",
	108: "ArrowDown", 109: "PageDown", 110: "Insert", 111: "Delete", 117: "NumpadEqual", 119: "Pause",
	125: "MetaLeft", 126: "MetaRight", 127: "ContextMenu",
	183: "F13", 184: "F14", 185: "F15", 186: "F16", 187: "F17", 188: "F18", 189: "F19", 190: "F20",
	191: "F21", 192: "F22", 193: "F23", 194: "F24",
}

// codeForEvdev returns the W3C code, or "Unknown<n>" so nothing is silently dropped.
func codeForEvdev(keycode int) string {
	if c, ok := evdevCodes[keycode]; ok {
		return c
	}
	return unknownCode(keycode)
}

func unknownCode(n int) string {
	return "Unidentified" + strconv.Itoa(n)
}
