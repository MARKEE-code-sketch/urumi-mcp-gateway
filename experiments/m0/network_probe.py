"""Unauthenticated M0 connectivity checks. Does not read .env or send keys."""
import asyncio
import json
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[2]


def windows_codes(error):
    codes = set()
    seen = set()
    pending = [error]
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if getattr(item, "winerror", None):
            codes.add(item.winerror)
        pending.extend(getattr(item, "exceptions", []))
        pending.extend(x for x in [item.__cause__, item.__context__] if x)
    return sorted(codes)


async def main():
    checks = []
    async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
        try:
            response = await http.get("https://api.groq.com/openai/v1/models")
            checks.append({"check": "groq_connectivity_only", "status": "PASS" if response.status_code == 401 else "BLOCKED", "http_status": response.status_code, "note": "No credential sent; 401 proves reachability, not key validity or free account status."})
        except Exception as error:
            checks.append({"check": "groq_connectivity_only", "status": "BLOCKED", "reason": "NETWORK_ACCESS_FAILED", "windows_errors": windows_codes(error)})
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
            async with streamable_http_client("https://learn.microsoft.com/api/mcp", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    names, cursor = [], None
                    for _ in range(10):
                        page = await session.list_tools(cursor=cursor)
                        names.extend(t.name for t in page.tools)
                        cursor = page.nextCursor
                        if not cursor:
                            break
                    if cursor:
                        raise RuntimeError("Discovery did not finish within the probe limit")
                    checks.append({"check": "microsoft_learn_initialize_and_list", "status": "PASS", "protocol": initialized.protocolVersion, "tool_names": names, "note": "Discovered, not called; gateway integration remains M10."})
    except Exception as error:
        checks.append({"check": "microsoft_learn_initialize_and_list", "status": "BLOCKED", "reason": "CONNECTIVITY_OR_PROTOCOL_FAILED", "windows_errors": windows_codes(error)})
    target = ROOT / "docs/evidence/m0/network-probe.json"
    target.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
