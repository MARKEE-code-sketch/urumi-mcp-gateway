"""Checks of the approved M0 message schemas, not the real application."""
import json
from pathlib import Path
import unittest
import sys
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/m0"))
from schema_validation import validator

CATALOG = json.loads((ROOT / "contracts/mcp-tools.schema.json").read_text(encoding="utf-8"))
TOOLS = {tool["name"]: tool for tool in CATALOG["tools"]}
SAMPLES = json.loads((ROOT / "tests/fixtures/m0/examples.json").read_text(encoding="utf-8"))


class ContractChecks(unittest.TestCase):
    def test_all_six_definitions_are_valid_schemas(self):
        self.assertEqual(len(TOOLS), 6)
        for tool in TOOLS.values():
            with self.subTest(tool=tool["name"]):
                Draft202012Validator.check_schema(tool["inputSchema"])
                Draft202012Validator.check_schema(tool["outputSchema"])

    def test_all_success_examples_match_both_schemas(self):
        for sample in SAMPLES["success"]:
            with self.subTest(tool=sample["tool"], arguments=sample["arguments"]):
                tool = TOOLS[sample["tool"]]
                validator(tool["inputSchema"]).validate(sample["arguments"])
                result = sample["result"]
                validator(tool["outputSchema"]).validate(result["structuredContent"])
                self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
                self.assertFalse(result["isError"])

    def test_invalid_inputs_are_rejected(self):
        invalid = [
            ("create_product", {"name": "Mug"}),
            ("create_product", {"name": "   ", "regular_price": "1.00"}),
            ("lookup_sku", {"sku": "   "}),
            ("create_product", {"name": "Mug", "regular_price": "-1"}),
            ("create_product", {"name": "Mug", "regular_price": 299}),
            ("create_product", {"name": "Mug", "regular_price": "1.999"}),
            ("get_order", {"order_id": 0}),
            ("update_order_status", {"order_id": 501, "status": "invented"}),
            ("list_products", {"page": 0}),
            ("list_products", {"per_page": 51}),
            ("list_orders", {"created_from": "2026-10-14T00:00:00"}),
            ("lookup_sku", {"sku": "DEMO-001", "user_id": "untrusted"}),
            ("list_orders", {"created_from": "2026-99-14T00:00:00Z"}),
        ]
        for name, arguments in invalid:
            with self.subTest(tool=name, arguments=arguments):
                with self.assertRaises(ValidationError):
                    validator(TOOLS[name]["inputSchema"]).validate(arguments)

    def test_errors_do_not_claim_success_schema(self):
        for sample in SAMPLES["failure"]:
            with self.subTest(tool=sample["tool"]):
                self.assertTrue(sample["result"]["isError"])
                self.assertNotIn("structuredContent", sample["result"])
                self.assertIn("error", json.loads(sample["result"]["content"][0]["text"]))
