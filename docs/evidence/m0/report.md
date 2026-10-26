# M0 experiment results

> **14 October progression decision:** User authorized proceeding to the M1 specification after the proposed M0 acceptance with exceptions. M0 is accepted for progression; technical results below retain their original PASS/FAIL/unverified status. Inspector clean exit and live Codex checks are deferred to M10; fresh installation reproducibility remains for M9. M1 implementation is not authorized by this decision.

**Date:** 14 October 2026. **Gate status: ACCEPTED FOR PROGRESSION WITH EXCEPTIONS.** Technical checklist remains incomplete as detailed below. M1 specification work is authorized; M1 implementation has not started.

## In simple terms

We have agreed on the messages our future parts will exchange and checked those messages using a small pretend shop. The pretend shop speaks real MCP over HTTP. This proves the selected Python pieces can communicate locally; the real shop, gateway, and Kubernetes system are still future work.

## Observed results

| Check | Result | Evidence |
|---|---|---|
| Local contract and HTTP tests | PASS: 14 tests, zero failures/errors; no captured warnings. | [Machine result](test-results.json), [full output](unittest-output.txt) |
| MCP initialize/list/call | PASS with Python SDK; negotiated protocol 2025-11-25. | Same local test output |
| Missing/wrong key, valid bearer/custom header, no-key server | PASS on disposable fixtures. | Same local test output |
| Paginated discovery, valid results, invalid inputs, tool/protocol errors | PASS on disposable fixtures. | Same local test output |
| Stateful session termination and stateless reconnect | PASS on disposable fixtures. | Same local test output |
| Cancel slow call and call a separate healthy endpoint | PASS in fixture test; not proof of gateway failure isolation. | Same local test output |
| Dependency compatibility | Installed cached packages; pip check reported no broken requirements. Versions locked. | [Lock file](../../../experiments/m0/requirements.lock.txt) |
| Hosted Microsoft Learn | PASS from user PowerShell: initialized protocol 2025-06-18; discovered microsoft_docs_search, microsoft_code_sample_search, microsoft_docs_fetch. No tool called. | [Network probe](network-probe.json) |
| Groq connectivity | PASS from user PowerShell: HTTP 401 without credentials proves reachability. This unauthenticated check proves reachability only; the separate model check below proves authenticated inference. | [Network probe](network-probe.json) |
| Real model tool loop | PASS from user PowerShell: Groq openai/gpt-oss-20b requested lookup_sku(DEMO-001), received validated sample data, and answered Bengaluru / 12 units. | [Model probe](model-probe.json) |
| MCP Inspector 0.19.0 | FAIL in both agent and user terminal: correct sample inventory reply, then Windows libuv shutdown assertion. User output reports client exit 3221226505 and PowerShell LASTEXITCODE 1. | [Agent output](inspector-probe.json), [user terminal evidence](inspector-user-terminal.json) |
| Codex real connection | NOT RUN. Configuration template only. | [Template](../../../experiments/m0/codex-mcp.example.toml) |
| Real gateway, login, revocation, upstream secret isolation, Kubernetes | NOT IMPLEMENTED in M0. | Later modules |

## What the checks caught

1. A date-time format checker without its optional parser could accept a date missing its timezone. Added an explicit checker and invalid-date cases.
2. Inspector called a tool before asking for the catalog. The SDK invokes the catalog callback internally without a request; our fixture now handles this and returns the complete internal catalog. Added a direct-call regression.
3. Explicitly closing client streams removed captured resource warnings in the local suite.

The Inspector sample call returns the expected Bengaluru quantity 12 with isError false. The user terminal independently reproduced the shutdown assertion after receiving the correct reply. npm also warned that Inspector v1 packages are deprecated. Its process crash remains unresolved; do not label Inspector compatible yet. The failure's stack identifies Node's Windows runtime, but its precise cause has not been established.

## Reproduce and finish

Run from the project folder in PowerShell:

~~~powershell
./.venv/Scripts/python.exe experiments/m0/run_checks.py
./.venv/Scripts/python.exe experiments/m0/network_probe.py
~~~

The first command is local. The user ran the second successfully in their own PowerShell session on 14 October 2026; the saved JSON matches the supplied terminal output. Earlier agent-run attempts were blocked. These are different execution environments, so the earlier access-denied errors do not describe the user's terminal connectivity.

The user supplied a successful Groq model-probe result, matching the saved JSON. The probe validates arguments and sample output before sending the tool result to Groq. This checks model tool calling directly, not MCP routing or future gateway chat. It does not independently verify billing or remaining quota. Next complete Inspector and Codex client checks and independently review all results. M0 acceptance remains pending until required live evidence is available or the user explicitly revises the gate.

## Limits

Sample authentication is not hashed-key storage, role enforcement, or revocation. Cancelling a fixture call does not prove the future gateway's isolation or its proposed 10-second limit. No real product/order was created and no Kubernetes deployment occurred. The user-run model probe sent the Groq key to Groq for authenticated inference; no key value appears in the saved result. The cached dependencies were installed only in this project's .venv. Standard command-runner recovery remains separate from the working alternate execution tool.
