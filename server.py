"""FastAPI surface for Hamlet's Ghost's internal research engine.

This API exists to run packets, preserve judgment evidence, and expose the
lab's current state to operators. It is an internal research surface, not a
public product API.
"""

from __future__ import annotations

import asyncio
from collections import Counter
import hashlib
import json
import os
import traceback as tb
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agents
import database as db
import experiments

load_dotenv()

# --- Experiment status constants ---
STATUS_INVALID = "invalid"
STATUS_CONSTRAINT_FAIL = "constraint_fail"
STATUS_DISCARD = "discard"
STATUS_KEPT = "kept"
STATUS_PROMOTED = "promoted"
STATUS_ERROR = "error"
STATUS_RUNNING = "running"
PROMOTION_CANDIDATE = "candidate"
PROMOTION_SHADOW = "shadow"
KEPT_STATUSES = {STATUS_KEPT, STATUS_PROMOTED}
DISCARDED_STATUSES = {STATUS_DISCARD, STATUS_CONSTRAINT_FAIL, STATUS_INVALID}

# --- Thresholds ---
PROMOTE_COMPOSITE_THRESHOLD = 7.0
KEEP_COMPOSITE_THRESHOLD = 6.5
MAX_DIVERGENCE_FOR_PROMOTION = 1.5
MAX_CONSECUTIVE_DISCARDS = 10
FORCED_ATHENA_LOW_SCORE_MODULO = max(0, int(os.getenv("FORCED_ATHENA_LOW_SCORE_MODULO", "5")))
FORCED_ATHENA_CONSTRAINT_FAIL_MODULO = max(0, int(os.getenv("FORCED_ATHENA_CONSTRAINT_FAIL_MODULO", "3")))
FORCED_ATHENA_UNKNOWN_CONSTRAINT_MODULO = max(0, int(os.getenv("FORCED_ATHENA_UNKNOWN_CONSTRAINT_MODULO", "4")))
DEFAULT_HOST = os.getenv("LAB_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("PORT", "7777"))
ADMIN_TOKEN_HEADER = "X-Admin-Token"
REPO_ROOT = Path(__file__).resolve().parent
TASTE_MEMORY_PATH = REPO_ROOT / "data" / "taste_memory.json"

_runner_task = None
_stop_event = asyncio.Event()
_runner_transition_lock = asyncio.Lock()


class DisagreementDecisionPayload(BaseModel):
    preferred_experiment_id: int | None = None
    rationale: str
    reviewer: str = "human_operator"
    review_channel: str | None = None
    outbound_message_id: str | None = None
    inbound_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PacketResolutionPayload(BaseModel):
    resolution: str
    rationale: str
    reviewer: str = "human_operator"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CouncilActionPayload(BaseModel):
    council_id: int | None = None
    action_type: str
    title: str
    status: str | None = None
    lane: str | None = None
    prompt_family: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def _load_review_reason_tag_catalog() -> dict[str, list[dict[str, Any]]]:
    empty = {
        "anti_patterns": [],
        "quality_signals": [],
        "evaluator_failure_modes": [],
    }
    if not TASTE_MEMORY_PATH.exists():
        return empty
    try:
        payload = json.loads(TASTE_MEMORY_PATH.read_text())
    except Exception:
        return empty

    def _entries(section_name: str) -> list[dict[str, Any]]:
        section = payload.get(section_name) or {}
        items = []
        for entry in section.get("entries") or []:
            tag = entry.get("tag")
            if not tag:
                continue
            items.append({
                "id": entry.get("id"),
                "tag": tag,
                "name": entry.get("name") or tag.replace("_", " "),
                "description": entry.get("description") or entry.get("why_it_fails") or entry.get("why_it_works") or "",
                "lanes": entry.get("lanes") or [],
                "domain": entry.get("domain"),
                "source": entry.get("source"),
            })
        return items

    catalog = {key: _entries(key) for key in empty}
    anti_patterns = catalog.get("anti_patterns") or []
    if not any(entry.get("tag") == "voice_collapse" for entry in anti_patterns):
        anti_patterns.insert(0, {
            "id": "voice_collapse",
            "tag": "voice_collapse",
            "name": "Voice Collapse",
            "description": "Competing generators converge on the same authorial persona, cadence, and aesthetic program, making the pair low-value for comparative judgment.",
            "lanes": ["creative", "business"],
            "domain": "pair_level",
            "source": "system_injected",
        })
    if not any(entry.get("tag") == "repetition_as_depth" for entry in anti_patterns):
        anti_patterns.insert(0, {
            "id": "repetition_as_depth",
            "tag": "repetition_as_depth",
            "name": "Repetition as Depth",
            "description": "Repeated phrasing, claims, or motifs are treated as development even though they do not deepen the thought and may be mismatched to the intended audience or rhetorical situation.",
            "lanes": ["creative", "business"],
            "domain": "audience_conditioned",
            "source": "system_injected",
        })
    catalog["anti_patterns"] = anti_patterns
    return catalog


class StartLabPayload(BaseModel):
    n_experiments: int = 40


class CustomExperimentPayload(BaseModel):
    lane: str = "creative"
    prompt: str
    creativity_type: str = "custom"
    constraints: list[str] = Field(default_factory=list)
    track: str = "custom"
    family: str = "custom_operator"
    hypothesis: str | None = None
    condition: str = "critique_on"
    packet_id: str | None = None
    packet_role_id: str = "genesis"
    packet_primary: bool = True


class ExternalExperimentPayload(BaseModel):
    lane: str = "creative"
    prompt: str
    artifact: str
    creativity_type: str = "custom"
    constraints: list[str] = Field(default_factory=list)
    track: str = "external"
    family: str = "external_operator"
    hypothesis: str | None = None
    condition: str = "critique_on"
    generation_protocol: str = "external_manual"
    packet_id: str | None = None
    packet_role_id: str | None = None
    packet_primary: bool = False
    process_trace: dict[str, Any] = Field(default_factory=dict)
    source_context: dict[str, Any] = Field(default_factory=dict)
    generator_provider: str = "theron_manual"
    generator_role_id: str = "theron"


class ExternalArtifactSubmission(BaseModel):
    id: str = "external"
    artifact: str
    track: str = "external"
    generation_protocol: str = "paired_external"
    generator_provider: str = "theron_manual"
    generator_role_id: str = "theron"
    process_trace: dict[str, Any] = Field(default_factory=dict)
    source_context: dict[str, Any] = Field(default_factory=dict)


class PairedExperimentPayload(BaseModel):
    id: str = "paired"
    lane: str = "creative"
    prompt: str
    creativity_type: str = "custom"
    constraints: list[str] = Field(default_factory=list)
    track: str = "paired"
    family: str = "paired_operator"
    hypothesis: str | None = None
    condition: str = "critique_on"
    generation_protocol: str = "paired_native"
    packet_id: str | None = None
    run_local: bool = True
    generate_external: bool = False
    local_role_id: str = "genesis"
    external_id: str = "theron"
    external_track: str = "paired_external"
    external_generation_protocol: str = "theron_paired_native"
    external_role_id: str = "theron"
    external_provider: str | None = None
    external_artifacts: list[ExternalArtifactSubmission] = Field(default_factory=list)


class CompilerComparePayload(BaseModel):
    id: str = "compiler_compare"
    lane: str = "creative"
    prompt: str
    creativity_type: str = "custom"
    constraints: list[str] = Field(default_factory=list)
    track: str = "compiler_compare"
    family: str = "custom_operator"
    hypothesis: str | None = None
    condition: str = "critique_on"
    packet_id: str | None = None
    local_role_id: str = "genesis"


def _hash_prompt(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _new_packet_id():
    return f"packet_{uuid.uuid4().hex[:12]}"


def _build_packet_task(task, *, packet_id=None, packet_role_id=None, packet_primary=True):
    clone = dict(task)
    clone["packet_id"] = packet_id or clone.get("packet_id") or _new_packet_id()
    clone["packet_role_id"] = packet_role_id or clone.get("packet_role_id") or "genesis"
    clone["packet_primary"] = packet_primary if packet_primary is not None else clone.get("packet_primary", True)
    return clone


def _get_admin_api_token():
    return os.getenv("LAB_ADMIN_TOKEN") or os.getenv("ADMIN_API_TOKEN")


def _require_admin_token(provided_token):
    expected_token = _get_admin_api_token()
    if not expected_token:
        return JSONResponse(
            {"error": "Admin API token is not configured. Set LAB_ADMIN_TOKEN to enable write endpoints."},
            status_code=503,
        )
    if provided_token != expected_token:
        return JSONResponse(
            {"error": f"Unauthorized. Provide {ADMIN_TOKEN_HEADER} for admin routes."},
            status_code=401,
        )
    return None


def _payload_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    raise TypeError(f"Unsupported payload type: {type(payload)!r}")


def _review_verdict(metadata: dict[str, Any] | None) -> str:
    verdict = str((metadata or {}).get("review_verdict") or "").strip().lower()
    return verdict if verdict in getattr(db, "REVIEW_VERDICTS", ()) else "preferred"


def _sanitize_experiment_record(record):
    sanitized = dict(record or {})
    raw_traceback = sanitized.pop("error_traceback", None)
    if raw_traceback:
        sanitized["has_internal_error_details"] = True
        if sanitized.get("status") == "error":
            sanitized["error_summary"] = "Experiment failed internally. Check server logs for full details."
    return sanitized


GENESIS_PROMPT_BUNDLE = "\n\n".join([
    agents.GENESIS_SYSTEM,
    getattr(agents, "GENESIS_DRAFT_SYSTEM", ""),
    getattr(agents, "SOCRATIC_INTERLOCUTOR_SYSTEM", ""),
    getattr(agents, "GENESIS_REVISION_SYSTEM", ""),
])
GENESIS_HASH = _hash_prompt(GENESIS_PROMPT_BUNDLE)
MUSE_HASH = _hash_prompt(agents.MUSE_SYSTEM)
MUSE_BUSINESS_HASH = _hash_prompt(agents.MUSE_BUSINESS_SYSTEM)
ATHENA_HASH = _hash_prompt(agents.ATHENA_SYSTEM)
ATHENA_BUSINESS_HASH = _hash_prompt(agents.ATHENA_BUSINESS_SYSTEM)
APOLLO_HASH = _hash_prompt(agents.APOLLO_SYSTEM)
APOLLO_BUSINESS_HASH = _hash_prompt(agents.APOLLO_BUSINESS_SYSTEM)


async def seed_hypotheses():
    for h_id, h_data in experiments.HYPOTHESES.items():
        await db.insert_hypothesis(h_id, h_data["description"], h_data["lane"])
    await db.store_prompt_version(GENESIS_HASH, "genesis", GENESIS_PROMPT_BUNDLE)
    await db.store_prompt_version(MUSE_HASH, "muse", agents.MUSE_SYSTEM)
    await db.store_prompt_version(MUSE_BUSINESS_HASH, "muse_business", agents.MUSE_BUSINESS_SYSTEM)
    await db.store_prompt_version(ATHENA_HASH, "athena", agents.ATHENA_SYSTEM)
    await db.store_prompt_version(ATHENA_BUSINESS_HASH, "athena_business", agents.ATHENA_BUSINESS_SYSTEM)


def _generator_role_id(task):
    return task.get("generator_role_id") or task.get("packet_role_id") or "genesis"


def _build_orchestration_trace(task):
    generator_role = _generator_role_id(task)
    return {
        "policy": agents.describe_orchestration_policy(),
        "planned_agents": [generator_role, "muse", "athena"],
        "executed_agents": [generator_role],
        "skipped_agents": [],
        "gates": {
            "athena": {"eligible": None, "decision": "pending", "reason": "awaiting_muse_triage"},
            "scout": {"eligible": False, "decision": "skipped", "reason": "not_implemented"},
        },
        "task_context": {
            "lane": task.get("lane"),
            "track": task.get("track"),
            "condition": task.get("condition"),
            "hypothesis_id": task.get("hypothesis"),
        },
    }


def _build_role_provenance(task):
    lane = task.get("lane", "creative")
    generator_role = _generator_role_id(task)
    role_provenance = {
        "genesis": {
            **agents.describe_role_runtime("genesis"),
            "prompt_hash": GENESIS_HASH,
            "generation_protocol": "socratic",
        },
        "muse": {
            **agents.describe_role_runtime("muse"),
            "prompt_hash": MUSE_BUSINESS_HASH if lane == "business" else MUSE_HASH,
        },
        "genesis_openclaw": {
            **agents.describe_role_runtime("genesis_openclaw"),
            "prompt_hash": GENESIS_HASH,
            "shadow_only": True,
            "enabled": bool(getattr(agents, "GENESIS_OPENCLAW_SHADOW_ENABLED", False)),
            "eligible_families": sorted(getattr(agents, "GENESIS_OPENCLAW_FAMILIES", set())),
        },
        "theron": {
            **agents.describe_role_runtime("theron"),
            "prompt_hash": GENESIS_HASH,
            "paired_generation_role": True,
            "enabled": bool(getattr(agents, "THERON_GENERATION_ENABLED", False)),
        },
        "athena": {
            **agents.describe_role_runtime("athena"),
            "prompt_hash": ATHENA_BUSINESS_HASH if lane == "business" else ATHENA_HASH,
            "promotion_gate_role": True,
        },
        "apollo": {
            **agents.describe_role_runtime("apollo"),
            "prompt_hash": APOLLO_BUSINESS_HASH if lane == "business" else APOLLO_HASH,
            "shadow_only": True,
            "enabled": bool(getattr(agents, "APOLLO_SHADOW_ENABLED", False)),
        },
    }
    if generator_role in role_provenance:
        role_provenance[generator_role]["generation_protocol"] = task.get("generation_protocol", "socratic")
    return role_provenance


def _should_run_openclaw_shadow(task):
    if not getattr(agents, "GENESIS_OPENCLAW_SHADOW_ENABLED", False):
        return False
    families = getattr(agents, "GENESIS_OPENCLAW_FAMILIES", set())
    if not families:
        return False
    return task.get("family") in families


def _forced_athena_reason(experiment_id, muse_result):
    if not experiment_id or not muse_result:
        return None
    composite = muse_result.get("composite")
    constraints_met = muse_result.get("constraints_met")
    if constraints_met is False and FORCED_ATHENA_CONSTRAINT_FAIL_MODULO and experiment_id % FORCED_ATHENA_CONSTRAINT_FAIL_MODULO == 0:
        return "forced_sample_constraint_fail"
    if constraints_met is None and FORCED_ATHENA_UNKNOWN_CONSTRAINT_MODULO and experiment_id % FORCED_ATHENA_UNKNOWN_CONSTRAINT_MODULO == 0:
        return "forced_sample_unknown_constraints"
    if composite is not None and composite < agents.ATHENA_MIN_MUSE_COMPOSITE:
        if FORCED_ATHENA_LOW_SCORE_MODULO and experiment_id % FORCED_ATHENA_LOW_SCORE_MODULO == 0:
            return "forced_sample_low_muse"
    return None


def _should_run_athena(muse_result, muse_parse_failure, experiment_id=None):
    if muse_parse_failure:
        return False, "muse_parse_failure"
    if not agents.ATHENA_GATE_ENABLED:
        return True, "gate_disabled"

    composite = muse_result.get("composite") if muse_result else None
    constraints_met = muse_result.get("constraints_met") if muse_result else None

    if composite is None:
        return False, "missing_muse_composite"
    if agents.ATHENA_REQUIRE_CONSTRAINT_PASS and constraints_met is False:
        forced_reason = _forced_athena_reason(experiment_id, muse_result)
        return (True, forced_reason) if forced_reason else (False, "constraint_failed_before_athena")
    if composite < agents.ATHENA_MIN_MUSE_COMPOSITE:
        forced_reason = _forced_athena_reason(experiment_id, muse_result)
        return (True, forced_reason) if forced_reason else (False, f"muse_below_threshold_{agents.ATHENA_MIN_MUSE_COMPOSITE:.1f}")
    if constraints_met is None:
        forced_reason = _forced_athena_reason(experiment_id, muse_result)
        if forced_reason:
            return True, forced_reason
    return True, "candidate_threshold_met"


def _extract_verifier_constraint_state(process_trace):
    trace = process_trace or {}
    return {
        "has_effective_constraints": bool(trace.get("verifier_checks") or trace.get("verifier_inferred_constraints")),
        "verification_status": trace.get("verification_status"),
    }


async def _resolve_policy_control(task):
    controls = await db.get_approved_policy_controls()
    family_default = controls.get((task.get("lane"), task.get("family")))
    approved_variant = family_default.get("approved_value") if family_default else None
    resolved = experiments.apply_policy_control(dict(task), approved_default_variant=approved_variant)
    if family_default:
        resolved["policy_operational_status"] = family_default.get("operational_status")
    return resolved


def _enrich_source_context(source_context, task, role_provenance):
    """Add packet metadata and role routing to a source_context dict."""
    ctx = dict(source_context or {})
    ctx.setdefault("role_routing", role_provenance)
    if task.get("packet_id"):
        ctx.setdefault("packet_id", task["packet_id"])
        ctx.setdefault("packet_role_id", task.get("packet_role_id"))
        ctx.setdefault("packet_primary", bool(task.get("packet_primary", True)))
    if task.get("prompt_compiler_mode"):
        ctx.setdefault("prompt_compiler_mode", task.get("prompt_compiler_mode"))
    if task.get("evaluation_prompt"):
        ctx.setdefault("evaluation_prompt", task.get("evaluation_prompt"))
    return ctx


def _init_process_trace(process_trace, role_provenance, orchestration_trace):
    """Ensure all standard keys exist in a process trace dict."""
    trace = dict(process_trace or {})
    trace.setdefault("verification_status", "not_run")
    trace.setdefault("verifier_findings", [])
    trace.setdefault("verifier_checks", [])
    trace.setdefault("verifier_inferred_constraints", [])
    trace.setdefault("stage_costs", {})
    trace.setdefault("role_routing", role_provenance)
    trace["orchestration"] = orchestration_trace
    return trace


def _compact_generator_feedback(feedback_bundle):
    if not feedback_bundle or not feedback_bundle.get("prior_feedback"):
        return None
    return {
        "scope_applied": feedback_bundle.get("scope_applied"),
        "family": feedback_bundle.get("family"),
        "lane": feedback_bundle.get("lane"),
        "reviewed_packets": feedback_bundle.get("reviewed_packets", 0),
        "final_reviewed_packets": feedback_bundle.get("final_reviewed_packets", 0),
        "tentative_reviews": feedback_bundle.get("tentative_reviews", 0),
        "wins": feedback_bundle.get("wins", 0),
        "losses": feedback_bundle.get("losses", 0),
        "top_strengths": feedback_bundle.get("top_strengths", []),
        "top_flaws": feedback_bundle.get("top_flaws", []),
        "prior_feedback": feedback_bundle.get("prior_feedback"),
    }


async def _get_generator_feedback_bundle(task, role_id):
    return await db.get_generator_feedback_for_task(
        role_id,
        family=task.get("family"),
        lane=task.get("lane"),
        epoch=db.CURRENT_EXPERIMENT_EPOCH,
    )


def _attach_generator_feedback(process_trace, source_context, *, role_id, feedback_bundle):
    compact_feedback = _compact_generator_feedback(feedback_bundle)
    if not compact_feedback:
        return process_trace, source_context
    trace = dict(process_trace or {})
    source = dict(source_context or {})
    trace.setdefault("generator_feedback", {})
    source.setdefault("generator_feedback", {})
    trace["generator_feedback"][role_id] = compact_feedback
    source["generator_feedback"][role_id] = compact_feedback
    return trace, source


def _build_council_tag_counts(calibration_rows):
    counts = Counter()
    for row in calibration_rows:
        metadata = row.get("metadata") or {}
        for tag in metadata.get("reason_tags") or []:
            normalized = str(tag or "").strip().lower()
            if normalized:
                counts[normalized] += 1
    return counts


def _summarize_council_focuses(analysis_payload, calibration_rows):
    human = analysis_payload.get("human_calibration") or {}
    generator_learning_raw = analysis_payload.get("generator_learning") or []
    if isinstance(generator_learning_raw, dict):
        generator_learning = generator_learning_raw.get("rows") or []
    elif isinstance(generator_learning_raw, list):
        generator_learning = generator_learning_raw
    else:
        generator_learning = []
    diagnostics = analysis_payload.get("evaluator_diagnostics") or {}
    learning_snapshot = analysis_payload.get("learning_snapshot") or {}
    tag_counts = _build_council_tag_counts(calibration_rows)

    same_writer_count = int(human.get("same_writer_count") or 0)
    low_confidence_count = int(human.get("low_confidence_count") or 0)
    reviewed = len(calibration_rows)

    if reviewed >= 8:
        confidence_level = "medium"
        confidence_reason = "there is enough human review to name recurring preference classes, but not enough to call the characterization stable"
    elif reviewed >= 3:
        confidence_level = "low"
        confidence_reason = "the signals are real but still thin; treat this as guided suspicion rather than a stable finding"
    else:
        confidence_level = "low"
        confidence_reason = "too little human characterization exists for the council to claim much beyond a provisional direction"

    if same_writer_count > 0:
        strongest = (
            f"Prompt diagnosis is still under-specifying rhetorical situation: {same_writer_count} reviewed packet(s) collapsed into same-writer convergence."
        )
        prompt_diagnosis_assessment = (
            "Genesis and Theron are still solving some prompts with the same default authorial template. "
            "The prompt diagnosis step should become more concrete about audience, relation, and goal, not just lane and family."
        )
    elif low_confidence_count > 0:
        strongest = (
            f"Human characterization still contains {low_confidence_count} tentative or coin-flip judgment(s), which means prompt diagnosis is not yet reliably clarifying what the piece is for."
        )
        prompt_diagnosis_assessment = (
            "The prewrite diagnosis is helping, but it still needs sharper answers about what the piece owes its reader. "
            "When confidence is low, the diagnosis should bias toward clarifying audience and desired effect before style."
        )
    else:
        strongest = "The council does not yet see a dominant prompt-diagnosis failure stronger than the current characterization drift."
        prompt_diagnosis_assessment = (
            "Prompt diagnosis is now instrumented, but the lab still needs enough reviewed packets to learn which misreadings recur. "
            "Treat this as an audit surface that needs evidence, not as a finished advantage."
        )

    evaluator_blind_spots = []
    for tag in ("repetition_as_depth", "rhetorical_situation_blindness", "solemnity_halo", "coherence_over_life"):
        if tag_counts.get(tag):
            evaluator_blind_spots.append(f"{tag.replace('_', ' ')} ({tag_counts[tag]})")
    if evaluator_blind_spots:
        evaluator_education_assessment = (
            "The panel now needs explicit characterization probes, not just score pressure. "
            "Current preference patterns most worth mapping: " + ", ".join(evaluator_blind_spots) + "."
        )
    else:
        evaluator_education_assessment = (
            "Panel characterization should focus on rhetorical situation, false seriousness, and durable worth, "
            "but the blind-spot ledger is still too sparse to prioritize one failure class with confidence."
        )

    one_experiment_to_run_next = (
        "Run a six-packet paired family where the same core prompt is rewritten for sharply different audiences and goals, "
        "then review whether Genesis and Theron actually diverge in form, diction, and obligation."
    )
    if same_writer_count > 0:
        one_experiment_to_run_next = (
            "Run a six-packet personification or letter family with explicit audience/goal contrasts "
            "(for example: public speech vs resignation note vs apology), then inspect whether same-writer convergence falls."
        )

    evaluator_trust_assessment = (
        "Evaluator trust should remain conditional. "
        + ("Human review is still sparse. " if reviewed < 5 else "")
        + (diagnostics.get("warnings") or ["The panel still needs regular comparison against human judgment."])[0]
    )
    protocol_assessment = (
        "The council should now be used to refine two things only: the generator prompt-diagnosis discipline and the panel preference map. "
        "Do not let it become a generic strategy narrator."
    )

    top_pair_failures = []
    for row in generator_learning:
        top_pair_failures.extend(row.get("top_pair_failures") or [])
    pair_failure_counts = Counter(top_pair_failures)
    recommendation = (
        "Use the council as a cartography engine: convert repeated panel-vs-human patterns into prompt-diagnosis refinements and taste-characterization targets."
    )
    if pair_failure_counts.get("voice_collapse"):
        recommendation += " Right now that especially means fighting voice collapse through sharper audience and goal diagnosis."

    stop_doing = (
        "Stop treating evaluator consensus or polished seriousness as evidence that the lab already understands quality. "
        "The council should map exactly where panel preference and human preference diverge."
    )
    if tag_counts.get("repetition_as_depth"):
        stop_doing = (
            "Stop letting repetition, solemn cadence, or prestige polish pass as elaboration. "
            "Those are cues the council should actively demote unless they fit audience and occasion."
        )

    memo = "\n\n".join([
        strongest,
        prompt_diagnosis_assessment,
        evaluator_education_assessment,
        "Next council job: turn recurring panel-vs-human patterns into contrast sets and divergence-ledger entries, not just prose summaries.",
        learning_snapshot.get("still_noisy") or "The evidence is still thin enough that the council should stay concrete and conservative.",
    ])

    prompt_diagnosis_recommendations = [
        {
            "title": "Make audience explicit",
            "scope": "all generators",
            "reason": "Prompt diagnosis should stop at audience only when it can name a real recipient rather than a genre label.",
            "action": "Prefer operator, voter, customer, grieving partner, manager, or public listener over generic labels like reader or audience.",
        },
        {
            "title": "Differentiate form pressure",
            "scope": "all generators",
            "reason": "The generators still risk solving multiple tasks with the same tasteful voice unless the diagnosis distinguishes strict framework from freer composition.",
            "action": "Force the diagnosis to choose among strict framework, creative openness, or hybrid before drafting.",
        },
    ]
    if same_writer_count > 0:
        prompt_diagnosis_recommendations.insert(0, {
            "title": "Push harder on rhetorical situation",
            "scope": "paired families with voice collapse",
            "reason": "Same-writer convergence suggests the diagnosis is too abstract to create meaningful generator divergence.",
            "action": "Add relation and stakes to the prewrite diagnosis for packets that repeatedly collapse into one authorial template.",
        })

    evaluator_education_recommendations = [
        {
            "title": "Probe recurrence conditionally",
            "scope": "Muse, Athena, Apollo",
            "reason": "Repetition should count only when it changes pressure, meaning, or obligation for the intended audience.",
            "action": "Build contrast pairs where the same repeated device is effective in a speech but deadening in a resignation letter or apology.",
        },
        {
            "title": "Attack solemnity halo",
            "scope": "Muse, Athena, Apollo",
            "reason": "Tasteful gravity and prestige polish still risk inflating value judgments.",
            "action": "Use exemplars and anti-exemplars that separate durable human preference from merely serious tone.",
        },
    ]
    if tag_counts.get("rhetorical_situation_blindness"):
        evaluator_education_recommendations.insert(0, {
            "title": "Score against obligation, not style alone",
            "scope": "all evaluators",
            "reason": "Human tags are already identifying rhetorical-situation blindness.",
            "action": "Require the evaluators to ask what the piece owes its reader before rewarding force, repetition, or elevation.",
        })

    contrast_set_candidates = [
        {
            "title": "Speech vs resignation note",
            "focus": "repetition and public-force rhetoric",
            "why_now": "This is the cleanest way to test whether the panel distinguishes public-force cadence from intimate or institutional overreach.",
        },
        {
            "title": "Apology vs campaign message",
            "focus": "solemnity, reassurance, and obligation",
            "why_now": "The evaluators need cases where warmth or force is judged relative to what the reader is owed.",
        },
    ]
    if pair_failure_counts.get("voice_collapse"):
        contrast_set_candidates.insert(0, {
            "title": "Same prompt, three audiences",
            "focus": "voice collapse and diagnosis specificity",
            "why_now": "If Genesis and Theron still sound like one writer, the council should demand audience-separated rewrites of the same core task.",
        })

    return {
        "confidence_level": confidence_level,
        "confidence_reason": confidence_reason,
        "strongest_supported_finding": strongest,
        "recommendation": recommendation,
        "one_experiment_to_run_next": one_experiment_to_run_next,
        "one_thing_to_stop_doing": stop_doing,
        "evaluator_trust_assessment": evaluator_trust_assessment,
        "protocol_assessment": protocol_assessment,
        "prompt_diagnosis_assessment": prompt_diagnosis_assessment,
        "evaluator_education_assessment": evaluator_education_assessment,
        "prompt_diagnosis_recommendations": prompt_diagnosis_recommendations,
        "evaluator_education_recommendations": evaluator_education_recommendations,
        "contrast_set_candidates": contrast_set_candidates,
        "research_memo": memo,
        "summary": recommendation,
    }


# Historical storage key: evaluator_education_target now means a
# panel-characterization probe. See docs/pivot-2026-04-17-characterization.md.
def _default_council_action_status(action_type):
    defaults = {
        "prompt_diagnosis_refinement": "adopted",
        "evaluator_education_target": "active",
        "contrast_set_candidate": "queued",
    }
    return defaults.get(action_type, "queued")


def _build_council_action_summary(rows):
    counts = Counter()
    grouped = {
        "prompt_diagnosis_refinement": [],
        "evaluator_education_target": [],
        "contrast_set_candidate": [],
    }
    for row in rows:
        action_type = row.get("action_type") or "unknown"
        status = row.get("status") or "unknown"
        counts[status] += 1
        grouped.setdefault(action_type, []).append(row)
    return {
        "headline": f"{len(rows)} council characterization actions recorded." if rows else "No council characterization actions yet.",
        "counts": dict(counts),
        "groups": grouped,
        "rows": rows,
    }


def _action_matches_task_scope(action, task):
    lane = str(action.get("lane") or "").strip().lower()
    prompt_family = str(action.get("prompt_family") or "").strip().lower()
    task_lane = str(task.get("lane") or "").strip().lower()
    task_family = str(task.get("family") or "").strip().lower()
    if lane and lane != task_lane:
        return False
    if prompt_family and prompt_family != task_family:
        return False
    return True


def _build_council_runtime_context(rows, task):
    context = {
        "prompt_diagnosis_rules": [],
        "evaluator_curriculum_targets": [],
        "contrast_set_candidates": [],
    }
    for row in rows:
        if not _action_matches_task_scope(row, task):
            continue
        payload = row.get("payload") or {}
        item = {
            "id": row.get("id"),
            "title": row.get("title"),
            "status": row.get("status"),
            "lane": row.get("lane"),
            "prompt_family": row.get("prompt_family"),
            "reason": payload.get("reason"),
            "action": payload.get("action"),
            "focus": payload.get("focus"),
            "why_now": payload.get("why_now"),
        }
        action_type = row.get("action_type")
        status = row.get("status")
        if action_type == "prompt_diagnosis_refinement" and status == "adopted":
            context["prompt_diagnosis_rules"].append(item)
        elif action_type == "evaluator_education_target" and status == "active":
            context["evaluator_curriculum_targets"].append(item)
        elif action_type == "contrast_set_candidate" and status == "queued":
            context["contrast_set_candidates"].append(item)
    return context


async def _get_council_runtime_context(task):
    rows = await db.get_council_actions(limit=100)
    return _build_council_runtime_context(rows, task)


def _build_generator_policy_context(task, council_context=None):
    payload = {
        "prompt_policy_variant": task.get("prompt_policy_variant"),
        "policy_source": task.get("policy_source"),
        "generation_guidance": task.get("generation_guidance"),
        "track": task.get("track"),
        "family": task.get("family"),
        "condition": task.get("condition"),
    }
    prompt_rules = list((council_context or {}).get("prompt_diagnosis_rules") or [])
    if prompt_rules:
        payload["active_prompt_diagnosis_rules"] = prompt_rules
    return payload


def _infer_output_form(task):
    prompt = str(task.get("prompt") or "").strip().lower()
    family = str(task.get("family") or "").strip().lower()
    for keyword, label in (
        ("email", "email"),
        ("memo", "memo"),
        ("letter", "letter"),
        ("speech", "speech"),
        ("plan", "plan"),
        ("outline", "outline"),
        ("obituary", "obituary"),
        ("prayer", "prayer"),
    ):
        if keyword in prompt:
            return label
    if family:
        return family.replace("_", " ")
    return "general response"


def _infer_prompt_compiler_diagnosis(task):
    prompt = str(task.get("prompt") or "").strip()
    prompt_lower = prompt.lower()
    lane = str(task.get("lane") or "creative").strip().lower() or "creative"
    family = str(task.get("family") or "general").strip() or "general"
    composition_mode = "creative_open"
    if lane == "business":
        composition_mode = "strict_framework"
    elif any(keyword in prompt_lower for keyword in ("email", "memo", "plan", "outline", "proposal", "brief")):
        composition_mode = "strict_framework"
    elif any(keyword in prompt_lower for keyword in ("letter", "resignation", "apology")):
        composition_mode = "hybrid"

    intended_audience = "thoughtful reader"
    if any(keyword in prompt_lower for keyword in ("customer", "client", "buyer")):
        intended_audience = "customer"
    elif any(keyword in prompt_lower for keyword in ("manager", "team", "board", "operator")):
        intended_audience = "professional recipient"
    elif any(keyword in prompt_lower for keyword in ("voter", "crowd", "public", "audience", "speech", "campaign")):
        intended_audience = "public audience"
    elif any(keyword in prompt_lower for keyword in ("lover", "girlfriend", "boyfriend", "partner", "friend")):
        intended_audience = "intimate recipient"

    piece_goal = "fulfill the user's request with clear situational fit"
    if any(keyword in prompt_lower for keyword in ("resignation", "quit", "stepping down")):
        piece_goal = "communicate departure clearly and credibly"
    elif any(keyword in prompt_lower for keyword in ("apology", "sorry")):
        piece_goal = "repair trust without evasive language"
    elif any(keyword in prompt_lower for keyword in ("speech", "manifesto", "campaign")):
        piece_goal = "move a public audience toward conviction or action"
    elif any(keyword in prompt_lower for keyword in ("memo", "plan", "brief", "proposal")):
        piece_goal = "deliver an actionable structured artifact"

    stakes = "moderate"
    if any(keyword in prompt_lower for keyword in ("obituary", "apology", "resignation", "eulogy", "grief")):
        stakes = "high"
    relation = "writer to reader"
    if "customer" in intended_audience:
        relation = "business to customer"
    elif intended_audience == "professional recipient":
        relation = "colleague or institution"
    elif intended_audience == "public audience":
        relation = "speaker to public"
    elif intended_audience == "intimate recipient":
        relation = "private writer to intimate recipient"

    ambiguity_level = "medium"
    if task.get("constraints"):
        ambiguity_level = "low"
    elif "thoughtful reader" == intended_audience and family in {"general", "custom_operator"}:
        ambiguity_level = "high"

    return {
        "lane": lane if lane in {"creative", "business", "hybrid"} else "hybrid",
        "prompt_family": family,
        "intended_audience": intended_audience,
        "piece_goal": piece_goal,
        "stakes": stakes,
        "relation": relation,
        "output_form": _infer_output_form(task),
        "composition_mode": composition_mode,
        "ambiguity_level": ambiguity_level,
    }


def _build_prompt_compilation_trace(task, council_context=None):
    council_context = council_context or {}
    diagnosis = _infer_prompt_compiler_diagnosis(task)
    prompt_rules = list(council_context.get("prompt_diagnosis_rules") or [])
    curriculum_targets = list(council_context.get("evaluator_curriculum_targets") or [])

    likely_failure_modes = []
    if diagnosis["composition_mode"] == "strict_framework":
        likely_failure_modes.append("under_structured_output")
    if diagnosis["intended_audience"] in {"intimate recipient", "professional recipient"}:
        likely_failure_modes.append("repetition_as_depth")
    if diagnosis["lane"] == "creative":
        likely_failure_modes.append("prestige_voice_drift")
    if diagnosis["ambiguity_level"] == "high":
        likely_failure_modes.append("audience_under_specification")
    likely_failure_modes = list(dict.fromkeys(likely_failure_modes))

    shared_blind_spots = []
    for target in curriculum_targets:
        title = str(target.get("title") or "").strip().lower().replace(" ", "_")
        if title:
            shared_blind_spots.append(title)

    selected_rule_ids = []
    rule_justifications = []
    for rule in prompt_rules:
        title = str(rule.get("title") or "prompt rule").strip()
        rule_id = f"diagnosis::{title.lower().replace(' ', '_')}"
        selected_rule_ids.append(rule_id)
        rule_justifications.append({
            "rule_id": rule_id,
            "reason": str(rule.get("reason") or rule.get("action") or title).strip(),
        })

    structure_moves = [
        f"Set composition mode to {diagnosis['composition_mode']}",
        f"Target output form: {diagnosis['output_form']}",
    ]
    preservation_moves = []
    if diagnosis["lane"] == "creative":
        preservation_moves.append("Preserve imaginative freedom while grounding audience and obligation.")
    else:
        preservation_moves.append("Preserve usefulness and structural clarity over ornamental flourish.")
    suppression_constraints = [mode.replace("_", " ") for mode in likely_failure_modes]

    compiled_lines = [
        "You are receiving a compiled prompt from Hamlet's Ghost.",
        "",
        "ORIGINAL USER REQUEST:",
        str(task.get("prompt") or "").strip(),
        "",
        "TASK DIAGNOSIS:",
        f"- lane: {diagnosis['lane']}",
        f"- family: {diagnosis['prompt_family']}",
        f"- audience: {diagnosis['intended_audience']}",
        f"- goal: {diagnosis['piece_goal']}",
        f"- relation: {diagnosis['relation']}",
        f"- stakes: {diagnosis['stakes']}",
        f"- output form: {diagnosis['output_form']}",
        f"- composition mode: {diagnosis['composition_mode']}",
    ]
    if task.get("constraints"):
        compiled_lines.extend([
            "",
            "HARD CONSTRAINTS:",
            *[f"- {item}" for item in (task.get("constraints") or []) if str(item).strip()],
        ])
    if prompt_rules:
        compiled_lines.extend(["", "ACTIVE DIAGNOSIS RULES:"])
        compiled_lines.extend(
            f"- {str(rule.get('action') or rule.get('reason') or rule.get('title') or '').strip()}"
            for rule in prompt_rules
            if str(rule.get("action") or rule.get("reason") or rule.get("title") or "").strip()
        )
    if likely_failure_modes:
        compiled_lines.extend(["", "LIKELY FAILURE RISKS TO AVOID:"])
        compiled_lines.extend(f"- {risk.replace('_', ' ')}" for risk in likely_failure_modes)
    compiled_lines.extend([
        "",
        "SUCCESS CRITERIA:",
        "- The output should fit the actual audience and rhetorical situation.",
        f"- It should accomplish this goal: {diagnosis['piece_goal']}.",
        "- It should avoid generic prestige language and misapplied structure.",
    ])

    compiler_mode = str(task.get("prompt_compiler_mode") or "preview_only").strip() or "preview_only"
    return {
        "schema_version": "0.1",
        "status": compiler_mode,
        "source_request": {
            "raw_request": str(task.get("prompt") or "").strip(),
            "hard_constraints": [str(item).strip() for item in (task.get("constraints") or []) if str(item).strip()],
        },
        "diagnosis": diagnosis,
        "risk_assessment": {
            "likely_failure_modes": likely_failure_modes,
            "shared_evaluator_blind_spots": shared_blind_spots,
            "needs_clarification": diagnosis["ambiguity_level"] == "high",
            "clarification_targets": ["audience", "goal"] if diagnosis["ambiguity_level"] == "high" else [],
        },
        "policy_selection": {
            "selected_rule_ids": selected_rule_ids,
            "suppression_constraints": suppression_constraints,
            "preservation_moves": preservation_moves,
            "structure_moves": structure_moves,
            "assumptions": [f"Inferred output form as {diagnosis['output_form']}."],
        },
        "compiled_prompt": {
            "system_goal": diagnosis["piece_goal"],
            "prompt_text": "\n".join(compiled_lines),
            "success_criteria": [
                "Fit the implied audience and stakes.",
                "Stay faithful to the user's request.",
                "Avoid the predicted failure modes unless the task clearly warrants them.",
            ],
        },
        "traceability": {
            "rule_justifications": rule_justifications,
            "evidence_basis": {
                "prompt_family_basis": [diagnosis["prompt_family"]],
                "council_action_ids": [item.get("id") for item in prompt_rules if item.get("id") is not None],
                "reference_pack_ids": [],
            },
        },
    }


def _attach_prompt_compilation(process_trace, source_context, prompt_compilation):
    if not prompt_compilation:
        return process_trace, source_context
    trace = dict(process_trace or {})
    source = dict(source_context or {})
    trace["prompt_compilation"] = {
        "status": prompt_compilation.get("status"),
        "diagnosis": prompt_compilation.get("diagnosis"),
        "selected_rule_ids": ((prompt_compilation.get("policy_selection") or {}).get("selected_rule_ids") or []),
        "compiled_prompt_preview": ((prompt_compilation.get("compiled_prompt") or {}).get("prompt_text") or "")[:800],
    }
    source["prompt_compilation"] = prompt_compilation
    return trace, source


def _task_generation_prompt(task, prompt_compilation=None):
    mode = str(task.get("prompt_compiler_mode") or "").strip().lower()
    if mode == "compiled_candidate":
        compiled_prompt = ((prompt_compilation or {}).get("compiled_prompt") or {}).get("prompt_text")
        if compiled_prompt:
            return compiled_prompt
    return task["prompt"]


def _task_evaluation_prompt(task):
    return task.get("evaluation_prompt") or task["prompt"]


def _compiler_compare_evaluator_signal(raw_member, compiled_member):
    raw_score = raw_member.get("composite") if raw_member else None
    compiled_score = compiled_member.get("composite") if compiled_member else None
    if raw_score is None or compiled_score is None:
        return "unreviewed", None
    margin = float(compiled_score) - float(raw_score)
    if margin > 0:
        return "helped", margin
    if margin < 0:
        return "hurt", margin
    return "mixed", margin


async def _record_compiler_compare_rule_evidence(packet_id, raw_member, compiled_member):
    if not compiled_member:
        return []
    source_context = compiled_member.get("source_context") or {}
    prompt_compilation = source_context.get("prompt_compilation") or {}
    selected_rule_ids = ((prompt_compilation.get("policy_selection") or {}).get("selected_rule_ids") or [])
    if not selected_rule_ids:
        return []

    evaluator_signal, evaluator_margin = _compiler_compare_evaluator_signal(raw_member, compiled_member)
    diagnosis = prompt_compilation.get("diagnosis") or {}
    traceability = prompt_compilation.get("traceability") or {}
    justification_lookup = {
        item.get("rule_id"): item
        for item in (traceability.get("rule_justifications") or [])
        if item.get("rule_id")
    }
    recorded = []
    for rule_id in selected_rule_ids:
        justification = justification_lookup.get(rule_id) or {}
        recorded.append(await db.record_rule_evidence_slice({
            "rule_key": rule_id,
            "title": rule_id.split("::", 1)[-1].replace("_", " ").title(),
            "scope_claim": "family_specific",
            "rule_type": "audience_grounding",
            "rule_text": justification.get("reason") or rule_id,
            "rationale": justification.get("reason") or "Selected by the prompt compiler for this packet.",
            "lane": diagnosis.get("lane"),
            "prompt_family": diagnosis.get("prompt_family"),
            "model_family": source_context.get("generator_provider") or source_context.get("generator_model") or source_context.get("generator_role_id"),
            "panel_version": getattr(agents, "JUDGE_PANEL_VERSION", getattr(db, "JUDGE_PANEL_VERSION", "muse_athena_apollo_v1_independent")),
            "experiment_type": "raw_vs_compiled",
            "packet_id": packet_id,
            "experiment_id": compiled_member.get("id"),
            "compared_experiment_id": raw_member.get("id") if raw_member else None,
            "human_signal": "unreviewed",
            "evaluator_signal": evaluator_signal,
            "evaluator_margin": evaluator_margin,
            "metadata": {
                "compiled_experiment_id": compiled_member.get("id"),
                "raw_experiment_id": raw_member.get("id") if raw_member else None,
                "compiler_status": prompt_compilation.get("status"),
                "source": "compiler_compare",
            },
        }))
    return recorded


def _attach_council_runtime_context(process_trace, source_context, council_context):
    prompt_rules = list((council_context or {}).get("prompt_diagnosis_rules") or [])
    curriculum_targets = list((council_context or {}).get("evaluator_curriculum_targets") or [])
    if not prompt_rules and not curriculum_targets:
        return process_trace, source_context
    trace = dict(process_trace or {})
    source = dict(source_context or {})
    mandate_payload = {}
    if prompt_rules:
        mandate_payload["prompt_diagnosis_rules"] = prompt_rules
    if curriculum_targets:
        mandate_payload["evaluator_curriculum_targets"] = curriculum_targets
    trace["council_mandates"] = mandate_payload
    source["council_mandates"] = mandate_payload
    return trace, source


async def _ensure_contrast_reference_pack(action_payload):
    title = str(action_payload.get("title") or "").strip()
    if not title:
        return dict(action_payload.get("payload") or {})
    existing = await db.list_reference_packs()
    for row in existing:
        if (
            (row.get("source_type") == "council_contrast_candidate")
            and str(row.get("title") or "").strip().lower() == title.lower()
        ):
            enriched = dict(action_payload.get("payload") or {})
            enriched["execution_status"] = "reference_pack_already_exists"
            enriched["reference_pack_id"] = row.get("id")
            return enriched
    payload = dict(action_payload.get("payload") or {})
    reference_pack_id = await db.create_reference_pack({
        "lane": action_payload.get("lane") or "creative",
        "prompt_family": action_payload.get("prompt_family") or "general",
        "title": title,
        "source_type": "council_contrast_candidate",
        "task_definition": {
            "focus": payload.get("focus"),
            "why_now": payload.get("why_now"),
            "council_id": action_payload.get("council_id"),
        },
        "failure_modes": [payload.get("focus")] if payload.get("focus") else [],
        "expected_tradeoffs": [payload.get("reason")] if payload.get("reason") else [],
        "paired_test_matrix": [{"title": title, "focus": payload.get("focus"), "why_now": payload.get("why_now")}],
        "notes": payload.get("why_now") or payload.get("action") or payload.get("reason"),
        "status": "queued",
    })
    enriched = dict(payload)
    enriched["execution_status"] = "reference_pack_created"
    enriched["reference_pack_id"] = reference_pack_id
    return enriched


async def _handle_empty_artifact(exp_id, artifact_content, process_trace, orchestration_trace, *, consecutive_discards=0, failure_reason="empty_artifact"):
    """Shared early exit when the artifact is empty."""
    process_trace["artifact_contract_status"] = "empty_artifact"
    process_trace["generation_failure_reason"] = process_trace.get("generation_failure_reason") or failure_reason
    orchestration_trace["gates"]["athena"] = {
        "eligible": False,
        "decision": "skipped",
        "reason": "empty_artifact_before_scoring",
        "muse_composite": None,
        "constraints_met": None,
    }
    orchestration_trace["skipped_agents"].extend(["muse", "athena"])
    orchestration_trace["final_outcome"] = {
        "status": STATUS_INVALID,
        "promotion_status": PROMOTION_CANDIDATE,
        "keep": False,
        "reason": "generation_failure_empty_artifact",
    }
    process_trace["orchestration"] = orchestration_trace
    await db.update_artifact_process_trace(exp_id, process_trace)
    await db.finalize_experiment(exp_id, status=STATUS_INVALID, promotion_status=PROMOTION_CANDIDATE, parse_failure=True, cost=0.0)
    await db.increment_experiment_counters(keep=False, status=STATUS_INVALID, composite=None, cost=0.0, consecutive_discards=consecutive_discards)
    return {
        "experiment_id": exp_id,
        "status": STATUS_INVALID,
        "promotion_status": PROMOTION_CANDIDATE,
        "keep": False,
        "artifact": artifact_content,
    }


async def _score_and_promote(exp_id, task, artifact_content, process_trace, orchestration_trace, role_provenance, *, council_context=None, consecutive_discards=0, initial_cost=0.0):
    """Score an artifact through MUSE, Athena, and Apollo, then apply promotion logic and update state."""
    total_cost = initial_cost or 0.0
    evaluation_prompt = _task_evaluation_prompt(task)

    muse_result, muse_cost, muse_parse_failure = await agents.run_muse(
        artifact=artifact_content,
        prompt=evaluation_prompt,
        constraints=task.get("constraints"),
        lane=task.get("lane", "creative"),
        curriculum_targets=(council_context or {}).get("evaluator_curriculum_targets"),
    )
    total_cost += muse_cost or 0.0

    has_constraints = bool(task.get("constraints"))
    stored_muse_result = dict(muse_result)
    if not has_constraints and stored_muse_result.get("constraints_met") is None:
        stored_muse_result["constraints_met"] = True
    await db.insert_score(exp_id, "muse", stored_muse_result, cost=muse_cost, parse_failure=muse_parse_failure)

    verifier_state = _extract_verifier_constraint_state(process_trace)
    run_athena, athena_gate_reason = _should_run_athena(muse_result, muse_parse_failure, experiment_id=exp_id)
    orchestration_trace["gates"]["athena"] = {
        "eligible": run_athena,
        "decision": "run" if run_athena else "skipped",
        "reason": athena_gate_reason,
        "muse_composite": muse_result.get("composite") if muse_result else None,
        "constraints_met": muse_result.get("constraints_met") if muse_result else None,
    }

    holdout_result = None
    holdout_parse_failure = True
    holdout_cost = 0.0
    external_apollo_result = None
    external_apollo_parse_failure = True
    external_apollo_cost = 0.0
    if run_athena:
        try:
            holdout_result, holdout_cost, holdout_parse_failure = await agents.run_athena(
                artifact=artifact_content,
                prompt=evaluation_prompt,
                constraints=task.get("constraints"),
                lane=task.get("lane", "creative"),
                curriculum_targets=(council_context or {}).get("evaluator_curriculum_targets"),
            )
            total_cost += holdout_cost or 0.0
            if not holdout_parse_failure:
                await db.insert_score(exp_id, "athena", holdout_result, cost=holdout_cost, parse_failure=False)
                orchestration_trace["executed_agents"].append("athena")
            else:
                orchestration_trace["gates"]["athena"]["decision"] = "parse_failure"
                orchestration_trace["gates"]["athena"]["reason"] = "athena_parse_failure"
        except Exception as exc:
            orchestration_trace["gates"]["athena"]["decision"] = "error"
            orchestration_trace["gates"]["athena"]["reason"] = str(exc)
    else:
        orchestration_trace["skipped_agents"].append("athena")

    if getattr(agents, "APOLLO_SHADOW_ENABLED", False) and run_athena:
        try:
            external_apollo_result, external_apollo_cost, external_apollo_parse_failure = await agents.run_external_hermes(
                artifact=artifact_content,
                prompt=evaluation_prompt,
                constraints=task.get("constraints"),
                lane=task.get("lane", "creative"),
                curriculum_targets=(council_context or {}).get("evaluator_curriculum_targets"),
            )
            total_cost += external_apollo_cost or 0.0
            if not external_apollo_parse_failure:
                await db.insert_score(exp_id, "apollo", external_apollo_result, cost=external_apollo_cost, parse_failure=False)
            process_trace.setdefault("shadow_evaluators", {})
            process_trace["shadow_evaluators"]["apollo"] = {
                "enabled": True,
                "backend": role_provenance["apollo"]["backend"],
                "model": role_provenance["apollo"]["model"],
                "independent": bool(getattr(agents, "APOLLO_INDEPENDENT", False)),
                "panel_version": getattr(agents, "JUDGE_PANEL_VERSION", getattr(db, "JUDGE_PANEL_VERSION", "muse_athena_apollo_v1_independent")),
                "parse_failure": bool(external_apollo_parse_failure),
                "composite": external_apollo_result.get("composite") if external_apollo_result else None,
                "constraints_met": external_apollo_result.get("constraints_met") if external_apollo_result else None,
            }
        except Exception as exc:
            process_trace.setdefault("shadow_evaluators", {})
            process_trace["shadow_evaluators"]["apollo"] = {
                "enabled": True,
                "backend": role_provenance["apollo"]["backend"],
                "model": role_provenance["apollo"]["model"],
                "independent": bool(getattr(agents, "APOLLO_INDEPENDENT", False)),
                "panel_version": getattr(agents, "JUDGE_PANEL_VERSION", getattr(db, "JUDGE_PANEL_VERSION", "muse_athena_apollo_v1_independent")),
                "error": str(exc),
            }

    # --- Promotion decision ---
    composite = muse_result.get("composite")
    constraints_met = muse_result.get("constraints_met")
    has_effective_constraints = has_constraints or verifier_state["has_effective_constraints"]
    # For promotion decisions, treat unknown constraints on constrained tasks as non-passing.
    # The raw constraints_met (which may be None) is preserved in the score record for analytics.
    effective_constraints_passed = constraints_met is not False if not has_effective_constraints else constraints_met is True

    critic_composite = holdout_result.get("composite") if holdout_result and not holdout_parse_failure else None
    divergence = abs(composite - critic_composite) if composite is not None and critic_composite is not None else None

    if muse_parse_failure:
        keep = False
        status = STATUS_INVALID
        promotion = PROMOTION_CANDIDATE
    elif has_effective_constraints and not effective_constraints_passed:
        keep = False
        status = STATUS_CONSTRAINT_FAIL
        promotion = PROMOTION_CANDIDATE
    elif composite is not None and composite >= PROMOTE_COMPOSITE_THRESHOLD and effective_constraints_passed:
        if divergence is not None and divergence < MAX_DIVERGENCE_FOR_PROMOTION:
            keep = True
            status = STATUS_PROMOTED
            promotion = PROMOTION_SHADOW
        else:
            keep = True
            status = STATUS_KEPT
            promotion = PROMOTION_CANDIDATE
    elif composite is not None and composite >= KEEP_COMPOSITE_THRESHOLD and effective_constraints_passed:
        keep = True
        status = STATUS_KEPT
        promotion = PROMOTION_CANDIDATE
    else:
        keep = False
        status = STATUS_DISCARD
        promotion = PROMOTION_CANDIDATE

    # --- Finalize traces and persist ---
    orchestration_trace["final_outcome"] = {"status": status, "promotion_status": promotion, "keep": keep}
    if external_apollo_result and external_apollo_result.get("composite") is not None and composite is not None:
        process_trace.setdefault("shadow_evaluators", {})
        process_trace["shadow_evaluators"]["apollo"]["divergence_from_muse"] = abs(composite - external_apollo_result.get("composite"))
        if holdout_result and holdout_result.get("composite") is not None:
            process_trace["shadow_evaluators"]["apollo"]["divergence_from_local_athena"] = abs(holdout_result.get("composite") - external_apollo_result.get("composite"))
    process_trace["orchestration"] = orchestration_trace
    await db.update_artifact_process_trace(exp_id, process_trace)
    await db.finalize_experiment(exp_id, status=status, promotion_status=promotion, parse_failure=muse_parse_failure, cost=total_cost)
    await db.increment_experiment_counters(keep=keep, status=status, composite=composite, cost=total_cost, consecutive_discards=consecutive_discards)
    return {
        "experiment_id": exp_id,
        "status": status,
        "promotion_status": promotion,
        "keep": keep,
        "artifact": artifact_content,
    }


async def _score_existing_artifact(exp_id, task, artifact_content, process_trace, source_context, *, council_context=None, consecutive_discards=0, initial_cost=0.0):
    orchestration_trace = _build_orchestration_trace(task)
    role_provenance = _build_role_provenance(task)
    prompt_compilation = _build_prompt_compilation_trace(task, council_context=council_context)
    process_trace = _init_process_trace(process_trace, role_provenance, orchestration_trace)
    normalized_source_context = _enrich_source_context(source_context, task, role_provenance)
    process_trace, normalized_source_context = _attach_prompt_compilation(
        process_trace,
        normalized_source_context,
        prompt_compilation,
    )
    process_trace, normalized_source_context = _attach_council_runtime_context(
        process_trace,
        normalized_source_context,
        council_context,
    )
    await db.insert_artifact(exp_id, artifact_content, process_trace=process_trace, source_context=normalized_source_context)

    if not artifact_content.strip():
        return await _handle_empty_artifact(
            exp_id, artifact_content, process_trace, orchestration_trace,
            consecutive_discards=consecutive_discards,
            failure_reason="empty_artifact_from_external_submission",
        )

    return await _score_and_promote(
        exp_id, task, artifact_content, process_trace, orchestration_trace, role_provenance,
        council_context=council_context,
        consecutive_discards=consecutive_discards, initial_cost=initial_cost,
    )


async def _execute_experiment(task, iteration, consecutive_discards=0):
    _ = iteration
    task = await _resolve_policy_control(task)
    exp_id = await db.create_experiment(task)
    await db.update_state(
        current_lane=task.get("lane"),
        current_track=task.get("track"),
        current_experiment_id=exp_id,
    )

    orchestration_trace = _build_orchestration_trace(task)
    role_provenance = _build_role_provenance(task)
    generator_feedback = await _get_generator_feedback_bundle(task, "genesis")
    council_context = await _get_council_runtime_context(task)
    prompt_compilation = _build_prompt_compilation_trace(task, council_context=council_context)
    policy_context = _build_generator_policy_context(task, council_context=council_context)
    generation_prompt = _task_generation_prompt(task, prompt_compilation=prompt_compilation)
    total_cost = 0.0
    try:
        genesis_result, genesis_cost, _genesis_parse_failure = await agents.run_genesis(
            prompt=generation_prompt,
            constraints=task.get("constraints"),
            prior_feedback=generator_feedback.get("prior_feedback"),
            lane=task.get("lane", "creative"),
            policy_context=policy_context,
        )
        total_cost += genesis_cost or 0.0
        artifact_content = genesis_result.get("artifact") or ""
        process_trace = _init_process_trace(genesis_result.get("process_trace"), role_provenance, orchestration_trace)
        source_context = _enrich_source_context({"role_routing": role_provenance}, task, role_provenance)
        process_trace, source_context = _attach_generator_feedback(
            process_trace,
            source_context,
            role_id="genesis",
            feedback_bundle=generator_feedback,
        )
        process_trace, source_context = _attach_prompt_compilation(
            process_trace,
            source_context,
            prompt_compilation,
        )
        process_trace, source_context = _attach_council_runtime_context(
            process_trace,
            source_context,
            council_context,
        )
        await db.insert_artifact(exp_id, artifact_content, process_trace=process_trace, source_context=source_context)

        if _should_run_openclaw_shadow(task):
            try:
                openclaw_result, openclaw_cost, openclaw_parse_failure = await agents.run_openclaw_genesis(
                    prompt=generation_prompt,
                    constraints=task.get("constraints"),
                    prior_feedback=generator_feedback.get("prior_feedback"),
                    lane=task.get("lane", "creative"),
                    policy_context=policy_context,
                )
                total_cost += openclaw_cost or 0.0
                process_trace.setdefault("shadow_generators", {})
                process_trace["shadow_generators"]["genesis_openclaw"] = {
                    "enabled": True,
                    "backend": role_provenance["genesis_openclaw"]["backend"],
                    "model": role_provenance["genesis_openclaw"]["model"],
                    "parse_failure": bool(openclaw_parse_failure),
                    "artifact_contract_status": (openclaw_result.get("process_trace") or {}).get("artifact_contract_status"),
                    "artifact": openclaw_result.get("artifact"),
                    "process_trace": openclaw_result.get("process_trace") or {},
                }
                shadow_context = _enrich_source_context(
                    {"role_routing": role_provenance, "shadow_generators": process_trace["shadow_generators"]},
                    task, role_provenance,
                )
                await db.update_artifact_source_context(exp_id, shadow_context)
            except Exception as exc:
                process_trace.setdefault("shadow_generators", {})
                process_trace["shadow_generators"]["genesis_openclaw"] = {
                    "enabled": True,
                    "backend": role_provenance["genesis_openclaw"]["backend"],
                    "model": role_provenance["genesis_openclaw"]["model"],
                    "error": str(exc),
                }
                shadow_context = _enrich_source_context(
                    {"role_routing": role_provenance, "shadow_generators": process_trace["shadow_generators"]},
                    task, role_provenance,
                )
                await db.update_artifact_source_context(exp_id, shadow_context)
        elif getattr(agents, "GENESIS_OPENCLAW_SHADOW_ENABLED", False):
            process_trace.setdefault("shadow_generators", {})
            process_trace["shadow_generators"]["genesis_openclaw"] = {
                "enabled": True,
                "skipped": True,
                "reason": "family_not_enabled",
            }
            shadow_context = _enrich_source_context(
                {"role_routing": role_provenance, "shadow_generators": process_trace["shadow_generators"]},
                task, role_provenance,
            )
            await db.update_artifact_source_context(exp_id, shadow_context)

        if not artifact_content.strip():
            return await _handle_empty_artifact(
                exp_id, artifact_content, process_trace, orchestration_trace,
                consecutive_discards=consecutive_discards,
                failure_reason="empty_artifact_from_genesis",
            )

        # Record Apollo-skipped status when Athena doesn't run but Apollo shadow is on
        if getattr(agents, "APOLLO_SHADOW_ENABLED", False):
            process_trace.setdefault("shadow_evaluators", {})

        return await _score_and_promote(
            exp_id, task, artifact_content, process_trace, orchestration_trace, role_provenance,
            council_context=council_context,
            consecutive_discards=consecutive_discards, initial_cost=total_cost,
        )
    except Exception:
        traceback_text = tb.format_exc()
        await db.finalize_experiment(exp_id, status=STATUS_ERROR, promotion_status=PROMOTION_CANDIDATE, parse_failure=True, cost=total_cost, error_traceback=traceback_text)
        raise


async def run_lab_loop(n_experiments=40):
    await db.update_state(running=1)
    try:
        schedule = experiments.build_experiment_schedule(
            n_experiments=n_experiments,
            approved_policy_controls=await db.get_approved_policy_controls(),
        )
        for task in schedule:
            if _stop_event.is_set():
                break
            state = await db.get_state()
            await _execute_experiment(
                task,
                iteration=(state["total_experiments"] or 0) + 1,
                consecutive_discards=state.get("consecutive_discards") or 0,
            )
    finally:
        await db.update_state(running=0, current_lane=None, current_track=None, current_experiment_id=None)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init_db()
    await seed_hypotheses()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/state")
async def get_state():
    return JSONResponse(await db.build_state_payload())


@app.get("/api/history")
async def get_history():
    rows = await db.get_recent_experiments(epoch=db.CURRENT_EXPERIMENT_EPOCH)
    return JSONResponse([_sanitize_experiment_record(row) for row in rows])


@app.get("/api/timeline")
async def get_timeline():
    return JSONResponse(await db.get_timeline(epoch=db.CURRENT_EXPERIMENT_EPOCH))


@app.get("/api/analysis")
async def get_analysis():
    return JSONResponse(await db.get_analysis_payload())


@app.get("/api/review/disagreements")
async def get_disagreement_queue():
    rows = await db.list_disagreement_packets(limit=12, unresolved_only=True, include_consensus=True)
    all_assembling_rows = await db.list_assembling_packets(limit=12)
    assembling_rows = [row for row in all_assembling_rows if row.get("assembly_health") == "active"]
    stalled_rows = [row for row in all_assembling_rows if row.get("assembly_health") == "stalled"]
    graveyard_rows = await db.list_packet_resolutions(limit=8)
    return JSONResponse({
        "headline": f"{len(rows)} paired packets need human judgment." if rows else "No paired packets ready for judgment yet.",
        "rows": rows,
        "assembling_headline": f"{len(assembling_rows)} paired packets still assembling." if assembling_rows else "",
        "assembling_rows": assembling_rows,
        "stalled_headline": f"{len(stalled_rows)} paired packets are stalled and need repair." if stalled_rows else "",
        "stalled_rows": stalled_rows,
        "graveyard_headline": f"{len(graveyard_rows)} packet resolution(s) are in the graveyard." if graveyard_rows else "",
        "graveyard_rows": graveyard_rows,
    })


@app.get("/api/review/disagreements/{packet_id}")
async def get_disagreement_packet(packet_id: str):
    payload = await db.get_disagreement_packet(packet_id)
    if not payload:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(payload)


@app.get("/api/review/reason-tags")
async def get_review_reason_tags():
    return JSONResponse(_load_review_reason_tag_catalog())


@app.post("/api/review/disagreements/{packet_id}/decision")
async def save_disagreement_decision(packet_id: str, payload: DisagreementDecisionPayload = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    payload = _payload_dict(payload)
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    preferred_experiment_id = payload.get("preferred_experiment_id")
    rationale = (payload.get("rationale") or "").strip()
    metadata = payload.get("metadata") or {}
    verdict = _review_verdict(metadata)
    if verdict == "preferred" and preferred_experiment_id is None:
        return JSONResponse({"error": "preferred_experiment_id is required"}, status_code=400)
    if not rationale:
        return JSONResponse({"error": "rationale is required"}, status_code=400)
    packet = await db.get_disagreement_packet(packet_id)
    if not packet:
        return JSONResponse({"error": "packet not found"}, status_code=404)
    valid_ids = {member.get("id") for member in packet.get("members", [])}
    if preferred_experiment_id is not None and preferred_experiment_id not in valid_ids:
        return JSONResponse({"error": "preferred_experiment_id must belong to the packet"}, status_code=400)
    if verdict != "preferred":
        preferred_experiment_id = None
    review = await db.save_comparison_review(
        packet_id,
        preferred_experiment_id=preferred_experiment_id,
        rationale=rationale,
        reviewer=payload.get("reviewer", "human_operator"),
        review_channel=payload.get("review_channel"),
        outbound_message_id=payload.get("outbound_message_id"),
        inbound_message_id=payload.get("inbound_message_id"),
        metadata=metadata,
    )
    return JSONResponse({"status": "saved", "review": review})


@app.post("/api/review/disagreements/{packet_id}/resolution")
async def save_packet_resolution(packet_id: str, payload: PacketResolutionPayload = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    payload = _payload_dict(payload)
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    packet = await db.get_disagreement_packet(packet_id)
    if not packet:
        return JSONResponse({"error": "packet not found"}, status_code=404)
    resolution = str(payload.get("resolution") or "").strip().lower()
    rationale = (payload.get("rationale") or "").strip()
    if not rationale:
        return JSONResponse({"error": "rationale is required"}, status_code=400)
    try:
        saved = await db.save_packet_resolution(
            packet_id,
            resolution=resolution,
            rationale=rationale,
            reviewer=payload.get("reviewer", "human_operator"),
            metadata=payload.get("metadata") or {},
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"status": "saved", "packet_resolution": saved})


@app.get("/api/providers")
async def get_provider_status():
    return JSONResponse({
        "theron": await agents.get_theron_provider_status(),
        "apollo": await agents.get_apollo_provider_status(),
        "cast": {
            "genesis": {"model": agents.MODEL, "backend": agents.GENESIS_BACKEND},
            "theron": {"model": agents.THERON_MODEL, "backend": agents.THERON_BACKEND or "openclaw_local"},
            "muse": {"model": agents.MUSE_MODEL, "backend": agents.MUSE_BACKEND},
            "athena": {"model": agents.ATHENA_MODEL, "backend": agents.ATHENA_BACKEND},
            "apollo": {"model": agents.APOLLO_MODEL, "backend": agents.APOLLO_BACKEND or agents.ATHENA_BACKEND},
        },
    })


@app.get("/api/reference-packs")
async def get_reference_packs():
    return JSONResponse(await db.list_reference_packs())


@app.post("/api/reference-packs")
async def create_reference_pack(payload: dict = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    ref_id = await db.create_reference_pack(payload)
    return JSONResponse({"status": "saved", "id": ref_id})


@app.get("/api/policy-ledger")
async def get_policy_ledger():
    return JSONResponse(await db.get_policy_registry())


@app.post("/api/policy-ledger")
async def update_policy_ledger(payload: dict = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    await db.upsert_policy_registry_entry(payload)
    return JSONResponse({"status": "saved"})


@app.post("/api/start")
async def start_lab(payload: StartLabPayload = Body(default=StartLabPayload()), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    global _runner_task, _stop_event
    payload = _payload_dict(payload)
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    async with _runner_transition_lock:
        if _runner_task and not _runner_task.done():
            return JSONResponse({"status": "already_running"})
        _stop_event = asyncio.Event()
        n_experiments = int(payload.get("n_experiments", 40))
        _runner_task = asyncio.create_task(run_lab_loop(n_experiments=n_experiments))
        return JSONResponse({"status": "started", "n_experiments": n_experiments})


@app.post("/api/stop")
async def stop_lab(x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    global _runner_task
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    async with _runner_transition_lock:
        _stop_event.set()
        if _runner_task and not _runner_task.done():
            try:
                await _runner_task
            except asyncio.CancelledError:
                pass
        await db.update_state(running=0, current_lane=None, current_track=None, current_experiment_id=None)
        return JSONResponse({"status": "stopped"})


@app.post("/api/experiment/custom")
async def run_custom_experiment(payload: CustomExperimentPayload = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    payload = _payload_dict(payload)
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    task = {
        "id": "custom",
        "lane": payload.get("lane", "creative"),
        "prompt": payload["prompt"],
        "creativity_type": payload.get("creativity_type", "custom"),
        "constraints": payload.get("constraints") or [],
        "track": payload.get("track", "custom"),
        "family": payload.get("family", "custom_operator"),
        "hypothesis": payload.get("hypothesis"),
        "condition": payload.get("condition", "critique_on"),
        "packet_id": payload.get("packet_id"),
        "packet_role_id": payload.get("packet_role_id", "genesis"),
        "packet_primary": payload.get("packet_primary", True),
    }
    state = await db.get_state()
    result = await _execute_experiment(task, iteration=(state["total_experiments"] or 0) + 1, consecutive_discards=state.get("consecutive_discards") or 0)
    return JSONResponse(result)


@app.post("/api/experiment/compiler-compare")
async def run_compiler_compare(payload: CompilerComparePayload = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    payload = _payload_dict(payload)
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error

    packet_id = payload.get("packet_id") or _new_packet_id()
    base_task = {
        "id": payload.get("id", "compiler_compare"),
        "lane": payload.get("lane", "creative"),
        "prompt": payload["prompt"],
        "creativity_type": payload.get("creativity_type", "custom"),
        "constraints": payload.get("constraints") or [],
        "track": payload.get("track", "compiler_compare"),
        "family": payload.get("family", "custom_operator"),
        "hypothesis": payload.get("hypothesis"),
        "condition": payload.get("condition", "critique_on"),
        "generator_role_id": payload.get("local_role_id", "genesis"),
        "evaluation_prompt": payload["prompt"],
    }

    state = await db.get_state()
    next_iteration = (state["total_experiments"] or 0) + 1
    consecutive_discards = state.get("consecutive_discards") or 0
    results = []

    raw_task = await _resolve_policy_control(_build_packet_task(
        {
            **base_task,
            "id": "compiler_compare_raw",
            "track": payload.get("track", "compiler_compare"),
            "generation_protocol": "prompt_compiler_raw",
            "prompt_compiler_mode": "raw_baseline",
        },
        packet_id=packet_id,
        packet_role_id="raw_prompt",
        packet_primary=True,
    ))
    raw_result = await _execute_experiment(
        raw_task,
        iteration=next_iteration,
        consecutive_discards=consecutive_discards,
    )
    raw_result["packet_id"] = packet_id
    results.append(raw_result)

    updated_state = await db.get_state()
    next_iteration = (updated_state["total_experiments"] or 0) + 1
    consecutive_discards = updated_state.get("consecutive_discards") or 0

    compiled_task = await _resolve_policy_control(_build_packet_task(
        {
            **base_task,
            "id": "compiler_compare_compiled",
            "track": payload.get("track", "compiler_compare"),
            "generation_protocol": "prompt_compiler_compiled",
            "prompt_compiler_mode": "compiled_candidate",
        },
        packet_id=packet_id,
        packet_role_id="compiled_prompt",
        packet_primary=False,
    ))
    compiled_result = await _execute_experiment(
        compiled_task,
        iteration=next_iteration,
        consecutive_discards=consecutive_discards,
    )
    compiled_result["packet_id"] = packet_id
    results.append(compiled_result)

    summaries = await db.get_experiment_summaries([result["experiment_id"] for result in results])
    summary_map = {row.get("id"): row for row in summaries}
    packet_members = []
    for result in results:
        experiment = summary_map.get(result["experiment_id"])
        if experiment:
            packet_members.append({
                "experiment_id": experiment.get("id"),
                "role_id": experiment.get("packet_role_id") or ((experiment.get("source_context") or {}).get("generator_role_id")) or "genesis",
                "provider": ((experiment.get("source_context") or {}).get("generator_provider")) or payload.get("local_role_id", "genesis"),
                "status": experiment.get("status"),
                "promotion_status": experiment.get("promotion_status"),
                "composite": experiment.get("composite"),
            })

    raw_member = next((row for row in summary_map.values() if row.get("packet_role_id") == "raw_prompt"), None)
    compiled_member = next((row for row in summary_map.values() if row.get("packet_role_id") == "compiled_prompt"), None)
    rule_evidence = await _record_compiler_compare_rule_evidence(packet_id, raw_member, compiled_member)

    return JSONResponse({
        "status": "completed",
        "packet_id": packet_id,
        "results": results,
        "members": packet_members,
        "rule_evidence": rule_evidence,
    })


@app.post("/api/experiment/external")
async def run_external_experiment(payload: ExternalExperimentPayload = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    payload = _payload_dict(payload)
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    artifact = (payload.get("artifact") or "").strip()
    if not payload.get("prompt"):
        return JSONResponse({"error": "prompt is required"}, status_code=400)
    if not artifact:
        return JSONResponse({"error": "artifact is required"}, status_code=400)

    task = {
        "id": "external",
        "lane": payload.get("lane", "creative"),
        "prompt": payload["prompt"],
        "creativity_type": payload.get("creativity_type", "custom"),
        "constraints": payload.get("constraints") or [],
        "track": payload.get("track", "external"),
        "family": payload.get("family", "external_operator"),
        "hypothesis": payload.get("hypothesis"),
        "condition": payload.get("condition", "critique_on"),
        "generation_protocol": payload.get("generation_protocol", "external_manual"),
        "packet_id": payload.get("packet_id"),
        "packet_role_id": payload.get("packet_role_id") or payload.get("generator_role_id", "theron"),
        "packet_primary": payload.get("packet_primary", False),
    }
    task = await _resolve_policy_control(task)
    exp_id = await db.create_experiment(task)
    await db.update_state(
        current_lane=task.get("lane"),
        current_track=task.get("track"),
        current_experiment_id=exp_id,
    )
    state = await db.get_state()
    result = await _score_existing_artifact(
        exp_id,
        task,
        artifact,
        payload.get("process_trace") or {
            "protocol": "external_manual",
            "artifact_contract_status": "ok",
            "submission_mode": "manual_bridge",
        },
        payload.get("source_context") or {
            "external_submission": True,
            "generator_provider": payload.get("generator_provider", "theron_manual"),
            "generator_role_id": payload.get("generator_role_id", "theron"),
            "submission_mode": "manual_bridge",
            "packet_id": task.get("packet_id"),
            "packet_role_id": task.get("packet_role_id"),
            "packet_primary": bool(task.get("packet_primary", False)),
        },
        consecutive_discards=state.get("consecutive_discards") or 0,
    )
    return JSONResponse(result)


@app.post("/api/experiment/paired")
async def run_paired_experiment(payload: PairedExperimentPayload = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    payload = _payload_dict(payload)
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    if not payload.get("prompt"):
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    packet_id = payload.get("packet_id") or _new_packet_id()
    base_task = {
        "id": payload.get("id", "paired"),
        "lane": payload.get("lane", "creative"),
        "prompt": payload["prompt"],
        "creativity_type": payload.get("creativity_type", "custom"),
        "constraints": payload.get("constraints") or [],
        "track": payload.get("track", "paired"),
        "family": payload.get("family", "paired_operator"),
        "hypothesis": payload.get("hypothesis"),
        "condition": payload.get("condition", "critique_on"),
        "generation_protocol": payload.get("generation_protocol", "paired_native"),
    }

    results = []
    state = await db.get_state()
    next_iteration = (state["total_experiments"] or 0) + 1
    consecutive_discards = state.get("consecutive_discards") or 0

    if payload.get("run_local", True):
        local_task = _build_packet_task(
            base_task,
            packet_id=packet_id,
            packet_role_id=payload.get("local_role_id", "genesis"),
            packet_primary=True,
        )
        local_result = await _execute_experiment(local_task, iteration=next_iteration, consecutive_discards=consecutive_discards)
        local_result["packet_id"] = packet_id
        results.append(local_result)
        updated_state = await db.get_state()
        next_iteration = (updated_state["total_experiments"] or 0) + 1
        consecutive_discards = updated_state.get("consecutive_discards") or 0

    if payload.get("generate_external", False):
        if not getattr(agents, "THERON_GENERATION_ENABLED", False):
            return JSONResponse({"error": "Theron generation is not configured. Set THERON_BACKEND/THERON_MODEL first."}, status_code=503)

        theron_task = await _resolve_policy_control(_build_packet_task(
            {
                **base_task,
                "id": payload.get("external_id", "theron"),
                "track": payload.get("external_track", "paired_external"),
                "generation_protocol": payload.get("external_generation_protocol", "theron_paired_native"),
            },
            packet_id=packet_id,
            packet_role_id=payload.get("external_role_id", "theron"),
            packet_primary=False,
        ))
        exp_id = await db.create_experiment(theron_task, iteration=next_iteration)
        await db.update_state(
            current_lane=theron_task.get("lane"),
            current_track=theron_task.get("track"),
            current_experiment_id=exp_id,
        )
        theron_feedback = await _get_generator_feedback_bundle(theron_task, payload.get("external_role_id", "theron"))
        theron_council_context = await _get_council_runtime_context(theron_task)
        theron_prompt_compilation = _build_prompt_compilation_trace(theron_task, council_context=theron_council_context)
        theron_generation_prompt = _task_generation_prompt(theron_task, prompt_compilation=theron_prompt_compilation)
        theron_result, theron_cost, theron_parse_failure = await agents.run_theron_genesis(
            prompt=theron_generation_prompt,
            constraints=theron_task.get("constraints"),
            prior_feedback=theron_feedback.get("prior_feedback"),
            lane=theron_task.get("lane", "creative"),
            policy_context=_build_generator_policy_context(theron_task, council_context=theron_council_context),
        )
        theron_artifact = (theron_result.get("artifact") or "").strip()
        theron_trace = theron_result.get("process_trace") or {
            "protocol": "theron_paired_native",
            "artifact_contract_status": "empty_artifact" if not theron_artifact else "ok",
        }
        theron_trace.setdefault("protocol", "theron_paired_native")
        theron_trace.setdefault("artifact_contract_status", "empty_artifact" if not theron_artifact else "ok")
        theron_trace.setdefault("role_routing", _build_role_provenance(theron_task))
        theron_trace, theron_source_context = _attach_generator_feedback(
            theron_trace,
            {
                "external_submission": True,
                "generator_provider": payload.get("external_provider", agents.describe_role_runtime("theron").get("backend")),
                "generator_role_id": payload.get("external_role_id", "theron"),
                "submission_mode": "paired_native_generated",
            },
            role_id=payload.get("external_role_id", "theron"),
            feedback_bundle=theron_feedback,
        )
        theron_trace, theron_source_context = _attach_prompt_compilation(
            theron_trace,
            theron_source_context,
            theron_prompt_compilation,
        )
        theron_trace, theron_source_context = _attach_council_runtime_context(
            theron_trace,
            theron_source_context,
            theron_council_context,
        )

        result = await _score_existing_artifact(
            exp_id,
            theron_task,
            theron_artifact,
            theron_trace,
            theron_source_context,
            council_context=theron_council_context,
            consecutive_discards=consecutive_discards,
            initial_cost=theron_cost,
        )
        result["packet_id"] = packet_id
        result["generation_parse_failure"] = bool(theron_parse_failure)
        result["generation_cost"] = theron_cost
        results.append(result)
        updated_state = await db.get_state()
        next_iteration = (updated_state["total_experiments"] or 0) + 1
        consecutive_discards = updated_state.get("consecutive_discards") or 0

    for submission in payload.get("external_artifacts") or []:
        artifact = (submission.get("artifact") or "").strip()
        if not artifact:
            continue
        external_task = await _resolve_policy_control(_build_packet_task(
            {
                **base_task,
                "id": submission.get("id", "external"),
                "track": submission.get("track", "external"),
                "generation_protocol": submission.get("generation_protocol", "paired_external"),
            },
            packet_id=packet_id,
            packet_role_id=submission.get("generator_role_id", "theron"),
            packet_primary=False,
        ))
        exp_id = await db.create_experiment(external_task, iteration=next_iteration)
        await db.update_state(
            current_lane=external_task.get("lane"),
            current_track=external_task.get("track"),
            current_experiment_id=exp_id,
        )
        external_council_context = await _get_council_runtime_context(external_task)
        result = await _score_existing_artifact(
            exp_id,
            external_task,
            artifact,
            submission.get("process_trace") or {
                "protocol": "paired_external_manual",
                "artifact_contract_status": "ok",
                "submission_mode": "paired_native",
            },
            submission.get("source_context") or {
                "external_submission": True,
                "generator_provider": submission.get("generator_provider", "theron_manual"),
                "generator_role_id": submission.get("generator_role_id", "theron"),
                "submission_mode": "paired_native",
            },
            council_context=external_council_context,
            consecutive_discards=consecutive_discards,
        )
        result["packet_id"] = packet_id
        results.append(result)
        updated_state = await db.get_state()
        next_iteration = (updated_state["total_experiments"] or 0) + 1
        consecutive_discards = updated_state.get("consecutive_discards") or 0

    packet_members = []
    summaries = await db.get_experiment_summaries([result["experiment_id"] for result in results])
    summary_map = {row.get("id"): row for row in summaries}
    for result in results:
        experiment = summary_map.get(result["experiment_id"])
        if experiment:
            packet_members.append({
                "experiment_id": experiment.get("id"),
                "role_id": experiment.get("packet_role_id") or ((experiment.get("source_context") or {}).get("generator_role_id")) or "genesis",
                "provider": ((experiment.get("source_context") or {}).get("generator_provider")),
                "status": experiment.get("status"),
                "promotion_status": experiment.get("promotion_status"),
                "composite": experiment.get("composite"),
            })

    return JSONResponse({
        "status": "completed",
        "packet_id": packet_id,
        "results": results,
        "members": packet_members,
    })


@app.get("/api/artifact/{experiment_id}")
async def get_artifact(experiment_id: int, x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    exp = await db.get_experiment_by_id(experiment_id)
    if not exp:
        return JSONResponse({"error": "not found"}, status_code=404)
    exp = _sanitize_experiment_record(exp)
    exp["holdout_scores"] = await db.get_holdout_scores(experiment_id)
    return JSONResponse(exp)


@app.post("/api/council/trigger")
async def trigger_council(x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    analysis_payload = await db.get_analysis_payload()
    calibration_rows = await db.get_recent_calibration_reviews(limit=50, epoch=db.CURRENT_EXPERIMENT_EPOCH)
    history = await db.get_council_history(limit=1)
    payload = _summarize_council_focuses(analysis_payload, calibration_rows)
    payload["session_number"] = (history[0]["id"] + 1) if history else 1
    payload["analysis_epoch"] = ((analysis_payload.get("analysis_scope") or {}).get("epoch") or db.CURRENT_EXPERIMENT_EPOCH)
    council_id = await db.add_council_entry(payload)
    payload["council_id"] = council_id
    latest = await db.get_council_history(limit=1)
    if latest:
        payload["created_at"] = latest[0].get("created_at")
    return JSONResponse(payload)


@app.get("/api/council/history")
async def council_history():
    return JSONResponse(await db.get_council_history(limit=10))


@app.get("/api/council/actions")
async def council_actions():
    rows = await db.get_council_actions(limit=100)
    return JSONResponse(_build_council_action_summary(rows))


@app.get("/api/rules/promotions")
async def rule_promotion_proposals():
    return JSONResponse(await db.compute_rule_promotion_proposals())


@app.post("/api/council/actions")
async def apply_council_action(payload: CouncilActionPayload = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    auth_error = _require_admin_token(x_admin_token)
    if auth_error:
        return auth_error
    payload = _payload_dict(payload)
    action_type = (payload.get("action_type") or "").strip()
    title = (payload.get("title") or "").strip()
    if action_type not in {"prompt_diagnosis_refinement", "evaluator_education_target", "contrast_set_candidate"}:
        return JSONResponse({"error": "unsupported council action type"}, status_code=400)
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)
    normalized = {
        "council_id": payload.get("council_id"),
        "action_type": action_type,
        "title": title,
        "status": (payload.get("status") or _default_council_action_status(action_type)).strip(),
        "lane": payload.get("lane"),
        "prompt_family": payload.get("prompt_family"),
        "payload": payload.get("payload") or {},
    }
    if action_type == "contrast_set_candidate" and normalized["status"] == "queued":
        normalized["payload"] = await _ensure_contrast_reference_pack({
            **normalized,
            "title": title,
        })
    saved = await db.upsert_council_action(normalized)
    return JSONResponse({"status": "saved", "action": saved})


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
