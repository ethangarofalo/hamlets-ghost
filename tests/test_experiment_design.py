import os
import unittest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import experiments


class ExperimentDesignTests(unittest.TestCase):
    def test_schedule_assigns_first_class_policy_fields(self):
        schedule = experiments.build_experiment_schedule(
            n_experiments=12,
            creative_weight=0.5,
            business_weight=0.5,
            study_mode="exploratory_batch",
        )

        self.assertTrue(schedule)
        for task in schedule:
            self.assertIn("prompt_policy_variant", task)
            self.assertIn("framing_style", task)
            self.assertIn("novelty_pressure", task)
            self.assertIn("audience_grounding_level", task)
            self.assertIn("study_mode", task)
            self.assertIn("generation_guidance", task)
            self.assertTrue(task["prompt_policy_variant"])
            self.assertTrue(task["study_mode"])

    def test_schedule_frontloads_policy_validation_for_unvalidated_defaults(self):
        schedule = experiments.build_experiment_schedule(
            n_experiments=12,
            approved_policy_controls={
                ("business", "retention_messaging"): {
                    "approved_value": "humanized_trust",
                    "operational_status": "approved_pending_use",
                }
            },
        )

        validation_runs = [task for task in schedule if task.get("study_mode") == "policy_validation"]
        self.assertTrue(validation_runs)
        self.assertTrue(all(task["policy_source"] == "approved_family_default" for task in validation_runs))
        self.assertTrue(all(task["prompt_policy_variant"] == "humanized_trust" for task in validation_runs))

    def test_apply_policy_variant_uses_lane_defaults(self):
        creative_task = experiments.apply_policy_variant({
            "lane": "creative",
            "prompt": "demo creative task",
        })
        business_task = experiments.apply_policy_variant({
            "lane": "business",
            "prompt": "demo business task",
        })

        self.assertEqual(creative_task["prompt_policy_variant"], experiments.DEFAULT_POLICY_VARIANTS["creative"])
        self.assertEqual(business_task["prompt_policy_variant"], experiments.DEFAULT_POLICY_VARIANTS["business"])
        self.assertEqual(creative_task["policy_source"], "system_default")
        self.assertEqual(business_task["policy_source"], "system_default")

    def test_apply_policy_control_marks_approved_default_provenance(self):
        task = experiments.apply_policy_control(
            {
                "lane": "business",
                "family": "retention_messaging",
                "prompt": "demo business task",
            },
            approved_default_variant="humanized_trust",
        )

        self.assertEqual(task["prompt_policy_variant"], "humanized_trust")
        self.assertEqual(task["policy_source"], "approved_family_default")
        self.assertEqual(task["approved_family_policy_variant"], "humanized_trust")

    def test_apply_policy_control_preserves_manual_override(self):
        task = experiments.apply_policy_control(
            {
                "lane": "creative",
                "family": "impossible_object",
                "prompt": "demo creative task",
                "prompt_policy_variant": "metaphorical_push",
            },
            approved_default_variant="balanced_imagery",
        )

        self.assertEqual(task["prompt_policy_variant"], "metaphorical_push")
        self.assertEqual(task["policy_source"], "manual_override")
        self.assertEqual(task["approved_family_policy_variant"], "balanced_imagery")


if __name__ == "__main__":
    unittest.main()
