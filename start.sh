#!/bin/bash
# Hamlet's Ghost — one-command launcher
#
# Usage:
#   ./start.sh           # live db (real experiments) — use this for demos
#   ./start.sh demo      # demo_lab.db synthetic fixture (artifacts are null)
#
# The script sources .env, frees port 7777 if it's already held, prints the
# admin token, and opens http://127.0.0.1:7777 in the default browser.

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

if [ ! -f .env ]; then
  echo "ERROR: .env not found at $ROOT_DIR/.env" >&2
  echo "Expected LAB_ADMIN_TOKEN and provider keys there." >&2
  exit 1
fi

# Load env (API keys, LAB_ADMIN_TOKEN, etc.)
set -a
# shellcheck disable=SC1091
source ./.env
set +a

# Pick db based on first arg
MODE="${1:-live}"
case "$MODE" in
  demo)
    export LAB_DB_PATH="demo_lab.db"
    BANNER="demo (synthetic fixture)"
    if [ ! -f "$LAB_DB_PATH" ]; then
      echo "demo_lab.db not found - bootstrapping from tracked fixtures..."
      "$PYTHON_BIN" scripts/bootstrap_demo.py
    fi
    ;;
  live|"")
    # Use whatever .env / default resolves to — creativity_lab.db in this tree
    BANNER="live (creativity_lab.db)"
    ;;
  *)
    echo "Usage: $0 [live|demo]" >&2
    exit 1
    ;;
esac

# Free port if already held
if lsof -ti :"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT in use — stopping existing process..."
  lsof -ti :"$PORT" | xargs kill 2>/dev/null || true
  sleep 1
fi

URL="http://$HOST:$PORT"
TOKEN="${LAB_ADMIN_TOKEN:-<not set in .env>}"

cat <<BANNER_END

  Hamlet's Ghost — $BANNER
  ────────────────────────────────────────────────
  URL:          $URL
  Admin token:  $TOKEN
  (paste the token when the UI first asks — it is cached in localStorage)

  Press Ctrl+C to stop the server.

BANNER_END

# Open the browser shortly after uvicorn starts listening
(
  sleep 2
  if command -v open >/dev/null 2>&1; then
    open "$URL" 2>/dev/null || true
  fi
) &

exec "$PYTHON_BIN" -m uvicorn server:app --host "$HOST" --port "$PORT"
