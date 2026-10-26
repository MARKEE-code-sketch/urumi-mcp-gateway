import asyncio
import json
from pathlib import Path
import sys
import socket
import time
from types import SimpleNamespace
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import BEARER_SENTINEL, HEADER_SENTINEL, LocalServer, fixture_app
from test_protocol import connect
from scripts.m4.probe import LimitedTransport, ProbeLimit, discover, probe
from services.sample_mcps.inventory import create_app


class CompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_auth_and_collision_fixtures(self):
        evidence = []
        for mode, headers in (("bearer", {"Authorization": "Bearer " + BEARER_SENTINEL}), ("header", {"X-Test-Api-Key": HEADER_SENTINEL})):
            server = LocalServer(fixture_app(mode))
            try:
                async with httpx.AsyncClient(trust_env=False) as http:
                    for wrong in ({}, {key: "wrong" for key in headers}):
                        self.assertEqual((await http.post(server.url + "/mcp", json={}, headers=wrong)).status_code, 401)
                        with self.assertRaises(Exception):
                            async with connect(server.url + "/mcp", wrong):
                                self.fail("Missing/wrong fixture credential initialized MCP.")
                async with connect(server.url + "/mcp", headers) as (session, _, __):
                    tools = (await session.list_tools()).tools
                    self.assertEqual([tool.name for tool in tools], ["service_info"])
                    result = await session.call_tool("service_info", {})
                    self.assertFalse(result.isError)
                    evidence.append({"mode": mode, "missing": 401, "wrong": 401, "valid": "PASS", "tool": tools[0].name})
            finally:
                server.close()
        encoded = json.dumps(evidence)
        self.assertNotIn(BEARER_SENTINEL, encoded)
        self.assertNotIn(HEADER_SENTINEL, encoded)
        print("M4 controlled authentication/collision:", encoded)

    async def test_bounded_failures_then_healthy_inventory(self):
        failures = []
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            unreachable_url = f"http://127.0.0.1:{unused.getsockname()[1]}/mcp"
        unreachable = await probe(unreachable_url, hosted=False, timeout=3)
        self.assertEqual(unreachable["status"], "FAIL")
        self.assertIn("ConnectError", unreachable["error_categories"])
        failures.append({"mode": "unreachable", "elapsed_seconds": unreachable["elapsed_seconds"], "error_categories": unreachable["error_categories"]})
        for mode in ("unavailable", "invalid", "slow"):
            server = LocalServer(fixture_app(mode))
            try:
                started = time.monotonic()
                result = await probe(server.url + "/mcp", hosted=False, timeout=.7)
                self.assertEqual(result["status"], "FAIL")
                self.assertFalse(result["real_hosted"])
                self.assertLess(time.monotonic() - started, 2)
                failures.append({"mode": mode, "elapsed_seconds": result["elapsed_seconds"], "error_categories": result["error_categories"]})
            finally:
                server.close()
        server = LocalServer(create_app())
        try:
            result = await probe(server.url + "/mcp", hosted=False)
            self.assertEqual(result["status"], "PASS", result)
        finally:
            server.close()
        print("M4 controlled failures and healthy recovery:", json.dumps(failures))

    async def test_response_and_aggregate_limits(self):
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"12345"
        for response_limit, aggregate_limit in ((4, 100), (100, 4)):
            bounded = LimitedTransport(httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream())), response_limit, aggregate_limit)
            async with httpx.AsyncClient(transport=bounded) as http:
                with self.assertRaises(ProbeLimit):
                    await http.get("https://fixture.invalid")
        bounded = LimitedTransport(httpx.MockTransport(lambda request: httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=Stream())))
        async with httpx.AsyncClient(transport=bounded) as http:
            with self.assertRaises(ProbeLimit):
                await http.get("https://fixture.invalid")

    async def test_discovery_repeated_cursor_and_limits(self):
        class Pages:
            def __init__(self, mode):
                self.mode, self.calls = mode, 0
            async def list_tools(self, cursor=None):
                self.calls += 1
                return SimpleNamespace(tools=[None] * (201 if self.mode == "tools" else 0), nextCursor="same" if self.mode == "repeat" else str(self.calls))
        for mode in ("repeat", "tools", "pages"):
            with self.assertRaises(ProbeLimit):
                await discover(Pages(mode))
