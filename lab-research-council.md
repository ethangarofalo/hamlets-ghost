# Lab Research Council

This is a research-governance adaptation of the broader "LLM Council" idea.
It is not a general business-advice council. Its job is to review evidence from the Creativity Lab, pressure-test conclusions, and recommend the next experiment or system change.

The goal is not "what should we do?" in the abstract.
The goal is "what does the evidence actually support, what is still weak, and what should the lab test next?"

## Why This Exists

The current lab council is still a single model playing multiple roles inside one prompt.
That is useful as a summarizer, but weak as a real review mechanism.

This council is designed to:
- separate perspectives into independent calls
- force disagreement before synthesis
- make evaluator trust an explicit object of scrutiny
- turn cost and sample-size limits into part of the analysis
- produce a concrete next experiment, not just a memo

## Current Operating Objective

For the current phase, the council should optimize for one narrow goal:
- determine whether the lab is learning creativity calibration

That means answering questions like:
- Is the lab getting better at detecting when creativity helps?
- Is the lab getting better at detecting when creativity hurts?
- Are critique and repair creating real improvement or just prettier traces?
- Is there visible correction recognition across repeated runs in the same family?

Until that is answered clearly, the council should deprioritize:
- broad product strategy
- speculative business-model advice
- large architecture rewrites
- open-ended brainstorming that is not grounded in current evidence

The council should prefer simple, efficient decisions that increase learning rate.

## When To Run It

Run the Lab Research Council when:
- a new batch of experiments has finished
- human calibration has changed the trustworthiness of MUSE or HERMES
- a protocol change needs a go/no-go decision
- the team is unsure whether to tune evaluators, generation, or task design next
- cost is rising and you need to know which step is actually worth it

Do not run it for:
- simple factual questions
- single-run artifact judgments
- broad brainstorming with no evidence in hand
- ordinary creative generation

## What It Reviews

Each session should consume a compact, structured evidence packet built from the lab:

1. Recent experiment batch
- experiment ids
- lane breakdown
- generation protocol used
- keep/discard/promote outcomes

2. Evaluator evidence
- MUSE/HERMES composites
- divergence
- evaluator diagnostics
- human calibration deltas

3. Process evidence
- selected traces from `process_trace`
- branch candidates
- selection rationale
- rejected candidates
- interlocutor status
- revision changes

4. Cost evidence
- total cost for the batch
- per-experiment cost
- `stage_costs` where available

5. Historical context
- prior council recommendations
- whether those recommendations were actually tried
- whether the newer batch improved or regressed

The council should review summaries first and only inspect raw traces when something looks suspicious or unusually promising.

## Step 0: Evidence Packet Assembly

Before the council runs, assemble the evidence packet mechanically from the lab's stored data.

Rules:
- no editorializing
- no persuasive summary language
- no cherry-picking of only the most flattering traces
- no generated interpretation inside the packet itself

The packet should be built from database queries and stored traces, then handed to the council as structured evidence.
It should contain raw or lightly tabulated facts:
- batch membership
- scores
- divergences
- promotions
- diagnostics
- human-review counts and deltas
- stage costs
- selected process traces
- prior recommendation status

The review question should then be written by the human operator.
The council may analyze the packet, but it should not author its own evidence framing from scratch.

## The Five Advisors

These are research roles, not theatrical personas.
They are meant to create productive tension around evidence quality, not produce a fake committee performance.

### 1. The Methodologist

Question: "Can this experiment design actually answer the stated hypothesis?"

Responsibilities:
- evaluate whether the experiment design can actually answer the stated hypothesis
- check sample sizes, control pairs, and confound risks
- determine whether hypotheses are falsifiable with the current task structure
- flag when the lab is collecting data without a testable prediction

Off limits:
- interpreting results
- recommending prompt or protocol changes
- arguing about evaluator trust

Those belong to the Skeptic, Protocol Designer, and Evaluator Auditor.

Bias to embrace:
- prefers validity over momentum

### 2. The Skeptic

Question: "What story is the lab telling itself that the evidence does not support?"

Responsibilities:
- challenge the strongest-looking result: is it real or an artifact of scoring, selection, or evaluator bias?
- detect prompt overfitting, scoring theater, and inflated keep/promote rates
- ask whether "improvement" is genuine or whether the evaluator learned to like the generation style
- name the most tempting story the lab is telling itself that the evidence does not support

Off limits:
- redesigning the experiment
- ruling on sample validity as a design question

That belongs to the Methodologist.

Bias to embrace:
- assumes the most exciting story is probably overstated

### 3. The Evaluator Auditor

Question: "Can we trust the measurement enough to act on it?"

Responsibilities:
- inspect MUSE/HERMES agreement and disagreement
- scrutinize halo effects, repeatability, and business-vs-creative mismatch
- use human calibration as the reality anchor
- recommend whether to tune evaluators, freeze them, or distrust them

Bias to embrace:
- measurement quality outranks aesthetic enthusiasm

### 4. The Protocol Designer

Question: "What experiment or protocol change would teach us the most next?"

Responsibilities:
- propose the single highest-information-value change to generation, task design, or Socratic pressure
- prefer small targeted experiments over large rewrites
- identify where branch-selection, interrogation, or mixed-task design should be pushed further
- if the generation protocol is not the bottleneck, say so and yield

Off limits:
- recommending evaluator changes
- questioning sample validity or experimental design

Those belong to the Evaluator Auditor and Methodologist.

Bias to embrace:
- optimize for learning rate, not elegance

### 5. The Ops and Budget Lead

Question: "Is this worth the cost, complexity, and experiment count?"

Responsibilities:
- inspect stage-level and batch-level spend
- ask whether expensive steps are buying measurable improvement
- guard against protocols that are impressive but too costly to study at useful sample sizes
- keep throughput, reliability, and maintenance in view

Must report for every batch:
- total batch cost and per-experiment cost
- cost per promoted artifact
- cost per human-calibrated data point, when reviews exist
- stage-level cost breakdown where available
- whether expensive stages are correlated with score improvement or promotion

Bias to embrace:
- no expensive ritual without evidence of return

## Council Workflow

### Step 1: Frame the Review Question

Create a neutral framed question from the evidence packet.
It should include:
- what changed
- what evidence is available
- what decision needs to be made
- what constraints matter most

Good framing example:

> "A batch of 8 `socratic_v2` runs was completed after tightening business-lane evaluator prompts. Human calibration improved on business surprise and novelty, but interlocutor reliability remains mixed. Should the lab spend tomorrow on evaluator tuning, trace fidelity, or mixed-task design?"

The framed question should not smuggle in a recommendation.

### Step 2: Independent Advisor Pass

Run all five advisors independently in parallel.

Each advisor should receive:
- the framed question
- the evidence packet
- a strict instruction to lean into their role
- a structured output requirement

Each advisor must answer in this exact format:

`STRONGEST SUPPORTED FINDING:` [one sentence]

`WEAKEST UNSUPPORTED CLAIM:` [one sentence]

`RECOMMENDED NEXT ACTION:` [one sentence]

`REASONING:` [150-250 words]

This forces commitment before prose and makes peer review faster and sharper.

### Step 3: Anonymous Peer Review

Collect the five advisor responses.
Anonymize them as Response A-E.
Randomize the mapping.

Then run a peer-review round in parallel.
Each reviewer sees all five anonymous responses and answers:

1. Which response is strongest, and why?
2. Which response has the biggest blind spot?
3. What did the full set still miss?

If all responses converge on the same conclusion, the reviewer must also answer:

4. What would have to be true for the consensus to be wrong?

Keep these short and sharp.
This step exists to expose weak reasoning and surface omissions, not to restate the same points.

### Step 4: Chairman Synthesis

The chairman receives:
- the framed question
- the five advisor responses with identities restored
- the anonymous peer-review outputs

The chairman must produce a direct research verdict with this exact structure:

## Strongest Supported Finding

[The clearest conclusion the evidence currently supports.]

## Weakest Unsupported Claim

[The most tempting overreach or conclusion that the evidence does not yet justify.]

## Evaluator Trust Assessment

[How much MUSE/HERMES can be trusted on this question, and why.]

## Protocol Assessment

[Whether the current generation/evaluation protocol is pulling its weight.]

## Confidence Level

[HIGH, MODERATE, or LOW, with a brief reason. If LOW, the recommendation should default toward collecting more data rather than changing architecture.]

## Recommendation

[A clear recommendation, not "it depends."]

## One Experiment To Run Next

[A single next experiment with enough detail to execute.]

## One Thing To Stop Doing

[One behavior, claim, or ritual the lab should stop.]

### Step 5: Save the Council Artifact

Default output should be markdown, not HTML.
This is a research artifact first, a presentation asset second.

Suggested files:
- `research-council-report-[timestamp].md`
- `research-council-transcript-[timestamp].md`

The report is the short verdict.
The transcript contains:
- the standing accountability check
- the framed question
- the evidence packet summary
- all five advisor responses
- anonymization mapping
- all peer reviews
- the final chairman synthesis

HTML can be added later if the council becomes part of the daily operating rhythm.

## Prompting Guidance

The council should review protocol-level evidence, not just outputs.
Every advisor should be reminded:
- do not treat MUSE/HERMES as ground truth
- do not confuse process trace richness with actual improvement
- do not recommend a major architecture change when a smaller experiment could answer the same question
- do not ignore cost, sample size, or human calibration
- do not confuse "more creative" with "better calibrated creativity"
- do not praise a result unless it helps clarify when creativity should be increased, reduced, or withheld

The chairman should be told explicitly:
- clarity matters more than diplomacy
- disagreement should be preserved, not smoothed away
- if the evidence is insufficient, say so plainly

## Standing Accountability Check

Every session should begin with this question:

> "Last session recommended [X]. Was it implemented? If yes, what happened? If no, why not?"

This should be answered from stored council history before the new batch is interpreted.

If the same recommendation appears repeatedly without being tried, that is itself a finding and should be surfaced in the report.

## Suggested Output Heuristics

The best sessions should usually end with one of these classes of decision:
- evaluator-first
- protocol-first
- task-design-first
- cost-control-first
- hold-steady-and-collect-more-data

For the current phase, the most useful outputs are usually:
- a clearer calibration metric
- a tighter paired experiment
- a simpler policy change tied to one repeated failure pattern
- a decision to hold steady and gather enough evidence before expanding scope

If the council cannot name one of those, it is probably being too vague.

## What Success Looks Like

This council is successful if it helps the lab do more of the following:
- stop making claims the evidence cannot support
- notice evaluator drift before building on it
- choose the next experiment with higher information value
- connect cost to actual research return
- convert batches of experiments into durable protocol knowledge

It is not successful if it merely produces impressive summaries.

## Tomorrow-Morning Build Target

The first implementation version should be intentionally modest:
- use the five research roles above
- operate on a recent experiment batch summary, not the whole database
- generate markdown only
- skip HTML and rich visualization
- keep prompts compact to control cost

That version is enough to replace the current one-prompt council theater with an actual review loop.
