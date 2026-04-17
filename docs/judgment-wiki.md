# Judgment Wiki

The judgment wiki is Hamlet's Ghost's living memory of what quality looks like, where judges disagree, and what humans keep teaching the system to notice.

## Purpose

The wiki is not the source of truth. SQLite remains the operational record. The wiki is the reflective layer that turns packet history into inspectable, revisable knowledge.

The reflective layer now has two compiled siblings:
- `taxonomy/` for promoted, machine-readable doctrine
- `calibration/` for evaluator alignment summaries

And two internal maintenance surfaces inside `wiki/` itself:
- `memos/` for filed council syntheses and research notes
- `lint/` for conservative sanity checks on weak or under-evidenced memory

The goal is not to build a generic research notebook. The goal is to preserve:

- packet evidence
- emerging lessons
- model voice profiles
- evaluator credibility
- human-confirmed judgment signals
- revision history for lessons and evaluators
- contradiction tracking where judges, families, and humans do not yet cohere
- the blind spots judges repeatedly reveal when humans correct them

## V1 Page Types

V1 stays intentionally narrow:

1. `Packet outcome pages`
   Each explicit packet gets a durable record with the prompt, artifacts, judge preferences, and any human rationale.

2. `Model voice pages`
   Each generator accumulates a profile of recurring strengths, likely weak spots, and representative evidence.

3. `Evaluator pages`
   Each judge accumulates a visible track record rather than behaving like an anonymous score dispenser.

4. `Task family pages`
   Families aggregate packet evidence and show what the lab is currently learning about a recurring prompt type.

5. `Lesson pages`
   Lessons are the most important pages. They should stay conservative, evidence-backed, and explicitly revisable.

V1.5 adds two synthesis layers once repeated review begins to accumulate:

6. `Concept pages`
   Repeated human reason-tags can become part of the lab's quality vocabulary when they recur enough to deserve their own evidence trail.

7. `Weekly synthesis pages`
   Short dated summaries capture what strengthened, what stayed contested, and which human signals keep recurring.

## Compiler Loop

The compiler should remain conservative:

1. Read current-epoch experiments and reviews from the database.
2. Build packet pages from explicit pairings only.
3. Link packet evidence into family, model, evaluator, and lesson pages.
4. Increase confidence slowly. Repeated evidence matters more than eloquent summaries.
5. Distill promoted concepts into `taxonomy/` only after evidence clears explicit gates, including prompt-family breadth and model-family breadth.
6. Track judge/human alignment separately in `calibration/` so evaluator credibility stays visible.
7. File durable council memos back into `wiki/memos/` so synthesis compounds instead of evaporating.
8. Emit a lint pass that flags weak, stale, or insufficiently grounded memory.
9. Preserve divergence-ledger evidence so evaluator reform is driven by recurring failure classes rather than by vague dissatisfaction.

## Design Rules

- Prefer evidence accumulation over ontology expansion.
- Keep uncertainty visible.
- Do not turn one-off observations into doctrine.
- Let structured tags and human rationale coexist.
- Prefer attributed tags and quoted excerpts over free-floating labels when human review can provide them.
- Treat the wiki as living judgment memory, not documentation exhaust.
- Promote repeated human reason-tags into concepts slowly, only when they are evidence-bearing rather than fashionable.
- Keep provenance and epistemic status separate.
- Do not treat prompt-family diversity as a substitute for model-family diversity when promoting doctrine.
- Let the wiki remember; let the taxonomy decide only after memory has earned it.
- Preserve contradiction rather than smoothing it away.
- Prefer revision history over silent overwrite.
- Let evaluator failure memory become curriculum, not just postmortem.

## Entrypoint

```bash
cd hamlets-ghost
./.venv/bin/python scripts/compile_judgment_wiki.py
```
