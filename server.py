from __future__ import annotations

import asyncio
import hashlib
import json
import os
import traceback as tb
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import agents
import database as db
import experiments

load_dotenv()

PROMOTE_COMPOSITE_THRESHOLD = 7.0
KEEP_COMPOSITE_THRESHOLD = 6.5
MAX_DIVERGENCE_FOR_PROMOTION = 1.5
MAX_CONSECUTIVE_DISCARDS = 10
FORCED_HERMES_LOW_SCORE_MODULO = max(0, int(os.getenv("FORCED_HERMES_LOW_SCORE_MODULO", "5")))
FORCED_HERMES_CONSTRAINT_FAIL_MODULO = max(0, int(os.getenv("FORCED_HERMES_CONSTRAINT_FAIL_MODULO", "3")))
FORCED_HERMES_UNKNOWN_CONSTRAINT_MODULO = max(0, int(os.getenv("FORCED_HERMES_UNKNOWN_CONSTRAINT_MODULO", "4")))
DEFAULT_HOST = os.getenv("LAB_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("PORT", "7777"))
ADMIN_TOKEN_HEADER = "X-Admin-Token"

_runner_task = None
_stop_event = asyncio.Event()
_runner_transition_lock = asyncio.Lock()


def _hash_prompt(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


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
HERMES_HASH = _hash_prompt(agents.HERMES_SYSTEM)
HERMES_BUSINESS_HASH = _hash_prompt(agents.HERMES_BUSINESS_SYSTEM)


async def seed_hypotheses():
    for h_id, h_data in experiments.HYPOTHESES.items():
        await db.insert_hypothesis(h_id, h_data["description"], h_data["lane"])
    await db.store_prompt_version(GENESIS_HASH, "genesis", GENESIS_PROMPT_BUNDLE)
    await db.store_prompt_version(MUSE_HASH, "muse", agents.MUSE_SYSTEM)
    await db.store_prompt_version(MUSE_BUSINESS_HASH, "muse_business", agents.MUSE_BUSINESS_SYSTEM)
    await db.store_prompt_version(HERMES_HASH, "hermes", agents.HERMES_SYSTEM)
    await db.store_prompt_version(HERMES_BUSINESS_HASH, "hermes_business", agents.HERMES_BUSINESS_SYSTEM)


def _build_orchestration_trace(task):
    return {
        "policy": agents.describe_orchestration_policy(),
        "planned_agents": ["genesis", "muse", "hermes"],
        "executed_agents": ["genesis"],
        "skipped_agents": [],
        "gates": {
            "hermes": {"eligible": None, "decision": "pending", "reason": "awaiting_muse_triage"},
            "scout": {"eligible": False, "decision": "skipped", "reason": "not_implemented"},
        },
        "task_context": {
            "lane": task.get("lane"),
            "track": task.get("track"),
            "condition": task.get("condition"),
            "hypothesis_id": task.get("hypothesis"),
        },
    }


def _forced_hermes_reason(experiment_id, muse_result):
    if not experiment_id or not muse_result:
        return None
    composite = muse_result.get("composite")
    constraints_met = muse_result.get("constraints_met")
    if constraints_met is False and FORCED_HERMES_CONSTRAINT_FAIL_MODULO and experiment_id % FORCED_HERMES_CONSTRAINT_FAIL_MODULO == 0:
        return "forced_sample_constraint_fail"
    if constraints_met is None and FORCED_HERMES_UNKNOWN_CONSTRAINT_MODULO and experiment_id % FORCED_HERMES_UNKNOWN_CONSTRAINT_MODULO == 0:
        return "forced_sample_unknown_constraints"
    if composite is not None and composite < agents.HERMES_MIN_MUSE_COMPOSITE:
        if FORCED_HERMES_LOW_SCORE_MODULO and experiment_id % FORCED_HERMES_LOW_SCORE_MODULO == 0:
            return "forced_sample_low_muse"
    return None


def _should_run_hermes(muse_result, muse_parse_failure, experiment_id=None):
    if muse_parse_failure:
        return False, "muse_parse_failure"
    if not agents.HERMES_GATE_ENABLED:
        return True, "gate_disabled"

    composite = muse_result.get("composite") if muse_result else None
    constraints_met = muse_result.get("constraints_met") if muse_result else None

    if composite is None:
        return False, "missing_muse_composite"
    if agents.HERMES_REQUIRE_CONSTRAINT_PASS and constraints_met is False:
        forced_reason = _forced_hermes_reason(experiment_id, muse_result)
        return (True, forced_reason) if forced_reason else (False, "constraint_failed_before_hermes")
    if composite < agents.HERMES_MIN_MUSE_COMPOSITE:
        forced_reason = _forced_hermes_reason(experiment_id, muse_result)
        return (True, forced_reason) if forced_reason else (False, f"muse_below_threshold_{agents.HERMES_MIN_MUSE_COMPOSITE:.1f}")
    if constraints_met is None:
        forced_reason = _forced_hermes_reason(experiment_id, muse_result)
        if forced_reason:
            return True, forced_reason
    return True, "candidate_threshold_met"


def _extract_verifier_constraint_state(process_trace):
    trace = process_trace or {}
    return {
        "has_effective_constraints": bool(trace.get("verifier_checks") or trace.get("verifier_inferred_constraints")),
        "verification_status": trace.get("verification_status"),
    }


def _apply_verifier_constraint_state(result, process_trace):
    return result, _extract_verifier_constraint_state(process_trace)


async def _resolve_policy_control(task):
    controls = await db.get_approved_policy_controls()
    family_default = controls.get((task.get("lane"), task.get("family")))
    approved_variant = family_default.get("approved_value") if family_default else None
    resolved = experiments.apply_policy_control(dict(task), approved_default_variant=approved_variant)
    if family_default:
        resolved["policy_operational_status"] = family_default.get("operational_status")
    return resolved


async def _execute_experiment(task, iteration, consecutive_discards=0):
    task = await _resolve_policy_control(task)
    exp_id = await db.create_experiment(task)
    await db.update_state(
        current_lane=task.get("lane"),
        current_track=task.get("track"),
        current_experiment_id=exp_id,
    )

    orchestration_trace = _build_orchestration_trace(task)
    total_cost = 0.0
    try:
        genesis_result, genesis_cost, _genesis_parse_failure = await agents.run_genesis(
            prompt=task["prompt"],
            constraints=task.get("constraints"),
            lane=task.get("lane", "creative"),
            policy_context={
                "prompt_policy_variant": task.get("prompt_policy_variant"),
                "policy_source": task.get("policy_source"),
                "generation_guidance": task.get("generation_guidance"),
            },
        )
        total_cost += genesis_cost or 0.0
        artifact_content = genesis_result.get("artifact") or ""
        process_trace = genesis_result.get("process_trace") or {}
        process_trace.setdefault("verification_status", "not_run")
        process_trace.setdefault("verifier_findings", [])
        process_trace.setdefault("verifier_checks", [])
        process_trace.setdefault("verifier_inferred_constraints", [])
        process_trace.setdefault("stage_costs", {})
        process_trace["orchestration"] = orchestration_trace
        await db.insert_artifact(exp_id, artifact_content, process_trace=process_trace, source_context={})

        muse_result, muse_cost, muse_parse_failure = await agents.run_muse(
            artifact=artifact_content,
            prompt=task["prompt"],
            constraints=task.get("constraints"),
            lane=task.get("lane", "creative"),
        )
        total_cost += muse_cost or 0.0

        has_constraints = bool(task.get("constraints"))
        stored_muse_result = dict(muse_result)
        if not has_constraints and stored_muse_result.get("constraints_met") is None:
            stored_muse_result["constraints_met"] = True
        await db.insert_score(exp_id, "muse", stored_muse_result, cost=muse_cost, parse_failure=muse_parse_failure)

        verifier_state = _extract_verifier_constraint_state(process_trace)
        run_hermes, hermes_gate_reason = _should_run_hermes(muse_result, muse_parse_failure, experiment_id=exp_id)
        orchestration_trace["gates"]["hermes"] = {
            "eligible": run_hermes,
            "decision": "run" if run_hermes else "skipped",
            "reason": hermes_gate_reason,
            "muse_composite": muse_result.get("composite") if muse_result else None,
            "constraints_met": muse_result.get("constraints_met") if muse_result else None,
        }

        holdout_result = None
        holdout_parse_failure = True
        holdout_cost = 0.0
        if run_hermes:
            try:
                holdout_result, holdout_cost, holdout_parse_failure = await agents.run_hermes(
                    artifact=artifact_content,
                    prompt=task["prompt"],
                    constraints=task.get("constraints"),
                    lane=task.get("lane", "creative"),
                )
                total_cost += holdout_cost or 0.0
                if not holdout_parse_failure:
                    await db.insert_score(exp_id, "hermes", holdout_result, cost=holdout_cost, parse_failure=False)
                    orchestration_trace["executed_agents"].append("hermes")
                else:
                    orchestration_trace["gates"]["hermes"]["decision"] = "parse_failure"
                    orchestration_trace["gates"]["hermes"]["reason"] = "hermes_parse_failure"
            except Exception as exc:
                orchestration_trace["gates"]["hermes"]["decision"] = "error"
                orchestration_trace["gates"]["hermes"]["reason"] = str(exc)
        else:
            orchestration_trace["skipped_agents"].append("hermes")

        composite = muse_result.get("composite")
        constraints_met = muse_result.get("constraints_met")
        has_effective_constraints = has_constraints or verifier_state["has_effective_constraints"]
        effective_constraints_passed = constraints_met is not False if not has_effective_constraints else constraints_met is True

        critic_composite = holdout_result.get("composite") if holdout_result and not holdout_parse_failure else None
        divergence = abs(composite - critic_composite) if composite is not None and critic_composite is not None else None

        if muse_parse_failure:
            keep = False
            status = "invalid"
            promotion = "candidate"
        elif has_effective_constraints and not effective_constraints_passed:
            keep = False
            status = "constraint_fail"
            promotion = "candidate"
        elif composite is not None and composite >= PROMOTE_COMPOSITE_THRESHOLD and effective_constraints_passed:
            if divergence is not None and divergence < MAX_DIVERGENCE_FOR_PROMOTION:
                keep = True
                status = "promoted"
                promotion = "shadow"
            else:
                keep = True
                status = "kept"
                promotion = "candidate"
        elif composite is not None and composite >= KEEP_COMPOSITE_THRESHOLD and effective_constraints_passed:
            keep = True
            status = "kept"
            promotion = "candidate"
        else:
            keep = False
            status = "discard"
            promotion = "candidate"

        orchestration_trace["final_outcome"] = {"status": status, "promotion_status": promotion, "keep": keep}
        process_trace["orchestration"] = orchestration_trace
        await db.update_artifact_process_trace(exp_id, process_trace)
        await db.finalize_experiment(
            exp_id,
            status=status,
            promotion_status=promotion,
            parse_failure=muse_parse_failure,
            cost=total_cost,
        )

        state = await db.get_state()
        best_score = state.get("best_score")
        next_best = best_score if best_score is not None else composite
        if composite is not None and (next_best is None or composite > next_best):
            next_best = composite
        await db.update_state(
            total_experiments=(state.get("total_experiments") or 0) + 1,
            kept=(state.get("kept") or 0) + (1 if status in {"kept", "promoted"} else 0),
            discarded=(state.get("discarded") or 0) + (1 if status in {"discard", "constraint_fail", "invalid"} else 0),
            promoted=(state.get("promoted") or 0) + (1 if status == "promoted" else 0),
            best_score=next_best,
            total_cost=(state.get("total_cost") or 0.0) + total_cost,
            consecutive_discards=0 if keep else min(MAX_CONSECUTIVE_DISCARDS, (consecutive_discards or 0) + 1),
        )
        return {
            "experiment_id": exp_id,
            "status": status,
            "promotion_status": promotion,
            "keep": keep,
            "artifact": artifact_content,
        }
    except Exception:
        traceback_text = tb.format_exc()
        await db.finalize_experiment(exp_id, status="error", promotion_status="candidate", parse_failure=True, cost=total_cost, error_traceback=traceback_text)
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
    rows = await db.get_recent_experiments()
    return JSONResponse([_sanitize_experiment_record(row) for row in rows])


@app.get("/api/timeline")
async def get_timeline():
    return JSONResponse(await db.get_timeline())


@app.get("/api/analysis")
async def get_analysis():
    return JSONResponse(await db.get_analysis_payload())


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
async def start_lab(payload: dict = Body(default={}), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
    global _runner_task, _stop_event
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
async def run_custom_experiment(payload: dict = Body(...), x_admin_token: str | None = Header(None, alias=ADMIN_TOKEN_HEADER)):
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
    }
    state = await db.get_state()
    result = await _execute_experiment(task, iteration=(state["total_experiments"] or 0) + 1, consecutive_discards=state.get("consecutive_discards") or 0)
    return JSONResponse(result)


@app.get("/api/artifact/{experiment_id}")
async def get_artifact(experiment_id: int):
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
    payload = {"summary": "Council trigger placeholder during recovery."}
    await db.add_council_entry(payload)
    return JSONResponse(payload)


@app.get("/api/council/history")
async def council_history():
    return JSONResponse(await db.get_council_history(limit=10))


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
