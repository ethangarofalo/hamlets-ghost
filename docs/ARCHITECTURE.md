# Truth-Seeking Architecture

This document inventories the epistemic commitments Hamlet's Ghost implements as architecture. It is not a feature list and not a roadmap. Its purpose is narrower: to show where the lab refuses unearned conclusions, where human judgment remains structurally distinct from model judgment, and where methodological promises are backed by files a skeptical reader can inspect.

## First Principles

Human reviewers are structurally separate voters, not inputs to a combined score. No rule can be characterized, promoted, or demoted from panel signal alone. Pre-registered hypotheses are immutable after their date. Seeded concepts are distinguishable from earned concepts at the data-structure level. Measurement authorization is decided before measurement, not after.

These principles are not decorations around the system. They are the conditions under which the system's outputs can be read as evidence rather than as taste laundered through automation.

## Named Commitments

### `insufficient_data` Is A First-Class Label

Statement: a rule that lacks enough decisive human review receives `insufficient_data`, even when the evaluator panel visibly leans one way.

The point of this label is to prevent panel self-consistency from masquerading as characterization. An LLM panel can produce a stable preference before humans have weighed in, but stability is not alignment. The lab therefore distinguishes "the panel prefers this" from "we have enough human signal to say what kind of preference this is."

Implementation: the allowed characterization labels are declared in `database.py:45`, and `_rule_characterization()` returns `insufficient_data` before considering alignment, divergence, or neutrality when the human-review floor is not met (`database.py:3050`, `database.py:3057`). The evidence schema also documents `insufficient_data` as the label for too few decisive human reviews (`data/prompt_rule_evidence_schema.json:8`).

Violation: any UI, script, wiki page, or essay that treats a panel-leaning rule as `aligned`, `divergent`, or `llm_specific` before the human floor is met violates this commitment.

### Human Characterization Requires Five Decisive Reviews

Statement: the default minimum for rule characterization is five decisive human reviews.

The number is intentionally small enough for an early-stage lab to reach and large enough to stop a single satisfying review from becoming doctrine. It is not a claim that five reviewers settle the matter. It is the first threshold at which the lab permits itself to compute a label other than `insufficient_data`.

Implementation: `PROMPT_RULE_PROMOTION_DEFAULTS` sets `characterization_min_human` to `5` (`database.py:32`, `database.py:43`). `_rule_characterization()` reads that threshold before computing any panel-vs-human label (`database.py:3057`). The promotion script exposes the same threshold in its report configuration (`scripts/promote_rules.py:45`).

Violation: changing a rule's characterization on the basis of one, two, three, or four decisive human reviews would violate the current architecture. Lowering the threshold may become justified, but doing so must be an explicit methodological change, not an incidental code path.

### Dual Constraint-Fail Slices Do Not Create Support

Statement: when both raw and compiled outputs fail constraints, the slice is suppressed from support and characterization math.

A comparison between two failures is not evidence that a rule helped. It may still be useful as an operational warning, because it shows a prompt or transformation created a degenerate comparison. But the rule should not receive support for winning a race in which neither artifact satisfied the constraint.

Implementation: `compute_rule_promotion_proposals()` computes `eligible_slices` separately from `total_slices` and counts `suppressed_dual_constraint_fail` when both compared outputs have `constraint_fail` status (`database.py:3218`, `database.py:3225`). The support-packet, support-family, model-family, human-signal, and evaluator-signal aggregates all guard against dual constraint-fail slices (`database.py:3231`, `database.py:3255`, `database.py:3275`). The promotion script prints suppressed dual constraint-fail slices rather than hiding them (`scripts/promote_rules.py:80`).

Violation: counting a dual constraint-fail slice as support for a prompt rule, or silently dropping it without reporting the suppression, violates this commitment.

### Pre-Registered Hypotheses Are Immutable

Statement: pre-registered hypothesis notes are not edited after their date; updates appear as new dated sections or companion notes.

This commitment is process-level rather than fully encoded in code. The lab cannot yet technically prevent a later edit to a markdown file. The point of writing the rule down anyway is to make the discipline inspectable before a tempting counterexample appears. A pre-registration that changes after observation is no longer a pre-registration; it becomes a story about what the operator wishes had been predicted.

Implementation: the first post-pivot evidence note states the rule directly in its "Pre-Registration Integrity" section (`docs/evidence-note-2026-04-17-make-audience-explicit.md:27`). The public timeline also records that rule as part of the dated narrative (`docs/TIMELINE.md`).

Violation: editing the original hypothesis after human review lands, instead of appending a dated update or creating a companion note, violates this commitment even if the final document reads more elegantly.

### `divergent` Authorizes Escalation, Not Automatic Correction

Statement: a `divergent` label authorizes prominence and review; it does not automatically demote a rule, rewrite evaluator prompts, or change compiler behavior.

This is the authorization-before-observation rule. It was written before the first `divergent` label fired because surprising measurements tempt systems into retroactive policy. A divergent label can mean panel pathology, human inconsistency, a real model-family preference useful for routing, or a task where the human reference needs a second read. The label surfaces the split; it does not settle its meaning.

Implementation: the evidence schema defines `divergent_authorization` in the `characterization_axes` block (`data/prompt_rule_evidence_schema.json:4`, `data/prompt_rule_evidence_schema.json:16`). The pivot memo repeats the rule and explains why it was written before observation (`docs/pivot-2026-04-17-characterization.md:75`). The same memo explicitly permits a rule to have `recommendation: promote` and `characterization: divergent` at the same time (`docs/pivot-2026-04-17-characterization.md:71`).

Violation: automatically changing rule status, evaluator prompts, compiler selection, or publication claims solely because a `divergent` label appears violates this commitment.

### Seeded And Earned Concepts Remain Distinct

Statement: seeded concepts may exist in the wiki, but their provenance must say whether they are seeded, merged, emergent, or promoted.

The lab begins with hypotheses. That is not a defect. The defect would be laundering those hypotheses into earned findings by placing them next to evidence-backed concepts without attribution. Seeded vocabulary is allowed, but it must remain visible as seeded until evidence attaches.

Implementation: `compute_provenance()` distinguishes seeded, merged, emergent, and promoted concepts in `judgment_wiki.py:314`. Concept pages carry `provenance`, `evidence_count`, `characterization`, `panel_preference_rate`, `human_alignment_rate`, and `rule_id` in frontmatter (`wiki/templates/concept.md:1`). The builder fills those fields from rule characterization proposals or an explicit empty characterization object (`judgment_wiki.py:506`, `judgment_wiki.py:999`, `judgment_wiki.py:1071`).

Violation: rendering seeded concepts as if they were earned findings, or removing provenance from concept pages because it makes the wiki look less settled, violates this commitment.

### Panel Independence Is Versioned

Statement: evaluator-panel configuration is part of the evidence, and the lab records whether Apollo is independent or collapsed into Athena.

Automated judges can agree because they share a taste, because they share a model family, or because the system accidentally gave two roles the same backend. The lab cannot characterize panel behavior unless the panel version is visible. Independence is not an aesthetic preference; it is part of the measurement apparatus.

Implementation: `agents.py` computes `APOLLO_INDEPENDENT` from Apollo's backend/model pair and sets `LAB_JUDGE_PANEL_VERSION` to `muse_athena_apollo_v1_independent` or `muse_athena_apollo_v0_collapsed` (`agents.py:98`, `agents.py:100`). The orchestration policy exposes Apollo's independence flag and panel version (`agents.py:735`, `agents.py:744`). Model descriptions list Muse, Athena, Apollo, and the council as distinct roles with their configured backends and models (`agents.py:721`). Apollo's independent path is explicitly configured through `APOLLO_BACKEND`; when set to `hermes_cli`, Apollo calls `APOLLO_HERMES_BIN` rather than the OpenAI API.

Violation: comparing evidence across panel configurations without recording the panel version, or presenting a collapsed Apollo/Athena configuration as an independent three-judge panel, violates this commitment.

### Rule Promotion Is Dry-Run Only

Statement: promotion proposals can be computed, displayed, and written as characterization metadata, but the script does not automatically change rule status.

The lab currently separates evidence synthesis from governance action. This matters because recommendation and characterization are not the same concept. A rule can be watch-worthy, promote-worthy, divergent, or insufficiently characterized in different combinations. The architecture should surface those combinations before the operator decides what, if anything, they authorize.

Implementation: `compute_rule_promotion_proposals()` returns `mode: "dry_run"` with thresholds and proposals (`database.py:3302`). It persists the current characterization label so the dashboard and wiki stay fresh, but it does not promote or demote rule status (`database.py:3291`). The promotion script prints "Prompt rule promotion dry-run" and "No statuses are changed by this script" before listing proposals (`scripts/promote_rules.py:52`).

Violation: a script, endpoint, or UI action that promotes, demotes, activates, or deactivates a rule automatically from proposal output would violate the current dry-run discipline.

## Known Limitations And Honest Gaps

The evidence scale is still small. Four compiler-compare packets and one rule under watch can test whether the architecture refuses overclaiming, but they cannot establish a stable theory of model taste.

Human-review throughput is the rate-limiting step. The system's most important labels require decisive human signal, and decisive human review is slower than model judgment. This is a feature epistemically and a bottleneck operationally.

The lab is still largely single-operator. That gives it coherence, but it also concentrates blind spots. A single operator can be disciplined and still miss entire families of failure because the questions being asked come from one mind.

The creative substrate may not transfer cleanly. Findings about prose, tone, personification, and audience framing may not generalize to legal drafting, software evaluation, mathematical proof, or policy analysis. Transfer should be treated as a hypothesis, not assumed from shared LLM infrastructure.

Evaluator dimension collapse remains a live risk. Muse, Athena, and Apollo have distinct roles, but a model judge can still collapse multiple criteria into one impression: eloquence, specificity, constraint satisfaction, and usefulness may blur into a single preference signal. The architecture records disagreement, but it does not guarantee that each evaluator's dimensions remain independent internally.

The pre-registration immutability rule is not yet enforced by tooling. It exists as a documented process commitment. Future work should add either append-only evidence-note generation or a preflight check that flags edits to dated pre-registration sections after first commit.

The public exhibit is curated. It contains the packets needed to verify the current claims, not the full private corpus. That is the right publication posture, but it means readers should not treat the public packet count as the total historical packet count.

## Falsifiability Catalog

`insufficient_data` as a first-class label would be weakened if readers or operators consistently infer characterization anyway from panel-leaning dashboard states. The test is behavioral: when a rule is panel-favored but below five decisive human reviews, does the UI and documentation keep saying "not yet" clearly enough that users do not overread it?

The `characterization_min_human: 5` threshold would be weakened as too strict if rules that clearly stabilize by three decisive reviews remain unusably stuck at `insufficient_data` for long periods without later flips. It would be weakened as too permissive if rules characterized at five decisive reviews frequently reverse at ten, fifteen, or twenty. The test is to re-run characterization at every multiple of five decisive reviews and record label stability.

Dual constraint-fail suppression would be weakened if suppressed slices prove predictive of later human preference despite both artifacts failing constraints. The current architecture says such slices should not count as support. If repeated human review shows that one failure mode is meaningfully preferable and operationally useful, the lab may need a separate "failure comparison" track rather than support suppression.

Pre-registration immutability would be falsified operationally by any edited pre-registration section whose change is not represented as a dated update. The remedy is not prose apology; it is an audit trail and, eventually, tooling that refuses silent mutation.

`divergent_authorization` would be weakened if repeated divergent labels overwhelmingly turn out to mean one thing, such as panel pathology, and never require the plural interpretation the memo preserves. Even then, the authorization rule would not be false on first principles; it would become conservative. The test is to classify post-review divergent cases by cause and see whether the four listed possibilities actually occur.

Seeded-vs-earned provenance would be falsified if seeded concepts accumulate authority in the writing or UI before packet evidence attaches. The test is not only schema inspection but reader comprehension: can a skeptical reader tell, from a concept page alone, whether a concept is seeded, merged, emergent, or promoted?

Panel independence would be weakened if independent panel versions produce the same preference patterns as collapsed versions across enough packets to make the distinction empirically unimportant. It would be falsified as implemented if evidence rows ever lack the panel version needed to separate those conditions.

Dry-run promotion would be falsified by any automatic status mutation from proposal output. It would be weakened as a workflow if human operators routinely copy dry-run recommendations into status changes without reading reasons, missing thresholds, suppressed slices, and characterization labels.

## Essay Map

This document is source material for the following essay arc:

- `The Refusing Instrument` — in progress. The argument that an honest evaluation instrument must be able to refuse conclusions it has not earned.
- `Authorization Before Observation` — planned. The argument for deciding what measurements authorize before the first surprising result appears.
- `When the Judge Drifts` — planned. The argument that LLM judges create an invisible centralization layer in modern evaluation pipelines.
- `Seeded, Not Earned` — planned. The argument that inherited opinion and observed evidence must remain distinct at the data-structure level.
- `The Pivot That Falsified Our Thesis` — planned. The account of the April 17 pivot from taste education to taste characterization.
- `Phronesis at the Threshold` — planned. The argument that evaluation architecture requires practical judgment where thresholds run out.
- `The Small Bell` — planned. The argument that the first honest empirical signal in a measurement instrument is often smaller than expected, and that smallness can be evidence the instrument is working.
