package main

import (
	"encoding/binary"
)

// Linux input event constants (linux/input-event-codes.h).
const (
	evSyn   = 0x00
	evKey   = 0x01
	evMsc   = 0x04
	mscScan = 0x04
)

type rawInputEvent struct {
	Sec, Usec int64
	Type      uint16
	Code      uint16
	Value     int32
}

// inputEventSize is sizeof(struct input_event): 24 on 64-bit, 16 on 32-bit.
func inputEventSize(wordSize int) int { return 2*wordSize + 8 }

// parseInputEvents decodes a buffer of struct input_event (little-endian hosts).
func parseInputEvents(buf []byte, wordSize int) []rawInputEvent {
	size := inputEventSize(wordSize)
	out := make([]rawInputEvent, 0, len(buf)/size)
	le := binary.LittleEndian
	for off := 0; off+size <= len(buf); off += size {
		b := buf[off : off+size]
		var ev rawInputEvent
		if wordSize == 8 {
			ev.Sec = int64(le.Uint64(b[0:8]))
			ev.Usec = int64(le.Uint64(b[8:16]))
		} else {
			ev.Sec = int64(int32(le.Uint32(b[0:4])))
			ev.Usec = int64(int32(le.Uint32(b[4:8])))
		}
		t := 2 * wordSize
		ev.Type = le.Uint16(b[t : t+2])
		ev.Code = le.Uint16(b[t+2 : t+4])
		ev.Value = int32(le.Uint32(b[t+4 : t+8]))
		out = append(out, ev)
	}
	return out
}

// evdevTranslator turns raw kernel events into canonical key events. It holds
// the last MSC_SCAN value so the HID usage can be attached to the key event
// that follows it in the same report.
type evdevTranslator struct {
	device      string
	pendingScan uint32
}

func (tr *evdevTranslator) translate(ev rawInputEvent) (KeyEvent, bool) {
	switch ev.Type {
	case evMsc:
		if ev.Code == mscScan {
			tr.pendingScan = uint32(ev.Value)
		}
		return KeyEvent{}, false
	case evSyn:
		tr.pendingScan = 0
		return KeyEvent{}, false
	case evKey:
		if ev.Value < 0 || ev.Value > 2 {
			return KeyEvent{}, false
		}
		k := KeyEvent{
			T:        float64(ev.Sec)*1000 + float64(ev.Usec)/1000,
			Type:     "down",
			Code:     codeForEvdev(int(ev.Code)),
			Repeat:   ev.Value == 2,
			Src:      "agent",
			Device:   tr.device,
			Scancode: int(ev.Code),
			HIDUsage: tr.pendingScan,
		}
		if ev.Value == 0 {
			k.Type = "up"
		}
		tr.pendingScan = 0
		return k, true
	}
	return KeyEvent{}, false
}
