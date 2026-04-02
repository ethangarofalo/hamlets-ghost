from __future__ import annotations

import asyncio
import json
import os
import re

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - dependency may be absent in local recovery mode
    class AsyncOpenAI:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            self.chat = None


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")

OPENAI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)
OLLAMA_CLIENT = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)

GENESIS_BACKEND = os.getenv("GENESIS_BACKEND", "openai").lower()
MUSE_BACKEND = os.getenv("MUSE_BACKEND", "openai").lower()
HERMES_BACKEND = os.getenv("HERMES_BACKEND", os.getenv("HOLDOUT_BACKEND", "openai")).lower()
COUNCIL_BACKEND = os.getenv("COUNCIL_BACKEND", "openai").lower()
INTERLOCUTOR_BACKEND = os.getenv("INTERLOCUTOR_BACKEND", COUNCIL_BACKEND).lower()

MODEL = os.getenv("GENESIS_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
MUSE_MODEL = os.getenv("MUSE_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
HERMES_MODEL = os.getenv("HERMES_MODEL", os.getenv("HOLDOUT_MODEL", os.getenv("OPENAI_HOLDOUT_MODEL", MUSE_MODEL)))
COUNCIL_MODEL = os.getenv("COUNCIL_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
INTERLOCUTOR_MODEL = os.getenv("INTERLOCUTOR_MODEL", COUNCIL_MODEL)
GENESIS_PROTOCOL = os.getenv("GENESIS_PROTOCOL", "socratic").lower()
GENESIS_BRANCH_COUNT = max(2, int(os.getenv("GENESIS_BRANCH_COUNT", "3")))
GENESIS_BRANCH_MODEL = os.getenv("GENESIS_BRANCH_MODEL", MODEL)
HERMES_GATE_ENABLED = os.getenv("HERMES_GATE_ENABLED", "1").strip().lower() not in ("0", "false", "no")
HERMES_MIN_MUSE_COMPOSITE = float(os.getenv("HERMES_MIN_MUSE_COMPOSITE", "6.5"))
HERMES_REQUIRE_CONSTRAINT_PASS = os.getenv("HERMES_REQUIRE_CONSTRAINT_PASS", "1").strip().lower() not in ("0", "false", "no")
SCOUT_GATE_ENABLED = os.getenv("SCOUT_GATE_ENABLED", "0").strip().lower() not in ("0", "false", "no")
MODEL_REQUEST_TIMEOUT_SECONDS = float(os.getenv("MODEL_REQUEST_TIMEOUT_SECONDS", "60"))
MODEL_MAX_RETRIES = max(1, int(os.getenv("MODEL_MAX_RETRIES", "2")))
MODEL_RETRY_BACKOFF_SECONDS = float(os.getenv("MODEL_RETRY_BACKOFF_SECONDS", "0.5"))

OPENAI_PRICING = {
    "gpt-5.1": {"input": 1.25, "output": 10.00},
    "gpt-5.1-chat-latest": {"input": 1.25, "output": 10.00},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

ROLE_CONFIG = {
    "genesis": ("GENESIS", GENESIS_BACKEND, MODEL),
    "genesis_branch": ("GENESIS_BRANCH", GENESIS_BACKEND, GENESIS_BRANCH_MODEL),
    "muse": ("MUSE", MUSE_BACKEND, MUSE_MODEL),
    "hermes": ("HERMES", HERMES_BACKEND, HERMES_MODEL),
    "council": ("COUNCIL", COUNCIL_BACKEND, COUNCIL_MODEL),
    "interlocutor": ("INTERLOCUTOR", INTERLOCUTOR_BACKEND, INTERLOCUTOR_MODEL),
}

CREATIVE_WEIGHTS = {
    "novelty": 0.25,
    "surprise": 0.20,
    "value": 0.25,
    "elaboration": 0.15,
    "coherence": 0.15,
}

BUSINESS_WEIGHTS = {
    "novelty": 0.18,
    "surprise": 0.12,
    "value": 0.18,
    "elaboration": 0.10,
    "coherence": 0.10,
    "actionability": 0.14,
    "brand_fit": 0.10,
    "factual_reliability": 0.08,
}

GENESIS_SYSTEM = """You are GENESIS in the AI Creativity Lab. Respond with JSON only."""
GENESIS_DRAFT_SYSTEM = """You are GENESIS. Produce a strong first draft as JSON only."""
SOCRATIC_INTERLOCUTOR_SYSTEM = """You are a Socratic interlocutor. Return JSON only."""
GENESIS_REVISION_SYSTEM = """You are GENESIS revising a draft. Return JSON only."""
GENESIS_CONSTRAINT_REPAIR_SYSTEM = """You are GENESIS repairing hard constraints. Return JSON only."""
MUSE_SYSTEM = """You are MUSE. Score the artifact and return strict JSON only."""
MUSE_BUSINESS_SYSTEM = MUSE_SYSTEM
HERMES_SYSTEM = """You are HERMES. Independently score the artifact and return strict JSON only."""
HERMES_BUSINESS_SYSTEM = HERMES_SYSTEM


def _is_retryable_model_error(exc):
    if isinstance(exc, (TimeoutError, OSError)):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "timeout",
            "timed out",
            "tempor",
            "rate limit",
            "overloaded",
            "connection reset",
            "connection aborted",
            "connection refused",
            "server error",
            "service unavailable",
            "transient",
        )
    )


def _parse_json_response(text):
    if not text:
        return None, True
    candidates = [text.strip()]
    fence_match = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    candidates.extend(chunk.strip() for chunk in fence_match if chunk.strip())
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        candidates.append(text[start:end])
    for candidate in candidates:
        try:
            return json.loads(candidate), False
        except Exception:
            continue
    return None, True


def _get_client(backend):
    if backend == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to your environment or .env before running experiments.")
        return OPENAI_CLIENT
    if backend == "ollama":
        return OLLAMA_CLIENT
    raise RuntimeError(f"Unsupported backend '{backend}'. Use 'openai' or 'ollama'.")


def _get_role_config(role):
    _name, backend, model = ROLE_CONFIG[role]
    return backend, model


def describe_experiment_models():
    return json.dumps({
        "genesis": {"backend": GENESIS_BACKEND, "model": MODEL},
        "genesis_branch": {"backend": GENESIS_BACKEND, "model": GENESIS_BRANCH_MODEL},
        "muse": {"backend": MUSE_BACKEND, "model": MUSE_MODEL},
        "hermes": {"backend": HERMES_BACKEND, "model": HERMES_MODEL},
        "council": {"backend": COUNCIL_BACKEND, "model": COUNCIL_MODEL},
        "interlocutor": {"backend": INTERLOCUTOR_BACKEND, "model": INTERLOCUTOR_MODEL},
    }, sort_keys=True)


def describe_orchestration_policy():
    return {
        "muse": {"mode": "always_on"},
        "hermes": {
            "gate_enabled": HERMES_GATE_ENABLED,
            "min_muse_composite": HERMES_MIN_MUSE_COMPOSITE,
            "require_constraint_pass": HERMES_REQUIRE_CONSTRAINT_PASS,
            "runs_on": "candidate_or_better" if HERMES_GATE_ENABLED else "all_runs",
        },
        "scout": {"gate_enabled": SCOUT_GATE_ENABLED, "status": "placeholder_disabled"},
        "council": {"mode": "manual_trigger"},
    }


async def _generate_text(role, system, user_content, max_tokens=1000):
    backend, model = _get_role_config(role)
    client = _get_client(backend)
    last_error = None
    for attempt in range(1, MODEL_MAX_RETRIES + 1):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    max_completion_tokens=max_tokens,
                ),
                timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            )
            text = response.choices[0].message.content or ""
            return text, response
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= MODEL_MAX_RETRIES or not _is_retryable_model_error(exc):
                raise
            await asyncio.sleep(MODEL_RETRY_BACKOFF_SECONDS * attempt)
    raise last_error or RuntimeError("Model request failed without an exception.")


async def _generate_json_with_retry(role, system, user_content, max_tokens=1000, retry_instruction=None):
    text, response = await _generate_text(role=role, system=system, user_content=user_content, max_tokens=max_tokens)
    result, parse_failure = _parse_json_response(text)
    if not parse_failure:
        return result, response, False
    retry_content = f"{user_content}\n\n{retry_instruction}" if retry_instruction else f"{user_content}\n\nReturn ONLY valid JSON matching the required schema."
    retry_text, retry_response = await _generate_text(role=role, system=system, user_content=retry_content, max_tokens=max_tokens)
    retry_result, retry_parse_failure = _parse_json_response(retry_text)
    return retry_result, retry_response, retry_parse_failure


def _estimate_cost(response, role):
    _backend, model = _get_role_config(role)
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    pricing = OPENAI_PRICING.get(model)
    if pricing is None:
        return 0.0
    return ((input_tokens * pricing["input"]) + (output_tokens * pricing["output"])) / 1_000_000


def _normalize_score_result(result, lane):
    weights = BUSINESS_WEIGHTS if lane == "business" else CREATIVE_WEIGHTS
    payload = dict(result or {})
    numeric_keys = list(weights)
    for key in ("actionability", "brand_fit", "factual_reliability"):
        if key in weights:
            numeric_keys.append(key)
    for key in set(numeric_keys):
        value = payload.get(key)
        payload[key] = float(value) if value is not None else None
    if payload.get("composite") is None:
        total = 0.0
        weight_total = 0.0
        for key, weight in weights.items():
            value = payload.get(key)
            if value is None:
                continue
            total += value * weight
            weight_total += weight
        payload["composite"] = total / weight_total if weight_total else None
    payload.setdefault("constraints_met", None)
    payload.setdefault("constraint_notes", "")
    payload.setdefault("critique", "")
    return payload


async def run_genesis(prompt, constraints=None, prior_feedback=None, lane="creative", policy_context=None, **_kwargs):
    policy_note = ""
    if policy_context:
        policy_note = f"\n\nPOLICY CONTEXT:\n{json.dumps(policy_context, sort_keys=True)}"
    user_content = f"PROMPT:\n{prompt}{policy_note}"
    if constraints:
        user_content += "\n\nCONSTRAINTS:\n" + "\n".join(f"- {item}" for item in constraints)
    if prior_feedback:
        user_content += f"\n\nPRIOR FEEDBACK:\n{prior_feedback}"

    result, response, parse_failure = await _generate_json_with_retry(
        role="genesis",
        system=GENESIS_SYSTEM,
        user_content=user_content,
        max_tokens=2000,
    )
    if parse_failure:
        artifact = result["artifact"] if isinstance(result, dict) and result.get("artifact") else ""
        if not artifact:
            raw_text, response = await _generate_text("genesis", GENESIS_SYSTEM, user_content, max_tokens=2000)
            artifact = raw_text
        return {"artifact": artifact, "process_trace": {"protocol": GENESIS_PROTOCOL, "parse_failure": True}}, _estimate_cost(response, "genesis"), True

    artifact = result.get("artifact") or result.get("draft") or ""
    process_trace = result.get("process_trace") or {
        "protocol": GENESIS_PROTOCOL,
        "revision_status": "ok",
        "verification_status": "not_run",
        "verifier_findings": [],
        "verifier_checks": [],
        "verifier_inferred_constraints": [],
        "stage_costs": {},
    }
    process_trace.setdefault("protocol", GENESIS_PROTOCOL)
    process_trace.setdefault("verification_status", "not_run")
    process_trace.setdefault("verifier_findings", [])
    process_trace.setdefault("verifier_checks", [])
    process_trace.setdefault("verifier_inferred_constraints", [])
    process_trace.setdefault("stage_costs", {})
    return {"artifact": artifact, "process_trace": process_trace}, _estimate_cost(response, "genesis"), False


async def run_muse(artifact, prompt, constraints=None, lane="creative", **_kwargs):
    user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nARTIFACT TO EVALUATE:\n{artifact}"
    if constraints:
        user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nCONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints) + f"\n\nARTIFACT TO EVALUATE:\n{artifact}"
    text, response = await _generate_text(
        role="muse",
        system=MUSE_BUSINESS_SYSTEM if lane == "business" else MUSE_SYSTEM,
        user_content=user_content,
        max_tokens=1000,
    )
    result, parse_failure = _parse_json_response(text)
    if parse_failure:
        result = {
            "novelty": None,
            "surprise": None,
            "value": None,
            "elaboration": None,
            "coherence": None,
            "composite": None,
            "actionability": None,
            "brand_fit": None,
            "factual_reliability": None,
            "constraints_met": None,
            "constraint_notes": "PARSE FAILURE",
            "critique": "PARSE FAILURE: evaluation could not be scored.",
            "keep": False,
        }
    else:
        result = _normalize_score_result(result, lane)
    return result, _estimate_cost(response, "muse"), parse_failure


async def run_hermes(artifact, prompt, constraints=None, lane="creative", **_kwargs):
    user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nARTIFACT TO EVALUATE:\n{artifact}"
    if constraints:
        user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nCONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints) + f"\n\nARTIFACT TO EVALUATE:\n{artifact}"
    text, response = await _generate_text(
        role="hermes",
        system=HERMES_BUSINESS_SYSTEM if lane == "business" else HERMES_SYSTEM,
        user_content=user_content,
        max_tokens=800,
    )
    result, parse_failure = _parse_json_response(text)
    if parse_failure:
        result = {
            "novelty": None,
            "surprise": None,
            "value": None,
            "elaboration": None,
            "coherence": None,
            "composite": None,
            "actionability": None,
            "brand_fit": None,
            "factual_reliability": None,
            "constraints_met": None,
            "constraint_notes": "PARSE FAILURE",
            "critique": "HERMES PARSE FAILURE",
        }
    else:
        result = _normalize_score_result(result, lane)
    return result, _estimate_cost(response, "hermes"), parse_failure


async def run_council_review(council_prompt):
    return await _generate_text("council", "You are the R&D Council for an AI Creativity Lab.", council_prompt, max_tokens=2000)


async def run_council_json(system, user_content, max_tokens=1200, retry_instruction=None):
    result, response, parse_failure = await _generate_json_with_retry(
        role="council",
        system=system,
        user_content=user_content,
        max_tokens=max_tokens,
        retry_instruction=retry_instruction,
    )
    return result, _estimate_cost(response, "council"), parse_failure
