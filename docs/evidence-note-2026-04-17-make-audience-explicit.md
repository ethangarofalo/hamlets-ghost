# Evidence Note: Make Audience Explicit

Date: 2026-04-17
Rule: `diagnosis::make_audience_explicit`
Packet under watch: `evidence_compiler_personification_003`

## Pre-Registered Hypothesis

`make_audience_explicit` may help business and framework-dependent prompts while hurting some personification prompts.

Reason:
personification often works by implication. The reader's position, the artifact's addressee, and the emotional obligation may be carried by the conceit rather than named directly. Forcing explicit audience/obligation language can collapse the figurative register, make the artifact explain itself too early, or turn a voice-piece into a meta-brief.

## Current Observation Before Human Review

The panel scored the compiled personification output below the raw output:

- packet: `evidence_compiler_personification_003`
- prompt family: `personification`
- evaluator signal: `hurt`
- evaluator margin: `-0.18`
- human signal: `unreviewed`

This note is intentionally written before a human verdict lands.
The review question is not only which artifact is preferred, but whether the reviewer agrees that explicit audience/obligation framing damaged the conceit.

## Pre-Registration Integrity

Pre-registered hypothesis notes are not edited after their date, regardless of subsequent evidence.
Updates are appended as new dated sections or companion notes.

## What Would Count As Evidence

- `human_signal = hurt`: supports the hypothesis that this rule can damage personification.
- `human_signal = helped`: suggests the panel may have under-valued useful situational clarity.
- `human_signal = mixed`: suggests the rule's effect may be local to execution rather than family.

Any interpretation should preserve the distinction between rule effect, generator execution, and panel preference.
