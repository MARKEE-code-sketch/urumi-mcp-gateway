# M0: small checks before building

**WHAT:** Test our message agreements with a temporary MCP server and sample shop/warehouse replies.

**WHY:** Find compatibility problems before building the real dashboard and shop.

**HOW:** A real Python MCP client talks to a small server over localhost HTTP. No Kubernetes, real shop, gateway, or database is involved yet.

## Files

| File | Job |
|---|---|
| fixture_server.py | Temporary server with six agreed tools and three diagnostic tools. |
| schema_validation.py | Checks message fields and timezone-aware dates. |
| run_checks.py | Runs the separate tests/m0 checks and saves results. |
| network_probe.py | Checks Groq reachability and Microsoft Learn discovery without reading keys. |
| model_probe.py | Checks a real Groq tool loop using sample inventory; requires confirmed free usage. |
| inspector_probe.py | Runs an already installed MCP Inspector CLI against the temporary server. |
| requirements.lock.txt | Exact dependencies used for the successful Windows M0 checks. |

The temporary server accepts bearer, custom-header, or no authentication depending on its launch setting. Its public sample key is m0-fixture-only-key. Never use that key for the application.

## Run in PowerShell, from the project folder

The project already has a prepared .venv. To repeat local checks:

~~~powershell
./.venv/Scripts/python.exe experiments/m0/run_checks.py
~~~

To check the two hosted endpoints without sending keys:

~~~powershell
./.venv/Scripts/python.exe experiments/m0/network_probe.py
~~~

Only after confirming your Groq account/model uses free quota with no paid billing:

~~~powershell
./.venv/Scripts/python.exe experiments/m0/model_probe.py --confirm-free-plan
~~~

That command reads GROQ_API_KEY from the root .env only after an unauthenticated connectivity check succeeds. It sends sample data, validates the requested tool arguments, returns a sample warehouse reply, and requires a final model answer. At most eight rounds/eight tool calls are allowed. It does not connect to MCP or prove the future chat module. Google fallback is deferred; there is no paid fallback.

Results are saved under docs/evidence/m0. A failure exits with a nonzero code. Do not paste .env or keys into logs or chat.

### Recreate the Python environment if needed

~~~powershell
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r experiments/m0/requirements.lock.txt
~~~

The agent could not download packages because this session denied outbound sockets. It reused 31 existing uv cache archives, repackaged them as wheels in ignored .cache/offline-wheels, and installed offline into this project's .venv. No other project's environment was changed. The lock is for these M0 experiments; later application dependencies need their own review.

### Inspect manually

In one PowerShell window, start the sample server:

~~~powershell
./.venv/Scripts/python.exe experiments/m0/fixture_server.py --port 8765
~~~

In another window, if npm can reach the registry:

~~~powershell
npx.cmd @modelcontextprotocol/inspector@0.19.0 --cli http://127.0.0.1:8765/mcp --transport http --method tools/call --tool-name lookup_sku --tool-arg sku=DEMO-001 --header "Authorization: Bearer m0-fixture-only-key"
~~~

Expected sample reply: DEMO-001, Bengaluru, quantity 12, isError false. The agent's cached Inspector returned this reply but Node v24.18.0 crashed during shutdown. A successful JSON reply alone does not pass this check; the client must also exit cleanly. The browser Inspector demonstration is still unverified.

## Codex preparation

[The example configuration](codex-mcp.example.toml) is a template only. It has not been installed into your Codex settings. It points only to the future gateway and reads a member key from an environment variable. The gateway does not exist yet. Real Codex discovery/calls remain an acceptance gap; do not claim them from Python SDK results.

## Results

Read [the M0 report](../../docs/evidence/m0/report.md). M0 is still incomplete. M1 requires its own approval after M0 acceptance.
