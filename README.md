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

Start and stop ScanWise with the scripts in the project root. They work from any directory.

```bash
./startup.sh      # start the server in the background
./shutdown.sh     # stop it
```

Then open `http://localhost:5000`: Tech Mode is `/`, Engineering Mode is `/engineering`.

**`startup.sh`**
- Picks a Python: `mise` if installed, else `venv/bin/python`, else `python3`.
- Installs `requirements.txt` quietly.
- Starts `run.py` in the background (Waitress).
- Writes the process ID to `scanwise.pid` and all output to `scanwise.log`.
- Refuses to start a second copy if ScanWise is already running.

**`shutdown.sh`**
- Stops the process named in `scanwise.pid`.
- If that file is missing, it looks for a running `python run.py`.
- Waits up to 5 seconds for a clean exit, then force-kills, and removes `scanwise.pid`.

**Restart** (needed after pulling or changing Python code; for HTML, CSS or JS changes a hard browser
refresh, Ctrl+Shift+R, is enough):

```bash
./shutdown.sh && ./startup.sh
```

**Check that it's running:**

```bash
cat scanwise.pid && ps -p "$(cat scanwise.pid)"   # is the process alive?
tail -f scanwise.log                              # server output and errors
```

If `startup.sh` says "failed to start", the reason is in `scanwise.log`. A common one is another
program already using port 5000.

**Settings** are environment variables, read at startup:

| Variable | Default | Meaning |
|---|---|---|
| `SCANWISE_HOST` | `0.0.0.0` | Address to listen on. `0.0.0.0` makes ScanWise reachable from other PCs on the network; use `127.0.0.1` to keep it on this PC only. |
| `SCANWISE_PORT` | `5000` | Port to listen on |
| `FLASK_DEBUG` | `True` | Flask debug flag |

```bash
SCANWISE_HOST=127.0.0.1 SCANWISE_PORT=8080 ./startup.sh
```

To run in the foreground instead (output in the terminal, stop with Ctrl+C):

```bash
mise exec python -- python run.py
```

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
