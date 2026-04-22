#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Creativity Lab preflight"
echo "cwd: $ROOT"
echo

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

echo "[1/8] Git status"
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  git status --short --branch
else
  echo "Not a git repository from this working directory."
fi
echo

echo "[2/8] Recovery directory"
if [ -d ".recovery" ]; then
  ls -lah .recovery
else
  echo "No .recovery directory found."
fi
echo

echo "[3/8] Core files"
ls -lah server.py agents.py database.py experiments.py
echo

echo "[4/8] Recovery snapshots"
find . -maxdepth 2 -type f \( -name "*.bak" -o -name "*.orig" -o -name "*.truncated-recovery" -o -name "*.pre-*" \) | sort || true
echo

echo "[5/8] Compile check"
"$PYTHON_BIN" -m py_compile server.py agents.py database.py experiments.py scripts/promote_rules.py
echo "Compile check passed."
echo

echo "[6/8] Backend tests"
"$PYTHON_BIN" -m unittest \
  tests.test_backend_hardening \
  tests.test_api_security \
  tests.test_lab_decision_matrix \
  tests.test_experiment_design \
  tests.test_analytics \
  tests.test_disagreement_reviews \
  tests.test_artifact_redaction \
  tests.test_prompt_compiler_schema
echo

echo "[7/8] Static and schema checks"
node --check static/app.js
"$PYTHON_BIN" -m json.tool data/prompt_compiler_schema.json >/dev/null
"$PYTHON_BIN" -m json.tool data/prompt_rule_evidence_schema.json >/dev/null
echo "Static and schema checks passed."
echo

echo "[8/8] Ruff"
"$PYTHON_BIN" -m ruff check \
  server.py agents.py database.py experiments.py judgment_wiki.py scripts/promote_rules.py \
  tests/test_backend_hardening.py tests/test_api_security.py tests/test_lab_decision_matrix.py \
  tests/test_experiment_design.py tests/test_analytics.py tests/test_disagreement_reviews.py \
  tests/test_artifact_redaction.py tests/test_prompt_compiler_schema.py
echo
echo "Preflight completed successfully."
