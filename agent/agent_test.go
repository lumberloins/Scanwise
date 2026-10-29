package main

import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func rawEvent(wordSize int, sec, usec int64, typ, code uint16, value int32) []byte {
	b := make([]byte, inputEventSize(wordSize))
	le := binary.LittleEndian
	if wordSize == 8 {
		le.PutUint64(b[0:], uint64(sec))
		le.PutUint64(b[8:], uint64(usec))
	} else {
		le.PutUint32(b[0:], uint32(sec))
		le.PutUint32(b[4:], uint32(usec))
	}
	t := 2 * wordSize
	le.PutUint16(b[t:], typ)
	le.PutUint16(b[t+2:], code)
	le.PutUint32(b[t+4:], uint32(value))
	return b
}

func TestParseAndTranslateEvdev(t *testing.T) {
	for _, ws := range []int{8, 4} {
		var buf []byte
		// A typical USB HID keyboard report: MSC_SCAN (HID usage), EV_KEY, SYN.
		buf = append(buf, rawEvent(ws, 10, 250, evMsc, mscScan, 0x700e0)...) // Left Control usage
		buf = append(buf, rawEvent(ws, 10, 250, evKey, 29, 1)...)
		buf = append(buf, rawEvent(ws, 10, 250, evSyn, 0, 0)...)
		buf = append(buf, rawEvent(ws, 10, 1250, evKey, 27, 1)...) // ] down (no MSC)
		buf = append(buf, rawEvent(ws, 10, 1300, evKey, 27, 2)...) // autorepeat
		buf = append(buf, rawEvent(ws, 10, 2000, evKey, 27, 0)...)
		raws := parseInputEvents(buf, ws)
		if len(raws) != 6 {
			t.Fatalf("ws=%d: parsed %d events", ws, len(raws))
		}
		tr := &evdevTranslator{device: "evdev:event3"}
		var got []KeyEvent
		for _, r := range raws {
			if ev, ok := tr.translate(r); ok {
				got = append(got, ev)
			}
		}
		if len(got) != 4 {
			t.Fatalf("ws=%d: got %d key events", ws, len(got))
		}
		if got[0].Code != "ControlLeft" || got[0].HIDUsage != 0x700e0 || got[0].Type != "down" {
			t.Errorf("ctrl event wrong: %+v", got[0])
		}
		if got[1].Code != "BracketRight" || got[1].HIDUsage != 0 {
			t.Errorf("] event wrong: %+v", got[1])
		}
		if !got[2].Repeat || got[3].Type != "up" {
			t.Errorf("repeat/up wrong: %+v %+v", got[2], got[3])
		}
		if got[1].T != 10001.25 {
			t.Errorf("timestamp ms = %v, want 10001.25", got[1].T)
		}
	}
}

func TestKeymapCoversScannerKeys(t *testing.T) {
	want := map[int]string{30: "KeyA", 28: "Enter", 15: "Tab", 27: "BracketRight", 42: "ShiftLeft", 82: "Numpad0", 109: "PageDown", 63: "F5"}
	for code, name := range want {
		if got := codeForEvdev(code); got != name {
			t.Errorf("code %d = %s, want %s", code, got, name)
		}
	}
	if got := codeForEvdev(999); got != "Unidentified999" {
		t.Errorf("unknown code = %s", got)
	}
}

func TestDetectScanner(t *testing.T) {
	if ok, _ := detectScanner("Generic USB Keyboard", "046d"); ok {
		t.Error("keyboard flagged as scanner")
	}
	if ok, why := detectScanner("Whatever", "05E0"); !ok || !strings.Contains(why, "Zebra") {
		t.Errorf("Zebra VID not detected: %v %s", ok, why)
	}
	if ok, _ := detectScanner("Honeywell Imaging & Mobility 1950", "0000"); !ok {
		t.Error("Honeywell name not detected")
	}
}

func writeCapture(t *testing.T) string {
	t.Helper()
	doc := `{"format":"scanwise-capture","version":1,"scans":[{"events":[
		{"t":100,"type":"down","code":"ControlLeft"},{"t":101,"type":"down","code":"BracketRight"},
		{"t":102,"type":"up","code":"BracketRight"},{"t":103,"type":"up","code":"ControlLeft"},
		{"t":104,"type":"down","code":"Enter"},{"t":105,"type":"up","code":"Enter"}]}]}`
	p := filepath.Join(t.TempDir(), "cap.json")
	if err := os.WriteFile(p, []byte(doc), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func newTestServer(t *testing.T) (*Server, *httptest.Server) {
	t.Helper()
	start := time.Now()
	rs, err := newReplaySource(writeCapture(t), 1, false, func() float64 { return float64(time.Since(start).Microseconds()) / 1000 })
	if err != nil {
		t.Fatal(err)
	}
	s := NewServer([]Source{rs}, []string{"http://localhost:5000"}, false, "test")
	ts := httptest.NewServer(s.Handler())
	t.Cleanup(ts.Close)
	return s, ts
}

func do(t *testing.T, method, url, origin, host, body string) *http.Response {
	t.Helper()
	req, _ := http.NewRequest(method, url, strings.NewReader(body))
	if origin != "" {
		req.Header.Set("Origin", origin)
	}
	if host != "" {
		req.Host = host
	}
	if method == http.MethodOptions {
		req.Header.Set("Access-Control-Request-Private-Network", "true")
	}
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	return res
}

func TestGuard(t *testing.T) {
	_, ts := newTestServer(t)
	cases := []struct {
		name, origin, host string
		want               int
	}{
		{"allowed origin", "http://localhost:5000", "", 200},
		{"no origin", "", "", 403},
		{"foreign origin", "http://evil.example", "", 403},
		{"dns rebinding host", "http://localhost:5000", "evil.example:47800", 403},
	}
	for _, c := range cases {
		res := do(t, "GET", ts.URL+"/status", c.origin, c.host, "")
		if res.StatusCode != c.want {
			t.Errorf("%s: status %d, want %d", c.name, res.StatusCode, c.want)
		}
		if c.want == 200 && res.Header.Get("Access-Control-Allow-Origin") != c.origin {
			t.Errorf("%s: missing CORS header", c.name)
		}
	}
	res := do(t, http.MethodOptions, ts.URL+"/select", "http://localhost:5000", "", "")
	if res.StatusCode != 204 || res.Header.Get("Access-Control-Allow-Private-Network") != "true" {
		t.Errorf("preflight: %d %v", res.StatusCode, res.Header)
	}
}

func TestNothingStreamsUntilSelected(t *testing.T) {
	s, ts := newTestServer(t)
	var st map[string]any
	json.NewDecoder(do(t, "GET", ts.URL+"/status", "http://localhost:5000", "", "").Body).Decode(&st)
	if st["selected"] != nil {
		t.Fatalf("device selected at startup: %v", st["selected"])
	}
	if s.sel != nil {
		t.Fatal("selection should be nil")
	}
	res := do(t, "POST", ts.URL+"/select", "http://localhost:5000", "", `{"id":"evdev:../../etc/passwd"}`)
	if res.StatusCode != 400 {
		t.Errorf("bad id accepted: %d", res.StatusCode)
	}
}

func TestReplayStreamsOverSSE(t *testing.T) {
	_, ts := newTestServer(t)
	req, _ := http.NewRequest("GET", ts.URL+"/events", nil)
	req.Header.Set("Origin", "http://localhost:5000")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if ct := res.Header.Get("Content-Type"); ct != "text/event-stream" {
		t.Fatalf("content-type %q", ct)
	}
	sel := do(t, "POST", ts.URL+"/select", "http://localhost:5000", "", `{"id":"replay:0"}`)
	if sel.StatusCode != 200 {
		t.Fatalf("select: %d", sel.StatusCode)
	}

	sc := bufio.NewScanner(res.Body)
	var codes []string
	event := ""
	deadline := time.After(5 * time.Second)
	lines := make(chan string)
	go func() {
		for sc.Scan() {
			lines <- sc.Text()
		}
		close(lines)
	}()
	for len(codes) < 6 {
		select {
		case <-deadline:
			t.Fatalf("timed out; got %v", codes)
		case line, ok := <-lines:
			if !ok {
				t.Fatalf("stream closed; got %v", codes)
			}
			if strings.HasPrefix(line, "event: ") {
				event = strings.TrimPrefix(line, "event: ")
			} else if strings.HasPrefix(line, "data: ") && event == "key" {
				var ev KeyEvent
				if err := json.Unmarshal([]byte(strings.TrimPrefix(line, "data: ")), &ev); err != nil {
					t.Fatal(err)
				}
				if ev.Src != "replay" {
					t.Errorf("src = %s", ev.Src)
				}
				codes = append(codes, ev.Type+":"+ev.Code)
			}
		}
	}
	want := "down:ControlLeft down:BracketRight up:BracketRight up:ControlLeft down:Enter up:Enter"
	if strings.Join(codes, " ") != want {
		t.Errorf("got %v", codes)
	}
}

func TestScancodeMap(t *testing.T) {
	cases := []struct {
		make   uint16
		e0, e1 bool
		want   string
		ok     bool
	}{
		{0x1E, false, false, "KeyA", true},
		{0x1C, false, false, "Enter", true},
		{0x1C, true, false, "NumpadEnter", true},
		{0x1D, true, false, "ControlRight", true},
		{0x52, false, false, "Numpad0", true}, // Alt+numpad digits arrive un-extended
		{0x52, true, false, "Insert", true},
		{0x51, true, false, "PageDown", true},
		{0x64, false, false, "F13", true},
		{0x2A, true, false, "", false}, // fake shift
		{0x1D, false, true, "Pause", true},
		{0x7F, false, false, "Unidentified127", true},
	}
	for _, c := range cases {
		got, ok := codeForScancode(c.make, c.e0, c.e1)
		if got != c.want || ok != c.ok {
			t.Errorf("scancode %#x e0=%v e1=%v = %q,%v want %q,%v", c.make, c.e0, c.e1, got, ok, c.want, c.ok)
		}
	}
}
