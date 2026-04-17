from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db

DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "demo_rule_evidence.json"
DEFAULT_DB = ROOT / "demo_lab.db"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a demo SQLite database for the public walkthrough.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--force", action="store_true", help="Replace an existing demo database.")
    return parser.parse_args()


def _remove_existing_db(path: Path) -> None:
    for candidate in (path, Path(f"{path}-shm"), Path(f"{path}-wal")):
        if candidate.exists():
            candidate.unlink()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


async def _seed(fixture: dict) -> dict:
    rule = await db.upsert_prompt_rule(fixture["rule"])
    seeded = []
    for index, item in enumerate(fixture.get("slices") or [], start=1):
        raw_id = await db.create_experiment(
            {
                "lane": item.get("lane"),
                "track": "compiler_compare",
                "creativity_type": "demo",
                "prompt": f"Demo compiler-compare packet {item['packet_id']}",
                "family": item.get("prompt_family"),
                "condition": "raw",
                "generation_protocol": "prompt_compiler_raw",
                "packet_id": item.get("packet_id"),
                "packet_role_id": "raw_prompt",
                "packet_primary": True,
            },
            status=item.get("raw_status") or "kept",
            iteration=(index * 2) - 1,
        )
        compiled_id = await db.create_experiment(
            {
                "lane": item.get("lane"),
                "track": "compiler_compare",
                "creativity_type": "demo",
                "prompt": f"Demo compiler-compare packet {item['packet_id']}",
                "family": item.get("prompt_family"),
                "condition": "compiled",
                "generation_protocol": "prompt_compiler_compiled",
                "packet_id": item.get("packet_id"),
                "packet_role_id": "compiled_prompt",
                "packet_primary": False,
            },
            status=item.get("compiled_status") or "kept",
            iteration=index * 2,
        )
        seeded.append(await db.record_rule_evidence_slice({
            "rule_key": fixture["rule"]["rule_key"],
            "title": fixture["rule"].get("title"),
            "scope_claim": fixture["rule"].get("scope_claim"),
            "rule_type": fixture["rule"].get("rule_type"),
            "rule_text": fixture["rule"].get("rule_text"),
            "rationale": fixture["rule"].get("rationale"),
            "rule_payload": fixture["rule"].get("payload") or {},
            "rule_version": rule.get("current_version") or 1,
            "lane": item.get("lane"),
            "prompt_family": item.get("prompt_family"),
            "model_family": item.get("model_family"),
            "panel_version": item.get("panel_version") or db.JUDGE_PANEL_VERSION,
            "experiment_type": "raw_vs_compiled",
            "packet_id": item.get("packet_id"),
            "experiment_id": compiled_id,
            "compared_experiment_id": raw_id,
            "human_signal": item.get("human_signal"),
            "human_signal_attribution_method": item.get("human_signal_attribution_method") or "uniform",
            "evaluator_signal": item.get("evaluator_signal"),
            "evaluator_margin": item.get("evaluator_margin"),
            "metadata": {
                "source": "demo_fixture",
                "raw_experiment_id": raw_id,
                "compiled_experiment_id": compiled_id,
                "raw_status": item.get("raw_status"),
                "compiled_status": item.get("compiled_status"),
            },
        }))
    report = await db.compute_rule_promotion_proposals()
    return {"rule": rule, "slices": seeded, "report": report}


def main() -> None:
    args = _parse_args()
    db_path = args.db_path.expanduser().resolve()
    fixture_path = args.fixture.expanduser().resolve()
    if db_path.exists() and not args.force:
        raise SystemExit(f"{db_path} already exists. Re-run with --force to replace it.")
    _remove_existing_db(db_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    db.DB_PATH = str(db_path)
    db._db_initialized = False
    db._initialized_db_path = None
    result = asyncio.run(_seed(fixture))
    proposals = result["report"]["proposals"]
    print(f"Seeded demo database: {_display_path(db_path)}")
    print(f"Fixture: {_display_path(fixture_path)}")
    print(f"Rule evidence slices: {len(result['slices'])}")
    if proposals:
        proposal = proposals[0]
        metrics = proposal["metrics"]
        print(f"Proposal: {proposal['recommendation']} {proposal['rule_key']}")
        print(f"Characterization: {proposal['characterization']}")
        print(f"Eligible slices: {metrics['eligible_slices']}")
        print(f"Suppressed dual constraint-fail slices: {metrics['suppressed_dual_constraint_fail']}")
        print(f"Decisive human reviews: {metrics['human_decisive']}")


if __name__ == "__main__":
    main()
