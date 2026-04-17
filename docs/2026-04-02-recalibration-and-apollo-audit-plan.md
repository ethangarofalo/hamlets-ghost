# Recalibration And Apollo Audit Plan

Last updated: 2026-04-02

## Why This Plan Exists

Hamlet's Ghost now has enough evidence to justify a real evaluator recalibration pass.

The current concern is not merely that the evaluators are imperfect.
It is that:

- `Muse` and `Athena` may be collapsing multiple rubric dimensions into a generalized quality signal
- `Apollo` may be too lightly differentiated from `Athena` to count as a truly outside evaluator
- human judgment has repeatedly favored artifacts that the internal stack under-recognized

That means the next phase should not be more protocol complexity.
It should be measurement repair.

## Immediate Findings

### 1. Internal evaluator miscalibration is now a live finding

Recent runs and council output both suggest:

- novelty and surprise are not being measured independently enough
- evaluator composites may be halo-dominated
- human preference diverges from internal evaluator preference in ways that matter

This is especially important in the creative lane, where the lab is trying to learn when creativity helps rather than merely reward polished competence.

### 2. Apollo is operationally real but not yet epistemically independent enough

Apollo is a real runtime role:

- it has a separate scorer identity in the database
- it logs separate scores
- it participates in the disagreement queue
- it is preserved in role packets and process traces

But code inspection shows a meaningful risk:

- `APOLLO_SYSTEM` falls back to `hermes_external`
- if that override is absent, it falls back again to `ATHENA_SYSTEM`
- Apollo also defaults to the same model family as Athena unless explicitly reconfigured

So the current implementation supports a distinct Apollo role,
but does not yet guarantee a distinct Apollo mind.

This explains why Apollo calibration may have felt "too easy."

## Working Hypothesis

The likely current state is:

- `Muse` = primary quality / possibility reader
- `Athena` = skeptical internal auditor
- `Apollo` = operationally separate shadow evaluator
- but Apollo may still be too close to Athena in evaluator stance and model family to count as a robust outside epistemic pressure

So the lab currently has:
- role differentiation
- packet differentiation
- storage differentiation

but not yet enough evaluator independence.

## Recalibration Experiment

### Goal

Repair evaluator trust before making stronger claims about:

- when creativity helps
- when critique helps
- which generator should be favored
- whether protocol complexity is paying for itself

### Design

Run a tightly scoped recalibration experiment with three strata.

#### Stratum A: promoted creative artifacts

Oversample recent promoted artifacts from:

- `personification`
- `genre_mismatch`
- `expert_surprise`
- `domain_transfer`

Goal:
- see whether human judgment agrees with evaluator confidence on the artifacts the lab is already favoring

#### Stratum B: disagreement-heavy artifacts

Oversample artifacts with:

- large `Muse/Athena` divergence
- large `Muse/Apollo` divergence
- items already in the disagreement queue
- human-vs-evaluator disagreement cases

Goal:
- identify whether disagreement is informative or merely noisy

#### Stratum C: business lane controls

Oversample recent business artifacts from:

- `retention_messaging`
- `customer_recovery`
- `product_strategy`

Goal:
- determine whether evaluator miscalibration is lane-specific
- determine whether novelty deltas are being misread differently in business than in creative work

### For Each Sample

Collect:

- artifact
- prompt
- lane
- family
- condition
- generator role
- Muse score
- Athena score
- Apollo score
- human fastpass:
  - overall quality
  - novelty
  - constraint fit
  - which artifact was better and why

### Metrics To Compute

For each lane, compute:

- human vs Muse gap on novelty
- human vs Athena gap on novelty
- human vs Apollo gap on novelty
- human vs evaluator gap on overall quality
- pairwise evaluator agreement
- dimension correlation / halo index
- test-retest stability on repeated prompts
- critique-on vs critique-off movement in human ratings

## Apollo Audit

The recalibration experiment should be paired with a direct Apollo audit.

### Audit Questions

1. Is Apollo using a meaningfully distinct prompt from Athena?
2. Is Apollo using a meaningfully distinct model from Athena?
3. Does Apollo disagree with Athena in patterned, intelligible ways?
4. Does Apollo align with human judgment better than Athena on creative-lane work?

### Audit Steps

1. Confirm Apollo runtime config on each run:
   - backend
   - model
   - prompt hash

2. Compare Apollo vs Athena on the same packet set:
   - mean divergence
   - winner divergence
   - rationale differences

3. Flag suspicious non-independence cases:
   - near-identical rationales
   - near-identical scores across long stretches
   - lack of lane-specific divergence

4. Upgrade Apollo if necessary:
   - give Apollo a dedicated prompt override
   - make Apollo explicitly more attuned to:
     - pathos
     - social intelligence
     - rhetorical force
     - anti-generic voice detection
   - if needed, move Apollo to a distinct model family later

## Operational Recommendation

Until recalibration is complete:

- treat `Muse`, `Athena`, and `Apollo` composites as advisory rather than sovereign
- keep promotion and policy conclusions provisional
- let the disagreement queue and human characterization carry more weight than usual

This does not weaken the lab.
It makes the lab more serious.

## Deliverable After The Experiment

The recalibration pass should end with a memo that answers:

1. Which evaluator tracks human judgment best by lane?
2. Are novelty and surprise real signals or mostly halo artifacts?
3. Is Apollo genuinely independent yet?
4. Should promotion logic change before more generator or protocol work proceeds?

## Short Practical Summary

The next move is:

- do not add more evaluator or protocol complexity first
- run a focused recalibration batch
- audit Apollo's true independence
- then decide what should actually govern the lab
