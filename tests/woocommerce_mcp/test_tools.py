import asyncio
from copy import deepcopy
import json
import sys
from pathlib import Path
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_shop import FakeShop, product_sample, order_sample
from test_oauth import FAKE_KEY, FAKE_SECRET
from services.woocommerce_mcp.schemas import DEFINITIONS, valid
from services.woocommerce_mcp.tools import Tools
from services.woocommerce_mcp.woocommerce_client import Settings, WooCommerceClient


class ToolChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeShop()
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(self.fake.app()), trust_env=False)
        self.settings = Settings(self.fake.canonical, "http://internal-only:8080", FAKE_KEY, FAKE_SECRET)
        self.tools = Tools(WooCommerceClient(self.settings, self.http))

    async def asyncTearDown(self):
        await self.http.aclose()

    async def call(self, name, args, code=None):
        result = await self.tools.call(name, args)
        body = json.loads(result.content[0].text)
        if code:
            self.assertTrue(result.isError)
            self.assertIsNone(result.structuredContent)
            self.assertEqual(body["error"]["code"], code)
        else:
            self.assertFalse(result.isError, body)
            self.assertEqual(result.structuredContent, body)
            self.assertTrue(valid(DEFINITIONS[name]["outputSchema"], body))
        self.assertNotIn(FAKE_SECRET, json.dumps(body))
        self.assertNotIn("SENTINEL-CONTACT", json.dumps(body))
        return body

    async def test_five_successes_and_rest_mapping(self):
        await self.call("list_products", {})
        created = await self.call("create_product", {"name": " Blue Mug ", "regular_price": "12.5", "sku": " NEW "})
        self.assertEqual(created["product"]["regular_price"], "12.50")
        await self.call("list_orders", {})
        await self.call("get_order", {"order_id": 1})
        updated = await self.call("update_order_status", {"order_id": 1, "status": "completed"})
        self.assertEqual(updated["order"]["status"], "completed")
        self.assertEqual(self.fake.observations[1]["body"], {"name": "Blue Mug", "regular_price": "12.5", "sku": "NEW", "type": "simple", "status": "publish"})
        self.assertEqual(self.fake.observations[-1]["body"], {"status": "completed"})
        self.assertTrue(all(item["signed"] and item["host"] == "fake-shop.urumi.test" for item in self.fake.observations))

    async def test_invalid_inputs_zero_dispatch(self):
        cases = [("get_order", {"order_id": value}) for value in (True, 1.0, "1", 0, -1)]
        cases += [("list_products", {key: value}) for key in ("page", "per_page") for value in (True, 1.0, 0)]
        cases += [("create_product", {"name": "mug", "regular_price": value}) for value in (1.0, "-1", "1e2", "1.123", " ")]
        cases += [("list_products", {"url": "http://bad"}), ("list_products", {"sku": " "}),
                  ("create_product", {"name": " ", "regular_price": "1"}),
                  ("create_product", {"name": "x" * 201, "regular_price": "1"}),
                  ("list_products", {"search": "x" * 201}),
                  ("list_products", {"sku": "x" * 101}),
                  ("list_products", {"per_page": 51}),
                  ("create_product", {"regular_price": "1"}),
                  ("create_product", {"name": "mug"}),
                  ("update_order_status", {"order_id": 1, "status": "trash"}),
                  ("list_orders", {"created_from": "2026-02-30T00:00:00Z"}),
                  ("list_orders", {"created_from": "2026-10-14T00:00:00"}),
                  ("list_orders", {"created_from": "2026-10-14T00:00:00+05:99"}),
                  ("list_orders", {"created_from": "2026-10-14T00:00:00+24:00"}),
                  ("list_orders", {"created_from": "2026-10-15T00:00:00Z", "created_to": "2026-10-14T00:00:00Z"}),
                  ("list_orders", {"created_from": "0001-01-01T00:00:00Z"})]
        for name, args in cases:
            with self.subTest(name=name, args=args):
                await self.call(name, args, "INVALID_ARGUMENT")
        self.assertEqual(self.fake.observations, [])

    async def test_three_source_pages_logical_pages_and_empty(self):
        self.fake.products = [product_sample(n) for n in range(1, 241)]
        all_ids = []
        for page in range(1, 6):
            body = await self.call("list_products", {"page": page, "per_page": 50})
            all_ids += [p["id"] for p in body["items"]]
            self.assertEqual(body["has_more"], page < 5)
        self.assertEqual(all_ids, list(range(1, 241)))
        self.assertEqual((await self.call("list_products", {"page": 6, "per_page": 50}))["items"], [])
        self.assertEqual((await self.call("list_products", {"sku": "SKU-240"}))["items"][0]["id"], 240)
        self.assertEqual((await self.call("list_products", {"sku": "SKU-1,SKU-2"}))["items"], [])
        searched = await self.call("list_products", {"search": "Mug 24"})
        self.assertEqual([item["id"] for item in searched["items"]], [24, 240])
        self.assertEqual(self.fake.observations[-1]["query"]["search"], "Mug 24")

    async def test_exactly_full_source_page_and_work_cap(self):
        self.fake.products = [product_sample(n) for n in range(1, 101)]
        body = await self.call("list_products", {"page": 2, "per_page": 50})
        self.assertFalse(body["has_more"])
        self.assertEqual(len(self.fake.observations), 1)
        self.fake.products.append(product_sample(101))
        self.tools.max_pages = 1
        await self.call("list_products", {"page": 3, "per_page": 50}, "UPSTREAM_LIMIT_EXCEEDED")

    async def test_inclusive_dates_fractional_bounds_and_pagination(self):
        self.fake.orders = [order_sample(1, "2026-10-14T18:29:59"), order_sample(2, "2026-10-14T18:30:00"),
                            order_sample(3, "2026-10-14T18:30:01"), order_sample(4, "2026-10-14T18:30:02")]
        args = {"created_from": "2026-10-15T00:00:00+05:30", "created_to": "2026-10-14T18:30:01Z", "per_page": 1}
        first = await self.call("list_orders", args)
        second = await self.call("list_orders", {**args, "page": 2})
        self.assertEqual([first["items"][0]["id"], second["items"][0]["id"]], [2, 3])
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        fractional = await self.call("list_orders", {**args, "created_from": "2026-10-14T18:30:00.5Z"})
        self.assertEqual(fractional["items"][0]["id"], 3)
        self.assertEqual(self.fake.observations[0]["query"]["after"], "2026-10-14T18:29:59Z")
        self.assertEqual(self.fake.observations[0]["query"]["dates_are_gmt"], "true")

    async def test_safe_failures_then_recovery(self):
        for mode, code in (("auth", "UPSTREAM_AUTH_FAILED"), ("forbidden", "UPSTREAM_AUTH_FAILED"),
                           ("invalid_json", "UPSTREAM_PROTOCOL_ERROR"), ("invalid_fields", "UPSTREAM_PROTOCOL_ERROR"),
                           ("missing_pagination", "UPSTREAM_PROTOCOL_ERROR"), ("redirect", "UPSTREAM_PROTOCOL_ERROR"),
                           ("unavailable", "UPSTREAM_UNAVAILABLE"), ("oversize", "UPSTREAM_LIMIT_EXCEEDED")):
            self.fake.mode = mode
            await self.call("list_products", {}, code)
            self.fake.mode = "healthy"
            await self.call("list_products", {})
        await self.call("get_order", {"order_id": 999}, "ORDER_NOT_FOUND")
        before = len(self.fake.observations)
        await self.call("create_product", {"name": "mug", "regular_price": "1", "sku": "SKU-1"}, "PRODUCT_SKU_CONFLICT")
        self.assertEqual(len(self.fake.observations), before + 1)

    async def test_source_integer_type_redaction_and_null_price(self):
        for field in ("id",):
            for value in (True, 1.0):
                self.fake.products[0][field] = value
                await self.call("list_products", {}, "UPSTREAM_PROTOCOL_ERROR")
        self.fake.products = [product_sample()]
        self.fake.products[0].update(price="", regular_price=None)
        self.assertIsNone((await self.call("list_products", {}))["items"][0]["price"])
        for field in ("quantity", "product_id"):
            for value in (True, 1.0):
                self.fake.orders = [order_sample()]
                self.fake.orders[0]["line_items"][0][field] = value
                await self.call("get_order", {"order_id": 1}, "UPSTREAM_PROTOCOL_ERROR")

    async def test_deadline_write_one_attempt_and_recovery(self):
        self.fake.mode = "slow"
        self.tools.deadline = 0.05
        before = len(self.fake.observations)
        result = await self.call("create_product", {"name": "uncertain", "regular_price": "1"}, "UPSTREAM_TIMEOUT")
        self.assertIn("may have completed", result["error"]["message"])
        self.assertEqual(len(self.fake.observations), before + 1)
        await self.call("list_products", {}, "UPSTREAM_TIMEOUT")
        self.fake.mode = "healthy"
        self.tools.deadline = 8
        await self.call("list_products", {})

    async def test_connection_error_and_logs_safe(self):
        async def broken(request):
            raise httpx.ConnectError("SENTINEL-CONTACT " + FAKE_SECRET)
        async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as http:
            tools = Tools(WooCommerceClient(self.settings, http))
            with self.assertLogs("woocommerce_mcp", level="INFO") as captured:
                result = await tools.call("list_products", {})
            self.assertEqual(json.loads(result.content[0].text)["error"]["code"], "UPSTREAM_UNAVAILABLE")
            self.assertNotIn(FAKE_SECRET, str(captured.output))
            self.assertNotIn("SENTINEL-CONTACT", str(captured.output))

    async def test_credential_echo_in_allowed_field_redacted(self):
        self.fake.products[0]["name"] = "product " + FAKE_SECRET + " " + FAKE_KEY
        result = await self.call("list_products", {})
        self.assertNotIn(FAKE_KEY, json.dumps(result))
        self.assertIn("[REDACTED]", result["items"][0]["name"])

    async def test_aggregate_source_byte_cap(self):
        self.fake.products = [{**product_sample(n), "padding": "x" * 15000} for n in range(1, 702)]
        await self.call("list_products", {"page": 14, "per_page": 50}, "UPSTREAM_LIMIT_EXCEEDED")
        self.assertEqual(len(self.fake.observations), 6)  # Six ~1.5 MiB pages exceed total8MiB before page7.

    async def test_normalized_result_byte_cap(self):
        line = {"product_id": 1, "name": "x" * 200, "sku": "SKU-1", "quantity": 1, "total": "1"}
        self.fake.orders[0]["line_items"] = [dict(line) for _ in range(3000)]
        await self.call("get_order", {"order_id": 1}, "UPSTREAM_LIMIT_EXCEEDED")
        self.assertEqual(len(self.fake.observations), 1)
