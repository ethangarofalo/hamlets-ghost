# Hermes Overseer Map for Creativity Lab

Last updated: 2026-04-01

## Purpose

Define how a Hermes agent can become maximally useful to the Creativity Lab without collapsing the lab into a closed loop of self-approval.

The core principle is:
- Hermes should automate operations, evidence synthesis, and disciplined iteration.
- Humans should retain authority over framing, calibration, and judgments where creativity value is not reducible to current metrics.

## Important distinction

The current codebase already has a `hermes` role, but that role is an independent evaluator / holdout scorer.

That should remain separate from a future **Hermes Overseer**.

Recommended naming:
- `hermes_evaluator`: current second-opinion scorer
- `hermes_overseer`: future agentic lab operator

Do not overload one agent identity with both responsibilities.

## What the Hermes Overseer should own

### 1. Experiment operations
Hermes Overseer should:
- schedule experiment batches
- choose the next queued experiment from an approved design space
- enforce budgets, stop criteria, and cooldowns
- monitor parse failures, fallback rates, verifier failures, and cost spikes
- pause lanes automatically when reliability drops below threshold

### 2. Evidence assembly
Hermes Overseer should:
- build evidence packets mechanically from DB state
- compute batch summaries, family summaries, divergence summaries, and cost summaries
- surface anomalies worth human inspection
- prepare candidate review queues for human calibration

### 3. Safe optimization proposals
Hermes Overseer should:
- propose small, testable protocol changes
- prefer paired tests over broad rewrites
- propose one-variable-at-a-time prompt-family adjustments
- open a recommendation only when linked to observed failure modes

Hermes Overseer should not directly rewrite the fixed evaluation harness on its own authority.

### 4. Governance and memory
Hermes Overseer should:
- track which council recommendations were actually tried
- track whether recommendations improved results or only changed traces
- maintain an audit trail for prompt changes, protocol changes, evaluator changes, and promotion decisions
- keep a ledger of approved, rejected, and still-unvalidated policy ideas

### 5. Human review routing
Hermes Overseer should:
- decide which artifacts most need human review
- sample not only top outputs, but also discarded and ambiguous ones
- prioritize reviews where MUSE/HERMES divergence is high
- prioritize reviews where novelty appears high but usefulness or trust may be fragile

## What must stay human-owned

### 1. Research framing
Humans should define:
- the real research question
- what counts as an interesting finding
- when a framing shift is scientifically meaningful versus just rhetorically attractive

### 2. Creativity calibration
Humans should remain the reality anchor for:
- whether something is genuinely alive or only decoratively strange
- whether novelty is useful novelty
- whether “humanized” and “creative” are being confused
- whether an artifact is worth saving despite imperfect metric performance

### 3. Promotion beyond shadow
Suggested authority split:
- candidate -> shadow: automated, with gates
- shadow -> validated: human approval required
- validated -> production: human approval required

### 4. Evaluator trust resets
If human calibration suggests MUSE or hermes_evaluator is drifting, humans should authorize:
- evaluator retuning
- evaluator freeze decisions
- rubric changes
- interpretation changes to published findings

## Best operating model

## A. Role stack
1. GENESIS
   Generates artifacts.
2. MUSE
   Primary triage evaluator.
3. HERMES Evaluator
   Independent holdout evaluator.
4. Hermes Overseer
   Runs the lab as an operations-and-governance agent.
5. Human Operator
   Owns framing, calibration, and final validation.

## B. Daily loop
1. Hermes Overseer checks lab health.
2. If reliability is acceptable, it launches approved experiments.
3. It gathers outputs, costs, parse failures, verifier results, and evaluator divergence.
4. It updates family-level summaries and trend summaries.
5. It routes selected artifacts into a human calibration queue.
6. It prepares a short decision memo:
   - strongest supported finding
   - weakest unsupported claim
   - top operational bottleneck
   - best next small experiment
7. Human reviews the memo and either:
   - approves next run
   - requests more evidence
   - changes priorities
   - freezes a lane

## C. Event-driven interrupts
Hermes Overseer should interrupt the normal loop when:
- MUSE/HERMES divergence stays above threshold
- baseline canaries drift materially
- verifier machine-checked share falls
- cost per promoted artifact spikes
- fallback or parse-failure rate rises sharply
- human calibration contradicts evaluator confidence

## Recommended authority matrix

### Hermes Overseer can do autonomously
- start/stop approved batches within budget
- create evidence packets
- generate dashboards and summaries
- nominate artifacts for human review
- recommend protocol changes
- pause unsafe or low-reliability lanes
- open implementation tasks for instrumentation and observability gaps

### Hermes Overseer can do only with human approval
- change prompt policies that affect validated or production flows
- alter evaluator prompts or weights
- promote from shadow to validated
- redefine task families or research framing
- publish claims externally

### Hermes Overseer must never do alone
- declare creativity success purely from evaluator scores
- remove human calibration from the loop
- broaden into speculative product strategy without evidence
- rewrite the evaluation harness and then claim improved science from it

## The most useful Hermes contribution to this project

Hermes is most useful when acting as the lab’s:
- operations lead
- evidence assembler
- accountability layer
- calibration queue manager
- recommendation engine for small, testable next steps

Hermes is less useful when acting as:
- final arbiter of creativity
- sole framer of research questions
- broad visionary replacing human taste and judgment

## Concrete product shape

### Phase 1: Overseer as copilot on the existing backend
Add a new overseer service that reads from the current SQLite DB and existing API endpoints.

Responsibilities:
- health checks
- batch launch proposals
- review queue generation
- council packet generation
- anomaly alerts
- daily memo generation

No autonomous code changes yet.

### Phase 2: Overseer with bounded write powers
Allow Hermes Overseer to:
- update policy ledger entries
- queue experiments from approved templates
- pause lanes on explicit thresholds
- create implementation tickets for instrumentation gaps

Still no ungated evaluator or rubric edits.

### Phase 3: Overseer with supervised backend improvement powers
Allow Hermes Overseer to inspect code, propose patches, run tests, and prepare PRs for:
- observability improvements
- reliability fixes
- experiment tooling
- evidence-packet quality
- human-review workflow improvements

Human reviews and merges.

## Best first implementation targets

1. Separate current Hermes evaluator from future Overseer naming and config.
2. Add an explicit `overseer` module with read-only access first.
3. Add a daily/weekly memo generator grounded in the roadmap questions.
4. Add a calibration queue selector that samples promoted, discarded, and disagreement cases.
5. Add lane health thresholds with automatic pause recommendations.
6. Add a recommendation ledger that links proposed changes to later outcomes.
7. Add a human-decision inbox for go/no-go calls.

## Good first questions for Hermes Overseer to answer

- Which lane is learning fastest right now?
- Where is the lab mistaking execution reliability for creativity improvement?
- Which prompt family has the strongest evidence that creativity helps?
- Where do human judgments disagree most with MUSE or hermes_evaluator?
- Which expensive stage is not paying for itself?
- What is the next smallest experiment with the highest information value?

## Bottom line

A strong Hermes Overseer for this lab should not replace human judgment.
It should increase the quality, discipline, and speed of the lab around the places where human judgment matters most.

The best version is not “AI runs the creativity lab alone.”
The best version is “AI keeps the lab honest, legible, and fast, while humans remain the calibration anchor for meaningfully creative success.”
