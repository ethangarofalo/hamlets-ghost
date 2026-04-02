import json
import os
import unittest

from fastapi.testclient import TestClient

os.environ.setdefault("THERON_GATEWAY_MODE", "mock")

from scripts import theron_gateway


class TheronGatewayTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(theron_gateway.app)

    def tearDown(self):
        self.client.close()

    def test_extract_json_object_reads_embedded_json(self):
        payload = theron_gateway._extract_json_object(
            "Sure, here it is:\n\n{\"artifact\": \"hello\", \"process_trace\": {\"drafts_considered\": 1}}"
        )
        self.assertEqual(payload["artifact"], "hello")

    def test_coerce_gateway_payload_requires_non_empty_artifact(self):
        with self.assertRaises(ValueError):
            theron_gateway._coerce_gateway_payload({"artifact": "   "})

    def test_health_reports_mock_mode(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "mock")

    def test_chat_completions_returns_openai_compatible_mock_response(self):
        response = self.client.post(
            "/v1/chat/completions",
            json={
                "model": "theron/latest",
                "messages": [
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": "Write a prayer from the perspective of a dying programming language."},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        self.assertIn("artifact", parsed)
        self.assertTrue(parsed["artifact"].strip())
        self.assertEqual(parsed["process_trace"]["transport"], "mock")

    def test_chat_completions_requires_user_message(self):
        response = self.client.post(
            "/v1/chat/completions",
            json={
                "model": "theron/latest",
                "messages": [
                    {"role": "system", "content": "Return JSON only."},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
