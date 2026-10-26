"""Bounded standalone MCP compatibility probe; returned content is data only."""
import argparse
import asyncio
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import re
import time

import httpx
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

LEARN_URL = "https://learn.microsoft.com/api/mcp"


class ProbeLimit(ValueError):
    pass


class LimitedStream(httpx.AsyncByteStream):
    def __init__(self, stream, transport):
        self.stream, self.transport = stream, transport

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            self.transport.total += len(chunk)
            if size > self.transport.response_limit or self.transport.total > self.transport.aggregate_limit:
                raise ProbeLimit("MCP response byte limit exceeded.")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class LimitedTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport=None, response_limit=2 * 1024 * 1024, aggregate_limit=8 * 1024 * 1024):
        self.transport = transport or httpx.AsyncHTTPTransport(retries=0)
        self.response_limit, self.aggregate_limit, self.total = response_limit, aggregate_limit, 0

    async def handle_async_request(self, request):
        response = await self.transport.handle_async_request(request)
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            await response.aclose()
            raise ProbeLimit("Compressed MCP responses are not accepted by this bounded probe.")
        response.stream = LimitedStream(response.stream, self)
        return response

    async def aclose(self):
        await self.transport.aclose()


async def discover(session):
    tools, cursor, seen = [], None, set()
    for _ in range(20):
        page = await session.list_tools(cursor=cursor)
        tools.extend(page.tools)
        if len(tools) > 200:
            raise ProbeLimit("MCP tool count limit exceeded.")
        cursor = page.nextCursor
        if cursor is None:
            return tools
        if cursor in seen:
            raise ProbeLimit("MCP discovery repeated a cursor.")
        seen.add(cursor)
    raise ProbeLimit("MCP discovery page limit exceeded.")


def documentation_call(tools):
    for tool in tools:
        properties = tool.inputSchema.get("properties", {})
        if "search" in tool.name.lower() and properties.get("query", {}).get("type") == "string":
            arguments = {"query": "Kubernetes readiness versus liveness probes"}
            if "question" in properties and "question" in tool.inputSchema.get("required", []):
                arguments["question"] = "What is the difference between Kubernetes readiness and liveness probes?"
            if not list(Draft202012Validator(tool.inputSchema).iter_errors(arguments)):
                return tool.name, arguments
    raise ValueError("No discovered documentation-search schema supports the planned query.")


async def probe(url=LEARN_URL, hosted=True, timeout=45, headers=None, transport=None):
    started = time.monotonic()
    evidence = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "url": url,
                "real_hosted": hosted, "versions": {name: importlib.metadata.version(name) for name in ("mcp", "httpx")}}
    bounded = LimitedTransport(transport)
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(transport=bounded, headers={"Accept-Encoding": "identity", **(headers or {})}, timeout=httpx.Timeout(15, connect=5, pool=5), trust_env=False, follow_redirects=False) as http:
                async with streamable_http_client(url, http_client=http) as (read, write, get_id):
                    async with ClientSession(read, write) as session:
                        initialized = await session.initialize()
                        evidence.update(protocol=initialized.protocolVersion, stateful_session=get_id() is not None)
                        tools = await discover(session)
                        evidence["tools"] = [tool.model_dump(exclude_none=True) for tool in tools]
                        if hosted:
                            name, arguments = documentation_call(tools)
                        else:
                            name, arguments = "lookup_sku", {"sku": "DEMO-001"}
                        result = await session.call_tool(name, arguments)
                        encoded = json.dumps(result.model_dump(exclude_none=True))
                        if len(encoded.encode()) > 2 * 1024 * 1024:
                            raise ProbeLimit("Serialized MCP result exceeds limit.")
                        if result.isError:
                            raise ValueError("MCP tool returned an execution error.")
                        evidence.update(selected_tool=name, arguments=arguments, result=result.model_dump(exclude_none=True))
                        if hosted:
                            direct = []
                            for block in result.content:
                                if getattr(block, "type", None) == "text":
                                    try:
                                        payload = json.loads(block.text)
                                        if isinstance(payload, dict):
                                            direct.extend(item["contentUrl"] for item in payload.get("results", []) if isinstance(item, dict) and isinstance(item.get("contentUrl"), str) and item["contentUrl"].startswith("https://learn.microsoft.com/"))
                                    except (ValueError, TypeError):
                                        pass
                            links = sorted(set(direct)) or sorted({link.rstrip("().,;") for link in re.findall(r"https://learn\.microsoft\.com/[^\s\"<>\\]+", encoded)})
                            if not links or not all(word in encoded.lower() for word in ("readiness", "liveness")):
                                raise ValueError("Hosted result does not contain relevant documentation and source links.")
                            evidence["source_urls"] = links
                        await read.aclose()
                        await write.aclose()
        evidence["status"] = "PASS"
    except Exception as exc:
        # Nested SDK task groups may contain transport failures; keep diagnostics bounded and header-free.
        def categories(error):
            return [type(error).__name__] + [kind for child in getattr(error, "exceptions", []) for kind in categories(child)]
        evidence.update(status="FAIL", error_categories=categories(exc), message="Compatibility check failed; inspect category and recorded complete discovery if available.")
    evidence.update(elapsed_seconds=round(time.monotonic() - started, 3), received_bytes=bounded.total)
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=LEARN_URL)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--output")
    options = parser.parse_args()
    if not options.inventory and options.url != LEARN_URL:
        parser.error("The hosted acceptance probe is restricted to Microsoft Learn.")
    evidence = asyncio.run(probe(options.url, hosted=not options.inventory))
    encoded = json.dumps(evidence, ensure_ascii=True, indent=2)
    if options.output:
        Path(options.output).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    raise SystemExit(0 if evidence["status"] == "PASS" else 1)
