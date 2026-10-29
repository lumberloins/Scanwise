# ScanWise: Medical Barcode & Scanner Configuration Diagnostic Tool

ScanWise tests USB HID keyboard-wedge barcode scanners and shows **every** character they inject,
including all non-printable characters (GS, CR, LF, FF, Tab, STX/ETX, NUL, ESC, ...), and how each
one was produced.

- **Tech Mode** (`/`): scan once and see how the scanner is configured: prefix, suffix (Tab / CR / CR+LF),
  AIM IDs, GS1 separators, and which EMR profile (Epic, Cerner, Meditech) it matches. See `docs/TECH_GUIDE.md`.
- **Engineering Mode** (`/engineering`): keystroke-level forensics, timing, findings, history, compare,
  export/replay, plus an optional **native capture agent** (`agent/`, Go) for device-level ground truth.
  See `docs/ENGINEERING_GUIDE.md`.

Architecture and build history: `BUILD_PLAN.md`. Original product spec: `vision.md`.

## Requirements

- Python 3.10+, Flask, Waitress (`requirements.txt`)
- Optional: Go 1.22+ to build the agent; Node 18+ and Chromium for the e2e tests

## Running

```bash
mise exec python -- python run.py        # or ./startup.sh / ./shutdown.sh
```

Open `http://localhost:5000`. Settings: `SCANWISE_HOST`, `SCANWISE_PORT`, `FLASK_DEBUG`.

Native agent (optional, for Engineering Mode):

```bash
agent/build.sh
agent/dist/scanwise-agent-linux-amd64 -list
agent/dist/scanwise-agent-linux-amd64          # then choose "Native agent" in Engineering Mode
```

## Tests

```bash
mise exec python -- python -m pytest -q
(cd agent && go test -race ./...)
node tools/e2e_cdp.mjs
```
