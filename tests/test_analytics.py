import os
import unittest

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

    def test_protocol_reliability_surfaces_fallback_and_forced_hermes_rates(self):
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
                            "hermes": {"decision": "run", "reason": "forced_sample_low_muse"}
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
                            "hermes": {"decision": "skipped", "reason": "muse_below_threshold_6.5"}
                        }
                    },
                },
            },
        ])

        self.assertIn("Protocol reliability tracked across 2 runs.", summary["headline"])
        self.assertAlmostEqual(summary["overview"]["selection_fallback_rate"], 0.5)
        self.assertAlmostEqual(summary["overview"]["interlocutor_fallback_rate"], 0.5)
        self.assertAlmostEqual(summary["overview"]["hermes_skip_rate"], 0.5)
        self.assertAlmostEqual(summary["overview"]["hermes_forced_rate"], 0.5)
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
        self.assertIn("unknown constraints 50%", metrics["headline"])

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


if __name__ == "__main__":
    unittest.main()
