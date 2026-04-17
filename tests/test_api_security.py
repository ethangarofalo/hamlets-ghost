import os
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient

import server


@asynccontextmanager
async def _noop_lifespan(app):
    yield


class ApiSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_lifespan = server.app.router.lifespan_context
        server.app.router.lifespan_context = _noop_lifespan
        self.original_admin_token = os.environ.get("LAB_ADMIN_TOKEN")
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server.app.router.lifespan_context = self.original_lifespan
        if self.original_admin_token is None:
            os.environ.pop("LAB_ADMIN_TOKEN", None)
        else:
            os.environ["LAB_ADMIN_TOKEN"] = self.original_admin_token

    def test_write_route_rejects_missing_admin_token(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        response = self.client.post("/api/start", json={"n_experiments": 1})

        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.json()["error"])

    def test_write_route_rejects_when_admin_token_not_configured(self):
        os.environ.pop("LAB_ADMIN_TOKEN", None)

        response = self.client.post("/api/start", json={"n_experiments": 1})

        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["error"])

    def test_artifact_route_rejects_missing_admin_token(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        response = self.client.get("/api/artifact/123")

        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.json()["error"])

    def test_artifact_response_redacts_internal_traceback(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"
        with patch.object(server.db, "get_experiment_by_id", AsyncMock(return_value={
            "id": 123,
            "status": "error",
            "prompt": "demo",
            "error_traceback": "Traceback (most recent call last): secret details",
        })), patch.object(server.db, "get_holdout_scores", AsyncMock(return_value=[])):
            response = self.client.get(
                "/api/artifact/123",
                headers={"X-Admin-Token": "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("error_traceback", payload)
        self.assertTrue(payload["has_internal_error_details"])
        self.assertIn("Check server logs", payload["error_summary"])

    def test_external_experiment_route_rejects_missing_artifact(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        response = self.client.post(
            "/api/experiment/external",
            json={"prompt": "demo prompt", "artifact": "   "},
            headers={"X-Admin-Token": "secret-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("artifact is required", response.json()["error"])

    def test_paired_experiment_route_rejects_missing_prompt(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        response = self.client.post(
            "/api/experiment/paired",
            json={"external_artifacts": [{"artifact": "demo"}]},
            headers={"X-Admin-Token": "secret-token"},
        )

        self.assertEqual(response.status_code, 422)

    def test_disagreement_decision_route_rejects_missing_admin_token(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        response = self.client.post(
            "/api/review/disagreements/packet_demo/decision",
            json={"preferred_experiment_id": 1, "rationale": "Option 1 is stronger."},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.json()["error"])

    def test_review_reason_tag_catalog_is_available(self):
        response = self.client.get("/api/review/reason-tags")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("anti_patterns", payload)
        self.assertIn("quality_signals", payload)
        self.assertIn("evaluator_failure_modes", payload)
        self.assertTrue(any(entry["tag"] == "generic_reassurance" for entry in payload["anti_patterns"]))
        self.assertTrue(any(entry["tag"] == "repetition_as_depth" for entry in payload["anti_patterns"]))
        self.assertTrue(any(entry["tag"] == "trustworthy_tone" for entry in payload["quality_signals"]))
        self.assertTrue(any(entry["tag"] == "rhetorical_situation_blindness" for entry in payload["evaluator_failure_modes"]))

    def test_council_trigger_returns_structured_curriculum_fields(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        analysis_payload = {
            "analysis_scope": {"epoch": "native_cast"},
            "human_calibration": {
                "same_writer_count": 2,
                "low_confidence_count": 1,
                "comparative_usefulness_score": 0.25,
            },
            "generator_learning": [
                {"role_id": "genesis", "top_pair_failures": ["voice_collapse"]},
                {"role_id": "theron", "top_pair_failures": ["voice_collapse"]},
            ],
            "evaluator_diagnostics": {
                "warnings": ["Evaluator disagreement is high enough that human calibration should stay active."],
            },
            "learning_snapshot": {
                "still_noisy": "Human versus MUSE agreement is still noisy.",
            },
        }
        calibration_rows = [
            {"metadata": {"reason_tags": ["repetition_as_depth", "voice_collapse"]}},
            {"metadata": {"reason_tags": ["rhetorical_situation_blindness"]}},
        ]

        with patch.object(server.db, "get_analysis_payload", AsyncMock(return_value=analysis_payload)), \
             patch.object(server.db, "get_recent_calibration_reviews", AsyncMock(return_value=calibration_rows)), \
             patch.object(server.db, "get_council_history", AsyncMock(return_value=[])), \
             patch.object(server.db, "add_council_entry", AsyncMock(return_value=1)):
            response = self.client.post(
                "/api/council/trigger",
                headers={"X-Admin-Token": "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["council_id"], 1)
        self.assertEqual(payload["session_number"], 1)
        self.assertIn("prompt diagnosis", payload["prompt_diagnosis_assessment"].lower())
        self.assertIn("repetition as depth", payload["evaluator_education_assessment"].lower())
        self.assertIn("cartography", payload["recommendation"].lower())
        self.assertEqual(payload["analysis_epoch"], "native_cast")
        self.assertTrue(payload["prompt_diagnosis_recommendations"])
        self.assertTrue(payload["evaluator_education_recommendations"])
        self.assertTrue(payload["contrast_set_candidates"])

    def test_council_action_routes_save_and_list_governed_actions(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"
        saved_action = {
            "id": 9,
            "council_id": 3,
            "action_type": "prompt_diagnosis_refinement",
            "title": "Make audience explicit",
            "status": "adopted",
            "lane": None,
            "prompt_family": None,
            "payload": {"action": "Name the actual recipient before drafting."},
            "created_at": "2026-04-09 15:00:00",
            "updated_at": "2026-04-09 15:00:00",
        }

        with patch.object(server.db, "upsert_council_action", AsyncMock(return_value=saved_action)):
            post_response = self.client.post(
                "/api/council/actions",
                json={
                    "council_id": 3,
                    "action_type": "prompt_diagnosis_refinement",
                    "title": "Make audience explicit",
                    "status": "adopted",
                    "payload": {"action": "Name the actual recipient before drafting."},
                },
                headers={"X-Admin-Token": "secret-token"},
            )

        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(post_response.json()["action"]["title"], "Make audience explicit")

        with patch.object(server.db, "get_council_actions", AsyncMock(return_value=[saved_action])):
            get_response = self.client.get("/api/council/actions")

        self.assertEqual(get_response.status_code, 200)
        payload = get_response.json()
        self.assertEqual(payload["counts"]["adopted"], 1)
        self.assertEqual(payload["groups"]["prompt_diagnosis_refinement"][0]["title"], "Make audience explicit")

    def test_rule_promotion_route_returns_dry_run_proposals(self):
        report = {
            "mode": "dry_run",
            "thresholds": {"provisional_packets": 5},
            "proposals": [{
                "rule_key": "diagnosis::make_audience_explicit",
                "current_status": "candidate",
                "proposed_status": "candidate",
                "recommendation": "hold",
                "metrics": {"support_packets": 0},
            }],
        }

        with patch.object(server.db, "compute_rule_promotion_proposals", AsyncMock(return_value=report)):
            response = self.client.get("/api/rules/promotions")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "dry_run")
        self.assertEqual(payload["proposals"][0]["recommendation"], "hold")

    def test_queued_contrast_set_action_creates_reference_pack(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"
        saved_action = {
            "id": 12,
            "council_id": 4,
            "action_type": "contrast_set_candidate",
            "title": "Speech vs resignation note",
            "status": "queued",
            "lane": "creative",
            "prompt_family": "letters",
            "payload": {
                "focus": "repetition and public-force rhetoric",
                "why_now": "Teach situation-conditioned repetition.",
                "reference_pack_id": 44,
                "execution_status": "reference_pack_created",
            },
            "created_at": "2026-04-09 15:00:00",
            "updated_at": "2026-04-09 15:00:00",
        }

        with patch.object(server.db, "list_reference_packs", AsyncMock(return_value=[])), \
             patch.object(server.db, "create_reference_pack", AsyncMock(return_value=44)), \
             patch.object(server.db, "upsert_council_action", AsyncMock(return_value=saved_action)) as upsert_mock:
            response = self.client.post(
                "/api/council/actions",
                json={
                    "council_id": 4,
                    "action_type": "contrast_set_candidate",
                    "title": "Speech vs resignation note",
                    "status": "queued",
                    "lane": "creative",
                    "prompt_family": "letters",
                    "payload": {
                        "focus": "repetition and public-force rhetoric",
                        "why_now": "Teach situation-conditioned repetition.",
                    },
                },
                headers={"X-Admin-Token": "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        saved_payload = upsert_mock.await_args.args[0]["payload"]
        self.assertEqual(saved_payload["reference_pack_id"], 44)
        self.assertEqual(saved_payload["execution_status"], "reference_pack_created")


if __name__ == "__main__":
    unittest.main()
