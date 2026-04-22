from __future__ import annotations

import json
import os
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import hashlib

import aiosqlite


DB_PATH = os.getenv("LAB_DB_PATH") or os.path.join(os.path.dirname(__file__), "creativity_lab.db")
SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_JOURNAL_MODE = "WAL"
SQLITE_SYNCHRONOUS_MODE = "NORMAL"
DISAGREEMENT_JUDGES = ("muse", "athena", "apollo")
APOLLO_REVIEW_JUDGE = "apollo"
APOLLO_CONTEXT_JUDGES = ("muse", "athena")
LEGACY_EXPERIMENT_EPOCH = os.getenv("LAB_LEGACY_EPOCH", "legacy_foundation")
CURRENT_EXPERIMENT_EPOCH = os.getenv("LAB_CURRENT_EPOCH", "native_cast")
REASON_TAG_ATTRIBUTION_KEYS = ("winner", "loser", "both", "unattributed")
REASON_TAG_EVIDENCE_TARGETS = ("winner", "loser", "both", "unattributed")
REVIEW_CONFIDENCE_LEVELS = ("certain", "tentative", "coin_flip")
REVIEW_DECISION_STATES = ("final", "revisit_later")
REVIEW_VERDICTS = ("preferred", "tie", "both_bad", "abstain")
PAIR_DISTINCTIVENESS_LEVELS = ("clearly_distinct", "somewhat_distinct", "same_writer")
PACKET_RESOLUTION_TYPES = ("discarded_failure", "repaired", "abandoned")
PROMPT_RULE_STATUSES = ("candidate", "provisional", "active", "core")
PROMPT_RULE_SCOPE_CLAIMS = ("universal", "family_specific", "model_specific")
PROMPT_RULE_EVIDENCE_SIGNALS = ("helped", "hurt", "mixed", "unreviewed")
PROMPT_RULE_EXPERIMENT_TYPES = ("raw_vs_compiled", "rule_on_vs_off", "variant_a_vs_b", "cross_model_replication")
PROMPT_RULE_PROMOTION_DEFAULTS = {
    "provisional_packets": 5,
    "provisional_families": 2,
    "active_packets": 15,
    "active_families": 3,
    "active_model_families": 2,
    "active_human_win_rate": 0.6,
    "active_human_decisive": 3,
    "hurt_flag_rate": 0.4,
    "hurt_flag_min": 5,
    "panel_preference_rate": 0.6,
    "characterization_min_human": 5,
}
PROMPT_RULE_CHARACTERIZATIONS = (
    "aligned",
    "llm_specific",
    "divergent",
    "human_specific",
    "neutral",
    "insufficient_data",
)
JUDGE_PANEL_VERSION = os.getenv("LAB_JUDGE_PANEL_VERSION", "muse_athena_apollo_v1_independent")
BLIND_REREVIEW_LOOKBACK_DAYS = 7
ASSEMBLING_STALE_MINUTES = max(5, int(os.getenv("LAB_ASSEMBLING_STALE_MINUTES", "20")))


def _canonical_role_id(role_id):
    if role_id == "hermes":
        return "athena"
    return "apollo" if role_id == "hermes_external" else role_id


def _judge_winner(score_map, *, judge, experiment_ids, min_margin):
    scored = []
    for experiment_id in experiment_ids:
        value = score_map.get(experiment_id, {}).get(judge)
        if value is not None:
            scored.append((experiment_id, float(value)))
    if len(scored) < 2:
        return None
    scored.sort(key=lambda item: (item[1], item[0]), reverse=True)
    top_id, top_score = scored[0]
    second_score = scored[1][1]
    margin = top_score - second_score
    return {
        "judge": judge,
        "winner_experiment_id": top_id if margin >= min_margin else None,
        "margin": margin,
        "scores": {experiment_id: score for experiment_id, score in scored},
    }


def _build_packet_disagreement(members, score_map, *, min_judge_margin):
    experiment_ids = [member.get("id") for member in members if member.get("id") is not None]
    judges = []
    for judge in DISAGREEMENT_JUDGES:
        summary = _judge_winner(score_map, judge=judge, experiment_ids=experiment_ids, min_margin=min_judge_margin)
        if summary:
            judges.append(summary)
    present_judges = {row["judge"] for row in judges}
    winners = [row["winner_experiment_id"] for row in judges if row["winner_experiment_id"] is not None]
    apollo_summary = next((row for row in judges if row["judge"] == APOLLO_REVIEW_JUDGE), None)
    apollo_winner = apollo_summary["winner_experiment_id"] if apollo_summary else None
    context_winners = [
        row["winner_experiment_id"]
        for row in judges
        if row["judge"] in APOLLO_CONTEXT_JUDGES and row["winner_experiment_id"] is not None
    ]
    has_review_ready_panel = (
        apollo_winner is not None
        and any(judge in present_judges for judge in APOLLO_CONTEXT_JUDGES)
    )
    has_complete_panel = len(judges) == len(DISAGREEMENT_JUDGES)
    has_noticeable_disagreement = has_review_ready_panel and any(
        winner != apollo_winner
        for winner in context_winners
    )
    vote_counts = {}
    for winner in winners:
        vote_counts[winner] = vote_counts.get(winner, 0) + 1
    return {
        "judges": judges,
        "has_review_ready_panel": has_review_ready_panel,
        "has_complete_panel": has_complete_panel,
        "has_noticeable_disagreement": has_noticeable_disagreement,
        "missing_judges": [judge for judge in DISAGREEMENT_JUDGES if judge not in present_judges],
        "vote_counts": vote_counts,
    }


def _mean(values):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _safe_json_loads(value, default=None):
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _slugify_key(value):
    key = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    while "__" in key:
        key = key.replace("__", "_")
    return key.strip("_") or "untitled"


def _normalize_rule_status(value):
    status = str(value or "").strip().lower()
    return status if status in PROMPT_RULE_STATUSES else "candidate"


def _normalize_rule_scope_claim(value, *, lane=None, prompt_family=None):
    scope = str(value or "").strip().lower()
    if scope in PROMPT_RULE_SCOPE_CLAIMS:
        return scope
    if prompt_family or lane:
        return "family_specific"
    return "universal"


def _normalize_rule_evidence_signal(value):
    signal = str(value or "").strip().lower()
    return signal if signal in PROMPT_RULE_EVIDENCE_SIGNALS else "unreviewed"


def _normalize_rule_experiment_type(value):
    experiment_type = str(value or "").strip().lower()
    return experiment_type if experiment_type in PROMPT_RULE_EXPERIMENT_TYPES else "raw_vs_compiled"


def _human_signal_from_review(review):
    if not review:
        return "unreviewed"
    metadata = _normalize_review_metadata(review.get("metadata") or {})
    verdict = metadata.get("review_verdict") or "preferred"
    if verdict in {"tie", "abstain"}:
        return "mixed"
    if verdict == "both_bad":
        return "mixed"
    preferred_experiment_id = review.get("preferred_experiment_id")
    if preferred_experiment_id is None:
        return "mixed"
    return None


def _normalize_reason_tag_list(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    normalized = []
    seen = set()
    for value in values:
        tag = str(value or "").strip().lower()
        if not tag:
            continue
        if tag not in seen:
            seen.add(tag)
            normalized.append(tag)
    return normalized


def _normalize_review_metadata(metadata):
    payload = dict(metadata or {})
    attribution = payload.get("reason_tag_attribution") or {}
    normalized_attribution = {
        key: _normalize_reason_tag_list(attribution.get(key))
        for key in REASON_TAG_ATTRIBUTION_KEYS
    }
    legacy_reason_tags = _normalize_reason_tag_list(payload.get("reason_tags"))
    if legacy_reason_tags and not any(normalized_attribution.values()):
        normalized_attribution["unattributed"] = legacy_reason_tags
    elif legacy_reason_tags:
        for tag in legacy_reason_tags:
            if not any(tag in normalized_attribution[key] for key in REASON_TAG_ATTRIBUTION_KEYS):
                normalized_attribution["unattributed"].append(tag)

    payload["reason_tag_attribution"] = {
        key: _normalize_reason_tag_list(normalized_attribution.get(key))
        for key in REASON_TAG_ATTRIBUTION_KEYS
    }
    payload["reason_tags"] = _normalize_reason_tag_list(
        [
            tag
            for key in REASON_TAG_ATTRIBUTION_KEYS
            for tag in payload["reason_tag_attribution"][key]
        ]
    )
    normalized_evidence = []
    for item in payload.get("reason_tag_evidence") or []:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip().lower()
        excerpt = str(item.get("excerpt") or "").strip()
        target = str(item.get("target") or "").strip().lower() or "unattributed"
        if target not in REASON_TAG_EVIDENCE_TARGETS:
            target = "unattributed"
        if not tag or not excerpt:
            continue
        normalized_evidence.append({
            "tag": tag,
            "target": target,
            "excerpt": excerpt,
        })
        if tag not in payload["reason_tag_attribution"][target]:
            payload["reason_tag_attribution"][target].append(tag)
        if tag not in payload["reason_tags"]:
            payload["reason_tags"].append(tag)
    payload["reason_tag_evidence"] = normalized_evidence
    confidence = str(payload.get("review_confidence") or "").strip().lower()
    payload["review_confidence"] = confidence if confidence in REVIEW_CONFIDENCE_LEVELS else None
    decision_state = str(payload.get("review_decision_state") or "").strip().lower()
    payload["review_decision_state"] = decision_state if decision_state in REVIEW_DECISION_STATES else "final"
    verdict = str(payload.get("review_verdict") or "").strip().lower()
    payload["review_verdict"] = verdict if verdict in REVIEW_VERDICTS else "preferred"
    pair_distinctiveness = str(payload.get("pair_distinctiveness") or "").strip().lower()
    payload["pair_distinctiveness"] = pair_distinctiveness if pair_distinctiveness in PAIR_DISTINCTIVENESS_LEVELS else None
    if payload["pair_distinctiveness"] == "same_writer":
        if "voice_collapse" not in payload["reason_tag_attribution"]["both"]:
            payload["reason_tag_attribution"]["both"].append("voice_collapse")
        if "voice_collapse" not in payload["reason_tags"]:
            payload["reason_tags"].append("voice_collapse")
    revision_history = payload.get("review_revision_history") or []
    normalized_history = []
    if isinstance(revision_history, list):
        for item in revision_history:
            if not isinstance(item, dict):
                continue
            normalized_history.append({
                "saved_at": item.get("saved_at"),
                "preferred_experiment_id": item.get("preferred_experiment_id"),
                "rationale": item.get("rationale"),
                "review_confidence": item.get("review_confidence"),
                "review_decision_state": item.get("review_decision_state"),
                "review_verdict": item.get("review_verdict") or "preferred",
                "pair_distinctiveness": item.get("pair_distinctiveness"),
                "reason_tag_attribution": {
                    key: _normalize_reason_tag_list((item.get("reason_tag_attribution") or {}).get(key))
                    for key in REASON_TAG_ATTRIBUTION_KEYS
                },
            })
    payload["review_revision_history"] = normalized_history
    payload["review_revision_count"] = len(normalized_history)
    reversal_count = 0
    prior_preferences = [item.get("preferred_experiment_id") for item in normalized_history if item.get("preferred_experiment_id") is not None]
    if payload.get("preferred_experiment_id") is not None:
        prior_preferences.append(payload.get("preferred_experiment_id"))
    for before, after in zip(prior_preferences, prior_preferences[1:]):
        if before != after:
            reversal_count += 1
    payload["review_reversal_count"] = reversal_count
    return payload


def _review_snapshot(review):
    metadata = _normalize_review_metadata(review.get("metadata") or {})
    return {
        "saved_at": review.get("updated_at") or review.get("created_at"),
        "preferred_experiment_id": review.get("preferred_experiment_id"),
        "rationale": review.get("rationale"),
        "review_confidence": metadata.get("review_confidence"),
        "review_decision_state": metadata.get("review_decision_state"),
        "review_verdict": metadata.get("review_verdict"),
        "pair_distinctiveness": metadata.get("pair_distinctiveness"),
        "reason_tag_attribution": metadata.get("reason_tag_attribution") or {
            key: [] for key in REASON_TAG_ATTRIBUTION_KEYS
        },
    }


def _reviews_meaningfully_differ(existing_review, new_payload):
    old_meta = _normalize_review_metadata(existing_review.get("metadata") or {})
    new_meta = _normalize_review_metadata(new_payload.get("metadata") or {})
    return any([
        existing_review.get("preferred_experiment_id") != new_payload.get("preferred_experiment_id"),
        (existing_review.get("rationale") or "").strip() != (new_payload.get("rationale") or "").strip(),
        old_meta.get("review_confidence") != new_meta.get("review_confidence"),
        old_meta.get("review_decision_state") != new_meta.get("review_decision_state"),
        old_meta.get("review_verdict") != new_meta.get("review_verdict"),
        old_meta.get("pair_distinctiveness") != new_meta.get("pair_distinctiveness"),
        old_meta.get("reason_tag_attribution") != new_meta.get("reason_tag_attribution"),
        old_meta.get("reason_tag_evidence") != new_meta.get("reason_tag_evidence"),
    ])


def _attach_review_metadata_stats(review_payload):
    payload = dict(review_payload or {})
    metadata = _normalize_review_metadata(payload.get("metadata") or {})
    preferences = [
        item.get("preferred_experiment_id")
        for item in metadata.get("review_revision_history") or []
        if item.get("preferred_experiment_id") is not None
    ]
    current_preference = payload.get("preferred_experiment_id")
    if current_preference is not None:
        preferences.append(current_preference)
    reversal_count = 0
    for before, after in zip(preferences, preferences[1:]):
        if before != after:
            reversal_count += 1
    metadata["review_reversal_count"] = reversal_count
    metadata["review_revision_count"] = len(metadata.get("review_revision_history") or [])
    payload["metadata"] = metadata
    return payload


def _parse_created_at(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def _packet_key_for_payload(payload):
    explicit_packet_id = payload.get("packet_id")
    if explicit_packet_id:
        return explicit_packet_id
    prompt = payload.get("prompt") or ""
    family = payload.get("prompt_family") or payload.get("family") or ""
    condition = payload.get("condition") or ""
    lane = payload.get("lane") or ""
    digest = hashlib.sha1(f"{lane}|{family}|{condition}|{prompt}".encode()).hexdigest()[:10]
    return f"pkt_{digest}"


def _normalize_epoch(value):
    epoch = (value or "").strip()
    return epoch or CURRENT_EXPERIMENT_EPOCH


def _get_role_routing(payload):
    trace = payload.get("process_trace") or {}
    source = payload.get("source_context") or {}
    return (trace.get("role_routing") or source.get("role_routing") or {})


def _get_primary_generator(payload):
    source = payload.get("source_context") or {}
    routing = _get_role_routing(payload)
    generator_role_id = payload.get("packet_role_id") or source.get("generator_role_id") or "genesis"
    role_meta = routing.get(generator_role_id) or routing.get("genesis") or {}
    provider = source.get("generator_provider") or role_meta.get("backend") or "internal"
    return {
        "role_id": generator_role_id,
        "provider": provider,
        "model": role_meta.get("model"),
        "shadow_only": not bool(payload.get("packet_primary", 1)),
        "artifact": payload.get("artifact"),
        "primary": bool(payload.get("packet_primary", 1)),
    }


def _build_role_packets(payload, scores=None):
    trace = payload.get("process_trace") or {}
    source = payload.get("source_context") or {}
    routing = _get_role_routing(payload)
    packets = {
        "generators": [],
        "evaluators": [],
    }

    primary_generator = _get_primary_generator(payload)
    packets["generators"].append(primary_generator)

    shadow_generators = source.get("shadow_generators") or trace.get("shadow_generators") or {}
    for role_id, info in shadow_generators.items():
        packets["generators"].append({
            "role_id": role_id,
            "provider": info.get("backend") or (routing.get(role_id) or {}).get("backend"),
            "model": info.get("model") or (routing.get(role_id) or {}).get("model"),
            "shadow_only": True,
            "artifact": info.get("artifact"),
            "artifact_contract_status": info.get("artifact_contract_status"),
            "primary": False,
        })

    score_rows = scores or []
    muse_payload = {k: payload.get(k) for k in ("novelty", "surprise", "value", "elaboration", "coherence", "composite", "actionability", "brand_fit", "factual_reliability", "constraints_met", "constraint_notes", "critique")}
    if any(v is not None for v in muse_payload.values()):
        score_rows = [{"scored_by": "muse", **muse_payload}, *score_rows]

    seen = set()
    for row in score_rows:
        role_id = row.get("scored_by")
        canonical_role_id = _canonical_role_id(role_id)
        if not role_id or canonical_role_id in seen:
            continue
        seen.add(canonical_role_id)
        role_meta = routing.get(canonical_role_id) or routing.get(role_id) or {}
        packets["evaluators"].append({
            "role_id": canonical_role_id,
            "provider": role_meta.get("backend"),
            "model": role_meta.get("model"),
            "shadow_only": canonical_role_id == "apollo",
            "scores": {
                "composite": row.get("composite"),
                "novelty": row.get("novelty"),
                "surprise": row.get("surprise"),
                "value": row.get("value"),
                "elaboration": row.get("elaboration"),
                "coherence": row.get("coherence"),
                "actionability": row.get("actionability"),
                "brand_fit": row.get("brand_fit"),
                "factual_reliability": row.get("factual_reliability"),
            },
            "constraints_met": row.get("constraints_met"),
            "critique": row.get("critique"),
        })
    return packets


def _attach_comparison_packets(records, threshold_seconds=2700):
    if not records:
        return records

    buckets = {}
    for payload in records:
        explicit_packet_id = payload.get("packet_id")
        if explicit_packet_id:
            key = ("explicit", explicit_packet_id)
        else:
            key = (
                payload.get("lane"),
                payload.get("prompt_family") or payload.get("family"),
                payload.get("condition"),
                payload.get("prompt"),
            )
        buckets.setdefault(key, []).append(payload)

    packet_index = {}
    for bucket in buckets.values():
        bucket.sort(key=lambda row: (_parse_created_at(row.get("created_at")) or datetime.min, row.get("id") or 0))
        cluster = []
        last_dt = None
        cluster_number = 0
        for payload in bucket:
            current_dt = _parse_created_at(payload.get("created_at"))
            if cluster and last_dt and current_dt and (current_dt - last_dt).total_seconds() > threshold_seconds:
                cluster_number += 1
                cluster = []
            if not cluster:
                cluster_number += 1
            cluster.append(payload)
            last_dt = current_dt or last_dt
            packet_key = _packet_key_for_payload(payload)
            packet_id = packet_key if payload.get("packet_id") else f"{packet_key}_{cluster_number}"
            packet_index[id(payload)] = packet_id

    grouped = {}
    for payload in records:
        packet_id = packet_index.get(id(payload))
        if not packet_id:
            continue
        grouped.setdefault(packet_id, []).append(payload)

    for packet_id, members in grouped.items():
        member_summaries = []
        role_ids = []
        for member in sorted(members, key=lambda row: row.get("id") or 0):
            generator = _get_primary_generator(member)
            role_ids.append(generator["role_id"])
            member_summaries.append({
                "experiment_id": member.get("id"),
                "role_id": generator["role_id"],
                "provider": generator.get("provider"),
                "status": member.get("status"),
                "promotion_status": member.get("promotion_status"),
                "composite": member.get("composite"),
            })
        for member in members:
            member["comparison_packet"] = {
                "packet_id": packet_id,
                "explicit": bool(member.get("packet_id")),
                "size": len(members),
                "role_ids": role_ids,
                "members": member_summaries,
            }
    return records


def _classify_creativity_overreach(row):
    gap = row.get("balance_gap")
    composite = row.get("composite")
    novelty = row.get("novelty")
    surprise = row.get("surprise")
    status = row.get("status")
    expressive_pressure = _mean([novelty, surprise])
    counterpart = row.get("balance_counterpart")
    pressure_gap = None if expressive_pressure is None or counterpart is None else expressive_pressure - counterpart

    if composite is None:
        return False
    if status == "constraint_fail" and expressive_pressure is not None and expressive_pressure >= 5.5:
        return True
    if row.get("lane") == "business":
        return pressure_gap is not None and pressure_gap > 0.25 and composite < 7.5
    if pressure_gap is not None and pressure_gap > 0.5 and composite < 7.0:
        return True
    return gap is not None and gap > 0.5 and composite < 7.0


def _build_policy_validation_summary(rows):
    overview = {
        "approved_pending_use": 0,
        "approved_in_trial": 0,
        "approved_validated": 0,
    }
    for row in rows:
        status = row.get("operational_status")
        if status in overview:
            overview[status] += 1
    return {
        "headline": f"{len(rows)} approved family defaults tracked.",
        "overview": overview,
        "rows": rows,
    }


def _build_protocol_reliability(rows):
    total = len(rows)
    if not total:
        return {
            "headline": "Protocol reliability tracked across 0 runs.",
            "overview": {},
            "protocol_versions": {},
        }

    def rate(pred):
        return sum(1 for row in rows if pred(row)) / total

    versions = {}
    for row in rows:
        trace = row.get("process_trace") or {}
        revision_status = trace.get("revision_status") or "unknown"
        versions[f"socratic_revision_{revision_status}"] = versions.get(f"socratic_revision_{revision_status}", 0) + 1

    def athena_gate(row):
        gates = ((row.get("process_trace") or {}).get("orchestration") or {}).get("gates", {})
        return gates.get("athena") or gates.get("hermes") or {}

    overview = {
        "selection_fallback_rate": rate(lambda row: "fallback" in ((row.get("process_trace") or {}).get("selection_status") or "")),
        "interlocutor_fallback_rate": rate(lambda row: "fallback" in ((row.get("process_trace") or {}).get("interlocutor_status") or "")),
        "athena_skip_rate": rate(lambda row: athena_gate(row).get("decision") == "skipped"),
        "athena_forced_rate": rate(lambda row: "forced_sample" in (athena_gate(row).get("reason") or "")),
    }
    return {
        "headline": f"Protocol reliability tracked across {total} runs.",
        "overview": overview,
        "protocol_versions": versions,
        "rows": rows,
    }


def _build_policy_effects(rows):
    if not rows:
        return {"headline": "Policy effects tracked across 0 lane/family/variant cells.", "overview": {}, "rows": []}

    grouped = {}
    for row in rows:
        key = (row.get("lane"), row.get("prompt_family"))
        grouped.setdefault(key, []).append(row)

    enriched = []
    for (lane, family), bucket in grouped.items():
        family_mean = _mean(item.get("mean_composite") for item in bucket) or 0.0
        baseline_keep = _mean(item.get("human_keep_rate") for item in bucket) or 0.0
        for row in bucket:
            clone = dict(row)
            clone["composite_lift"] = (row.get("mean_composite") or 0.0) - family_mean
            clone["human_keep_lift"] = (row.get("human_keep_rate") or 0.0) - baseline_keep
            enriched.append(clone)

    enriched.sort(key=lambda row: (row.get("composite_lift") or 0, row.get("trials") or 0), reverse=True)
    best_variant = max(enriched, key=lambda row: row.get("mean_composite") or float("-inf"))
    critique_sensitive = max(enriched, key=lambda row: row.get("critique_delta") or float("-inf"))
    return {
        "headline": f"Policy effects tracked across {len(rows)} lane/family/variant cells.",
        "overview": {
            "best_variant": best_variant,
            "critique_sensitive_variant": critique_sensitive,
        },
        "rows": enriched,
    }


def _build_policy_recommendations(family_metrics, policy_effect_rows, registry_rows, adoption_rows=None):
    adoption_rows = adoption_rows or []
    adoption_index = {
        (row.get("lane"), row.get("prompt_family"), row.get("policy_key"), row.get("approved_value")): row
        for row in adoption_rows
    }

    rows = []
    if registry_rows:
        for row in registry_rows:
            clone = dict(row)
            adoption = adoption_index.get(
                (clone.get("lane"), clone.get("prompt_family"), clone.get("policy_key"), clone.get("approved_value"))
            )
            if adoption:
                clone.update(adoption)
                clone["operational_status"] = "approved_validated" if (adoption.get("adopted_trials") or 0) >= 3 else "approved_in_trial"
            else:
                clone["operational_status"] = "approved_pending_use"
            rows.append(clone)
        return {"headline": f"{len(rows)} policy recommendations tracked.", "rows": rows}

    family_lookup = {(row.get("lane"), row.get("prompt_family")): row for row in family_metrics}
    grouped = {}
    for row in policy_effect_rows:
        grouped.setdefault((row.get("lane"), row.get("prompt_family")), []).append(row)

    for key, bucket in grouped.items():
        best = max(bucket, key=lambda row: ((row.get("composite_lift") or 0), (row.get("human_keep_lift") or 0)))
        family = family_lookup.get(key, {})
        rationale = (
            f"Recommend {best.get('prompt_policy_variant')} as the family default after outperforming peers "
            f"with composite lift {best.get('composite_lift', 0):+.2f} and human keep lift {best.get('human_keep_lift', 0):+.2f}."
        )
        rows.append({
            "lane": key[0],
            "prompt_family": key[1],
            "policy_key": "prompt_policy_default",
            "recommended_value": best.get("prompt_policy_variant"),
            "approval_status": "recommended",
            "rationale": rationale,
            "sample_size": family.get("sample_size"),
        })
    return {"headline": f"{len(rows)} policy recommendations tracked.", "rows": rows}


def _build_calibration_metrics(rows, verifier_rows, paired_rows, calibration_rows):
    if not rows:
        return {"overview": {}, "families": [], "headline": "No calibration metrics yet."}

    family_groups = {}
    for row in rows:
        family_groups.setdefault((row.get("lane") or "creative", row.get("prompt_family") or "unclassified"), []).append(row)

    family_metrics = []
    for (lane, family), bucket in family_groups.items():
        family_metrics.append({
            "lane": lane,
            "prompt_family": family,
            "sample_size": len(bucket),
            "overreach_rate": _mean(1.0 if _classify_creativity_overreach(row) else 0.0 for row in bucket),
            "novelty_gap": _mean(row.get("balance_gap") for row in bucket),
        })

    overview = {
        "tracked_runs": len(rows),
        "creativity_overreach_rate": _mean(1.0 if _classify_creativity_overreach(row) else 0.0 for row in rows),
        "unknown_constraint_rate": _mean(1.0 if row.get("constraints_met") is None else 0.0 for row in rows),
        "mean_novelty_gap": _mean(row.get("balance_gap") for row in rows),
        "human_agreement_rate": None,
    }
    headline = (
        f"Calibration readout across {len(rows)} scored runs: overreach {overview['creativity_overreach_rate']:.0%}, "
        f"unknown constraints {overview['unknown_constraint_rate']:.0%}."
    )
    return {"overview": overview, "families": family_metrics[:8], "headline": headline}


def _build_learning_snapshot(rows, paired_rows, verifier_rows, calibration_rows):
    if not rows:
        return {
            "headline": "No learning snapshot yet.",
            "improved": "Need more scored runs before calling anything improved.",
            "regressed": "No clear regression yet.",
            "still_noisy": "Sample size is too small for a stable judgment.",
            "next_move": "Run a small paired batch in one family and compare critique-on versus critique-off.",
        }

    recent = rows[:10]
    prior = rows[10:20]

    def summarize_window(bucket):
        known_constraints = [row.get("constraints_met") for row in bucket if row.get("constraints_met") is not None]
        return {
            "composite": _mean(row.get("composite") for row in bucket),
            "overreach": _mean(1.0 if _classify_creativity_overreach(row) else 0.0 for row in bucket),
            "constraint_pass": _mean(1.0 if value else 0.0 for value in known_constraints),
        }

    recent_summary = summarize_window(recent)
    prior_summary = summarize_window(prior)

    improved = "Recent runs are still too isolated to name a clear improvement."
    regressed = "No clear regression yet."
    still_noisy = "Human agreement is still too sparse to anchor the calibration story."

    if prior:
        overreach_delta = None
        if recent_summary["overreach"] is not None and prior_summary["overreach"] is not None:
            overreach_delta = recent_summary["overreach"] - prior_summary["overreach"]
        constraint_delta = None
        if recent_summary["constraint_pass"] is not None and prior_summary["constraint_pass"] is not None:
            constraint_delta = recent_summary["constraint_pass"] - prior_summary["constraint_pass"]
        composite_delta = None
        if recent_summary["composite"] is not None and prior_summary["composite"] is not None:
            composite_delta = recent_summary["composite"] - prior_summary["composite"]

        if constraint_delta is not None and constraint_delta > 0.15:
            improved = f"Constraint pass rate improved {constraint_delta:+.0%} in the latest window, which is the clearest sign of correction recognition."
        elif overreach_delta is not None and overreach_delta < -0.10:
            improved = f"Creativity overreach fell {abs(overreach_delta):.0%} in the latest window, suggesting slightly better calibration."
        elif composite_delta is not None and composite_delta > 0.25:
            improved = f"Mean composite improved {composite_delta:+.2f} in the latest window, though the cause still needs attribution."

        if overreach_delta is not None and overreach_delta > 0.10:
            regressed = f"Creativity overreach rose {overreach_delta:+.0%}, so the lab may still be rewarding flourish where it should be restrained."
        elif constraint_delta is not None and constraint_delta < -0.15:
            regressed = f"Constraint pass rate fell {constraint_delta:+.0%}, which suggests the correction loop is not stable yet."
        elif composite_delta is not None and composite_delta < -0.25:
            regressed = f"Mean composite fell {composite_delta:+.2f} in the latest window."

    if paired_rows:
        ambiguous = min(paired_rows, key=lambda row: abs(row.get("composite_delta") or 0))
        still_noisy = (
            f"Critique effect is still noisy in {ambiguous.get('prompt_family') or 'unclassified'} "
            f"({(ambiguous.get('composite_delta') or 0):+.2f}), so that family still needs tighter paired testing."
        )

    if calibration_rows:
        agreement = []
        for row in calibration_rows:
            worth_saving = row.get("worth_saving")
            muse_composite = row.get("muse_composite")
            if worth_saving is None or muse_composite is None:
                continue
            agreement.append(1.0 if (worth_saving >= 4) == (muse_composite >= 6.5) else 0.0)
        agreement_rate = _mean(agreement)
        if agreement_rate is not None and agreement_rate < 0.7:
            still_noisy = (
                f"Human versus MUSE save/discard agreement is only {agreement_rate:.0%}, "
                "so evaluator trust is still the main source of uncertainty."
            )

    return {
        "headline": "Learning snapshot updated.",
        "improved": improved,
        "regressed": regressed,
        "still_noisy": still_noisy,
        "next_move": "Run one paired family with critique-on versus critique-off and compare overreach, constraint recovery, and human save/discard.",
    }


def _build_hypothesis_summary(rows):
    grouped = {}
    for row in rows:
        key = row.get("hypothesis") or row.get("hypothesis_id")
        if not key:
            continue
        grouped.setdefault(key, []).append(row)
    summary = []
    for hypothesis_id, bucket in grouped.items():
        summary.append({
            "hypothesis": hypothesis_id,
            "lane": bucket[0].get("lane"),
            "sample_size": len(bucket),
            "mean_composite": _mean(row.get("composite") for row in bucket),
            "keep_rate": _mean(1.0 if row.get("status") in {"kept", "promoted"} else 0.0 for row in bucket),
        })
    summary.sort(key=lambda row: ((row.get("mean_composite") or 0), row.get("sample_size") or 0), reverse=True)
    return summary[:10]


def _build_creativity_balance(rows):
    grouped = {}
    for row in rows:
        lane = row.get("lane") or "creative"
        grouped.setdefault(lane, []).append(row)
    summaries = []
    for lane, bucket in grouped.items():
        novelty_pressure = _mean(
            value
            for row in bucket
            for value in (row.get("novelty"), row.get("surprise"))
            if value is not None
        )
        value_grounding = _mean(
            value
            for row in bucket
            for value in (row.get("value"), row.get("coherence"))
            if value is not None
        )
        summaries.append({
            "lane": lane,
            "sample_size": len(bucket),
            "novelty_pressure": novelty_pressure,
            "value_grounding": value_grounding,
            "balance_gap": None if novelty_pressure is None or value_grounding is None else novelty_pressure - value_grounding,
        })
    return sorted(summaries, key=lambda row: row["lane"])


def _build_paired_condition_summary(records):
    grouped = {}
    for row in records:
        packet = row.get("comparison_packet") or {}
        packet_id = packet.get("packet_id")
        if not packet_id:
            continue
        family = row.get("prompt_family") or row.get("family") or "unclassified"
        lane = row.get("lane") or "creative"
        condition = row.get("condition") or "unknown"
        grouped.setdefault((lane, family, condition), []).append(row)

    rows = []
    for (lane, family, condition), bucket in grouped.items():
        rows.append({
            "lane": lane,
            "prompt_family": family,
            "condition": condition,
            "sample_size": len(bucket),
            "mean_composite": _mean(row.get("composite") for row in bucket),
            "keep_rate": _mean(1.0 if row.get("status") in {"kept", "promoted"} else 0.0 for row in bucket),
        })
    rows.sort(key=lambda row: ((row.get("mean_composite") or 0), row.get("sample_size") or 0), reverse=True)
    return rows[:12]


def _build_business_creativity_tax(rows):
    business_rows = [row for row in rows if row.get("lane") == "business"]
    if not business_rows:
        return []
    grouped = {}
    for row in business_rows:
        family = row.get("prompt_family") or "unclassified"
        grouped.setdefault(family, []).append(row)
    tax_rows = []
    for family, bucket in grouped.items():
        novelty = _mean(row.get("novelty") for row in bucket)
        actionability = _mean(row.get("actionability") for row in bucket)
        factual = _mean(row.get("factual_reliability") for row in bucket)
        grounding = _mean(value for value in (actionability, factual) if value is not None)
        tax_rows.append({
            "prompt_family": family,
            "sample_size": len(bucket),
            "novelty": novelty,
            "grounding": grounding,
            "creativity_tax": None if novelty is None or grounding is None else novelty - grounding,
        })
    tax_rows.sort(key=lambda row: abs(row.get("creativity_tax") or 0), reverse=True)
    return tax_rows[:8]


def _build_champions(records):
    candidates = [row for row in records if row.get("composite") is not None]
    candidates.sort(key=lambda row: (row.get("composite") or 0, row.get("id") or 0), reverse=True)
    champions = []
    for row in candidates[:8]:
        champions.append({
            "experiment_id": row.get("id"),
            "lane": row.get("lane"),
            "family": row.get("prompt_family") or row.get("family"),
            "status": row.get("status"),
            "promotion_status": row.get("promotion_status"),
            "composite": row.get("composite"),
            "prompt_preview": (row.get("prompt") or "")[:160],
        })
    return champions


def _feedback_generator_role(row):
    return row.get("packet_role_id") or ((row.get("source_context") or {}).get("generator_role_id")) or "genesis"


def _group_reviewed_packets_for_feedback(records, calibration_rows):
    review_map = {
        row.get("packet_id"): row
        for row in calibration_rows
        if row.get("packet_id")
    }
    grouped = {}
    for row in records:
        packet = row.get("comparison_packet") or {}
        packet_id = packet.get("packet_id")
        if not packet_id or not packet.get("explicit") or packet.get("size", 0) < 2:
            continue
        if packet_id not in review_map:
            continue
        grouped.setdefault(packet_id, []).append(row)

    packets = []
    for packet_id, members in grouped.items():
        members = sorted(members, key=lambda row: row.get("id") or 0)
        review = review_map.get(packet_id)
        metadata = (review or {}).get("metadata") or {}
        packets.append({
            "packet_id": packet_id,
            "review": review,
            "metadata": metadata,
            "lane": members[0].get("lane") or "unknown",
            "family": members[0].get("prompt_family") or members[0].get("family") or "unclassified",
            "members": members,
        })
    return packets


def _top_counter_list(counter, *, limit=3):
    return [item for item, _count in counter.most_common(limit)]


def _format_generator_feedback_text(role_id, family, lane, summary):
    if not summary.get("reviewed_packets"):
        return None
    scope_bits = []
    if family:
        scope_bits.append(family.replace("_", " "))
    if lane:
        scope_bits.append(f"{lane} lane")
    scope_label = " / ".join(scope_bits) if scope_bits else "recent reviewed packets"
    lines = [
        f"Generator coaching for {role_id} from {summary.get('final_reviewed_packets', 0)} final human-reviewed packet(s) in {scope_label}.",
    ]
    if summary.get("top_flaws"):
        lines.append("Recurring failure tags when you lose: " + ", ".join(summary["top_flaws"]) + ".")
    if summary.get("top_strengths"):
        lines.append("Signals to preserve when you win: " + ", ".join(summary["top_strengths"]) + ".")
    if summary.get("same_writer_reviews"):
        lines.append(
            f"{summary['same_writer_reviews']} reviewed packet(s) were judged to sound like the same writer across generators; force clearer generator separation and avoid converging on the same prestige-literary solution."
        )
    if summary.get("top_pair_failures"):
        lines.append("Recurring pair-level failure tags: " + ", ".join(summary["top_pair_failures"]) + ".")
    if summary.get("flaw_excerpts"):
        lines.append("Representative losing excerpts: " + " | ".join(f'"{excerpt}"' for excerpt in summary["flaw_excerpts"][:2]) + ".")
    if summary.get("evaluator_cautions"):
        lines.append("Recent evaluator cautions: " + " | ".join(summary["evaluator_cautions"][:2]) + ".")
    if summary.get("low_confidence_reviews"):
        lines.append(f"{summary['low_confidence_reviews']} review(s) were saved with non-certain confidence, so treat this coaching as provisional.")
    if summary.get("revisit_later_reviews"):
        lines.append(f"{summary['revisit_later_reviews']} review(s) are still marked revisit-later, so treat this coaching as revisable.")
    lines.append("Use this as pressure against repeated failure modes, not as a template to imitate.")
    return "\n".join(lines)


def _summarize_generator_feedback(records, calibration_rows, *, role_id, family=None, lane=None):
    packets = _group_reviewed_packets_for_feedback(records, calibration_rows)
    reviewed_packets = 0
    final_reviewed_packets = 0
    revisit_later_reviews = 0
    low_confidence_reviews = 0
    win_count = 0
    loss_count = 0
    family_counts = Counter()
    family_losses = Counter()
    strength_tags = Counter()
    flaw_tags = Counter()
    pair_failure_tags = Counter()
    confidence_mix = Counter()
    distinctiveness_mix = Counter()
    same_writer_reviews = 0
    flaw_excerpts = []
    evaluator_cautions = []

    for packet in packets:
        if family and packet["family"] != family:
            continue
        if lane and packet["lane"] != lane:
            continue
        member = next((item for item in packet["members"] if _feedback_generator_role(item) == role_id), None)
        if not member:
            continue

        reviewed_packets += 1
        family_counts[packet["family"]] += 1
        metadata = packet.get("metadata") or {}
        verdict = metadata.get("review_verdict") or "preferred"
        confidence = metadata.get("review_confidence") or "unspecified"
        confidence_mix[confidence] += 1
        if confidence in {"tentative", "coin_flip"}:
            low_confidence_reviews += 1
        decision_state = metadata.get("review_decision_state") or "final"
        if decision_state == "revisit_later":
            revisit_later_reviews += 1
        else:
            final_reviewed_packets += 1
        pair_distinctiveness = metadata.get("pair_distinctiveness") or "unspecified"
        distinctiveness_mix[pair_distinctiveness] += 1
        if pair_distinctiveness == "same_writer":
            same_writer_reviews += 1
            pair_failure_tags.update((metadata.get("reason_tag_attribution") or {}).get("both") or [])

        preferred_id = (packet.get("review") or {}).get("preferred_experiment_id")
        if verdict != "preferred" or preferred_id is None:
            continue
        won = preferred_id == member.get("id")
        target_key = "winner" if won else "loser"
        attribution = metadata.get("reason_tag_attribution") or {}
        tags = attribution.get(target_key) or []
        evidence = metadata.get("reason_tag_evidence") or []
        excerpts = [
            item.get("excerpt")
            for item in evidence
            if item.get("target") == target_key and item.get("excerpt")
        ]
        critique = (member.get("critique") or "").strip()

        if won:
            win_count += 1
            strength_tags.update(tags)
        else:
            loss_count += 1
            family_losses[packet["family"]] += 1
            flaw_tags.update(tags)
            for excerpt in excerpts:
                if excerpt not in flaw_excerpts:
                    flaw_excerpts.append(excerpt)
            if critique and critique not in evaluator_cautions:
                evaluator_cautions.append(critique)

    focus_family = None
    if family_losses:
        focus_family = family_losses.most_common(1)[0][0]
    elif family_counts:
        focus_family = family_counts.most_common(1)[0][0]

    summary = {
        "role_id": role_id,
        "family": family,
        "lane": lane,
        "reviewed_packets": reviewed_packets,
        "final_reviewed_packets": final_reviewed_packets,
        "revisit_later_reviews": revisit_later_reviews,
        "low_confidence_reviews": low_confidence_reviews,
        "wins": win_count,
        "losses": loss_count,
        "confidence_mix": dict(confidence_mix),
        "distinctiveness_mix": dict(distinctiveness_mix),
        "same_writer_reviews": same_writer_reviews,
        "focus_family": focus_family,
        "top_strengths": _top_counter_list(strength_tags),
        "top_flaws": _top_counter_list(flaw_tags),
        "top_pair_failures": _top_counter_list(pair_failure_tags),
        "flaw_excerpts": flaw_excerpts[:3],
        "evaluator_cautions": evaluator_cautions[:3],
    }
    summary["prior_feedback"] = _format_generator_feedback_text(role_id, family, lane, summary)
    return summary


async def get_generator_feedback_for_task(role_id, *, family=None, lane=None, epoch=CURRENT_EXPERIMENT_EPOCH, limit=400):
    records = await get_recent_experiments(limit=limit, epoch=epoch)
    calibration_rows = await get_recent_calibration_reviews(limit=limit, epoch=epoch)
    scopes = []
    if family and lane:
        scopes.append(("family_lane", {"family": family, "lane": lane}))
    if lane:
        scopes.append(("lane", {"lane": lane}))
    if family and not lane:
        scopes.append(("family", {"family": family}))
    scopes.append(("global", {}))

    for scope_applied, kwargs in scopes:
        summary = _summarize_generator_feedback(records, calibration_rows, role_id=role_id, **kwargs)
        if summary.get("reviewed_packets"):
            summary["scope_applied"] = scope_applied
            return summary

    empty = _summarize_generator_feedback(records, calibration_rows, role_id=role_id, family=family, lane=lane)
    empty["scope_applied"] = "none"
    return empty


def _build_generator_learning_summary(records, calibration_rows):
    rows = []
    for role_id in ("genesis", "theron"):
        overall = _summarize_generator_feedback(records, calibration_rows, role_id=role_id)
        if not overall.get("reviewed_packets"):
            continue
        focus_family = overall.get("focus_family")
        focused = _summarize_generator_feedback(
            records,
            calibration_rows,
            role_id=role_id,
            family=focus_family,
        ) if focus_family else overall
        rows.append({
            "role_id": role_id,
            "reviewed_packets": overall.get("reviewed_packets", 0),
            "final_reviewed_packets": overall.get("final_reviewed_packets", 0),
            "revisit_later_reviews": overall.get("revisit_later_reviews", 0),
            "low_confidence_reviews": overall.get("low_confidence_reviews", 0),
            "wins": overall.get("wins", 0),
            "losses": overall.get("losses", 0),
            "same_writer_reviews": overall.get("same_writer_reviews", 0),
            "focus_family": focus_family,
            "top_strengths": overall.get("top_strengths", []),
            "top_flaws": overall.get("top_flaws", []),
            "top_pair_failures": overall.get("top_pair_failures", []),
            "focus_top_strengths": focused.get("top_strengths", []),
            "focus_top_flaws": focused.get("top_flaws", []),
            "focus_top_pair_failures": focused.get("top_pair_failures", []),
            "focus_scope_applied": focused.get("scope_applied") or ("family" if focus_family else "global"),
            "focus_reviewed_packets": focused.get("reviewed_packets", 0),
            "confidence_mix": overall.get("confidence_mix", {}),
            "distinctiveness_mix": overall.get("distinctiveness_mix", {}),
            "prior_feedback": focused.get("prior_feedback"),
        })
    if not rows:
        return {
            "headline": "No generator coaching yet because no explicit human-reviewed paired packets are in memory.",
            "rows": [],
        }
    return {
        "headline": "Genesis and Theron now have family-level coaching hooks from human-reviewed packet history, including pair-separation failures.",
        "rows": rows,
    }


def _build_human_calibration_summary(calibration_rows):
    if not calibration_rows:
        return {
            "headline": "No human calibration reviews yet.",
            "lane_summaries": [],
            "priority": None,
            "confidence_mix": {},
            "distinctiveness_mix": {},
            "revisit_later_count": 0,
            "low_confidence_count": 0,
            "reversal_count": 0,
            "same_writer_count": 0,
            "comparative_usefulness_score": None,
            "blind_candidates": [],
        }

    grouped = {}
    confidence_mix = Counter()
    distinctiveness_mix = Counter()
    revisit_later_count = 0
    low_confidence_count = 0
    reversal_count = 0
    usefulness_total = 0.0
    usefulness_count = 0
    for row in calibration_rows:
        grouped.setdefault(row.get("lane") or "unknown", []).append(row)
        metadata = row.get("metadata") or {}
        confidence = metadata.get("review_confidence") or "unspecified"
        confidence_mix[confidence] += 1
        if confidence in {"tentative", "coin_flip"}:
            low_confidence_count += 1
        if metadata.get("review_decision_state") == "revisit_later":
            revisit_later_count += 1
        distinctiveness = metadata.get("pair_distinctiveness") or "unspecified"
        distinctiveness_mix[distinctiveness] += 1
        if distinctiveness in {"clearly_distinct", "somewhat_distinct", "same_writer"}:
            usefulness_count += 1
            usefulness_total += {
                "clearly_distinct": 1.0,
                "somewhat_distinct": 0.5,
                "same_writer": 0.0,
            }[distinctiveness]
        reversal_count += int(metadata.get("review_reversal_count") or 0)

    lane_summaries = []
    for lane, bucket in grouped.items():
        lane_summaries.append({
            "lane": lane,
            "sample_size": len(bucket),
            "mean_muse_composite": _mean(row.get("muse_composite") for row in bucket),
        })
    lane_summaries.sort(key=lambda row: row["lane"])

    return {
        "headline": f"{len(calibration_rows)} human calibration reviews recorded.",
        "lane_summaries": lane_summaries,
        "priority": max(lane_summaries, key=lambda row: row.get("sample_size") or 0)["lane"] if lane_summaries else None,
        "confidence_mix": dict(confidence_mix),
        "distinctiveness_mix": dict(distinctiveness_mix),
        "revisit_later_count": revisit_later_count,
        "low_confidence_count": low_confidence_count,
        "reversal_count": reversal_count,
        "same_writer_count": distinctiveness_mix.get("same_writer", 0),
        "comparative_usefulness_score": None if not usefulness_count else usefulness_total / usefulness_count,
    }


def _build_constraint_verifier_summary(verifier_rows):
    if not verifier_rows:
        return {"headline": "No verifier-tracked runs yet.", "totals": {}, "families": []}
    totals = {
        "runs_with_verifier": len(verifier_rows),
        "verification_pass_rate": _mean(1.0 if ((row.get("process_trace") or {}).get("verification_status") == "passed") else 0.0 for row in verifier_rows),
        "repair_attempt_rate": _mean(1.0 if ((row.get("process_trace") or {}).get("verifier_checks") or []) else 0.0 for row in verifier_rows),
    }
    grouped = {}
    for row in verifier_rows:
        family = row.get("prompt_family") or row.get("family") or "unclassified"
        grouped.setdefault(family, []).append(row)
    families = []
    for family, bucket in grouped.items():
        families.append({
            "prompt_family": family,
            "sample_size": len(bucket),
            "verification_pass_rate": _mean(1.0 if ((row.get("process_trace") or {}).get("verification_status") == "passed") else 0.0 for row in bucket),
        })
    families.sort(key=lambda row: (row.get("sample_size") or 0), reverse=True)
    return {
        "headline": f"Constraint verifier tracked across {len(verifier_rows)} runs.",
        "totals": totals,
        "families": families[:8],
    }


def _build_evaluator_diagnostics(records, disagreement_rows, calibration_rows):
    scored = [row for row in records if row.get("composite") is not None]
    warnings = []
    disagreement_rate = None
    paired_packets = [row for row in records if (row.get("comparison_packet") or {}).get("size", 0) > 1]
    if paired_packets:
        packet_ids = {row.get("comparison_packet", {}).get("packet_id") for row in paired_packets}
        disagreement_rate = len(disagreement_rows) / len(packet_ids) if packet_ids else None
        if disagreement_rate is not None and disagreement_rate > 0.35:
            warnings.append("Evaluator disagreement is high enough that human calibration should stay active.")
    if calibration_rows and len(calibration_rows) < 5:
        warnings.append("Human calibration sample is still small relative to live disagreement volume.")
    if not warnings:
        warnings.append("Diagnostics are populated from live runs; keep comparing evaluator behavior against human review.")
    return {
        "headline": f"Evaluator diagnostics drawn from {len(scored)} scored runs.",
        "warnings": warnings,
        "disagreement_rate": disagreement_rate,
        "human_reviews": len(calibration_rows),
    }


@asynccontextmanager
async def connect():
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    await conn.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}")
    await conn.execute(f"PRAGMA synchronous = {SQLITE_SYNCHRONOUS_MODE}")
    try:
        yield conn
    finally:
        await conn.close()


_db_initialized = False
_initialized_db_path = None


async def init_db():
    global _db_initialized, _initialized_db_path
    current_db_path = str(DB_PATH)
    if _db_initialized and _initialized_db_path == current_db_path:
        return
    async with connect() as conn:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lab_state (
                id INTEGER PRIMARY KEY,
                running INTEGER NOT NULL DEFAULT 0,
                total_experiments INTEGER NOT NULL DEFAULT 0,
                kept INTEGER NOT NULL DEFAULT 0,
                discarded INTEGER NOT NULL DEFAULT 0,
                invalid INTEGER NOT NULL DEFAULT 0,
                promoted INTEGER NOT NULL DEFAULT 0,
                best_score REAL,
                total_cost REAL NOT NULL DEFAULT 0,
                cost_cap REAL NOT NULL DEFAULT 50,
                consecutive_discards INTEGER NOT NULL DEFAULT 0,
                current_lane TEXT,
                current_track TEXT,
                current_experiment_id INTEGER,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane TEXT,
                track TEXT,
                iteration INTEGER,
                epoch TEXT,
                creativity_type TEXT,
                prompt TEXT,
                prompt_family TEXT,
                constraints TEXT,
                condition TEXT,
                status TEXT,
                promotion_status TEXT,
                hypothesis_id TEXT,
                parse_failure INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                error_traceback TEXT,
                generation_protocol TEXT DEFAULT 'one_shot',
                packet_id TEXT,
                packet_role_id TEXT,
                packet_primary INTEGER NOT NULL DEFAULT 1,
                primary_rule_id INTEGER REFERENCES prompt_rules(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                content TEXT,
                process_trace TEXT,
                source_context TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id INTEGER NOT NULL,
                experiment_id INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                scored_by TEXT NOT NULL,
                novelty REAL,
                surprise REAL,
                value REAL,
                elaboration REAL,
                coherence REAL,
                composite REAL,
                actionability REAL,
                brand_fit REAL,
                factual_reliability REAL,
                constraints_met INTEGER,
                constraint_notes TEXT,
                critique TEXT,
                parse_failure INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS policy_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane TEXT NOT NULL,
                prompt_family TEXT NOT NULL,
                policy_key TEXT NOT NULL,
                recommended_value TEXT,
                approved_value TEXT,
                approval_status TEXT,
                operational_status TEXT,
                rationale TEXT,
                reviewer_note TEXT,
                source TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(lane, prompt_family, policy_key)
            );

            CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_hash TEXT UNIQUE,
                prompt_family TEXT,
                prompt_text TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS hypotheses (
                id TEXT PRIMARY KEY,
                description TEXT,
                lane TEXT
            );

            CREATE TABLE IF NOT EXISTS reference_packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane TEXT,
                prompt_family TEXT,
                title TEXT,
                source_type TEXT DEFAULT 'manual',
                task_definition TEXT,
                live_examples TEXT,
                failure_modes TEXT,
                expected_tradeoffs TEXT,
                constraint_patterns TEXT,
                paired_test_matrix TEXT,
                notes TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS council_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS council_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                council_id INTEGER REFERENCES council_history(id) ON DELETE SET NULL,
                action_type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                lane TEXT,
                prompt_family TEXT,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(action_type, title)
            );

            CREATE TABLE IF NOT EXISTS prompt_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_key TEXT NOT NULL UNIQUE,
                scope_claim TEXT NOT NULL DEFAULT 'family_specific',
                status TEXT NOT NULL DEFAULT 'candidate',
                characterization TEXT,
                current_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS rule_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER NOT NULL REFERENCES prompt_rules(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                title TEXT NOT NULL,
                rule_type TEXT,
                rule_text TEXT,
                rationale TEXT,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rule_id, version)
            );

            CREATE TABLE IF NOT EXISTS rule_evidence_slices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER NOT NULL REFERENCES prompt_rules(id) ON DELETE CASCADE,
                rule_version INTEGER NOT NULL DEFAULT 1,
                lane TEXT,
                prompt_family TEXT,
                model_family TEXT,
                panel_version TEXT,
                experiment_type TEXT NOT NULL,
                packet_id TEXT,
                experiment_id INTEGER REFERENCES experiments(id) ON DELETE SET NULL,
                compared_experiment_id INTEGER REFERENCES experiments(id) ON DELETE SET NULL,
                human_signal TEXT NOT NULL DEFAULT 'unreviewed',
                human_signal_attribution_method TEXT NOT NULL DEFAULT 'uniform',
                evaluator_signal TEXT NOT NULL DEFAULT 'unreviewed',
                evaluator_margin REAL,
                metadata TEXT,
                observed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rule_id, rule_version, experiment_type, packet_id, experiment_id, compared_experiment_id)
            );

            CREATE TABLE IF NOT EXISTS comparison_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_id TEXT NOT NULL UNIQUE,
                preferred_experiment_id INTEGER REFERENCES experiments(id) ON DELETE CASCADE,
                rationale TEXT,
                reviewer TEXT DEFAULT 'human_operator',
                review_channel TEXT,
                outbound_message_id TEXT,
                inbound_message_id TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS packet_resolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_id TEXT NOT NULL UNIQUE,
                resolution TEXT NOT NULL,
                rationale TEXT,
                reviewer TEXT DEFAULT 'human_operator',
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await conn.execute("INSERT OR IGNORE INTO lab_state (id) VALUES (1)")
        columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(policy_registry)")).fetchall()]
        if "operational_status" not in columns:
            await conn.execute("ALTER TABLE policy_registry ADD COLUMN operational_status TEXT")
        experiment_columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(experiments)")).fetchall()]
        if "epoch" not in experiment_columns:
            await conn.execute("ALTER TABLE experiments ADD COLUMN epoch TEXT")
        await conn.execute(
            "UPDATE experiments SET epoch = ? WHERE epoch IS NULL OR TRIM(epoch) = ''",
            (LEGACY_EXPERIMENT_EPOCH,),
        )
        if "packet_id" not in experiment_columns:
            await conn.execute("ALTER TABLE experiments ADD COLUMN packet_id TEXT")
        if "packet_role_id" not in experiment_columns:
            await conn.execute("ALTER TABLE experiments ADD COLUMN packet_role_id TEXT")
        if "packet_primary" not in experiment_columns:
            await conn.execute("ALTER TABLE experiments ADD COLUMN packet_primary INTEGER NOT NULL DEFAULT 1")
        if "primary_rule_id" not in experiment_columns:
            await conn.execute("ALTER TABLE experiments ADD COLUMN primary_rule_id INTEGER")
        if "rule_id" in experiment_columns and "primary_rule_id" in [row["name"] for row in await (await conn.execute("PRAGMA table_info(experiments)")).fetchall()]:
            await conn.execute("UPDATE experiments SET primary_rule_id = COALESCE(primary_rule_id, rule_id)")
        evidence_columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(rule_evidence_slices)")).fetchall()]
        if "panel_version" not in evidence_columns:
            await conn.execute("ALTER TABLE rule_evidence_slices ADD COLUMN panel_version TEXT")
        if "human_signal_attribution_method" not in evidence_columns:
            await conn.execute("ALTER TABLE rule_evidence_slices ADD COLUMN human_signal_attribution_method TEXT NOT NULL DEFAULT 'uniform'")
        prompt_rule_columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(prompt_rules)")).fetchall()]
        if "characterization" not in prompt_rule_columns:
            await conn.execute("ALTER TABLE prompt_rules ADD COLUMN characterization TEXT")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_experiments_primary_rule_id ON experiments(primary_rule_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_rule_evidence_rule ON rule_evidence_slices(rule_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_rule_evidence_scope ON rule_evidence_slices(lane, prompt_family, model_family)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_rule_evidence_panel ON rule_evidence_slices(panel_version)")
        council_rule_rows = await (await conn.execute(
            """
            SELECT id, council_id, action_type, title, status, lane, prompt_family, payload, created_at, updated_at
            FROM council_actions
            WHERE action_type = 'prompt_diagnosis_refinement'
            """
        )).fetchall()
        for row in council_rule_rows:
            action = dict(row)
            action["payload"] = _safe_json_loads(action.get("payload"), {})
            rule = _rule_payload_from_council_action(action)
            rule_key = rule["rule_key"]
            await conn.execute(
                """
                INSERT INTO prompt_rules (rule_key, scope_claim, status, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(rule_key) DO NOTHING
                """,
                (
                    rule_key,
                    _normalize_rule_scope_claim(rule.get("scope_claim"), lane=action.get("lane"), prompt_family=action.get("prompt_family")),
                    _normalize_rule_status(rule.get("status")),
                ),
            )
            prompt_rule = await (await conn.execute(
                "SELECT id, current_version FROM prompt_rules WHERE rule_key = ?",
                (rule_key,),
            )).fetchone()
            if not prompt_rule:
                continue
            existing_version = await (await conn.execute(
                "SELECT id FROM rule_versions WHERE rule_id = ? AND version = ?",
                (prompt_rule["id"], prompt_rule["current_version"]),
            )).fetchone()
            if existing_version:
                continue
            await conn.execute(
                """
                INSERT INTO rule_versions (rule_id, version, title, rule_type, rule_text, rationale, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_rule["id"],
                    prompt_rule["current_version"],
                    rule["title"],
                    rule.get("rule_type"),
                    rule.get("rule_text"),
                    rule.get("rationale"),
                    json.dumps(rule.get("payload") or {}),
                ),
            )
        comparison_columns = await (await conn.execute("PRAGMA table_info(comparison_reviews)")).fetchall()
        preferred_review_column = next((row for row in comparison_columns if row["name"] == "preferred_experiment_id"), None)
        if preferred_review_column and preferred_review_column["notnull"]:
            await conn.executescript(
                """
                CREATE TABLE comparison_reviews_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_id TEXT NOT NULL UNIQUE,
                    preferred_experiment_id INTEGER REFERENCES experiments(id) ON DELETE CASCADE,
                    rationale TEXT,
                    reviewer TEXT DEFAULT 'human_operator',
                    review_channel TEXT,
                    outbound_message_id TEXT,
                    inbound_message_id TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO comparison_reviews_new (
                    id, packet_id, preferred_experiment_id, rationale, reviewer, review_channel,
                    outbound_message_id, inbound_message_id, metadata, created_at, updated_at
                )
                SELECT
                    id, packet_id, preferred_experiment_id, rationale, reviewer, review_channel,
                    outbound_message_id, inbound_message_id, metadata, created_at, updated_at
                FROM comparison_reviews;
                DROP TABLE comparison_reviews;
                ALTER TABLE comparison_reviews_new RENAME TO comparison_reviews;
                """
            )
        ref_columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(reference_packs)")).fetchall()]
        if "lane" not in ref_columns and "payload" in ref_columns:
            # Migrate old single-payload schema to structured columns
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN lane TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN prompt_family TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN source_type TEXT DEFAULT 'manual'")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN task_definition TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN live_examples TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN failure_modes TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN expected_tradeoffs TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN constraint_patterns TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN paired_test_matrix TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN notes TEXT")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN status TEXT DEFAULT 'draft'")
            await conn.execute("ALTER TABLE reference_packs ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP")
        await conn.commit()
        _db_initialized = True
        _initialized_db_path = current_db_path


async def increment_experiment_counters(*, keep, status, composite, cost, consecutive_discards=0, max_consecutive_discards=10):
    """Atomically increment experiment counters in a single UPDATE to avoid read-modify-write races."""
    async with connect() as conn:
        await conn.execute(
            """
            UPDATE lab_state SET
                total_experiments = total_experiments + 1,
                kept = kept + ?,
                discarded = discarded + ?,
                promoted = promoted + ?,
                best_score = CASE
                    WHEN ? IS NOT NULL AND (best_score IS NULL OR ? > best_score) THEN ?
                    ELSE best_score
                END,
                total_cost = total_cost + ?,
                consecutive_discards = CASE WHEN ? THEN 0 ELSE MIN(?, COALESCE(consecutive_discards, 0) + 1) END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (
                1 if status in ("kept", "promoted") else 0,
                1 if status in ("discard", "constraint_fail", "invalid") else 0,
                1 if status == "promoted" else 0,
                composite, composite, composite,
                cost or 0.0,
                1 if keep else 0,
                max_consecutive_discards,
            ),
        )
        await conn.commit()


async def get_state():
    await init_db()
    async with connect() as conn:
        row = await (await conn.execute("SELECT * FROM lab_state WHERE id = 1")).fetchone()
        return dict(row)


async def update_state(**fields):
    await init_db()
    if not fields:
        return await get_state()
    fields["updated_at"] = "CURRENT_TIMESTAMP"
    assignments = []
    values = []
    for key, value in fields.items():
        if value == "CURRENT_TIMESTAMP":
            assignments.append(f"{key} = CURRENT_TIMESTAMP")
        else:
            assignments.append(f"{key} = ?")
            values.append(value)
    async with connect() as conn:
        await conn.execute(f"UPDATE lab_state SET {', '.join(assignments)} WHERE id = 1", values)
        await conn.commit()
    return await get_state()


async def insert_hypothesis(hypothesis_id, description, lane):
    await init_db()
    async with connect() as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO hypotheses (id, description, lane) VALUES (?, ?, ?)",
            (hypothesis_id, description, lane),
        )
        await conn.commit()


async def store_prompt_version(prompt_hash, prompt_family, prompt_text):
    await init_db()
    async with connect() as conn:
        columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(prompt_versions)")).fetchall()]
        if {"prompt_hash", "prompt_family", "prompt_text"}.issubset(columns):
            await conn.execute(
                "INSERT OR REPLACE INTO prompt_versions (prompt_hash, prompt_family, prompt_text) VALUES (?, ?, ?)",
                (prompt_hash, prompt_family, prompt_text),
            )
        else:
            await conn.execute(
                "INSERT OR REPLACE INTO prompt_versions (hash, role, content) VALUES (?, ?, ?)",
                (prompt_hash, prompt_family, prompt_text),
            )
        await conn.commit()


async def create_experiment(task, status="running", iteration=None):
    await init_db()
    state = await get_state()
    async with connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO experiments (
                lane, track, iteration, epoch, creativity_type, prompt, prompt_family, constraints,
                condition, status, promotion_status, hypothesis_id, generation_protocol,
                packet_id, packet_role_id, packet_primary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.get("lane"),
                task.get("track"),
                iteration if iteration is not None else (state.get("total_experiments") or 0) + 1,
                _normalize_epoch(task.get("epoch")),
                task.get("creativity_type"),
                task.get("prompt"),
                task.get("family"),
                json.dumps(task.get("constraints") or []),
                task.get("condition"),
                status,
                "candidate",
                task.get("hypothesis"),
                task.get("generation_protocol", "socratic"),
                task.get("packet_id"),
                task.get("packet_role_id"),
                1 if task.get("packet_primary", True) else 0,
            ),
        )
        await conn.commit()
        return cur.lastrowid


async def finalize_experiment(experiment_id, *, status, promotion_status="candidate", parse_failure=False, cost=0.0, error_traceback=None):
    async with connect() as conn:
        await conn.execute(
            """
            UPDATE experiments
            SET status = ?, promotion_status = ?, parse_failure = ?, error_traceback = ?
            WHERE id = ?
            """,
            (status, promotion_status, int(bool(parse_failure)), error_traceback, experiment_id),
        )
        await conn.commit()


async def insert_artifact(experiment_id, artifact, process_trace=None, source_context=None):
    async with connect() as conn:
        existing = await (await conn.execute("SELECT id FROM artifacts WHERE experiment_id = ?", (experiment_id,))).fetchone()
        if existing:
            artifact_id = existing["id"]
            await conn.execute(
                "UPDATE artifacts SET content = ?, process_trace = ?, source_context = ? WHERE experiment_id = ?",
                (artifact, json.dumps(process_trace or {}), json.dumps(source_context or {}), experiment_id),
            )
        else:
            cur = await conn.execute(
                "INSERT INTO artifacts (experiment_id, content, process_trace, source_context) VALUES (?, ?, ?, ?)",
                (experiment_id, artifact, json.dumps(process_trace or {}), json.dumps(source_context or {})),
            )
            artifact_id = cur.lastrowid
        await conn.commit()
        return artifact_id


async def update_artifact_process_trace(experiment_id, process_trace):
    async with connect() as conn:
        await conn.execute(
            "UPDATE artifacts SET process_trace = ? WHERE experiment_id = ?",
            (json.dumps(process_trace or {}), experiment_id),
        )
        await conn.commit()


async def update_artifact_source_context(experiment_id, source_context):
    async with connect() as conn:
        await conn.execute(
            "UPDATE artifacts SET source_context = ? WHERE experiment_id = ?",
            (json.dumps(source_context or {}), experiment_id),
        )
        await conn.commit()


async def insert_score(experiment_id, scored_by, payload, cost=0.0, parse_failure=False):
    async with connect() as conn:
        artifact_row = await (await conn.execute("SELECT id FROM artifacts WHERE experiment_id = ? ORDER BY id DESC LIMIT 1", (experiment_id,))).fetchone()
        artifact_id = artifact_row["id"] if artifact_row else 0
        await conn.execute(
            """
            INSERT INTO scores (
                artifact_id, experiment_id, novelty, surprise, value, elaboration, coherence, composite,
                actionability, brand_fit, factual_reliability, constraints_met, constraint_notes, critique,
                scored_by, parse_failure
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                experiment_id,
                payload.get("novelty"),
                payload.get("surprise"),
                payload.get("value"),
                payload.get("elaboration"),
                payload.get("coherence"),
                payload.get("composite"),
                payload.get("actionability"),
                payload.get("brand_fit"),
                payload.get("factual_reliability"),
                None if payload.get("constraints_met") is None else int(bool(payload.get("constraints_met"))),
                payload.get("constraint_notes"),
                payload.get("critique"),
                scored_by,
                int(bool(parse_failure)),
            ),
        )
        await conn.commit()


async def get_holdout_scores(experiment_id):
    async with connect() as conn:
        rows = await (await conn.execute(
            "SELECT * FROM scores WHERE experiment_id = ? AND scored_by IN ('critic_holdout', 'athena', 'hermes', 'apollo', 'hermes_external') ORDER BY id",
            (experiment_id,),
        )).fetchall()
        return [dict(row) for row in rows]


async def get_experiment_by_id(experiment_id):
    async with connect() as conn:
        row = await (await conn.execute(
            """
            SELECT e.*, a.content, a.process_trace, a.source_context
            FROM experiments e
            LEFT JOIN artifacts a ON a.experiment_id = e.id
            WHERE e.id = ?
            """,
            (experiment_id,),
        )).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["epoch"] = _normalize_epoch(payload.get("epoch"))
        payload["artifact"] = payload.pop("content", payload.get("artifact"))
        payload["family"] = payload.get("prompt_family")
        payload["hypothesis"] = payload.get("hypothesis_id")
        payload["constraints"] = _safe_json_loads(payload.get("constraints"), [])
        payload["process_trace"] = _safe_json_loads(payload.get("process_trace"), {})
        payload["source_context"] = _safe_json_loads(payload.get("source_context"), {})
        holdout_scores = await get_holdout_scores(experiment_id)
        payload["holdout_scores"] = holdout_scores
        payload["role_packets"] = _build_role_packets(payload, holdout_scores)
        siblings = await get_recent_experiments(limit=200)
        packet = next((row.get("comparison_packet") for row in siblings if row.get("id") == experiment_id), None)
        if packet:
            payload["comparison_packet"] = packet
            payload["comparison_siblings"] = [
                row for row in siblings
                if row.get("comparison_packet", {}).get("packet_id") == packet.get("packet_id") and row.get("id") != experiment_id
            ]
            payload["comparison_review"] = await get_comparison_review(packet.get("packet_id"))
        else:
            payload["comparison_packet"] = None
            payload["comparison_siblings"] = []
            payload["comparison_review"] = None
        return payload


async def get_experiment_summaries(experiment_ids):
    if not experiment_ids:
        return []
    placeholders = ",".join("?" for _ in experiment_ids)
    async with connect() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT
                e.id,
                e.status,
                e.promotion_status,
                e.packet_role_id,
                a.source_context,
                s.composite
            FROM experiments e
            LEFT JOIN artifacts a ON a.experiment_id = e.id
            LEFT JOIN scores s ON s.experiment_id = e.id AND s.scored_by = 'muse'
            WHERE e.id IN ({placeholders})
            """,
            experiment_ids,
        )).fetchall()
    records = []
    for row in rows:
        payload = dict(row)
        payload["source_context"] = _safe_json_loads(payload.get("source_context"), {})
        records.append(payload)
    return records


async def get_comparison_review(packet_id):
    if not packet_id:
        return None
    async with connect() as conn:
        row = await (await conn.execute(
            "SELECT * FROM comparison_reviews WHERE packet_id = ?",
            (packet_id,),
        )).fetchone()
        if not row:
            return None
        return _attach_review_metadata_stats({
            **dict(row),
            "metadata": _safe_json_loads(dict(row).get("metadata"), {}),
        })


async def get_packet_resolution(packet_id):
    if not packet_id:
        return None
    async with connect() as conn:
        row = await (await conn.execute(
            "SELECT * FROM packet_resolutions WHERE packet_id = ?",
            (packet_id,),
        )).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["metadata"] = _safe_json_loads(payload.get("metadata"), {})
        return payload


async def get_packet_resolutions_map(packet_ids):
    if not packet_ids:
        return {}
    placeholders = ",".join("?" for _ in packet_ids)
    async with connect() as conn:
        rows = await (await conn.execute(
            f"SELECT * FROM packet_resolutions WHERE packet_id IN ({placeholders})",
            tuple(packet_ids),
        )).fetchall()
    resolutions = {}
    for row in rows:
        payload = dict(row)
        payload["metadata"] = _safe_json_loads(payload.get("metadata"), {})
        resolutions[payload["packet_id"]] = payload
    return resolutions


async def save_packet_resolution(
    packet_id,
    *,
    resolution,
    rationale,
    reviewer="human_operator",
    metadata=None,
):
    await init_db()
    normalized_resolution = str(resolution or "").strip().lower()
    if normalized_resolution not in PACKET_RESOLUTION_TYPES:
        raise ValueError(f"invalid packet resolution: {resolution}")
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO packet_resolutions (
                packet_id, resolution, rationale, reviewer, metadata, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(packet_id) DO UPDATE SET
                resolution = excluded.resolution,
                rationale = excluded.rationale,
                reviewer = excluded.reviewer,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                packet_id,
                normalized_resolution,
                rationale,
                reviewer,
                json.dumps(metadata or {}),
            ),
        )
        if normalized_resolution == "discarded_failure":
            await conn.execute(
                """
                UPDATE experiments
                SET status = CASE WHEN status = 'running' THEN 'error' ELSE status END,
                    error_traceback = CASE
                        WHEN status = 'running' THEN ?
                        ELSE error_traceback
                    END
                WHERE packet_id = ?
                """,
                ("Packet discarded as stalled failure by operator.", packet_id),
            )
        await conn.commit()
    return await get_packet_resolution(packet_id)


async def list_packet_resolutions(limit=20, *, epoch=CURRENT_EXPERIMENT_EPOCH):
    await init_db()
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT
                pr.packet_id,
                pr.resolution,
                pr.rationale,
                pr.reviewer,
                pr.metadata,
                pr.created_at,
                pr.updated_at,
                pm.lane,
                pm.prompt_family,
                pm.condition,
                pm.prompt
            FROM packet_resolutions pr
            LEFT JOIN (
                SELECT
                    packet_id,
                    MIN(lane) AS lane,
                    MIN(epoch) AS epoch,
                    MIN(prompt_family) AS prompt_family,
                    MIN(condition) AS condition,
                    MIN(prompt) AS prompt
                FROM experiments
                WHERE packet_id IS NOT NULL
                GROUP BY packet_id
            ) pm ON pm.packet_id = pr.packet_id
            WHERE COALESCE(pm.epoch, ?) = ?
            ORDER BY pr.updated_at DESC
            LIMIT ?
            """,
            (epoch, epoch, limit),
        )).fetchall()
    payloads = []
    for row in rows:
        payload = dict(row)
        payload["metadata"] = _safe_json_loads(payload.get("metadata"), {})
        payloads.append(payload)
    return payloads


async def get_recent_calibration_reviews(limit=50, *, epoch=None):
    await init_db()
    filters = []
    params = []
    if epoch:
        filters.append("COALESCE(e.epoch, pm.epoch) = ?")
        params.append(epoch)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    async with connect() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT
                cr.packet_id,
                cr.preferred_experiment_id,
                cr.rationale,
                cr.reviewer,
                cr.review_channel,
                cr.metadata,
                cr.created_at,
                cr.updated_at,
                COALESCE(e.lane, pm.lane) AS lane,
                COALESCE(e.epoch, pm.epoch) AS epoch,
                COALESCE(e.prompt_family, pm.prompt_family) AS prompt_family,
                s.composite AS muse_composite
            FROM comparison_reviews cr
            LEFT JOIN experiments e ON e.id = cr.preferred_experiment_id
            LEFT JOIN (
                SELECT packet_id, MIN(lane) AS lane, MIN(epoch) AS epoch, MIN(prompt_family) AS prompt_family
                FROM experiments
                WHERE packet_id IS NOT NULL
                GROUP BY packet_id
            ) pm ON pm.packet_id = cr.packet_id
            LEFT JOIN scores s ON s.experiment_id = e.id AND s.scored_by = 'muse'
            {where_clause}
            ORDER BY cr.id DESC
            LIMIT ?
            """,
            (*params, limit),
        )).fetchall()
        payloads = []
        for row in rows:
            payload = dict(row)
            payload["epoch"] = _normalize_epoch(payload.get("epoch"))
            payload["metadata"] = _safe_json_loads(payload.get("metadata"), {})
            payloads.append(_attach_review_metadata_stats(payload))
        return payloads


async def save_comparison_review(
    packet_id,
    *,
    preferred_experiment_id,
    rationale,
    reviewer="human_operator",
    review_channel=None,
    outbound_message_id=None,
    inbound_message_id=None,
    metadata=None,
):
    await init_db()
    existing_review = await get_comparison_review(packet_id)
    normalized_metadata = _normalize_review_metadata(metadata or {})
    if existing_review and _reviews_meaningfully_differ(
        existing_review,
        {
            "preferred_experiment_id": preferred_experiment_id,
            "rationale": rationale,
            "metadata": normalized_metadata,
        },
    ):
        history = list((existing_review.get("metadata") or {}).get("review_revision_history") or [])
        history.append(_review_snapshot(existing_review))
        normalized_metadata["review_revision_history"] = history
    normalized_metadata = _normalize_review_metadata(normalized_metadata)
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO comparison_reviews (
                packet_id, preferred_experiment_id, rationale, reviewer, review_channel,
                outbound_message_id, inbound_message_id, metadata, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(packet_id) DO UPDATE SET
                preferred_experiment_id = excluded.preferred_experiment_id,
                rationale = excluded.rationale,
                reviewer = excluded.reviewer,
                review_channel = excluded.review_channel,
                outbound_message_id = excluded.outbound_message_id,
                inbound_message_id = excluded.inbound_message_id,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                packet_id,
                preferred_experiment_id,
                rationale,
                reviewer,
                review_channel,
                outbound_message_id,
                inbound_message_id,
                json.dumps(normalized_metadata),
            ),
        )
        await conn.commit()
    review = await get_comparison_review(packet_id)
    await backfill_rule_evidence_human_signal(packet_id, review)
    return review


async def get_recent_experiments(limit=40, *, epoch=None):
    filters = []
    params = []
    if epoch:
        filters.append("e.epoch = ?")
        params.append(epoch)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    async with connect() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT
                e.*,
                a.content,
                a.process_trace,
                a.source_context,
                s.composite,
                s.novelty,
                s.surprise,
                s.value,
                s.elaboration,
                s.coherence,
                s.actionability,
                s.brand_fit,
                s.factual_reliability,
                s.constraints_met,
                s.constraint_notes,
                s.critique
            FROM experiments e
            LEFT JOIN artifacts a ON a.experiment_id = e.id
            LEFT JOIN scores s ON s.experiment_id = e.id AND s.scored_by = 'muse'
            {where_clause}
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (*params, limit),
        )).fetchall()
    holdout_score_map = await _get_holdout_score_map([row["id"] for row in rows])
    records = []
    for row in rows:
        payload = dict(row)
        payload["epoch"] = _normalize_epoch(payload.get("epoch"))
        payload["artifact"] = payload.pop("content", None)
        payload["family"] = payload.get("prompt_family")
        payload["hypothesis"] = payload.get("hypothesis_id")
        payload["constraints"] = _safe_json_loads(payload.get("constraints"), [])
        payload["process_trace"] = _safe_json_loads(payload.get("process_trace"), {})
        payload["source_context"] = _safe_json_loads(payload.get("source_context"), {})
        payload["holdout_scores"] = holdout_score_map.get(payload["id"], [])
        payload["role_packets"] = _build_role_packets(payload, payload["holdout_scores"])
        records.append(payload)
    return _attach_comparison_packets(records)


async def _get_score_map(experiment_ids):
    if not experiment_ids:
        return {}
    placeholders = ",".join("?" for _ in experiment_ids)
    async with connect() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT experiment_id, scored_by, composite
            FROM scores
            WHERE experiment_id IN ({placeholders})
              AND scored_by IN ('muse', 'athena', 'hermes', 'apollo', 'hermes_external')
            ORDER BY id
            """,
            experiment_ids,
        )).fetchall()
    score_map = {}
    for row in rows:
        payload = dict(row)
        experiment_id = payload["experiment_id"]
        score_map.setdefault(experiment_id, {})
        score_map[experiment_id][_canonical_role_id(payload["scored_by"])] = payload.get("composite")
    return score_map


async def _get_holdout_score_map(experiment_ids):
    if not experiment_ids:
        return {}
    placeholders = ",".join("?" for _ in experiment_ids)
    async with connect() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT *
            FROM scores
            WHERE experiment_id IN ({placeholders})
              AND scored_by IN ('critic_holdout', 'athena', 'hermes', 'apollo', 'hermes_external')
            ORDER BY id
            """,
            experiment_ids,
        )).fetchall()
    score_map = {}
    for row in rows:
        payload = dict(row)
        score_map.setdefault(payload["experiment_id"], []).append(payload)
    return score_map


def _group_explicit_packet_records(records):
    grouped = {}
    for row in records:
        packet = row.get("comparison_packet") or {}
        packet_id = packet.get("packet_id")
        if packet_id and packet.get("explicit"):
            grouped.setdefault(packet_id, []).append(row)
    return grouped


def _summarize_disagreement_packet(packet_id, members, score_map, review, *, min_judge_margin):
    comparison = _build_packet_disagreement(members, score_map, min_judge_margin=min_judge_margin)
    members = sorted(members, key=lambda row: row.get("id") or 0)
    return {
        "packet_id": packet_id,
        "has_noticeable_disagreement": comparison["has_noticeable_disagreement"],
        "has_review_ready_panel": comparison["has_review_ready_panel"],
        "has_complete_panel": comparison["has_complete_panel"],
        "missing_judges": comparison["missing_judges"],
        "lane": members[0].get("lane"),
        "prompt": members[0].get("prompt"),
        "constraints": members[0].get("constraints") or [],
        "family": members[0].get("prompt_family") or members[0].get("family"),
        "condition": members[0].get("condition"),
        "members": [
            {
                "experiment_id": row.get("id"),
                "role_id": row.get("packet_role_id") or "genesis",
                "status": row.get("status"),
                "promotion_status": row.get("promotion_status"),
                "artifact_preview": (row.get("artifact") or "")[:280],
                "muse_composite": score_map.get(row.get("id"), {}).get("muse"),
                "athena_composite": score_map.get(row.get("id"), {}).get("athena"),
                "apollo_composite": score_map.get(row.get("id"), {}).get("apollo"),
            }
            for row in members
        ],
        "judge_preferences": comparison["judges"],
        "vote_counts": comparison["vote_counts"],
        "human_review": review,
    }


def _review_still_active(review):
    if not review:
        return False
    metadata = review.get("metadata") or {}
    return metadata.get("review_decision_state") == "revisit_later"


def _packet_last_activity_at(members):
    timestamps = [
        _parse_created_at(member.get("created_at"))
        for member in members
        if _parse_created_at(member.get("created_at")) is not None
    ]
    if not timestamps:
        return None
    return max(timestamps)


def _classify_assembly_health(members):
    latest = _packet_last_activity_at(members)
    if latest is None:
        return "stalled"
    age = datetime.now() - latest
    return "active" if age <= timedelta(minutes=ASSEMBLING_STALE_MINUTES) else "stalled"


async def list_disagreement_packets(limit=10, *, unresolved_only=True, include_consensus=False, min_judge_margin=0.2, recent_limit=250, epoch=CURRENT_EXPERIMENT_EPOCH):
    records = await get_recent_experiments(limit=recent_limit, epoch=epoch)
    grouped = _group_explicit_packet_records(records)
    if not grouped:
        return []

    resolutions = await get_packet_resolutions_map(grouped.keys())
    experiment_ids = [row.get("id") for rows in grouped.values() for row in rows if row.get("id") is not None]
    score_map = await _get_score_map(experiment_ids)
    reviews = {}
    if unresolved_only:
        async with connect() as conn:
            rows = await (await conn.execute("SELECT * FROM comparison_reviews")).fetchall()
            for row in rows:
                payload = _attach_review_metadata_stats({
                    **dict(row),
                    "metadata": _safe_json_loads(dict(row).get("metadata"), {}),
                })
                reviews[payload["packet_id"]] = payload

    packets = []
    for packet_id, members in grouped.items():
        if resolutions.get(packet_id):
            continue
        review = reviews.get(packet_id)
        if unresolved_only and review and not _review_still_active(review):
            continue
        summary = _summarize_disagreement_packet(packet_id, members, score_map, review, min_judge_margin=min_judge_margin)
        if not summary:
            continue
        if not summary.get("has_review_ready_panel"):
            continue
        if include_consensus or summary.get("has_noticeable_disagreement"):
            packets.append(summary)
    packets.sort(key=lambda row: max(member["experiment_id"] for member in row["members"]), reverse=True)
    return packets[:limit]


async def list_assembling_packets(limit=6, *, recent_limit=250, epoch=CURRENT_EXPERIMENT_EPOCH):
    records = await get_recent_experiments(limit=recent_limit, epoch=epoch)
    grouped = _group_explicit_packet_records(records)
    if not grouped:
        return []

    resolutions = await get_packet_resolutions_map(grouped.keys())
    experiment_ids = [row.get("id") for rows in grouped.values() for row in rows if row.get("id") is not None]
    score_map = await _get_score_map(experiment_ids)

    packets = []
    for packet_id, members in grouped.items():
        if resolutions.get(packet_id):
            continue
        summary = _summarize_disagreement_packet(packet_id, members, score_map, None, min_judge_margin=0.2)
        if not summary or summary.get("has_review_ready_panel"):
            continue
        stage = "awaiting_pair_member" if len(members) < 2 else "awaiting_evaluator_panel"
        latest = _packet_last_activity_at(members)
        packets.append({
            **summary,
            "assembly_stage": stage,
            "assembly_health": _classify_assembly_health(members),
            "latest_activity_at": latest.strftime("%Y-%m-%d %H:%M:%S") if latest else None,
        })
    packets.sort(key=lambda row: max(member["experiment_id"] for member in row["members"]), reverse=True)
    return packets[:limit]


async def get_disagreement_packet(packet_id, *, min_judge_margin=0.2):
    if not packet_id:
        return None
    resolution = await get_packet_resolution(packet_id)
    records = await get_recent_experiments(limit=400, epoch=CURRENT_EXPERIMENT_EPOCH)
    members = [
        row
        for row in records
        if (row.get("comparison_packet") or {}).get("packet_id") == packet_id
        and (row.get("comparison_packet") or {}).get("explicit")
    ]
    if not members:
        return None
    experiment_ids = [row.get("id") for row in members if row.get("id") is not None]
    score_map = await _get_score_map(experiment_ids)
    review = await get_comparison_review(packet_id)
    summary = _summarize_disagreement_packet(packet_id, members, score_map, review, min_judge_margin=min_judge_margin)
    summary["packet_resolution"] = resolution
    summary["members"] = [
        {
            **member,
            "artifact": member.get("artifact") or "",
            "scores": score_map.get(member.get("id"), {}),
        }
        for member in sorted(members, key=lambda row: row.get("id") or 0)
    ]
    return summary


async def list_blind_rereview_candidates(limit=5, *, epoch=CURRENT_EXPERIMENT_EPOCH):
    await init_db()
    cutoff = (datetime.now(UTC) - timedelta(days=BLIND_REREVIEW_LOOKBACK_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT
                cr.packet_id,
                cr.preferred_experiment_id,
                cr.rationale,
                cr.reviewer,
                cr.review_channel,
                cr.metadata,
                cr.created_at,
                cr.updated_at,
                COALESCE(e.lane, pm.lane) AS lane,
                COALESCE(e.epoch, pm.epoch) AS epoch,
                COALESCE(e.prompt_family, pm.prompt_family) AS prompt_family
            FROM comparison_reviews cr
            LEFT JOIN experiments e ON e.id = cr.preferred_experiment_id
            LEFT JOIN (
                SELECT packet_id, MIN(lane) AS lane, MIN(epoch) AS epoch, MIN(prompt_family) AS prompt_family
                FROM experiments
                WHERE packet_id IS NOT NULL
                GROUP BY packet_id
            ) pm ON pm.packet_id = cr.packet_id
            WHERE COALESCE(e.epoch, pm.epoch) = ?
              AND cr.updated_at <= ?
            ORDER BY
              CASE json_extract(cr.metadata, '$.review_confidence')
                WHEN 'coin_flip' THEN 0
                WHEN 'tentative' THEN 1
                ELSE 2
              END,
              cr.updated_at ASC
            LIMIT ?
            """,
            (epoch, cutoff, limit),
        )).fetchall()
    candidates = []
    for row in rows:
        payload = _attach_review_metadata_stats({
            **dict(row),
            "metadata": _safe_json_loads(dict(row).get("metadata"), {}),
        })
        candidates.append({
            "packet_id": payload.get("packet_id"),
            "lane": payload.get("lane"),
            "family": payload.get("prompt_family"),
            "updated_at": payload.get("updated_at"),
            "review_confidence": (payload.get("metadata") or {}).get("review_confidence"),
            "review_decision_state": (payload.get("metadata") or {}).get("review_decision_state"),
            "review_revision_count": (payload.get("metadata") or {}).get("review_revision_count", 0),
            "review_reversal_count": (payload.get("metadata") or {}).get("review_reversal_count", 0),
        })
    return candidates


async def get_recent_scores(limit=200, *, epoch=None):
    filters = []
    params = []
    if epoch:
        filters.append("e.epoch = ?")
        params.append(epoch)
    where_clause = f"AND {' AND '.join(filters)}" if filters else ""
    async with connect() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT s.*, e.lane, e.prompt_family, e.status
            FROM scores s
            JOIN experiments e ON e.id = s.experiment_id
            WHERE s.scored_by = 'muse'
            {where_clause}
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (*params, limit),
        )).fetchall()
        return [dict(row) for row in rows]


async def get_timeline(limit=120, *, epoch=CURRENT_EXPERIMENT_EPOCH):
    filters = []
    params = []
    if epoch:
        filters.append("e.epoch = ?")
        params.append(epoch)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    async with connect() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT e.id, e.status, e.created_at, s.composite, e.lane, e.condition
            FROM experiments e
            LEFT JOIN scores s ON s.experiment_id = e.id AND s.scored_by = 'muse'
            {where_clause}
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (*params, limit),
        )).fetchall()
        return [dict(row) for row in reversed(rows)]


async def get_best_scores(*, epoch=None):
    filters = ["scored_by = 'muse'"]
    params = []
    if epoch:
        filters.append("experiment_id IN (SELECT id FROM experiments WHERE epoch = ?)")
        params.append(epoch)
    async with connect() as conn:
        row = await (await conn.execute(
            f"""
            SELECT novelty, surprise, value, elaboration, coherence
            FROM scores
            WHERE {' AND '.join(filters)}
            ORDER BY composite DESC, id DESC
            LIMIT 1
            """,
            params,
        )).fetchone()
        return dict(row) if row else {key: None for key in ("novelty", "surprise", "value", "elaboration", "coherence")}


async def get_trends(*, epoch=CURRENT_EXPERIMENT_EPOCH):
    scores = await get_recent_scores(limit=200, epoch=epoch)
    if not scores:
        return {
            "mean_composite": None,
            "median_composite": None,
            "early_mean": None,
            "recent_mean": None,
            "muse_critic_divergence": None,
            "muse_critic_pairs": 0,
            "lanes": [],
            "conditions": [],
        }
    composites = [row.get("composite") for row in scores if row.get("composite") is not None]
    recent = composites[:10]
    early = composites[-10:] if len(composites) >= 10 else composites
    lane_groups = {}
    for row in scores:
        lane_groups.setdefault(row.get("lane") or "creative", []).append(row)
    lanes = [
        {"lane": lane, "lane_mean": _mean(item.get("composite") for item in bucket), "lane_count": len(bucket)}
        for lane, bucket in lane_groups.items()
    ]
    return {
        "mean_composite": _mean(composites),
        "median_composite": sorted(composites)[len(composites) // 2] if composites else None,
        "early_mean": _mean(early),
        "recent_mean": _mean(recent),
        "muse_critic_divergence": None,
        "muse_critic_pairs": 0,
        "lanes": lanes,
        "conditions": [],
    }


async def upsert_policy_registry_entry(row):
    await init_db()
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO policy_registry (
                lane, prompt_family, policy_key, recommended_value, approved_value,
                approval_status, operational_status, rationale, reviewer_note, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(lane, prompt_family, policy_key) DO UPDATE SET
                recommended_value = excluded.recommended_value,
                approved_value = excluded.approved_value,
                approval_status = excluded.approval_status,
                operational_status = excluded.operational_status,
                rationale = excluded.rationale,
                reviewer_note = excluded.reviewer_note,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                row.get("lane"),
                row.get("prompt_family"),
                row.get("policy_key"),
                row.get("recommended_value"),
                row.get("approved_value"),
                row.get("approval_status"),
                row.get("operational_status"),
                row.get("rationale"),
                row.get("reviewer_note"),
                row.get("source"),
            ),
        )
        await conn.commit()


async def get_policy_registry():
    async with connect() as conn:
        rows = await (await conn.execute("SELECT * FROM policy_registry ORDER BY updated_at DESC, id DESC")).fetchall()
        return [dict(row) for row in rows]


async def get_approved_policy_controls():
    rows = await get_policy_registry()
    controls = {}
    for row in rows:
        if row.get("policy_key") == "prompt_policy_default" and row.get("approval_status") == "approved" and row.get("approved_value"):
            controls[(row.get("lane"), row.get("prompt_family"))] = row
    return controls


async def list_reference_packs():
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT id, lane, prompt_family, title, source_type, task_definition, live_examples,
                   failure_modes, expected_tradeoffs, constraint_patterns, paired_test_matrix,
                   notes, status, created_at, updated_at
            FROM reference_packs
            ORDER BY id DESC
            """
        )).fetchall()
        payloads = []
        for row in rows:
            payload = dict(row)
            for key in ("task_definition", "live_examples", "failure_modes", "expected_tradeoffs", "constraint_patterns", "paired_test_matrix"):
                payload[key] = _safe_json_loads(payload.get(key), payload.get(key))
            payloads.append(payload)
        return payloads


async def create_reference_pack(payload):
    async with connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO reference_packs (
                lane, prompt_family, title, source_type, task_definition, live_examples,
                failure_modes, expected_tradeoffs, constraint_patterns, paired_test_matrix, notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("lane", "creative"),
                payload.get("prompt_family", "general"),
                payload.get("title"),
                payload.get("source_type", "manual"),
                json.dumps(payload.get("task_definition")),
                json.dumps(payload.get("live_examples")),
                json.dumps(payload.get("failure_modes")),
                json.dumps(payload.get("expected_tradeoffs")),
                json.dumps(payload.get("constraint_patterns")),
                json.dumps(payload.get("paired_test_matrix")),
                payload.get("notes"),
                payload.get("status", "draft"),
            ),
        )
        await conn.commit()
        return cur.lastrowid


async def add_council_entry(payload):
    async with connect() as conn:
        cur = await conn.execute(
            "INSERT INTO council_history (payload) VALUES (?)",
            (json.dumps(payload),),
        )
        await conn.commit()
        return cur.lastrowid


async def get_council_history(limit=10):
    async with connect() as conn:
        rows = await (await conn.execute(
            "SELECT id, payload, created_at FROM council_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )).fetchall()
        return [{"id": row["id"], "payload": _safe_json_loads(row["payload"], {}), "created_at": row["created_at"]} for row in rows]


async def upsert_council_action(payload):
    await init_db()
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO council_actions (
                council_id, action_type, title, status, lane, prompt_family, payload, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(action_type, title) DO UPDATE SET
                council_id = excluded.council_id,
                status = excluded.status,
                lane = excluded.lane,
                prompt_family = excluded.prompt_family,
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                payload.get("council_id"),
                payload.get("action_type"),
                payload.get("title"),
                payload.get("status"),
                payload.get("lane"),
                payload.get("prompt_family"),
                json.dumps(payload.get("payload") or {}),
            ),
        )
        await conn.commit()

        row = await (await conn.execute(
            """
            SELECT id, council_id, action_type, title, status, lane, prompt_family, payload, created_at, updated_at
            FROM council_actions
            WHERE action_type = ? AND title = ?
            """,
            (payload.get("action_type"), payload.get("title")),
        )).fetchone()
        result = dict(row)
        result["payload"] = _safe_json_loads(result.get("payload"), {})
    if result.get("action_type") == "prompt_diagnosis_refinement":
        result["prompt_rule"] = await upsert_prompt_rule_from_council_action(result)
    return result


async def get_council_actions(limit=100):
    await init_db()
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT id, council_id, action_type, title, status, lane, prompt_family, payload, created_at, updated_at
            FROM council_actions
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )).fetchall()
        payloads = []
        for row in rows:
            payload = dict(row)
            payload["payload"] = _safe_json_loads(payload.get("payload"), {})
            payloads.append(payload)
        return payloads


def _rule_payload_from_council_action(action):
    payload = action.get("payload") or {}
    title = str(action.get("title") or payload.get("title") or "Prompt diagnosis rule").strip()
    default_namespace = "diagnosis" if action.get("action_type") == "prompt_diagnosis_refinement" else (action.get("action_type") or "council")
    rule_key = payload.get("rule_key") or f"{default_namespace}::{_slugify_key(title)}"
    rule_text = str(payload.get("action") or payload.get("reason") or title).strip()
    return {
        "rule_key": rule_key,
        "title": title,
        "scope_claim": payload.get("scope_claim") or _normalize_rule_scope_claim(
            None,
            lane=action.get("lane"),
            prompt_family=action.get("prompt_family"),
        ),
        "status": payload.get("rule_status") or "candidate",
        "rule_type": payload.get("rule_type") or "audience_grounding",
        "rule_text": rule_text,
        "rationale": payload.get("reason") or payload.get("why_now") or rule_text,
        "payload": {
            **payload,
            "source": "council_action",
            "council_action_id": action.get("id"),
            "council_id": action.get("council_id"),
            "action_status": action.get("status"),
            "lane": action.get("lane"),
            "prompt_family": action.get("prompt_family"),
        },
    }


async def upsert_prompt_rule(rule):
    await init_db()
    rule_key = str(rule.get("rule_key") or "").strip()
    if not rule_key:
        raise ValueError("rule_key is required")
    title = str(rule.get("title") or rule_key).strip()
    scope_claim = _normalize_rule_scope_claim(
        rule.get("scope_claim"),
        lane=rule.get("lane"),
        prompt_family=rule.get("prompt_family"),
    )
    status = _normalize_rule_status(rule.get("status"))
    rule_text = str(rule.get("rule_text") or rule.get("action") or title).strip()
    rationale = str(rule.get("rationale") or "").strip()
    payload = rule.get("payload") or {}

    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO prompt_rules (rule_key, scope_claim, status, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(rule_key) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            """,
            (rule_key, scope_claim, status),
        )
        prompt_rule = await (await conn.execute(
            "SELECT * FROM prompt_rules WHERE rule_key = ?",
            (rule_key,),
        )).fetchone()
        rule_id = prompt_rule["id"]
        latest = await (await conn.execute(
            """
            SELECT version, rule_text, rationale, payload
            FROM rule_versions
            WHERE rule_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (rule_id,),
        )).fetchone()
        serialized_payload = json.dumps(payload)
        if latest is None:
            version = 1
            await conn.execute(
                """
                INSERT INTO rule_versions (rule_id, version, title, rule_type, rule_text, rationale, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rule_id, version, title, rule.get("rule_type"), rule_text, rationale, serialized_payload),
            )
        elif (
            latest["rule_text"] != rule_text
            or (latest["rationale"] or "") != rationale
            or (latest["payload"] or "{}") != serialized_payload
        ):
            version = int(latest["version"]) + 1
            await conn.execute(
                """
                INSERT INTO rule_versions (rule_id, version, title, rule_type, rule_text, rationale, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rule_id, version, title, rule.get("rule_type"), rule_text, rationale, serialized_payload),
            )
        else:
            version = int(latest["version"])
        await conn.execute(
            "UPDATE prompt_rules SET current_version = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (version, rule_id),
        )
        await conn.commit()

        row = await (await conn.execute(
            """
            SELECT pr.*, rv.title, rv.rule_type, rv.rule_text, rv.rationale, rv.payload
            FROM prompt_rules pr
            JOIN rule_versions rv ON rv.rule_id = pr.id AND rv.version = pr.current_version
            WHERE pr.id = ?
            """,
            (rule_id,),
        )).fetchone()
    result = dict(row)
    result["payload"] = _safe_json_loads(result.get("payload"), {})
    return result


async def upsert_prompt_rule_from_council_action(action):
    return await upsert_prompt_rule(_rule_payload_from_council_action(action))


async def list_prompt_rules(limit=100):
    await init_db()
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT pr.*, rv.title, rv.rule_type, rv.rule_text, rv.rationale, rv.payload
            FROM prompt_rules pr
            JOIN rule_versions rv ON rv.rule_id = pr.id AND rv.version = pr.current_version
            ORDER BY pr.updated_at DESC, pr.id DESC
            LIMIT ?
            """,
            (limit,),
        )).fetchall()
    payloads = []
    for row in rows:
        payload = dict(row)
        payload["payload"] = _safe_json_loads(payload.get("payload"), {})
        payloads.append(payload)
    return payloads


async def record_rule_evidence_slice(payload):
    await init_db()
    rule_key = str(payload.get("rule_key") or "").strip()
    if not rule_key:
        raise ValueError("rule_key is required")
    rule = await upsert_prompt_rule({
        "rule_key": rule_key,
        "title": payload.get("title") or rule_key,
        "scope_claim": payload.get("scope_claim"),
        "status": "candidate",
        "rule_type": payload.get("rule_type") or "model_adaptation",
        "rule_text": payload.get("rule_text") or payload.get("title") or rule_key,
        "rationale": payload.get("rationale") or "",
        "payload": payload.get("rule_payload") or {},
    })
    rule_id = rule["id"]
    rule_version = int(payload.get("rule_version") or rule.get("current_version") or 1)
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO rule_evidence_slices (
                rule_id, rule_version, lane, prompt_family, model_family, panel_version, experiment_type,
                packet_id, experiment_id, compared_experiment_id, human_signal,
                human_signal_attribution_method, evaluator_signal, evaluator_margin, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id, rule_version, experiment_type, packet_id, experiment_id, compared_experiment_id)
            DO UPDATE SET
                human_signal = excluded.human_signal,
                human_signal_attribution_method = excluded.human_signal_attribution_method,
                evaluator_signal = excluded.evaluator_signal,
                evaluator_margin = excluded.evaluator_margin,
                metadata = excluded.metadata,
                panel_version = excluded.panel_version,
                observed_at = CURRENT_TIMESTAMP
            """,
            (
                rule_id,
                rule_version,
                payload.get("lane"),
                payload.get("prompt_family"),
                payload.get("model_family"),
                payload.get("panel_version") or JUDGE_PANEL_VERSION,
                _normalize_rule_experiment_type(payload.get("experiment_type")),
                payload.get("packet_id"),
                payload.get("experiment_id"),
                payload.get("compared_experiment_id"),
                _normalize_rule_evidence_signal(payload.get("human_signal")),
                payload.get("human_signal_attribution_method") or "uniform",
                _normalize_rule_evidence_signal(payload.get("evaluator_signal")),
                payload.get("evaluator_margin"),
                json.dumps(payload.get("metadata") or {}),
            ),
        )
        if payload.get("experiment_id"):
            await conn.execute(
                "UPDATE experiments SET primary_rule_id = COALESCE(primary_rule_id, ?) WHERE id = ?",
                (rule_id, payload.get("experiment_id")),
            )
        await conn.commit()
        row = await (await conn.execute(
            """
            SELECT res.*, pr.rule_key, pr.scope_claim, pr.status
            FROM rule_evidence_slices res
            JOIN prompt_rules pr ON pr.id = res.rule_id
            WHERE pr.rule_key = ?
            ORDER BY res.id DESC
            LIMIT 1
            """,
            (rule_key,),
        )).fetchone()
    result = dict(row)
    result["metadata"] = _safe_json_loads(result.get("metadata"), {})
    return result


async def backfill_rule_evidence_human_signal(packet_id, review):
    if not packet_id or not review:
        return []
    base_signal = _human_signal_from_review(review)
    preferred_experiment_id = review.get("preferred_experiment_id")
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT id, experiment_id
            FROM rule_evidence_slices
            WHERE packet_id = ?
            """,
            (packet_id,),
        )).fetchall()
        updated = []
        for row in rows:
            signal = base_signal
            if signal is None:
                signal = "helped" if row["experiment_id"] == preferred_experiment_id else "hurt"
            signal = _normalize_rule_evidence_signal(signal)
            await conn.execute(
                """
                UPDATE rule_evidence_slices
                SET human_signal = ?,
                    human_signal_attribution_method = 'uniform',
                    observed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (signal, row["id"]),
            )
            updated.append({"id": row["id"], "human_signal": signal, "human_signal_attribution_method": "uniform"})
        await conn.commit()
    return updated


async def list_rule_evidence_slices(limit=100):
    await init_db()
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT res.*, pr.rule_key, pr.scope_claim, pr.status
            FROM rule_evidence_slices res
            JOIN prompt_rules pr ON pr.id = res.rule_id
            ORDER BY res.observed_at DESC, res.id DESC
            LIMIT ?
            """,
            (limit,),
        )).fetchall()
    payloads = []
    for row in rows:
        payload = dict(row)
        payload["metadata"] = _safe_json_loads(payload.get("metadata"), {})
        payloads.append(payload)
    return payloads


def _promotion_thresholds(overrides=None):
    thresholds = dict(PROMPT_RULE_PROMOTION_DEFAULTS)
    for key, value in (overrides or {}).items():
        if key not in thresholds or value is None:
            continue
        if key.endswith("_rate"):
            thresholds[key] = float(value)
        else:
            thresholds[key] = int(value)
    return thresholds


def _rule_characterization(metrics, thresholds):
    total_slices = max(int(metrics.get("eligible_slices") or metrics.get("total_slices") or 0), 1)
    evaluator_helped = int(metrics.get("evaluator_helped") or 0)
    panel_prefers = (
        evaluator_helped > 0
        and (evaluator_helped / total_slices) >= thresholds.get("panel_preference_rate", 0.6)
    )
    human_decisive = int(metrics.get("human_decisive") or 0)
    if human_decisive < thresholds.get("characterization_min_human", 5):
        return "insufficient_data"

    human_win_rate = metrics.get("human_win_rate")
    human_prefers = human_win_rate is not None and human_win_rate >= 0.6
    human_disprefers = human_win_rate is not None and human_win_rate <= 0.4
    if panel_prefers and human_prefers:
        return "aligned"
    if panel_prefers and human_disprefers:
        return "divergent"
    if panel_prefers and not human_prefers and not human_disprefers:
        return "llm_specific"
    if not panel_prefers and human_prefers:
        return "human_specific"
    return "neutral"


def _rule_promotion_recommendation(row, thresholds):
    status = row["status"]
    support_packets = int(row["support_packets"] or 0)
    support_families = int(row["support_families"] or 0)
    support_model_families = int(row["support_model_families"] or 0)
    human_helped = int(row["human_helped"] or 0)
    human_hurt = int(row["human_hurt"] or 0)
    human_decisive = human_helped + human_hurt
    human_win_rate = (human_helped / human_decisive) if human_decisive else None
    hurt_rate = (human_hurt / human_decisive) if human_decisive else None

    reasons = []
    missing = []
    proposed_status = status
    recommendation = "hold"

    if status == "candidate":
        if support_packets >= thresholds["provisional_packets"]:
            reasons.append(f"{support_packets} supporting packets")
        else:
            missing.append(f"{thresholds['provisional_packets'] - support_packets} more supporting packet(s)")
        if support_families >= thresholds["provisional_families"]:
            reasons.append(f"{support_families} prompt families")
        else:
            missing.append(f"{thresholds['provisional_families'] - support_families} more prompt family/families")
        if not missing:
            proposed_status = "provisional"
            recommendation = "promote"
    elif status == "provisional":
        checks = [
            (
                support_packets >= thresholds["active_packets"],
                f"{support_packets} supporting packets",
                f"{thresholds['active_packets'] - support_packets} more supporting packet(s)",
            ),
            (
                support_families >= thresholds["active_families"],
                f"{support_families} prompt families",
                f"{thresholds['active_families'] - support_families} more prompt family/families",
            ),
            (
                support_model_families >= thresholds["active_model_families"],
                f"{support_model_families} model families",
                f"{thresholds['active_model_families'] - support_model_families} more model family/families",
            ),
            (
                human_decisive >= thresholds["active_human_decisive"],
                f"{human_decisive} decisive human reviews",
                f"{thresholds['active_human_decisive'] - human_decisive} more decisive human review(s)",
            ),
            (
                human_win_rate is not None and human_win_rate > thresholds["active_human_win_rate"],
                f"{human_win_rate:.2f} human win rate" if human_win_rate is not None else "human win rate unavailable",
                f"human win rate must exceed {thresholds['active_human_win_rate']:.2f}",
            ),
        ]
        for passed, reason, miss in checks:
            if passed:
                reasons.append(reason)
            else:
                missing.append(miss)
        if not missing:
            proposed_status = "active"
            recommendation = "promote"
    elif status == "active":
        if (
            hurt_rate is not None
            and human_decisive >= thresholds["hurt_flag_min"]
            and hurt_rate >= thresholds["hurt_flag_rate"]
        ):
            recommendation = "watch"
            reasons.append(f"{hurt_rate:.2f} human hurt rate across {human_decisive} decisive reviews")
        else:
            missing.append("no demotion signal strong enough to flag")

    # Watch can fire on candidate/provisional rules too. A rule accumulating
    # decisive negative human signal must be visible regardless of status,
    # otherwise a bad candidate looks identical to an unevidenced one and the
    # operator never sees the warning. Reuses the active-rule hurt thresholds.
    if (
        recommendation != "watch"
        and status in ("candidate", "provisional")
        and hurt_rate is not None
        and human_decisive >= thresholds["hurt_flag_min"]
        and hurt_rate >= thresholds["hurt_flag_rate"]
    ):
        recommendation = "watch"
        reasons.append(f"{hurt_rate:.2f} human hurt rate across {human_decisive} decisive reviews")

    metrics = {
        "total_slices": int(row["total_slices"] or 0),
        "eligible_slices": int(row["eligible_slices"] or 0),
        "suppressed_dual_constraint_fail": int(row["suppressed_dual_constraint_fail"] or 0),
        "support_packets": support_packets,
        "support_families": support_families,
        "support_model_families": support_model_families,
        "human_helped": human_helped,
        "human_hurt": human_hurt,
        "human_mixed": int(row["human_mixed"] or 0),
        "human_unreviewed": int(row["human_unreviewed"] or 0),
        "human_decisive": human_decisive,
        "human_win_rate": human_win_rate,
        "hurt_rate": hurt_rate,
        "evaluator_helped": int(row["evaluator_helped"] or 0),
        "panel_versions": _safe_json_loads(row["panel_versions"], []),
    }
    characterization = _rule_characterization(metrics, thresholds)

    return {
        "rule_id": row["rule_id"],
        "rule_key": row["rule_key"],
        "title": row["title"],
        "current_status": status,
        "proposed_status": proposed_status,
        "recommendation": recommendation,
        "characterization": characterization,
        "reasons": reasons,
        "missing": missing,
        "metrics": metrics,
    }


async def compute_rule_promotion_proposals(threshold_overrides=None):
    """Compute dry-run promotion proposals from accumulated rule evidence.

    Note on temporal behavior of support metrics: human verdict supersedes
    evaluator verdict (a slice counts as "supporting" only when the human
    signal is "helped" OR the human signal is "unreviewed" and the evaluator
    signal is "helped"). This means support_packets / support_families /
    support_model_families can DECREASE for a given rule when a human reviews
    a previously-unreviewed packet and disagrees with the evaluator. That is
    intentional, not a bug -- the lab is comparing panel preference against
    human preference rather than treating unreviewed panel inference as final.
    """
    await init_db()
    thresholds = _promotion_thresholds(threshold_overrides)
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT
                pr.id AS rule_id,
                pr.rule_key,
                pr.status,
                rv.title,
                COUNT(res.id) AS total_slices,
                SUM(CASE
                    WHEN res.id IS NOT NULL
                        AND NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                    THEN 1 ELSE 0
                END) AS eligible_slices,
                SUM(CASE
                    WHEN res.id IS NOT NULL
                        AND COALESCE(compiled.status, '') = 'constraint_fail'
                        AND COALESCE(compared.status, '') = 'constraint_fail'
                    THEN 1 ELSE 0
                END) AS suppressed_dual_constraint_fail,
                COUNT(DISTINCT CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND (
                            res.human_signal = 'helped'
                            OR (res.human_signal = 'unreviewed' AND res.evaluator_signal = 'helped')
                        )
                    THEN COALESCE(res.packet_id, 'experiment:' || res.experiment_id)
                END) AS support_packets,
                COUNT(DISTINCT CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND (
                            res.human_signal = 'helped'
                            OR (res.human_signal = 'unreviewed' AND res.evaluator_signal = 'helped')
                        )
                    THEN NULLIF(res.prompt_family, '')
                END) AS support_families,
                COUNT(DISTINCT CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND (
                            res.human_signal = 'helped'
                            OR (res.human_signal = 'unreviewed' AND res.evaluator_signal = 'helped')
                        )
                    THEN NULLIF(res.model_family, '')
                END) AS support_model_families,
                SUM(CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND res.human_signal = 'helped'
                    THEN 1 ELSE 0 END
                ) AS human_helped,
                SUM(CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND res.human_signal = 'hurt'
                    THEN 1 ELSE 0 END
                ) AS human_hurt,
                SUM(CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND res.human_signal = 'mixed'
                    THEN 1 ELSE 0 END
                ) AS human_mixed,
                SUM(CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND res.human_signal = 'unreviewed'
                    THEN 1 ELSE 0 END
                ) AS human_unreviewed,
                SUM(CASE
                    WHEN NOT (COALESCE(compiled.status, '') = 'constraint_fail' AND COALESCE(compared.status, '') = 'constraint_fail')
                        AND res.evaluator_signal = 'helped'
                    THEN 1 ELSE 0 END
                ) AS evaluator_helped,
                json_group_array(DISTINCT res.panel_version) AS panel_versions
            FROM prompt_rules pr
            JOIN rule_versions rv ON rv.rule_id = pr.id AND rv.version = pr.current_version
            LEFT JOIN rule_evidence_slices res ON res.rule_id = pr.id AND res.rule_version = pr.current_version
            LEFT JOIN experiments compiled ON compiled.id = res.experiment_id
            LEFT JOIN experiments compared ON compared.id = res.compared_experiment_id
            GROUP BY pr.id
            ORDER BY pr.updated_at DESC, pr.id DESC
            """
        )).fetchall()
    proposals = [_rule_promotion_recommendation(row, thresholds) for row in rows]
    async with connect() as conn:
        for proposal in proposals:
            await conn.execute(
                """
                UPDATE prompt_rules
                SET characterization = ?
                WHERE id = ? AND COALESCE(characterization, '') != ?
                """,
                (proposal["characterization"], proposal["rule_id"], proposal["characterization"]),
            )
        await conn.commit()
    return {
        "mode": "dry_run",
        "thresholds": thresholds,
        "proposals": proposals,
    }


async def build_state_payload():
    state = await get_state()
    best_scores = await get_best_scores(epoch=CURRENT_EXPERIMENT_EPOCH)
    trends = await get_trends(epoch=CURRENT_EXPERIMENT_EPOCH)
    epoch_summary = await get_epoch_summary()
    return {
        "state": state,
        "best_scores": best_scores,
        "trends": trends,
        "current_epoch": CURRENT_EXPERIMENT_EPOCH,
        "epoch_summary": epoch_summary,
    }


async def get_epoch_summary():
    await init_db()
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT epoch, COUNT(*) AS experiment_count, MAX(id) AS latest_experiment_id
            FROM experiments
            GROUP BY epoch
            ORDER BY latest_experiment_id DESC
            """
        )).fetchall()
    epochs = []
    total = 0
    for row in rows:
        payload = dict(row)
        payload["epoch"] = _normalize_epoch(payload.get("epoch"))
        total += payload.get("experiment_count") or 0
        epochs.append(payload)
    return {
        "current_epoch": CURRENT_EXPERIMENT_EPOCH,
        "legacy_epoch": LEGACY_EXPERIMENT_EPOCH,
        "total_experiments": total,
        "epochs": epochs,
        "headline": f"{len(epochs)} experiment epoch{'s' if len(epochs) != 1 else ''} recorded.",
    }


async def get_analysis_payload(*, epoch=CURRENT_EXPERIMENT_EPOCH):
    records = await get_recent_experiments(limit=200, epoch=epoch)
    rows = []
    for row in records:
        if row.get("composite") is None:
            continue
        enriched = dict(row)
        expressive_pressure = _mean(value for value in (row.get("novelty"), row.get("surprise")) if value is not None)
        grounding = _mean(value for value in (row.get("value"), row.get("coherence")) if value is not None)
        enriched["balance_counterpart"] = grounding
        enriched["balance_gap"] = None if expressive_pressure is None or grounding is None else expressive_pressure - grounding
        rows.append(enriched)
    policy_rows = await get_policy_registry()
    disagreement_rows = await list_disagreement_packets(limit=8, unresolved_only=True, include_consensus=True, epoch=epoch)
    all_assembling_rows = await list_assembling_packets(limit=12, epoch=epoch)
    assembling_rows = [row for row in all_assembling_rows if row.get("assembly_health") == "active"]
    stalled_rows = [row for row in all_assembling_rows if row.get("assembly_health") == "stalled"]
    graveyard_rows = await list_packet_resolutions(limit=8, epoch=epoch)
    calibration_rows = await get_recent_calibration_reviews(limit=50, epoch=epoch)
    blind_rereview_candidates = await list_blind_rereview_candidates(limit=4, epoch=epoch)

    paired_groups = {}
    for row in records:
        packet = row.get("comparison_packet") or {}
        packet_id = packet.get("packet_id")
        if packet_id and packet.get("size", 0) > 1:
            paired_groups.setdefault(packet_id, []).append(row)

    paired_rows = []
    for packet_id, members in paired_groups.items():
        members = [member for member in members if member.get("composite") is not None]
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda item: (item.get("composite") or 0, item.get("id") or 0), reverse=True)
        best = ordered[0]
        second = ordered[1]
        paired_rows.append({
            "packet_id": packet_id,
            "lane": best.get("lane"),
            "prompt_family": best.get("prompt_family") or best.get("family"),
            "condition": best.get("condition"),
            "composite_delta": (best.get("composite") or 0) - (second.get("composite") or 0),
        })

    verifier_rows = [
        row
        for row in records
        if (row.get("process_trace") or {}).get("verification_status")
        or (row.get("process_trace") or {}).get("verifier_checks")
    ]

    calibration_metrics = _build_calibration_metrics(rows, verifier_rows, paired_rows, calibration_rows)
    learning_snapshot = _build_learning_snapshot(rows, paired_rows, verifier_rows, calibration_rows)
    generator_learning = _build_generator_learning_summary(records, calibration_rows)
    policy_effects = _build_policy_effects([])
    policy_recommendations = _build_policy_recommendations([], [], policy_rows)

    balance_rows = _build_creativity_balance(rows)
    business_tax_rows = _build_business_creativity_tax(rows)
    champions = _build_champions(records)
    hypotheses = _build_hypothesis_summary(records)
    paired_conditions = _build_paired_condition_summary(records)
    human_calibration = _build_human_calibration_summary(calibration_rows)
    human_calibration["blind_candidates"] = blind_rereview_candidates
    constraint_verifier = _build_constraint_verifier_summary(verifier_rows)
    evaluator_diagnostics = _build_evaluator_diagnostics(records, disagreement_rows, calibration_rows)

    return {
        "analysis_scope": {
            "epoch": epoch,
            "headline": f"Analytics default to the {epoch} epoch while preserving historical memory.",
        },
        "epoch_summary": await get_epoch_summary(),
        "balance_summary": {
            "headline": f"Balance readout across {len(rows)} scored runs.",
            "lane_summaries": balance_rows,
        },
        "learning_snapshot": learning_snapshot,
        "generator_learning": generator_learning,
        "recommendations": {},
        "hypotheses": hypotheses,
        "creativity_balance": balance_rows,
        "paired_conditions": paired_conditions,
        "business_creativity_tax": business_tax_rows,
        "champions": champions,
        "policy_effects": policy_effects,
        "policy_validation": _build_policy_validation_summary(policy_rows),
        "evaluator_diagnostics": evaluator_diagnostics,
        "protocol_reliability": _build_protocol_reliability(records),
        "human_calibration": human_calibration,
        "constraint_verifier": constraint_verifier,
        "calibration_metrics": calibration_metrics,
        "disagreement_queue": {
            "headline": f"{len(disagreement_rows)} paired packets need human judgment." if disagreement_rows else "No paired packets ready for judgment yet.",
            "rows": disagreement_rows,
            "assembling_headline": f"{len(assembling_rows)} paired packets still assembling." if assembling_rows else "",
            "assembling_rows": assembling_rows,
            "stalled_headline": f"{len(stalled_rows)} paired packets are stalled and need repair." if stalled_rows else "",
            "stalled_rows": stalled_rows,
            "graveyard_headline": f"{len(graveyard_rows)} packet resolution(s) are in the graveyard." if graveyard_rows else "",
            "graveyard_rows": graveyard_rows,
        },
        "policy_recommendations": policy_recommendations,
    }
