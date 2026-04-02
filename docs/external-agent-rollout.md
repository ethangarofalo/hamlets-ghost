# External Agent Rollout

Last updated: 2026-04-02

This document defines how the Creativity Lab should integrate:
- `Genesis = OpenClaw` as an alternate generator
- `Muse = internal evaluator` as the continuity anchor
- `Hermes = external evaluator` as a true outside opinion

See also: `docs/theron-genesis-adapter.md` for the Telegram-bot adapter contract for Theron as Genesis.

The core principle is:
- external opinion should increase epistemic tension without increasing operational chaos

## Why This Exists

The lab becomes more worthwhile when it contains real disagreement:
- a generator with a distinct creative signature
- an internal evaluator that preserves continuity with past runs
- an outside evaluator that is not just the same voice under a different name

But the lab stops being trustworthy if outside models are given broad backend power too early.

So the right move is:
- keep the lab core local
- integrate external models through narrow, validated interfaces
- expand authority only after calibration evidence exists

## Target Architecture

### Role stack
1. `genesis_local`
   - current local/default generator path
2. `genesis_openclaw`
   - alternate generator path for paired experiments
3. `muse_internal`
   - default internal evaluator and continuity anchor
4. `hermes_external`
   - external evaluator running as a bounded second opinion
5. `human_operator`
   - final calibration and governance authority

### Design rule

External agents should not directly own:
- scheduler state
- DB schema changes
- promotion logic
- policy mutation
- deployment decisions

They should operate through:
- provider adapters
- strict JSON contracts
- stored provenance
- reversible configuration

## System Boundaries

### Keep local
- experiment scheduling
- storage and migrations
- promotion gates
- safety rules
- analytics and audit history

### Externalize carefully
- generation for selected lanes or families
- evaluator judgments
- council-style synthesis

### Never externalize without a second layer of control
- direct DB writes
- code rewrites
- promotion beyond shadow
- evaluator policy changes

## Provider Abstraction Plan

The codebase should move toward explicit role-based provider routing.

### Needed abstraction

Introduce a provider adapter layer for:
- generation
- evaluation
- council review

Each role should be configurable by:
- provider name
- model name
- timeout
- retry policy
- cost budget
- schema validator

Suggested provider values:
- `openai`
- `anthropic`
- `ollama`
- `openclaw_gateway`
- future hosted adapter names

### Contract rule

Every external role must return validated JSON only.

Minimum required protections:
- request timeout
- retry on transient failure only
- parse validation
- fallback classification on schema failure
- provider identity stored in provenance

## External Hermes Plan

### Stage 1: Shadow judge only

Hermes external may:
- read prompt and artifact
- return scores and critique
- log its judgment

Hermes external may not:
- affect promotions
- block experiments
- mutate prompts
- trigger retries or rewrites

Required measurements:
- Muse/Hermes agreement rate
- divergence distribution
- constraint disagreement rate
- parse-failure rate
- timeout rate
- cost per scored artifact
- correlation with human review where available

### Stage 2: Advisory influence

Hermes external may:
- nominate artifacts for human review
- flag runs for disagreement inspection
- contribute to council packets

Still may not:
- promote or demote artifacts on its own
- rewrite evaluator policy

### Stage 3: Narrow operational authority

Hermes external may:
- act as a veto only in pre-approved narrow cases
- for example: large disagreement plus uncertain constraints plus human-review-required lane

This stage requires:
- stable parse behavior
- acceptable cost and latency
- demonstrated usefulness in human-reviewed disagreements

## OpenClaw Genesis Plan

### Stage 1: Bounded generator

OpenClaw Genesis should start only on selected prompt families.

Recommended first families:
- `personification`
- `genre_mismatch`
- one business family with clear constraints

OpenClaw Genesis should run:
- in paired experiments against local Genesis
- with identical task prompts and constraints
- with provenance explicitly recording generator source

### Stage 2: Alternating lane trials

Once stable, OpenClaw Genesis may:
- own selected batch slices
- alternate with local Genesis within the same family
- contribute to family-level comparison reports

### Stage 3: Expanded generation scope

Only after repeated reliable runs:
- more prompt families
- more lanes
- more autonomous scheduling within approved templates

## Paired Experiment Design

The lab should not replace local Genesis immediately.
It should compare generators head-to-head.

### Minimum paired packet
- same prompt
- same constraints
- same lane
- same prompt family
- `genesis_local` artifact
- `genesis_openclaw` artifact
- `muse_internal` scores for both
- `hermes_external` scores for both
- human review sample when disagreement is high

### Questions to answer
- Does OpenClaw produce a distinct artifact signature?
- Does external Hermes catch issues Muse misses?
- Do Muse and Hermes disagree in ways humans find informative?
- Which generator/evaluator pair produces the strongest useful novelty?

## Required Provenance Additions

The following should be explicitly stored per run:
- `generator_provider`
- `generator_model`
- `generator_role_id`
- `evaluator_provider`
- `evaluator_model`
- `evaluator_role_id`
- `external_judge_shadow`
- `paired_run_group`
- `disagreement_reason_code` when detectable

If schema changes are deferred, these may begin as JSON fields inside existing provenance storage.

## Safety Conditions Before Rollout

Before integrating external roles:
- git checkpoint exists
- preflight passes
- provider config can be turned off without code edits
- timeouts and retries are bounded
- parse failures are classified as invalid, not mistaken for real judgments
- blank artifacts remain invalidated before scoring

## Implementation Sequence

### Phase 1: External Hermes shadow mode
- add evaluator provider config by role
- add external Hermes adapter
- store external Hermes judgments separately from Muse
- add disagreement analytics
- keep promotion logic unchanged

### Phase 2: OpenClaw Genesis bounded mode
- add generator provider config by role
- add paired-run support
- run local Genesis vs OpenClaw Genesis on a limited family set
- compare score distributions and human preferences

### Phase 3: Structured disagreement review
- build a disagreement queue
- sample high-divergence artifacts for human review
- track which evaluator better matches human judgment

### Phase 4: Advisory authority
- let external Hermes influence review routing
- let OpenClaw Genesis own approved experimental slices

### Phase 5: Earned authority
- expand only where calibration, reliability, and reversibility are strong

## Success Criteria

This rollout is succeeding if:
- external Hermes disagrees in meaningful, human-useful ways
- OpenClaw Genesis produces measurably distinct artifact profiles
- lab reliability remains stable
- council summaries become more informative, not more confused
- human calibration becomes more precise, not less

## Failure Signals

Pause or narrow the rollout if:
- parse failures spike
- evaluator disagreement becomes noisy rather than useful
- external costs rise without added decision value
- OpenClaw outputs are more volatile than informative
- provenance becomes too weak to reconstruct why outcomes happened

## Bottom Line

The goal is not to let outside agents take over the lab.

The goal is to create a lab that learns from structured disagreement:
- one generator can surprise the system
- one evaluator can preserve continuity
- one outside judge can challenge internal taste
- the human can decide what that disagreement really means
