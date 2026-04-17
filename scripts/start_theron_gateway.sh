#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Starting Theron gateway from $ROOT"
echo

./.venv/bin/python scripts/theron_doctor.py || true
echo
echo "Launching dedicated Theron gateway..."
exec ./.venv/bin/python scripts/theron_gateway.py
