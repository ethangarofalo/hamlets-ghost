import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import agents
import database as db
import server


class LabDecisionMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_lab.db")

        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        await db.init_db()

        self.original_run_genesis = agents.run_genesis
        self.original_run_openclaw_genesis = getattr(agents, "run_openclaw_genesis", None)
        self.original_run_theron_genesis = getattr(agents, "run_theron_genesis", None)
        self.original_run_muse = agents.run_muse
        self.original_run_hermes = agents.run_hermes
        self.original_run_athena = getattr(agents, "run_athena", None)
        self.original_run_external_hermes = getattr(agents, "run_external_hermes", None)
        self.original_athena_gate_enabled = agents.ATHENA_GATE_ENABLED
        self.original_athena_min_muse_composite = agents.ATHENA_MIN_MUSE_COMPOSITE
        self.original_athena_require_constraint_pass = agents.ATHENA_REQUIRE_CONSTRAINT_PASS
        self.original_apollo_shadow_enabled = getattr(agents, "APOLLO_SHADOW_ENABLED", False)
        self.original_genesis_openclaw_shadow_enabled = getattr(agents, "GENESIS_OPENCLAW_SHADOW_ENABLED", False)
        self.original_genesis_openclaw_families = getattr(agents, "GENESIS_OPENCLAW_FAMILIES", set())
        self.original_theron_generation_enabled = getattr(agents, "THERON_GENERATION_ENABLED", False)
        self.original_forced_athena_low_score_modulo = server.FORCED_ATHENA_LOW_SCORE_MODULO
        self.original_forced_athena_constraint_fail_modulo = server.FORCED_ATHENA_CONSTRAINT_FAIL_MODULO
        self.original_forced_athena_unknown_constraint_modulo = server.FORCED_ATHENA_UNKNOWN_CONSTRAINT_MODULO
        self.original_admin_token = os.environ.get("LAB_ADMIN_TOKEN")

        agents.ATHENA_GATE_ENABLED = True
        agents.ATHENA_MIN_MUSE_COMPOSITE = 999.0
        agents.ATHENA_REQUIRE_CONSTRAINT_PASS = True
        agents.APOLLO_SHADOW_ENABLED = False
        agents.GENESIS_OPENCLAW_SHADOW_ENABLED = False
        agents.GENESIS_OPENCLAW_FAMILIES = set()
        server.FORCED_ATHENA_LOW_SCORE_MODULO = self.original_forced_athena_low_score_modulo
        server.FORCED_ATHENA_CONSTRAINT_FAIL_MODULO = self.original_forced_athena_constraint_fail_modulo
        server.FORCED_ATHENA_UNKNOWN_CONSTRAINT_MODULO = self.original_forced_athena_unknown_constraint_modulo

    async def asyncTearDown(self):
        agents.run_genesis = self.original_run_genesis
        if self.original_run_openclaw_genesis is not None:
            agents.run_openclaw_genesis = self.original_run_openclaw_genesis
        if self.original_run_theron_genesis is not None:
            agents.run_theron_genesis = self.original_run_theron_genesis
        agents.run_muse = self.original_run_muse
        agents.run_hermes = self.original_run_hermes
        if self.original_run_athena is not None:
            agents.run_athena = self.original_run_athena
        if self.original_run_external_hermes is not None:
            agents.run_external_hermes = self.original_run_external_hermes
        agents.ATHENA_GATE_ENABLED = self.original_athena_gate_enabled
        agents.ATHENA_MIN_MUSE_COMPOSITE = self.original_athena_min_muse_composite
        agents.ATHENA_REQUIRE_CONSTRAINT_PASS = self.original_athena_require_constraint_pass
        agents.APOLLO_SHADOW_ENABLED = self.original_apollo_shadow_enabled
        agents.GENESIS_OPENCLAW_SHADOW_ENABLED = self.original_genesis_openclaw_shadow_enabled
        agents.GENESIS_OPENCLAW_FAMILIES = self.original_genesis_openclaw_families
        agents.THERON_GENERATION_ENABLED = self.original_theron_generation_enabled
        server.FORCED_ATHENA_LOW_SCORE_MODULO = self.original_forced_athena_low_score_modulo
        server.FORCED_ATHENA_CONSTRAINT_FAIL_MODULO = self.original_forced_athena_constraint_fail_modulo
        server.FORCED_ATHENA_UNKNOWN_CONSTRAINT_MODULO = self.original_forced_athena_unknown_constraint_modulo
        if self.original_admin_token is None:
            os.environ.pop("LAB_ADMIN_TOKEN", None)
        else:
            os.environ["LAB_ADMIN_TOKEN"] = self.original_admin_token
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def _run_experiment(
        self,
        *,
        constraints,
        muse_result,
        muse_parse_failure,
        muse_cost=0.0,
        athena_result=None,
        athena_parse_failure=False,
        athena_cost=0.0,
        athena_should_raise=False,
        external_athena_result=None,
        external_athena_parse_failure=False,
        external_athena_cost=0.0,
        external_athena_should_raise=False,
        enable_apollo=False,
        openclaw_genesis_result=None,
        openclaw_genesis_parse_failure=False,
        openclaw_genesis_cost=0.0,
        openclaw_genesis_should_raise=False,
        enable_openclaw_genesis=False,
        athena_min_muse_composite=999.0,
        genesis_artifact="rain in dusk\nrain on stone\nrain goes on",
        process_trace=None,
        task_overrides=None,
    ):
        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            return {
                "artifact": genesis_artifact,
                "process_trace": process_trace or {
                    "protocol": "test_probe",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "verifier_repair_summary": "",
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            return dict(muse_result), muse_cost, muse_parse_failure

        async def fake_run_openclaw_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            if openclaw_genesis_should_raise:
                raise RuntimeError("simulated openclaw genesis failure")
            payload = openclaw_genesis_result if openclaw_genesis_result is not None else {
                "artifact": "shadow openclaw artifact",
                "process_trace": {
                    "protocol": "openclaw_shadow",
                    "artifact_contract_status": "ok",
                },
            }
            return payload, openclaw_genesis_cost, openclaw_genesis_parse_failure

        async def fake_run_athena(artifact, prompt, constraints=None, lane="creative", **kwargs):
            if athena_should_raise:
                raise RuntimeError("simulated athena failure")
            payload = dict(athena_result) if athena_result is not None else {
                "novelty": 7.0,
                "surprise": 7.0,
                "value": 7.0,
                "elaboration": 7.0,
                "coherence": 7.0,
                "composite": 7.0,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            }
            return payload, athena_cost, athena_parse_failure

        async def fake_run_external_hermes(artifact, prompt, constraints=None, lane="creative", **kwargs):
            if external_athena_should_raise:
                raise RuntimeError("simulated apollo failure")
            payload = dict(external_athena_result) if external_athena_result is not None else {
                "novelty": 7.4,
                "surprise": 7.3,
                "value": 7.4,
                "elaboration": 7.2,
                "coherence": 7.3,
                "composite": 7.3,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "external shadow review",
            }
            return payload, external_athena_cost, external_athena_parse_failure

        agents.run_genesis = fake_run_genesis
        agents.run_openclaw_genesis = fake_run_openclaw_genesis
        agents.run_muse = fake_run_muse
        agents.run_hermes = fake_run_athena
        agents.run_athena = fake_run_athena
        agents.run_external_hermes = fake_run_external_hermes
        agents.ATHENA_MIN_MUSE_COMPOSITE = athena_min_muse_composite
        agents.APOLLO_SHADOW_ENABLED = enable_apollo
        agents.GENESIS_OPENCLAW_SHADOW_ENABLED = enable_openclaw_genesis
        agents.GENESIS_OPENCLAW_FAMILIES = {"custom_operator"} if enable_openclaw_genesis else set()

        state = await db.get_state()
        result = await server._execute_experiment(
            {
                "id": "test_task",
                "lane": "creative",
                "prompt": "Write exactly three lines about rain.",
                "creativity_type": "custom",
                "constraints": constraints,
                "track": "custom",
                "family": "custom_operator",
                "hypothesis": None,
                "condition": "critique_on",
                **(task_overrides or {}),
            },
            iteration=(state["total_experiments"] or 0) + 1,
            consecutive_discards=state.get("consecutive_discards") or 0,
        )
        return result

    async def _seed_reviewed_pair(
        self,
        *,
        packet_id,
        family,
        lane="creative",
        preferred_role_id="theron",
        winner_tags=None,
        loser_tags=None,
    ):
        base_task = {
            "lane": lane,
            "track": "paired",
            "prompt": "Write a prayer from the perspective of a dying programming language.",
            "family": family,
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "paired_native",
            "packet_id": packet_id,
        }
        genesis_id = await db.create_experiment(
            {**base_task, "packet_role_id": "genesis", "packet_primary": True},
            status="promoted",
        )
        theron_id = await db.create_experiment(
            {**base_task, "packet_role_id": "theron", "packet_primary": False},
            status="promoted",
        )
        await db.insert_artifact(genesis_id, "Genesis historical artifact")
        await db.insert_artifact(theron_id, "Theron historical artifact")
        await db.finalize_experiment(genesis_id, status="promoted", promotion_status="shadow")
        await db.finalize_experiment(theron_id, status="promoted", promotion_status="shadow")
        winner_tags = winner_tags or ["real_pathos"]
        loser_tags = loser_tags or ["generic_reassurance"]
        preferred_experiment_id = theron_id if preferred_role_id == "theron" else genesis_id
        await db.save_comparison_review(
            packet_id,
            preferred_experiment_id=preferred_experiment_id,
            rationale="Historical review used for generator coaching.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={
                "reason_tag_attribution": {
                    "winner": winner_tags,
                    "loser": loser_tags,
                },
                "reason_tag_evidence": [
                    {
                        "tag": winner_tags[0],
                        "target": "winner",
                        "excerpt": "The winning artifact carried the pressure all the way through.",
                    },
                    {
                        "tag": loser_tags[0],
                        "target": "loser",
                        "excerpt": "The losing artifact relaxed into a familiar fallback line.",
                    },
                ],
            },
        )
        return {"genesis_id": genesis_id, "theron_id": theron_id}

    def _fetch_one(self, query, params=()):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    async def test_constrained_parse_failure_stores_unknown_and_marks_invalid(self):
        result = await self._run_experiment(
            constraints=["Use exactly three lines.", "Every line must contain rain."],
            muse_result={
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
            },
            muse_parse_failure=True,
        )

        experiment = self._fetch_one(
            "SELECT status, parse_failure FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        score = self._fetch_one(
            "SELECT constraints_met, parse_failure, constraint_notes FROM scores WHERE experiment_id = ? AND scored_by = 'muse'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(experiment["status"], "invalid")
        self.assertEqual(experiment["parse_failure"], 1)
        self.assertIsNone(score["constraints_met"])
        self.assertEqual(score["parse_failure"], 1)
        self.assertEqual(score["constraint_notes"], "PARSE FAILURE")

    async def test_constrained_unknown_without_parse_failure_blocks_promotion_but_stays_null(self):
        result = await self._run_experiment(
            constraints=["Use exactly three lines.", "Every line must contain rain."],
            muse_result={
                "novelty": 7.0,
                "surprise": 6.8,
                "value": 7.5,
                "elaboration": 7.1,
                "coherence": 7.0,
                "composite": 7.3,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": None,
                "constraint_notes": "Evaluator could not verify all constraints.",
                "critique": "Constraint assessment was inconclusive.",
                "keep": False,
            },
            muse_parse_failure=False,
        )

        experiment = self._fetch_one(
            "SELECT status, parse_failure FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        score = self._fetch_one(
            "SELECT constraints_met, parse_failure FROM scores WHERE experiment_id = ? AND scored_by = 'muse'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "constraint_fail")
        self.assertEqual(experiment["status"], "constraint_fail")
        self.assertEqual(experiment["parse_failure"], 0)
        self.assertIsNone(score["constraints_met"])
        self.assertEqual(score["parse_failure"], 0)

    async def test_unconstrained_unknown_defaults_to_true_for_storage_and_can_be_kept(self):
        result = await self._run_experiment(
            constraints=[],
            muse_result={
                "novelty": 7.4,
                "surprise": 7.2,
                "value": 7.5,
                "elaboration": 7.0,
                "coherence": 7.1,
                "composite": 7.2,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": None,
                "constraint_notes": "",
                "critique": "Solid unconstrained draft.",
                "keep": True,
            },
            muse_parse_failure=False,
        )

        experiment = self._fetch_one(
            "SELECT status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        score = self._fetch_one(
            "SELECT constraints_met FROM scores WHERE experiment_id = ? AND scored_by = 'muse'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "kept")
        self.assertEqual(experiment["status"], "kept")
        self.assertEqual(score["constraints_met"], 1)

    async def test_resolve_policy_control_uses_approved_family_default(self):
        await db.upsert_policy_registry_entry({
            "lane": "business",
            "prompt_family": "retention_messaging",
            "policy_key": "prompt_policy_default",
            "recommended_value": "humanized_trust",
            "approved_value": "humanized_trust",
            "approval_status": "approved",
            "rationale": "test",
            "source": "unit_test",
        })

        resolved = await server._resolve_policy_control({
            "lane": "business",
            "family": "retention_messaging",
            "prompt": "demo task",
            "track": "custom",
            "creativity_type": "custom",
            "constraints": [],
        })

        self.assertEqual(resolved["prompt_policy_variant"], "humanized_trust")
        self.assertEqual(resolved["policy_source"], "approved_family_default")
        self.assertEqual(resolved["approved_family_policy_variant"], "humanized_trust")

    async def test_constrained_explicit_pass_with_high_composite_and_low_divergence_promotes(self):
        result = await self._run_experiment(
            constraints=["Use exactly three lines."],
            muse_result={
                "novelty": 8.0,
                "surprise": 7.8,
                "value": 8.2,
                "elaboration": 7.9,
                "coherence": 8.1,
                "composite": 7.8,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "All constraints satisfied.",
                "critique": "Strong and compliant.",
                "keep": True,
            },
            muse_parse_failure=False,
            athena_result={
                "novelty": 7.9,
                "surprise": 7.7,
                "value": 8.1,
                "elaboration": 7.8,
                "coherence": 8.0,
                "composite": 7.5,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "All constraints satisfied.",
                "critique": "",
            },
            athena_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status, parse_failure FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        holdout_score = self._fetch_one(
            "SELECT composite, constraints_met, parse_failure FROM scores WHERE experiment_id = ? AND scored_by = 'athena'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "promoted")
        self.assertEqual(result["promotion_status"], "shadow")
        self.assertEqual(experiment["status"], "promoted")
        self.assertEqual(experiment["promotion_status"], "shadow")
        self.assertEqual(experiment["parse_failure"], 0)
        self.assertEqual(holdout_score["constraints_met"], 1)
        self.assertEqual(holdout_score["parse_failure"], 0)

    async def test_constrained_explicit_fail_blocks_promotion_even_with_high_composite(self):
        result = await self._run_experiment(
            constraints=["Use exactly three lines."],
            muse_result={
                "novelty": 8.3,
                "surprise": 8.0,
                "value": 8.4,
                "elaboration": 8.2,
                "coherence": 8.1,
                "composite": 8.0,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": False,
                "constraint_notes": "Constraint violated.",
                "critique": "High quality, but not compliant.",
                "keep": False,
            },
            muse_parse_failure=False,
            athena_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        muse_score = self._fetch_one(
            "SELECT constraints_met FROM scores WHERE experiment_id = ? AND scored_by = 'muse'",
            (result["experiment_id"],),
        )
        athena_count = self._fetch_one(
            "SELECT COUNT(*) AS count FROM scores WHERE experiment_id = ? AND scored_by = 'athena'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "constraint_fail")
        self.assertEqual(experiment["status"], "constraint_fail")
        self.assertEqual(experiment["promotion_status"], "candidate")
        self.assertEqual(muse_score["constraints_met"], 0)
        self.assertEqual(athena_count["count"], 0)

    async def test_high_composite_with_athena_parse_failure_is_kept_not_promoted(self):
        result = await self._run_experiment(
            constraints=[],
            muse_result={
                "novelty": 8.1,
                "surprise": 8.0,
                "value": 8.2,
                "elaboration": 8.0,
                "coherence": 8.1,
                "composite": 7.9,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Strong draft.",
                "keep": True,
            },
            muse_parse_failure=False,
            athena_result={
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
                "critique": "ATHENA PARSE FAILURE",
            },
            athena_parse_failure=True,
            athena_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        athena_count = self._fetch_one(
            "SELECT COUNT(*) AS count FROM scores WHERE experiment_id = ? AND scored_by = 'athena'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "kept")
        self.assertEqual(result["promotion_status"], "candidate")
        self.assertEqual(experiment["status"], "kept")
        self.assertEqual(experiment["promotion_status"], "candidate")
        self.assertEqual(athena_count["count"], 0)

    async def test_low_muse_run_can_force_athena_sampling_for_calibration(self):
        server.FORCED_ATHENA_LOW_SCORE_MODULO = 1
        result = await self._run_experiment(
            constraints=[],
            muse_result={
                "novelty": 5.0,
                "surprise": 5.1,
                "value": 5.2,
                "elaboration": 5.0,
                "coherence": 5.1,
                "composite": 5.3,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Weak draft.",
                "keep": False,
            },
            muse_parse_failure=False,
            athena_result={
                "novelty": 5.4,
                "surprise": 5.2,
                "value": 5.3,
                "elaboration": 5.1,
                "coherence": 5.2,
                "composite": 5.4,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            },
            athena_min_muse_composite=6.5,
        )

        holdout_score = self._fetch_one(
            "SELECT composite FROM scores WHERE experiment_id = ? AND scored_by = 'athena'",
            (result["experiment_id"],),
        )
        artifact = self._fetch_one(
            "SELECT process_trace FROM artifacts WHERE experiment_id = ?",
            (result["experiment_id"],),
        )

        self.assertIsNotNone(holdout_score)
        self.assertIn("forced_sample_low_muse", artifact["process_trace"])

    async def test_apollo_shadow_is_logged_without_changing_promotion_gate(self):
        result = await self._run_experiment(
            constraints=[],
            muse_result={
                "novelty": 8.2,
                "surprise": 8.0,
                "value": 8.1,
                "elaboration": 7.9,
                "coherence": 8.0,
                "composite": 7.9,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Strong draft.",
                "keep": True,
            },
            muse_parse_failure=False,
            athena_result={
                "novelty": 8.0,
                "surprise": 7.8,
                "value": 8.0,
                "elaboration": 7.8,
                "coherence": 7.9,
                "composite": 7.7,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            },
            external_athena_result={
                "novelty": 5.8,
                "surprise": 5.7,
                "value": 6.1,
                "elaboration": 6.0,
                "coherence": 6.0,
                "composite": 5.9,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "External shadow evaluator is much less convinced.",
            },
            enable_apollo=True,
            athena_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        external_holdout = self._fetch_one(
            "SELECT composite FROM scores WHERE experiment_id = ? AND scored_by = 'apollo'",
            (result["experiment_id"],),
        )
        artifact = self._fetch_one(
            "SELECT process_trace, source_context FROM artifacts WHERE experiment_id = ?",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "promoted")
        self.assertEqual(experiment["promotion_status"], "shadow")
        self.assertEqual(external_holdout["composite"], 5.9)
        self.assertIn("apollo", artifact["process_trace"])
        self.assertIn("shadow_only", artifact["source_context"])

    async def test_openclaw_shadow_generator_is_logged_without_affecting_primary_outcome(self):
        result = await self._run_experiment(
            constraints=[],
            muse_result={
                "novelty": 7.8,
                "surprise": 7.7,
                "value": 7.9,
                "elaboration": 7.8,
                "coherence": 7.9,
                "composite": 7.8,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Strong local draft.",
                "keep": True,
            },
            muse_parse_failure=False,
            athena_result={
                "novelty": 7.5,
                "surprise": 7.4,
                "value": 7.6,
                "elaboration": 7.5,
                "coherence": 7.5,
                "composite": 7.4,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            },
            enable_openclaw_genesis=True,
            openclaw_genesis_result={
                "artifact": "Theron shadow artifact",
                "process_trace": {
                    "protocol": "openclaw_shadow",
                    "artifact_contract_status": "ok",
                    "strategy_notes": "Alternative generator path.",
                },
            },
            athena_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        artifact = self._fetch_one(
            "SELECT process_trace, source_context FROM artifacts WHERE experiment_id = ?",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "promoted")
        self.assertEqual(experiment["promotion_status"], "shadow")
        self.assertIn("genesis_openclaw", artifact["process_trace"])
        self.assertIn("Theron shadow artifact", artifact["source_context"])

    async def test_recent_experiments_expose_native_role_and_comparison_packets(self):
        packet_id = "packet_native_pair"
        first = await self._run_experiment(
            constraints=[],
            muse_result={
                "novelty": 7.8,
                "surprise": 7.4,
                "value": 8.0,
                "elaboration": 7.9,
                "coherence": 8.1,
                "composite": 7.86,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Strong local artifact.",
            },
            muse_parse_failure=False,
            athena_result={
                "novelty": 7.4,
                "surprise": 7.2,
                "value": 7.8,
                "elaboration": 7.6,
                "coherence": 8.0,
                "composite": 7.56,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            },
            athena_min_muse_composite=6.5,
            genesis_artifact="local paired artifact",
            task_overrides={
                "packet_id": packet_id,
                "packet_role_id": "genesis",
                "packet_primary": True,
            },
        )

        task = await server._resolve_policy_control({
            "id": "external_pair_task",
            "lane": "creative",
            "prompt": "Write exactly three lines about rain.",
            "creativity_type": "custom",
            "constraints": [],
            "track": "custom",
            "family": "custom_operator",
            "hypothesis": None,
            "condition": "critique_on",
            "packet_id": packet_id,
            "packet_role_id": "theron",
            "packet_primary": False,
        })
        exp_id = await db.create_experiment(task)
        await db.insert_artifact(
            exp_id,
            "theron paired artifact",
            process_trace={
                "protocol": "theron_manual_bridge",
                "artifact_contract_status": "ok",
                "role_routing": server._build_role_provenance(task),
            },
            source_context={
                "generator_provider": "theron_manual",
                "generator_role_id": "theron",
                "submission_mode": "manual_bridge",
                "role_routing": server._build_role_provenance(task),
            },
        )
        await db.insert_score(
            exp_id,
            "muse",
            {
                "novelty": 8.2,
                "surprise": 8.0,
                "value": 8.1,
                "elaboration": 8.2,
                "coherence": 8.4,
                "composite": 8.16,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Theron paired artifact.",
            },
        )
        await db.finalize_experiment(exp_id, status="kept", promotion_status="candidate")

        recent = await db.get_recent_experiments(limit=10)
        native_pair = [row for row in recent if row["id"] in {first["experiment_id"], exp_id}]

        self.assertEqual(len(native_pair), 2)
        for row in native_pair:
            self.assertIn("role_packets", row)
            self.assertIn("comparison_packet", row)
            self.assertEqual(row["comparison_packet"]["size"], 2)
            self.assertEqual(row["comparison_packet"]["packet_id"], packet_id)
        external = next(row for row in native_pair if row["id"] == exp_id)
        self.assertEqual(external["role_packets"]["generators"][0]["role_id"], "theron")

    async def test_explicit_packet_id_groups_mixed_prompts_under_one_native_packet(self):
        packet_id = "packet_cross_prompt"
        first = await self._run_experiment(
            constraints=[],
            muse_result={
                "novelty": 7.5,
                "surprise": 7.4,
                "value": 7.8,
                "elaboration": 7.7,
                "coherence": 8.1,
                "composite": 7.7,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            },
            muse_parse_failure=False,
            athena_min_muse_composite=6.5,
            task_overrides={
                "packet_id": packet_id,
                "packet_role_id": "genesis",
                "packet_primary": True,
                "prompt": "Write one line about rain.",
            },
        )

        task = await server._resolve_policy_control({
            "id": "external_pair_variant",
            "lane": "creative",
            "prompt": "Write one line about thunder.",
            "creativity_type": "custom",
            "constraints": [],
            "track": "external",
            "family": "custom_operator",
            "hypothesis": None,
            "condition": "critique_on",
            "packet_id": packet_id,
            "packet_role_id": "theron",
            "packet_primary": False,
        })
        exp_id = await db.create_experiment(task)
        await db.insert_artifact(
            exp_id,
            "theron cross prompt artifact",
            process_trace={
                "protocol": "theron_manual_bridge",
                "artifact_contract_status": "ok",
                "role_routing": server._build_role_provenance(task),
            },
            source_context={
                "generator_provider": "theron_manual",
                "generator_role_id": "theron",
                "submission_mode": "manual_bridge",
                "packet_id": packet_id,
                "packet_role_id": "theron",
                "packet_primary": False,
                "role_routing": server._build_role_provenance(task),
            },
        )
        await db.insert_score(
            exp_id,
            "muse",
            {
                "novelty": 8.0,
                "surprise": 7.9,
                "value": 7.9,
                "elaboration": 8.0,
                "coherence": 8.1,
                "composite": 7.98,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            },
        )
        await db.finalize_experiment(exp_id, status="kept", promotion_status="candidate")

        recent = await db.get_recent_experiments(limit=10)
        native_pair = [row for row in recent if row["id"] in {first["experiment_id"], exp_id}]
        self.assertEqual(len(native_pair), 2)
        for row in native_pair:
            self.assertEqual(row["comparison_packet"]["packet_id"], packet_id)
            self.assertEqual(row["comparison_packet"]["size"], 2)

    async def test_paired_route_can_generate_theron_inside_packet(self):
        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            return {
                "artifact": "genesis generated inside packet",
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_theron_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            return {
                "artifact": "theron generated inside packet",
                "process_trace": {
                    "protocol": "theron_paired_native",
                    "artifact_contract_status": "ok",
                },
            }, 0.25, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            score = 8.3 if "theron" in artifact else 7.9
            return {
                "novelty": score,
                "surprise": score,
                "value": score,
                "elaboration": score,
                "coherence": score,
                "composite": score,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            }, 0.0, False

        async def fake_run_hermes(artifact, prompt, constraints=None, lane="creative", **kwargs):
            score = 8.1 if "theron" in artifact else 7.8
            return {
                "novelty": score,
                "surprise": score,
                "value": score,
                "elaboration": score,
                "coherence": score,
                "composite": score,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            }, 0.0, False

        agents.run_genesis = fake_run_genesis
        agents.run_theron_genesis = fake_run_theron_genesis
        agents.run_muse = fake_run_muse
        agents.run_hermes = fake_run_hermes
        agents.run_athena = fake_run_hermes
        agents.THERON_GENERATION_ENABLED = True
        agents.ATHENA_MIN_MUSE_COMPOSITE = 6.5
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        with patch.object(server.db, "get_experiment_by_id", AsyncMock(side_effect=AssertionError("paired route should use lightweight summaries"))):
            response = await server.run_paired_experiment(
                {
                    "lane": "creative",
                    "track": "paired",
                    "family": "personification",
                    "condition": "critique_off",
                    "prompt": "Write a prayer from the perspective of a dying programming language.",
                    "constraints": [],
                    "run_local": True,
                    "generate_external": True,
                    "external_role_id": "theron",
                },
                x_admin_token="secret-token",
            )
        payload = json.loads(response.body.decode())

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(len(payload["results"]), 2)
        role_ids = {member["role_id"] for member in payload["members"]}
        self.assertEqual(role_ids, {"genesis", "theron"})

        recent = await db.get_recent_experiments(limit=10)
        paired = [row for row in recent if row.get("comparison_packet", {}).get("packet_id") == payload["packet_id"]]
        self.assertEqual(len(paired), 2)
        theron = next(row for row in paired if row["packet_role_id"] == "theron")
        self.assertEqual(theron["role_packets"]["generators"][0]["role_id"], "theron")
        self.assertEqual(theron["source_context"]["submission_mode"], "paired_native_generated")
        self.assertEqual(theron["process_trace"]["protocol"], "theron_paired_native")
        self.assertEqual(theron["process_trace"]["orchestration"]["planned_agents"][0], "theron")
        self.assertEqual(theron["process_trace"]["orchestration"]["executed_agents"][0], "theron")
        self.assertEqual(theron["process_trace"]["role_routing"]["theron"]["generation_protocol"], "theron_paired_native")
        self.assertEqual(theron["process_trace"]["role_routing"]["genesis"]["generation_protocol"], "socratic")

    async def test_execute_experiment_passes_human_feedback_into_genesis(self):
        await self._seed_reviewed_pair(
            packet_id="packet_feedback_genesis",
            family="personification",
            preferred_role_id="theron",
            winner_tags=["real_pathos"],
            loser_tags=["generic_reassurance"],
        )

        captured = {}

        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            captured["prior_feedback"] = prior_feedback
            captured["policy_context"] = kwargs.get("policy_context") or {}
            return {
                "artifact": "new genesis artifact",
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            return {
                "novelty": 7.4,
                "surprise": 7.3,
                "value": 7.2,
                "elaboration": 7.4,
                "coherence": 7.5,
                "composite": 7.36,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Avoid generic reassurance.",
            }, 0.0, False

        agents.run_genesis = fake_run_genesis
        agents.run_muse = fake_run_muse
        agents.ATHENA_GATE_ENABLED = False

        result = await server._execute_experiment(
            {
                "id": "feedback_task",
                "lane": "creative",
                "track": "custom",
                "prompt": "Write a prayer from the perspective of a dying programming language.",
                "family": "personification",
                "constraints": [],
                "condition": "critique_off",
            },
            iteration=1,
            consecutive_discards=0,
        )

        self.assertIn("generic_reassurance", captured["prior_feedback"])
        self.assertEqual(captured["policy_context"]["track"], "custom")
        self.assertEqual(captured["policy_context"]["family"], "personification")
        self.assertEqual(captured["policy_context"]["condition"], "critique_off")
        record = await db.get_experiment_by_id(result["experiment_id"])
        self.assertEqual(
            record["process_trace"]["generator_feedback"]["genesis"]["scope_applied"],
            "family_lane",
        )
        self.assertEqual(
            record["process_trace"]["generator_feedback"]["genesis"]["top_flaws"],
            ["generic_reassurance"],
        )

    async def test_execute_experiment_applies_adopted_council_prompt_diagnosis_rules(self):
        captured = {}

        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            captured["policy_context"] = kwargs.get("policy_context") or {}
            return {
                "artifact": "new genesis artifact",
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            return {
                "novelty": 7.4,
                "surprise": 7.3,
                "value": 7.2,
                "elaboration": 7.4,
                "coherence": 7.5,
                "composite": 7.36,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Solid enough.",
            }, 0.0, False

        agents.run_genesis = fake_run_genesis
        agents.run_muse = fake_run_muse
        agents.ATHENA_GATE_ENABLED = False

        with patch.object(server.db, "get_council_actions", AsyncMock(return_value=[{
            "id": 11,
            "action_type": "prompt_diagnosis_refinement",
            "title": "Make audience explicit",
            "status": "adopted",
            "lane": "creative",
            "prompt_family": "personification",
            "payload": {"action": "Name the actual recipient before drafting."},
        }])):
            result = await server._execute_experiment(
                {
                    "id": "feedback_task",
                    "lane": "creative",
                    "track": "custom",
                    "prompt": "Write a prayer from the perspective of a dying programming language.",
                    "family": "personification",
                    "constraints": [],
                    "condition": "critique_off",
                },
                iteration=1,
                consecutive_discards=0,
            )

        self.assertEqual(
            captured["policy_context"]["active_prompt_diagnosis_rules"][0]["title"],
            "Make audience explicit",
        )
        record = await db.get_experiment_by_id(result["experiment_id"])
        self.assertEqual(
            record["process_trace"]["council_mandates"]["prompt_diagnosis_rules"][0]["title"],
            "Make audience explicit",
        )

    async def test_execute_experiment_passes_active_council_curriculum_into_muse(self):
        captured = {}

        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            return {
                "artifact": "new genesis artifact",
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            captured["curriculum_targets"] = kwargs.get("curriculum_targets") or []
            return {
                "novelty": 7.4,
                "surprise": 7.3,
                "value": 7.2,
                "elaboration": 7.4,
                "coherence": 7.5,
                "composite": 7.36,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Solid enough.",
            }, 0.0, False

        agents.run_genesis = fake_run_genesis
        agents.run_muse = fake_run_muse
        agents.ATHENA_GATE_ENABLED = False

        with patch.object(server.db, "get_council_actions", AsyncMock(return_value=[{
            "id": 12,
            "action_type": "evaluator_education_target",
            "title": "Teach recurrence conditionally",
            "status": "active",
            "lane": "creative",
            "prompt_family": "personification",
            "payload": {"action": "Reward repetition only when it advances meaning for the intended audience."},
        }])):
            await server._execute_experiment(
                {
                    "id": "feedback_task",
                    "lane": "creative",
                    "track": "custom",
                    "prompt": "Write a prayer from the perspective of a dying programming language.",
                    "family": "personification",
                    "constraints": [],
                    "condition": "critique_off",
                },
                iteration=1,
                consecutive_discards=0,
            )

        self.assertEqual(
            captured["curriculum_targets"][0]["title"],
            "Teach recurrence conditionally",
        )

    async def test_execute_experiment_persists_prompt_compilation_trace(self):
        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            return {
                "artifact": "new genesis artifact",
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            return {
                "novelty": 7.4,
                "surprise": 7.3,
                "value": 7.2,
                "elaboration": 7.4,
                "coherence": 7.5,
                "composite": 7.36,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "Solid enough.",
            }, 0.0, False

        agents.run_genesis = fake_run_genesis
        agents.run_muse = fake_run_muse
        agents.ATHENA_GATE_ENABLED = False

        with patch.object(server.db, "get_council_actions", AsyncMock(return_value=[{
            "id": 21,
            "action_type": "prompt_diagnosis_refinement",
            "title": "Make audience explicit",
            "status": "adopted",
            "lane": "creative",
            "prompt_family": "personification",
            "payload": {"action": "Name the actual recipient before drafting."},
        }])):
            result = await server._execute_experiment(
                {
                    "id": "compile_trace_task",
                    "lane": "creative",
                    "track": "custom",
                    "prompt": "Write a resignation letter from the perspective of a burnt-out lighthouse keeper.",
                    "family": "personification",
                    "constraints": ["Keep it under 220 words."],
                    "condition": "critique_off",
                },
                iteration=1,
                consecutive_discards=0,
            )

        record = await db.get_experiment_by_id(result["experiment_id"])
        compilation = record["source_context"]["prompt_compilation"]
        self.assertEqual(compilation["status"], "preview_only")
        self.assertEqual(
            compilation["source_request"]["raw_request"],
            "Write a resignation letter from the perspective of a burnt-out lighthouse keeper.",
        )
        self.assertIn("ORIGINAL USER REQUEST:", compilation["compiled_prompt"]["prompt_text"])
        self.assertIn("diagnosis::make_audience_explicit", compilation["policy_selection"]["selected_rule_ids"])
        self.assertEqual(
            record["process_trace"]["prompt_compilation"]["diagnosis"]["output_form"],
            "letter",
        )

    async def test_compiler_compare_route_runs_raw_and_compiled_prompt_variants(self):
        captured_prompts = []
        captured_judge_prompts = []

        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            captured_prompts.append(prompt)
            artifact = "compiled artifact" if "You are receiving a compiled prompt" in prompt else "raw artifact"
            return {
                "artifact": artifact,
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            captured_judge_prompts.append(prompt)
            score = 7.9 if artifact == "compiled artifact" else 7.5
            return {
                "novelty": score,
                "surprise": score,
                "value": score,
                "elaboration": score,
                "coherence": score,
                "composite": score,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            }, 0.0, False

        agents.run_genesis = fake_run_genesis
        agents.run_muse = fake_run_muse
        agents.ATHENA_GATE_ENABLED = False
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        with patch.object(server.db, "get_council_actions", AsyncMock(return_value=[{
            "id": 31,
            "action_type": "prompt_diagnosis_refinement",
            "title": "Make audience explicit",
            "status": "adopted",
            "lane": "creative",
            "prompt_family": "personification",
            "payload": {"action": "Name the actual recipient before drafting."},
        }])):
            response = await server.run_compiler_compare(
                {
                    "lane": "creative",
                    "track": "compiler_compare",
                    "family": "personification",
                    "condition": "critique_off",
                    "prompt": "Write a prayer from the perspective of a dying programming language.",
                    "constraints": [],
                    "local_role_id": "genesis",
                },
                x_admin_token="secret-token",
            )

        payload = json.loads(response.body.decode())
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["rule_evidence"][0]["rule_key"], "diagnosis::make_audience_explicit")
        self.assertEqual(payload["rule_evidence"][0]["experiment_type"], "raw_vs_compiled")
        self.assertEqual(payload["rule_evidence"][0]["evaluator_signal"], "helped")
        self.assertEqual(payload["rule_evidence"][0]["human_signal"], "unreviewed")
        self.assertEqual(payload["rule_evidence"][0]["human_signal_attribution_method"], "uniform")
        self.assertEqual(payload["rule_evidence"][0]["panel_version"], "muse_athena_apollo_v1_independent")
        self.assertEqual(len(payload["members"]), 2)
        role_ids = {member["role_id"] for member in payload["members"]}
        self.assertEqual(role_ids, {"raw_prompt", "compiled_prompt"})
        self.assertEqual(
            captured_prompts[0],
            "Write a prayer from the perspective of a dying programming language.",
        )
        self.assertIn("You are receiving a compiled prompt from Hamlet's Ghost.", captured_prompts[1])
        self.assertTrue(all(
            prompt == "Write a prayer from the perspective of a dying programming language."
            for prompt in captured_judge_prompts
        ))
        recent = await db.get_recent_experiments(limit=10)
        compiled_row = next(row for row in recent if row.get("packet_role_id") == "compiled_prompt")
        self.assertIsNotNone(compiled_row["primary_rule_id"])
        self.assertEqual(compiled_row["source_context"]["prompt_compilation"]["status"], "compiled_candidate")
        self.assertEqual(compiled_row["source_context"]["evaluation_prompt"], "Write a prayer from the perspective of a dying programming language.")
        rule_slices = await db.list_rule_evidence_slices(limit=5)
        self.assertEqual(rule_slices[0]["rule_key"], "diagnosis::make_audience_explicit")
        self.assertEqual(rule_slices[0]["prompt_family"], "personification")
        self.assertEqual(rule_slices[0]["panel_version"], "muse_athena_apollo_v1_independent")
        self.assertEqual(rule_slices[0]["human_signal"], "unreviewed")

        await db.save_comparison_review(
            payload["packet_id"],
            preferred_experiment_id=compiled_row["id"],
            rationale="Compiled prompt gave the model a clearer rhetorical situation.",
            reviewer="ethan",
            metadata={"review_verdict": "preferred", "review_confidence": "certain"},
        )
        updated_slices = await db.list_rule_evidence_slices(limit=5)
        self.assertEqual(updated_slices[0]["human_signal"], "helped")
        self.assertEqual(updated_slices[0]["human_signal_attribution_method"], "uniform")

    async def test_paired_route_passes_human_feedback_into_theron(self):
        await self._seed_reviewed_pair(
            packet_id="packet_feedback_theron",
            family="personification",
            preferred_role_id="genesis",
            winner_tags=["structural_integrity"],
            loser_tags=["hedged_profundity"],
        )

        captured = {}

        async def fake_run_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            return {
                "artifact": "genesis generated inside packet",
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                    "verification_status": "passed",
                    "verifier_findings": [],
                    "verifier_checks": [],
                    "verifier_inferred_constraints": [],
                    "stage_costs": {},
                },
            }, 0.0, False

        async def fake_run_theron_genesis(prompt, constraints=None, prior_feedback=None, **kwargs):
            captured["prior_feedback"] = prior_feedback
            captured["policy_context"] = kwargs.get("policy_context") or {}
            return {
                "artifact": "theron generated inside packet",
                "process_trace": {
                    "protocol": "theron_paired_native",
                    "artifact_contract_status": "ok",
                },
            }, 0.25, False

        async def fake_run_muse(artifact, prompt, constraints=None, lane="creative", **kwargs):
            score = 8.0 if "theron" in artifact else 7.9
            return {
                "novelty": score,
                "surprise": score,
                "value": score,
                "elaboration": score,
                "coherence": score,
                "composite": score,
                "actionability": None,
                "brand_fit": None,
                "factual_reliability": None,
                "constraints_met": True,
                "constraint_notes": "",
                "critique": "",
            }, 0.0, False

        agents.run_genesis = fake_run_genesis
        agents.run_theron_genesis = fake_run_theron_genesis
        agents.run_muse = fake_run_muse
        agents.ATHENA_GATE_ENABLED = False
        agents.THERON_GENERATION_ENABLED = True
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        response = await server.run_paired_experiment(
            {
                "lane": "creative",
                "track": "paired",
                "family": "personification",
                "condition": "critique_off",
                "prompt": "Write a prayer from the perspective of a dying programming language.",
                "constraints": [],
                "run_local": True,
                "generate_external": True,
                "external_role_id": "theron",
            },
            x_admin_token="secret-token",
        )
        payload = json.loads(response.body.decode())

        self.assertEqual(payload["status"], "completed")
        self.assertIn("hedged_profundity", captured["prior_feedback"])
        self.assertEqual(captured["policy_context"]["track"], "paired_external")
        self.assertEqual(captured["policy_context"]["family"], "personification")
        self.assertEqual(captured["policy_context"]["condition"], "critique_off")
        recent = await db.get_recent_experiments(limit=20)
        theron_rows = [
            row for row in recent
            if row.get("packet_role_id") == "theron"
            and row.get("family") == "personification"
            and row.get("source_context", {}).get("submission_mode") == "paired_native_generated"
        ]
        current_theron = theron_rows[0]
        self.assertEqual(
            current_theron["source_context"]["generator_feedback"]["theron"]["scope_applied"],
            "family_lane",
        )
        self.assertEqual(
            current_theron["source_context"]["generator_feedback"]["theron"]["top_flaws"],
            ["hedged_profundity"],
        )

    async def test_save_disagreement_decision_accepts_both_bad_without_preferred_artifact(self):
        await self._seed_reviewed_pair(
            packet_id="packet_review_verdict",
            family="personification",
            preferred_role_id="theron",
        )
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        response = await server.save_disagreement_decision(
            "packet_review_verdict",
            {
                "preferred_experiment_id": None,
                "rationale": "Both artifacts miss in different ways.",
                "metadata": {
                    "review_verdict": "both_bad",
                    "review_confidence": "tentative",
                    "reason_tag_attribution": {"both": ["hedged_profundity"]},
                },
            },
            x_admin_token="secret-token",
        )
        payload = json.loads(response.body.decode())

        self.assertEqual(payload["status"], "saved")
        self.assertIsNone(payload["review"]["preferred_experiment_id"])
        self.assertEqual(payload["review"]["metadata"]["review_verdict"], "both_bad")

    async def test_run_genesis_normalizes_prompt_diagnosis_when_model_omits_it(self):
        with patch("agents._generate_json_with_retry", new=AsyncMock(return_value=(
            {
                "artifact": "A compact test artifact.",
                "process_trace": {
                    "protocol": "test_probe",
                    "artifact_contract_status": "ok",
                },
            },
            object(),
            False,
        ))):
            result, _cost, parse_failure = await agents.run_genesis(
                prompt="Write a resignation letter from the perspective of a burnt-out lighthouse keeper.",
                constraints=[],
                lane="creative",
                policy_context={"track": "custom", "family": "personification", "condition": "critique_off"},
            )

        self.assertFalse(parse_failure)
        self.assertEqual(
            result["process_trace"]["prompt_diagnosis"],
            {
                "composition_mode": "unspecified",
                "intended_audience": "unspecified",
                "piece_goal": "unspecified",
            },
        )


if __name__ == "__main__":
    unittest.main()
