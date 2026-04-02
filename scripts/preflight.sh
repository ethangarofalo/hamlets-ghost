#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Creativity Lab preflight"
echo "cwd: $ROOT"
echo

echo "[1/6] Git status"
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  git status --short --branch
else
  echo "Not a git repository from this working directory."
fi
echo

echo "[2/6] Recovery directory"
if [ -d ".recovery" ]; then
  ls -lah .recovery
else
  echo "No .recovery directory found."
fi
echo

echo "[3/6] Core files"
ls -lah server.py agents.py database.py experiments.py
echo

echo "[4/6] Recovery snapshots"
find . -maxdepth 2 -type f \( -name "*.bak" -o -name "*.orig" -o -name "*.truncated-recovery" -o -name "*.pre-*" \) | sort || true
echo

echo "[5/6] Compile check"
python3 -m py_compile server.py agents.py database.py experiments.py
echo "Compile check passed."
echo

echo "[6/6] Backend tests"
python3 -m unittest \
  tests.test_backend_hardening \
  tests.test_api_security \
  tests.test_lab_decision_matrix \
  tests.test_experiment_design \
  tests.test_analytics
echo
echo "Preflight completed successfully."
