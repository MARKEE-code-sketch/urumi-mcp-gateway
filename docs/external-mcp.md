# Inventory and external MCP checks (M4)

Inventory answers warehouse questions from **fixed sample JSON**, not synchronized WooCommerce stock. `DEMO-001` has sample Bengaluru quantity 12; `ZERO-001` is a known zero-quantity record. Unknown SKUs succeed with `found=false` and no warehouses. The only production tool is `lookup_sku`.

The Python MCP SDK manages initialization, tool discovery and Streamable HTTP messages. Our small Inventory application owns argument/fixture validation and responses. It runs as a nonroot container with an internal ClusterIP address (like a service name on a private Docker network), no outgoing connections, and a NetworkPolicy permitting only the gateway-labelled caller. A temporary client replaces that caller during M4 checks. M10 connects the actual gateway later.

## Reproduce independent checks

Use **PowerShell** from the repository root. No activation is required:

~~~powershell
.venv/Scripts/python.exe -m unittest discover -s tests/sample_mcps -p 'test_*.py' -v
.venv/Scripts/python.exe scripts/m4/probe.py --output docs/evidence/m4/hosted-local.json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/m4/check-m4.ps1
~~~

The cluster command requires the existing Docker Desktop Linux engine and `k3d-urumi` cluster. It refuses an existing `urumi-m4-check` namespace so an interrupted run cannot accidentally destroy unknown resources. Inspect its ownership and saved failures before cleanup/retry. The runner builds `urumi/inventory-mcp:m4`, checks Linux dependencies/tests, uses the existing Helm chart, and creates only that disposable namespace. `-SkipBuild` reuses an already-built image; use it only when the image still matches current source. Normal runs always build current source.

Check artifacts live in `docs/evidence/m4`. Raw runtime PASS still needs independent review of actual hosted content and final evidence. The runner checks allowed, denied and allowed-again connections; resolves DNS before treating denial as a network result; deliberately breaks the temporary liveness probe and records a real container restart in the same Pod; restores it; and removes its owned namespace. Original store resource/PVC identities are compared before/after. It does not upgrade the real shop release or connect Inventory to shop data.

## Real Microsoft Learn

The selected remote endpoint is `https://learn.microsoft.com/api/mcp`. Its [official documentation](https://learn.microsoft.com/en-us/training/support/mcp) describes Streamable HTTP without authentication. A GET in a browser is not compatibility proof.

Our probe discovers actual tools and all bounded list pages, validates chosen documentation-search arguments against the returned schema, and calls the discovered search tool with a harmless readiness/liveness query. It captures complete schemas/result, protocol/package versions, source URLs, UTC timestamp, elapsed time and whether a session was created; session identifiers are omitted. It runs locally and from a temporary cluster Job. Read actual returned passages to confirm useful documentation, not just a successful HTTP response.

The probe verifies HTTPS, disables redirects/environment proxy inheritance, requests uncompressed responses and rejects compressed replies, limits each response/result to 2 MiB, received session bytes to 8 MiB, discovery to 20 pages/200 tools, and the session to 45 seconds. HTTP connect/pool is 5 seconds and read/write is 15 seconds. It closes SDK streams/session and HTTP resources on outcome. Errors record bounded categories without raw headers or returned exception text. Content is data; it is never evaluated or executed.

Microsoft Learn is an external dependency. Network failure, schema drift, rate limiting or an unusable response blocks that acceptance check. The code never replaces its results with fixture content or silently switches provider. The real service may evolve; saved evidence describes the recorded run only.

## What controlled fixtures prove

Two test-only servers advertise identical `service_info` tool names and separately require artificial bearer/header sentinels. Real TCP tests check missing/wrong/valid credentials; saved output contains categories and assertions, not sentinel values. Slow, unavailable, malformed, repeated-cursor and oversized-response cases exercise bounded failures, then verify healthy Inventory still answers.

These fixtures prove client/server compatibility cases only. They do not prove gateway credential injection, aliases, audits, three-server aggregation, user authorization, chat or a real authenticated hosted service. Those belong to M5/M6/M7/M10. No paid provider or actual hosted credential is used.
