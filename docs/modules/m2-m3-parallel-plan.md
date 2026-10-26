# M2 + M3 — parallel work plan

**Status:** Specification coordination for review. No application implementation authorized.  
**Date:** 15 October 2026.  
**Read first:** [M2: the real shop](m2-spec.md) and [M3: the shop tool translator](m3-spec.md).

## 1. The simple idea

**WHAT:** Give one subagent the shop and another the tool translator.

**WHY:** The translator can practise with a pretend shop while the real shop is being installed. Neither agent needs to wait for the other's finished code.

**HOW:** Agree on messages and connection settings first, give each agent separate files, check each module separately, and connect the real pieces in M10.

| Work lane | What it builds/checks | Independent result |
|---|---|---|
| M2 agent | Real WooCommerce shop, MariaDB, disks, checkout and restart checks. | A person can place an order; data and picture survive Pod replacement. |
| M3 agent | Our five MCP tools, using a pretend REST shop. | A real MCP test client can discover/call the tools and see safe success/failure replies. |
| Main agent + reviewer | Shared settings, contract consistency, reviews, evidence and user explanations. | Agents do not overwrite shared files or mistake sample results for real-shop proof. |

## 2. What is already agreed

Python/FastAPI, MariaDB for the shop, k3d, Helm, INR, Asia/Kolkata, and the five M0 tool contracts remain unchanged. M1's nine checks passed; requesting these next specifications is recorded as acceptance to progress to planning.

M2's WordPress/WooCommerce installation is existing shop software. M3 is the custom MCP server we write ourselves. M3 does not rebuild WooCommerce.

## 3. One shared decision before design approval

**How does the translator prove its identity to the shop?** WooCommerce documents different authentication paths for HTTP and HTTPS. A working fake Basic-auth endpoint must not become evidence that the real local shop accepts that method.

| Option | Simple meaning | Tradeoff |
|---|---|---|
| Signed OAuth 1.0a over local HTTP | The client signs each request with the shop credential instead of sending the secret directly. | Fits the current local HTTP plan; requires tested signing, correct canonical shop URL and header handling. It does not encrypt returned shop data. |
| Basic authentication over trusted HTTPS | An encrypted connection carries the shop key/secret in its authentication header. | Simpler client authentication; needs a real TLS route and certificate trust, including for the internal caller. |

**Decision remains open:** compare these in the joint design review, then get your choice before coding the authentication path. No disabled certificate verification, forged HTTPS indicators, or raw credentials in URLs. This shop authentication is separate from optional OAuth login for gateway users.

M2 independently proves its selected REST authentication works on the real shop. M3 tests the same agreed method with fake credentials. The real MCP-to-shop connection still waits for M10.

[Official WooCommerce authentication reference](https://developer.woocommerce.com/docs/apis/rest-api/authentication/) supports these transport/authentication distinctions; it is a technical reference, not an added product requirement.

## 4. Shared handoff agreement

Resolve and record this once during design; both agents use the same result.

| Agreement | M2 supplies | M3 consumes |
|---|---|---|
| Shop address | Public shop hostname, internal connection address, canonical URL and REST path /wp-json/wc/v3. | Configured destination only; tool arguments cannot override it. |
| Shop credential | Dedicated integration identity; Secret name/key names; selected authentication method. | Same configuration shape; fake credential/fixture until M10. |
| Shop settings | INR, Asia/Kolkata, permalink/API configuration, plugin version and demo SKU. | Normalization and UTC date handling from M0 contract. |
| Saved data | Real products, orders and image, with persistence evidence. | Fixture data only during M3; no real-store writes until integration. |
| Exposure | Shop public through Ingress, MariaDB internal. | MCP server internal and restricted to gateway caller; test stand-in is temporary. |

## 5. Rules that make parallel work safe

- Each agent edits only its module-owned files listed in its spec. The main agent alone merges shared chart values/helpers, dependencies shared across modules, contract changes, and cross-module notes.
- Keep contracts read-only unless a proposed change is reviewed and approved. Do not silently change M0 to make one module easier.
- Do not run concurrent Helm upgrades against the same release. The main agent schedules live cluster mutations.
- **Proposed test isolation:** M2 uses the existing urumi application release. M3 uses a separately named disposable namespace/release with fake REST credentials and all real-store resources disabled. Design records exact names and required resources before creation.
- Separate test images, resource names, evidence folders, and cleanup lists. M3 cleanup must not touch M2 disks, products, credentials, or Pods.
- Check laptop capacity before simultaneous cluster tests. Code/spec work can remain parallel even if deployment/check steps need to run in sequence.
- Test stand-ins may use explicit temporary gateway labels in the isolated M3 harness. This proves a policy mechanism, not real gateway authentication. Remove the stand-ins and temporary permissions afterward.

## 6. What happens next

| Stage | Parallel work | Review gate |
|---|---|---|
| Specifications — now | Draft M2 and M3 independently; review their shared boundary. | You approve scopes and proposed defaults. |
| Designs | Settle shared authentication first; design each module's files/resources/checks in parallel. | Independent review and your design approval. |
| Implementation | Separate subagents implement their own approved module files. | Review each module before its checks. |
| Checks | M2 uses real shop journeys; M3 uses fake REST plus real MCP transport. | Each module gets its own observed results and user acceptance. |
| Final connection — M10 | Connect real shop, MCP, gateway and chat. | Prove actual five-tool behavior and the full two-user assignment flow. |

**Current limits:** These documents are plans. No M2/M3 code, tests, Secret creation, or cluster changes happened during specification work. No paid services or optional bonus work are proposed.
