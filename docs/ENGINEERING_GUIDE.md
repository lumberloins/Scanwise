# ScanWise Engineering Guide

Engineering Mode (`/engineering`) answers *exactly what the scanner injected, and how*, down to each key
event. With the optional native agent it also proves whether characters were lost between the device
and the page.

## 1. How capture works (why this is hard in wedge mode)

A HID keyboard-wedge scanner sends **key presses, not bytes**. Every character, including control
characters, has to be rebuilt from physical keys plus modifiers. Depending on the scanner's
control-character setting, GS (0x1D) arrives as:

| Scanner setting | Key events | ScanWise `Produced by` |
|---|---|---|
| Ctrl-ASCII emulation | `Ctrl` + `]` | Ctrl emulation |
| Alt / keypad emulation | `Alt` held, `Numpad0 0 2 9`, `Alt` released | Alt+numpad |
| Function-key mapping | an F-key or nothing | function key (token) |

ScanWise records raw `keydown`/`keyup` events (physical `code`, host `key`, modifiers, timestamps) and
decodes them server-side in `scanwise/capture/decoder.py` against the US layout (the scanner's factory
keyboard-country setting). Browser and agent captures go through the same decoder.

Decoder rules: Ctrl+A..Z → 0x01..0x1A; Ctrl+`[` `\` `]` → ESC FS GS; Ctrl+Shift+6 → RS; Ctrl+Shift+- → US;
Ctrl+Shift+2 / Ctrl+Space → NUL; Alt+numpad → the digit value (leading 0 = Windows-1252, else CP437 above
127); Enter/Tab/Backspace/Escape/Delete → CR/TAB/BS/ESC/DEL; F-keys, arrows, paging keys → non-byte
*tokens*; modifier keys never become characters.

## 2. Browser-only limits

| Limit | Effect | Mitigation |
|---|---|---|
| Browser shortcuts | In Ctrl-ASCII mode, ETB = Ctrl+W (close tab), DC4 = Ctrl+T, SO = Ctrl+N | **Keyboard lock** button (Chromium: fullscreen + `navigator.keyboard.lock()`), or use the agent. A mid-scan Ctrl+W hits a "Leave site?" prompt, and focus loss marks the scan *interrupted*. |
| No device identity | The page can't tell the scanner from the keyboard | Use the agent |
| Timer precision | `event.timeStamp` may be coarsened by the browser | Use the agent (kernel timestamps on Linux) |
| Alt+numpad on Linux/macOS | The OS doesn't compose Alt codes; ScanWise still decodes the key events | n/a (this is a diagnostic advantage) |

## 3. Native agent (`agent/`)

Single static Go binary, stdlib only. Reads the OS input layer, streams canonical key events over
Server-Sent Events on `127.0.0.1:47800`.

### Build

```bash
agent/build.sh          # gofmt check, vet (linux+windows), tests, binaries into agent/dist/
```

Produces `scanwise-agent-linux-amd64`, `-linux-arm64`, `-windows-amd64.exe`.

### Run

```bash
scanwise-agent -list                                    # keyboards; * = looks like a scanner
scanwise-agent                                          # serve; page origin http://localhost:5000 allowed
scanwise-agent -allow-origin http://scanwise.example:5000
scanwise-agent -device evdev:event7 -grab               # preselect + exclusive grab (Linux)
scanwise-agent -no-native -replay capture.json -replay-loop   # demo / test without hardware
```

| Platform | Source | Notes |
|---|---|---|
| Linux | evdev (`/dev/input/event*`) | Needs read access: `sudo usermod -aG input $USER`, then log in again. `-grab` (EVIOCGRAB) stops scans from also typing into other apps; it's released on exit. HID usage (`MSC_SCAN`) is attached to each event. Timestamps are kernel monotonic, µs resolution. |
| Windows | Raw Input (`WM_INPUT`, `RIDEV_INPUTSINK`) | No admin needed. **No grab**: keys still reach the focused app. Device names come from HID strings; VID/PID from the device path. **Not yet tested on Windows hardware**: verify `-list` and a live scan first. |
| macOS | none yet | Replay only. |

### Security model

The agent can read any keyboard, so it:
- listens on loopback only (refuses other `-listen` addresses);
- requires an allowed `Origin` on every request (blocks other web pages). Command-line clients need
  `-allow-no-origin`;
- requires a loopback `Host` header (blocks DNS rebinding);
- streams **nothing** until a device is explicitly selected in the UI (or with `-device`).

If the UI is served from a different host than the agent, Chromium may ask for local-network access
permission or block the connection from a non-HTTPS page. The simplest setup for engineers is running
ScanWise locally (`http://localhost:5000`).

### API

| Endpoint | |
|---|---|
| `GET /status` | version, platform, sources, selected device, grab, connected clients, dropped events |
| `GET /devices` | keyboard-class devices: id, name, path, phys, bus, vendor/product id, likely_scanner, can_grab |
| `POST /select {"id","grab"}` | open a device (closes the previous one) |
| `POST /release` | stop streaming |
| `GET /events` | SSE: `event: key` (canonical key event + `scancode`, `hid_usage`, `device`), `event: status` |

## 4. Engineering Mode tour

- **Source**: *Browser*, *Native agent*, or **Both**. Both pairs the agent's scan (ground truth) with what
  the browser received within 1 s. If the browser got nothing, or a different stream, that becomes the
  headline finding and the **Compare** tab shows the exact lost/extra characters. Leave **Grab off** in
  Both mode (a grab hides the keys from the browser).
- **Scan gap**: a scan ends this long after a suffix key (Enter, Tab, LF). With no suffix key it ends
  after 1000 ms (or the gap, if larger), so a scanner that pauses mid-barcode isn't split into pieces.
- **Byte stream**: click any character to highlight it in every panel.
- **Characters**: one row per character or token: hex, decimal, name, category, region
  (prefix/aim/data/suffix), how it was produced, the key combo, time, Δ from the previous character, dwell,
  what the host layout produced, and flags (layout mismatch, Caps Lock, repeat, incomplete Alt sequence,
  code page).
- **Key events**: every raw down/up event.
- **Hex dump**: offset / hex / ASCII with badges.
- **Timing**: inter-character delay chart with spike threshold, statistics, histogram.
- **Framing & data**: prefix/suffix hex, profile checks, AIM, ISO/IEC 15434 envelope, control-char
  method counts, layout mismatches, GS1 element table with check-digit/date/length checks.
- **Findings**: every finding with evidence, in both engineering and tech wording.
- **Compare**: agent-vs-browser for the current scan, plus any two history scans.
- **Session history**: last 50 scans, **in memory only**. Nothing goes to disk, and it's gone on reload. Older
  versions saved history in `localStorage`; that copy is deleted when the page loads.
- **Export** is **redacted by default**: every data character becomes `X` / `x` / `0`, at the key-event level.
  Kept: control characters, key order, modifiers, timing, how each character was produced, AIM IDs, GS1 AI
  codes and separators, and a prefix/suffix confirmed by an EMR profile. Punctuation and spaces are kept.
  Check digits and dates won't validate in a redacted file. **With data…** exports the full contents and
  needs a second click; only use it on barcodes with no patient information. Files are named
  `scanwise-redacted-*.json` or `scanwise-FULL-DATA-*.json`. Either way the export is a replay file:

```json
{"format": "scanwise-capture", "version": 1, "scans": [{"events": [...], "meta": {...}, "source": {...}}]}
```

  Import it here to re-analyse, or play it through the agent with `-replay`.

## 5. EMR profiles

`scanwise/profiles/emr_profiles.json` holds `expected_prefix` / `expected_suffix` per profile. These
are **site configuration**: confirm them against your EMR team's scanner programming sheets and edit as
needed. A profile with `"pass_through": true` accepts any framing and is excluded from auto-detection.

| Key | Meaning |
|---|---|
| `expected_prefix` | Text the EMR expects before the data |
| `prefix_case_insensitive` | Match the prefix in any letter case |
| `expected_suffix` | Preferred suffix (`""` = none) |
| `accepted_suffixes` | Every suffix the EMR accepts; include `""` if none is required (then a missing suffix is not a fault) |
| `optional_terminators` | `expected_suffix` may be followed by any mix of these characters, or none |

**Epic** (confirmed by the team from a real DENSO scan): the barcode is wrapped in backslashes,
`\<data>\` (written `\data\` in Epic's documentation). So prefix `\`, suffix `\`, and then optionally
any mix of CR, LF and Tab, depending on the workflow. None of those terminators is a fault, and Tech Mode
says which one is sent: "Epic EMR (Hyperspace / Rover): "\" before the data, "\" after it, no Enter or
Tab" or "..., then CR (Enter)". The AIM ID may come before or after the opening `\`. The closing `\` is
only removed when the opening one was found, so other data that ends in `\` is left alone. The captured
scan is kept as a regression test (`tests/fixtures/denso_epic_gs1.json`).

If the scanner sends a prefix no profile knows, but a valid AIM ID (e.g. `]d2`) follows it, the leading
text is still treated as a prefix (`prefix_unrecognized: true`) and the barcode is parsed normally.

## 6. Tests

```bash
mise exec python -- python -m pytest -q      # decoder, analysis, API
(cd agent && go test -race ./...)            # agent
node tools/e2e_cdp.mjs                       # headless Chromium, real key events; suites: tech engineering agent harness
SCANWISE_SHOTS=/some/dir node tools/e2e_cdp.mjs   # also save screenshots
```

`tools/cdp.mjs` drives Chromium over the DevTools Protocol with only Node built-ins. Its `Scanner` class
types like a HID scanner (Shift per capital, `ctrl('BracketRight')`, `alt('0029')`).
`scanwise/static/dev/capture-harness.html` is a bare capture page for debugging.
