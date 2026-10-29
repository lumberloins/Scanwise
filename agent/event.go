package main

import "time"

var agentStart = time.Now()

// nowMs is the agent's monotonic clock in milliseconds (µs resolution).
func nowMs() float64 { return float64(time.Since(agentStart).Microseconds()) / 1000 }

// KeyEvent is the canonical key event (BUILD_PLAN.md section 3), as streamed to the browser.
type KeyEvent struct {
	T        float64 `json:"t"`                   // ms, monotonic
	Type     string  `json:"type"`                // "down" | "up"
	Code     string  `json:"code"`                // W3C KeyboardEvent.code
	Repeat   bool    `json:"repeat,omitempty"`    // kernel autorepeat
	Src      string  `json:"src"`                 // "agent" | "replay"
	Device   string  `json:"device,omitempty"`    // device id
	Scancode int     `json:"scancode,omitempty"`  // raw OS key code (evdev keycode / PC scancode)
	HIDUsage uint32  `json:"hid_usage,omitempty"` // HID usage from MSC_SCAN when the kernel reports it
}

// Device describes a keyboard-class input device the agent can stream.
type Device struct {
	ID            string `json:"id"`
	Name          string `json:"name"`
	Path          string `json:"path,omitempty"`
	Phys          string `json:"phys,omitempty"`
	Bus           string `json:"bus,omitempty"`
	VendorID      string `json:"vendor_id,omitempty"`
	ProductID     string `json:"product_id,omitempty"`
	LikelyScanner bool   `json:"likely_scanner"`
	ScannerReason string `json:"scanner_reason,omitempty"`
	CanGrab       bool   `json:"can_grab"`
	Kind          string `json:"kind"` // "evdev" | "rawinput" | "replay"
	Error         string `json:"error,omitempty"`
}

// Source enumerates devices and opens one for streaming.
type Source interface {
	Kind() string
	Devices() ([]Device, error)
	// Open starts streaming key events from device id into out until the returned stop func is called.
	Open(id string, grab bool, out chan<- KeyEvent) (stop func(), err error)
}
