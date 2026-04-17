# Current vs Target Process

Last updated: 2026-04-02

This document distinguishes:
- what Hamlet's Ghost already does
- what it is clearly moving toward

The goal is to prevent the lab's self-understanding from drifting ahead of the actual implementation.

## Current Process

### 1. Task selection

Prompts do not appear from nowhere.

They currently come from the structured local prompt library in [data/prompt_library.json](../data/prompt_library.json), loaded by [experiments.py](../experiments.py), including:
- creative tasks
- business tasks
- hypothesis-linked prompt families
- a wider 100-prompt local corpus that does not require constant prompt-generation API calls

For ordinary batches, the backend builds a schedule through `build_experiment_schedule(...)`.

### 2. Generation

The lab currently supports:
- `Genesis` as the default internal generator
- `Theron` as a first-class paired generator

On paired runs, both generators can produce artifacts inside the same packet.

That means the lab can now natively compare:
- Genesis artifact
- Theron artifact

without treating Theron as a pasted outsider.

### 3. Evaluation

The lab currently has three evaluator roles:
- `Muse`
- `Athena`
- `Apollo`

Their current functional roles are:
- `Muse`: primary internal evaluator, used first
- `Athena`: internal holdout evaluator and promotion-gate counterpart
- `Apollo`: external evaluator / bounded second opinion

### 4. Model defaults

As of the current repo defaults in `.env.example`, the evaluator defaults are:
- `Muse = gpt-4.1-mini`
- `Athena = gpt-4.1-mini`
- `Apollo = gpt-4.1-mini`

Those are defaults, not destiny.

They can be changed independently through environment configuration.

### 5. Disagreement handling

The lab now supports a real disagreement-review flow.

If a paired packet produces meaningful disagreement across:
- Muse
- Athena
- Apollo

then that packet can enter the disagreement queue.

The batch does not need to stop.

The current intended rhythm is:
- run the batch
- collect disagreement packets
- review them later
- store human judgment as characterization data and judgment-memory input

### 6. Human judgment

The human role is not an interruption to the lab.
It is a calibration layer above the run loop.

The human question is intentionally simple:
- which was better?
- why?

That judgment is now storable as comparison-review memory, attributed reason-tags, and judgment-wiki evidence instead of being lost in chat.

### 7. Research memory state

What is real:
- the judgment wiki compiler exists
- seeded taste vocabulary exists
- compiled taxonomy output exists
- evaluator characterization output exists

What is still thin:
- packet-backed concept promotion
- strong refinement histories from repeated human review
- enough reviewed packets for calibration pages to become dense

### 8. Council state

The council exists only partially in implementation right now.

What is real:
- council history storage exists
- manual council triggering exists in a lightweight form

What is not yet real:
- true daily scheduled council synthesis
- automatic daily report delivery
- a mature council packet that synthesizes the whole day without manual prompting

So the current council is still more manual than operational.

## Target Process

### 1. Full batch flow

The target batch flow is:
1. Build a schedule from the local prompt library
2. Run Genesis and Theron on selected paired tasks
3. Score with Muse, Athena, and Apollo
4. Let the batch complete even when disagreements exist
5. Queue disagreement packets for later human review
6. Store human preference and rationale as characterization data
7. Compile that data into wiki, taxonomy, and characterization outputs
8. Fold the resulting lessons back into future research framing

This means disagreement should be informative, not blocking.

### 2. Human review cadence

The target is not constant interruption.

The target is:
- unresolved disagreement packets accumulate during the run
- the human reviews them after the batch
- at minimum, the human reviews them at least once per day

That gives the lab:
- uninterrupted throughput
- delayed but real human characterization
- structured memory of taste disagreement
- a path from packet evidence to revisable doctrine

### 3. Daily synthesis

The target council loop is:
- once per day, or once per completed batch
- summarize runs
- summarize disagreements
- summarize human characterization inputs
- summarize model/evaluator drift
- summarize what changed in the wiki and taxonomy
- produce a short report for the human operator

### 4. Memory promotion

The target memory flow is:
- packet evidence enters the wiki quickly
- repeated human signals become concepts slowly
- promoted concepts enter taxonomy only after explicit gates
- evaluator alignment enters characterization outputs as its own surface

### 5. First and final principles

The long-term shape is not:
- models acting in isolation
- the human arriving only at the end

It is:
- the lab generates
- the evaluators disagree
- the human calibrates
- memory compiles
- the council synthesizes
- principles are refined collaboratively and revisably

That is how Hamlet's Ghost becomes more than a benchmark harness.

## Practical Summary

### Already true
- task scheduling exists
- Genesis exists
- Theron exists as a native generator
- Muse exists
- Athena exists
- Apollo exists
- paired packets exist
- disagreement queue exists
- human comparison reviews can now be stored
- judgment wiki compilation exists
- compiled taxonomy exists
- evaluator characterization output exists

### Not yet fully true
- automatic delivery of disagreement packets without operator initiation
- automatic ingestion of human replies from Telegram
- real daily council scheduling
- automatic daily council delivery
- dense enough reviewed evidence for the taxonomy to become mostly empirical rather than seeded

## Working Mental Model

The cleanest current mental model is:

Hamlet's Ghost runs experiments without waiting for human judgment.
When judges disagree in meaningful ways, it preserves those packets for later human characterization.
That calibration is not an exception to the lab.
It is one of the lab's native organs.
The resulting judgments should accumulate into reflective memory first and doctrine only later.
