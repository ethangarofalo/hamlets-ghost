from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database as db  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run prompt-rule promotion proposals from rule evidence slices."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--only-promotions", action="store_true", help="Hide hold/watch rows in text output.")
    parser.add_argument("--provisional-packets", type=int)
    parser.add_argument("--provisional-families", type=int)
    parser.add_argument("--active-packets", type=int)
    parser.add_argument("--active-families", type=int)
    parser.add_argument("--active-model-families", type=int)
    parser.add_argument("--active-human-win-rate", type=float)
    parser.add_argument("--active-human-decisive", type=int)
    parser.add_argument("--hurt-flag-rate", type=float)
    parser.add_argument("--hurt-flag-min", type=int)
    parser.add_argument("--panel-preference-rate", type=float)
    parser.add_argument("--characterization-min-human", type=int)
    return parser


def _threshold_overrides(args: argparse.Namespace) -> dict:
    return {
        "provisional_packets": args.provisional_packets,
        "provisional_families": args.provisional_families,
        "active_packets": args.active_packets,
        "active_families": args.active_families,
        "active_model_families": args.active_model_families,
        "active_human_win_rate": args.active_human_win_rate,
        "active_human_decisive": args.active_human_decisive,
        "hurt_flag_rate": args.hurt_flag_rate,
        "hurt_flag_min": args.hurt_flag_min,
        "panel_preference_rate": args.panel_preference_rate,
        "characterization_min_human": args.characterization_min_human,
    }


def _print_text_report(report: dict, *, only_promotions: bool) -> None:
    print("Prompt rule promotion dry-run")
    print("No statuses are changed by this script.")
    print()
    print("Thresholds:")
    for key, value in report["thresholds"].items():
        print(f"  {key}: {value}")
    print()

    proposals = report["proposals"]
    if only_promotions:
        proposals = [item for item in proposals if item["recommendation"] == "promote"]
    if not proposals:
        print("No matching rule proposals.")
        return

    for item in proposals:
        metrics = item["metrics"]
        transition = f"{item['current_status']} -> {item['proposed_status']}"
        print(f"{item['recommendation'].upper()}: {item['rule_key']} ({transition})")
        print(f"  title: {item['title']}")
        print(f"  characterization: {item.get('characterization', 'insufficient_data')}")
        print(
            "  support: "
            f"{metrics['support_packets']} packet(s), "
            f"{metrics['support_families']} prompt family/families, "
            f"{metrics['support_model_families']} model family/families"
        )
        if metrics.get("suppressed_dual_constraint_fail"):
            print(f"  suppressed: {metrics['suppressed_dual_constraint_fail']} dual constraint-fail slice(s)")
        print(
            "  human: "
            f"{metrics['human_helped']} helped, "
            f"{metrics['human_hurt']} hurt, "
            f"{metrics['human_mixed']} mixed, "
            f"{metrics['human_unreviewed']} unreviewed"
        )
        if metrics["human_win_rate"] is not None:
            print(f"  human_win_rate: {metrics['human_win_rate']:.2f}")
        if item["reasons"]:
            print(f"  reasons: {'; '.join(item['reasons'])}")
        if item["missing"]:
            print(f"  missing: {'; '.join(item['missing'])}")
        print()


async def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    report = await db.compute_rule_promotion_proposals(_threshold_overrides(args))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text_report(report, only_promotions=args.only_promotions)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
