import json
import unittest
from pathlib import Path


class PromptCompilerSchemaTests(unittest.TestCase):
    def test_prompt_compiler_schema_has_expected_top_level_fields(self):
        schema_path = Path(__file__).resolve().parents[1] / "data" / "prompt_compiler_schema.json"
        payload = json.loads(schema_path.read_text())

        self.assertEqual(payload["schema_version"], "0.1")
        self.assertIn("source_request", payload["required"])
        self.assertIn("diagnosis", payload["required"])
        self.assertIn("risk_assessment", payload["required"])
        self.assertIn("policy_selection", payload["required"])
        self.assertIn("compiled_prompt", payload["required"])
        self.assertIn("traceability", payload["required"])

    def test_prompt_compiler_schema_diagnosis_contract_is_explicit(self):
        schema_path = Path(__file__).resolve().parents[1] / "data" / "prompt_compiler_schema.json"
        payload = json.loads(schema_path.read_text())

        diagnosis = payload["fields"]["diagnosis"]
        self.assertIn("composition_mode", diagnosis["required"])
        self.assertEqual(
            diagnosis["properties"]["composition_mode"]["values"],
            ["creative_open", "strict_framework", "hybrid"],
        )
        self.assertIn("intended_audience", diagnosis["required"])
        self.assertIn("piece_goal", diagnosis["required"])

    def test_prompt_rule_evidence_schema_requires_scope_and_slices(self):
        schema_path = Path(__file__).resolve().parents[1] / "data" / "prompt_rule_evidence_schema.json"
        payload = json.loads(schema_path.read_text())

        self.assertEqual(payload["schema_version"], "0.1")
        self.assertIn("scope_claim", payload["required"])
        self.assertIn("evidence_slices", payload["required"])
        self.assertEqual(
            payload["fields"]["scope_claim"]["values"],
            ["universal", "family_specific", "model_specific"],
        )
        self.assertIn(
            "cross_model_replication",
            payload["fields"]["evidence_slices"]["items"]["properties"]["experiment_type"]["values"],
        )
        self.assertIn(
            "panel_version",
            payload["fields"]["evidence_slices"]["items"]["properties"],
        )
        self.assertIn(
            "human_signal_attribution_method",
            payload["fields"]["evidence_slices"]["items"]["properties"],
        )


if __name__ == "__main__":
    unittest.main()
