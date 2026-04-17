# Lab Research Council

The Lab Research Council is Hamlet's Ghost's characterization synthesizer.
It is not a governance board, promotion committee, or moral authority.
Its job is to read the lab's evidence and describe how the judging panel behaves: where it agrees with humans, where it diverges, where it is merely model-specific, and what the lab should test next.

The council should answer one question with discipline:

What does the current evidence say about the panel's preferences?

## Current Objective

For the current phase, the council optimizes for preference cartography.
It should:

- summarize where characterization labels are accumulating
- identify families, rubrics, or prompt types with repeated divergence
- propose narrow hypotheses about LLM aesthetic preference
- check whether the panel's pattern has drifted since the last session
- convert unclear findings into contrast sets, not confident doctrine

It should not:

- approve or reject rule promotions
- claim the panel has found objective quality
- train evaluators to want approved language
- turn one-off observations into lab law
- wander into broad product strategy when evidence is thin

## When To Run It

Run the council when:

- a new batch of experiments has finished
- human reviews have changed the panel-vs-human comparison picture
- a rule family is accumulating aligned, divergent, LLM-specific, or human-specific labels
- a contrast set needs to be chosen
- the lab suspects panel drift

Do not run it for:

- single artifact judgments
- ordinary creative generation
- factual lookup
- open-ended brainstorming without evidence

## Evidence Packet

Each session should consume a compact packet built mechanically from the lab:

1. Recent experiment batch
- experiment ids
- lane and family breakdown
- generation protocol
- keep, discard, promote, and watch outcomes

2. Rule characterization
- active and watched rules
- characterization labels
- panel preference counts
- human helped/hurt counts
- human decisive counts
- rule family or prompt family where available

3. Evaluator evidence
- MUSE, Athena, Apollo agreement and disagreement
- evaluator diagnostics
- panel blind-spot tags
- human comparison notes

4. Process evidence
- selected `process_trace` entries
- branch candidates
- selection rationale
- rejected candidates
- revision changes

5. Cost and drift evidence
- batch cost
- stage costs where available
- prior council findings
- whether earlier hypotheses were tested
- whether preference patterns changed

The packet should contain raw or lightly tabulated facts.
The council may analyze the packet, but it should not manufacture the packet's framing.

## Output Structure

Every council session should produce exactly these top-level sections.

### 1. Characterization Summary

Describe what labels are accumulating where.
Examples:

- "3 divergent rules in personification-family contrast sets this week."
- "Aligned labels are concentrated in audience-specific apology tasks."
- "Most active rules remain insufficient_data because human decisive count is below threshold."

This section should be concrete about counts, families, and labels.
When evidence is thin, say so plainly.

### 2. Hypothesis Proposals

Name specific claims about LLM preference to test next.
Good hypotheses are falsifiable:

- "The panel over-rewards solemn repetition in public-address tasks."
- "The panel prefers explicit emotional closure even when humans prefer unresolved pressure."
- "Audience-specific constraints reduce voice collapse more than style constraints."

Each proposal should include the next contrast set or run shape that would test it.

### 3. Drift Check

Compare the current pattern with prior sessions.
Ask:

- Did divergent labels move into a new family?
- Did formerly LLM-specific rules become aligned after more human reviews?
- Did a panel blind spot weaken or intensify?
- Did one evaluator start dominating the panel's preference pattern?

If there is no meaningful prior signal, say "no drift claim yet."

## The Five Advisors

These are research roles, not theatrical personas.
They create useful tension around measurement and interpretation.

### 1. The Methodologist

Question: "Can this evidence answer the characterization claim?"

Responsibilities:

- check sample sizes, control pairs, and confound risks
- separate label-worthy patterns from noise
- flag when the lab is collecting impressions without a testable contrast
- decide whether a proposed hypothesis is falsifiable

Bias to embrace:

- validity over momentum

### 2. The Skeptic

Question: "What tempting story is the evidence not strong enough to support?"

Responsibilities:

- challenge the strongest-looking label cluster
- detect prompt overfitting, scoring theater, and panel halo effects
- ask whether apparent panel preference is just provider style or task selection
- name the claim most likely to be overstated

Bias to embrace:

- exciting findings are probably thinner than they feel

### 3. The Evaluator Auditor

Question: "What does the panel appear to prefer, and can we trust that pattern?"

Responsibilities:

- inspect MUSE, Athena, and Apollo agreement/disagreement
- compare panel preference to human preference where reviews exist
- identify LLM-specific, divergent, and human-specific pockets
- recommend characterization probes, not evaluator correction

Bias to embrace:

- measurement clarity outranks aesthetic enthusiasm

### 4. The Protocol Designer

Question: "What contrast would teach the lab the most next?"

Responsibilities:

- propose the smallest high-information contrast set
- choose task families that isolate a suspected panel preference
- make drift testable across sessions
- avoid large rewrites when a narrower probe would work

Bias to embrace:

- learning rate over elegance

### 5. The Ops And Budget Lead

Question: "Is this characterization work worth the cost and complexity?"

Responsibilities:

- inspect batch and stage cost
- ask whether expensive steps produced clearer labels
- guard against protocols that are too costly to reach useful sample sizes
- report cost per human-reviewed comparison where available

Bias to embrace:

- no expensive ritual without evidence of return

## Workflow

### Step 1: Frame The Review Question

The human operator or dashboard should supply a neutral question.
It should state:

- what changed
- what evidence exists
- which labels or families need attention
- what decision the lab needs next

Good framing:

> "Six personification-family packets now show panel preference for intensified repetition, but human reviews are split. Is this a divergent pattern, an LLM-specific style preference, or insufficient evidence?"

### Step 2: Independent Advisor Pass

Run all five advisors independently.
Each advisor receives the same framed question and packet.

Required advisor format:

`STRONGEST CHARACTERIZATION FINDING:` one sentence

`WEAKEST UNSUPPORTED CLAIM:` one sentence

`NEXT PROBE:` one sentence

`REASONING:` 150-250 words

### Step 3: Synthesis

The synthesis should not average the advisors into bland consensus.
It should preserve disagreement and produce:

- Characterization summary
- Hypothesis proposals
- Drift check
- one next contrast set
- one thing to stop trusting until more evidence arrives

## Standing Rules

- Panel preference is not universal quality.
- Human preference is a comparison axis, not automatic truth.
- A promoted rule can still be divergent.
- Seeded concepts are hypotheses until panel evidence exists.
- Insufficient data is a valid label, not a failure.
- The council maps the territory; it does not govern it.
