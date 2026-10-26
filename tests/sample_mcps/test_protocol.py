from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import LocalServer
from services.sample_mcps.inventory import DEFINITION, create_app


@asynccontextmanager
async def connect(url, headers=None):
    async with httpx.AsyncClient(timeout=4, trust_env=False, headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, get_id):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                try:
                    yield session, initialized, get_id
                finally:
                    await read.aclose()
                    await write.aclose()


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(create_app())

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    async def test_real_discovery_calls_and_unknown_error(self):
        async with connect(self.server.url + "/mcp") as (session, initialized, get_id):
            tools = (await session.list_tools()).tools
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].model_dump(exclude_none=True), DEFINITION)
            self.assertIsNone(get_id())
            for args, found in (({"sku": " DEMO-001 "}, True), ({"sku": "unknown"}, False), ({"sku": "ZERO-001"}, True)):
                result = await session.call_tool("lookup_sku", args)
                self.assertFalse(result.isError)
                self.assertEqual(result.structuredContent["found"], found)
                self.assertEqual(json.loads(result.content[0].text), result.structuredContent)
            bad = await session.call_tool("lookup_sku", {"sku": True})
            self.assertTrue(bad.isError)
            self.assertIsNone(bad.structuredContent)
            with self.assertRaises(McpError):
                await session.call_tool("unknown", {})
            print("M4 real TCP negotiated protocol:", initialized.protocolVersion)

    async def test_http_boundary_and_health(self):
        async with httpx.AsyncClient(trust_env=False, timeout=3) as http:
            for headers in ({"Origin": "http://browser.invalid"}, {"Host": "unapproved.invalid"}):
                self.assertEqual((await http.post(self.server.url + "/mcp", json={}, headers=headers)).status_code, 403)
            self.assertEqual((await http.post(self.server.url + "/mcp", content=b"x" * 65537)).status_code, 413)
            async def chunks():
                yield b"x" * 32768
                yield b"x" * 32769
            self.assertEqual((await http.post(self.server.url + "/mcp", content=chunks())).status_code, 413)
            reply = await http.get(self.server.url + "/mcp", headers={"Accept": "text/event-stream"})
            self.assertEqual(reply.status_code, 405)
            self.assertEqual(reply.headers["Allow"], "POST")
            for path in ("/livez", "/readyz"):
                self.assertEqual((await http.get(self.server.url + path)).status_code, 200)

    async def test_bad_fixture_prevents_startup(self):
        guarded = create_app()
        with patch.object(Path, "read_bytes", return_value=b"malformed-fixture"):
            with self.assertRaisesRegex(ValueError, "^Sample inventory configuration is invalid.$"):
                async with guarded.app.router.lifespan_context(guarded.app):
                    self.fail("Invalid fixture reached usable lifespan.")
