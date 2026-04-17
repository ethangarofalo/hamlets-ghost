# Prompt Science Method

## Purpose

Hamlet's Ghost should treat prompting as an empirical discipline, not a bag of tricks.

The lab is only scientific if it can answer questions like:

- which transformation helped
- for which task family
- on which generator or model family
- according to which judges
- under what human review outcome

If the system cannot keep those variables separate, it will mistake house taste for doctrine.

## Lab Role Vs Product Role

The lab exists to discover, test, and falsify prompt-improvement rules.

The product should only apply rules that have survived that testing.

That means:

- the lab is allowed to hold competing hypotheses at once
- the product is not allowed to pretend a rule is universal when it is only model-specific
- the council should promote rules into governed product policy only after evidence has been sorted by scope

## Core Variables

Prompt quality is not a single-variable problem.

At minimum, the lab must preserve:

- target generator or model family
- evaluator panel composition
- writing lane
- prompt family
- rhetorical form
- audience and stakes diagnosis
- prompt-transformation rule or policy variant
- human review outcome

The point is not to eliminate interaction effects.
The point is to observe them honestly.

## Rule Scope Tiers

Every prompt-transformation rule should be tracked at one of three scopes.

### 1. Universal

Definition:
- repeated evidence that a rule helps across multiple prompt families and multiple model families

Meaning:
- rare
- valuable
- the closest thing to product doctrine

### 2. Family-Specific

Definition:
- a rule that reliably helps within a prompt family or rhetorical form

Examples:
- suppress private-form repetition in resignation letters
- make deliverable shape explicit in planning memos

Meaning:
- useful product routing knowledge
- not automatically portable outside its family

### 3. Model-Specific

Definition:
- a rule that helps Genesis, Theron, or another model family in a way that does not generalize

Meaning:
- valuable for routing and adaptation
- not taxonomy-grade doctrine by itself

The product must not flatten model-specific wins into universal rules.

## Experimental Units

The lab should treat these as distinct experiment types:

### Raw Vs Compiled

Purpose:
- test whether compilation itself improves outcomes over the user's original request

Control:
- same generator
- same task
- same evaluators
- same human review standard

### Rule On Vs Rule Off

Purpose:
- isolate the effect of one transformation rule

Control:
- compiled prompt baseline stays fixed except for the targeted rule

### Variant A Vs Variant B

Purpose:
- compare two competing policy implementations for the same diagnosed task

Example:
- audience-first compilation vs structure-first compilation

### Cross-Model Replication

Purpose:
- distinguish model-specific gains from broader compiler knowledge

Example:
- a rule helps Genesis on speeches but hurts Theron on speeches

That is not failure.
That is evidence about scope.

## Minimal Scientific Discipline

Every serious rule test should preserve:

- hypothesis
- intervention
- expected upside
- expected downside
- target scope
- packet ids or experiment ids
- evaluator outcome
- human outcome where available

The lab does not need formal statistics to be serious.
It does need disciplined comparison and honest provenance.

## Promotion Logic

A rule should move through these judgments:

1. Does it help at all?
2. Where does it help?
3. Where does it hurt?
4. Is the gain human-visible or only evaluator-visible?
5. Is the effect specific to one model, one family, or broader?

Promotion should require both success and boundedness.

A rule that helps in one place and harms in another is not invalid.
It is conditional.

## Council Responsibility

The council should not ask, "What is the best prompt?"

It should ask:

- which rule classes are showing signal
- which signals are only model-specific
- which families still need replication
- where evaluator judgment is overstating confidence
- which next experiment would collapse the most uncertainty

The council's serious role is to reduce uncertainty, not to produce ornate summaries.

## Product Consequence

The product should eventually behave less like a static compiler and more like a governed routing system:

- diagnose the request
- choose the right rule family
- adapt to the target model
- preserve traceability
- stay reversible when evidence changes

That is why the lab matters.
It is not trying to discover one perfect prompt.
It is trying to learn when different prompting policies are appropriate.

## Failure Modes To Resist

The lab should actively resist:

- mistaking eloquent summaries for empirical support
- mistaking evaluator consensus for reference signal
- mistaking model-specific behavior for universal doctrine
- mistaking compiled prompt length for prompt quality
- mistaking product convenience for validated policy

If Hamlet's Ghost remembers those five things, it has a real chance to become a science instead of a style system.
