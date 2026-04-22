"""Regression tests for the public /api/artifact response contract."""

import asyncio
import json
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient

import agents
import database as db
import server
from scripts import bootstrap_demo


ADMIN_TOKEN = "secret-token"

EXPECTED_TOP_LEVEL_KEYS = {
    "artifact",
    "comparison_packet",
    "comparison_review",
    "comparison_siblings",
    "condition",
    "constraints",
    "created_at",
    "creativity_type",
    "epoch",
    "family",
    "generation_protocol",
    "holdout_scores",
    "hypothesis",
    "hypothesis_id",
    "id",
    "iteration",
    "lane",
    "packet_id",
    "packet_primary",
    "packet_role_id",
    "parse_failure",
    "primary_rule_id",
    "process_trace",
    "promotion_status",
    "prompt",
    "prompt_family",
    "role_packets",
    "source_context",
    "status",
    "track",
}

SYSTEM_PROMPT_SENTINELS = [
    agents.GENESIS_SYSTEM[:40],
    agents.THERON_SYSTEM[:40],
    agents.MUSE_SYSTEM[:40],
    agents.ATHENA_SYSTEM[:40],
    agents.APOLLO_SYSTEM[:40],
]


@asynccontextmanager
async def _noop_lifespan(app):
    yield


def _contains_key(value, target_key):
    if isinstance(value, dict):
        return target_key in value or any(_contains_key(child, target_key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, target_key) for child in value)
    return False


class ArtifactRedactionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "demo_lab.db")
        self.original_db_path = db.DB_PATH
        self.original_db_initialized = db._db_initialized
        self.original_initialized_db_path = db._initialized_db_path
        self.original_lifespan = server.app.router.lifespan_context
        self.original_admin_token = os.environ.get("LAB_ADMIN_TOKEN")

        db.DB_PATH = self.db_path
        db._db_initialized = False
        db._initialized_db_path = None
        fixture = json.loads(bootstrap_demo.DEFAULT_FIXTURE.read_text(encoding="utf-8"))
        asyncio.run(bootstrap_demo._seed(fixture))

        server.app.router.lifespan_context = _noop_lifespan
        os.environ["LAB_ADMIN_TOKEN"] = ADMIN_TOKEN
        self.client = TestClient(server.app)
        self.experiment_id = 1

    def tearDown(self):
        self.client.close()
        server.app.router.lifespan_context = self.original_lifespan
        if self.original_admin_token is None:
            os.environ.pop("LAB_ADMIN_TOKEN", None)
        else:
            os.environ["LAB_ADMIN_TOKEN"] = self.original_admin_token
        db.DB_PATH = self.original_db_path
        db._db_initialized = self.original_db_initialized
        db._initialized_db_path = self.original_initialized_db_path
        self.temp_dir.cleanup()

    def _get_artifact(self):
        return self.client.get(
            f"/api/artifact/{self.experiment_id}",
            headers={"X-Admin-Token": ADMIN_TOKEN},
        )

    def test_artifact_requires_admin_token(self):
        response = self.client.get(f"/api/artifact/{self.experiment_id}")

        self.assertEqual(response.status_code, 401)

    def test_artifact_response_shape_is_audited(self):
        response = self._get_artifact()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        unexpected_keys = set(payload) - EXPECTED_TOP_LEVEL_KEYS
        self.assertFalse(
            unexpected_keys,
            f"New /api/artifact keys need redaction review before being allowed: {unexpected_keys}",
        )

    def test_artifact_does_not_leak_system_prompts_or_council_payloads(self):
        response = self._get_artifact()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        body_text = json.dumps(payload, sort_keys=True)
        for sentinel in SYSTEM_PROMPT_SENTINELS:
            self.assertNotIn(sentinel, body_text)
        self.assertFalse(_contains_key(payload, "council_payload"))
        self.assertFalse(_contains_key(payload, "raw_council_payload"))

    def test_artifact_does_not_leak_error_traceback(self):
        response = self._get_artifact()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error_traceback", response.json())


if __name__ == "__main__":
    unittest.main()
