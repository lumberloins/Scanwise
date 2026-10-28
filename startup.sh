#!/usr/bin/env bash
# ==============================================================================
# ScanWise Startup Script for RHEL / Linux Servers
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="scanwise.pid"
LOG_FILE="scanwise.log"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "ScanWise is already running with PID $OLD_PID."
        exit 1
    else
        rm -f "$PID_FILE"
    fi
fi

echo "Starting ScanWise diagnostic server..."

# Determine python / mise environment
if command -v mise &> /dev/null; then
    PYTHON_CMD="mise exec python -- python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_CMD="./venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "Error: Python 3 not found." >&2
    exit 1
fi

# Ensure dependencies are installed quietly
$PYTHON_CMD -m pip install --quiet -r requirements.txt || true

# Start server in background with nohup
nohup $PYTHON_CMD run.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

echo "$SERVER_PID" > "$PID_FILE"
sleep 1

if ps -p "$SERVER_PID" > /dev/null 2>&1; then
    echo "ScanWise successfully started with PID $SERVER_PID."
    echo "Logs are being written to $LOG_FILE."
else
    echo "Error: ScanWise failed to start. Check $LOG_FILE for details." >&2
    rm -f "$PID_FILE"
    exit 1
fi
