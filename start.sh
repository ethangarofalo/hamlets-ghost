#!/bin/bash
cd /Users/ethangarofalo/creativity-lab
HOST="${LAB_HOST:-127.0.0.1}"
PORT="${PORT:-7777}"
exec /Users/ethangarofalo/creativity-lab/.venv/bin/python -m uvicorn server:app --host "$HOST" --port "$PORT"
