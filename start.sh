#!/bin/bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[start.sh] Launching simple_round_ws.py"
python3 -u simple_round_ws.py &

echo "[start.sh] Launching webserver.py"
python3 -u webserver.py

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python3 simple_round_ws.py &
python3 webserver.py
