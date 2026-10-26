import json
from pathlib import Path
import unittest
from unittest.mock import patch

from services.sample_mcps.inventory import DEFINITION, load_inventory, lookup, valid


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = load_inventory(Path("services/sample_mcps/data/inventory.json"))

    def test_known_unknown_zero_trim_case_and_copy(self):
        for sku, found, quantity in ((" DEMO-001 ", True, 12), ("ZERO-001", True, 0), ("missing", False, None), ("demo-001", False, None)):
            result = lookup(self.inventory, {"sku": sku})
            self.assertFalse(result.isError)
            self.assertEqual(result.structuredContent, json.loads(result.content[0].text))
            self.assertTrue(valid(DEFINITION["outputSchema"], result.structuredContent))
            self.assertEqual(result.structuredContent["sku"], sku.strip())
            self.assertEqual(result.structuredContent["found"], found)
            if found:
                self.assertEqual(result.structuredContent["warehouses"][0]["quantity"], quantity)
        lookup(self.inventory, {"sku": "DEMO-001"}).structuredContent["warehouses"][0]["quantity"] = 99
        self.assertEqual(lookup(self.inventory, {"sku": "DEMO-001"}).structuredContent["warehouses"][0]["quantity"], 12)

    def test_invalid_arguments(self):
        for args in ({}, None, [], {"sku": True}, {"sku": 1}, {"sku": ""}, {"sku": " \t"}, {"sku": "x" * 101}, {"sku": "DEMO-001", "url": "http://invalid"}):
            result = lookup(self.inventory, args)
            self.assertTrue(result.isError, args)
            self.assertIsNone(result.structuredContent)
            self.assertEqual(json.loads(result.content[0].text)["error"]["code"], "INVALID_ARGUMENT")

    def test_bad_fixtures(self):
        good = {"sku": "A", "warehouses": [{"name": "B", "quantity": 0}]}
        cases = [None, {}, [good, good], [{"sku": "A", "warehouses": [], "extra": 1}], [{"sku": " ", "warehouses": []}]]
        for quantity in (-1, True, 1.0, "1"):
            cases.append([{"sku": "A", "warehouses": [{"name": "B", "quantity": quantity}]}])
        cases += [[{"sku": "A", "warehouses": [{"name": " ", "quantity": 0}]}], [good] * 101,
                  [{"sku": "A", "warehouses": good["warehouses"] * 21}]]
        path = Path("private-path.json")
        for value in cases:
            with patch.object(Path, "read_bytes", return_value=json.dumps(value).encode()):
                with self.assertRaisesRegex(ValueError, "^Sample inventory configuration is invalid.$"):
                    load_inventory(path)
        for value in ("bad-json", "x" * 65537):
            with patch.object(Path, "read_bytes", return_value=value.encode()):
                with self.assertRaises(ValueError):
                    load_inventory(path)
        with self.assertRaises(ValueError):
            load_inventory(Path(".tools/m4/does-not-exist.json"))
