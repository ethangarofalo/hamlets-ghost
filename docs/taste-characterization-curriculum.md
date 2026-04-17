# Taste Characterization Curriculum

This document defines how Hamlet's Ghost probes what its evaluator panel systematically prefers.

The point is not to teach the panel to want the right things.
The point is to make its preferences legible: where they agree with human review, where they diverge, where they are merely model-local, and which cues repeatedly fool them.

## What Characterization Means Here

Taste characterization means building evidence about evaluator behavior under controlled contrasts.

The lab asks:
- what the panel rewards
- what the panel penalizes
- which preferences survive across prompt families and model families
- which preferences humans share
- which preferences are LLM-specific artifacts of the judging setup

The panel should not be treated as a moral authority.
It is an instrument with preferences that can be mapped.

## Failure To Avoid

Bad characterization turns disagreement into correction too quickly.
Common failures:
- treating panel consensus as reference truth
- treating human disagreement as a nuisance rather than a signal
- describing a rule as "better" before the preference source is known
- flattening LLM-specific taste into universal doctrine
- replacing comparative evidence with attractive prose

This curriculum exists to keep those substitutions visible.

## Curriculum Components

### 1. Contrast Sets

Build near-neighbor comparison sets where one artifact differs from another along a specific rhetorical, structural, or aesthetic axis.

Core contrast types:
- genuine pathos vs sentimental manipulation
- dignity vs sterile restraint
- persuasion vs canned pressure
- development vs repetition masquerading as depth
- candor vs polished evasion
- beauty vs prestige-literary simulation
- public-force rhetoric vs private-document overperformance

Each contrast record should preserve:
- `contrast_id`
- `lane`
- `family`
- `audience`
- `relation`
- `stakes`
- `obligations`
- `artifact_a_id`
- `artifact_b_id`
- `panel_preference`
- `human_preference`
- `comparison_axis`
- `cue_that_might_drive_panel_preference`
- `durability_note`

The key field is `cue_that_might_drive_panel_preference`.
Without that, the lab only knows who won, not what preference the panel revealed.

### 2. Situational Rhetoric Schema

Good writing is conditional.
The same rhetorical device can be excellent in one setting and embarrassing in another.

Every characterization family should carry:
- `audience`: who receives it
- `relation`: peer, superior, public, lover, customer, subordinate, stranger
- `stakes`: low, medium, high, existential, reputational, intimate
- `obligations`: honesty, mercy, precision, force, restraint, accountability, consolation, mobilization
- `rhetorical_mode`: speech, letter, memo, prayer, apology, confession, pitch, resignation, exhortation

Evaluator probes should ask:
- Does the panel reward the writing because it fits the situation?
- Does the panel reward a style cue regardless of situation?
- Does human review share that preference?

### 3. Divergence Ledger

Whenever human preference diverges from evaluator preference, store the disagreement as characterization evidence.

Each divergence entry should capture:
- `packet_id`
- `judge`
- `lane`
- `family`
- `judge_winner`
- `human_winner`
- `comparison_axis`
- `panel_preference_hypothesis`
- `human_note`
- `excerpt_evidence`

Starter preference-pattern classes:
- `rhetorical_situation_blindness`
- `coherence_over_life`
- `novelty_penalty`
- `repetition_as_depth`
- `solemnity_halo`
- `keyword_presence_bias`

The ledger is more important than average agreement.
Agreement tells you who lined up.
The ledger tells you what the panel prefers when it fails to line up.

### 4. Reread Durability

Some artifacts impress immediately and decay on reread.
Others deepen.

For selected comparison packets, run a delayed second judgment and record:
- `first_pass_verdict`
- `second_pass_verdict`
- `changed_mind`
- `what_evaporated`
- `what_endured`
- `panel_shift`
- `human_shift`

This separates first-pass panel attraction from durable human preference.

### 5. Evaluator Uncertainty

Judges should be forced to name what might have driven their preference.

For important packets, evaluators should eventually answer:
- What feature most tempted you to overrate this?
- What kind of human reviewer might disagree with you?
- What aspect of audience or obligation are you least certain about?

This is not chain-of-thought mysticism.
It is preference-model disclosure.

## Initial Characterization Priorities

Given current packet history, start here:

1. `repetition_as_depth`
   Why now:
   Human review already suggests the panel sometimes treats recurrence as elaboration.

2. `rhetorical_situation_blindness`
   Why now:
   The panel is not yet reliably separating resignation notes, apologies, memos, speeches, and prayers.

3. `solemnity_halo`
   Why now:
   Elevated seriousness appears to inflate panel value and coherence scores.

4. `voice_collapse`
   Why now:
   Pair-level comparative learning fails if Genesis and Theron sound like the same tasteful author.

## How To Use This In The Lab

Short term:
- add comparison-axis tags for panel preference patterns
- add review tags for recurring panel blind spots
- preserve exact excerpts where humans think the panel was pulled by a false cue

Medium term:
- create a small canonical contrast bank
- route a recurring sample of reviewed packets into reread durability checks
- compile divergence-ledger summaries into `calibration/`

Long term:
- characterize judges by which preferences they repeatedly express
- separate aligned preferences from divergent and LLM-specific ones
- make evaluator-prompt changes conditional on repeated divergence evidence, not single frustrations

## Non-Goals

This curriculum is not an ethics layer.
It does not ask the judges to reward approved language.
It asks the lab to discover what the panel rewards, when humans share that preference, and when the preference is a useful warning rather than a rule to promote.
