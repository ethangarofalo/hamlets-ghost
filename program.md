# AI Creativity Lab — Research Program

> This file is the "org code." Humans write it. Agents execute it.
> Following the autoresearch pattern: the research protocol is a markdown file
> that defines what the agent does, how it evaluates, and when it stops.

## Mission

Discover prompt policies and dialogue protocols that increase useful novelty on specific tasks,
as estimated by evaluator agreement and validated, when available, by human judgment or business outcomes.

See also: `research-roadmap.md` for the active improvement plan, finding criteria, and sharing path.
See also: `docs/backend-safety-protocol.md` for the required preflight and recovery rules before risky backend edits.
See also: `docs/hermes-trust-model.md` for the staged authority model for backend/operator integration.

## Source Safety

The lab is only useful if the source tree stays recoverable.

Before nontrivial backend work on core modules:
- confirm rollback or backup path
- create explicit restorable copies of touched files
- make one small change family at a time
- verify after each step before continuing

Do not trade reversibility for speed on `server.py`, `database.py`, or `agents.py`.

## Architecture: Three Layers

### Layer 1: Exploration
- GENESIS generates artifacts against task prompts
- Default generation protocol is branch generation -> forced selection under tradeoff -> Socratic questioning -> revision so the process trace records actual rejected paths, not just a retrospective self-report
- Tasks are drawn from two lanes: **creative** and **business**
- Each task has a hypothesis, constraints, and success criteria
- The agent modifies only the *prompt strategy* — the evaluation harness is fixed

### Layer 2: Evaluation
- MUSE scores artifacts (internal critic — used for triage, not truth)
- HERMES scores artifacts independently (separate evaluator lane — same rubric for now, no shared context)
- Evaluator diagnostics track inter-dimension correlation, repeated-run stability, and MUSE/HERMES agreement before conclusions are trusted
- Constraint satisfaction is checked and gates promotion
- Parse failures are flagged as invalid trials, not recorded as real scores
- Results are logged to an append-only `results_log` table in SQLite
- Fixed baseline canary tasks are replayed on a cadence to measure evaluator and policy drift

### Layer 3: Deployment
- Artifacts and prompt strategies move through tiers:
  - `candidate` — generated, scored, not yet reviewed
  - `shadow` — passed automated checks, waiting for human review
  - `validated` — human-approved or A/B-tested
  - `production` — in use
- Only `validated` or `production` prompts touch real workflows
- Promotion requires: composite >= 7.0 AND constraints_met AND HERMES agrees (within 1.5 points of MUSE)

## Experiment Loop (autoresearch pattern)

```
LOOP FOREVER:
  1. Pick next task from schedule
  2. If critique_on condition: load the last relevant completed critique (same prompt, hypothesis, or prompt family)
  3. Run GENESIS with task prompt + constraints + prior feedback using the active generation protocol
  4. Store artifact with full provenance, including draft/question/revision trace when available
  5. Run MUSE and HERMES concurrently
  6. Score, check constraints, decide keep/discard/promote
  7. Log to results_log: experiment_id, composite, status, hypothesis, cost
  8. If improvement: advance the prompt strategy
  9. If regression or constraint failure: revert
  10. Check cost cap and kill criteria
  NEVER STOP unless cost cap reached or human intervenes
```

## Evaluation Harness (fixed — agents cannot modify)

Scoring dimensions (1.0–10.0):
- **Novelty** (0.25): Distance from known prior work
- **Surprise** (0.20): Apt expectation violation
- **Value** (0.25): Accomplishes something worth reading/using
- **Elaboration** (0.15): Specificity and depth of development
- **Coherence** (0.15): Internal consistency

For **business tasks**, additional dimensions:
- **Actionability**: Can someone act on this output?
- **Brand fit**: Does it match the specified voice/tone?
- **Factual reliability**: Are claims accurate?

Composite weights:
- **Creative lane**: Novelty(0.25) + Surprise(0.20) + Value(0.25) + Elaboration(0.15) + Coherence(0.15)
- **Business lane**: Novelty(0.18) + Surprise(0.12) + Value(0.18) + Elaboration(0.10) + Coherence(0.10) + Actionability(0.14) + Brand fit(0.10) + Factual reliability(0.08)

## Keep/Discard/Promote Logic

- **Discard**: composite < 6.5 OR constraints violated OR parse failure
- **Keep**: composite >= 6.5 AND constraints met
- **Promote to shadow**: composite >= 7.0 AND constraints met AND |MUSE - HERMES| < 1.5
- **Promote to validated**: human review passes OR A/B test positive

## Kill Criteria

Stop a research lane if:
- 10 consecutive discards with no improvement
- Cost exceeds lane budget
- Mean composite trending down over 20 experiments
- MUSE-HERMES divergence exceeds 2.0 consistently (evaluator unreliable)

## R&D Council (runs every N experiments)

Five roles, differentiated:
1. **Research Lead**: summarizes results, identifies uncertainty
2. **Optimizer**: proposes prompt strategy changes
3. **Skeptic**: attacks weak conclusions, detects overfitting to MUSE
4. **Product Owner**: asks whether results help the business
5. **Safety/Ops**: checks cost, risk, automation health

Council consumes:
- Last batch of experiments
- Top promoted prompts
- Failed prompts and failure modes
- Cost by lane
- Prior council decisions (short memory)

Council outputs:
- 3 proposed changes
- 1 thing to stop
- 1 thing to scale
- 1 short research memo

Council CANNOT directly modify production prompts without gated promotion.

## Provenance Requirements

Every experiment must record:
- `hypothesis_id`: what belief is being tested
- `prompt_version`: hash of the system prompt used
- `evaluator_version`: hash of the internal evaluator prompt used
- `holdout_evaluator_version`: hash of the independent holdout evaluator prompt used
- `model_version`: per-role backend + model routing used for the run
- `source_context`: any documents or prior artifacts referenced
- `generation_protocol`: one-shot | socratic_v1 | socratic_v2 | future variants
- `error_traceback`: full traceback on failure, not just "error"
- `promotion_status`: candidate | shadow | validated | production
