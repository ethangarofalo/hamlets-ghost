import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import agents
import database as db
import experiments
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
        self.original_run_muse = agents.run_muse
        self.original_run_hermes = agents.run_hermes
        self.original_run_external_hermes = getattr(agents, "run_external_hermes", None)
        self.original_hermes_gate_enabled = agents.HERMES_GATE_ENABLED
        self.original_hermes_min_muse_composite = agents.HERMES_MIN_MUSE_COMPOSITE
        self.original_hermes_require_constraint_pass = agents.HERMES_REQUIRE_CONSTRAINT_PASS
        self.original_hermes_external_shadow_enabled = getattr(agents, "HERMES_EXTERNAL_SHADOW_ENABLED", False)
        self.original_genesis_openclaw_shadow_enabled = getattr(agents, "GENESIS_OPENCLAW_SHADOW_ENABLED", False)
        self.original_genesis_openclaw_families = getattr(agents, "GENESIS_OPENCLAW_FAMILIES", set())
        self.original_forced_hermes_low_score_modulo = server.FORCED_HERMES_LOW_SCORE_MODULO
        self.original_forced_hermes_constraint_fail_modulo = server.FORCED_HERMES_CONSTRAINT_FAIL_MODULO
        self.original_forced_hermes_unknown_constraint_modulo = server.FORCED_HERMES_UNKNOWN_CONSTRAINT_MODULO

        agents.HERMES_GATE_ENABLED = True
        agents.HERMES_MIN_MUSE_COMPOSITE = 999.0
        agents.HERMES_REQUIRE_CONSTRAINT_PASS = True
        agents.HERMES_EXTERNAL_SHADOW_ENABLED = False
        agents.GENESIS_OPENCLAW_SHADOW_ENABLED = False
        agents.GENESIS_OPENCLAW_FAMILIES = set()
        server.FORCED_HERMES_LOW_SCORE_MODULO = self.original_forced_hermes_low_score_modulo
        server.FORCED_HERMES_CONSTRAINT_FAIL_MODULO = self.original_forced_hermes_constraint_fail_modulo
        server.FORCED_HERMES_UNKNOWN_CONSTRAINT_MODULO = self.original_forced_hermes_unknown_constraint_modulo

    async def asyncTearDown(self):
        agents.run_genesis = self.original_run_genesis
        if self.original_run_openclaw_genesis is not None:
            agents.run_openclaw_genesis = self.original_run_openclaw_genesis
        agents.run_muse = self.original_run_muse
        agents.run_hermes = self.original_run_hermes
        if self.original_run_external_hermes is not None:
            agents.run_external_hermes = self.original_run_external_hermes
        agents.HERMES_GATE_ENABLED = self.original_hermes_gate_enabled
        agents.HERMES_MIN_MUSE_COMPOSITE = self.original_hermes_min_muse_composite
        agents.HERMES_REQUIRE_CONSTRAINT_PASS = self.original_hermes_require_constraint_pass
        agents.HERMES_EXTERNAL_SHADOW_ENABLED = self.original_hermes_external_shadow_enabled
        agents.GENESIS_OPENCLAW_SHADOW_ENABLED = self.original_genesis_openclaw_shadow_enabled
        agents.GENESIS_OPENCLAW_FAMILIES = self.original_genesis_openclaw_families
        server.FORCED_HERMES_LOW_SCORE_MODULO = self.original_forced_hermes_low_score_modulo
        server.FORCED_HERMES_CONSTRAINT_FAIL_MODULO = self.original_forced_hermes_constraint_fail_modulo
        server.FORCED_HERMES_UNKNOWN_CONSTRAINT_MODULO = self.original_forced_hermes_unknown_constraint_modulo
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def _run_experiment(
        self,
        *,
        constraints,
        muse_result,
        muse_parse_failure,
        muse_cost=0.0,
        hermes_result=None,
        hermes_parse_failure=False,
        hermes_cost=0.0,
        hermes_should_raise=False,
        external_hermes_result=None,
        external_hermes_parse_failure=False,
        external_hermes_cost=0.0,
        external_hermes_should_raise=False,
        enable_external_hermes=False,
        openclaw_genesis_result=None,
        openclaw_genesis_parse_failure=False,
        openclaw_genesis_cost=0.0,
        openclaw_genesis_should_raise=False,
        enable_openclaw_genesis=False,
        hermes_min_muse_composite=999.0,
        genesis_artifact="rain in dusk\nrain on stone\nrain goes on",
        process_trace=None,
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

        async def fake_run_hermes(artifact, prompt, constraints=None, lane="creative", **kwargs):
            if hermes_should_raise:
                raise RuntimeError("simulated hermes failure")
            payload = dict(hermes_result) if hermes_result is not None else {
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
            return payload, hermes_cost, hermes_parse_failure

        async def fake_run_external_hermes(artifact, prompt, constraints=None, lane="creative", **kwargs):
            if external_hermes_should_raise:
                raise RuntimeError("simulated external hermes failure")
            payload = dict(external_hermes_result) if external_hermes_result is not None else {
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
            return payload, external_hermes_cost, external_hermes_parse_failure

        agents.run_genesis = fake_run_genesis
        agents.run_openclaw_genesis = fake_run_openclaw_genesis
        agents.run_muse = fake_run_muse
        agents.run_hermes = fake_run_hermes
        agents.run_external_hermes = fake_run_external_hermes
        agents.HERMES_MIN_MUSE_COMPOSITE = hermes_min_muse_composite
        agents.HERMES_EXTERNAL_SHADOW_ENABLED = enable_external_hermes
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
            },
            iteration=(state["total_experiments"] or 0) + 1,
            consecutive_discards=state.get("consecutive_discards") or 0,
        )
        return result

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
            hermes_result={
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
            hermes_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status, parse_failure FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        holdout_score = self._fetch_one(
            "SELECT composite, constraints_met, parse_failure FROM scores WHERE experiment_id = ? AND scored_by = 'hermes'",
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
            hermes_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        muse_score = self._fetch_one(
            "SELECT constraints_met FROM scores WHERE experiment_id = ? AND scored_by = 'muse'",
            (result["experiment_id"],),
        )
        hermes_count = self._fetch_one(
            "SELECT COUNT(*) AS count FROM scores WHERE experiment_id = ? AND scored_by = 'hermes'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "constraint_fail")
        self.assertEqual(experiment["status"], "constraint_fail")
        self.assertEqual(experiment["promotion_status"], "candidate")
        self.assertEqual(muse_score["constraints_met"], 0)
        self.assertEqual(hermes_count["count"], 0)

    async def test_high_composite_with_hermes_parse_failure_is_kept_not_promoted(self):
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
            hermes_result={
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
            },
            hermes_parse_failure=True,
            hermes_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        hermes_count = self._fetch_one(
            "SELECT COUNT(*) AS count FROM scores WHERE experiment_id = ? AND scored_by = 'hermes'",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "kept")
        self.assertEqual(result["promotion_status"], "candidate")
        self.assertEqual(experiment["status"], "kept")
        self.assertEqual(experiment["promotion_status"], "candidate")
        self.assertEqual(hermes_count["count"], 0)

    async def test_low_muse_run_can_force_hermes_sampling_for_calibration(self):
        server.FORCED_HERMES_LOW_SCORE_MODULO = 1
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
            hermes_result={
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
            hermes_min_muse_composite=6.5,
        )

        holdout_score = self._fetch_one(
            "SELECT composite FROM scores WHERE experiment_id = ? AND scored_by = 'hermes'",
            (result["experiment_id"],),
        )
        artifact = self._fetch_one(
            "SELECT process_trace FROM artifacts WHERE experiment_id = ?",
            (result["experiment_id"],),
        )

        self.assertIsNotNone(holdout_score)
        self.assertIn("forced_sample_low_muse", artifact["process_trace"])

    async def test_external_hermes_shadow_is_logged_without_changing_promotion_gate(self):
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
            hermes_result={
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
            external_hermes_result={
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
            enable_external_hermes=True,
            hermes_min_muse_composite=6.5,
        )

        experiment = self._fetch_one(
            "SELECT status, promotion_status FROM experiments WHERE id = ?",
            (result["experiment_id"],),
        )
        external_holdout = self._fetch_one(
            "SELECT composite FROM scores WHERE experiment_id = ? AND scored_by = 'hermes_external'",
            (result["experiment_id"],),
        )
        artifact = self._fetch_one(
            "SELECT process_trace, source_context FROM artifacts WHERE experiment_id = ?",
            (result["experiment_id"],),
        )

        self.assertEqual(result["status"], "promoted")
        self.assertEqual(experiment["promotion_status"], "shadow")
        self.assertEqual(external_holdout["composite"], 5.9)
        self.assertIn("hermes_external", artifact["process_trace"])
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
            hermes_result={
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
            hermes_min_muse_composite=6.5,
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


if __name__ == "__main__":
    unittest.main()
