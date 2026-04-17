# AI Creativity Lab — Research Roadmap

Last updated: April 1, 2026

## Purpose

This document translates the lab's broad mission into a practical research and architecture roadmap.
It answers four questions:

1. What should improve next in the lab itself?
2. How should experiments be structured so prompt optimization findings are actually interpretable?
3. What counts as a real finding about AI creativity?
4. How should the results be shared once the evidence is mature enough?

The aim is not to collect interesting artifacts.
The aim is to learn when prompting for creativity helps, when it hurts, and how reliably the system can produce creativity on demand without sacrificing usefulness.

## Working Research Questions

### RQ1: When should AI be prompted to be creative?

The lab should be able to answer questions like:
- Does creativity help more in creative transformation tasks than in business persuasion tasks?
- When does creativity improve distinctiveness without reducing usefulness?
- When does creativity become decoration that lowers trust, clarity, or actionability?

### RQ2: How successful is the model when creativity is explicitly requested?

The lab should be able to distinguish:
- creative intent in the prompt
- creative appearance in the output
- human-perceived creativity
- evaluator-scored novelty or surprise

The key distinction is between:
- "the model sounded fancy"
- "the model produced useful novelty"

### RQ3: Can prompt strategy make creativity more controllable?

The lab should test whether specific interventions improve outcomes:
- critique-on vs critique-off
- open-ended vs constrained
- direct instruction vs metaphorical framing
- safe business realism vs novelty-seeking language
- different levels of specificity or audience grounding

### RQ4: Can the lab produce externally credible evidence?

The lab should eventually support claims like:
- "Creativity prompting helps on these task families."
- "It reliably fails on these conditions."
- "Human judgment and evaluator judgment align here, but diverge here."

That requires clean methodology, not just compelling examples.

## Immediate Architecture Priorities

### 1. Finish verifier reliability on formal constraints

Goal:
- make hard constraints fail for the right reason
- reduce false passes on custom prompt wording

Needed:
- broader machine-checkable constraint detection from prompt text
- explicit logging for why a verifier check did not run
- per-family stats for:
  - passed
  - passed_after_repair
  - failed_after_repair
  - downstream MUSE constraint_fail

Why it matters:
- if constraint handling is untrustworthy, then prompt optimization findings are polluted by last-mile formatting failures rather than real creativity effects

### 2. Improve Socratic reliability

Goal:
- reduce `fallback_questions`
- make the Socratic stage a real pressure test, not a sometimes-decorative step

Needed:
- keep prompt payload narrow
- continue improving structured output reliability
- track fallback rate by prompt family and task type

Why it matters:
- if Socratic pressure is inconsistent, it becomes impossible to tell whether critique helps or whether it simply executed cleanly on some runs and not others

### 3. Track reliability explicitly

Goal:
- turn operational failures into measurable research variables

Needed metrics:
- branch parse-failure rate
- interlocutor fallback rate
- revision parse-failure rate
- verifier repair rate
- HERMES skip rate
- cost per successful promoted artifact

Why it matters:
- otherwise the lab looks more stable than it is, and conclusions over-credit the prompt rather than the surrounding machinery

## Experiment Design Priorities

### 4. Shift from general batches to paired tests

The next useful experiments should be controlled pairs, not just mixed prompt collections.

For each family, create a small matrix:
- creativity-forward wording vs utility-forward wording
- critique_on vs critique_off
- constrained vs lightly constrained
- literal framing vs metaphorical framing

Hold constant:
- task family
- lane
- scoring policy
- promotion rule
- prompt objective

Why:
- paired tests are what make prompt optimization claims credible

### 5. Build prompt families around one variable at a time

Strong family categories:
- formal constraint stress tests
- genre transfer and mismatch
- transformational invention
- impossible objects and sensory imagination
- business specificity and trust
- strategic positioning and executive communication

Within each family, isolate one variable:
- specificity
- emotional intensity
- audience grounding
- novelty pressure
- structural rigidity

Why:
- the lab should answer "what changed?" with one real answer, not five confounded ones

### 6. Keep human calibration small but steady

Human review should stay the reality anchor.

Priorities:
- sample across lanes, not only best artifacts
- sample across statuses: promoted, kept, discarded
- compare human judgment to MUSE and HERMES on:
  - novelty
  - usefulness
  - constraint fit
  - worth saving

Why:
- a creativity lab without human grounding risks becoming a closed-loop taste simulator

### 7. Add a "humanized vs creative" prompt family

The lab should explicitly distinguish between:
- prompts that try to sound more human
- prompts that try to be more creative
- prompts that try to do both
- plain direct prompts used as baseline

Recommended comparison set:
- plain
- humanized
- creativity-seeking
- humanized + creativity-seeking

Questions to answer:
- does humanized prompting increase perceived humanness more than actual creativity?
- does creativity prompting increase originality without simply performing stylistic messiness?
- does combining the two produce better work, or just more camouflage?

Why:
- "human-like" and "creative" are often treated as the same thing in prompt culture, but they are not the same research object
- this distinction is likely to become one of the clearest framing ideas for the lab's eventual public writeup

## What Counts as a Real Finding

Real findings are comparative, bounded, and tradeoff-aware.

### Strong finding shape

A strong finding includes:
- the task family
- the tested condition
- the comparison baseline
- the direction of effect
- the tradeoff

Examples:
- "On business positioning tasks, creativity-forward prompts increased novelty but reduced trust and actionability relative to direct, audience-specific prompts."
- "On transformational poetry tasks, critique-on improved coherence and evaluator agreement without reducing human-rated originality."
- "On formal constraint prompts, the main failure mode was not lack of imagination but last-mile constraint repair."
- "MUSE and HERMES agree in business lane more than creative lane, suggesting tighter shared priors on usefulness than on novelty."

### Weak finding shape

Weak findings sound like:
- "The model was creative."
- "This protocol feels better."
- "The outputs got more interesting."
- "The evaluator liked the new style."

These are not findings because they do not specify:
- compared to what
- under what task condition
- according to whose judgment
- at what cost

## Creativity Measurement Framework

The lab should treat creativity as multi-part, not singular.

### Creativity components

- novelty: non-obviousness relative to expectation
- surprise: apt expectation violation
- value: worth reading or using
- constraint mastery: satisfying formal or task requirements
- transfer power: ability to move between domains or forms without collapse
- human distinctiveness: whether a human actually experiences the artifact as unusually alive, sharp, or original

### Recommended interpretation rule

Do not call an artifact "successful creativity" unless it shows one of:
- higher novelty at equal usefulness
- higher surprise at equal coherence
- higher originality without failing core constraints
- a clear gain in distinctiveness that humans judge worth saving

This avoids collapsing "creativity" into decorative weirdness.

## Most Useful Near-Term Outputs

The best outputs for prompt optimization are not single artifacts.
They are summaries at the family and condition level.

### Summaries the lab should produce

- creativity-forward vs utility-forward by family
- critique_on vs critique_off by family
- constraint rescue rate by family
- MUSE vs HERMES divergence by lane
- human vs evaluator agreement by family
- cost per promoted or human-endorsed artifact

### Questions these summaries should answer

- Where does creativity improve the result?
- Where does creativity create a tax?
- Where does critique help?
- Where is evaluator trust weak?
- Which prompt strategies are robust rather than lucky?

## Sharing Plan

Once enough evidence exists, results should be shared in layers.

### Layer 1: Internal research memo

Audience:
- operator, collaborators, future self

Contents:
- what changed
- what appears true
- what still looks weak
- next experiment to run
- one thing to stop

### Layer 2: Methods note

Audience:
- technically serious readers

Contents:
- generation protocol
- evaluation protocol
- verifier behavior
- human review method
- lane definitions
- known limitations and confounds

This is where credibility is built.

### Layer 3: Public-facing findings writeup

Audience:
- AI researchers
- product builders
- creators

Best structure:
- why this question matters
- how the lab works
- what was tested
- strongest findings
- representative paired examples
- limits of the study

Avoid:
- "AI can be creative" as the headline

Prefer:
- "Creativity prompting helps in these conditions, hurts in these others, and is often mismeasured unless usefulness and constraint mastery are tracked separately."

## Recommended Execution Order

### Phase 1: Measurement integrity

1. Finish verifier reliability for formal constraints
2. Reduce Socratic fallback rate
3. Add explicit reliability dashboards

Exit criteria:
- machine-checkable custom prompts reliably trigger verifier checks
- fallback rate is low enough to trust critique experiments
- orchestration and trace logging remain stable

### Phase 2: Controlled prompt optimization

4. Run paired prompt-family tests
5. Expand human calibration on a representative subset
6. Produce first family-level comparison tables

Exit criteria:
- at least a few prompt families have paired evidence
- at least some human-reviewed examples exist in each lane
- conclusions are comparative rather than anecdotal

### Phase 3: Council and communication

7. Schedule morning/evening council sessions with minimum-data guards
8. Save recurring briefing history
9. Draft the first findings memo

Exit criteria:
- the council is reviewing evidence, not noise
- the lab can generate a meaningful daily or twice-daily readout
- there is enough evidence to communicate external conclusions responsibly

## Near-Term Target Findings

The first real findings the lab should try to earn are:

- whether creativity-forward prompting is a net positive or net tax in business writing
- whether Socratic critique improves outputs or simply improves evaluator appeal
- whether evaluator agreement in creative lane is a useful trust signal or mostly shared taste
- whether formal-constraint prompts fail because of generation quality or verifier/repair weakness
- whether transformational prompts are the clearest area where prompting for creativity produces genuine gains
- whether "humanized" prompts improve humanness without improving genuine creativity

These are strong early findings because they are:
- narrow enough to test
- meaningful to prompt optimization
- understandable to an outside audience

## Current Recommendation

Right now the highest-leverage path is:
- finish the formal constraint verifier
- keep running targeted custom paired prompts
- expand human calibration on representative samples
- start writing findings at the family level rather than the artifact level

That path is the fastest route to prompt optimization conclusions that are both useful and publishable.

## Lean 2-Week Roadmap

The next two weeks should stay narrow.
Do not try to solve product identity, broad customer segmentation, or full automation all at once.

### Primary objective

Prove that the lab can detect and record improved creativity calibration over repeated experiments.

The question is not:
- "Did the model become more creative?"

The question is:
- "Did the lab get better at distinguishing when creativity helps, when it hurts, and when it should be suppressed?"

### Week 1: Make calibration visible

Build or tighten the smallest set of metrics that answer whether the system is learning:
- creativity-overreach rate by lane and family
- constraint recovery rate by family
- critique help rate by family
- novelty-minus-utility gap by family
- human-agreement with save/discard on a small steady sample

Required output:
- one compact internal snapshot that states:
  - what improved
  - what regressed
  - what still looks noisy
  - what one experiment should run next

### Week 2: Make learning explicit

Add one simple adaptation mechanism rather than a full autonomous loop.

Preferred version:
- detect prompt families where critique consistently helps or hurts
- record that as a recommendation or default policy for future runs

Acceptable alternatives:
- detect families where creativity-forward prompting reliably creates tax
- detect families where verifier repair is rescuing otherwise strong generations

Required output:
- one short report showing:
  - the repeated failure pattern
  - the correction or policy change
  - whether the next runs improved

### What to avoid during this phase

- broad productization work
- adding many new task families at once
- complicated autonomous policy mutation
- presentation-heavy dashboard work that does not improve research judgment
- making claims about "general creativity" instead of calibration

### Success criteria for this phase

At the end of this 2-week window, the lab should be able to say:
- where creativity is a net gain
- where creativity is a tax
- whether critique is teaching anything real
- whether the system is showing visible correction recognition over time

If the lab cannot say those clearly, keep tightening measurement before expanding scope.
