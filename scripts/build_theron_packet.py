from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import experiments  # noqa: E402


def _resolve_task(task_id: str) -> dict:
    task = experiments.ALL_TASKS.get(task_id)
    if not task:
        raise KeyError(f"Unknown task_id '{task_id}'.")
    return deepcopy(task)


def _apply_policy(task: dict, policy_variant: str | None) -> dict:
    if policy_variant:
        return experiments.apply_policy_variant(task, policy_variant, provenance="manual_override")
    return experiments.apply_policy_control(task)


def build_theron_message(task: dict, *, condition: str) -> str:
    lines = [
        "THERON LAB REQUEST",
        "",
        "You are generating one artifact for Creativity Lab.",
        "Return only the final artifact text.",
        "Do not include commentary, JSON, bullet labels, or explanations before or after the artifact.",
        "",
        f"LANE: {task['lane']}",
        f"FAMILY: {task['family']}",
        f"CONDITION: {condition}",
        "",
        "PROMPT:",
        task["prompt"],
    ]
    constraints = task.get("constraints") or []
    if constraints:
        lines.extend([
            "",
            "CONSTRAINTS:",
            *[f"- {item}" for item in constraints],
        ])
    guidance = task.get("generation_guidance")
    if guidance:
        lines.extend([
            "",
            "POLICY GUIDANCE:",
            guidance,
        ])
    lines.extend([
        "",
        "FINAL INSTRUCTION:",
        "Produce the strongest possible artifact that satisfies the prompt and constraints. Return the artifact only.",
    ])
    return "\n".join(lines)


def build_submission_template(task: dict, *, condition: str) -> dict:
    return {
        "prompt": task["prompt"],
        "artifact": "<paste Theron artifact here>",
        "lane": task["lane"],
        "constraints": task.get("constraints") or [],
        "family": task["family"],
        "track": task.get("track", "external"),
        "creativity_type": task.get("creativity_type", "custom"),
        "hypothesis": task.get("hypothesis"),
        "condition": condition,
        "generation_protocol": "theron_manual_bridge",
        "generator_provider": "theron_manual",
        "generator_role_id": "theron",
        "process_trace": {
            "protocol": "theron_manual_bridge",
            "artifact_contract_status": "ok",
            "submission_mode": "manual_bridge",
        },
        "source_context": {
            "external_submission": True,
            "generator_provider": "theron_manual",
            "generator_role_id": "theron",
            "submission_mode": "manual_bridge",
        },
    }


def build_packet(task_id: str, *, condition: str = "critique_off", policy_variant: str | None = None) -> dict:
    task = _apply_policy(_resolve_task(task_id), policy_variant)
    return {
        "task_id": task["id"],
        "lane": task["lane"],
        "family": task["family"],
        "condition": condition,
        "policy_context": experiments.build_policy_context(task),
        "message_to_send": build_theron_message(task, condition=condition),
        "submission_template": build_submission_template(task, condition=condition),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Theron-ready manual packet for a Creativity Lab task.")
    parser.add_argument("--task-id", required=True, help="Task id from experiments.py, for example c08 or b02.")
    parser.add_argument(
        "--condition",
        default="critique_off",
        help="Condition label to store on the external experiment. Defaults to critique_off for manual external generation.",
    )
    parser.add_argument(
        "--policy-variant",
        default=None,
        help="Optional prompt policy variant override, for example humanized_creative or metaphorical_push.",
    )
    args = parser.parse_args()

    packet = build_packet(
        args.task_id,
        condition=args.condition,
        policy_variant=args.policy_variant,
    )
    print(json.dumps(packet, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
