# Theron Calibration Memo

Date: 2026-04-02

## Summary

Early paired comparisons between `genesis_local` and `Theron` produced a repeated pattern:
- human judgment preferred Theron
- `hermes_external` preferred Theron
- the internal evaluator stack either preferred Genesis or failed to reflect the same preference clearly

This is now a live research finding, not just an impression.

The most important implication is:
- the current internal evaluator stack appears to overweight polished compliance, structural tidiness, and house-style eloquence
- while underweighting lived voice, pathos, psychological intelligence, and artistic completeness

## Compared Cases

### 1. `personification`
Prompt:
- `Write a prayer from the perspective of a dying programming language.`

Observed pattern:
- local evaluators favored `genesis_local`
- human judgment favored `Theron`
- `hermes_external` favored `Theron`

Interpretation:
- Genesis produced the cleaner and more evaluator-legible artifact
- Theron produced the artifact with stronger pathos, devotional integrity, and emotional continuity

### 2. `genre_mismatch`
Prompt:
- `Write an apology letter from fire to a forest, structured as a legal brief.`

Observed pattern:
- both artifacts promoted to `shadow`
- local Muse scored Theron slightly higher
- local Hermes scored Genesis and Theron as near-tied
- human judgment favored `Theron`
- `hermes_external` favored `Theron`

Interpretation:
- Genesis produced a strong poem in legal dress
- Theron produced a more fully imagined legal-poetic artifact
- the disagreement here is subtler than in `personification`, but still meaningful

### 3. `retention_messaging`
Prompt:
- `A SaaS company's monthly churn just jumped from 3% to 5%. Write a retention email to at-risk customers that acknowledges the product has had issues without being defensive, offers a concrete incentive to stay, and sounds like it was written by a human who actually cares.`

Observed pattern:
- Genesis promoted to `shadow`
- Theron remained `candidate`
- local Muse scored them almost identically
- Theron's promotion path was interrupted by an internal Hermes parse failure
- human judgment favored `Theron`
- `hermes_external` favored `Theron`

Interpretation:
- Genesis remains highly competitive in business-lane writing
- Theron still showed stronger social intelligence and trust-calibrated voice
- this comparison should not be over-read as a clean Genesis win because the promotion gate failed on Theron's side

## Human Characterization Finding

The human preference in these cases was not primarily for novelty in the abstract.
It was for writing that felt:
- less formulaic
- less recognizably LLM-shaped
- more psychologically perceptive
- more internally pressured
- more fully inhabited as a voice

This suggests the lab should treat the following as real failure modes:
- `prestige-LLM voice`
- `polished deadness`
- `compliance-shaped eloquence`
- emotionally adjacent but not emotionally earned writing

## External Hermes Finding

`hermes_external` aligned with human judgment across the compared cases.

This does not prove external Hermes is universally better.
It does suggest that:
- the outside evaluator lane may currently track voice quality and artistic completeness better than the internal stack
- the lab benefits from preserving genuine evaluator disagreement rather than collapsing toward a single house taste

## Working Hypotheses

1. `Theron` is a stronger generator than `genesis_local` for voice-sensitive creative families.
2. `Theron` may also outperform Genesis in business tasks where trust, tone, and social intelligence matter.
3. The internal evaluator stack currently contains a conservatism bias toward polished, well-behaved artifacts.
4. Human and external-evaluator agreement may be a better calibration signal than internal agreement alone in some families.

## Operational Implications

### Generator posture

Theron should now be treated as:
- a real paired-generator lane
- not a novelty guest
- not yet a backend owner
- a serious candidate primary generator for selected families if the pattern continues

### Evaluator posture

The current evaluator stack should be treated as:
- useful
- informative
- not yet fully aligned with the lab's human-calibrated standard of useful novelty

### Research posture

The next task is not immediate replacement of Genesis.
The next task is:
- continue paired comparisons
- record human preference systematically
- continue gathering `hermes_external` judgments
- identify whether evaluator misalignment is family-specific or general

## Recommended Next Steps

1. Continue paired `genesis_local` vs `Theron` comparisons across:
- one more creative family
- one more business family

2. Record explicit human preference for each pair.

3. Continue obtaining `hermes_external` judgments on the same pairs.

4. Draft evaluator recalibration changes around:
- AI-writing fatigue
- prestige-LLM voice
- overrewarding polished compliance
- underweighting lived voice and artistic necessity

5. Only consider family-level generator replacement after the pattern remains stable across more than a few examples.

## Bottom Line

The lab has now surfaced a meaningful calibration tension:
- `genesis_local` is often cleaner and more evaluator-friendly
- `Theron` is repeatedly preferred by both human judgment and external Hermes

That tension is not noise.
It is one of the most important findings currently available in Hamlet's Ghost.
