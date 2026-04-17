"""Compile Hamlet's Ghost's reflective judgment memory.

This module turns packet evidence and human review into three research outputs:
- `wiki/` as reflective, revisable memory
- `taxonomy/` as promoted doctrine
- `calibration/` as evaluator alignment summaries
"""

from __future__ import annotations

import asyncio

import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

import database as db


REPO_ROOT = Path(__file__).resolve().parent
WIKI_ROOT = REPO_ROOT / "wiki"
TEMPLATE_ROOT = WIKI_ROOT / "templates"
TASTE_MEMORY_PATH = REPO_ROOT / "data" / "taste_memory.json"
TAXONOMY_ROOT = REPO_ROOT / "taxonomy"
CALIBRATION_ROOT = REPO_ROOT / "calibration"

GENERATED_DIRS = {
    "packets": "packets",
    "families": "families",
    "models": "models",
    "evaluators": "evaluators",
    "lessons": "lessons",
    "concepts": "concepts",
    "memos": "memos",
    "lint": "lint",
    "weekly": "weekly",
}

CONCEPT_EMERGENCE_THRESHOLD = 3
PROMOTION_MIN_PACKETS = 5
PROMOTION_MIN_DISTINCT_FAMILIES = 2
PROMOTION_MIN_MODEL_FAMILIES = 2


def load_taste_memory() -> dict[str, Any]:
    if not TASTE_MEMORY_PATH.exists():
        return {"anti_patterns": {"entries": []}, "quality_signals": {"entries": []}, "evaluator_failure_modes": {"entries": []}, "promotion_rules": {}}
    return json.loads(TASTE_MEMORY_PATH.read_text())


def _taste_entries_by_tag(taste: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_tag: dict[str, dict[str, Any]] = {}
    for entry in taste.get("anti_patterns", {}).get("entries", []):
        by_tag[entry["tag"]] = entry
    for entry in taste.get("quality_signals", {}).get("entries", []):
        by_tag[entry["tag"]] = entry
    for entry in taste.get("evaluator_failure_modes", {}).get("entries", []):
        by_tag[entry["tag"]] = entry
    return by_tag


def _taste_entries_for_lane(taste: dict[str, Any], lane: str, section: str) -> list[dict[str, Any]]:
    return [
        entry for entry in taste.get(section, {}).get("entries", [])
        if not entry.get("lanes") or lane in entry["lanes"]
    ]


def slugify(value: str) -> str:
    text = (value or "").strip().lower()
    out = []
    last_dash = False
    for ch in text:
        if ch.isalnum():
            out.append(ch)
            last_dash = False
        elif not last_dash:
            out.append("-")
            last_dash = True
    slug = "".join(out).strip("-")
    return slug or "untitled"


def humanize_tag(tag: str) -> str:
    return (tag or "").replace("_", " ").replace("-", " ").strip() or "untagged"


def _shorten(text: str, limit: int = 120) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def page_status(evidence_count: int, *, human_confirmed: bool = False, contested: bool = False) -> str:
    if contested:
        return "contested"
    if human_confirmed:
        return "human-confirmed"
    if evidence_count >= 4:
        return "repeated"
    if evidence_count >= 2:
        return "emerging"
    return "tentative"


def confidence_label(evidence_count: int, *, human_confirmed: bool = False, contested: bool = False) -> str:
    if contested:
        return "low"
    if human_confirmed and evidence_count >= 3:
        return "high"
    if human_confirmed or evidence_count >= 3:
        return "medium"
    return "low"


def role_label(role_id: str) -> str:
    labels = {
        "genesis": "Genesis",
        "theron": "Theron",
        "muse": "Muse",
        "athena": "Athena",
        "apollo": "Apollo",
    }
    return labels.get(role_id, role_id)


def model_family_label(model_family: str) -> str:
    labels = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
        "meta": "Meta",
        "mistral": "Mistral",
        "xai": "xAI",
        "qwen": "Qwen",
        "deepseek": "DeepSeek",
        "openclaw": "OpenClaw",
        "ollama": "Ollama",
        "unknown": "Unknown",
    }
    return labels.get(model_family, humanize_tag(model_family))


def condition_label(condition: str | None) -> str:
    if condition == "critique_on":
        return "With critique"
    if condition == "critique_off":
        return "Without critique"
    return condition or "Unknown mode"


def _load_template(name: str) -> Template:
    return Template((TEMPLATE_ROOT / name).read_text())


def _write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n")


def _cleanup_generated(root: Path) -> None:
    for child in GENERATED_DIRS.values():
        target = root / child
        if target.exists():
            shutil.rmtree(target)


def _generator_role(row: dict[str, Any]) -> str:
    return row.get("packet_role_id") or row.get("source_context", {}).get("generator_role_id") or "genesis"


def _infer_model_family(*values: Any) -> str | None:
    text = " ".join(str(value or "") for value in values).strip().lower()
    if not text:
        return None
    if any(token in text for token in ("gpt-", "gpt4", "gpt5", "openai", "o1", "o3", "o4")):
        return "openai"
    if "claude" in text or "anthropic" in text:
        return "anthropic"
    if "gemini" in text or "google" in text:
        return "google"
    if "llama" in text or "meta" in text:
        return "meta"
    if "mistral" in text:
        return "mistral"
    if "grok" in text or "xai" in text:
        return "xai"
    if "qwen" in text or "alibaba" in text:
        return "qwen"
    if "deepseek" in text:
        return "deepseek"
    if any(token in text for token in ("openclaw", "theron", "hermes_cli", "openclaw_local", "openclaw_gateway")):
        return "openclaw"
    if "ollama" in text:
        return "ollama"
    return "unknown"


def _primary_generator_family(row: dict[str, Any]) -> str | None:
    generators = row.get("role_packets", {}).get("generators", [])
    primary = generators[0] if generators else {}
    return _infer_model_family(
        primary.get("model"),
        primary.get("provider"),
        row.get("source_context", {}).get("generator_provider"),
    )


def _review_tags(review: dict[str, Any] | None) -> list[str]:
    if not review:
        return []
    metadata = review.get("metadata") or {}
    tags = metadata.get("reason_tags") or []
    if not isinstance(tags, list):
        return []
    return [str(tag).strip() for tag in tags if str(tag).strip()]


def _review_tag_attribution(review: dict[str, Any] | None) -> dict[str, list[str]]:
    empty = {"winner": [], "loser": [], "both": [], "unattributed": []}
    if not review:
        return empty
    metadata = review.get("metadata") or {}
    attribution = metadata.get("reason_tag_attribution") or {}
    normalized = {}
    for key in empty:
        values = attribution.get(key) or []
        if not isinstance(values, list):
            values = []
        normalized[key] = [str(tag).strip() for tag in values if str(tag).strip()]
    return normalized


def _review_tag_evidence(review: dict[str, Any] | None) -> list[dict[str, str]]:
    if not review:
        return []
    metadata = review.get("metadata") or {}
    evidence = metadata.get("reason_tag_evidence") or []
    normalized = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        excerpt = str(item.get("excerpt") or "").strip()
        target = str(item.get("target") or "").strip() or "unattributed"
        if not tag or not excerpt:
            continue
        normalized.append({
            "tag": tag,
            "target": target,
            "excerpt": excerpt,
        })
    return normalized


def _format_top_counter(counter: Counter, *, limit: int = 4, transform=None, empty: str = "- none yet") -> str:
    transform = transform or (lambda item: item)
    if not counter:
        return empty
    return "\n".join(f"- {transform(item)} ({count})" for item, count in counter.most_common(limit))


def _format_tag_phrase(tags: list[str]) -> str:
    readable = [humanize_tag(tag) for tag in tags if tag]
    if not readable:
        return ""
    if len(readable) == 1:
        return readable[0]
    if len(readable) == 2:
        return f"{readable[0]} and {readable[1]}"
    return ", ".join(readable[:-1]) + f", and {readable[-1]}"


def _format_bullet_list(items: list[str], *, empty: str = "- none yet") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def _format_excerpt_lines(items: list[dict[str, str]], *, empty: str = "- no excerpt evidence recorded yet", limit: int = 6) -> str:
    if not items:
        return empty
    lines = []
    seen = set()
    for item in items:
        key = (item.get("target"), item.get("tag"), item.get("excerpt"))
        if key in seen:
            continue
        seen.add(key)
        excerpt = _shorten(item.get("excerpt", ""), 180)
        lines.append(
            f"- {humanize_tag(item.get('target', 'unattributed'))} / {humanize_tag(item.get('tag', 'untagged'))}: \"{excerpt}\""
        )
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else empty


# ---------------------------------------------------------------------------
# Provenance + promotion
# ---------------------------------------------------------------------------

# Provenance states:
#   seeded    — from taste_memory.json, no packet evidence yet
#   emergent  — from human reason-tags crossing the emergence threshold
#   merged    — seeded entry with packet evidence attached
#   promoted  — meets full promotion criteria (evidence + structure + optional human gate)

def compute_provenance(
    *,
    is_seeded: bool,
    evidence_count: int,
    distinct_prompt_families: int | None = None,
    distinct_families: int | None = None,
    distinct_model_families: int = 0,
    has_correction_strategy: bool,
    human_confirmed: bool,
) -> str:
    """Determine the provenance state for a concept entry."""
    prompt_family_count = distinct_prompt_families if distinct_prompt_families is not None else (distinct_families or 0)

    if is_seeded and evidence_count == 0:
        return "seeded"
    if is_seeded and evidence_count > 0:
        # Check if it qualifies for promotion
        if (
            evidence_count >= PROMOTION_MIN_PACKETS
            and prompt_family_count >= PROMOTION_MIN_DISTINCT_FAMILIES
            and distinct_model_families >= PROMOTION_MIN_MODEL_FAMILIES
            and has_correction_strategy
            and human_confirmed
        ):
            return "promoted"
        return "merged"
    # Not seeded — must be emergent
    if (
        evidence_count >= PROMOTION_MIN_PACKETS
        and prompt_family_count >= PROMOTION_MIN_DISTINCT_FAMILIES
        and distinct_model_families >= PROMOTION_MIN_MODEL_FAMILIES
        and has_correction_strategy
        and human_confirmed
    ):
        return "promoted"
    return "emergent"


# ---------------------------------------------------------------------------
# Refinement history
# ---------------------------------------------------------------------------

_REFINEMENT_SECTION_MARKER = "## Refinement History"


def _read_existing_refinement_history(wiki_root: Path, page_path: Path) -> list[str]:
    """Read the refinement history entries from a previously compiled page."""
    full_path = wiki_root / page_path
    if not full_path.exists():
        return []
    text = full_path.read_text()
    if _REFINEMENT_SECTION_MARKER not in text:
        return []
    section = text.split(_REFINEMENT_SECTION_MARKER, 1)[1]
    # Stop at the next ## heading or end of file
    lines = []
    for line in section.strip().splitlines():
        if line.startswith("## ") and line.strip() != _REFINEMENT_SECTION_MARKER:
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            lines.append(stripped)
    return lines


def _append_history_entry(*, stamp: str, body: str, previous_entries: list[str]) -> list[str]:
    new_entry = f"- {stamp}: {body.strip().rstrip('.') }."
    if previous_entries:
        last = previous_entries[-1]
        last_body = last.split(": ", 1)[1] if ": " in last else last
        new_body = new_entry.split(": ", 1)[1] if ": " in new_entry else new_entry
        if last_body == new_body:
            return previous_entries
    return previous_entries + [new_entry]


def _packet_members(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        packet = row.get("comparison_packet") or {}
        packet_id = packet.get("packet_id")
        if packet_id and packet.get("explicit"):
            grouped[packet_id].append(row)
    for packet_id in list(grouped):
        grouped[packet_id] = sorted(
            grouped[packet_id],
            key=lambda row: (0 if row.get("packet_primary") else 1, row.get("id") or 0),
        )
    return grouped


def _judge_vote(members: list[dict[str, Any]], judge: str) -> tuple[int | None, float | None]:
    pairs = []
    for row in members:
        score = None
        for evaluator in row.get("role_packets", {}).get("evaluators", []):
            if evaluator.get("role_id") == judge:
                score = evaluator.get("scores", {}).get("composite")
                break
        if score is not None:
            pairs.append((row["id"], score))
    if len(pairs) < 2:
        return None, None
    pairs.sort(key=lambda item: item[1], reverse=True)
    if pairs[0][1] == pairs[1][1]:
        return None, 0.0
    return pairs[0][0], pairs[0][1] - pairs[1][1]


def _build_packet_summaries(
    packets: dict[str, list[dict[str, Any]]],
    review_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries = []
    for packet_id, members in packets.items():
        review = review_map.get(packet_id)
        judge_votes = {}
        vote_margins = {}
        for judge in ("muse", "athena", "apollo"):
            winner, margin = _judge_vote(members, judge)
            judge_votes[judge] = winner
            vote_margins[judge] = margin
        winner_row = next((row for row in members if row.get("id") == (review or {}).get("preferred_experiment_id")), None)
        tag_attribution = _review_tag_attribution(review)
        tag_evidence = _review_tag_evidence(review)
        decision_reason_tags = list(dict.fromkeys(
            tag_attribution["winner"] + tag_attribution["loser"] + tag_attribution["unattributed"]
        ))
        packet_model_families = sorted({
            family
            for family in (_primary_generator_family(member) for member in members)
            if family and family != "unknown"
        })
        summaries.append({
            "packet_id": packet_id,
            "members": members,
            "review": review,
            "prompt": members[0].get("prompt") or "",
            "family": members[0].get("prompt_family") or members[0].get("family") or "unclassified",
            "lane": members[0].get("lane") or "unknown",
            "condition": members[0].get("condition"),
            "judge_votes": judge_votes,
            "vote_margins": vote_margins,
            "reason_tags": _review_tags(review),
            "reason_tag_attribution": tag_attribution,
            "reason_tag_evidence": tag_evidence,
            "winner_reason_tags": tag_attribution["winner"],
            "loser_reason_tags": tag_attribution["loser"],
            "shared_reason_tags": tag_attribution["both"],
            "unattributed_reason_tags": tag_attribution["unattributed"],
            "decision_reason_tags": decision_reason_tags,
            "human_preferred_role": _generator_role(winner_row) if winner_row else None,
            "preferred_model_family": _primary_generator_family(winner_row) if winner_row else None,
            "packet_model_families": packet_model_families,
            "judge_human_disagreements": [
                judge
                for judge, winner in judge_votes.items()
                if review and winner is not None and winner != review.get("preferred_experiment_id")
            ],
        })
    return summaries


async def collect_wiki_context(limit: int = 400, epoch: str | None = None) -> dict[str, Any]:
    await db.init_db()
    current_epoch = epoch or db.CURRENT_EXPERIMENT_EPOCH
    records = await db.get_recent_experiments(limit=limit, epoch=current_epoch)
    reviews = await db.get_recent_calibration_reviews(limit=limit, epoch=current_epoch)
    review_map = {review["packet_id"]: review for review in reviews if review.get("packet_id")}
    packets = _packet_members(records)
    packet_summaries = _build_packet_summaries(packets, review_map)
    taste = load_taste_memory()
    council_history = await db.get_council_history(limit=25)
    rule_proposals = await db.compute_rule_promotion_proposals()
    return {
        "records": records,
        "packets": packets,
        "packet_summaries": packet_summaries,
        "reviews": reviews,
        "review_map": review_map,
        "epoch": current_epoch,
        "taste": taste,
        "taste_by_tag": _taste_entries_by_tag(taste),
        "council_history": council_history,
        "rule_proposals": rule_proposals.get("proposals", []),
    }


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def _empty_concept_characterization():
    return {
        "label": "insufficient_data",
        "panel_preference_rate": "null",
        "human_alignment_rate": "null",
        "rule_id": "null",
        "section": "hypothesis — no panel evidence yet",
    }


def _concept_rule_characterizations(proposals):
    by_tag = {}
    for proposal in proposals or []:
        title = str(proposal.get("title") or "")
        rule_key = str(proposal.get("rule_key") or "")
        candidates = {
            slugify(title),
            slugify(rule_key.split("::")[-1]),
            slugify(rule_key.replace("::", "-")),
        }
        metrics = proposal.get("metrics") or {}
        total_slices = int(metrics.get("total_slices") or 0)
        evaluator_helped = int(metrics.get("evaluator_helped") or 0)
        human_win_rate = metrics.get("human_win_rate")
        panel_rate = (evaluator_helped / total_slices) if total_slices else None
        rule_id = proposal.get("rule_id")
        label = proposal.get("characterization") or "insufficient_data"
        section = (
            f"- rule_id: {rule_id}\n"
            f"- characterization: {label}\n"
            f"- panel preference: {evaluator_helped}/{total_slices}"
        )
        if panel_rate is not None:
            section += f" ({panel_rate:.2f})"
        section += "\n"
        if human_win_rate is None:
            section += "- human alignment rate: null\n"
        else:
            section += f"- human alignment rate: {human_win_rate:.2f}\n"
        section += f"- decisive human reviews: {int(metrics.get('human_decisive') or 0)}"
        payload = {
            "label": label,
            "panel_preference_rate": "null" if panel_rate is None else f"{panel_rate:.3f}",
            "human_alignment_rate": "null" if human_win_rate is None else f"{float(human_win_rate):.3f}",
            "rule_id": "null" if rule_id is None else str(rule_id),
            "section": section,
        }
        for candidate in candidates:
            if candidate:
                by_tag.setdefault(candidate, payload)
    return by_tag


def build_packet_pages(context: dict[str, Any]) -> list[dict[str, Any]]:
    template = _load_template("packet_outcome.md")
    pages = []
    for summary in context["packet_summaries"]:
        review = summary["review"]
        vote_lines = []
        for judge in ("muse", "athena", "apollo"):
            winner = summary["judge_votes"][judge]
            margin = summary["vote_margins"][judge]
            if winner is None:
                vote_lines.append(f"- {role_label(judge)}: split")
            else:
                vote_lines.append(f"- {role_label(judge)}: prefers #{winner} (Δ {margin:.2f})")
        member_sections = []
        source_packets = []
        for idx, member in enumerate(summary["members"]):
            artifact_label = chr(65 + idx)
            source_packets.append(str(member.get("id")))
            evaluators = member.get("role_packets", {}).get("evaluators", [])
            score_line = " · ".join(
                f"{role_label(evaluator.get('role_id'))} {evaluator.get('scores', {}).get('composite', '--'):.2f}"
                if isinstance(evaluator.get("scores", {}).get("composite"), (int, float))
                else f"{role_label(evaluator.get('role_id'))} --"
                for evaluator in evaluators
            ) or "No evaluator scores recorded."
            member_sections.append(
                f"## Artifact {artifact_label}\n"
                f"- experiment_id: {member.get('id')}\n"
                f"- generator: {role_label(_generator_role(member))}\n"
                f"- outcome: {member.get('status')} / {member.get('promotion_status')}\n"
                f"- judges: {score_line}\n\n"
                f"{member.get('artifact') or '(no artifact)'}\n"
            )
        tags = summary["reason_tags"]
        decisive_tags = summary["decision_reason_tags"]
        winner_tags = summary["winner_reason_tags"]
        loser_tags = summary["loser_reason_tags"]
        shared_tags = summary["shared_reason_tags"]
        unattributed_tags = summary["unattributed_reason_tags"]
        evidence_lines = _format_excerpt_lines(summary["reason_tag_evidence"])
        takeaway_tags = winner_tags or decisive_tags
        if review and takeaway_tags and summary["human_preferred_role"]:
            key_takeaway = (
                f"Human review preferred {role_label(summary['human_preferred_role'])} for "
                f"{_format_tag_phrase(takeaway_tags[:3])}."
            )
        elif review:
            key_takeaway = "Human-confirmed packet."
        else:
            key_takeaway = "Awaiting or not routed to human review."
        content = template.safe_substitute(
            packet_id=summary["packet_id"],
            lane=summary["lane"],
            family=summary["family"],
            condition=condition_label(summary["condition"]),
            prompt=summary["prompt"],
            judges="\n".join(vote_lines),
            human_preference=(f"#{review['preferred_experiment_id']}" if review else "not yet reviewed"),
            rationale=(review.get("rationale") if review else "No human rationale yet."),
            reason_tags=(", ".join(tags) or "none recorded"),
            winner_reason_tags=(", ".join(winner_tags) or "none recorded"),
            loser_reason_tags=(", ".join(loser_tags) or "none recorded"),
            shared_reason_tags=(", ".join(shared_tags) or "none recorded"),
            unattributed_reason_tags=(", ".join(unattributed_tags) or "none recorded"),
            evidence_excerpts=evidence_lines,
            key_takeaway=key_takeaway,
            member_sections="\n".join(member_sections),
        )
        pages.append({
            "path": Path(GENERATED_DIRS["packets"]) / f"{summary['packet_id']}.md",
            "content": content,
            "packet_id": summary["packet_id"],
            "family": summary["family"],
            "lane": summary["lane"],
            "reviewed": bool(review),
            "source_packets": source_packets,
        })
    return pages


def build_family_pages(context: dict[str, Any], packet_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    template = _load_template("task_family.md")
    taste = context["taste"]
    by_family: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "records": [],
            "packets": [],
            "lanes": set(),
            "generators": Counter(),
            "human_reviews": 0,
            "reason_tags": Counter(),
            "winning_tags": Counter(),
            "losing_tags": Counter(),
            "judge_disagreement_tags": Counter(),
            "human_preferred_roles": Counter(),
        }
    )
    for row in context["records"]:
        family = row.get("prompt_family") or row.get("family") or "unclassified"
        by_family[family]["records"].append(row)
        by_family[family]["lanes"].add(row.get("lane") or "unknown")
        primary = row.get("role_packets", {}).get("generators", [{}])[0]
        if primary.get("role_id"):
            by_family[family]["generators"][primary["role_id"]] += 1
    for page in packet_pages:
        by_family[page["family"]]["packets"].append(page)
    for summary in context["packet_summaries"]:
        family = summary["family"]
        tags = summary["decision_reason_tags"]
        if summary["review"]:
            by_family[family]["human_reviews"] += 1
            if summary["human_preferred_role"]:
                by_family[family]["human_preferred_roles"][summary["human_preferred_role"]] += 1
        by_family[family]["reason_tags"].update(tags)
        by_family[family]["winning_tags"].update(summary["winner_reason_tags"])
        by_family[family]["losing_tags"].update(summary["loser_reason_tags"])
        if summary["judge_human_disagreements"]:
            by_family[family]["judge_disagreement_tags"].update(tags)

    pages = []
    for family, bucket in sorted(by_family.items()):
        strongest = bucket["generators"].most_common(1)
        recurring = [humanize_tag(tag) for tag, _ in bucket["winning_tags"].most_common(3)]
        disagreement = [humanize_tag(tag) for tag, _ in bucket["judge_disagreement_tags"].most_common(3)]
        contradiction_lines = []
        if len(bucket["human_preferred_roles"]) > 1:
            contradiction_lines.append(
                f"Human review is not settled here yet: preferences split across "
                f"{', '.join(role_label(role) for role, _ in bucket['human_preferred_roles'].most_common())}."
            )
        if disagreement:
            contradiction_lines.append(
                f"Judge/human disagreement in this family most often clusters around {_format_tag_phrase(disagreement)}."
            )
        if bucket["packets"] and not bucket["human_reviews"]:
            contradiction_lines.append(
                "This family has explicit packet evidence but no human calibration yet, so current beliefs may be overly evaluator-shaped."
            )

        # Gather anti-patterns relevant to this family's lanes
        family_lanes = bucket["lanes"] or {"unknown"}
        relevant_anti_patterns = []
        for lane in family_lanes:
            for entry in _taste_entries_for_lane(taste, lane, "anti_patterns"):
                if entry["tag"] not in [e["tag"] for e in relevant_anti_patterns]:
                    relevant_anti_patterns.append(entry)
        anti_pattern_lines = _format_bullet_list(
            [f"{entry['name']} ({entry['id']}): {entry['description'][:120]}..." if len(entry.get('description', '')) > 120
             else f"{entry['name']} ({entry['id']}): {entry.get('description', '')}"
             for entry in relevant_anti_patterns[:5]],
            empty="- no lane-specific anti-patterns seeded yet",
        )

        # Gather quality signals relevant to this family's lanes
        relevant_signals = []
        for lane in family_lanes:
            for entry in _taste_entries_for_lane(taste, lane, "quality_signals"):
                if entry["tag"] not in [e["tag"] for e in relevant_signals]:
                    relevant_signals.append(entry)
        quality_signal_lines = _format_bullet_list(
            [f"{entry['name']} ({entry['id']}): {entry.get('description', '')[:120]}..."
             if len(entry.get('description', '')) > 120
             else f"{entry['name']} ({entry['id']}): {entry.get('description', '')}"
             for entry in relevant_signals[:5]],
            empty="- no lane-specific quality signals seeded yet",
        )

        content = template.safe_substitute(
            family=family,
            evidence_count=len(bucket["records"]),
            confidence=confidence_label(len(bucket["packets"]), human_confirmed=bucket["human_reviews"] > 0),
            status=page_status(len(bucket["packets"]), human_confirmed=bucket["human_reviews"] > 0),
            what_it_tests=f"This family currently probes {family.replace('_', ' ')} under comparative judgment.",
            failure_modes=(
                "- generic language\n- evaluator disagreement without clear human tie-break"
                if bucket["records"] else "- not enough evidence yet"
            ),
            anti_patterns_observed=anti_pattern_lines,
            strong_outputs=(
                f"Human-reviewed winners in this family most often carry {_format_tag_phrase(recurring)}."
                if recurring else
                ("Strong outputs in this family tend to combine constraint fit with memorable voice." if bucket["records"] else "Not enough evidence yet.")
            ),
            quality_signals_observed=quality_signal_lines,
            judge_patterns=(
                f"When judges and humans split in this family, the fault line most often involves {_format_tag_phrase(disagreement)}."
                if disagreement else
                ("Judges often converge on coherence first and split on vividness or pressure." if bucket["packets"] else "No explicit packet evidence yet.")
            ),
            contradictions=_format_bullet_list(
                contradiction_lines,
                empty="- no explicit family-level contradictions recorded yet",
            ),
            current_leader=(role_label(strongest[0][0]) if strongest else "No leader yet"),
            confidence_note=(
                f"{len(bucket['packets'])} explicit packets, {bucket['human_reviews']} human-reviewed."
                if bucket["packets"] else "No explicit packet pages yet."
            ),
            recurring_human_signals=_format_top_counter(bucket["reason_tags"], transform=humanize_tag),
            related_packets="\n".join(f"- [[packets/{page['packet_id']}]]" for page in bucket["packets"][:8]) or "- none yet",
        )
        pages.append({
            "path": Path(GENERATED_DIRS["families"]) / f"{slugify(family)}.md",
            "content": content,
            "family": family,
            "human_reviews": bucket["human_reviews"],
            "packet_count": len(bucket["packets"]),
        })
    return pages


def build_model_pages(context: dict[str, Any]) -> list[dict[str, Any]]:
    template = _load_template("model_voice.md")
    by_role: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "records": [],
            "families": Counter(),
            "review_wins": 0,
            "review_losses": 0,
            "winning_tags": Counter(),
            "losing_tags": Counter(),
            "disagreement_tags": Counter(),
        }
    )
    for row in context["records"]:
        generator = _generator_role(row)
        by_role[generator]["records"].append(row)
        family = row.get("prompt_family") or row.get("family") or "unclassified"
        by_role[generator]["families"][family] += 1
    for summary in context["packet_summaries"]:
        preferred_role = summary["human_preferred_role"]
        if not preferred_role:
            continue
        for member in summary["members"]:
            role_id = _generator_role(member)
            if role_id == preferred_role:
                by_role[role_id]["review_wins"] += 1
                by_role[role_id]["winning_tags"].update(summary["winner_reason_tags"])
            else:
                by_role[role_id]["review_losses"] += 1
                by_role[role_id]["losing_tags"].update(summary["loser_reason_tags"])
            if summary["judge_human_disagreements"]:
                if role_id == preferred_role:
                    by_role[role_id]["disagreement_tags"].update(summary["winner_reason_tags"])
                else:
                    by_role[role_id]["disagreement_tags"].update(summary["loser_reason_tags"])

    pages = []
    for role_id, bucket in sorted(by_role.items()):
        best_families = ", ".join(f.replace("_", " ") for f, _ in bucket["families"].most_common(3)) or "No stable pattern yet"
        strengths = (
            f"Human-reviewed wins most often mention {_format_tag_phrase([tag for tag, _ in bucket['winning_tags'].most_common(3)])}."
            if bucket["winning_tags"] else
            (f"Most frequent strong families: {best_families}." if bucket["records"] else "No strengths established yet.")
        )
        weaknesses = (
            f"Losses are most often associated with {_format_tag_phrase([tag for tag, _ in bucket['losing_tags'].most_common(3)])}."
            if bucket["losing_tags"] else
            "Weaknesses remain provisional until more human-reviewed packets accumulate."
        )
        disagreement_patterns = (
            f"When judges and humans split, this voice is most often entangled with {_format_tag_phrase([tag for tag, _ in bucket['disagreement_tags'].most_common(3)])}."
            if bucket["disagreement_tags"] else
            "Track against evaluator and human disagreement as more reviewed packets accumulate."
        )
        content = template.safe_substitute(
            role=role_label(role_id),
            role_id=role_id,
            evidence_count=len(bucket["records"]),
            confidence=confidence_label(len(bucket["records"]), human_confirmed=bucket["review_wins"] > 0),
            status=page_status(len(bucket["records"]), human_confirmed=bucket["review_wins"] > 0),
            tendencies=(
                f"This voice most often appears in {best_families}."
                if bucket["records"] else "No stable tendencies established yet."
            ),
            strengths=strengths,
            weaknesses=weaknesses,
            best_families=best_families,
            family_gaps="Not enough evidence for a reliable weak-family map yet.",
            disagreement_patterns=disagreement_patterns,
            recurring_signals=_format_top_counter(bucket["winning_tags"], transform=humanize_tag),
            representative_examples="\n".join(
                f"- experiment #{row.get('id')} · {(row.get('prompt_family') or row.get('family') or 'unclassified').replace('_', ' ')} · Muse {row.get('composite', '--'):.2f}"
                if isinstance(row.get("composite"), (int, float))
                else f"- experiment #{row.get('id')}"
                for row in bucket["records"][:6]
            ) or "- none yet",
            trend=("human-confirmed" if bucket["review_wins"] > bucket["review_losses"] else "provisional"),
        )
        pages.append({"path": Path(GENERATED_DIRS["models"]) / f"{slugify(role_id)}.md", "content": content})
    return pages


def build_evaluator_pages(context: dict[str, Any]) -> list[dict[str, Any]]:
    template = _load_template("evaluator.md")
    taste = context["taste"]
    evaluator_failure_entries = taste.get("evaluator_failure_modes", {}).get("entries", [])
    existing_refinements = context.get("existing_refinements", {})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    judges = ("muse", "athena", "apollo")
    pages = []
    for judge in judges:
        judged = 0
        aligned = 0
        splits = 0
        lane_totals = Counter()
        lane_aligned = Counter()
        family_totals = Counter()
        family_aligned = Counter()
        hit_tags = Counter()
        miss_tags = Counter()
        examples = []
        for summary in context["packet_summaries"]:
            winner = summary["judge_votes"][judge]
            review = summary["review"]
            if winner is None:
                splits += 1
            if review:
                judged += 1
                lane_totals[summary["lane"]] += 1
                family_totals[summary["family"]] += 1
                if winner == review.get("preferred_experiment_id"):
                    aligned += 1
                    lane_aligned[summary["lane"]] += 1
                    family_aligned[summary["family"]] += 1
                    hit_tags.update(summary["decision_reason_tags"])
                else:
                    miss_tags.update(summary["decision_reason_tags"])
            if len(examples) < 6:
                examples.append(f"- [[packets/{summary['packet_id']}]] · winner {('#' + str(winner)) if winner else 'split'}")
        contested = judged > 0 and aligned / judged < 0.5
        lane_lines = "\n".join(
            f"- {lane}: {lane_aligned[lane]}/{total} aligned with human review"
            for lane, total in sorted(lane_totals.items())
        ) or "No lane-specific human-reviewed evidence yet."
        contradiction_lines = []
        lane_rates = {
            lane: (lane_aligned[lane] / total)
            for lane, total in lane_totals.items()
            if total
        }
        if lane_rates:
            best_lane = max(lane_rates, key=lane_rates.get)
            worst_lane = min(lane_rates, key=lane_rates.get)
            if best_lane != worst_lane and lane_rates[best_lane] != lane_rates[worst_lane]:
                contradiction_lines.append(
                    f"This judge behaves unevenly by lane: {best_lane} currently aligns at {lane_rates[best_lane]:.0%}, "
                    f"while {worst_lane} aligns at {lane_rates[worst_lane]:.0%}."
                )
        weak_families = [
            family.replace("_", " ")
            for family, total in family_totals.items()
            if total >= 2 and family_aligned[family] / total < 0.5
        ]
        if weak_families:
            contradiction_lines.append(
                f"Family-specific drift is visible in {', '.join(weak_families[:3])}."
            )
        if miss_tags:
            contradiction_lines.append(
                f"Human/judge splits repeatedly involve {_format_tag_phrase([tag for tag, _ in miss_tags.most_common(3)])}."
            )

        # Known evaluator failure modes from taste memory
        # Show all seeded failure modes; as evidence accumulates, entries with
        # affected_judges matching this judge get highlighted.
        failure_mode_lines = []
        for ef in evaluator_failure_entries:
            affected = ef.get("affected_judges", [])
            if affected and judge not in affected:
                continue
            marker = " **(observed)**" if judge in affected else ""
            failure_mode_lines.append(f"{ef['name']} ({ef['id']}): {ef.get('description', '')[:140]}{marker}")
        failure_modes_text = _format_bullet_list(
            failure_mode_lines,
            empty="- no seeded evaluator failure modes yet; watch for systematic human/judge divergence",
        )
        page_path = Path(GENERATED_DIRS["evaluators"]) / f"{slugify(judge)}.md"
        previous_entries = existing_refinements.get(str(page_path), [])
        strongest_miss_signal = (
            _format_tag_phrase([tag for tag, _ in miss_tags.most_common(2)])
            if miss_tags else
            "no repeated miss tags yet"
        )
        history_body = (
            f"{aligned}/{judged} aligned with human review, {splits} split packet(s), "
            f"strongest misses around {strongest_miss_signal}"
        )
        refinement_history = "\n".join(
            _append_history_entry(stamp=stamp, body=history_body, previous_entries=previous_entries)
        )

        content = template.safe_substitute(
            judge=role_label(judge),
            role_id=judge,
            evidence_count=len(context["packets"]),
            confidence=confidence_label(judged or len(context["packets"]), human_confirmed=judged > 0, contested=contested),
            status=page_status(judged or len(context["packets"]), human_confirmed=judged > 0, contested=contested),
            alignment=(f"{aligned}/{judged} aligned with human-reviewed packets" if judged else "No human-reviewed packets yet."),
            lane_behavior=lane_lines,
            biases=(
                f"This judge most often misses packets tagged {_format_tag_phrase([tag for tag, _ in miss_tags.most_common(3)])}."
                if miss_tags else
                "Bias patterns should be revised only from repeated packet evidence."
            ),
            failure_modes=failure_modes_text,
            stability="Rerun stability not yet compiled into this page.",
            disagreement_frequency=f"{splits} packet splits across {len(context['packets'])} explicit packets.",
            blind_spots=(
                f"Recurring misses currently cluster around {_format_tag_phrase([tag for tag, _ in miss_tags.most_common(4)])}."
                if miss_tags else
                "Look especially for cases where vividness, trust, or symbolic pressure are penalized."
            ),
            contradictions=_format_bullet_list(
                contradiction_lines,
                empty="- no explicit evaluator contradictions recorded yet",
            ),
            high_signal_tags=_format_top_counter(hit_tags, transform=humanize_tag),
            examples="\n".join(examples) or "- none yet",
            refinement_history=refinement_history or f"- {stamp}: no evaluator revision history yet.",
        )
        pages.append({"path": page_path, "content": content})
    return pages


def build_concept_pages(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Build concept pages from two sources, with explicit provenance.

    1. Seeded entries from taste_memory.json (anti-patterns, quality signals,
       evaluator failure modes). Always produce pages.
    2. Emergent tags from human review. Produce pages only when the tag
       recurs in CONCEPT_EMERGENCE_THRESHOLD or more packets.

    Provenance states:
      seeded   — from taste memory, no packet evidence yet
      emergent — from human tags crossing the emergence threshold
      merged   — seeded entry with packet evidence attached
      promoted — meets full promotion criteria
    """
    template = _load_template("concept.md")
    rule_characterizations = _concept_rule_characterizations(context.get("rule_proposals", []))

    # Collect emergent tag evidence from packet summaries
    decisive_tag_packets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    shared_tag_packets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unattributed_tag_packets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    excerpt_evidence_by_tag: dict[str, list[dict[str, str]]] = defaultdict(list)
    families_by_tag: dict[str, Counter] = defaultdict(Counter)
    model_families_by_tag: dict[str, Counter] = defaultdict(Counter)
    judges_by_tag: dict[str, Counter] = defaultdict(Counter)
    attribution_by_tag: dict[str, Counter] = defaultdict(Counter)
    for summary in context["packet_summaries"]:
        for tag in set(summary["decision_reason_tags"]):
            decisive_tag_packets[tag].append(summary)
            families_by_tag[tag][summary["family"]] += 1
            for model_family in summary.get("packet_model_families") or []:
                model_families_by_tag[tag][model_family] += 1
            for judge in summary["judge_human_disagreements"]:
                judges_by_tag[tag][judge] += 1
        for tag in set(summary["winner_reason_tags"]):
            attribution_by_tag[tag]["winner"] += 1
        for tag in set(summary["loser_reason_tags"]):
            attribution_by_tag[tag]["loser"] += 1
        for tag in set(summary["shared_reason_tags"]):
            shared_tag_packets[tag].append(summary)
            attribution_by_tag[tag]["both"] += 1
        for tag in set(summary["unattributed_reason_tags"]):
            unattributed_tag_packets[tag].append(summary)
            attribution_by_tag[tag]["unattributed"] += 1
        for item in summary.get("reason_tag_evidence") or []:
            excerpt_evidence_by_tag[item["tag"]].append(item)

    built_tags: set[str] = set()
    pages = []

    # Pass 1: seeded entries
    all_seeded = []
    for section in ("anti_patterns", "quality_signals", "evaluator_failure_modes"):
        for entry in context["taste"].get(section, {}).get("entries", []):
            all_seeded.append((section, entry))

    for section, entry in all_seeded:
        tag = entry["tag"]
        built_tags.add(tag)
        packets = decisive_tag_packets.get(tag, [])
        shared_packets = shared_tag_packets.get(tag, [])
        unattributed_packets = unattributed_tag_packets.get(tag, [])
        evidence_count = len(packets)
        distinct_prompt_families = len(families_by_tag.get(tag, Counter()))
        distinct_model_families = len(model_families_by_tag.get(tag, Counter()))
        has_correction = bool(entry.get("correction_strategy"))
        has_human_review = any(s.get("review") for s in packets)

        if section == "anti_patterns":
            domain = "anti-pattern"
        elif section == "quality_signals":
            domain = "quality-signal"
        else:
            domain = "evaluator-failure"

        provenance = compute_provenance(
            is_seeded=True,
            evidence_count=evidence_count,
            distinct_prompt_families=distinct_prompt_families,
            distinct_model_families=distinct_model_families,
            has_correction_strategy=has_correction,
            human_confirmed=has_human_review,
        )

        source = entry.get("source", "seed")
        if evidence_count > 0:
            source = f"{source} + {evidence_count} packets"
        characterization = rule_characterizations.get(slugify(tag)) or _empty_concept_characterization()

        contested = len({s["human_preferred_role"] for s in packets if s["human_preferred_role"]}) > 1 if packets else False

        examples_bad_lines = _format_bullet_list(
            [f'"{ex}"' for ex in entry.get("examples_bad", [])],
            empty="- none seeded",
        )
        examples_good_lines = _format_bullet_list(
            [f'"{ex}"' for ex in entry.get("examples_good", [])],
            empty="- none seeded",
        )

        content = template.safe_substitute(
            tag=entry.get("name", humanize_tag(tag)),
            tag_id=tag,
            domain=domain,
            provenance=provenance,
            evidence_count=evidence_count,
            distinct_prompt_families=distinct_prompt_families,
            distinct_model_families=distinct_model_families,
            attribution_mix=_format_bullet_list(
                [
                    f"winner-tagged packets: {attribution_by_tag[tag].get('winner', 0)}",
                    f"loser-tagged packets: {attribution_by_tag[tag].get('loser', 0)}",
                    f"shared packets: {len(shared_packets)}",
                    f"legacy unattributed packets: {len(unattributed_packets)}",
                ]
            ),
            confidence=confidence_label(evidence_count, human_confirmed=has_human_review, contested=contested),
            status=page_status(evidence_count, human_confirmed=has_human_review, contested=contested),
            source=source,
            characterization=characterization["label"],
            panel_preference_rate=characterization["panel_preference_rate"],
            human_alignment_rate=characterization["human_alignment_rate"],
            rule_id=characterization["rule_id"],
            characterization_section=characterization["section"],
            detection_difficulty=entry.get("detection_difficulty", "unknown"),
            description=entry.get("description", ""),
            why_it_matters=entry.get("why_it_fails", entry.get("why_it_works", "This concept is part of the lab's seeded taste vocabulary.")),
            correction_strategy=entry.get("correction_strategy", "No correction strategy documented yet."),
            examples_bad=examples_bad_lines,
            examples_good=examples_good_lines,
            positive_examples=(
                "\n".join(f"- [[packets/{s['packet_id']}]]" for s in packets[:4])
                if packets else "- no packet evidence yet"
            ),
            negative_examples="- awaiting packet evidence",
            related_families=_format_top_counter(families_by_tag.get(tag, Counter()), transform=lambda item: item.replace("_", " ")),
            affected_models=_format_top_counter(model_families_by_tag.get(tag, Counter()), transform=model_family_label),
            disagreement_links=_format_top_counter(judges_by_tag.get(tag, Counter()), transform=role_label),
            evidence_excerpts=_format_excerpt_lines(excerpt_evidence_by_tag.get(tag, [])),
            packet_evidence=(
                "\n".join(f"- [[packets/{s['packet_id']}]] ({s['family']})" for s in packets[:6])
                if packets else "- none yet — this concept is seeded from taste memory and awaiting empirical grounding"
            ),
        )
        pages.append({
            "path": Path(GENERATED_DIRS["concepts"]) / f"{slugify(tag)}.md",
            "content": content,
            "tag": tag,
            "domain": domain,
            "provenance": provenance,
            "evidence_count": evidence_count,
            "distinct_prompt_families": distinct_prompt_families,
            "distinct_model_families": distinct_model_families,
            "shared_packet_count": len(shared_packets),
            "unattributed_packet_count": len(unattributed_packets),
            "entry": entry,
        })

    # Pass 2: emergent tags
    for tag, packets in sorted(decisive_tag_packets.items()):
        if tag in built_tags:
            continue
        if len(packets) < CONCEPT_EMERGENCE_THRESHOLD:
            continue
        built_tags.add(tag)
        shared_packets = shared_tag_packets.get(tag, [])
        unattributed_packets = unattributed_tag_packets.get(tag, [])
        distinct_prompt_families = len(families_by_tag.get(tag, Counter()))
        distinct_model_families = len(model_families_by_tag.get(tag, Counter()))
        has_human_review = any(s.get("review") for s in packets)
        contested = len({s["human_preferred_role"] for s in packets if s["human_preferred_role"]}) > 1
        characterization = rule_characterizations.get(slugify(tag)) or _empty_concept_characterization()

        provenance = compute_provenance(
            is_seeded=False,
            evidence_count=len(packets),
            distinct_prompt_families=distinct_prompt_families,
            distinct_model_families=distinct_model_families,
            has_correction_strategy=False,
            human_confirmed=has_human_review,
        )

        content = template.safe_substitute(
            tag=humanize_tag(tag),
            tag_id=tag,
            domain="emergent",
            provenance=provenance,
            evidence_count=len(packets),
            distinct_prompt_families=distinct_prompt_families,
            distinct_model_families=distinct_model_families,
            attribution_mix=_format_bullet_list(
                [
                    f"winner-tagged packets: {attribution_by_tag[tag].get('winner', 0)}",
                    f"loser-tagged packets: {attribution_by_tag[tag].get('loser', 0)}",
                    f"shared packets: {len(shared_packets)}",
                    f"legacy unattributed packets: {len(unattributed_packets)}",
                ]
            ),
            confidence=confidence_label(len(packets), human_confirmed=has_human_review, contested=contested),
            status=page_status(len(packets), human_confirmed=has_human_review, contested=contested),
            source=f"emergent from {len(packets)} packets",
            characterization=characterization["label"],
            panel_preference_rate=characterization["panel_preference_rate"],
            human_alignment_rate=characterization["human_alignment_rate"],
            rule_id=characterization["rule_id"],
            characterization_section=characterization["section"],
            detection_difficulty="unknown",
            description="This concept emerged from recurring human reason-tags across multiple packets.",
            why_it_matters="This concept now recurs often enough in human review to function as part of the lab's quality vocabulary.",
            correction_strategy="Not yet documented. As evidence accumulates, derive a correction strategy from the pattern of human preferences.",
            examples_bad="- awaiting analysis",
            examples_good="- awaiting analysis",
            positive_examples="\n".join(f"- [[packets/{s['packet_id']}]]" for s in packets[:4]) or "- none yet",
            negative_examples="- none yet",
            related_families=_format_top_counter(families_by_tag[tag], transform=lambda item: item.replace("_", " ")),
            affected_models=_format_top_counter(model_families_by_tag[tag], transform=model_family_label),
            disagreement_links=_format_top_counter(judges_by_tag[tag], transform=role_label),
            evidence_excerpts=_format_excerpt_lines(excerpt_evidence_by_tag.get(tag, [])),
            packet_evidence="\n".join(f"- [[packets/{s['packet_id']}]] ({s['family']})" for s in packets[:6]) or "- none yet",
        )
        pages.append({
            "path": Path(GENERATED_DIRS["concepts"]) / f"{slugify(tag)}.md",
            "content": content,
            "tag": tag,
            "domain": "emergent",
            "provenance": provenance,
            "evidence_count": len(packets),
            "distinct_prompt_families": distinct_prompt_families,
            "distinct_model_families": distinct_model_families,
            "shared_packet_count": len(shared_packets),
            "unattributed_packet_count": len(unattributed_packets),
            "entry": None,
        })

    return pages


def build_lesson_pages(context: dict[str, Any]) -> list[dict[str, Any]]:
    template = _load_template("lesson.md")
    taste_by_tag = context["taste_by_tag"]
    existing_refinements = context.get("existing_refinements", {})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lessons = []
    by_family_wins: dict[str, Counter] = defaultdict(Counter)
    evidence_packets: dict[tuple[str, str], list[str]] = defaultdict(list)
    family_role_tags: dict[tuple[str, str], Counter] = defaultdict(Counter)
    family_disagreement_tags: dict[str, Counter] = defaultdict(Counter)
    for summary in context["packet_summaries"]:
        if not summary["review"] or not summary["human_preferred_role"]:
            continue
        family = summary["family"]
        role_id = summary["human_preferred_role"]
        by_family_wins[family][role_id] += 1
        evidence_packets[(family, role_id)].append(summary["packet_id"])
        family_role_tags[(family, role_id)].update(summary["winner_reason_tags"])
        family_disagreement_tags[family].update(summary["winner_reason_tags"] if summary["judge_human_disagreements"] else [])

    for family, winners in sorted(by_family_wins.items()):
        role_id, count = winners.most_common(1)[0]
        contested = len(winners) > 1
        recurring_tags = [tag for tag, _ in family_role_tags[(family, role_id)].most_common(3)]
        disagreement_tags = [tag for tag, _ in family_disagreement_tags[family].most_common(2)]

        if recurring_tags:
            statement = (
                f"In {family.replace('_', ' ')} tasks, human review currently rewards "
                f"{_format_tag_phrase(recurring_tags)}, which is presently favoring {role_label(role_id)}."
            )
        else:
            statement = f"In {family.replace('_', ' ')} tasks, human review currently prefers {role_label(role_id)}."

        conf = confidence_label(count, human_confirmed=True, contested=contested)
        confidence_note = "Human-reviewed once; treat as tentative."
        if count > 1 and recurring_tags:
            confidence_note = f"Repeated human-reviewed signal. The strongest recurring reasons are {_format_tag_phrase(recurring_tags)}."
        elif count > 1:
            confidence_note = "Human-reviewed and repeated."
        if disagreement_tags:
            confidence_note += f" Automated judges most often resist this lesson around {_format_tag_phrase(disagreement_tags)}."
        contradiction_lines = []
        if contested:
            contradiction_lines.append(
                f"Human review is still split in {family.replace('_', ' ')}; other packet evidence favors "
                f"{', '.join(role_label(other_role) for other_role in winners if other_role != role_id)}."
            )
        if disagreement_tags:
            contradiction_lines.append(
                f"Automated judges repeatedly resist this lesson around {_format_tag_phrase(disagreement_tags)}."
            )

        # Related concepts
        related_concept_lines = []
        for tag in recurring_tags:
            if tag in taste_by_tag:
                entry = taste_by_tag[tag]
                related_concept_lines.append(f"[[concepts/{slugify(tag)}|{entry.get('name', humanize_tag(tag))}]]")
            elif tag in {t for t, _ in family_role_tags[(family, role_id)].most_common(10)}:
                related_concept_lines.append(f"[[concepts/{slugify(tag)}|{humanize_tag(tag)}]] (emergent)")
        related_concepts = _format_bullet_list(related_concept_lines, empty="- no linked concepts yet")

        # Refinement history — read from snapshotted entries, diff, append only if changed
        page_path = Path(GENERATED_DIRS["lessons"]) / f"{slugify(family)}-{slugify(role_id)}.md"
        previous_entries = existing_refinements.get(str(page_path), [])
        refinement_entries = _append_history_entry(
            stamp=stamp,
            body=(
                f"{count} supporting packet(s), confidence {conf}"
                f"{', contested' if contested else ''}"
                f"; recurring signals: {_format_tag_phrase(recurring_tags) if recurring_tags else 'none yet'}"
            ),
            previous_entries=previous_entries,
        )
        if not refinement_entries:
            refinement_entries = [f"- {stamp}: initial compilation. {count} supporting packet(s), confidence {conf}."]
        refinement_history = "\n".join(refinement_entries)

        content = template.safe_substitute(
            title=statement,
            evidence_count=count,
            confidence=conf,
            status=page_status(count, human_confirmed=True, contested=contested),
            lesson_statement=statement,
            supporting_packets="\n".join(f"- [[packets/{packet_id}]]" for packet_id in evidence_packets[(family, role_id)]) or "- none yet",
            dissenting_packets="\n".join(
                f"- [[packets/{packet_id}]]"
                for other_role, _other_count in winners.items()
                if other_role != role_id
                for packet_id in evidence_packets.get((family, other_role), [])
            ) or "- none yet",
            confidence_note=confidence_note,
            recurring_signals=("\n".join(f"- {humanize_tag(tag)}" for tag in recurring_tags) if recurring_tags else "- no repeated tags yet"),
            contradictions=_format_bullet_list(
                contradiction_lines,
                empty="- no explicit lesson contradictions recorded yet",
            ),
            related_concepts=related_concepts,
            refinement_history=refinement_history,
            human_confirmed="yes",
        )
        lessons.append({"path": page_path, "content": content})

    if not lessons:
        page_path = Path(GENERATED_DIRS["lessons"]) / "no-stable-lessons-yet.md"
        previous_entries = existing_refinements.get(str(page_path), [])
        refinement_entries = _append_history_entry(
            stamp=stamp,
            body="0 supporting packet(s), confidence low; no stable lessons yet",
            previous_entries=previous_entries,
        )
        if not refinement_entries:
            refinement_entries = [f"- {stamp}: no lessons yet."]

        content = template.safe_substitute(
            title="No stable lesson candidates yet",
            evidence_count=0,
            confidence="low",
            status="tentative",
            lesson_statement="The current epoch does not yet have enough human-reviewed packets to justify stable lesson pages.",
            supporting_packets="- none yet",
            dissenting_packets="- none yet",
            confidence_note="Collect more explicit packet reviews before elevating provisional beliefs into lessons.",
            recurring_signals="- no repeated tags yet",
            contradictions="- no contradiction tracking yet because no lesson candidates are stable",
            related_concepts="- concepts will link here once lessons and tags co-occur",
            refinement_history="\n".join(refinement_entries),
            human_confirmed="no",
        )
        lessons.append({"path": page_path, "content": content})
    return lessons


def build_calibration_pages(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Build evaluator calibration entries from packet evidence.

    These are distinct from evaluator *profile* pages. A calibration entry
    records a specific, repeatable observation about judge behavior:
      - "Apollo aligns with humans better than Muse in creative-lane personification"
      - "Athena penalizes novelty in genre_mismatch tasks"

    Entries are compiled from the intersection of judge votes, human reviews,
    and family data. They only appear when there is enough evidence.
    """
    pages = []
    judges = ("muse", "athena", "apollo")

    # Collect per-judge, per-family alignment data
    judge_family_data: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"aligned": 0, "misaligned": 0, "total": 0})
    )
    judge_lane_data: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"aligned": 0, "misaligned": 0, "total": 0})
    )

    for summary in context["packet_summaries"]:
        review = summary.get("review")
        if not review:
            continue
        preferred = review.get("preferred_experiment_id")
        family = summary["family"]
        lane = summary["lane"]
        for judge in judges:
            winner = summary["judge_votes"][judge]
            if winner is None:
                continue
            judge_family_data[judge][family]["total"] += 1
            judge_lane_data[judge][lane]["total"] += 1
            if winner == preferred:
                judge_family_data[judge][family]["aligned"] += 1
                judge_lane_data[judge][lane]["aligned"] += 1
            else:
                judge_family_data[judge][family]["misaligned"] += 1
                judge_lane_data[judge][lane]["misaligned"] += 1

    # Generate calibration entries where there's enough data
    entries = []
    for judge in judges:
        for lane, data in sorted(judge_lane_data[judge].items()):
            if data["total"] < 2:
                continue
            rate = data["aligned"] / data["total"] if data["total"] > 0 else 0
            entries.append({
                "judge": judge,
                "scope": f"{lane} lane",
                "alignment_rate": rate,
                "total": data["total"],
                "aligned": data["aligned"],
                "summary": (
                    f"{role_label(judge)} aligned with human review {data['aligned']}/{data['total']} "
                    f"({rate:.0%}) in {lane}-lane packets."
                ),
            })
        for family, data in sorted(judge_family_data[judge].items()):
            if data["total"] < 2:
                continue
            rate = data["aligned"] / data["total"] if data["total"] > 0 else 0
            entries.append({
                "judge": judge,
                "scope": f"{family} family",
                "alignment_rate": rate,
                "total": data["total"],
                "aligned": data["aligned"],
                "summary": (
                    f"{role_label(judge)} aligned with human review {data['aligned']}/{data['total']} "
                    f"({rate:.0%}) in {family.replace('_', ' ')} tasks."
                ),
            })

    if not entries:
        return pages

    # Build a single calibration index page
    lines = ["# Evaluator Calibration", "", "Compiled from human-reviewed packet evidence.", ""]
    # Group by judge
    for judge in judges:
        judge_entries = [e for e in entries if e["judge"] == judge]
        if not judge_entries:
            continue
        lines.append(f"## {role_label(judge)}")
        lines.append("")
        for entry in sorted(judge_entries, key=lambda e: e["alignment_rate"]):
            lines.append(f"- {entry['summary']}")
        lines.append("")

    # Comparative entries: where one judge outperforms another
    lines.append("## Comparative Observations")
    lines.append("")
    comparisons = []
    for lane in sorted({e["scope"] for e in entries if "lane" in e["scope"]}):
        lane_entries = {e["judge"]: e for e in entries if e["scope"] == lane and e["total"] >= 2}
        if len(lane_entries) < 2:
            continue
        best = max(lane_entries.values(), key=lambda e: e["alignment_rate"])
        worst = min(lane_entries.values(), key=lambda e: e["alignment_rate"])
        if best["alignment_rate"] > worst["alignment_rate"]:
            comparisons.append(
                f"- In {lane}: {role_label(best['judge'])} ({best['aligned']}/{best['total']}) "
                f"aligns with humans more than {role_label(worst['judge'])} ({worst['aligned']}/{worst['total']})."
            )
    if comparisons:
        lines.extend(comparisons)
    else:
        lines.append("- not enough comparative evidence yet")
    lines.append("")

    content = "\n".join(lines)
    pages.append({
        "path": Path("calibration") / "index.md",
        "content": content,
    })
    return pages


def build_memo_pages(context: dict[str, Any]) -> list[dict[str, Any]]:
    pages = []
    for entry in context.get("council_history", []):
        payload = entry.get("payload") or {}
        created_at = entry.get("created_at") or ""
        stamp = created_at[:10] if len(created_at) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        title = _shorten(
            payload.get("strongest_finding")
            or payload.get("summary")
            or payload.get("research_memo")
            or f"Council memo {entry.get('id')}"
        )
        recommendation = payload.get("next_experiment") or payload.get("recommendation") or "No recommendation recorded."
        trust = payload.get("evaluator_trust_assessment") or "No evaluator trust note recorded."
        research_memo = payload.get("research_memo") or payload.get("memo") or "No long-form memo recorded."
        prompt_recommendations = "\n".join(
            f"- {item.get('title')}: {item.get('action') or item.get('reason') or ''}".rstrip()
            for item in (payload.get("prompt_diagnosis_recommendations") or [])
        ) or "- no prompt-diagnosis refinements recorded"
        evaluator_recommendations = "\n".join(
            f"- {item.get('title')}: {item.get('action') or item.get('reason') or ''}".rstrip()
            for item in (payload.get("evaluator_education_recommendations") or [])
        ) or "- no evaluator-curriculum refinements recorded"
        contrast_candidates = "\n".join(
            f"- {item.get('title')}: {item.get('why_now') or item.get('focus') or ''}".rstrip()
            for item in (payload.get("contrast_set_candidates") or [])
        ) or "- no contrast-set candidates recorded"
        content = "\n".join([
            "---",
            "page_type: council_memo",
            f"council_id: {entry.get('id')}",
            f"created_at: {created_at}",
            "---",
            "",
            f"# {title}",
            "",
            f"- created_at: {created_at}",
            f"- council_id: {entry.get('id')}",
            "",
            "## Strongest Finding",
            "",
            payload.get("strongest_finding") or payload.get("summary") or "No strongest finding recorded.",
            "",
            "## Research Memo",
            "",
            research_memo,
            "",
            "## Recommendation",
            "",
            recommendation,
            "",
            "## Evaluator Trust Assessment",
            "",
            trust,
            "",
            "## Prompt Diagnosis Refinements",
            "",
            prompt_recommendations,
            "",
            "## Evaluator Curriculum Refinements",
            "",
            evaluator_recommendations,
            "",
            "## Contrast Set Candidates",
            "",
            contrast_candidates,
            "",
        ])
        pages.append({
            "path": Path(GENERATED_DIRS["memos"]) / f"{stamp}-{entry.get('id')}.md",
            "content": content,
            "title": title,
        })
    return pages


def build_lint_pages(context: dict[str, Any], sections: dict[str, list[dict[str, Any]]], taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seeded_without_evidence = [
        page for page in sections.get("concepts", [])
        if page.get("provenance") == "seeded" and page.get("evidence_count", 0) == 0
    ]
    contested_lessons = [
        page for page in sections.get("lessons", [])
        if "status: contested" in page.get("content", "")
    ]
    model_family_blocked = [
        page for page in sections.get("concepts", [])
        if page.get("evidence_count", 0) >= PROMOTION_MIN_PACKETS
        and page.get("distinct_prompt_families", 0) >= PROMOTION_MIN_DISTINCT_FAMILIES
        and page.get("distinct_model_families", 0) < PROMOTION_MIN_MODEL_FAMILIES
        and page.get("provenance") != "promoted"
    ]
    families_without_review = [
        page for page in sections.get("families", [])
        if page.get("packet_count", 0) > 0 and page.get("human_reviews", 0) == 0
    ]
    lint_lines = [
        "# Judgment Wiki Lint",
        "",
        f"- generated_at: {stamp}",
        f"- epoch: {context['epoch']}",
        "",
        "## Seeded Concepts Awaiting Evidence",
        "",
    ]
    if seeded_without_evidence:
        lint_lines.extend(
            f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]"
            for page in seeded_without_evidence[:12]
        )
    else:
        lint_lines.append("- every seeded concept now has at least some packet evidence")
    lint_lines.extend([
        "",
        "## Concepts Blocked On Model-Family Diversity",
        "",
    ])
    if model_family_blocked:
        lint_lines.extend(
            (
                f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]] "
                f"({page.get('distinct_model_families', 0)} model families)"
            )
            for page in model_family_blocked[:8]
        )
    else:
        lint_lines.append("- no concept is currently blocked only by missing model-family evidence")
    lint_lines.extend([
        "",
        "## Lessons Needing Caution",
        "",
    ])
    if contested_lessons:
        lint_lines.extend(
            f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]"
            for page in contested_lessons[:8]
        )
    else:
        lint_lines.append("- no explicitly contested lessons right now")
    lint_lines.extend([
        "",
        "## Families Missing Human Review",
        "",
    ])
    if families_without_review:
        lint_lines.extend(
            f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]"
            for page in families_without_review[:8]
        )
    else:
        lint_lines.append("- every family page in the current epoch has some human review context")
    lint_lines.extend([
        "",
        "## Taxonomy Promotion Health",
        "",
        f"- promoted entries: {taxonomy['summary']['promoted']}",
        f"- merged entries: {taxonomy['summary']['merged']}",
        f"- emergent entries: {taxonomy['summary']['emergent']}",
        f"- seeded entries: {taxonomy['summary']['seeded']}",
        "",
        "## Council Memo Coverage",
        "",
        f"- memo pages filed this compile: {len(sections.get('memos', []))}",
        "",
        "## Note",
        "",
        "This lint pass is conservative. Its job is to flag weak memory surfaces, not to auto-correct them into false certainty.",
        "",
    ])
    return [{
        "path": Path(GENERATED_DIRS["lint"]) / "latest.md",
        "content": "\n".join(lint_lines),
    }]


def build_taxonomy(context: dict[str, Any], concept_pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile the promoted taxonomy — the machine-readable doctrine layer.

    Only entries that have cleared promotion gates appear here.
    The taxonomy is not the product surface. It is the distilled doctrine layer
    that falls out of repeated packet evidence and human review.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    promoted = []
    merged = []
    seeded = []
    emergent = []

    for page in concept_pages:
        provenance = page.get("provenance", "seeded")
        entry = page.get("entry") or {}
        record = {
            "tag": page["tag"],
            "domain": page["domain"],
            "provenance": provenance,
            "evidence_count": page.get("evidence_count", 0),
            "distinct_prompt_families": page.get("distinct_prompt_families", 0),
            "distinct_model_families": page.get("distinct_model_families", 0),
            "shared_packet_count": page.get("shared_packet_count", 0),
            "unattributed_packet_count": page.get("unattributed_packet_count", 0),
            "distinct_families": page.get("distinct_prompt_families", 0),
            "name": entry.get("name", humanize_tag(page["tag"])),
            "id": entry.get("id"),
            "description": entry.get("description", ""),
            "correction_strategy": entry.get("correction_strategy"),
            "detection_difficulty": entry.get("detection_difficulty"),
            "lanes": entry.get("lanes", []),
            "source": entry.get("source", provenance),
        }
        if provenance == "promoted":
            promoted.append(record)
        elif provenance == "merged":
            merged.append(record)
        elif provenance == "emergent":
            emergent.append(record)
        else:
            seeded.append(record)

    return {
        "version": "0.1.0",
        "compiled_at": stamp,
        "epoch": context["epoch"],
        "summary": {
            "promoted": len(promoted),
            "merged": len(merged),
            "emergent": len(emergent),
            "seeded": len(seeded),
            "total": len(concept_pages),
        },
        "promotion_criteria": {
            "min_packets": PROMOTION_MIN_PACKETS,
            "min_distinct_prompt_families": PROMOTION_MIN_DISTINCT_FAMILIES,
            "min_distinct_families": PROMOTION_MIN_DISTINCT_FAMILIES,
            "min_distinct_model_families": PROMOTION_MIN_MODEL_FAMILIES,
            "requires_correction_strategy": True,
            "requires_human_confirmation": True,
        },
        "promoted": promoted,
        "merged": merged,
        "emergent": emergent,
        "seeded": seeded,
    }


def build_weekly_summary(context: dict[str, Any], sections: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    template = _load_template("weekly_summary.md")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reviewed = [summary for summary in context["packet_summaries"] if summary["review"]]
    tag_counts = Counter()
    judge_disagreements = Counter()
    for summary in reviewed:
        tag_counts.update(summary["decision_reason_tags"])
        judge_disagreements.update(summary["judge_human_disagreements"])

    # Anti-pattern activity: use structured evidence_count from page dicts
    taste_entries = [
        page for page in sections.get("concepts", [])
        if page.get("domain") in ("anti-pattern", "quality-signal", "evaluator-failure")
    ]
    entries_with_evidence = sum(1 for p in taste_entries if p.get("evidence_count", 0) > 0)
    merged_count = sum(1 for p in taste_entries if p.get("provenance") == "merged")
    promoted_count = sum(1 for p in taste_entries if p.get("provenance") == "promoted")
    anti_pattern_activity_lines = []
    if taste_entries:
        anti_pattern_activity_lines.append(
            f"- {len(taste_entries)} seeded taste entries, {entries_with_evidence} with packet evidence"
        )
    if merged_count:
        anti_pattern_activity_lines.append(f"- {merged_count} merged (seed + evidence)")
    if promoted_count:
        anti_pattern_activity_lines.append(f"- {promoted_count} promoted to stable taxonomy")
    anti_pattern_activity = "\n".join(anti_pattern_activity_lines) or "- no anti-pattern or quality signal activity this period"
    memo_activity = "\n".join(
        f"- [[{page['path'].as_posix()}|{page.get('title', page['path'].stem.replace('-', ' '))}]]"
        for page in sections.get("memos", [])[:3]
    ) or "- no council memos filed into the wiki yet"
    lint_activity = "\n".join(
        f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]"
        for page in sections.get("lint", [])[:2]
    ) or "- no lint pass recorded"

    content = template.safe_substitute(
        week=stamp,
        packet_count=len(context["packets"]),
        reviewed_count=len(reviewed),
        top_signals=_format_top_counter(tag_counts, transform=humanize_tag),
        top_disagreements=_format_top_counter(judge_disagreements, transform=role_label),
        lesson_changes="\n".join(
            f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]"
            for page in sections["lessons"][:5]
        ) or "- none yet",
        concept_changes="\n".join(
            f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]"
            for page in sections["concepts"][:5]
            if page.get("provenance") == "emergent"
        ) or "- none yet",
        memo_activity=memo_activity,
        anti_pattern_activity=anti_pattern_activity,
        lint_activity=lint_activity,
        note=(
            "No human-reviewed packets yet in this epoch. The weekly layer will sharpen as review accumulates."
            if not reviewed else
            "This summary is provisional and should be revised as new packet reviews land."
        ),
    )
    return [{"path": Path(GENERATED_DIRS["weekly"]) / f"{stamp}.md", "content": content}]


def build_index(context: dict[str, Any], sections: dict[str, list[dict[str, Any]]]) -> str:
    template = _load_template("index.md")

    def _section_links(pages: list[dict[str, Any]], limit: int = 10) -> str:
        return "\n".join(
            f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]"
            for page in pages[:limit]
        ) or "- none yet"

    # Split concepts by domain and provenance
    anti_patterns = [p for p in sections.get("concepts", []) if p.get("domain") == "anti-pattern"]
    quality_signals = [p for p in sections.get("concepts", []) if p.get("domain") == "quality-signal"]
    evaluator_failures = [p for p in sections.get("concepts", []) if p.get("domain") == "evaluator-failure"]
    taxonomy_count = len(anti_patterns) + len(quality_signals) + len(evaluator_failures)

    # Add provenance annotations to anti-pattern links
    def _annotated_links(pages: list[dict[str, Any]], limit: int = 10) -> str:
        lines = []
        for page in pages[:limit]:
            prov = page.get("provenance", "")
            annotation = f" ({prov})" if prov in ("merged", "promoted") else ""
            lines.append(
                f"- [[{page['path'].as_posix()}|{page['path'].stem.replace('-', ' ')}]]{annotation}"
            )
        return "\n".join(lines) or "- none yet"

    return template.safe_substitute(
        epoch=context["epoch"],
        record_count=len(context["records"]),
        packet_count=len(context["packets"]),
        review_count=len(context["reviews"]),
        taxonomy_count=taxonomy_count,
        packet_links=_section_links(sections["packets"]),
        family_links=_section_links(sections["families"]),
        model_links=_section_links(sections["models"]),
        evaluator_links=_section_links(sections["evaluators"]),
        lesson_links=_section_links(sections["lessons"]),
        anti_pattern_links=_annotated_links(anti_patterns + [p for p in sections.get("concepts", []) if p.get("provenance") == "emergent"]),
        quality_signal_links=_annotated_links(quality_signals),
        evaluator_failure_links=_annotated_links(evaluator_failures),
        memo_links=_section_links(sections["memos"]),
        lint_links=_section_links(sections["lint"]),
        weekly_links=_section_links(sections["weekly"]),
    )


async def compile_wiki(
    output_dir: Path | None = None,
    *,
    taxonomy_dir: Path | None = None,
    calibration_dir: Path | None = None,
    limit: int = 400,
    epoch: str | None = None,
) -> dict[str, Any]:
    root = Path(output_dir or WIKI_ROOT)
    tax_root = Path(taxonomy_dir or TAXONOMY_ROOT)
    cal_root = Path(calibration_dir or CALIBRATION_ROOT)
    root.mkdir(parents=True, exist_ok=True)

    # Snapshot refinement history from existing pages BEFORE cleanup
    existing_refinements: dict[str, list[str]] = {}
    for section in ("lessons", "evaluators"):
        section_dir = root / GENERATED_DIRS[section]
        if section_dir.exists():
            for md_file in section_dir.glob("*.md"):
                rel_path = Path(GENERATED_DIRS[section]) / md_file.name
                entries = _read_existing_refinement_history(root, rel_path)
                if entries:
                    existing_refinements[str(rel_path)] = entries

    _cleanup_generated(root)
    context = await collect_wiki_context(limit=limit, epoch=epoch)
    context["existing_refinements"] = existing_refinements

    sections: dict[str, list[dict[str, Any]]] = {}
    sections["packets"] = build_packet_pages(context)
    sections["families"] = build_family_pages(context, sections["packets"])
    sections["models"] = build_model_pages(context)
    sections["evaluators"] = build_evaluator_pages(context)
    sections["lessons"] = build_lesson_pages(context)
    sections["concepts"] = build_concept_pages(context)
    sections["memos"] = build_memo_pages(context)
    taxonomy = build_taxonomy(context, sections["concepts"])
    sections["lint"] = build_lint_pages(context, sections, taxonomy)
    sections["weekly"] = build_weekly_summary(context, sections)

    # Write wiki pages under wiki root
    for pages in sections.values():
        for page in pages:
            _write_page(root / page["path"], page["content"])
    _write_page(root / "index.md", build_index(context, sections))

    # Write calibration pages to top-level calibration/
    calibration_pages = build_calibration_pages(context)
    cal_root.mkdir(parents=True, exist_ok=True)
    for page in calibration_pages:
        _write_page(cal_root / Path(page["path"]).name, page["content"])

    # Write compiled taxonomy to top-level taxonomy/
    tax_root.mkdir(parents=True, exist_ok=True)
    (tax_root / "compiled_taxonomy.json").write_text(
        json.dumps(taxonomy, indent=2, ensure_ascii=False) + "\n"
    )

    return {
        "root": str(root),
        "taxonomy_root": str(tax_root),
        "calibration_root": str(cal_root),
        "epoch": context["epoch"],
        "records": len(context["records"]),
        "packets": len(context["packets"]),
        "reviews": len(context["reviews"]),
        "sections": {name: len(pages) for name, pages in sections.items()},
        "calibration_pages": len(calibration_pages),
        "taxonomy": taxonomy["summary"],
    }


def main() -> None:
    result = asyncio.run(compile_wiki())
    print(
        f"Compiled judgment wiki to {result['root']} "
        f"(epoch={result['epoch']}, records={result['records']}, packets={result['packets']}, reviews={result['reviews']})"
    )
    for name, count in result["sections"].items():
        print(f"  {name}: {count} pages")
    print(f"  calibration: {result.get('calibration_pages', 0)} pages -> {result.get('calibration_root', '')}")
    taxonomy = result.get("taxonomy", {})
    if taxonomy:
        print(
            f"  taxonomy: {taxonomy.get('promoted', 0)} promoted, "
            f"{taxonomy.get('merged', 0)} merged, "
            f"{taxonomy.get('emergent', 0)} emergent, "
            f"{taxonomy.get('seeded', 0)} seeded "
            f"-> {result.get('taxonomy_root', '')}"
        )


if __name__ == "__main__":
    main()
