#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
export PATH="/opt/homebrew/bin:$PATH"
HOST="${LAB_HOST:-127.0.0.1}"
PORT="${PORT:-7777}"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi
exec "$PYTHON_BIN" -m uvicorn server:app --host "$HOST" --port "$PORT"
