"""Controlled fixtures only; artificial credentials are never logged."""
import asyncio
from contextlib import asynccontextmanager
import hmac
import socket
import threading
import time

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

BEARER_SENTINEL = "m4-artificial-bearer-sentinel"
HEADER_SENTINEL = "m4-artificial-header-sentinel"


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
            raise RuntimeError("Local fixture did not start.")

    def close(self):
        self.server.should_exit = True
        self.thread.join(4)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(2)
        if self.thread.is_alive():
            raise RuntimeError("Local fixture did not stop.")


def fixture_app(mode="bearer"):
    server = Server("m4-controlled-fixture")
    @server.list_tools()
    async def tools():
        return [types.Tool(name="service_info", description="Controlled SAMPLE fixture.", inputSchema={"type": "object", "properties": {}, "additionalProperties": False})]

    @server.call_tool()
    async def call(name, arguments):
        return [types.TextContent(type="text", text='{"fixture_only":true}')]

    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)
    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    class Endpoint:
        async def __call__(self, scope, receive, send):
            headers = dict(scope["headers"])
            if mode in ("bearer", "header"):
                actual = headers.get(b"authorization" if mode == "bearer" else b"x-test-api-key", b"")
                expected = ("Bearer " + BEARER_SENTINEL if mode == "bearer" else HEADER_SENTINEL).encode()
                if not hmac.compare_digest(actual, expected):
                    return await JSONResponse({"error": "Fixture authentication failed."}, status_code=401)(scope, receive, send)
            if mode == "slow":
                await asyncio.sleep(5)
            if mode in ("invalid", "unavailable"):
                return await JSONResponse({"not_mcp": True}, status_code=503 if mode == "unavailable" else 200)(scope, receive, send)
            await manager.handle_request(scope, receive, send)

    return Starlette(routes=[Route("/mcp", Endpoint())], lifespan=lifespan)
