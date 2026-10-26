# M0 design: how our parts talk

**Status:** Design approved by the user on 14 October 2026. M0 experiments are authorized and in progress; module acceptance is pending.

## Read this page first

**WHAT:** Agree on the information passed between our dashboard, gateway, shop helper, and other MCP servers.

**WHY:** Each module can then be built and checked separately without guessing what another module expects.

**HOW:** Use the written examples below as the shared agreement. Later we replace the sample replies with real services, keeping the same messages.

## One request, from start to finish

You type: **“Create a product called Blue Mug for ₹299.”**

1. The dashboard sends your message using your login session.
2. The backend checks who you are. The model asks to use the product-creation tool.
3. The gateway checks your access again and starts an activity record.
4. The shop helper receives the product name and price. It asks WooCommerce to create the product.
5. The gateway records the result. Chat shows the answer and the tool it actually called.

Codex follows the same checked path using your personal gateway key instead of a dashboard login cookie. The shop's credential remains inside the server side of our system.

## The written agreements

| File | Everyday purpose |
|---|---|
| [Tool agreement](../../contracts/mcp-tools.md) | What the five shop actions and Inventory action need and return; how external tools are discovered. |
| [Dashboard agreement](../../contracts/platform-api.md) | What the web pages ask the backend for, including login, keys, helpers, activity, and chat. |
| [Identity/activity agreement](../../contracts/identity-and-audit.md) | How we know who asked, who is allowed, and what gets written in the activity history. |
| [Exact tool field rules](../../contracts/mcp-tools.schema.json) | Machine-readable proposed field checklists. You do not need to read this first. |
| [Sample replies](../../tests/fixtures/m0/examples.json) | Clearly labelled examples for checking unfinished modules. These are not live shop records. |

The shop lookup and Inventory lookup can jointly answer: **“Find DEMO-001 in our shop, tell me its price, and check warehouse availability.”** A separate Microsoft Learn call will demonstrate a real hosted source. An external source's tools come from discovery; we do not hardcode Microsoft's tool names.

## Approved starting defaults

The user approved these on 14 October. They were not specified by the assignment. The main stack choices already confirmed are in [decisions.md](../decisions.md).

| Proposal | What it means |
|---|---|
| Invitation lasts 24 hours | A link works once and expires after a day. |
| Login lasts 8 hours | After that, the person signs in again. Logout ends it earlier. |
| Members see their own activity; admin sees all | Team members can inspect their actions while the admin can review the team. Members can still use all enabled tools. |
| Helper discovery waits up to 3 seconds; tool calls up to 10 | A slow helper gets a clear error instead of holding up the others. Validate these starting values in experiments. |
| Chat allows up to 8 model/tool rounds | Stops an endless chain of requests and shows what actually happened. |

The approved security design includes: browser cookie/CSRF checks, a dedicated namespace for upstream Secrets, allowed destination URLs, reserved credential headers, and the tool-name mapping. Their purpose is to keep identity and credentials in the right places. They are described in the three agreements; no security behavior has been implemented or proved yet.

**If a write times out:** it might have happened in WooCommerce even though we lost the reply. We record timeout/uncertainty and do not repeat it automatically. **If a key is revoked:** the next not-yet-dispatched call is denied; revocation cannot undo an action already sent.

## What was checked and what comes next

The documents were saved and read back. JSON samples were parsed and checked for matching text/structured replies. Formal schema and localhost MCP experiments now pass 14 checks. Inspector exits with a Windows Node assertion despite returning replies; hosted discovery and the user-run Groq tool loop now pass; clean Inspector exit and Codex checks remain incomplete. No application module was implemented. See [M0 results](../evidence/m0/report.md).

M0 experiments cover or still need to check real MCP initialize/list/call, authentication, pagination/errors, Codex/Inspector compatibility, a real Groq tool loop (Google free tier if needed), and the working dependency versions. Evidence belongs in docs/evidence/m0/. M1 is a separate approval gate after the M0 results.

The alternate workspace tool can edit files and launch PowerShell. Docker's last check returned permission denied from this tool identity; Kubernetes readiness is not established. Read the [workspace evidence](../evidence/workspace-access-2026-10-14.md) for the exact limitation.
