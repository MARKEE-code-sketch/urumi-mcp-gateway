"""Disposable M0 Streamable HTTP fixture; no real shop or gateway actions."""

import argparse
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import secrets

from schema_validation import validator
from mcp import McpError, types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_KEY = "m0-fixture-only-key"  # Deliberately public, never a real credential.


def result(data, error=False):
    fields = {"content": [types.TextContent(type="text", text=json.dumps(data))], "isError": error}
    if not error:
        fields["structuredContent"] = data
    return types.CallToolResult(**fields)


def failure(code, message):
    return result({"error": {"code": code, "message": message}}, error=True)


class FixtureAuth:
    def __init__(self, app, mode):
        self.app, self.mode = app, mode

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp" and self.mode != "none":
            headers = dict(scope.get("headers", []))
            header = b"authorization" if self.mode == "bearer" else b"x-api-key"
            expected = ("Bearer " if self.mode == "bearer" else "") + FIXTURE_KEY
            if not secrets.compare_digest(headers.get(header, b""), expected.encode()):
                await JSONResponse({"error": "Fixture authentication required."}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(auth_mode="bearer", stateless=True):
    if auth_mode not in {"bearer", "header", "none"}:
        raise ValueError("auth_mode must be bearer, header, or none")
    definitions = json.loads((ROOT / "contracts/mcp-tools.schema.json").read_text(encoding="utf-8"))["tools"]
    samples = json.loads((ROOT / "tests/fixtures/m0/examples.json").read_text(encoding="utf-8"))["success"]
    for name in ("service_info", "always_fail", "slow_reply"):
        schema = {"type": "object", "properties": {}, "additionalProperties": False}
        if name == "slow_reply":
            schema["properties"]["delay_seconds"] = {"type": "number", "minimum": 0, "maximum": 2, "default": 0.3}
        definitions.append({"name": name, "description": "M0 fixture diagnostic only: " + name, "inputSchema": schema})
    tools = [types.Tool(**definition) for definition in definitions]
    schemas = {tool.name: tool.inputSchema for tool in tools}
    server = Server("m0-disposable-fixture")

    @server.list_tools()
    async def list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
        # SDK internal lookup has no request and needs the complete catalog.
        if request is None:
            return types.ListToolsResult(tools=tools)
        cursor = request.params.cursor if request.params else None
        if cursor is not None and (len(cursor) > 3 or not cursor.isascii() or not cursor.isdecimal() or str(int(cursor)) != cursor):
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Invalid fixture cursor."))
        start = int(cursor) if cursor is not None else 0
        if start >= len(tools) or start % 3:
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Invalid fixture cursor."))
        end = start + 3
        return types.ListToolsResult(tools=tools[start:end], nextCursor=str(end) if end < len(tools) else None)

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict):
        if name not in schemas:
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Unknown fixture tool."))
        arguments = {key: value.strip() if key in {"name", "sku", "search"} and isinstance(value, str) else value
                     for key, value in arguments.items()}
        if list(validator(schemas[name]).iter_errors(arguments)):
            return failure("INVALID_ARGUMENT", "Arguments do not match the fixture tool schema.")
        if name == "always_fail":
            return failure("FIXTURE_FAILURE", "Deliberate fixture failure.")
        if name == "slow_reply":
            await asyncio.sleep(arguments.get("delay_seconds", 0.3))
            return result({"fixture_only": True, "replied": True})
        if name == "service_info":
            return result({"fixture_only": True, "name": "m0-disposable-fixture"})
        sample = next(item for item in samples if item["tool"] == name)
        data = deepcopy(sample["result"]["structuredContent"])
        if name in {"get_order", "update_order_status"}:
            if arguments["order_id"] != data["order"]["id"]:
                return failure("ORDER_NOT_FOUND", "Order was not found in the fixture.")
            if name == "update_order_status":
                data["order"]["status"] = arguments["status"]
        elif name == "lookup_sku":
            data["sku"] = arguments["sku"]
            if arguments["sku"] != sample["arguments"]["sku"]:
                data.update(found=False, warehouses=[])
        elif name == "create_product":
            price = format(Decimal(arguments["regular_price"]), ".2f")
            data["product"].update(name=arguments["name"], sku=arguments.get("sku", ""), price=price, regular_price=price)
        elif name in {"list_products", "list_orders"}:
            items = data["items"]
            if name == "list_products":
                items = [p for p in items if ("sku" not in arguments or p["sku"] == arguments["sku"])
                         and ("search" not in arguments or arguments["search"].casefold() in p["name"].casefold())]
            else:
                parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
                if "created_from" in arguments and "created_to" in arguments and parse(arguments["created_from"]) > parse(arguments["created_to"]):
                    return failure("INVALID_ARGUMENT", "The start time must not follow the end time.")
                items = [o for o in items if ("status" not in arguments or o["status"] == arguments["status"])
                         and ("created_from" not in arguments or parse(o["date_created"]) >= parse(arguments["created_from"]))
                         and ("created_to" not in arguments or parse(o["date_created"]) <= parse(arguments["created_to"]))]
            page, per_page = arguments.get("page", 1), arguments.get("per_page", 20)
            start = (page - 1) * per_page
            data.update(items=items[start:start + per_page], page=page, per_page=per_page, has_more=start + per_page < len(items))
        return result(data)

    # The SDK catches exceptions inside call_tool; guard names outside that wrapper.
    sdk_call_handler = server.request_handlers[types.CallToolRequest]

    async def checked_call(request):
        if request.params.name not in schemas:
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Unknown fixture tool."))
        return await sdk_call_handler(request)

    server.request_handlers[types.CallToolRequest] = checked_call
    manager = StreamableHTTPSessionManager(app=server, json_response=True, stateless=stateless)

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    class MCPEndpoint:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    async def health(request):
        return JSONResponse({"status": "ok", "fixture_only": True})

    app = Starlette(routes=[Route("/health", health), Route("/mcp", MCPEndpoint())], lifespan=lifespan)
    return FixtureAuth(app, auth_mode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--auth-mode", choices=["bearer", "header", "none"], default="bearer")
    parser.add_argument("--stateful", action="store_true")
    args = parser.parse_args()
    uvicorn.run(create_app(args.auth_mode, stateless=not args.stateful), host="127.0.0.1", port=args.port)
