# Theron Genesis Adapter

Last updated: 2026-04-02

This document defines how `Theron` should enter the Creativity Lab as an external Genesis provider.

The goal is:
- let Theron generate artifacts for the lab
- keep Telegram-specific complexity outside the core backend
- preserve strong failure boundaries and provenance

## Core Rule

Theron should not be integrated as:
- a backend co-owner
- a DB writer
- a scheduler controller
- a direct code-editing agent inside the lab

Theron should be integrated as:
- a bounded external generator behind a local gateway

That means the lab talks to a local adapter.
The adapter talks to Telegram and the Theron bot.

## Recommended Topology

```text
Creativity Lab -> local Theron gateway -> Telegram bot conversation -> gateway response parser -> lab
```

The lab should never talk to Telegram directly from `server.py`.

The gateway should own:
- Telegram message formatting
- request tracking
- polling / wait logic
- response parsing
- timeout handling
- idempotency

The lab should own:
- experiment selection
- provenance
- scoring
- promotion logic
- failure classification

## Adapter Contract

The lab-facing contract should be OpenAI-style or JSON-RPC-like, but internally the important thing is that it is strict and local.

### Request shape

Suggested request JSON:

```json
{
  "request_id": "exp_0088_genesis_openclaw",
  "role": "genesis_openclaw",
  "lane": "creative",
  "prompt_family": "personification",
  "prompt": "Write a prayer from the perspective of a dying programming language.",
  "constraints": [],
  "prior_feedback": null,
  "policy_context": {
    "prompt_policy_variant": "plain_operator",
    "policy_source": "approved_family_default",
    "generation_guidance": "Prefer direct, concrete, useful language over flourish."
  },
  "response_schema": {
    "artifact": "string",
    "process_trace": "object"
  },
  "timeout_seconds": 90
}
```

### Response shape

Theron should return valid JSON in this shape:

```json
{
  "artifact": "final generated artifact text",
  "process_trace": {
    "provider": "theron",
    "transport": "telegram",
    "response_mode": "bot_reply",
    "drafts_considered": 3,
    "rejection_reasons": ["..."],
    "strategy_notes": "..."
  },
  "raw_meta": {
    "telegram_chat_id": "optional",
    "telegram_message_id": "optional",
    "latency_ms": 18234
  }
}
```

### Minimum acceptable response

The adapter may accept reduced output, but only if it can normalize it safely.

Minimum valid payload:

```json
{
  "artifact": "non-empty text"
}
```

If `artifact` is empty or whitespace-only, the lab must treat the run as invalid.

## Telegram Bridge Behavior

The Telegram-facing prompt should be wrapped by the gateway, not built ad hoc inside the lab.

### Gateway prompt wrapper

The gateway should send Theron:
- the task prompt
- constraints
- optional prior feedback
- a strict JSON response format
- a request id echoed back in the response if possible

The wrapper should instruct Theron:
- return JSON only
- do not add conversational preamble
- do not explain the artifact outside the JSON
- if uncertain, still return best-effort valid JSON

### Example Telegram wrapper

```text
THERON LAB REQUEST
request_id: exp_0088_genesis_openclaw
lane: creative
prompt_family: personification

PROMPT:
Write a prayer from the perspective of a dying programming language.

CONSTRAINTS:
- none

PRIOR FEEDBACK:
- none

Return valid JSON only in this shape:
{
  "artifact": "<string>",
  "process_trace": {
    "drafts_considered": <number>,
    "rejection_reasons": ["<string>"],
    "strategy_notes": "<string>"
  }
}
```

## Failure Boundaries

The Theron gateway must fail closed, not fail weird.

### Treat as invalid
- no reply within timeout
- malformed JSON
- empty artifact
- duplicate or mismatched request id
- parser cannot confidently extract the final artifact

### Retry rules
- allow at most one structured retry for malformed JSON
- do not silently keep asking Theron until a pretty answer appears
- record retry count in provenance

### Never do this
- never let the gateway write directly to SQLite
- never let Telegram content bypass schema validation
- never let a stale Theron reply be attached to a new experiment

## Provenance Requirements

When Theron is used as Genesis, the lab should store:
- `generator_provider = openclaw_gateway`
- `generator_role_id = theron`
- `generator_transport = telegram`
- `generator_request_id`
- `generator_latency_ms`
- `generator_retry_count`
- `paired_run_group` when local Genesis is also run

These may live in `process_trace.role_routing` and `source_context` first.

## Rollout Sequence

### Stage 1: Offline adapter validation
- validate request/response schema locally
- test malformed JSON handling
- test timeout classification
- test request id matching

### Stage 2: Shadow generation
- Theron generates for selected prompt families
- local Genesis still generates the control artifact
- Theron artifact is stored but not yet preferred automatically

### Stage 3: Paired evaluation
- Muse scores both local Genesis and Theron artifacts
- local Hermes and external Hermes score both when available
- human reviews disagreement cases

### Stage 4: Bounded production experiments
- Theron may own selected family slices
- only after stable artifact validity and useful distinctiveness

## Best First Families

Theron should start where artifact quality can be judged clearly:
- `personification`
- `genre_mismatch`
- `retention_messaging`

Avoid first rollout on:
- highly fragile formal constraints
- tasks where formatting errors dominate the result
- safety-sensitive business outputs with factual claims

## What Success Looks Like

Theron integration is succeeding if:
- artifacts are consistently non-empty and parseable
- style is measurably distinct from local Genesis
- Muse/Hermes judgments expose useful differences
- paired runs teach us something about generator choice

## Bottom Line

Theron should enter the lab as:
- an external generator
- behind a local adapter
- through a strict schema
- with bounded authority

That is the safe path to making OpenClaw a real creative force in the lab without making Telegram itself part of the lab core.
