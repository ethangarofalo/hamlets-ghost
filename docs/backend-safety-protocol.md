# Creativity Lab Backend Safety Protocol

Last updated: 2026-04-02

This protocol exists to protect the lab from accidental source loss during backend work.

The rule is simple:
- source integrity comes before implementation speed

Use this document before any nontrivial change to `server.py`, `database.py`, `agents.py`, or other files that can break the lab loop.

## Operating Principle

For core backend work, the first question is not:
- "Can we improve this quickly?"

The first question is:
- "Can we restore the current working state instantly if the edit goes wrong?"

If the answer is no, stop and create a recovery path first.

## Risk Tiers

### Low risk
- one small patch in a non-core file
- copy edits in docs
- read-only analysis
- adding tests without touching runtime logic

### Medium risk
- a small targeted patch in one core backend file
- adding one endpoint
- changing one query path
- adding one retry or guardrail

### High risk
- touching `server.py`, `database.py`, and `agents.py` in one pass
- any broad refactor across core modules
- any rewrite-oriented edit path
- schema work against the live SQLite file
- changes that affect scheduling, state transitions, scoring, or startup

High-risk work requires the full preflight checklist.

## Preflight Checklist

Before editing a core backend file:

1. Confirm recoverability.
- Check whether the repo is under git from the current working directory.
- Check whether there is a usable remote or external backup.
- Check whether local file-history recovery exists.

2. Create explicit file backups.
- Copy each target file before editing.
- Use a clear suffix like `.pre-<date>-<short-label>` or `.bak`.

3. Narrow the scope.
- Define one change family only.
- Do not batch scheduler hardening, DB hardening, runtime hardening, and tests together.

4. Choose a safe edit path.
- Prefer targeted patch edits.
- Do not use full-file rewrites on core modules unless a human explicitly approves the risk.

5. Define the verification step first.
- Identify the exact test, import check, or endpoint check that will validate the change.

If any of those steps is missing, do not begin implementation.

## Mandatory Rules For Agent Edits

- No full-file rewrites on core backend modules without explicit human approval.
- No multi-file hardening batch without a restorable checkpoint.
- One change family at a time.
- After each core-file change:
  - run one verification step
  - inspect the file if anything looks abnormal
  - stop immediately on malformed output
- If the file contents look truncated, redacted, or syntactically abnormal after a write, stop further edits and begin recovery.

## Safe Execution Loop

Use this loop for risky backend changes:

1. Checkpoint
2. Make one small patch
3. Run one targeted test or import check
4. Inspect result
5. Repeat

Do not move to the next hardening family until the current one is verified.

## Recovery Playbook

If a core source file is damaged:

1. Stop editing immediately.
2. Copy the damaged file aside so the failure state is preserved for inspection.
3. Look for recovery sources in this order:
- git history
- local backup copy
- OS local history / snapshot
- generated artifacts that can help reconstruct state
- tests and API contract expectations
4. Recover the minimum working source first.
5. Only after imports and key tests pass should improvement work resume.

## Human Authorization Boundaries

Human approval is required before:

- broad refactors across core backend files
- live-schema surgery on the primary database
- deleting backups or recovery snapshots
- replacing a whole module instead of patching it
- changing the evaluation harness rules in a way that would alter research interpretation

## Preferred Verification Ladder

For backend changes, verify in this order when relevant:

1. `python3 -m py_compile server.py agents.py database.py experiments.py`
2. targeted unit tests
3. API smoke checks for affected endpoints
4. end-to-end run only after the earlier checks pass

## Incident Note Template

If something goes wrong, write a short note with:

- what file was being edited
- what recovery path existed before the edit
- what edit path was used
- what failed
- what restored the system
- what guardrail should be added next

Short notes are enough. The point is to improve the operating protocol, not assign blame.
