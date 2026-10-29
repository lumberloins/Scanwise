package main

// PC scancode set 1 (as reported by Windows Raw Input MakeCode + RI_KEY_E0)
// -> W3C code. Non-extended codes 0x01-0x58 equal Linux evdev keycodes.
var scancodeExtended = map[uint16]string{
	0x1C: "NumpadEnter", 0x1D: "ControlRight", 0x35: "NumpadDivide", 0x37: "PrintScreen",
	0x38: "AltRight", 0x47: "Home", 0x48: "ArrowUp", 0x49: "PageUp", 0x4B: "ArrowLeft",
	0x4D: "ArrowRight", 0x4F: "End", 0x50: "ArrowDown", 0x51: "PageDown", 0x52: "Insert",
	0x53: "Delete", 0x5B: "MetaLeft", 0x5C: "MetaRight", 0x5D: "ContextMenu",
}

var scancodeHigh = map[uint16]string{
	0x59: "NumpadEqual", 0x64: "F13", 0x65: "F14", 0x66: "F15", 0x67: "F16", 0x68: "F17",
	0x69: "F18", 0x6A: "F19", 0x6B: "F20", 0x6C: "F21", 0x6D: "F22", 0x6E: "F23", 0x76: "F24",
}

// codeForScancode maps a set-1 make code. ok=false means "ignore this event"
// (Windows' fake shift events E0 2A / E0 36 that wrap some extended keys).
func codeForScancode(make uint16, e0, e1 bool) (code string, ok bool) {
	switch {
	case e1:
		return "Pause", true
	case e0 && (make == 0x2A || make == 0x36):
		return "", false
	case e0:
		if c, found := scancodeExtended[make]; found {
			return c, true
		}
		return unknownCode(0xE000 | int(make)), true
	case make <= 0x58:
		return codeForEvdev(int(make)), true
	default:
		if c, found := scancodeHigh[make]; found {
			return c, true
		}
		return unknownCode(int(make)), true
	}
}
