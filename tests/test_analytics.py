import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import database as db


class AnalyticsTests(unittest.TestCase):
    def test_policy_validation_summary_tracks_pending_trial_and_validated_defaults(self):
        summary = db._build_policy_validation_summary([
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "policy_key": "prompt_policy_default",
                "approval_status": "approved",
                "approved_value": "humanized_trust",
                "operational_status": "approved_pending_use",
                "adopted_trials": 0,
            },
            {
                "lane": "creative",
                "prompt_family": "impossible_object",
                "policy_key": "prompt_policy_default",
                "approval_status": "approved",
                "approved_value": "balanced_imagery",
                "operational_status": "approved_in_trial",
                "adopted_trials": 2,
                "adopted_mean_composite": 7.8,
            },
            {
                "lane": "business",
                "prompt_family": "founder_story",
                "policy_key": "prompt_policy_default",
                "approval_status": "approved",
                "approved_value": "creative_push",
                "operational_status": "approved_validated",
                "adopted_trials": 4,
                "adopted_mean_composite": 8.2,
            },
        ])

        self.assertIn("3 approved family defaults tracked.", summary["headline"])
        self.assertEqual(summary["overview"]["approved_pending_use"], 1)
        self.assertEqual(summary["overview"]["approved_in_trial"], 1)
        self.assertEqual(summary["overview"]["approved_validated"], 1)

    def test_protocol_reliability_surfaces_fallback_and_forced_athena_rates(self):
        summary = db._build_protocol_reliability([
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "process_trace": {
                    "branch_status": "ok",
                    "selection_status": "fallback_first_candidate",
                    "interlocutor_status": "fallback_questions",
                    "revision_status": "ok",
                    "verification_status": "passed_after_repair",
                    "orchestration": {
                        "gates": {
                            "athena": {"decision": "run", "reason": "forced_sample_low_muse"}
                        }
                    },
                },
            },
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "process_trace": {
                    "branch_status": "fallback_single_candidate",
                    "selection_status": "ok",
                    "interlocutor_status": "ok",
                    "revision_status": "parse_failed",
                    "verification_status": "not_run",
                    "orchestration": {
                        "gates": {
                            "athena": {"decision": "skipped", "reason": "muse_below_threshold_6.5"}
                        }
                    },
                },
            },
        ])

        self.assertIn("Protocol reliability tracked across 2 runs.", summary["headline"])
        self.assertAlmostEqual(summary["overview"]["selection_fallback_rate"], 0.5)
        self.assertAlmostEqual(summary["overview"]["interlocutor_fallback_rate"], 0.5)
        self.assertAlmostEqual(summary["overview"]["athena_skip_rate"], 0.5)
        self.assertAlmostEqual(summary["overview"]["athena_forced_rate"], 0.5)
        self.assertEqual(summary["protocol_versions"]["socratic_revision_parse_failed"], 1)

    def test_policy_effects_reports_family_relative_lift_and_risk(self):
        rows = [
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "prompt_policy_variant": "plain_operator",
                "framing_style": "plain",
                "novelty_pressure": "low",
                "audience_grounding_level": "specific_operator",
                "trials": 4,
                "mean_composite": 7.0,
                "constraint_fail_rate": 0.0,
                "unknown_constraint_rate": 0.0,
                "human_keep_rate": 0.5,
                "critique_delta": 0.1,
            },
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "prompt_policy_variant": "humanized_trust",
                "framing_style": "humanized",
                "novelty_pressure": "medium",
                "audience_grounding_level": "specific_operator",
                "trials": 4,
                "mean_composite": 8.0,
                "constraint_fail_rate": 0.25,
                "unknown_constraint_rate": 0.0,
                "human_keep_rate": 0.75,
                "critique_delta": 0.6,
            },
        ]

        summary = db._build_policy_effects(rows)

        self.assertIn("Policy effects tracked across 2 lane/family/variant cells.", summary["headline"])
        self.assertEqual(summary["overview"]["best_variant"]["prompt_policy_variant"], "humanized_trust")
        self.assertEqual(summary["overview"]["critique_sensitive_variant"]["prompt_policy_variant"], "humanized_trust")
        top_row = summary["rows"][0]
        self.assertEqual(top_row["prompt_policy_variant"], "humanized_trust")
        self.assertAlmostEqual(top_row["composite_lift"], 0.5)

    def test_policy_recommendations_promote_winning_variant_to_family_default(self):
        family_metrics = [
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "sample_size": 8,
                "overreach_rate": 0.0,
                "constraint_recovery_rate": None,
                "critique_help_rate": 0.5,
                "novelty_gap": -0.4,
            }
        ]
        policy_effect_rows = [
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "prompt_policy_variant": "plain_operator",
                "trials": 4,
                "composite_lift": -0.5,
                "human_keep_lift": -0.25,
                "constraint_fail_rate": 0.0,
                "unknown_constraint_rate": 0.0,
                "critique_delta": 0.1,
            },
            {
                "lane": "business",
                "prompt_family": "retention_messaging",
                "prompt_policy_variant": "humanized_trust",
                "trials": 4,
                "composite_lift": 0.5,
                "human_keep_lift": 0.25,
                "constraint_fail_rate": 0.0,
                "unknown_constraint_rate": 0.0,
                "critique_delta": 0.4,
            },
        ]

        recommendations = db._build_policy_recommendations(
            family_metrics,
            policy_effect_rows,
            registry_rows=[],
        )

        variant_defaults = [
            row for row in recommendations["rows"]
            if row["policy_key"] == "prompt_policy_default"
        ]
        self.assertEqual(len(variant_defaults), 1)
        self.assertEqual(variant_defaults[0]["recommended_value"], "humanized_trust")
        self.assertIn("outperforming", variant_defaults[0]["rationale"])

    def test_policy_recommendations_track_approved_default_operational_status(self):
        recommendations = db._build_policy_recommendations(
            family_metrics=[],
            policy_effect_rows=[],
            registry_rows=[
                {
                    "lane": "business",
                    "prompt_family": "retention_messaging",
                    "policy_key": "prompt_policy_default",
                    "recommended_value": "humanized_trust",
                    "approved_value": "humanized_trust",
                    "approval_status": "approved",
                    "rationale": "Approved from prior review.",
                    "reviewer_note": None,
                    "updated_at": "2026-04-01 12:00:00",
                }
            ],
            adoption_rows=[
                {
                    "lane": "business",
                    "prompt_family": "retention_messaging",
                    "policy_key": "prompt_policy_default",
                    "approved_value": "humanized_trust",
                    "adopted_trials": 3,
                    "adopted_mean_composite": 8.1,
                    "adopted_constraint_fail_rate": 0.0,
                    "adopted_human_keep_rate": 1.0,
                }
            ],
        )

        self.assertEqual(len(recommendations["rows"]), 1)
        row = recommendations["rows"][0]
        self.assertEqual(row["operational_status"], "approved_validated")
        self.assertEqual(row["adopted_trials"], 3)
        self.assertAlmostEqual(row["adopted_mean_composite"], 8.1)

    def test_calibration_metrics_reports_unknown_constraint_rate(self):
        rows = [
            {
                "lane": "creative",
                "prompt_family": "custom_operator",
                "status": "kept",
                "composite": 7.2,
                "novelty": 6.0,
                "surprise": 6.0,
                "balance_gap": 0.0,
                "balance_counterpart": 6.0,
                "constraints_met": True,
            },
            {
                "lane": "creative",
                "prompt_family": "custom_operator",
                "status": "constraint_fail",
                "composite": 6.4,
                "novelty": 6.1,
                "surprise": 6.0,
                "balance_gap": 0.0,
                "balance_counterpart": 6.0,
                "constraints_met": None,
            },
            {
                "lane": "creative",
                "prompt_family": "custom_operator",
                "status": "discard",
                "composite": 6.8,
                "novelty": 5.8,
                "surprise": 5.9,
                "balance_gap": 0.0,
                "balance_counterpart": 6.0,
                "constraints_met": None,
            },
            {
                "lane": "creative",
                "prompt_family": "custom_operator",
                "status": "constraint_fail",
                "composite": 6.1,
                "novelty": 6.2,
                "surprise": 6.1,
                "balance_gap": 0.0,
                "balance_counterpart": 6.0,
                "constraints_met": False,
            },
        ]

        metrics = db._build_calibration_metrics(
            rows,
            verifier_rows=[],
            paired_rows=[],
            calibration_rows=[],
        )

        self.assertAlmostEqual(metrics["overview"]["unknown_constraint_rate"], 0.5)

    def test_human_calibration_summary_tracks_confidence_and_reversals(self):
        summary = db._build_human_calibration_summary([
            {
                "lane": "creative",
                "muse_composite": 8.1,
                "metadata": {
                    "review_confidence": "certain",
                    "review_decision_state": "final",
                    "pair_distinctiveness": "clearly_distinct",
                    "review_reversal_count": 1,
                },
            },
            {
                "lane": "creative",
                "muse_composite": 7.4,
                "metadata": {
                    "review_confidence": "coin_flip",
                    "review_decision_state": "revisit_later",
                    "pair_distinctiveness": "same_writer",
                    "review_reversal_count": 0,
                },
            },
        ])

        self.assertIn("2 human calibration reviews recorded.", summary["headline"])
        self.assertEqual(summary["confidence_mix"]["certain"], 1)
        self.assertEqual(summary["confidence_mix"]["coin_flip"], 1)
        self.assertEqual(summary["distinctiveness_mix"]["same_writer"], 1)
        self.assertEqual(summary["revisit_later_count"], 1)
        self.assertEqual(summary["low_confidence_count"], 1)
        self.assertEqual(summary["same_writer_count"], 1)
        self.assertAlmostEqual(summary["comparative_usefulness_score"], 0.5)
        self.assertEqual(summary["reversal_count"], 1)

    def test_learning_snapshot_excludes_unknown_constraints_from_regression_delta(self):
        rows = [
            {
                "lane": "creative",
                "status": "kept",
                "composite": 7.0,
                "novelty": 6.0,
                "surprise": 6.0,
                "constraints_met": None,
            }
            for _ in range(10)
        ] + [
            {
                "lane": "creative",
                "status": "constraint_fail",
                "composite": 7.0,
                "novelty": 6.0,
                "surprise": 6.0,
                "constraints_met": False,
            }
            for _ in range(10)
        ]

        snapshot = db._build_learning_snapshot(
            rows,
            paired_rows=[],
            verifier_rows=[],
            calibration_rows=[],
        )

        self.assertEqual(snapshot["regressed"], "No clear regression yet.")

    def test_learning_snapshot_reports_constraint_improvement_from_known_values_only(self):
        rows = [
            {
                "lane": "creative",
                "status": "kept",
                "composite": 7.2,
                "novelty": 6.0,
                "surprise": 6.0,
                "constraints_met": True if idx < 5 else None,
            }
            for idx in range(10)
        ] + [
            {
                "lane": "creative",
                "status": "constraint_fail",
                "composite": 7.2,
                "novelty": 6.0,
                "surprise": 6.0,
                "constraints_met": False if idx < 5 else None,
            }
            for idx in range(10)
        ]

        snapshot = db._build_learning_snapshot(
            rows,
            paired_rows=[],
            verifier_rows=[],
            calibration_rows=[],
        )

        self.assertIn("Constraint pass rate improved +100%", snapshot["improved"])

    def test_generator_learning_summary_surfaces_family_level_coaching(self):
        records = [
            {
                "id": 1,
                "lane": "creative",
                "prompt_family": "personification",
                "packet_role_id": "genesis",
                "comparison_packet": {"packet_id": "pkt1", "explicit": True, "size": 2},
                "source_context": {},
                "critique": "Avoid generic reassurance.",
            },
            {
                "id": 2,
                "lane": "creative",
                "prompt_family": "personification",
                "packet_role_id": "theron",
                "comparison_packet": {"packet_id": "pkt1", "explicit": True, "size": 2},
                "source_context": {},
                "critique": "",
            },
        ]
        calibration_rows = [
            {
                "packet_id": "pkt1",
                "preferred_experiment_id": 2,
                "metadata": {
                    "reason_tag_attribution": {
                        "winner": ["real_pathos"],
                        "loser": ["generic_reassurance"],
                        "both": [],
                        "unattributed": [],
                    },
                    "reason_tag_evidence": [
                        {"tag": "generic_reassurance", "target": "loser", "excerpt": "The losing artifact softened into boilerplate."},
                    ],
                    "review_confidence": "certain",
                    "review_decision_state": "final",
                },
            }
        ]

        summary = db._build_generator_learning_summary(records, calibration_rows)
        by_role = {row["role_id"]: row for row in summary["rows"]}

        self.assertIn("human-reviewed packet history", summary["headline"])
        self.assertEqual(by_role["genesis"]["focus_family"], "personification")
        self.assertEqual(by_role["genesis"]["focus_top_flaws"], ["generic_reassurance"])
        self.assertIn("generic_reassurance", by_role["genesis"]["prior_feedback"])
        self.assertEqual(by_role["theron"]["focus_top_strengths"], ["real_pathos"])

    def test_generator_learning_summary_tracks_pair_separation_failures(self):
        records = [
            {
                "id": 1,
                "lane": "creative",
                "prompt_family": "personification",
                "packet_role_id": "genesis",
                "comparison_packet": {"packet_id": "pkt1", "explicit": True, "size": 2},
                "source_context": {},
                "critique": "",
            },
            {
                "id": 2,
                "lane": "creative",
                "prompt_family": "personification",
                "packet_role_id": "theron",
                "comparison_packet": {"packet_id": "pkt1", "explicit": True, "size": 2},
                "source_context": {},
                "critique": "",
            },
        ]
        calibration_rows = [
            {
                "packet_id": "pkt1",
                "preferred_experiment_id": None,
                "metadata": {
                    "review_verdict": "tie",
                    "review_confidence": "tentative",
                    "review_decision_state": "final",
                    "pair_distinctiveness": "same_writer",
                    "reason_tag_attribution": {
                        "winner": [],
                        "loser": [],
                        "both": ["voice_collapse"],
                        "unattributed": [],
                    },
                    "reason_tag_evidence": [],
                },
            }
        ]

        summary = db._build_generator_learning_summary(records, calibration_rows)
        by_role = {row["role_id"]: row for row in summary["rows"]}

        self.assertEqual(by_role["genesis"]["same_writer_reviews"], 1)
        self.assertEqual(by_role["theron"]["same_writer_reviews"], 1)
        self.assertEqual(by_role["genesis"]["top_pair_failures"], ["voice_collapse"])
        self.assertEqual(by_role["theron"]["top_pair_failures"], ["voice_collapse"])
        self.assertEqual(by_role["genesis"]["low_confidence_reviews"], 1)
        self.assertIn("same writer across generators", by_role["genesis"]["prior_feedback"])


class AnalyticsEpochTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_analytics_epoch.db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db._db_initialized = False
        db._initialized_db_path = None
        await db.init_db()

    async def asyncTearDown(self):
        db.DB_PATH = self.original_db_path
        db._db_initialized = False
        db._initialized_db_path = None
        self.temp_dir.cleanup()

    async def test_analysis_defaults_to_current_epoch_and_preserves_summary(self):
        current_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Current epoch prompt",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "paired_native",
        }
        legacy_task = {
            **current_task,
            "prompt": "Legacy prompt",
            "epoch": db.LEGACY_EXPERIMENT_EPOCH,
        }

        current_id = await db.create_experiment(current_task, status="kept")
        legacy_id = await db.create_experiment(legacy_task, status="kept")
        await db.insert_artifact(current_id, "Current artifact")
        await db.insert_artifact(legacy_id, "Legacy artifact")
        await db.insert_score(current_id, "muse", {"composite": 8.4, "novelty": 8.0, "surprise": 8.1, "value": 8.2, "elaboration": 8.3, "coherence": 8.4})
        await db.insert_score(legacy_id, "muse", {"composite": 6.1, "novelty": 6.0, "surprise": 6.1, "value": 6.0, "elaboration": 6.2, "coherence": 6.1})
        await db.finalize_experiment(current_id, status="kept", promotion_status="candidate")
        await db.finalize_experiment(legacy_id, status="kept", promotion_status="candidate")

        payload = await db.get_analysis_payload()

        self.assertEqual(payload["analysis_scope"]["epoch"], db.CURRENT_EXPERIMENT_EPOCH)
        self.assertEqual(payload["balance_summary"]["headline"], "Balance readout across 1 scored runs.")
        epochs = {row["epoch"]: row["experiment_count"] for row in payload["epoch_summary"]["epochs"]}
        self.assertEqual(epochs[db.CURRENT_EXPERIMENT_EPOCH], 1)
        self.assertEqual(epochs[db.LEGACY_EXPERIMENT_EPOCH], 1)


if __name__ == "__main__":
    unittest.main()
