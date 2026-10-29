# ScanWise Build Plan: Hybrid Capture (Tech Mode + Engineering Mode)

Living document. Each phase is sized to finish in one working session. After a
phase completes, its **Status** is updated and a short entry is added to the
**Phase Log** at the bottom (what was built, how it was verified, known gaps).

---

## 1. Goals

| Audience | Page | Needs |
|---|---|---|
| Onsite techs | `/` (Tech Mode) | Scan one barcode and learn **how the scanner is configured**: prefix, suffix (Tab / CR / LF / CR+LF / none), AIM IDs on/off, and whether it matches a known profile (Epic, Cerner, Meditech, ...). Plain language, no hex. |
| Engineering team | `/engineering` | Full forensic view: every key event (down/up, physical code, modifiers, timing), every reconstructed byte including **all** of 0x00-0x1F and 0x7F, how each control character was produced (Enter key vs Ctrl+M vs Alt+0013), hex dump, timing chart, all findings (not just one verdict), history, compare, export. Optional native agent for ground-truth capture. |

## 2. Core design principle

In USB HID keyboard-wedge mode **the scanner sends key presses, not bytes**.
Each byte has to be rebuilt from key presses plus modifier state. So:

1. **Capture key events, not characters.** Both capture sources (browser, native
   agent) emit the same *canonical key event* (Section 3).
2. **Decode explicitly, in one place.** `scanwise/capture/decoder.py` turns key
   events into *units* (bytes or non-byte key tokens) and records **how** each one
   was produced. The decoder is unit-tested.
3. **Never pass pre-rendered strings to the UI.** The API returns structured
   per-character data. The UI builds badges with `textContent` only (no HTML
   injection, so `<GS>` can never be swallowed as a tag again).

```
 Scanner (HID keyboard)
     |                                   (optional, engineering)
     |-- OS keyboard stack --> Browser keydown/keyup ----+
     |                                                   |   canonical key events
     +-- evdev / Raw Input --> scanwise-agent (Go) --SSE-+--> POST /api/analyze
                                                              |
                                          decoder.py -> units/bytes
                                          framing / AIM / GS1 / timing / findings
                                                              |
                                        Tech Mode summary  |  Engineering detail
```

## 3. Canonical key event (contract between all components)

```json
{
  "t": 1234.567,          // ms, monotonic, float (sub-ms when the source allows)
  "type": "down",         // "down" | "up"
  "code": "BracketRight", // W3C UI Events KeyboardEvent.code (physical key)
  "key": "]",             // OPTIONAL: what the host OS layout produced (browser only)
  "mods": {"ctrl": true, "shift": false, "alt": false, "meta": false}, // OPTIONAL (browser)
  "repeat": false,        // OPTIONAL autorepeat flag
  "src": "browser"        // "browser" | "agent" | "replay"
}
```

* Agent events have no `key`/`mods`; the decoder tracks modifier state from
  modifier down/up events. Browser events carry `mods`, which take precedence.
* The decoder assumes the scanner's keyboard-country setting is **US**, which is
  the factory default. When `key` is present and disagrees with the US decode, a
  **keyboard layout mismatch** finding is raised.

### Decoder rules (US layout)

| Input | Result | `via` |
|---|---|---|
| Printable key (+Shift) | ASCII char | `key` |
| `Enter` / `NumpadEnter` | 0x0D | `enter_key` |
| `Tab`, `Backspace`, `Escape`, `Delete` | 0x09, 0x08, 0x1B, 0x7F | `named_key` |
| Ctrl + A..Z | 0x01..0x1A | `ctrl` |
| Ctrl + `[` `\` `]` | 0x1B 0x1C 0x1D | `ctrl` |
| Ctrl + `@`(Shift+2) / Space, `^`(Shift+6), `_`(Shift+-) | 0x00, 0x1E, 0x1F | `ctrl` |
| Alt held + Numpad digits, released | value of digits (leading 0 = Windows-1252, else CP437 for >127) | `alt_numpad` |
| F1-F24, arrows, PageUp/Down, Home/End, Insert | non-byte **key token** (e.g. `[F5]`) | `function_key` |
| Modifier keys alone | nothing (they are tracked, never emitted) | - |

## 4. File layout (target)

```
scanwise/
  capture/            decoder.py, keymap.py      (Phase 1)
  parsers/            ascii_chars.py (all 256 named), aim_codes.py, gs1_parser.py
  diagnostics/        framing.py, anomalies.py, timing.py, verdict.py, config_summary.py
  routes/             api.py, views.py (/ and /engineering)
  static/js/
    core/             capture.js, render.js, api.js     (shared)
    tech.js           Tech Mode controller
    engineering.js    Engineering Mode controller
    agent-client.js   SSE client for the native agent
  templates/          base.html, tech.html, engineering.html
agent/                Go native capture agent (zero external deps)
  main.go, server.go, source_linux.go, source_windows.go, source_replay.go, keymap_*.go
tools/
  e2e_cdp.mjs         Headless-Chromium end-to-end test (real key events via CDP)
tests/                pytest suite
docs/                 TECH_GUIDE.md, ENGINEERING_GUIDE.md
```

---

## 5. Phases

### Phase 0: Plan ✅
This document.

### Phase 1: Key-event decoder (Python) + full control-character table ✅
- `scanwise/capture/keymap.py`: W3C `code` -> (unshifted, shifted) US table, named-key table, function-key set, modifier set.
- `scanwise/capture/decoder.py`: `decode_events(events) -> {units, text, summary}`.
  - Modifier tracking (event `mods` win when present).
  - Ctrl-char, Alt+numpad (with code-page handling), named keys, function-key tokens.
  - Layout mismatch detection when `key` is present.
  - Summary: control-char transmission method(s) observed, counts by `via`, unknown keys.
- `parsers/ascii_chars.py`: name **every** value 0x00-0x1F, 0x7F, C1 0x80-0x9F, NBSP, and non-ASCII; add a short `abbr` for badges (`GS`, `CR`, `LF`, `FF`, ...). Categories: `gs1_delimiter`, `terminator`, `whitespace`, `control`, `printable`, `extended`.
- Tests: `tests/test_decoder.py` covering every rule in the table above, plus Shift capitals (regression: `[Shift]` must never leak into data).

**Done when:** pytest is green, and `Ctrl+]`, `Alt+0029` and an in-band GS all decode to 0x1D with the correct `via`.

### Phase 2: Backend analysis and API ✅
- `framing.py`: auto-detect instead of requiring a profile.
  - Leading control run (e.g. STX) and any known profile prefix count as prefix. **The AIM ID is no longer stripped by framing** (fixes AIM loss on the generic profile).
  - Trailing run of terminators/controls counts as suffix (CR, LF, CR+LF, Tab, ETX, double CR, ...).
- Profile matching against **all** profiles; return best match + per-profile result. Expected-profile check is optional.
- `diagnostics/config_summary.py`: tech-facing summary (prefix, suffix, AIM on/off, symbology, control-char method, GS1 separator status, matched profile, plain-language sentences).
- `verdict.py`: return `findings[]` (all issues, with severity/category/evidence) **and** the headline verdict.
- `api.py /api/analyze`: accept `key_events` (preferred) or legacy `raw_input`. Return `units[]` with per-char info, `text_hex`, `decode`, `timing` (using key-down times, dwell times, per-unit deltas), `summary`, `findings`. No HTML in responses.
- Timing: per-unit deltas, dwell, histogram buckets, jitter, configurable thresholds.
- Update existing tests/sample payloads; add API tests that use key events.

**Done when:** pytest is green, and the API returns structured units for a key-event scan containing GS/CR/LF/FF/Tab.

### Phase 3: Shared browser capture core (JS) ✅
- `core/capture.js`: `keydown`+`keyup` on `window` (capture phase) -> canonical events (`performance.now()`).
  - `preventDefault` on all keydowns while armed (ignored while a form control is focused).
  - Scan segmentation by configurable idle gap.
  - Detect `blur`/`visibilitychange` mid-scan -> scan flagged *interrupted* (Ctrl+T / Ctrl+N = DC4 / SO).
  - `beforeunload` guard while a scan is active (turns Ctrl+W = ETB into a "Leave site?" prompt instead of closing the tab).
  - Optional fullscreen + `navigator.keyboard.lock()` (Chromium) to capture Ctrl+W/T/N.
- `core/render.js`: `el()` DOM builder, badge renderer (colour by category), hex/ASCII dump builder, copy-to-clipboard helper. All text goes through `textContent`.
- `core/api.js`: `analyze(events, opts)`.
- `tools/e2e_cdp.mjs`: launches headless Chromium, sends **real** key events via the DevTools Protocol (including Ctrl+] and Shift), and asserts on the API result and the DOM.

**Done when:** an e2e script scanning `Shift+A, Ctrl+], Enter` produces `A <GS> <CR>` in the page.

### Phase 4: Tech Mode UI (`/`) ✅
- Replaces the old dashboard; old `wedge.js`/`ui.js` stop being loaded.
- One large scan area. After a scan, show a **Scanner Configuration card**:
  - *Configured for:* Epic / Cerner / Meditech / Generic / Unknown (auto-detected)
  - *Prefix:* none, or e.g. `/DATA/`
  - *Suffix:* Enter (CR), Tab, CR+LF, LF, none ... as words and badges
  - *AIM symbology IDs:* On (GS1 DataMatrix) / Off
  - *GS1 separators:* Present / Missing / Not a GS1 barcode
  - Scanned data line with **all** control characters as badges.
  - One plain-English "what to do" line if something's wrong.
- Optional "Expected profile" dropdown -> PASS/FAIL banner.
- Pass/fail sound (keep `audio.js`). Link to Engineering Mode.
- Extend e2e to cover Tech Mode (Epic framing, Tab suffix, CR+LF suffix).

**Done when:** e2e passes for the three framings; the page has no hex unless "Show details" is opened.

### Phase 5: Engineering Mode UI (browser source) ✅
- `/engineering` page with panels:
  1. Byte stream (badges, with click-to-select linking all panels)
  2. Character table: index, glyph/badge, hex, dec, name, category, `via`, key(s) used, t, delta, dwell, layout-mismatch flag
  3. Raw key-event log (every down/up, code, key, mods)
  4. Hex dump (offset | 16 hex | ASCII with badge abbreviations)
  5. Timing chart (inline SVG inter-key delta bars, threshold lines)
  6. Framing / AIM / GS1 parse table
  7. All findings with evidence
- Settings: segmentation gap, expected profile, keyboard lock.
- Session history (localStorage), compare two scans (byte diff), export/import JSON (re-analysable replay), copy hex/ASCII (keeps the copy buttons from the uncommitted `ui.js` work).
- Extend e2e for engineering (Alt+numpad, FF, function key token).

### Phase 6: Native agent (Go): core + Linux evdev + replay ✅
- `agent/` Go module, **stdlib only**, single static binary.
- Linux source: enumerate `/dev/input/event*` keyboards (name, phys, VID:PID via ioctls), read `input_event` with kernel timestamps (µs), optional `EVIOCGRAB` exclusive grab, map evdev keycodes -> W3C `code`.
- Replay source: play a recorded JSON capture at its original timing (demo/testing without hardware).
- HTTP on `127.0.0.1` only: `GET /status`, `GET /devices`, `POST /select {id, grab}`, `GET /events` (Server-Sent Events).
- Security: loopback bind, **Origin allowlist** (CORS, default `http://localhost:5000`, `http://127.0.0.1:5000`; `--allow-origin` flag), Private Network Access preflight header, **no device is streamed until one is explicitly selected**, and scanner-looking devices are flagged (known VIDs: 05e0 Zebra/Symbol, 0c2e Honeywell/Metrologic, 0536 Hand Held Products, 05f9 Datalogic). The agent can read any keyboard, so it must never stream one implicitly.
- Go tests: evdev byte parsing, keymap, SSE framing, origin checks, replay.

### Phase 7: Native agent: Windows Raw Input + builds ✅
- `source_windows.go`: message-only window, `RegisterRawInputDevices` (RIDEV_INPUTSINK), `WM_INPUT` -> `RAWKEYBOARD`, scancode (+E0) -> W3C code, per-device handle -> name/VID:PID via `GetRawInputDeviceInfoW`. Pure `syscall` (no cgo).
  - Limitation: Raw Input cannot stop keys from also reaching the focused app (no grab on Windows).
- `agent/build.sh`: linux/amd64, linux/arm64, windows/amd64 binaries into `agent/dist/`.
- Verification: cross-compiles and passes vet. **Runtime test on Windows hardware must be done by the team** (not possible from this Linux workstation).

### Phase 8: Engineering UI <-> agent integration ✅
- `agent-client.js`: detect agent, list devices, select + grab toggle, SSE stream -> same segmentation -> analyze.
- Source switch: Browser / Agent / **Both (comparison)**. Comparison aligns the agent's (ground truth) and browser's decoded units and reports drops, reorders, and layout differences: proof of whether the loss is in the scanner or in the host/OS/browser/VDI layer.
- Device info panel (name, VID:PID, phys, grabbed).
- e2e with the agent in replay mode.

### Phase 9: Docs, cleanup, final verification ✅
- `docs/TECH_GUIDE.md` (one page, for techs), `docs/ENGINEERING_GUIDE.md` (agent install, `input` group, Windows notes, reading the panels, replay files).
- README update; remove dead `wedge.js`/`ui.js`/old template; `.gitignore` for `scanwise.pid`, `agent/dist/`.
- Full test pass (pytest, `go test`, `go vet`, e2e).

---

## 6. Status

| Phase | Status |
|---|---|
| 0 Plan | ✅ Complete |
| 1 Decoder | ✅ Complete |
| 2 Backend/API | ✅ Complete |
| 3 Capture core | ✅ Complete |
| 4 Tech Mode | ✅ Complete |
| 5 Engineering UI | ✅ Complete |
| 6 Agent core + Linux | ✅ Complete |
| 7 Agent Windows + builds | ✅ Complete (runtime untested on Windows) |
| 8 Agent integration | ✅ Complete |
| 9 Docs/cleanup | ✅ Complete |
| 10 GS1 detection + data display | ✅ Complete |
| 11 Tech Mode simplification + components | ✅ Complete |

## 7. Environment notes

- Tests: `mise exec python -- python -m pytest -q` (baseline before Phase 1: 16 passed).
- E2E: `node tools/e2e_cdp.mjs [suite...]` (starts Flask on :5055 + headless Chromium; no npm deps).
- Go 1.27, Node 26, Chromium are available for agent builds and e2e.
- The dev user is **not** in the `input` group, so live evdev capture can't be exercised on this
  workstation; the Linux source is verified by unit tests on raw `input_event` bytes plus the
  replay source. To test with a real scanner: `sudo usermod -aG input $USER` (re-login), or run the agent with sudo.

## 8. Phase Log

- **Phase 0** (2026-10-28): Plan written. Baseline 16 tests passing.
- **Phase 1** (2026-10-28): Added `scanwise/capture/{keymap,decoder}.py`. Rewrote `parsers/ascii_chars.py`
  with `describe_char()` covering every C0 control, DEL, C1, invisible Unicode and U+FFFD (badge `abbr`,
  category, severity) and `visualize()` for plain-text `<GS>` rendering. Test helper `tests/keyseq.py`
  types like a scanner. `tests/test_decoder.py`: 15 tests (Shift regression, Ctrl A-Z, Ctrl symbols,
  GS via Ctrl+] and Alt+0029, Alt code pages, incomplete Alt, function-key tokens, layout mismatch,
  Caps Lock, browser mods, dwell). Category `harmful_control` was renamed to `control`; the old test was updated.
  **31 passed.** Not yet wired into the API (Phase 2).
- **Phase 2** (2026-10-28): New `scanwise/analysis.py` pipeline (used by `/api/analyze`). `framing.py` now
  auto-detects prefix/suffix (leading control run + known profile prefixes; trailing terminator/control run),
  keeps the AIM ID for the AIM parser, and evaluates **every** profile with plain-language reasons. Generic is
  marked `pass_through`. `anomalies.py` classifies controls by region (prefix/aim/data/suffix) and detects
  ISO/IEC 15434 envelopes. `timing.py` adds median/p95/stdev/spikes/histogram/dwell. `verdict.py` adds
  `build_findings()` (all findings, `detail` + `tech_hint`), and the headline is derived from them.
  New `config_summary.py` gives the tech-facing summary. GS1: more AIs (00/02/20/22/37/241/250), SSCC check,
  too-long/truncated field flags, and GS1 is only parsed when AIM says GS1 or the data parses cleanly from
  00/01/02 (fixes plain wristbands like `E10293` being treated as GS1). The API accepts `key_events`,
  validates input, and returns structured `units` (no HTML). Expired product is now `info` (it's a product
  issue, not a scanner fault; the sample label's 2025-12-31 date had started failing the PASS test).
  **48 passed.**
- **Phase 3** (2026-10-28): `static/js/core/{capture,render,api}.js` (ES modules, no build step) and
  `static/css/scan.css` (badge colours per category). `KeyCapture` records keydown/keyup with `e.timeStamp`,
  `preventDefault`s everything outside form controls, segments by idle gap, flags blur/visibility/unload
  mid-scan as *interrupted*, guards `beforeunload` (Ctrl+W = ETB), and has `push()` for agent events.
  `enableKeyboardLock()` covers fullscreen + `navigator.keyboard.lock()`. `render.js` builds DOM via text
  nodes only. Dev page `static/dev/capture-harness.html`. E2E driver `tools/cdp.mjs` + `tools/e2e_cdp.mjs`
  (raw CDP over Node's built-in WebSocket; synthesizes Shift/Ctrl/Alt+numpad like a scanner).
  **E2E harness: 5 passed** (Ctrl+] -> GS badge, Alt+0029 -> GS, Tab/FF/LF with focus kept, Shift capitals,
  markup stays text). pytest still 48 passed.
- **Phase 4** (2026-10-28): `/` now renders `templates/tech.html` + `static/js/tech.js` + `static/css/tech.css`
  (the old `dashboard.html`/`wedge.js`/`ui.js`/`app.js` are no longer loaded; deleted in Phase 9). `base.html`
  has Tech/Engineering nav; `/engineering` is a placeholder route. The page has no text box: the whole page
  is the scan target, with a pulsing zone and a pass/warn/fail colour. The configuration card shows Configured
  for, Prefix, Suffix (badges, then words for control chars, e.g. `CR` `LF` = CR (Enter) + LF), AIM IDs, GS1
  separators, a ✓/✗ check per profile with reasons, the scanned data with badges + legend, and "Also check"
  (findings other than the headline). Hex is behind "Show details". The profile-mismatch hint now says what
  to program. Fixed a self-inflicted bug: the `beforeunload` guard fired for 1.5 s after every scan; it's now
  active only while a scan is in progress. **E2E: 10 passed** (tech: Epic PASS, Tab suffix, CR+LF, expected-
  Epic fault, FF/BEL flagged). Screenshots reviewed (`SCANWISE_SHOTS=dir`). pytest 48 passed.
- **Phase 5** (2026-10-28): `/engineering` = `templates/engineering.html` + `static/js/engineering.js` +
  `static/css/engineering.css`. Panels: live key-event strip; summary stats; byte stream (click-to-trace:
  selection syncs stream, character table, key-event rows, hex cells, timing bars); tabs for Characters
  (hex/dec/name/category/region/produced-by/keys/t/Δ/dwell/host key/flags), Key events (every down/up with
  code, host key, mods, linked char), Hex dump (+copy), Timing (SVG bar chart of per-character delay with
  spike threshold, hover tooltip, char labels; stats + histogram tables), Framing & data (framing, AIM,
  ISO 15434, decode method counts, layout mismatches, GS1 table), Findings (all, with evidence + tech
  wording), Compare (LCS character diff of two history scans + field table). Session history in
  localStorage (50 max), export/import of `{"format":"scanwise-capture","version":1,"scans":[{events,meta,
  source}]}`, the same format the agent's `--replay` will read. Gap ms + expected profile + Keyboard Lock
  controls. `window.scanwise.ingest()` is the plug-in point for the agent (Phase 8). Copy buttons from the
  uncommitted `ui.js` work are carried over (visual / hex / JSON string). **E2E: 15 passed** (engineering:
  Alt+numpad/FF/F5 token rendering, cross-panel selection, chart bar count, history + compare diff,
  agent-style replay import). Screenshots reviewed. pytest 48 passed.
- **Phase 6** (2026-10-28): `agent/` Go module (stdlib only). `source_linux.go`: enumerates
  `/dev/input/event*` keyboards (EV_KEY bitmap must have A-E + Enter), name/phys/bus/VID:PID via ioctls,
  `EVIOCSCLOCKID` monotonic timestamps, optional `EVIOCGRAB`, released on stop/SIGTERM. `evdev_parse.go`
  (portable, tested on 64- and 32-bit layouts) attaches `MSC_SCAN` HID usage to each key event, keeps
  autorepeat, and maps keycodes to W3C codes via `keymap.go` (unknowns become `Unidentified<n>`, never dropped).
  `source_replay.go` plays `scanwise-capture` files at original timing (`-replay-speed`, `-replay-loop`).
  `server.go`: `/status`, `/devices`, `POST /select {id,grab}`, `POST /release`, `/events` (SSE, keepalive,
  one flush per burst, slow-client drop counter). Security: loopback-only listen (refuses others), Host must be
  loopback (DNS rebinding), Origin allowlist (default localhost:5000 / 127.0.0.1:5000, `-allow-origin`),
  no-Origin requests refused unless `-allow-no-origin`, PNA preflight header, nothing streamed until a
  device is selected, device ids validated. Scanner hints by VID (05e0, 0c2e, 0536, 05f9) and name.
  **go test (incl. -race): pass** (evdev parsing 64/32-bit, MSC_SCAN, repeat, timestamps, keymap, detection,
  guard matrix, no-stream-until-select, path-traversal id, replay over SSE end-to-end). On this workstation
  `-list` reports the `input`-group permission problem correctly; **live evdev capture is untested here**.
- **Phase 7** (2026-10-28): `source_windows.go`: message-only window (own class whose WndProc is
  `DefWindowProcW`, so no Go callbacks), `RegisterRawInputDevices` (page 1 / usage 6, `RIDEV_INPUTSINK`
  so capture works when the page has focus), `WM_INPUT` -> `GetRawInputData` filtered to the selected
  `hDevice`, repeat inferred from pressed-key state, unregisters on stop (`PostThreadMessage WM_QUIT`).
  Devices via `GetRawInputDeviceList` + `RIDI_DEVICENAME` (VID/PID parsed from the path) + `HidD_Get*String`
  for friendly names. `keymap_scancode.go` (portable, tested): set-1 make codes + E0/E1, Windows fake-shift
  filtering, F13-F24. Shared `nowMs()` clock. `agent/build.sh`: gofmt check, vet (linux + windows), tests,
  static `-trimpath` binaries for linux/amd64, linux/arm64, windows/amd64 in `agent/dist/`. Verified:
  cross-compiles, `GOOS=windows go vet` clean, PE32+ produced. **Not run on Windows**: the team must test
  `scanwise-agent-windows-amd64.exe -list` and a live scan on real hardware.
- **Phase 8** (2026-10-28): `static/js/agent-client.js` (HTTP + EventSource). Engineering Mode source panel:
  Browser / Native agent / Both, agent URL (persisted), device picker (★ = likely scanner, VID:PID), Grab
  toggle (disabled where unsupported), live status, plus the actionable "start it with -allow-origin <this
  origin>" message when the agent is unreachable. Agent events run through their own `KeyCapture.push()`
  segmenter, so decoding/analysis is identical to browser capture. **Both** pairs the agent scan with the
  browser scan arriving within 1 s; if the browser got nothing or a different stream, a client-side
  `ENVIRONMENT_FAULT` finding becomes the headline (caught during screenshot review: it first showed PASS
  with 1 char lost). The Compare tab shows "agent (ground truth) vs browser" diff above history compare.
  E2E `agent` suite builds the agent, runs it in replay mode (`-no-native`), and drives the page:
  **E2E: 18 passed** (agent decode of evdev-style events, browser-received-nothing, dropped-char diff with
  headline). pytest 48, go test pass.
- **Phase 9** (2026-10-28): `docs/TECH_GUIDE.md` (one page for onsite techs), `docs/ENGINEERING_GUIDE.md`
  (decoder rules, browser limits, agent build/run/permissions/security/API, panel tour, replay format,
  profiles, tests), README rewritten, implementation note in `vision.md` section 4. Removed the dead
  `static/js/wedge.js`, `static/js/app.js`, `templates/dashboard.html` (unmodified, recoverable from git).
  **Left in place:** `static/js/ui.js`. It is no longer loaded, but it holds uncommitted copy-button edits
  (now reimplemented in Engineering Mode), so deleting it is the owner's call. `.gitignore` now covers
  `scanwise.pid` and `agent/dist/`; `scanwise.pid` is still tracked (`git rm --cached scanwise.pid` to stop).
  Final matrix: **pytest 48 passed · go vet (linux+windows) clean · go test -race pass · e2e 18 passed**.

## 9. Open items for the team

1. **Windows agent runtime test** on real hardware (`-list`, live scan, Both mode).
2. **Linux live evdev test** with a real scanner (`input` group), including `-grab`.
3. **Confirm EMR profile values** (`emr_profiles.json`): Epic is confirmed from a real DENSO scan
   (2026-10-29): data wrapped in backslashes `\<data>\`, optional CR/LF/Tab after. `~` + CR for Cerner
   and CR for Meditech are still from `vision.md`, not verified against site programming sheets.
4. **Scanner keyboard-country:** the decoder assumes US. Non-US scanner settings show as layout mismatches;
   add per-country tables if the fleet uses them.
5. **Cross-host agent access:** if the UI is served from a server (not localhost), verify Chromium's
   local-network-access behaviour on your managed browsers; HTTPS for the UI may be required.
6. Consider stopping tracking `scanwise.pid` and deleting `static/js/ui.js`.
- **Phase 10** (2026-10-28, after team feedback "not detecting GS1 correctly; show the data with
  non-printables in place; GS1 fields can be out of order"). Root causes reproduced first: (1) without an
  AIM ID, GS1 was only detected when the data started with 00/01/02, so (17)- or (21)-first labels were
  missed; (2) only 18 AIs were known, so NHRN 710-716, 725x patient AIs, GSRN 8017/8018 and internal 91-99
  broke the parse; (3) the AIM table was wrong (`]Q1` marked GS1; GS1 QR is `]Q3`; `]d3`-`]d6`, Aztec and
  DataBar modifiers missing or mislabeled). New `parsers/gs1_ai.py`: full AI table with format specs and
  the predefined-length rule (prefix-free, asserted at import). New `parsers/gs1_parser.py`: parses in any
  order; terminator per field (`predefined` / `gs` / `end` / `missing_gs`); definite missing GS (value over
  max length, re-split at the most plausible boundary; non-predefined AI such as (422) followed directly by
  data) vs *possible* (a variable field hides a strongly validated AI, e.g. lot + 17 + valid date);
  unnecessary GS after predefined fields; CSET82 / numeric / check-digit / date (GS1 century rule, DD=00)
  / date-time validation; implied-decimal measures; bracketed HRI `(01)...` and GS1 Digital Link input.
  `detect_gs1()` gives confidence + reason; non-GS1 data (MRNs, plain URLs) stays non-GS1, and GS1 data
  in a non-GS1 symbol (`]C0`) is flagged. Characters are tagged with their GS1 field (`gs1_element`,
  `gs1_part`). UI: Tech Mode has a **Scanned data** card directly under the result: the stream exactly
  as received (every hidden char inline), then for GS1 a **field view** (labelled boxes in received
  order: AIM, each field, each GS separator, suffix; how each field ended; red box + "GS MISSING" when a
  separator is missing), an order line ("Any order is valid GS1"; warns only when the primary key isn't
  first, since that's where order-dependent EMR parsers break), and a field table. Engineering Mode has the
  same field view under the byte stream and a fuller GS1 table (format spec, position, terminator, checks,
  detection reason). **pytest 70 passed** (new `tests/test_gs1.py`), **e2e 21 passed**.
- **Phase 11** (2026-10-28, after feedback "Tech Mode broken: no GS1, datastream not shown; must be simple
  enough to show a nurse; show GTIN/serial/expiry/lot"). Investigation: the live :5000 server was running
  current code and passed the Tech e2e suite with synthetic keys; static files are `no-cache`; 20k fuzzed
  payloads produced no server errors. Reproduced a real failure mode: keystrokes that arrive **without a
  physical key code** (`code: ""`, as with RDP/Citrix, Windows VK_PACKET Unicode injection, Bluetooth/virtual
  keyboards, scanner "Unicode" modes) decoded to *nothing*, so no data and no GS1. The decoder now falls
  back to the OS-produced character (`via: host_key`; Ctrl+letter still means a control char; named keys
  mapped), capture records `keyCode` (229 IME / 231 VK_PACKET), and an info finding reports it. **Not
  confirmed** to be the user's cause (no hardware here). Tech Mode rebuilt: Scanner / Barcode status pills
  + one sentence; **What's in this barcode** component cards (Product/GTIN with check digit + NDC from
  03-prefixed GTINs, Expiration as a readable date + EXPIRED/Not expired, Lot, Serial, then others; plain
  data card for non-GS1); **Exactly what the scanner sent**; Scanner setup; technical detail under "More
  details (for IT)". "Nothing readable" scans and script/load failures show explicit messages instead of
  a blank page. Generic matches now read "No prefix, CR (Enter) after each scan (matches Meditech
  Expanse)". Engineering Mode gets the same component cards. **pytest 72, e2e 24 passed** (new: component
  cards + pills, code-less keystroke GS1 scan, nothing-readable message).
- **Phase 12** (2026-10-29, after feedback "not displaying the full data stream"). Cause reproduced: capture
  ended a scan after 150 ms of silence, so a scanner that stalls mid-barcode (Bluetooth buffering,
  keystroke-delay settings, a busy PC, slow Alt+numpad sequences) was split into several "scans", and Tech
  Mode showed only the last piece. Capture now ends a scan after `gapMs` only when the last key was a
  suffix key (Enter, NumpadEnter, Tab, Ctrl+M/J/I); otherwise it waits `idleMs` (1000 ms). Tech Mode also
  ignores an analysis response that arrives after a newer scan started. **pytest 72, e2e 25 passed** (new:
  barcode with two 450 ms stalls stays one scan and the full stream is shown).
- **Phase 13** (2026-10-29, "still broken; export shows only IS of IS2205993"). The user's exports
  (`~/Downloads/scanwise-*.json`) show the keys never reached the page: Shift down/up with no key where the
  `I` should be, and nothing after the last Alt+0029, all within about 90 ms. The machine runs Wayland +
  Firefox + **fcitx5** (`GTK_IM_MODULE=fcitx`), which routes every keystroke through an input method.
  That's the likely cause, unconfirmed. ScanWise could not see the loss before. The decoder now emits a
  `LOST KEY` token (via `lost_key`) wherever a modifier is pressed and released alone, `lost_key_count`
  is in the summary, and `keys_lost` (error, ENVIRONMENT_FAULT) is the top finding, so an incomplete
  scan is never presented as complete. Characters dropped *without* a modifier cannot be seen from the
  browser; the native agent in Both mode is the ground truth. **pytest 75, e2e 25 passed.**
- **Phase 14** (2026-10-29). Root cause of "only IS shows" found with a raw key-log page
  (`/static/dev/keylog.html`): on this Firefox 155 / Wayland / fcitx5 machine, keystrokes reach a page
  reliably **only while a text field has focus**. With focus on the bare page, both unblocked and blocked,
  only `Shift I Shift S` of `IS2216121` arrived. In a textarea every key arrived. Capture now uses a hidden,
  always-focused `<textarea id="scan-sink">` (refocused after clicks; not while a real form control
  is in use or text is selected). Plain character keys are allowed to type into it; everything else is
  still blocked. Text that arrives as `input`/`compositionend` with no matching key press is recorded as
  code-less key events (`from_input`). The sink is emptied after each scan. Added `tools/evdump.py` (raw
  evdev dump, needs root). **pytest 75, e2e 28 passed** (new: sink focus, real text-producing keys
  without duplicates, input-only text).
- **Phase 15** (2026-10-29, "secure against storing PHI"). Audit: the only on-disk copy was Engineering
  history in `localStorage` (50 full scans). Now: history is memory-only and legacy `localStorage` history
  is purged on load. Exports are redacted by default through `/api/redact` (`scanwise/redact.py`: visible
  data characters become X/x/0 at the key-event level, including Alt+numpad and code-less keys, while
  AIM, GS1 AIs/separators, controls, timing and profile-confirmed framing are kept). Full-data export
  needs a second click and is named `FULL-DATA`. API responses are `no-store`. The 500 handler logs the
  exception type and traceback without the message. The capture sink is emptied on every input and on
  pagehide. Diagnostic tools carry PHI warnings. The server never wrote scans to disk; the agent logs
  no key data. **pytest 82, e2e 30 passed** (new `tests/test_redact.py`; e2e: storage audit, legacy
  purge, export defaults).
- **Phase 16** (2026-10-29, "GS1 not recognized with Epic configuration; it's the \data\ prefix; Epic
  doesn't require CR/LF or Tab"). Cause: the Epic profile expected `/DATA/` + CR (from `vision.md`), and
  prefixes matched only exactly. So `\data\` stayed in the payload, GS1 detection saw `\data\0100…`, and
  scans without a suffix failed Epic and raised `no_suffix`. The Epic profile is now `\data\`,
  `prefix_case_insensitive`, `accepted_suffixes` none/CR/CR+LF/Tab. `no_suffix` is raised only when the
  expected or matched profile needs a suffix (`framing.suffix_required`). An unknown visible prefix
  directly before a registered AIM ID is split off as `prefix_unrecognized`. Tech Mode shows "Nothing
  (not needed for this setup)" for the suffix. **pytest 87** (new Epic GS1 tests: no suffix, any case,
  every accepted suffix, no AIM, unknown prefix).
- **Phase 17** (2026-10-29, "still 'framing doesn't match' when \data\ is present and correct; a CR/LF/Tab
  suffix is fine for some Epic workflows, but techs should see it"). Two causes reproduced. (1) Scanners
  that send the AIM ID ahead of the custom prefix (`]d2\data\…`): the prefix was only looked for at the
  start, giving "Missing prefix". `detect_framing` now recognises AIM-then-prefix (`framing.aim_at`) and
  `region_of` labels both parts correctly. (2) Only none/CR/CR+LF/Tab were accepted, so LF alone or Tab+CR
  failed. The Epic profile now uses `accepted_suffix_chars` "\r\n\t" (none or any mix). For a matched
  profile with a prefix, "Set up for" now names the suffix ("…, CR (Enter) after each scan" / "…, no
  suffix"). **pytest 90, e2e 31 passed.** Not yet confirmed against the user's actual scan (no export).
- **Phase 18** (2026-10-29). The user's full-data export settled it: the enterprise Epic configuration
  sends `\01095011015300031715011910AB-123\`, with the data **wrapped** in backslashes and no
  terminator. "\data\" in Epic terms means \ + data + \, not literal text. Phases 16 and 17 had modelled
  a literal `\data\` prefix, so the real scans still failed ("Missing prefix", no GS1, "No suffix").
  The Epic profile is now prefix `\`, suffix `\`, `optional_terminators` "\r\n\t" (replacing
  `accepted_suffix_chars`). `detect_framing` splits off a profile's visible closing text only when that
  profile's opening prefix was found. "Set up for" spells out the wrapping and the terminator. A missing
  terminator is an info finding unless the selected or matched profile needs one. The real scan is a
  fixture (`tests/fixtures/denso_epic_gs1.json`). **pytest 108, e2e 31 passed.**

