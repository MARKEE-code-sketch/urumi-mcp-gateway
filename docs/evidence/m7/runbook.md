# M7 independent verification runbook

**WHAT:** Test the chat loop separately. **WHY:** A failure should be attributable to chat rather than a shop, database or dashboard. **HOW:** Supply prepared identities, gateway results and model replies; then separately check the real model against the same fake gateway.

Use PowerShell from the repository root. The root-managed `.tools/m6/venv` contains the shared M6/M7 lock. Do not modify `.tools/m5/venv` or activate a CMD `.bat` file in PowerShell.

## Offline check

```powershell
./.tools/m6/venv/Scripts/python.exe scripts/m7/check-m7.py
```

This runs deterministic pytest checks plus loopback TCP/ASGI transport tests, with no hosted inference, shop, PostgreSQL or Kubernetes requirement. It saves `unit-output.txt` and `unit-results.json` here. Exit 0 means this offline suite passed; it does not imply provider or complete-system acceptance.

For an individual source change:

```powershell
./.tools/m6/venv/Scripts/python.exe -m pytest tests/chat -q --assert=plain -p no:cacheprovider
```

## Controlled real-provider check

Confirm the current Groq account/model uses approved free access before this command. A successful API response cannot independently establish billing status. The runner refuses inference without the explicit flag and never switches providers or models.

Supply `GROQ_API_KEY` privately through the process environment, or keep the existing key in the ignored root `.env`; do not put the value on a command line or into source/evidence. The application itself never automatically reads `.env`.

```powershell
./.tools/m6/venv/Scripts/python.exe scripts/m7/check-m7.py --live-provider --confirm-free-plan
```

The command reruns offline checks, then asks Groq `openai/gpt-oss-20b` to call the advertised fake `inventory__lookup_sku` tool for DEMO-001 and answer from sample Bengaluru/12 data. Exactly one expected call and a correct sample answer are required. It writes `provider-probe.json`; failures are not converted into mocked passes. Exit 2 means live evidence is blocked/failed; inspect safe saved status, never print the key or raw provider response.

This is a real provider with a fake gateway/identity, not a real MCP or shop operation. It creates no cluster resources and needs no cleanup beyond closing clients and the temporary loopback fixtures used by pytest.

## Runtime responsibilities

`ChatAgent` receives provider, gateway, identity and optional clock as dependencies. `mount_chat` adds one route to a supplied test application. Gateway catalog/dispatch and completion-context helpers are shared with M6; M7 never opens an upstream MCP connection or writes its own audit row. On cancellation, no further dispatch is started and late synchronous work remains capacity-bounded.

The final backend provider key must come from a pre-created Kubernetes Secret through `secretKeyRef`, with no provider key in a browser response or model payload. This final deployment wiring belongs to M10. The root may additionally run this suite in the shared Linux image; save that output separately and keep it distinct from live Kubernetes and browser evidence.

The completed shared-image run passed all **119 tests (72 chat plus 47 gateway) in 43.66 seconds**; see [Linux output](../m6/linux-module-tests.txt). Runtime source/image parity was verified by the root. This passes Linux module checks, while M7's actual provider acceptance remains BLOCKED until the explicitly confirmed free-account probe runs.

Chat intentionally rejects unsafe/unbounded schema features. Its regex subset is the two owned linear nonblank/decimal-price patterns; schemas are limited to 16 KiB and 256 expanded visits/depth 10, and generic schema/argument JSON to 512 nodes/depth 20. Unsupported tools are disclosed rather than silently changing their contract. Connection/protocol failures after a possible write stop the message and require inspecting remote state before any user retry.
