# 2026-04-17 Pivot: Characterization, Not Taste Education

Hamlet's Ghost is now framed as a comparative-judgment instrument for characterizing LLM aesthetic preference.

The pivot is conceptual, not a schema reset.
The lab still runs rival outputs, evaluator panels, human review, rule evidence, and promotion proposals.
What changed is the claim attached to that evidence.

## What Changed

The old framing implied that the lab was educating evaluators toward better taste.
That was too strong.
It risked treating human preference as reference signal and panel movement as moral progress.

The new framing treats every judgment source as an object of study:
- the panel has preferences
- humans have preferences
- prompt transformations can increase panel preference
- human review characterizes whether that panel preference is aligned, divergent, LLM-specific, human-specific, neutral, or not yet knowable

This changes the language of the project:
- "characterization reference" becomes "characterization reference"
- "reference signal" becomes "reference signal" or "comparison axis"
- "panel-preference lift" becomes "panel-preference lift"
- "taste characterization" becomes "taste characterization"
- "panel-preference findings" becomes "panel-preference findings"

## What Did Not Change

The existing storage semantics remain stable.
Do not rename database columns such as:
- `human_signal`
- `human_win_rate`
- `active_human_decisive`
- `calibration_metrics`

Those names are historical implementation vocabulary.
The interpretation shifts in documentation and API surfaces, while the persisted data stays compatible.

Apollo v1 independence also stays.
Panel independence still matters because the lab needs to know whether a preference repeats across evaluator roles rather than merely echoing one judge.

## New Product Thesis

The product is not "better writing" in the abstract.

The product thesis is:

> Pipelines with LLM judges need instruments that show what their judges systematically prefer, where those preferences align with humans, and where they drift into model-local taste.

The best early market is any workflow with LLM judges in the loop:
- evaluation harnesses
- RLHF and preference-data pipelines
- automated grading
- prompt-compiler validation
- creative or business-content review systems

The promise is not universal truth.
The promise is legibility: panel-preference findings with human comparison axes.

## Rule Characterization Labels

Rules now carry a characterization label:
- `aligned`: panel prefers the rule and humans also prefer it
- `divergent`: panel prefers the rule while humans disprefer it
- `llm_specific`: panel prefers the rule while humans are neutral or mixed
- `human_specific`: humans prefer the rule but the panel does not
- `neutral`: neither side shows a strong preference
- `insufficient_data`: too few decisive human reviews exist

A rule can still receive `recommendation: promote` while being `characterization: divergent`.
That is not a contradiction.
It means the rule produces panel-preferred output and the lab should treat that as an important finding, not automatically as a user-facing default.

## What a `divergent` Label Authorizes

Written before the first one fires, on purpose.

> A `divergent` characterization is an escalation signal, not an automatic demotion or correction. It authorizes dashboard prominence, wiki annotation, and human review of the rule/panel/reviewer relationship. It does not by itself change rule status, evaluator prompts, or compiler behavior.

The reason this sentence exists in advance is that `divergent` is the label most likely to produce a reflexive interpretation — "the panel is wrong" — and that interpretation is only one of several possibilities. A `divergent` label can mean any of:

- panel pathology (the judges share a bias the rule is exploiting)
- human inconsistency (the reviewers disagree with each other more than with the panel)
- a real model-family preference worth capturing for routing rather than suppressing
- a task where the human reference itself needs a second read

None of those conclusions should be drawn from the label alone. The label surfaces the split; a human decides what the split means.

## Operating Principle

Keep hypotheses alive, but label their evidence honestly.

Seeded concepts may remain in the wiki.
They are allowed as hypotheses.
But until panel evidence exists, the page should say so.
