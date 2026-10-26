# Context7 discovery timeout repair — 25 October 2026

Result: fixed and deployed. Context7 is Connected, both tools are visible in the dashboard, and an authenticated external MCP client successfully resolved FastAPI documentation through the gateway.

## Cause and change

The saved registration already used the correct URL, `https://mcp.context7.com/mcp`, and bearer authentication. Context7's [official client instructions](https://context7.com/docs/resources/all-clients) support this configuration. No token replacement or authentication change was needed.

An in-backend diagnostic using the production upstream client and saved Secret completed initialization and tool discovery in approximately 3.25 seconds. The gateway previously limited the entire discovery operation, including credential lookup and MCP initialization, to 3 seconds. This produced a false Unreachable/TIMEOUT result.

`backend/gateway/discovery.py` now gives discovery a finite 10-second deadline. This changes only the discovery budget. Tool execution deadlines, URL validation, SSRF protection, credential storage, authorization and network policies remain unchanged.

## Verification

- Regression reproduced with the previous 3-second deadline; a simulated 3.1-second handshake now succeeds. Stalled credential/upstream operations still time out and leave a healthy peer available.
- `tests/gateway`, `tests/chat` and `tests/e2e/test_runtime.py`: **200 passed**. A preceding run encountered a Windows temporary-directory permission error; rerunning with a fresh workspace-local temporary directory passed without changing application behavior or assertions. See `tests.txt`.
- Backend image `urumi/backend:m10-discovery-timeout` deployed using the existing Helm release. `runtime.json` records the rollout, preserved data/registrations/key metadata/PVC identities, and unchanged other six Pod identities.
- Real HTTPS browser check: **PASS**, TLS validation enabled. Both `context7__resolve-library-id` and `context7__query-docs` are displayed. See `browser.json` and `connected-tools.png`.
- Real external MCP client: **PASS**, using a gateway personal API key. Called `context7__resolve-library-id` with a read-only FastAPI documentation lookup. The response included official FastAPI library IDs. Matching successful audit: `52f8b083-0ee5-4fa1-a92f-b5055eb02204`; duration 4864 ms. See `gateway-call.json`.

Reproducible checks, from PowerShell in the repository root:

```powershell
.\.tools\m10\venv\Scripts\python.exe scripts\m10\check-context7.py
```

The browser checker is `scripts/m8/check-context7.mjs`; it requires the existing private operator/browser environment. Neither checker publishes credentials. The external-client checker reads only the private gateway key; it does not read the Context7 upstream token.

## Limits

The successful live invocation covered library resolution, not `query-docs` execution or a provider-driven Context7 chat conversation. Both tool schemas were discovered and displayed. Other servers' reachability changed between observations; the latest recorded lookup shows Microsoft Learn CONNECTION_FAILED while Context7 succeeded. No claim is made that all external services remain continuously reachable. User registration enable/disable choices were not changed by this repair.

Discovery remains bounded; a slower service can still time out. Several slow services can also delay an uncached aggregate tool listing. This repair does not promise arbitrary upstream latency support.
