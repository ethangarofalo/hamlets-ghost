# Status as of 2026-04-17

This document is updated on the first of every month or when any claim in it becomes false, whichever comes first.

## Current Empirical State

- Rules under watch: 1 (`diagnosis::make_audience_explicit`)
- Compiler-compare packets in rule evidence: 4
- Eligible slices: 3 (1 suppressed for dual constraint-fail)
- Prompt families with support slices: 2
- Decisive human reviews: 0
- Characterized rules: 0 (all `insufficient_data`)

These numbers come from the current `scripts/promote_rules.py` dry-run report.

## Implemented

- Dual-generator orchestration exists for Genesis and Theron-style external generation packets; see `server.py` and `scripts/build_theron_packet.py`.
- The evaluator panel records Muse, Athena, and Apollo configuration, including `muse_athena_apollo_v1_independent` when Apollo is actually independent; see `agents.py`.
- Compiler-compare experiments run paired raw and compiled prompt variants through `/api/experiment/compiler-compare`; see `server.py`.
- Rule evidence persists `panel_version`, `human_signal_attribution_method`, evaluator signal, and human signal; see `data/prompt_rule_evidence_schema.json`.
- Dual constraint-fail slices are suppressed from support and characterization math while still reported; see `database.py` and `scripts/promote_rules.py`.
- Rule promotion is dry-run only: proposals are computed and displayed, but statuses are not automatically changed; see `scripts/promote_rules.py`.
- Characterization labels and thresholds are implemented, including `characterization_min_human: 5`; see `database.py`.
- Admin-token authentication protects write endpoints and `/api/artifact/{id}`; see `server.py`.
- Preflight runs git status, compile checks, unit tests, `node --check`, JSON validation, and ruff; see `scripts/preflight.sh`.
- `/api/rules/promotions` feeds the Compiler Learning UI strip, including characterization chips and suppressed dual-fail notes; see `server.py` and `static/app.js`.

## Prototype

- Apollo independence routing is wired, but behavioral validation against accumulated live packets is pending.
- Human-signal attribution currently exercises `uniform`; `per_rule`, `primary_only`, and `none` are declared in schema but not yet used as normal review paths.
- Dimension-correlation and evaluator-drift analysis surfaces exist in code and tests, but they have not yet produced a stable real-data finding.
- The public packet exhibit is curated, not complete. It supports verification of current claims, not full corpus analysis.

## Aspirational

- Automatic rule promotion is intentionally deferred; human approval remains required by design.
- Domain expansion beyond the current creative substrate is pending a separate build and evidence plan.
- A falsifiability dashboard should track per-rule disconfirmation and label stability over time.
- A paid or otherwise independent human-reviewer pipeline is not built.
- Postgres migration is deferred until the experiment count or concurrency profile justifies it.
- The empirical state block in this file should eventually be generated from the database at doc-build time.

## Known Broken, Disabled, Or Deleted

- `scout` appears in orchestration trace as `not_implemented`; it is a disabled placeholder, not an active agent.
- `constraint_recovery_rate` and `critique_help_rate` are not live status metrics in the current public surface; they appear only in analytics test fixtures.
- The public branch intentionally omits the private database, `.env`, recovery artifacts, and the full packet corpus.

## Drift Commitment

This document is not auto-generated. Drift is possible. If you find a claim here that is false or stale, open an issue and reference the exact line. Corrections are higher-priority than new features.
