# Backend Recovery Incident

Date: 2026-04-02

## Summary

A backend hardening pass damaged core source files in the lab.

The failure mode was not bad diagnosis. It was unsafe execution in a fragile environment:
- no confirmed git checkpoint from the active working path
- no confirmed remote rollback path
- no explicit pre-change backups of all core files
- too many hardening concerns bundled into one pass

The lab was recovered by reconstructing the backend into a working state, validating the current SQLite schema, and rerunning the backend test pack until the app and API contract were stable again.

## What Failed

- Core backend files were edited without a strong rollback path.
- The edit strategy appears to have used a rewrite-oriented path on high-risk files.
- `server.py` and `agents.py` were corrupted/truncated.
- Recovery had to be done from the remaining code, tests, runtime expectations, and the live database schema.

## What Restored The System

- Immediate stop on further risky edits
- preservation of damaged files as recovery snapshots
- reconstruction of:
  - `server.py`
  - `agents.py`
  - `database.py`
- re-verification against:
  - `py_compile`
  - backend unit tests
  - API smoke checks

## Lessons

1. Core backend work in this lab is high-fragility work.
2. Reversibility must be confirmed before implementation begins.
3. Broad backend hardening should be split into one change family at a time.
4. Targeted patching is safer than rewrite-oriented edits on foundational modules.
5. A localhost experimental lab still needs production-style state-preservation discipline.

## New Guardrails Added

- [backend-safety-protocol.md](backend-safety-protocol.md)
- source-safety section added to [program.md](../program.md)
- runnable preflight script added at `./scripts/preflight.sh`

## Follow-Up

- decide on proper git initialization and backup posture for this folder
- make preflight checks part of the normal backend workflow
- stage Hermes autonomy through a trust ladder instead of broad shell trust from day one
