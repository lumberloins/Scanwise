#!/usr/bin/env python3
"""
Dump raw Linux evdev key events from one input device: what the scanner sent,
before the compositor, input method or browser touched it.

    sudo python3 tools/evdump.py /dev/input/by-id/<scanner>-event-kbd [seconds] [out.jsonl]

Scan during the window (default 10 s). Writes one JSON object per key event
(t ms, type down/up/repeat, Linux key code and name, MSC_SCAN usage if sent).
"""
import json
import os
import select
import struct
import sys
import time

EV_KEY, EV_MSC, MSC_SCAN = 0x01, 0x04, 0x04
FMT = "llHHi"   # struct input_event on 64-bit: timeval, type, code, value
SIZE = struct.calcsize(FMT)

NAMES = {1: "ESC", 14: "BACKSPACE", 15: "TAB", 28: "ENTER", 29: "LEFTCTRL", 42: "LEFTSHIFT", 54: "RIGHTSHIFT",
         56: "LEFTALT", 100: "RIGHTALT", 97: "RIGHTCTRL", 57: "SPACE", 58: "CAPSLOCK", 69: "NUMLOCK", 96: "KPENTER",
         12: "MINUS", 13: "EQUAL", 26: "LEFTBRACE", 27: "RIGHTBRACE", 39: "SEMICOLON", 40: "APOSTROPHE",
         41: "GRAVE", 43: "BACKSLASH", 51: "COMMA", 52: "DOT", 53: "SLASH", 55: "KPASTERISK", 74: "KPMINUS",
         78: "KPPLUS", 83: "KPDOT", 98: "KPSLASH"}
for i, d in enumerate("1234567890"):
    NAMES[2 + i] = d
for row, start in (("QWERTYUIOP", 16), ("ASDFGHJKL", 30), ("ZXCVBNM", 44)):
    for i, ch in enumerate(row):
        NAMES[start + i] = ch
for code, d in zip((82, 79, 80, 81, 75, 76, 77, 71, 72, 73), "0123456789"):
    NAMES[code] = f"KP{d}"
for i in range(10):
    NAMES[59 + i] = f"F{i + 1}"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    out_path = sys.argv[3] if len(sys.argv) > 3 else "evdump.jsonl"
    fd = os.open(path, os.O_RDONLY)
    print(f"Reading {path} for {seconds:g} s. Scan now.", file=sys.stderr)
    events, scan, t0 = [], None, None
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        if not select.select([fd], [], [], left)[0]:
            continue
        sec, usec, typ, code, value = struct.unpack(FMT, os.read(fd, SIZE))
        t = sec * 1000 + usec / 1000
        if typ == EV_MSC and code == MSC_SCAN:
            scan = value
        elif typ == EV_KEY:
            t0 = t if t0 is None else t0
            events.append({"t": round(t - t0, 3), "type": {0: "up", 1: "down", 2: "repeat"}.get(value, value),
                           "code": code, "name": NAMES.get(code, f"KEY_{code}"),
                           "scan": hex(scan) if scan is not None else None})
            scan = None
    os.close(fd)
    with open(out_path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    os.chmod(out_path, 0o644)
    downs = [e["name"] for e in events if e["type"] == "down"]
    print(f"{len(events)} events -> {out_path}\nkeys down: {' '.join(downs)}", file=sys.stderr)


if __name__ == "__main__":
    main()
