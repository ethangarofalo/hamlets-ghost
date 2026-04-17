# Hamlet's Ghost — Research Program

> This file is the org code. Humans write it. Agents execute it.
> It defines how the lab runs, what counts as evidence, and how judgment becomes memory without becoming dogma too early.

## Mission

Hamlet's Ghost is an internal research engine for comparative AI judgment.

Its job is to:
- compare rival model voices under shared prompts and constraints
- preserve where automated judges agree and disagree
- use human review as a characterization reference
- turn repeated panel preference into durable but revisable knowledge

The animating research question is:

> Which artifacts do humans prefer when machines disagree, and what does that reveal about panel preference, human alignment, and evaluator drift?

See also:
- `README.md` for the repo-level doctrine
- `docs/current-vs-target-process.md` for the implemented versus intended lab flow
- `docs/judgment-wiki.md` for the memory architecture
- `docs/prompt-compiler-architecture.md` for the productization path from lab findings to a governed prompt compiler
- `docs/prompt-science-method.md` for the multi-variable method that keeps prompt optimization empirical instead of ideological
- `docs/backend-safety-protocol.md` for preflight and recovery requirements before risky backend edits
- `docs/external-agent-rollout.md` for the staged authority model for Theron and Apollo

## Source Safety

The lab is only useful if the source tree stays recoverable.

Before nontrivial backend work on core modules:
- confirm rollback or backup path
- make one change family at a time
- verify after each step before continuing
- checkpoint in git before risky edits

Do not trade reversibility for speed on:
- `server.py`
- `database.py`
- `agents.py`
- `judgment_wiki.py`

## Architecture: Four Layers

### Layer 1: Tasking

Tasks come from the structured prompt corpus in `data/prompt_library.json`.

Each task carries:
- lane
- prompt
- constraints
- family
- hypothesis
- difficulty
- human judgment priority

The scheduler in `experiments.py` exists to broaden evidence, not to manufacture novelty for novelty's sake.

### Layer 2: Generation

The lab currently compares:
- `Genesis` as the default internal generator
- `Theron` as the bounded paired external generator

The preferred research unit is the explicit packet:
- same prompt
- same constraints
- same lane
- same family
- one Genesis artifact
- one Theron artifact

Single-generator runs still exist, but paired packets are the clearest path to comparative judgment.

### Layer 3: Evaluation

The evaluator organism currently includes:
- `Muse` as the first reader of possibility
- `Athena` as the skeptical internal holdout
- `Apollo` as the bounded outside judge

Evaluation is not truth. It is structured pressure.

The lab tracks:
- composite scores
- evaluator disagreement
- constraint checks
- parse failures
- trace/provenance

Promotion statuses like `candidate` and `shadow` are internal research bookkeeping, not product claims or deployment guarantees.

### Layer 4: Memory and Governance

The lab now has three memory surfaces:
- SQLite as the operational record
- `wiki/` as reflective judgment memory
- `taxonomy/` and `calibration/` as distilled panel-preference findings and evaluator characterization output

Within `wiki/`, memory should remain historically legible:
- lesson pages should show what changed and why
- evaluator pages should accumulate revision history rather than only current posture
- useful council memos should be filed back into memory
- a lint surface should periodically flag weak, stale, or under-evidenced beliefs

Human review sits above the evaluator layer and below rule characterization.

The human role is:
- characterization reference
- adjudicator of close or disputed artifacts
- source of reusable preference vocabulary

## Core Loop

```
LOOP:
  1. Select the next task or explicit paired packet
  2. Generate one or more artifacts under shared constraints
  3. Score with Muse, Athena, and Apollo where configured
  4. Record packet provenance, traces, and disagreement structure
  5. Queue high-value disagreements for later human review
  6. Store human preference, rationale, and reason-tags
  7. Compile reflective memory into wiki / taxonomy / characterization outputs
  8. Update working beliefs only when repeated evidence justifies it
```

The loop should increase judgment quality, not just throughput.

## Evaluation Harness

Creative scoring dimensions:
- `Novelty`
- `Surprise`
- `Value`
- `Elaboration`
- `Coherence`

Business scoring dimensions add:
- `Actionability`
- `Brand fit`
- `Factual reliability`

Important rule:
- evaluators are instruments, not sovereigns
- disagreement is evidence
- human comparison outranks elegant evaluator consensus

## Internal Status Logic

The lab still uses internal status fields to keep the run loop disciplined:
- `discard`
- `kept`
- `promoted`
- `candidate`
- `shadow`
- `invalid`

These statuses mean:
- whether the artifact survived the current research pass
- whether it deserves further inspection
- whether it should be routed toward human review

They do not mean:
- customer-ready
- market-validated
- final truth

## Panel-Preference Memory Rules

The wiki and taxonomy must remain conservative.

Rules:
- repeated evidence matters more than eloquent summaries
- one-off observations do not become doctrine
- provenance and epistemic status stay separate
- seeded vocabulary is allowed, but promoted findings must be earned
- free-text rationale and structured tags should coexist

Promotion toward stable taxonomy requires more than recurrence.
It should require:
- distinct packets
- cross-prompt-family evidence
- cross-model-family evidence
- structural identity
- human characterization for the highest tiers

## Human Review

Human review should answer a simple question:
- which artifact was better?
- why?

But the lab should store more than a verdict.

Human review should ideally yield:
- preferred artifact
- free-text rationale
- structured reason-tags with artifact attribution (`winner`, `loser`, `both` where possible)
- quoted excerpts tied to those tags when the human can point to the sentence that earned the judgment

Those tags are not bureaucracy.
They are the beginnings of taste memory.

## Taste Characterization Of Judges

The evaluators cannot be understood by slogans like "reward humane writing."
That hides proxy worship:
- seriousness mistaken for value
- polish mistaken for dignity
- repetition mistaken for development
- prestige aura mistaken for beauty

The lab should characterize judges through contrast, situation, and comparison.

That means:
- probe with near-neighbor pairs, not abstract exhortation
- record not just human disagreement, but the panel preference that produced it
- judge artifacts relative to audience, relation, stakes, and rhetorical obligations
- distinguish public rhetoric from private writing rather than rewarding one style everywhere
- preserve reread reversals because durable worth and first-pass impressiveness are not the same thing

The task is not to make evaluators admire approved language.
It is to map when the panel rewards language that honors reality, relation, and stakes, and when it rewards language that merely performs those things.

Practical consequence:
- build contrast sets where one artifact is stronger for ethical or rhetorical reasons, not merely stylistic ones
- maintain a divergence ledger for recurring human-vs-judge errors
- treat evaluator failure modes as characterization findings
- let panel preference be conditioned by situation, not flattened into universal elegance

## Council Role

The council exists to synthesize preference cartography, not to govern.

Its job is to:
- summarize which characterization labels are accumulating
- identify recurring disagreement
- propose next hypotheses to test
- warn when the lab is becoming overconfident

The council does not approve rule promotions or redefine quality by fiat.

## Productization Path

The product that should emerge from this lab is not "better writing."
It is a prompt compiler.

That compiler should:
- accept a rough user request
- diagnose audience, goal, stakes, relation, and form
- select empirically characterized prompt-transformation rules
- emit a stronger compiled prompt for Genesis, Theron, or a downstream customer model
- preserve enough traceability that the lab can test whether the compilation actually helped

The lab remains the place where prompt-transformation rules are discovered and characterized.
The compiler becomes the place where validated rules are applied.

Important:
- no prompt-compilation rule becomes default product behavior until it beats naive prompting under blinded comparative review
- prompt compilation should preserve user intention, not overwrite it with house style
- a clean compiled prompt is not success; interpretable panel-preference lift, compared against human review, is success
- model-specific wins are routing knowledge, not universal doctrine
- family-specific wins are useful compiler policy, but they should not be promoted as cross-family truth without replication

## Prompt Science Method

The lab should explicitly treat prompt optimization as a multi-variable discipline.

The important variables are:
- generator or model family
- lane
- prompt family
- rhetorical form
- transformation rule or policy variant
- evaluator panel response
- human review outcome

The clean scientific unit is not "this compiled prompt seemed better."
It is:
- this intervention produced panel-preferred results
- for this family
- on this model
- under this evaluation setup
- and human review labeled that preference aligned, divergent, LLM-specific, human-specific, neutral, or insufficient

Every prompt-transformation rule should carry a scope claim:
- `universal`
- `family_specific`
- `model_specific`

Those scopes mean:
- universal rules are rare and require cross-family and cross-model evidence
- family-specific rules are productively local and should shape compiler routing for matching tasks
- model-specific rules are valuable adaptation knowledge, but they are not doctrine

The lab should prefer experiments that isolate one change at a time:
- raw vs compiled
- rule on vs rule off
- variant A vs variant B
- replication across model families

The council's job inside this method is not to declare winners in the abstract.
It is to name uncertainty honestly and propose the next experiment that most efficiently separates:
- universal signal
- family signal
- model signal

## Working Principles

- Preserve disagreement instead of flattening it too early.
- Treat human judgment as a serious comparison signal, not clerical cleanup.
- Keep the ontology smaller than the evidence.
- Let memory become inspectable before it becomes authoritative.
- Build a better judgment engine before attempting to build a broader product.

## Provenance Requirements

Every packet or experiment should preserve:
- prompt family
- lane
- condition
- packet id
- role id
- generation protocol
- generator/evaluator provider and model
- source context
- process trace
- human review metadata where available
- epoch

If judgment becomes hard to audit, the lab is losing its reason to exist.
