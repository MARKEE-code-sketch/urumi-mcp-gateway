"""One read-only SAMPLE tool; no shop or outgoing network connection."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, validators
from mcp import McpError, types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

ROOT = Path(__file__).resolve().parents[2]
DEFINITION = next(item for item in json.loads((ROOT / "contracts/mcp-tools.schema.json").read_text(encoding="utf-8"))["tools"] if item["name"] == "lookup_sku")
StrictValidator = validators.extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda checker, value: type(value) is int))


def valid(schema, value):
    return not any(StrictValidator(schema).iter_errors(value))


def load_inventory(path):
    try:
        raw = Path(path).read_bytes()
        if len(raw) > 65536:
            raise ValueError()
        records = json.loads(raw)
        if not isinstance(records, list) or len(records) > 100:
            raise ValueError()
        inventory = {}
        for record in records:
            if not isinstance(record, dict) or set(record) != {"sku", "warehouses"}:
                raise ValueError()
            if not valid(DEFINITION["inputSchema"], {"sku": record["sku"]}):
                raise ValueError()
            sku = record["sku"].strip()
            warehouses = record["warehouses"]
            if sku in inventory or not isinstance(warehouses, list) or len(warehouses) > 20:
                raise ValueError()
            result = {"sku": sku, "found": True, "warehouses": warehouses}
            if not valid(DEFINITION["outputSchema"], result) or any(not item["name"].strip() for item in warehouses):
                raise ValueError()
            inventory[sku] = deepcopy(warehouses)
        return inventory
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("Sample inventory configuration is invalid.") from None


def lookup(inventory, arguments):
    if not valid(DEFINITION["inputSchema"], arguments):
        return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=json.dumps({"error": {"code": "INVALID_ARGUMENT", "message": "Provide only a nonblank sku of at most 100 characters."}}))])
    sku = arguments["sku"].strip()
    result = {"sku": sku, "found": sku in inventory, "warehouses": deepcopy(inventory.get(sku, []))}
    return types.CallToolResult(isError=False, structuredContent=result, content=[types.TextContent(type="text", text=json.dumps(result))])


class RequestGuard:
    def __init__(self, app, hosts):
        self.app, self.hosts = app, hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/mcp":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            host_ok = urlsplit("//" + headers.get(b"host", b"").decode("ascii")).hostname in self.hosts
        except (ValueError, UnicodeError):
            host_ok = False
        if b"origin" in headers or not host_ok:
            return await JSONResponse({"error": "Request origin or host is not permitted."}, status_code=403)(scope, receive, send)
        if scope["method"] != "POST":
            return await JSONResponse({"error": "This stateless endpoint accepts POST only."}, status_code=405, headers={"Allow": "POST"})(scope, receive, send)
        started = False

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            async with asyncio.timeout(10):
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

                await self.app(scope, replay, tracked_send)
        except TimeoutError:
            if not started:
                return await JSONResponse({"error": "Request deadline exceeded."}, status_code=408)(scope, receive, send)
            await send({"type": "http.response.body", "body": b"", "more_body": False})


def create_app(fixture=None, allowed_hosts=None):
    fixture = fixture or Path(__file__).parent / "data/inventory.json"
    inventory = {}
    ready = False
    server = Server("urumi-inventory", version="m4")

    @server.list_tools()
    async def list_tools():
        return [types.Tool(**DEFINITION)]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        return lookup(inventory, arguments)

    original = server.request_handlers[types.CallToolRequest]

    async def checked(request):
        if request.params.name != "lookup_sku":
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Unknown tool."))
        return await original(request)

    server.request_handlers[types.CallToolRequest] = checked
    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal inventory, ready
        inventory = load_inventory(fixture)
        async with manager.run():
            ready = True
            try:
                yield
            finally:
                ready = False

    class Endpoint:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    async def live(request):
        return JSONResponse({"status": "alive"})

    async def readiness(request):
        return JSONResponse({"status": "ready" if ready else "starting"}, status_code=200 if ready else 503)

    app = Starlette(routes=[Route("/mcp", Endpoint()), Route("/livez", live), Route("/readyz", readiness)], lifespan=lifespan)
    return RequestGuard(app, allowed_hosts or os.getenv("MCP_ALLOWED_HOSTS", "localhost,127.0.0.1").split(","))


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
    try:
        load_inventory(Path(__file__).parent / "data/inventory.json")
    except ValueError:
        logging.error("Sample inventory configuration is invalid.")
        raise SystemExit(1)
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, access_log=False)
