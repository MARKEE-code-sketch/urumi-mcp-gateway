"""Streamable HTTP entry point and local health probes."""
from contextlib import asynccontextmanager
import logging
from urllib.parse import urlsplit

import httpx
from mcp import McpError, types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from .schemas import DEFINITIONS, NAMES
from .tools import Tools
from .woocommerce_client import Settings, WooCommerceClient


class RequestGuard:
    def __init__(self, app, hosts):
        self.app, self.hosts = app, hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/mcp":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode("ascii", errors="ignore")
        try:
            permitted_host = urlsplit("//" + host).hostname in self.hosts
        except ValueError:
            permitted_host = False
        if b"origin" in headers or not permitted_host:
            return await JSONResponse({"error": "Request origin or host is not permitted."}, status_code=403)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 65536:
                return await JSONResponse({"error": "Request is too large."}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(settings=None, transport=None):
    settings = settings or Settings.from_env()
    server = Server("urumi-woocommerce", version="m3")
    definitions = [types.Tool(**DEFINITIONS[name]) for name in NAMES]
    operations = None
    ready = False

    @server.list_tools()
    async def list_tools():
        return definitions

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        return await operations.call(name, arguments)

    original_call = server.request_handlers[types.CallToolRequest]

    async def checked_call(request):
        if request.params.name not in DEFINITIONS:
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Unknown tool."))
        return await original_call(request)

    server.request_handlers[types.CallToolRequest] = checked_call
    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal operations, ready
        async with httpx.AsyncClient(transport=transport, trust_env=False) as http:
            operations = Tools(WooCommerceClient(settings, http))
            async with manager.run():
                ready = True
                try:
                    yield
                finally:
                    ready = False

    class MCPEndpoint:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    async def live(request):
        return JSONResponse({"status": "alive"})

    async def readiness(request):
        return JSONResponse({"status": "ready" if ready else "starting"}, status_code=200 if ready else 503)

    app = Starlette(routes=[Route("/mcp", MCPEndpoint()), Route("/livez", live), Route("/readyz", readiness)], lifespan=lifespan)
    return RequestGuard(app, settings.allowed_hosts)


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, access_log=False)
