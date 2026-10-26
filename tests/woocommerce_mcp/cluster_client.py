"""Disposable gateway stand-in or blocked caller; fake shop checks only."""
import argparse
import asyncio
import json
import socket
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client
from services.woocommerce_mcp.schemas import DEFINITIONS, NAMES, valid


async def allowed(url):
    evidence = {"fixture_only": True, "mode": "allowed", "calls": []}
    async with httpx.AsyncClient(timeout=12, trust_env=False) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, get_id):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                evidence["protocol"] = initialized.protocolVersion
                assert get_id() is None
                direct = await session.call_tool("get_order", {"order_id": 1})
                assert not direct.isError
                tools = (await session.list_tools()).tools
                assert [item.name for item in tools] == list(NAMES)
                evidence["tools"] = [item.model_dump(exclude_none=True) for item in tools]
                for item in tools:
                    assert item.inputSchema == DEFINITIONS[item.name]["inputSchema"]
                    assert item.outputSchema == DEFINITIONS[item.name]["outputSchema"]
                for name, args in (("list_products", {}),
                                   ("create_product", {"name": "Cluster fake mug", "regular_price": "12.50"}),
                                   ("list_orders", {}), ("get_order", {"order_id": 1}),
                                   ("update_order_status", {"order_id": 1, "status": "completed"})):
                    result = await session.call_tool(name, args)
                    assert not result.isError and valid(DEFINITIONS[name]["outputSchema"], result.structuredContent)
                    assert json.loads(result.content[0].text) == result.structuredContent
                    evidence["calls"].append({"tool": name, "result": result.model_dump(exclude_none=True)})
                invalid = await session.call_tool("get_order", {"order_id": True})
                assert invalid.isError and json.loads(invalid.content[0].text)["error"]["code"] == "INVALID_ARGUMENT"
                missing = await session.call_tool("get_order", {"order_id": 999})
                assert missing.isError and json.loads(missing.content[0].text)["error"]["code"] == "ORDER_NOT_FOUND"
                try:
                    await session.call_tool("not_a_tool", {})
                except McpError:
                    evidence["unknown_tool_protocol_error"] = True
                else:
                    raise AssertionError("Unknown tool accepted")
                await read.aclose()
                await write.aclose()
        for path in ("/livez", "/readyz"):
            assert (await http.get(url.removesuffix("/mcp") + path)).status_code == 200
    encoded = json.dumps(evidence)
    assert "SENTINEL-CONTACT" not in encoded and "cs_m3_public_fixture" not in encoded
    print(encoded)


def denied(url):
    parsed = urlsplit(url)
    # Resolve outside the policy check: a DNS failure is not proof of blocking.
    resolved = socket.gethostbyname(parsed.hostname)
    try:
        with socket.create_connection((resolved, parsed.port), timeout=3):
            raise AssertionError("Unrelated Pod connected to internal MCP service")
    except (TimeoutError, ConnectionRefusedError) as exc:
        print(json.dumps({"fixture_only": True, "mode": "denied", "blocked": True, "exception": type(exc).__name__}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--mode", choices=["allowed", "denied"], required=True)
    options = parser.parse_args()
    if options.mode == "allowed":
        asyncio.run(allowed(options.url))
    else:
        denied(options.url)
