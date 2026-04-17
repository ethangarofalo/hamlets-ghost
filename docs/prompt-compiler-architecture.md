# Prompt Compiler Architecture

## Purpose

Hamlet's Ghost is the lab.

The productized system that should emerge from it is a prompt compiler:

- input: a rough human request
- output: a sharper, more situationally legible prompt that helps a downstream model understand what the user is actually asking for

This is not a prompt beautifier.
It is a traced transformation system whose rules are learned empirically through comparative judgment.

The core product question is:

> Given a rough user request, what prompt transformation reliably produces panel-preferred output, and how does that preference compare with human review?

## Lab Boundary Vs Product Boundary

The lab exists to discover and characterize prompt-transformation moves.

The product exists to apply validated moves automatically.

The separation should remain explicit:

- Hamlet's Ghost Lab:
  - discovers prompt-diagnosis rules
  - discovers anti-pattern suppression rules
  - discovers evaluator preference patterns
  - tests raw prompts against compiled prompts
  - promotes only repeated panel-preference findings into active rule hypotheses

- Prompt Compiler:
  - accepts a rough user request
  - diagnoses rhetorical situation
  - selects transformation rules
  - emits a compiled prompt plus traceability
  - routes the compiled prompt to Genesis, Theron, or a downstream customer model

Important:
- the product should not assume one compiler policy works equally well across all model families
- some learned rules will be universal, some will be family-specific, and some will only be valid as model-adaptation rules
- the compiler should eventually route by both task diagnosis and target model behavior

## Compiler Loop

The compiler should operate in six stages.

### 1. Intake

Receive the raw user request exactly as written.

Store:
- source request
- optional user context
- channel or product surface
- whether the user supplied hard constraints

### 2. Diagnosis

Infer the basic structure of the task before touching wording.

Required diagnosis fields:
- lane
- prompt family
- intended audience
- goal of the piece
- stakes
- relation
- output form
- composition mode
- ambiguity level

The diagnosis step is the core of the product.
If this is wrong, the rest of the compiler becomes elaborate nonsense.

### 3. Risk Assessment

Identify what usually goes wrong for this class of prompt.

Examples:
- prestige voice drift
- generic reassurance
- repetition as depth
- rhetorical-situation blindness
- over-structured business tone in intimate writing
- under-structured output in framework-dependent tasks

The compiler should reason in terms of likely failure pressure, not just stylistic preference.

### 4. Policy Selection

Choose transformation rules based on diagnosis and risk.

Rule types:
- clarification rules
- structure rules
- audience-grounding rules
- obligation rules
- anti-pattern suppression rules
- creativity-preservation rules

Important:
- the compiler should not over-structure inherently open tasks
- the compiler should not preserve vagueness when the task clearly needs framework

### 5. Prompt Construction

Build the compiled prompt from:
- task framing
- audience and obligation framing
- output requirements
- hard constraints
- suppression instructions
- optional quality bar guidance

The compiled prompt should be stronger because it is more situationally precise, not because it is longer.

### 6. Validation

Every compiler move should remain empirically testable.

The lab should compare:
- raw prompt vs compiled prompt
- compiled prompt variant A vs compiled prompt variant B
- rule on vs rule off
- suppression on vs suppression off

The primary measured signal is not internal elegance.
It is panel-preference lift, interpreted against human preference when reviews exist.

## Compiler Schema

The prompt compiler should emit a structured record, not just a rewritten prompt.

See `data/prompt_compiler_schema.json`.

The schema is designed to preserve:
- what the user originally asked
- how the system diagnosed it
- what risks it predicted
- what rules it applied
- what prompt it produced
- why those moves were justified

That traceability matters because:
- the lab needs to know which compiler moves helped
- operator review needs to know what assumptions were made
- future rule activation needs rule-level provenance

## Rule Promotion And Characterization

Compiler rules should move through four stages.

### 1. Candidate

Status:
- hypothesized
- not trusted

Evidence:
- one or two promising packets
- maybe one family only

Usage:
- manual testing only

### 2. Provisional

Status:
- early signal

Evidence:
- repeated improvement within one family or one lane

Usage:
- allowed in controlled A/B prompt compilation

### 3. Active

Status:
- fit for controlled compiler use within its characterized scope

Evidence:
- repeated wins across multiple prompt families
- panel-preference lift is stable
- human comparison class is known or explicitly marked insufficient
- no major degradation on adjacent dimensions

Usage:
- enabled in the prompt compiler by default for matching scopes

### 4. Core

Status:
- strong panel-preference finding

Evidence:
- cross-family
- cross-model
- durable under reread and human review

Usage:
- baseline compiler behavior unless explicitly overridden

## Scope Discipline

The compiler should explicitly distinguish between three kinds of rule knowledge.

### Universal Rule

Use when:
- the rule helps across multiple prompt families
- the rule helps across multiple model families
- the panel preference survives human comparison as aligned or consciously accepted as LLM-specific

### Family-Specific Rule

Use when:
- the rule helps within a clear rhetorical family or form
- evidence is stable within that family
- transfer outside the family is unproven or mixed

### Model-Specific Rule

Use when:
- the rule helps one generator or model family
- the same rule is mixed, neutral, or harmful elsewhere

Model-specific rules are not embarrassments.
They are part of the product's routing intelligence.
But they should not be promoted as global findings.

## Experimental Method

The compiler should be validated through a small set of disciplined experiment types:

### 1. Raw Vs Compiled

Purpose:
- determine whether compilation itself improves outcomes over naive prompting

### 2. Rule On Vs Rule Off

Purpose:
- isolate the effect of one transformation rule

### 3. Variant A Vs Variant B

Purpose:
- compare competing compilation policies for the same task diagnosis

### 4. Cross-Model Replication

Purpose:
- detect whether a win is universal, family-local, or model-specific

The main mistake to avoid is claiming a universal compiler benefit when the gain only exists on one model family, one evaluator panel, or one unreviewed preference pattern.

## First Transformation Rules To Test

These are the first ten rules worth testing as compiler hypotheses.

### 1. Name the Audience

If the request is vague about recipient, infer or ask the model to infer a real audience instead of leaving the prompt socially ungrounded.

### 2. State the Goal Before Style

When the request mixes tone and task, force the compiler to articulate function before aesthetic treatment.

### 3. Distinguish Open From Structured Work

Require the compiler to choose `creative_open`, `strict_framework`, or `hybrid`.

### 4. Add Stakes And Obligation

Private or consequential writing should name what the piece owes the reader, not just what it wants to sound like.

### 5. Suppress Prestige Drift

If the prompt family often yields solemn prestige voice, add grounding instructions that favor inhabited specificity over elevated abstraction.

### 6. Suppress Repetition In Private Forms

For letters, apologies, resignations, and intimate notes, recurrence should be limited unless explicitly justified by audience and occasion.

### 7. Preserve Repetition In Public Rhetoric When Functional

For speeches, manifestos, campaigns, and exhortation, repetition may be preserved if it builds cumulative force.

### 8. Make Deliverable Shape Explicit In Business Writing

If the task implies a frameworked artifact, tell the model the required shape before asking for tone or creativity.

### 9. Add Concrete Success Criteria

Compiled prompts should name what would make the result successful for the intended reader.

### 10. Surface Likely Failure Modes

The prompt should warn against the few most probable errors for that family, not spray generic caution everywhere.

## Product Metrics

The compiler should be evaluated on:

- raw-vs-compiled win rate
- panel-preference lift
- characterization label distribution
- win rate by lane
- win rate by prompt family
- win rate by model family
- win rate by rule id
- win rate by rule scope
- reduction in known anti-pattern frequency
- impact on pair distinctiveness
- human confidence in final judgment
- human alignment rate
- stability on reread

The metrics should always be sliceable enough to answer:
- what the panel prefers broadly
- what the panel prefers only in one family
- what the panel prefers only on one generator
- which preferences humans align with, reject, or leave unresolved

The failure condition is straightforward:
- if compiled prompts do not produce stable, interpretable panel-preference lift under blinded review, the compiler is not real yet

## Data Products Needed

To make the compiler operational, the lab needs:

- rule ledger
- prompt diagnosis ledger
- raw vs compiled experiment support
- compiler trace storage
- family-level rule performance analytics
- model-level rule performance analytics
- human review fields that can say whether panel-preferred compiler moves aligned with or distorted the user's request

## Near-Term Build Sequence

### Phase 1

- define compiler schema
- define rule IDs
- define rule status model
- store compiled prompt traces
- record characterization axes for panel preference and human preference

### Phase 2

- run raw-vs-compiled paired experiments
- compare outputs under Muse, Athena, Apollo, and human review
- attach panel-preference lift and human comparison labels back to the specific rules applied

### Phase 3

- activate only stable panel-preferred rules in controlled live compilation
- let council recommendations propose compiler rule candidates
- promote rules only through repeated panel evidence
- keep aligned, divergent, LLM-specific, human-specific, and insufficient-data labels visible
- keep local wins local unless cross-model replication proves broader support

## Operating Principle

The compiler should never become a second source of elegant delusion.

It succeeds only if it makes the user's actual request more legible to the model without replacing the user's intention with the lab's house taste.
