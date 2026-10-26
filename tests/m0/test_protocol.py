"""Real SDK client/server exchanges over localhost HTTP; fixture data only."""
import asyncio
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/m0"))
from fixture_server import create_app, FIXTURE_KEY
from schema_validation import validator


class LocalFixture:
    def __init__(self, mode="bearer", stateless=True):
        self.mode, self.stateless = mode, stateless

    def __enter__(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.url = f"http://127.0.0.1:{sock.getsockname()[1]}/mcp"
        config = uvicorn.Config(create_app(self.mode, self.stateless), log_level="critical", access_log=False, timeout_graceful_shutdown=1)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not self.server.started:
            self.server.should_exit = True
            self.thread.join(2)
            sock.close()
            raise RuntimeError("Fixture server did not start.")
        return self

    def __exit__(self, *unused):
        self.server.should_exit = True
        self.thread.join(3)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(2)
        if self.thread.is_alive():
            raise RuntimeError("Fixture server did not stop.")


@asynccontextmanager
async def connect(url, headers):
    async with httpx.AsyncClient(headers=headers, timeout=3, trust_env=False) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, session_id):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                try:
                    yield session, initialized, session_id
                finally:
                    await read.aclose()
                    await write.aclose()


async def discover(session):
    tools, cursor = [], None
    for _ in range(10):
        page = await session.list_tools(cursor=cursor)
        tools.extend(page.tools)
        cursor = page.nextCursor
        if not cursor:
            return tools
    raise AssertionError("Fixture discovery did not terminate.")


class ProtocolChecks(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.bearer = LocalFixture().__enter__()
        cls.header = LocalFixture("header").__enter__()
        cls.open = LocalFixture("none").__enter__()

    @classmethod
    def tearDownClass(cls):
        for fixture in (cls.open, cls.header, cls.bearer):
            fixture.__exit__(None, None, None)

    async def test_missing_and_wrong_authentication_rejected(self):
        async with httpx.AsyncClient(timeout=2, trust_env=False) as http:
            for url, headers in [
                (self.bearer.url, {}),
                (self.bearer.url, {"Authorization": "Bearer wrong-fixture-key"}),
                (self.header.url, {}),
                (self.header.url, {"X-API-Key": "wrong-fixture-key"}),
                (self.header.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}),
            ]:
                with self.subTest(url=url, headers=list(headers)):
                    response = await http.post(url, headers=headers, json={})
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn(FIXTURE_KEY, response.text)

    async def test_initialize_and_paginated_discovery(self):
        async with connect(self.bearer.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, initialized, session_id):
            tools = await discover(session)
            self.assertEqual(len(tools), 9)
            self.assertEqual(len({t.name for t in tools}), 9)
            self.assertTrue(initialized.protocolVersion)
            self.assertIsNone(session_id())
            self.__class__.negotiated_protocol = initialized.protocolVersion

    async def test_custom_header_and_no_auth_clients(self):
        for url, headers in [(self.header.url, {"X-API-Key": FIXTURE_KEY}), (self.open.url, {})]:
            async with connect(url, headers) as (session, _, __):
                await discover(session)
                reply = await session.call_tool("lookup_sku", {"sku": "DEMO-001"})
                self.assertFalse(reply.isError)
                self.assertEqual(reply.structuredContent["warehouses"][0]["quantity"], 12)

    async def test_call_before_discovery(self):
        async with connect(self.bearer.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, _, __):
            reply = await session.call_tool("lookup_sku", {"sku": "DEMO-001"})
            self.assertFalse(reply.isError)
            self.assertEqual(reply.structuredContent["sku"], "DEMO-001")

    async def test_six_sample_tools_return_valid_output(self):
        samples = json.loads((ROOT / "tests/fixtures/m0/examples.json").read_text(encoding="utf-8"))["success"]
        catalog = json.loads((ROOT / "contracts/mcp-tools.schema.json").read_text(encoding="utf-8"))["tools"]
        schemas = {t["name"]: t["outputSchema"] for t in catalog}
        async with connect(self.bearer.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, _, __):
            await discover(session)
            for sample in samples:
                with self.subTest(tool=sample["tool"], arguments=sample["arguments"]):
                    reply = await session.call_tool(sample["tool"], sample["arguments"])
                    self.assertFalse(reply.isError)
                    validator(schemas[sample["tool"]]).validate(reply.structuredContent)
                    self.assertEqual(json.loads(reply.content[0].text), reply.structuredContent)

    async def test_safe_execution_errors_and_invalid_inputs(self):
        cases = [
            ("get_order", {"order_id": 999}, "ORDER_NOT_FOUND"),
            ("create_product", {"name": "Mug", "regular_price": "-1"}, "INVALID_ARGUMENT"),
            ("update_order_status", {"order_id": 501, "status": "invented"}, "INVALID_ARGUMENT"),
            ("list_orders", {"created_from": "2026-10-14T12:00:00Z", "created_to": "2026-10-14T00:00:00Z"}, "INVALID_ARGUMENT"),
            ("list_orders", {"created_from": "2026-10-14T00:00:00"}, "INVALID_ARGUMENT"),
            ("list_orders", {"created_from": "2026-99-14T00:00:00Z"}, "INVALID_ARGUMENT"),
            ("always_fail", {}, "FIXTURE_FAILURE"),
        ]
        async with connect(self.bearer.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, _, __):
            await discover(session)
            for name, arguments, code in cases:
                with self.subTest(tool=name, code=code):
                    reply = await session.call_tool(name, arguments)
                    self.assertTrue(reply.isError)
                    self.assertIsNone(reply.structuredContent)
                    self.assertEqual(json.loads(reply.content[0].text)["error"]["code"], code)

    async def test_unknown_tool_and_invalid_cursor_are_protocol_errors(self):
        async with connect(self.bearer.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, _, __):
            with self.assertRaises(McpError) as error:
                await session.call_tool("unknown_tool", {})
            self.assertEqual(error.exception.error.code, -32602)
            with self.assertRaises(McpError):
                await session.list_tools(cursor="invalid")

    async def test_slow_fixture_can_be_cancelled_and_other_endpoint_works(self):
        async with connect(self.bearer.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, _, __):
            await discover(session)
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(session.call_tool("slow_reply", {"delay_seconds": 1}), timeout=0.1)
        async with connect(self.open.url, {}) as (healthy, _, __):
            await discover(healthy)
            reply = await healthy.call_tool("service_info", {})
            self.assertFalse(reply.isError)

    async def test_stateless_reconnect(self):
        for _ in range(2):
            async with connect(self.bearer.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, _, session_id):
                await discover(session)
                self.assertIsNone(session_id())
                self.assertFalse((await session.call_tool("service_info", {})).isError)

    async def test_stateful_session_is_created_and_terminated(self):
        with LocalFixture(stateless=False) as fixture:
            async with connect(fixture.url, {"Authorization": f"Bearer {FIXTURE_KEY}"}) as (session, _, session_id):
                await discover(session)
                token = session_id()
                self.assertTrue(token)
                self.assertFalse((await session.call_tool("service_info", {})).isError)
            async with httpx.AsyncClient(timeout=2, trust_env=False) as http:
                response = await http.post(fixture.url, headers={"Authorization": f"Bearer {FIXTURE_KEY}", "Mcp-Session-Id": token, "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}, json={"jsonrpc":"2.0","id":99,"method":"tools/list"})
                self.assertEqual(response.status_code, 404)
