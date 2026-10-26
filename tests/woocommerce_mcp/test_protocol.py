"""Real TCP/Streamable HTTP, not only direct Python function calls."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_shop import FakeShop
from test_oauth import FAKE_KEY, FAKE_SECRET
from services.woocommerce_mcp.schemas import DEFINITIONS, NAMES
from services.woocommerce_mcp.server import create_app
from services.woocommerce_mcp.woocommerce_client import Settings


class LocalServer:
    def __init__(self, app):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, timeout_graceful_shutdown=1))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        if not self.server.started:
            self.close()
            raise RuntimeError("Local fixture did not start")

    def close(self):
        self.server.should_exit = True
        self.thread.join(4)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(2)
        if self.thread.is_alive():
            raise RuntimeError("Local fixture did not stop")


@asynccontextmanager
async def connect(url):
    async with httpx.AsyncClient(timeout=12, trust_env=False) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, get_id):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                try:
                    yield session, initialized, get_id
                finally:
                    await read.aclose()
                    await write.aclose()


class ProtocolChecks(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeShop()
        cls.rest = LocalServer(cls.fake.app())
        cls.settings = Settings(cls.fake.canonical, cls.rest.url, FAKE_KEY, FAKE_SECRET)
        cls.mcp = LocalServer(create_app(cls.settings))

    @classmethod
    def tearDownClass(cls):
        cls.mcp.close()
        cls.rest.close()

    async def test_discovery_exact_schemas_and_all_five_calls(self):
        async with connect(self.mcp.url + "/mcp") as (session, initialized, get_id):
            self.assertTrue(initialized.protocolVersion)
            self.assertIsNone(get_id())
            reply = await session.call_tool("get_order", {"order_id": 1})
            self.assertFalse(reply.isError)
            listed = (await session.list_tools()).tools
            self.assertEqual([item.name for item in listed], list(NAMES))
            for item in listed:
                self.assertEqual(item.inputSchema, DEFINITIONS[item.name]["inputSchema"])
                self.assertEqual(item.outputSchema, DEFINITIONS[item.name]["outputSchema"])
                self.assertEqual(item.annotations.model_dump(exclude_none=True), DEFINITIONS[item.name]["annotations"])
            cases = [("list_products", {}), ("create_product", {"name": "Network Mug", "regular_price": "11.00"}),
                     ("list_orders", {}), ("get_order", {"order_id": 1}),
                     ("update_order_status", {"order_id": 1, "status": "completed"})]
            for name, args in cases:
                result = await session.call_tool(name, args)
                self.assertFalse(result.isError, result)
                self.assertEqual(json.loads(result.content[0].text), result.structuredContent)
            print("M3 negotiated protocol:", initialized.protocolVersion)

    async def test_invalid_args_unknown_tool_and_recovery(self):
        before = len(self.fake.observations)
        async with connect(self.mcp.url + "/mcp") as (session, _, __):
            bad = await session.call_tool("get_order", {"order_id": True})
            self.assertTrue(bad.isError)
            self.assertEqual(json.loads(bad.content[0].text)["error"]["code"], "INVALID_ARGUMENT")
            self.assertEqual(len(self.fake.observations), before)
            with self.assertRaises(McpError):
                await session.call_tool("unknown_shop_tool", {})
            good = await session.call_tool("get_order", {"order_id": 1})
            self.assertFalse(good.isError)

    async def test_http_guards_and_health_during_shop_outage(self):
        async with httpx.AsyncClient(trust_env=False) as http:
            for headers in ({"Origin": "http://browser.invalid"}, {"Host": "evil.invalid"}):
                response = await http.post(self.mcp.url + "/mcp", json={}, headers=headers)
                self.assertEqual(response.status_code, 403)
            response = await http.post(self.mcp.url + "/mcp", content=b"x" * 65537)
            self.assertEqual(response.status_code, 413)
            async def chunks():
                yield b"x" * 32768
                yield b"y" * 32769
            response = await http.post(self.mcp.url + "/mcp", content=chunks())
            self.assertEqual(response.status_code, 413)
            self.fake.mode = "unavailable"
            try:
                async with connect(self.mcp.url + "/mcp") as (session, _, __):
                    failed = await session.call_tool("list_products", {})
                    self.assertTrue(failed.isError)
                for path in ("/livez", "/readyz"):
                    self.assertEqual((await http.get(self.mcp.url + path)).status_code, 200)
            finally:
                self.fake.mode = "healthy"

    async def test_real_read_timeout_uncertain_write_one_dispatch(self):
        self.fake.mode = "slow"
        before = len(self.fake.observations)
        try:
            async with connect(self.mcp.url + "/mcp") as (session, _, __):
                started = time.monotonic()
                result = await session.call_tool("create_product", {"name": "Real timeout", "regular_price": "1"})
                self.assertTrue(result.isError)
                body = json.loads(result.content[0].text)
                self.assertEqual(body["error"]["code"], "UPSTREAM_TIMEOUT")
                self.assertIn("may have completed", body["error"]["message"])
                self.assertLess(time.monotonic() - started, 8)
                self.assertEqual(len(self.fake.observations), before + 1)
        finally:
            self.fake.mode = "healthy"
