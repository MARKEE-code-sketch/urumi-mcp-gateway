# Module 0: agree before we build

**Status:** Design approved and local experiments performed, 14 October 2026. M0 is incomplete; see [results](../evidence/m0/report.md).

**Source:** The assignment DOCX sets requirements. `blueprint.md` sets the proposed module plan. `AGENTS.md` sets our learning and review steps. Your request to start M0 authorizes this preparation; proposed choices remain open until agreed.

## What, why, and how

**WHAT:** Write down how the project parts will ask for things and answer each other. Check that the main libraries and AI client can speak the same language.

**WHY:** The dashboard and gateway can be built separately only if both know what a request and reply look like. Otherwise, one might send `product_price` while the other expects `price`.

**HOW:** Start with everyday examples, agree on their exact fields, prepare sample replies, then run small throwaway experiments. We will explain each experiment before building it.

A **contract** is that written agreement. A **fixture** is prepared sample data used to check a part before the real shop exists. Neither word means we must build the complete system now.

## One example we will agree on

You ask: **“Create a product called Blue Mug for 299.”**

1. The AI chooses the shop action `create_product`.
2. The gateway knows which signed-in person requested it.
3. The shop helper receives the agreed product fields.
4. The helper returns the new product's ID and details, or a clear failure.
5. The activity record identifies the person, action, time, duration, and result.

Illustrative product arguments:

```json
{"name": "Blue Mug", "regular_price": "299.00"}
```

This is a proposed example, not a working shop request. Price is shown as text to preserve its decimal value. Currency comes from the shop configuration; INR is confirmed. M0 will settle field names and required fields after checking WooCommerce's official API.

## Our steps and review points

| Step | What we do | Result |
|---|---|---|
| 1. Agree on choices | Discuss stack, sample helpers, AI access, timezone, and deadline. | A short decision list; unresolved choices stay clearly marked. |
| 2. Write the agreements | Describe shop tools, dashboard requests, user identity, and activity records. | Three readable contract documents. |
| 3. Review the design | Check message examples against the assignment and security rules. | Independent review and your design approval. |
| 4. Run small experiments | Try a temporary MCP client/server and an approved real AI model using sample data. | Saved commands, results, and compatible version numbers. |
| 5. Review M0 | Explain what worked, what failed, and what is still missing. | Your decision on starting M1. |

Steps 1–3 have saved agreements, independent design review, and user approval. Step 4 has 14 passing local checks; hosted/model/client gaps remain. See [the M0 design overview](m0-design.md) and results report.

## Files M0 will produce

| File or folder | Purpose |
|---|---|
| `docs/decisions.md` | Agreed choices, reasons, dates, and open questions. |
| `contracts/mcp-tools.md` | Inputs, replies, and errors for all five shop tools, the Inventory sample helper, and external tool discovery; gateway tool naming. |
| `contracts/platform-api.md` | Dashboard requests and replies for login, invites, people, keys, servers, chat, and activity. |
| `contracts/identity-and-audit.md` | How a verified caller is represented and how each attempted action is recorded. |
| `tests/fixtures/` | Clearly labelled sample replies and temporary helpers, including slow and failed ones. |
| Dependency lock file(s) | Exact working package versions, chosen after the experiments. |
| `docs/evidence/m0/` | Commands, experiment transcripts, review notes, and remaining gaps. |

The decision record, three approved design agreements, tool schemas, sample replies, executable fixtures, dependency lock, and local runtime evidence now exist. Live provider/client checks remain incomplete.

## What M0 must prove before it is complete

| Check | What counts as proof |
|---|---|
| Agreements are clear | Required inputs, example replies, errors, and the responsible module are written down. Two separately built parts can use the same examples. |
| MCP works over Streamable HTTP | A temporary real client connects, lists tools, calls one, and handles a failure using the selected SDK. |
| Authentication is understood | The temporary server accepts the selected header and rejects a missing or wrong key. These are sample keys only. |
| Session behavior is understood | Record whether sessions are used, how the client reconnects, and how later per-request key checks will work. No claim that the real gateway's revocation is implemented. |
| Failures can be simulated | Fixtures cover successful, failed, and slow replies. The actual gateway's failure isolation belongs to M6. |
| The chosen model can request a tool | An approved real model requests a tool with valid arguments, gets sample results, and produces an answer. No real shop connection is needed. |
| Versions are repeatable | Record and lock the library versions that actually passed. Do not choose versions from memory. |

Passing M0 does not prove that Kubernetes or the finished project works. Those checks belong to later modules.

## Confirmed choices and remaining review

See [the decision record](../decisions.md). Python/FastAPI, React/TypeScript, PostgreSQL, k3d, WooCommerce + Inventory + Microsoft Learn, India time, INR, and the 20 October deadline are confirmed. Groq or Google AI Studio may be used only within verified free usage.

The gateway must accept compatible external Streamable HTTP servers by URL, with no credential, a bearer token, or a configured API-key header. Discover tools generically. Microsoft Learn checks the no-key external path; controlled fixtures check authenticated paths and failures. A real hosted keyed-server run must be reported separately if completed.

MariaDB, local login, Groq first with Google free tier second, and Codex plus Inspector are now confirmed. Still discuss member activity visibility, invitation/session lifetimes, exact model and client compatibility, and detailed identity/Secret/URL/session/timeout rules. No need to choose all implementation settings before their design is explained. Define today's orders consistently from midnight to now in Asia/Kolkata.

## Initial environment observations

Read-only checks on 13 October 2026 found Docker, kubectl, Python, uv, Node, npm, and Cursor commands on PATH. k3d, Helm, and Claude Code commands were not found on PATH. This does not prove the tools are absent from the computer or that an AI account is configured.

The Docker information check could not connect to the local engine pipe and could not read Docker's config because access was denied. Docker runtime readiness and available Docker memory/CPU therefore remain unverified; the cause has not been established. A Windows hardware query also returned access denied.

These checks installed nothing and changed no machine settings. We can agree on messages now; Docker and hardware readiness must be resolved before experiments that need Docker and before M1 deployment.

**Next review:** Finish hosted/model/client checks and review the M0 report. M1 needs your separate approval after M0 acceptance.

**14 October update:** Decisions are now saved and read back through an alternate workspace tool. The normal command runner remains under investigation; the earlier Docker observation is historical, not proof of current Docker failure.
