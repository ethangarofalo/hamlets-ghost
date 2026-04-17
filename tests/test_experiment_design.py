import os
import unittest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import experiments


class ExperimentDesignTests(unittest.TestCase):
    def test_prompt_library_loads_expected_corpus_shape(self):
        self.assertEqual(experiments.PROMPT_LIBRARY_VERSION, "2026-04-03")
        self.assertEqual(len(experiments.ALL_TASKS), 100)
        self.assertEqual(len(experiments.CREATIVE_CONSTRAINED), 40)
        self.assertEqual(len(experiments.CREATIVE_OPEN), 10)
        self.assertEqual(len(experiments.CREATIVE_TRANSFORMATIONAL), 10)
        self.assertEqual(len(experiments.BUSINESS_TASKS), 40)
        self.assertIn("c08", experiments.ALL_TASKS)
        self.assertIn("b02", experiments.ALL_TASKS)
        self.assertEqual(experiments.PROMPT_LIBRARY_DEFAULTS["status"], "active")
        self.assertEqual(experiments.PROMPT_LIBRARY_DEFAULTS["provenance"], "hamlets_ghost_seed_corpus")

    def test_prompt_library_normalizes_metadata_fields(self):
        task = experiments.ALL_TASKS["c08"]

        self.assertEqual(task["status"], "active")
        self.assertEqual(task["provenance"], "hamlets_ghost_seed_corpus")
        self.assertIn(task["difficulty"], experiments.PROMPT_DIFFICULTIES)
        self.assertIn(task["human_judgment_priority"], {"low", "medium", "high"})
        self.assertIn("creative", task["tags"])
        self.assertIn("personification", task["tags"])
        self.assertIn("h_personification", task["tags"])
        self.assertIsInstance(task["notes"], str)

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

    def test_get_next_task_draws_from_structured_library(self):
        creative_task = experiments.get_next_task(track="transformational")
        business_task = experiments.get_next_task(lane="business")

        self.assertEqual(creative_task["track"], "transformational")
        self.assertEqual(creative_task["lane"], "creative")
        self.assertEqual(business_task["lane"], "business")
        self.assertIn("constraints", creative_task)
        self.assertIn("constraints", business_task)

    def test_prompt_metadata_query_helpers_work(self):
        active_tasks = experiments.get_tasks_by_status("active")
        high_priority_tasks = experiments.get_human_review_priority_tasks("high")

        self.assertEqual(len(active_tasks), 100)
        self.assertTrue(high_priority_tasks)
        self.assertTrue(all(task["status"] == "active" for task in high_priority_tasks))
        self.assertTrue(all(task["human_judgment_priority"] == "high" for task in high_priority_tasks))


if __name__ == "__main__":
    unittest.main()
