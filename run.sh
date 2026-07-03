#!/bin/bash
set -e

PROJECT_DIR="/home/yova/Mark-XLVII"
cd "$PROJECT_DIR"

PORTS=(9107 8000 8001)

echo "=== ALICE Launcher ==="

# Kill existing alice process
OLD_PID=$(pgrep -f "python3.*main.py" 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
    echo "[+] Killing existing ALICE (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[+] Force killing..."
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
fi

# Free up ports
for port in "${PORTS[@]}"; do
    PID=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "[+] Freeing port $port (PID $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
done
sleep 0.5

export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/1000

echo "[+] Starting ALICE..."
./venv/bin/python3 main.py
