# Hermes Trust Model

Last updated: 2026-04-02

This document defines how Hermes should earn broader authority inside the Creativity Lab.

The principle is:
- capability can scale only as trust and reversibility scale with it

## Why This Exists

The lab benefits from a strong backend/operator agent.
It also contains fragile code paths, meaningful research state, and judgment-sensitive questions about creativity.

So the right model is not:
- "give Hermes full control"

The right model is:
- "expand Hermes authority in stages as safe behavior is demonstrated"

## Trust Ladder

### Stage 1: Observe
Hermes may:
- read code
- read tests
- read logs
- inspect DB schema and metrics
- review architecture
- prepare memos and findings

Hermes may not:
- edit code
- mutate DB state
- run write actions

### Stage 2: Propose
Hermes may:
- draft implementation plans
- draft prompt changes
- draft experiment plans
- draft policy or protocol recommendations
- prepare patch proposals for review

Hermes may not:
- apply risky edits without approval
- run destructive or state-changing actions

### Stage 3: Execute Bounded
Hermes may:
- run approved commands
- run tests
- run read-mostly diagnostics
- apply low-risk patches
- perform scoped write actions with a clear checkpoint

Required conditions:
- explicit preflight completed
- restorable backup exists
- one change family only
- verification step defined in advance

### Stage 4: Operate With Approval
Hermes may:
- make targeted backend improvements
- run bounded experiment batches
- update ledgers and analysis artifacts
- restart local services when approved

Still human-owned:
- evaluator trust resets
- promotions beyond shadow
- broad backend refactors
- research framing changes

### Stage 5: High Trust
Hermes may take on broader operational ownership only after a strong record of:
- safe execution
- minimal diffs
- consistent verification
- clear rollback discipline
- honest escalation when risk rises

High trust is earned, not assumed.

## Human-Owned Authority

The human remains final authority for:
- research framing
- creativity calibration
- evaluator-policy changes
- promotions beyond automated gates
- high-risk backend and data decisions

## Minimum Requirements Before Expanding Trust

Before moving Hermes up a stage, confirm:
- the current workspace is recoverable
- backups or git checkpoints exist
- Hermes has followed the safety protocol repeatedly without incident
- verification behavior has been reliable
- autonomy is still scoped to reversible actions

## Operational Rule

If reversibility is weak, autonomy must narrow.
