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

    def test_artifact_response_redacts_internal_traceback(self):
        with patch.object(server.db, "get_experiment_by_id", AsyncMock(return_value={
            "id": 123,
            "status": "error",
            "prompt": "demo",
            "error_traceback": "Traceback (most recent call last): secret details",
        })), patch.object(server.db, "get_holdout_scores", AsyncMock(return_value=[])):
            response = self.client.get("/api/artifact/123")

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


if __name__ == "__main__":
    unittest.main()
