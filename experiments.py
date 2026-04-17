"""Task corpus and scheduling helpers for Hamlet's Ghost.

This module provides the structured prompt substrate for the research engine.
Its job is to produce comparable evidence across lanes and families, not to act
like a product feature surface of its own.
"""

import json
import random
from pathlib import Path


PROMPT_LIBRARY_PATH = Path(__file__).resolve().parent / "data" / "prompt_library.json"
PROMPT_STATUSES = {"active", "paused", "retired", "calibration"}
PROMPT_DIFFICULTIES = {"starter", "standard", "stretch", "frontier"}


CREATIVE_POLICY_VARIANTS = {
    "literal_discipline": {
        "prompt_policy_variant": "literal_discipline",
        "framing_style": "literal",
        "novelty_pressure": "low",
        "audience_grounding_level": "medium",
        "generation_guidance": "Favor literal clarity, direct images, and disciplined execution over ornamental surprise.",
    },
    "balanced_imagery": {
        "prompt_policy_variant": "balanced_imagery",
        "framing_style": "balanced",
        "novelty_pressure": "medium",
        "audience_grounding_level": "medium",
        "generation_guidance": "Balance originality with legibility. Reach for striking language only when it sharpens the core idea.",
    },
    "metaphorical_push": {
        "prompt_policy_variant": "metaphorical_push",
        "framing_style": "metaphorical",
        "novelty_pressure": "high",
        "audience_grounding_level": "light",
        "generation_guidance": "Push for surprising metaphors, layered associations, and stronger expressive risk without violating constraints.",
    },
}

BUSINESS_POLICY_VARIANTS = {
    "plain_operator": {
        "prompt_policy_variant": "plain_operator",
        "framing_style": "plain",
        "novelty_pressure": "low",
        "audience_grounding_level": "specific_operator",
        "generation_guidance": "Write like a sharp operator. Prioritize specificity, trustworthiness, and direct usefulness over cleverness.",
    },
    "humanized_trust": {
        "prompt_policy_variant": "humanized_trust",
        "framing_style": "humanized",
        "novelty_pressure": "medium",
        "audience_grounding_level": "specific_operator",
        "generation_guidance": "Sound observably human, concrete, and emotionally believable while staying commercially useful.",
    },
    "creative_push": {
        "prompt_policy_variant": "creative_push",
        "framing_style": "creative",
        "novelty_pressure": "high",
        "audience_grounding_level": "light",
        "generation_guidance": "Search for non-obvious angles and memorable phrasing, but keep the business objective intact.",
    },
    "humanized_creative": {
        "prompt_policy_variant": "humanized_creative",
        "framing_style": "humanized_creative",
        "novelty_pressure": "high",
        "audience_grounding_level": "specific_operator",
        "generation_guidance": "Combine believable human voice with novel, non-generic thinking that still feels grounded in the user's situation.",
    },
}

DEFAULT_POLICY_VARIANTS = {
    "creative": "balanced_imagery",
    "business": "plain_operator",
}

STUDY_MODES = {
    "exploratory_batch": {
        "creative": ("literal_discipline", "metaphorical_push"),
        "business": ("plain_operator", "humanized_creative"),
    },
    "calibration_mode": {
        "creative": ("balanced_imagery", "literal_discipline"),
        "business": ("plain_operator", "humanized_trust"),
    },
}


def _load_prompt_library(path: Path = PROMPT_LIBRARY_PATH):
    payload = json.loads(path.read_text())
    defaults = payload.get("defaults") or {}
    tasks = [_normalize_prompt_record(task, defaults) for task in (payload.get("tasks") or [])]
    if not tasks:
        raise ValueError("Prompt library is empty.")

    ids = [task["id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Prompt library contains duplicate task ids.")

    by_track = {
        "creative_constrained": [task for task in tasks if task["status"] == "active" and task["lane"] == "creative" and task["track"] == "constrained"],
        "creative_open": [task for task in tasks if task["status"] == "active" and task["lane"] == "creative" and task["track"] == "open_ended"],
        "creative_transformational": [task for task in tasks if task["status"] == "active" and task["lane"] == "creative" and task["track"] == "transformational"],
        "business": [task for task in tasks if task["status"] == "active" and task["lane"] == "business"],
    }

    return {
        "version": payload.get("version", "unknown"),
        "summary": payload.get("summary", {}),
        "defaults": defaults,
        "tasks": tasks,
        **by_track,
    }


def _derive_prompt_difficulty(task):
    track = task.get("track")
    family = task.get("family")
    constraints = task.get("constraints") or []
    if track == "transformational":
        return "frontier"
    if track == "open_ended":
        return "stretch"
    if family in {"formal_constraint_poetry", "formal_constraint_prose", "lexical_constraint"}:
        return "stretch"
    if len(constraints) >= 4:
        return "stretch"
    return "standard"


def _derive_prompt_priority(task):
    family = task.get("family")
    track = task.get("track")
    lane = task.get("lane")
    if track in {"open_ended", "transformational"}:
        return "high"
    if family in {"personification", "genre_mismatch", "retention_messaging", "customer_recovery"}:
        return "high"
    if lane == "business" and family in {"pitch", "internal_comms"}:
        return "medium"
    return "medium" if lane == "creative" else "low"


def _derive_prompt_tags(task):
    tags = {
        task["lane"],
        task["track"],
        task["family"],
        task["hypothesis"],
    }
    tags.add("constrained_prompt" if task.get("constraints") else "unconstrained_prompt")
    if task["track"] == "transformational":
        tags.add("form_invention")
    if task["track"] == "open_ended":
        tags.add("novelty_probe")
    if task["lane"] == "business":
        tags.add("commercial")
    return sorted(tags)


def _normalize_prompt_record(task, defaults):
    normalized = dict(task)
    normalized["constraints"] = list(normalized.get("constraints") or [])
    normalized["status"] = normalized.get("status") or defaults.get("status", "active")
    if normalized["status"] not in PROMPT_STATUSES:
        raise ValueError(f"Prompt '{normalized['id']}' has invalid status '{normalized['status']}'.")

    normalized["difficulty"] = normalized.get("difficulty") or _derive_prompt_difficulty(normalized)
    if normalized["difficulty"] not in PROMPT_DIFFICULTIES:
        raise ValueError(f"Prompt '{normalized['id']}' has invalid difficulty '{normalized['difficulty']}'.")

    normalized["provenance"] = normalized.get("provenance") or defaults.get("provenance", "hamlets_ghost_seed_corpus")
    normalized["human_judgment_priority"] = normalized.get("human_judgment_priority") or _derive_prompt_priority(normalized)
    normalized["tags"] = sorted(set((normalized.get("tags") or []) + _derive_prompt_tags(normalized)))
    normalized["notes"] = normalized.get("notes") or ""
    return normalized


PROMPT_LIBRARY = _load_prompt_library()
PROMPT_LIBRARY_VERSION = PROMPT_LIBRARY["version"]
PROMPT_LIBRARY_DEFAULTS = PROMPT_LIBRARY.get("defaults", {})


# =============================================================================
# TASKS
# =============================================================================

CREATIVE_CONSTRAINED = PROMPT_LIBRARY["creative_constrained"]
CREATIVE_OPEN = PROMPT_LIBRARY["creative_open"]
CREATIVE_TRANSFORMATIONAL = PROMPT_LIBRARY["creative_transformational"]
BUSINESS_TASKS = PROMPT_LIBRARY["business"]


# =============================================================================
# HYPOTHESES
# =============================================================================

HYPOTHESES = {
    "h_constraint_satisfaction": {
        "description": "Can iterative critique improve constraint satisfaction without reducing creative quality?",
        "lane": "creative",
    },
    "h_dual_register": {
        "description": "Can outputs maintain coherence in two registers simultaneously (e.g., grief + furniture assembly)?",
        "lane": "creative",
    },
    "h_genre_mismatch": {
        "description": "Does genre mismatch produce higher surprise scores than single-genre tasks without collapsing coherence?",
        "lane": "creative",
    },
    "h_domain_transfer": {
        "description": "Can emotional content emerge from structural relationships in a non-emotional domain?",
        "lane": "creative",
    },
    "h_impossible_object": {
        "description": "Can language evoke sensory experiences of things that do not exist or cannot be directly seen?",
        "lane": "creative",
    },
    "h_personification": {
        "description": "Does personification of technical or abstract subjects produce genuine pathos rather than decorative novelty?",
        "lane": "creative",
    },
    "h_open_novelty": {
        "description": "Do unconstrained tasks produce useful novelty or merely ungoverned strangeness?",
        "lane": "creative",
    },
    "h_expert_surprise": {
        "description": "Can the system produce work that a domain expert would find genuinely surprising?",
        "lane": "creative",
    },
    "h_transformational": {
        "description": "Can the system critique an existing form's limitations and invent a genuinely new form that addresses them?",
        "lane": "creative",
    },
    "h_business_copy": {
        "description": "Can AI-generated business writing sound specific, differentiated, and commercially useful without collapsing into cliche?",
        "lane": "business",
    },
    "h_retention": {
        "description": "Can AI-generated retention and winback messaging sound authentically human while being strategically effective?",
        "lane": "business",
    },
    "h_strategic_positioning": {
        "description": "Can the system generate positioning and strategy grounded in specific scenarios rather than generic claims?",
        "lane": "business",
    },
    "h_conversion": {
        "description": "Can constraint-driven copy generation produce clearer, stronger conversion language than generic marketing phrasing?",
        "lane": "business",
    },
    "h_customer_voice": {
        "description": "Can AI produce customer-facing responses that avoid corporate cliches while maintaining accountability and trust?",
        "lane": "business",
    },
    "h_product_ideation": {
        "description": "Can the system generate product ideas grounded in behavioral insight rather than feature checklist thinking?",
        "lane": "business",
    },
    "h_persuasion": {
        "description": "Can the system produce persuasive business writing that is memorable without becoming gimmicky?",
        "lane": "business",
    },
    "h_leadership_comms": {
        "description": "Can AI draft leadership communications that are honest, trust-preserving, and operationally useful during difficult change?",
        "lane": "business",
    },
}


# =============================================================================
# ALL TASKS
# =============================================================================

ALL_CREATIVE = CREATIVE_CONSTRAINED + CREATIVE_OPEN + CREATIVE_TRANSFORMATIONAL
ALL_BUSINESS = BUSINESS_TASKS
ALL_TASKS = {task["id"]: task for task in ALL_CREATIVE + ALL_BUSINESS}

BASELINE_CANARIES = {
    "creative": {
        **CREATIVE_CONSTRAINED[0],
        **CREATIVE_POLICY_VARIANTS[DEFAULT_POLICY_VARIANTS["creative"]],
        "condition": "critique_off",
        "purpose": "baseline_canary",
        "study_mode": "baseline_canary",
        "repetition": "baseline",
    },
    "business": {
        **BUSINESS_TASKS[0],
        **BUSINESS_POLICY_VARIANTS[DEFAULT_POLICY_VARIANTS["business"]],
        "condition": "critique_off",
        "purpose": "baseline_canary",
        "study_mode": "baseline_canary",
        "repetition": "baseline",
    },
}


def get_next_task(lane=None, track=None):
    if lane == "business":
        return random.choice(ALL_BUSINESS)
    if track == "constrained":
        return random.choice(CREATIVE_CONSTRAINED)
    if track == "open_ended":
        return random.choice(CREATIVE_OPEN)
    if track == "transformational":
        return random.choice(CREATIVE_TRANSFORMATIONAL)
    return random.choice(CREATIVE_CONSTRAINED)


def get_tasks_by_status(status="active"):
    return [task for task in PROMPT_LIBRARY["tasks"] if task["status"] == status]


def get_human_review_priority_tasks(priority="high"):
    return [task for task in get_tasks_by_status("active") if task.get("human_judgment_priority") == priority]


def get_policy_variants_for_lane(lane):
    return CREATIVE_POLICY_VARIANTS if lane == "creative" else BUSINESS_POLICY_VARIANTS


def apply_policy_variant(task, variant_name=None, provenance=None, approved_default_variant=None):
    lane = task.get("lane", "creative")
    variants = get_policy_variants_for_lane(lane)
    chosen = variant_name or task.get("prompt_policy_variant") or DEFAULT_POLICY_VARIANTS.get(lane)
    policy = variants.get(chosen) or variants[DEFAULT_POLICY_VARIANTS[lane]]
    resolved_provenance = provenance
    if resolved_provenance is None:
        if task.get("prompt_policy_variant") and variant_name is None:
            resolved_provenance = "manual_override"
        elif approved_default_variant and chosen == approved_default_variant:
            resolved_provenance = "approved_family_default"
        elif chosen == DEFAULT_POLICY_VARIANTS.get(lane):
            resolved_provenance = "system_default"
        else:
            resolved_provenance = "exploratory_non_default"
    return {
        **task,
        **policy,
        "policy_source": resolved_provenance,
        "approved_family_policy_variant": approved_default_variant,
    }


def apply_policy_control(task, approved_default_variant=None):
    explicit_variant = task.get("prompt_policy_variant")
    if explicit_variant:
        return apply_policy_variant(
            task,
            explicit_variant,
            provenance="manual_override",
            approved_default_variant=approved_default_variant,
        )
    if approved_default_variant:
        return apply_policy_variant(
            task,
            approved_default_variant,
            provenance="approved_family_default",
            approved_default_variant=approved_default_variant,
        )
    return apply_policy_variant(
        task,
        DEFAULT_POLICY_VARIANTS.get(task.get("lane", "creative")),
        provenance="system_default",
        approved_default_variant=approved_default_variant,
    )


def build_policy_context(task):
    return {
        "prompt_policy_variant": task.get("prompt_policy_variant"),
        "framing_style": task.get("framing_style"),
        "novelty_pressure": task.get("novelty_pressure"),
        "audience_grounding_level": task.get("audience_grounding_level"),
        "generation_guidance": task.get("generation_guidance", ""),
        "policy_source": task.get("policy_source"),
        "approved_family_policy_variant": task.get("approved_family_policy_variant"),
    }


def _inject_baseline_canaries(schedule, n_experiments, cadence=8):
    """Replay fixed tasks at a regular cadence to measure drift against a stable baseline."""
    if not schedule or cadence <= 0:
        return schedule[:n_experiments]

    result = list(schedule[:n_experiments])
    insert_points = list(range(cadence - 1, len(result), cadence))
    canaries = [BASELINE_CANARIES["creative"], BASELINE_CANARIES["business"]]

    for idx, insert_at in enumerate(insert_points):
        canary = dict(canaries[idx % len(canaries)])
        canary["baseline_slot"] = insert_at + 1
        result[insert_at] = canary

    return result


def _build_policy_validation_tasks(policy_controls, max_tasks=6):
    if not policy_controls:
        return []

    validation = []
    for (lane, family), control in policy_controls.items():
        status = control.get("operational_status")
        approved_variant = control.get("approved_value")
        if status not in {"approved_pending_use", "approved_in_trial"} or not approved_variant:
            continue

        pool = [
            task
            for task in (ALL_BUSINESS if lane == "business" else ALL_CREATIVE)
            if task.get("family") == family and task.get("lane") == lane
        ]
        if not pool:
            continue

        base_task = random.choice(pool)
        for idx, condition in enumerate(("critique_on", "critique_off")):
            validation_task = apply_policy_control(
                {
                    **base_task,
                    "condition": condition,
                    "repetition": f"validation_{idx}",
                    "study_mode": "policy_validation",
                },
                approved_variant,
            )
            validation_task["validation_target_status"] = status
            validation.append(validation_task)
            if len(validation) >= max_tasks:
                return validation

    return validation


def build_experiment_schedule(
    n_experiments=40,
    creative_weight=0.6,
    business_weight=0.4,
    study_mode="exploratory_batch",
    approved_policy_controls=None,
):
    """Build experimental schedule with:
    - Two lanes: creative and business
    - Paired controls: same prompt with and without critique
    - Repeated prompts for variance measurement
    - Balanced distribution by weight
    """
    policy_controls = approved_policy_controls or {}
    validation_schedule = _build_policy_validation_tasks(policy_controls, max_tasks=max(2, min(6, n_experiments // 4 or 1)))
    schedule = list(validation_schedule)

    remaining_slots = max(0, n_experiments - len(validation_schedule))
    creative_ratio = float(creative_weight)
    business_ratio = float(business_weight)
    total_ratio = creative_ratio + business_ratio
    if total_ratio <= 0:
        creative_ratio = 0.6
        business_ratio = 0.4
        total_ratio = 1.0
    n_creative = int(remaining_slots * (creative_ratio / total_ratio))
    n_business = remaining_slots - n_creative

    selected_mode = STUDY_MODES.get(study_mode, STUDY_MODES["exploratory_batch"])

    creative_sample = random.sample(ALL_CREATIVE, min(n_creative // 4 + 1, len(ALL_CREATIVE)))
    for task in creative_sample:
        creative_variants = selected_mode["creative"]
        control = policy_controls.get((task.get("lane"), task.get("family")), {})
        approved_variant = control.get("approved_value")
        for condition in ["critique_on", "critique_off"]:
            for rep, variant_name in enumerate(creative_variants):
                scheduled_task = {
                    **task,
                    "condition": condition,
                    "repetition": rep,
                    "study_mode": study_mode,
                }
                if rep == 0 and approved_variant:
                    schedule.append(apply_policy_control(scheduled_task, approved_variant))
                else:
                    schedule.append(
                        apply_policy_variant(
                            scheduled_task,
                            variant_name,
                            provenance="exploratory_non_default",
                            approved_default_variant=approved_variant,
                        )
                    )

    business_sample = random.sample(ALL_BUSINESS, min(n_business // 4 + 1, len(ALL_BUSINESS)))
    for task in business_sample:
        business_variants = selected_mode["business"]
        control = policy_controls.get((task.get("lane"), task.get("family")), {})
        approved_variant = control.get("approved_value")
        for condition in ["critique_on", "critique_off"]:
            for rep, variant_name in enumerate(business_variants):
                scheduled_task = {
                    **task,
                    "condition": condition,
                    "repetition": rep,
                    "study_mode": study_mode,
                }
                if rep == 0 and approved_variant:
                    schedule.append(apply_policy_control(scheduled_task, approved_variant))
                else:
                    schedule.append(
                        apply_policy_variant(
                            scheduled_task,
                            variant_name,
                            provenance="exploratory_non_default",
                            approved_default_variant=approved_variant,
                        )
                    )

    exploratory_schedule = schedule[len(validation_schedule):]
    random.shuffle(exploratory_schedule)
    final_schedule = list(validation_schedule) + exploratory_schedule
    return _inject_baseline_canaries(final_schedule, n_experiments=n_experiments)
