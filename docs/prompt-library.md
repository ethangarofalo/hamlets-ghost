# Prompt Library

Last updated: 2026-04-03

Hamlet's Ghost now uses a structured local prompt corpus instead of relying only on hardcoded Python lists.

## Why

The lab needs more prompt breadth than a tiny built-in exam can provide, but it does not need to burn APIs continuously just to invent prompts.

The local prompt library gives the lab:
- broader coverage
- repeatable experiments
- lower operating cost
- versioned prompt memory
- room for future council and human-approved additions
- a stable task substrate for the research engine and judgment-memory loop

## Current Shape

The corpus lives in [data/prompt_library.json](../data/prompt_library.json).

Version:
- `2026-04-03`

Current counts:
- `40` creative constrained prompts
- `10` creative open-ended prompts
- `10` creative transformational prompts
- `40` business prompts

Total:
- `100` prompts

## Prompt Record Format

Each prompt record now stores:
- `id`
- `lane`
- `prompt`
- `creativity_type`
- `constraints`
- `track`
- `family`
- `hypothesis`
- `status`
- `difficulty`
- `provenance`
- `human_judgment_priority`
- `tags`
- `notes`

Some of those metadata fields can be explicitly stored later, but they are already normalized by the loader today so every prompt has a richer experimental profile immediately.

## How It Is Used

[experiments.py](../experiments.py) loads the JSON corpus and exposes:
- `CREATIVE_CONSTRAINED`
- `CREATIVE_OPEN`
- `CREATIVE_TRANSFORMATIONAL`
- `BUSINESS_TASKS`
- `ALL_TASKS`

The existing scheduler then samples from that structured library through `build_experiment_schedule(...)`.

Helper accessors now also exist for:
- active tasks
- human-judgment-priority tasks

The important framing is:
- the prompt library is not a content product
- it is the lab's task substrate
- its job is to create comparable evidence, disagreement, and human-characterization opportunities

## Next Good Moves

- Add room for council-proposed prompts that require human approval before becoming active.
- Build a lightweight operator surface for browsing and approving prompts without editing JSON by hand.
- Add per-prompt performance history so the lab can see which prompts consistently create evaluator disagreement or useful human characterization.
