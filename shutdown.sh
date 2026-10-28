#!/usr/bin/env bash
# ==============================================================================
# ScanWise Shutdown Script for RHEL / Linux Servers
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="scanwise.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "ScanWise PID file not found. Checking for running process..."
    PID=$(pgrep -f "python run.py" || true)
else
    PID=$(cat "$PID_FILE")
fi

if [ -z "$PID" ] || ! ps -p "$PID" > /dev/null 2>&1; then
    echo "ScanWise is not currently running."
    rm -f "$PID_FILE"
    exit 0
fi

echo "Stopping ScanWise server (PID $PID)..."
kill "$PID" || true

# Wait for graceful shutdown
for i in {1..5}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "ScanWise stopped successfully."
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

echo "Force killing ScanWise server..."
kill -9 "$PID" > /dev/null 2>&1 || true
rm -f "$PID_FILE"
echo "ScanWise stopped."
