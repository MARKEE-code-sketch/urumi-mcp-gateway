# Project decisions

**Recorded:** 14 October 2026. These are explicit choices from our conversation. The assignment DOCX remains the product source of truth; unlisted proposals are still open.

## Confirmed choices

| Area | Your choice | Boundary |
|---|---|---|
| Backend | Python + FastAPI | One backend, split into separately checked modules. |
| Dashboard | React + TypeScript | React is required; you chose the recommended TypeScript approach. Vite remains the proposed build tool. |
| Platform database | PostgreSQL | Team accounts, key hashes, server records, sessions, and activity history. Shop database choice is separate. |
| Local Kubernetes | k3d using Docker Desktop | k3d runs k3s inside Docker. VPS deployability uses the same Helm chart with changed settings. |
| First MCP server | Our own WooCommerce MCP | The five required shop tools; internal to Kubernetes, called by the gateway. |
| Second MCP server | Inventory | Sample warehouse information, not automatically synchronized with shop stock. Planned tool: lookup_sku(sku). |
| Third MCP server | Microsoft Learn | Real external hosted server, replacing the proposed Shipping server. Discover its tools rather than hardcode them. |
| External server support | Register compatible Streamable HTTP servers by URL | Support no credential, static bearer tokens, and API keys in a configured header. Adding a compatible provider must not require new gateway code. |
| Credential boundary | Server-side upstream credentials | A member's gateway key authenticates to our gateway. It is never forwarded to an upstream server. |
| Shop database | MariaDB | Confirmed for WooCommerce; PostgreSQL remains the separate platform database. |
| Dashboard login | Local accounts | No Google sign-in requirement appears in the assignment. Use the recommended local password/invitation approach; detailed lifetimes remain a design item. |
| Dashboard AI provider | Groq first; Google AI Studio free tier second | Select and check a free tool-calling model. User-run M0 probe successfully used Groq openai/gpt-oss-20b; Google remains untested. No automatic paid switch. |
| Possible paid fallback | User would obtain an OpenAI model if both free choices are unsuitable | User named “GPT-5.1 mini”; verify exact supported model ID, access, and agreed budget before any paid use. This is a future option, not a current model selection. |
| External AI demo client | Codex | Confirmed preference. Prove discovery, tool calls, multi-source prompts, and revocation in a fresh user-B client session with only gateway URL and B's key. |
| Protocol checking client | MCP Inspector | Use for protocol checks and include an Inspector connection/call in the final demonstration, since it is explicitly named in the assignment checklist. |
| Shop timezone | Asia/Kolkata | Today's orders means midnight to now in shop time. Audit timestamps use UTC. |
| Shop currency | INR | Demo prices use Indian rupees. |
| Deadline | 20 October 2026 | Exact cutoff time has not been supplied. |
| Choice process | Explain recommendations and alternatives before choosing | Architecture, cost, security, and scope decisions remain subject to user review. |

## What we will check

- Microsoft Learn proves real external connectivity without credentials. Its documented endpoint is https://learn.microsoft.com/api/mcp; compatibility remains to be tested.
- Controlled MCP test servers will check missing, wrong, and valid bearer/custom-header credentials. Microsoft Learn alone does not prove API-key handling. A real authenticated hosted-server test remains separate and unverified until performed.
- Discover tools and their input schemas from each server. Test duplicate names, disabled servers, timeouts, and failures without provider-specific routing branches.
- Check that upstream keys never appear in browser responses, client configuration, prompts, or logs.
- The two-source demo will use WooCommerce plus Inventory: look up a product's SKU in the shop, then ask the sample warehouse about that SKU. Microsoft Learn supplies the third server and proves hosted-server registration.

## Still to decide

| Choice | Current proposal |
|---|---|
| Login details | Approved: 24h invitations, 8h sessions, members own audit/admin all. Implementation and acceptance remain future work. |
| Model and client compatibility | Groq then Google free usage is the selected order; Codex is selected. Check exact model, account quota, client auth, and session behavior during M0. |
| Security and protocol details | Contract design approved. Runtime enforcement remains to be implemented and checked in the owning modules. |

## Status and evidence

M0 is accepted for progression with documented exceptions, following the user instruction to proceed with the M1 specification on 14 October 2026. Inspector clean exit and live Codex compatibility remain unverified and are deferred to M10 against the real gateway. This acceptance does not turn failed or missing checks into PASS. M1 specification work is authorized; M1 implementation and broader blueprint/design approval remain separate gates.

The user reports starting Docker Desktop. Its current readiness has not been verified. The standard command runner failed before PowerShell started. Sandbox logs identify a runtime permission update blocked by Windows file-in-use error 32 on node_repl.exe. An alternate workspace tool can read/write project files and launch PowerShell successfully. This is a working recovery path, not proof that the standard runner is repaired. A new Docker check from that tool returned permission denied; see the workspace-access evidence.

No AI key values were read or printed. M0 sample-server experiments and a project-local dependency installation have now been performed; no application implementation or cluster deployment has occurred. Earlier agent-run hosted attempts were blocked. Subsequent user PowerShell probes passed hosted discovery and authenticated Groq sample tool calling; see the M0 report.

## Assignment and client clarification

The DOCX requires admin/member roles, invitations, personal keys, and audit attribution. It does not prescribe Google sign-in or local login. Local accounts are the selected implementation approach.

The user story says an MCP client “such as Claude Code or Cursor”; the definition-of-done text explicitly names Claude Code, Cursor, or MCP Inspector. Codex is the selected AI client based on its documented Streamable HTTP/bearer support. This is a technical suitability inference, not explicit naming of Codex in the assignment. Include Inspector evidence as well. Actual Codex interoperability has not been tested yet.

[Official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) documents Streamable HTTP, bearer authentication, and bearer_token_env_var. Configure only the gateway and the member key in the isolated demo client, not the upstream credentials.

## M0 design approval

On 14 October 2026 the user replied “approved” to the M0 design and defaults: invitation 24h, login 8h, members own audit/admin all, discovery3s/tool10s, chat8 rounds, and the linked contracts/security proposals. This authorizes M0 executable experiments and their checks only, not M1 or application integration. Experimental runtime choices are recorded with evidence; no runtime pass is inferred from approval.

## M0 progression and M1 specification authorization

On 14 October 2026, after the assistant proposed accepting M0 with deferred Inspector/Codex checks, the user said: “let us proceed forward with spec m1 now.” Recorded as acceptance for progression with those exceptions and authorization to draft/review M1 specification only. Clean fresh online dependency installation also remains unverified; M9 clean-setup evidence must address reproducibility. See docs/modules/m1-spec.md.

## M1 specification approval and design request

On 14 October 2026 the user approved M1 recommendations: one server node, bundled Traefik, local .test hostnames with loopback mapping, port 80 with 8080 fallback, local-path storage, and one shared Helm chart with a temporary opt-in test workload. The user then replied “yes go ahead” to preparing the detailed M1 design. This authorizes design work, not M1 implementation or M2. Proposed exact pins/settings are in docs/modules/m1-design.md for the design review gate.

## M1 implementation approval

The user said “GO AHEAD AND IMPLEMENT” after reviewing the M1 design summary. This authorizes the approved M1 files, portable tool installation, cluster setup, implementation review, and the listed acceptance checks. Elevated hosts-file editing remains user-run. M2 remains a separate module approval gate.

## M1 runtime status after permission change

User changed command approval settings, requested Docker retry (successful outside sandbox), and said “yes resume.” This continued previously approved M1 setup/checks. Docker/portabletools/cluster now work through approved escalated commands; standard sandbox runner still fails. Seven live checks pass; user-run hostname/browser and cleanup remain pending. No host changes performed or M2 acceptance inferred. See docs/evidence/m1/report.md.

## M1 verification closure

User supplied the requested page screenshot, now saved as docs/evidence/m1/foundation-browser.png. All nine checks have passing observed evidence after final cleanup correction. Temporary foundation workload and recorded checking Jobs/Pods removed; original Bound PVC and Ready cluster retained. M1 is ready for user module acceptance. This does not authorize M2 implementation or imply full-project/VPS acceptance.

## M1 progression acceptance and parallel M2/M3 specifications

On 15 October 2026 user requested “prepare m2 spec and m3 spec, we will use subagents to work in parallel so we can complete it faster.” Recorded as acceptance to progress from completed M1 into these specification phases, and explicit authorization for parallel subagent planning. Separate agents own the M2 and M3 specification files; a reviewer checks both. Implementation and designs retain their approval gates. Real shop-to-MCP wiring stays M10. Shared HTTP/HTTPS REST authentication is flagged for joint design/user selection; no credential/transport choice silently made.

## M2/M3 approval, REST authentication, and document format

On 15 October 2026 the user explicitly approved both M2 and M3 specifications and their implementation. After discussing section 3 of the earlier coordination plan, the user selected OAuth 1.0a signed requests for the local HTTP WooCommerce REST connection. This is server-to-shop authentication using a consumer key/secret, separate from the optional browser-login OAuth feature on the gateway. HTTP does not encrypt the shop data in transit. No change to gateway API-key authentication is authorized by this choice.

The user then requested defining the M2 and M3 designs before implementation. Detailed design review remains the next gate; the earlier implementation authorization is retained, rather than treated as withdrawn. Each module's design will live inside its existing specification: docs/modules/m2-spec.md and docs/modules/m3-spec.md. The user requested just these two specs and no additional parallel-plan specification documents going forward. Existing coordination documents are historical; the current module specs own their design and shared settings. Real M2/M3 connection remains M10.

The user reported applying the workspace-runner fallback and restarting. A fresh standard exec_command Get-Location check exited 0 in the correct workspace. This verifies shell launch recovery; it does not by itself verify Docker, cluster access, or module functionality.

## M2/M3 detailed design approval and implementation

After receiving links to both detailed designs and their plain-language summaries, the user said “PLEASE IMPLEMENT”. This approves the designs in M2 section 10 and M3 section 11 and authorizes their implementation, independent review and planned module checks. Separate module agents own separate files; the main agent owns shared Helm settings and coordinates deployments. Real shop-to-MCP wiring remains M10. Module acceptance and later-module gates remain separate.

## M2/M3 progression and M4/M5 specification request

On 16 October 2026, after receiving the completed M2/M3 verification results, the user said “now let us proceed with spec 4 and spec 5”. Recorded as acceptance to progress from the independently checked M2/M3 scope into M4/M5 specification work. This is not a claim of full-system or M10 acceptance and does not authorize M4/M5 implementation. Create only docs/modules/m4-spec.md and docs/modules/m5-spec.md; keep later detailed designs within those files and do not create another parallel-plan spec. M4 retains Inventory plus hosted Microsoft Learn. M5 retains the approved local-account, invitation/session, personal-key, registry and audit contracts.

## M4/M5 implementation request and concrete design review

On 16 October 2026 the user said “go ahead and implement both modules using subagents”. This authorizes implementation of the two specified scopes and their independent checks, with separate module subagents. The concrete designs had not yet been written. Following AGENTS.md and the specifications' explicit design-review gate, prepare and independently review those designs inside the existing two spec files before application code. Retain the user's implementation authorization; ask only for review of the newly concrete design choices, particularly M5 security and recovery behavior. No additional plan/design spec is created. Real gateway/chat/dashboard integration remains M10.

## M4/M5 concrete design approval

After receiving the concrete designs and independent review, the user said “let's proceed to the implementation”. This approves M4 section 11 and M5 section 12 and authorizes implementation, independent review and the specified module checks using subagents. This includes M5's password/session controls, one-worker recovery ownership, scoped credential namespace, and retaining the newly committed configuration if old-Secret retirement fails. The main agent owns shared Helm values; separate agents own module source/tests and isolated check resources. No early gateway/chat/dashboard or real upstream integration is authorized; M10 remains the integration gate.

## M6/M7 specification request

On 17 October 2026 the user requested M6 and M7 specifications for review, followed by the same design and implementation flow. This authorizes drafting and independent specification review only. The request permits progression from the completed M4/M5 checks, without claiming full-system acceptance. Create exactly two module specs; detailed designs will be added inside those files after specification review/approval. M6 owns gateway discovery/routing and M7 owns chat through that gateway; final real-module wiring remains M10. Existing choices and approved contracts remain authoritative. Exact connection/session lifecycle, payload limits, concurrency and provider budgets require the later concrete design review; no new implementation or paid-provider approval is inferred.

## M6/M7 implementation request and pending concrete design review

On 18 October 2026 the user said "go ahead and implement the modules 6 and 7" after receiving their specifications. This approves the specified scopes and authorizes implementation/review/checks once the required concrete-design gate is satisfied. M6 section 10 and M7 section 11 will contain those designs; user approval of the newly concrete choices is still pending. Retain implementation authorization and do not request it again. No new parallel plan, early M10 wiring or paid-provider switch is authorized.

## M6/M7 concrete design approval

On 18 October 2026 user replied "approved, please go ahead and implement" to the concrete designs in M6 section 10 and M7 section 11. This satisfies their design gates and authorizes source implementation, independent review and the planned isolated acceptance checks. Retain gateway-only access and no real-module integration until M10. Do not request implementation permission again for this scope. Provider live checks remain limited to approved free Groq access, with no automatic paid switch.

## M8/M9 implementation request and concrete design review

On 18 October 2026 the user said "go ahead and implement both modules" after the two specifications were delivered. Record specification approval and implementation authorization for M8/M9, subject to their explicit concrete-design review gate. Prepare M8 section 10 and M9 section 8 inside the same two files and independently review them before application/Helm implementation. Do not request implementation permission again after those concrete choices are approved. Final runtime orchestration remains M10; the unrun M7 real-provider criterion is not silently accepted.

## M8/M9 concrete design approval

On 18 October 2026 user replied "implement" to the concrete M8 section 10 and M9 section 8 designs. Their review gates are satisfied, and implementation plus independent scoped checks are authorized. M8 isolated browser/static Kubernetes checks and M9 static release/package checks remain distinct from M10 integration. No local certificate trust installation, provider call or VPS deployment is implied.


## M10 design and implementation authorization

User said "design and implement" after reviewing the M10 specification and then resumed implementation on 20 October after usage limits. Record specification/progression approval with documented earlier verification exceptions retained, and authorization for routine in-scope backend composition, tests and packaging after independent concrete-design review. Section12 design review found no blocking defect. Deployment target, machine certificate/hosts trust changes and current free-provider account confirmation remain unanswered specific decisions; no provider call, full release apply or retained-data transition is inferred. This is not final acceptance of M8/M9 runtime integration or the complete system.


## 20 October 2026 - live M10 inputs and fresh target authorized

User confirmed Groq is currently on the free plan and authorized HTTPS. The user first questioned a second shop and then allowed existing-shop testing with no existing data; their latest explicit instruction was "make a new shop for testing, that's fine". Follow the latest choice: release/application namespace urumi-m10, dynamic Secret namespace urumi-m10-secrets, fresh database/content/platform claims and separate credentials, hosts shop-m10.urumi.test and dashboard-m10.urumi.test. Keep the original urumi shop intact. Authorization covers the planned real checks and synthetic products/orders/faults/recovery, not VPS purchase/publication/upload/submission.

HTTPS setup uses a constrained .urumi.test development CA trusted only in CurrentUser Root; its signing key remains in ACL-restricted ignored operator storage. User-approved elevation added only the two test hostname mappings. Existing k3d load balancer was updated in place to expose loopback443; server node and old shop disks were not recreated. Windows chain and actual normal HTTPS request passed. No verification bypass. The real Groq probe passed with two rounds; no paid fallback.
