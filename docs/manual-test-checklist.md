# Manual testing checklist — Urumi gateway

**Prepared:** 21 October 2026. **Purpose:** Your own repeatable checks of the completed app.

This checklist was prepared from the current implementation, assignment requirements, and demo guide. Rows explicitly marked **Succeeded** record observed checks with linked evidence; other rows remain instructions, not newly executed results. Record your own PASS / FAIL / BLOCKED for each remaining check.

## 0. Start the existing server

1. Open **Docker Desktop** and wait until its engine is running with Linux containers.
2. Open **PowerShell** and run:

```powershell
cd C:\Users\mrina\Downloads\URUMI_Assignment
./.tools/m1/k3d.exe cluster start urumi
```

This starts the existing Kubernetes cluster. Kubernetes brings up the already installed shop, dashboard, gateway, and supporting services; you do not start FastAPI or React separately.

3. Give the applications time to become ready. Check their status with:

```powershell
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi-m10 get pods
```

The application Pods should show `Running` with all containers ready, for example `1/1`. Then open:

If the backend remains `0/1` after a Docker/cluster restart, compare the current Kubernetes API address with the backend's exact network allowlist before registering a credential-backed server. Local container addresses can change. See [API-address troubleshooting](operations.md#local-kubernetes-api-address-changes); do not broaden the allowlist or repeatedly submit a failed registration.

- **Dashboard:** https://dashboard-m10.urumi.test
- **Shop:** http://shop-m10.urumi.test/shop/

If the cluster is already running, open those URLs and use the status command if needed. If startup reports that the cluster does not exist, share the error before creating or reinstalling anything. The commands above resume the existing installation; they were documented here, not executed as part of this checklist update.

## Before starting

| Item | Use this |
|---|---|
| Dashboard | https://dashboard-m10.urumi.test |
| Storefront | http://shop-m10.urumi.test/shop/ |
| Shop admin | http://shop-m10.urumi.test/wp-admin/ |
| External MCP gateway | https://dashboard-m10.urumi.test/mcp |
| Accounts | A = dashboard admin; B = member in a separate browser profile/private window. WordPress admin login is separate. |
| Test data | Use fictional checkout details and disposable products/orders. |
| Fresh suffix | Replace `RUN_TAG` everywhere with a new short lowercase value, for example `20261021a`. Use a different value for another run. |
| Order placeholder | Replace `ORDER_ID` with the actual ID of the disposable order you create below. Do not send the placeholder literally. |

These are the full-demo addresses documented in README, not the older `shop.urumi.test` installation. Do not reset or delete either installation to start these checks. Use your existing private credentials; keep passwords, invitation links, and complete API keys out of screenshots.

**Three things that are expected behavior:**

- Each chat message is independent. Include the product name, SKU, or order ID again; do not rely on “that product” in the next message. Chat history is not saved across visits.
- Members can use the shared shop tools, including writes. Members cannot administer servers/members or access another person's keys/audit records.
- Inventory is fixed sample warehouse data, not live shop stock. Revoking an external key does not log the person out of the browser.

## 1. Login and dashboard

| ID | What to do | Expected result |
|---|---|---|
| L1 | Open the dashboard without logging in. | Login page; no private server/account data is displayed. HTTPS opens without a certificate warning. |
| L2 | Enter the correct email with a wrong password of valid length. | Clear login failure; no signed-in access. |
| L3 | Log in as A with the correct password. | Servers page opens; header shows A and admin role. |
| L4 | Refresh the page, then navigate through Servers, Members, Keys, Audit, and Chat. | Session remains usable; pages load without errors. |
| L5 | At the end of a session, click Logout, then reload or use the Back button. | Private content is cleared and protected requests require login again. |

## 2. Servers and tool discovery

| ID | What to do | Expected result |
|---|---|---|
| S1 | As A, open Servers and click Refresh servers. | WooCommerce, Inventory, and Microsoft Learn are registered. Enabled reachable servers show Connected. |
| S2 | Click View tools on WooCommerce. | Five tools: list_products, create_product, list_orders, get_order, update_order_status. Public names may include the `woocommerce__` prefix. |
| S3 | View Inventory and Microsoft Learn tools. | Inventory has lookup_sku; Learn shows its actually discovered tools. The tool schemas/descriptions display. |
| S4 | As A, register a disposable alias for `https://learn.microsoft.com/api/mcp`, with a unique slug such as `qa-learn-RUN_TAG` in lowercase and Authentication None. Refresh tools, edit its display name, then remove only this alias. | Add/edit/discover/remove work. Its tools have a distinct prefix; removing the alias leaves the original three servers intact. |

If a preview says **Stale**, it is a previously discovered list, not proof that the server is currently reachable. Refresh and check status.

Refresh servers reloads the backend's recorded status; it does not synchronously ping every server. Allow the background discovery/status check to finish, then refresh again before deciding a new registration failed.

## 3. Storefront checkout

| ID | What to do | Expected result |
|---|---|---|
| W1 | Open the storefront and a product page. | Published products, INR prices, and any uploaded image display. |
| W2 | Add a product to the cart. Check quantity and total. Complete checkout with fictional details and cash on delivery. | An order confirmation appears. Record the new order ID and total; no real payment is required. |
| W3 | Log into WooCommerce admin and open that order. | Same order ID, product, quantity, total, and COD payment method. Do not assume COD orders are already completed. |

## 4. Chat — exact prompts to use

Log into the dashboard as A and open **Chat**. For every tool-backed answer, inspect **Actual tool attempts** and later match it to **Audit**. A convincing sentence alone is not proof.

| ID | Copy this prompt | What to check |
|---|---|---|
| Q1 | `Use the WooCommerce tools to list products in our shop, including their IDs, SKUs and prices in INR.` | A successful list_products call. Compare several IDs/prices with the real shop. |
| Q2 | `Create exactly one published simple product named QA Blue Mug RUN_TAG, with SKU QA-MUG-RUN_TAG and regular price "299.00" INR. Call the creation tool once; do not retry a write. Return its product ID and price.` | create_product succeeds once. The exact name/SKU and INR 299.00 appear in Woo admin and the public storefront. Record its product ID. |
| Q3 | `Use the WooCommerce tool to find the product with exact SKU QA-MUG-RUN_TAG. Return its ID, name and price.` | Same product ID as Q2; exactly the matching product, not an invented result. |
| Q4 | First manually buy the Q2 product in the storefront. Then ask: `Use the WooCommerce tools to show all orders created today in Asia/Kolkata, including order IDs, statuses, totals and items.` | The order you just placed is included. Check its ID/total in Woo admin. Exact date arguments are not exposed in the current chat UI; operator check T6 verifies boundaries and multiple pages. |
| Q5 | `Use the WooCommerce get_order tool to show order ORDER_ID, including its status, total and line items.` | Exact disposable order returned, matching Woo admin. No customer address, email, phone, or payment secrets in the tool result. |
| Q6 | `Change only the status of disposable test order ORDER_ID to completed. Call the update tool once and return its updated status.` | update_order_status succeeds; Woo admin shows completed. Product quantities/prices are not changed by the tool request. |
| Q7 | `Use Inventory to check sample warehouse availability for SKU DEMO-001.` | lookup_sku; Bengaluru, quantity 12. Answer identifies sample warehouse information. |
| Q8 | `Use Inventory to check sample warehouse availability for SKU ZERO-001.` | Known SKU with Bengaluru quantity 0. Zero stock is not an unknown SKU. |
| Q9 | `Use Inventory to check sample warehouse availability for SKU QA-NOT-FOUND-RUN_TAG.` | found=false and no warehouses; no invented availability. |
| Q10 | `Use Microsoft Learn to find official documentation explaining Kubernetes Pods. Summarise the result and provide the source links.` | An actual Learn tool call and relevant documentation results/links, not only the model's remembered explanation. |
| Q11 | `Find SKU DEMO-001 in our WooCommerce shop, tell me its current price, and check its warehouse availability using Inventory.` | Actual calls to both WooCommerce and Inventory. Shop price matches the real product; sample warehouse is Bengaluru, 12. |

For Q11, first confirm the shop contains SKU DEMO-001. The standard seed creates it, but do not overwrite an existing product to satisfy the test. If absent, prepare a labelled test product deliberately. Buying a shop product does not reduce the fixed Inventory sample count.

Do not automatically resend Q2/Q6 after a timeout or interrupted page. First inspect the shop and audit records: a write may already have happened.

## 5. Invitations and member permissions

| ID | What to do | Expected result |
|---|---|---|
| U1 | As A, open Members, enter a fresh test email, and click Create invitation. | A private one-use link appears with expiry. Email delivery is not required; share the link manually. |
| U2 | Open that link in B's separate browser profile/private window. Try a password shorter than 12 characters, then a valid private password. | Short password rejected; valid password creates B's member account. Log into B's account. |
| U3 | Try redeeming the original invitation link again. | Reuse rejected; no second account created. |
| U4 | As B, use Servers/View tools, Chat, Keys and Audit. Repeat Q1 and Q7. | Shared tools work. Members management and server add/edit/disable/remove controls are unavailable. |
| U5 | As B, directly open `/members` on the dashboard. | Access denied, not a members list. Also test actual admin API denial in section 10; hiding a button alone is insufficient. |
| U6 | As B, inspect Audit and own key management. | Only B's permitted records/keys. B must not receive A's key metadata or audit history. |

## 6. API keys and an external MCP client

| ID | What to do | Expected result | Recorded result |
|---|---|---|---|
| K1 | As B, open Keys, enter label `Manual QA RUN_TAG`, and issue a key. Save it privately. Dismiss the one-time value and refresh. | Full value appears only at creation; later views show metadata/prefix and Active status, not the full key. | Not rerun in this check. |
| K2 | Configure an external MCP client with **only** the gateway URL above and B's personal key as bearer authentication. | Tool discovery succeeds for all enabled servers. No upstream URLs, Woo keys, Learn keys, or admin login are required. | **Succeeded — 24 October 2026.** External Python MCP client authenticated with B's supplied personal key; verified TLS and discovered 9 tools across all 3 enabled servers. No upstream credentials or browser login were given to that client. [Evidence](evidence/manual-client/20261024-095606/results.json). |
| K3 | In that external client repeat the prompt text from Q4 and Q11, using the order already created; another checkout is unnecessary. | Actual order lookup and two-server answer succeed. Audit attributes calls to B, not A. | **Succeeded — 24 October 2026.** Today's Asia/Kolkata interval returned 0 orders; separately retrieved existing order21. DEMO-001: INR499.00; sample Inventory: Bengaluru12. All4 actual calls succeeded and their audit records identify member B and this API key. No new checkout or shop write. [Evidence](evidence/manual-client/20261024-095606/results.json). |
| K4 | Try a missing/wrong key in a separate client configuration. | Authentication rejected; no tool execution. Opening `/mcp` as a normal browser page is not a valid MCP test. | **Succeeded — 24 October 2026.** Missing and wrong keys each received HTTP401 / UNAUTHENTICATED for MCP initialize and tools/call. Both attempted tool calls have denied audits with no user attribution or upstream dispatch. [Evidence](evidence/manual-client/20261024-095606/results.json). |
| K5 | Issue a second control key. Keep the first client's connection open; revoke its selected key as A or B, then make its next tool call. | Revoked key rejected, including an already-open client. The second key still works. B's browser session/chat remains usable. Already-dispatched work may finish. | **Succeeded — 24 October 2026.** User's revoked key returns HTTP401 / KEY_REVOKED. A complete controlled repeat with two disposable B keys kept both SDK clients open: revoking the test-selected key denied its next call, while the same control session still returned Bengaluru12. Exact success/denial audits identify B; both disposable keys revoked afterward. B browser/chat usability was confirmed by the user, not separately retested by the operator. [K5 evidence](evidence/manual-client/20261024-095606/k5-verification.json). |

Run K5 after the other tests that use that key. Use the control key for any remaining external-client checks.

The24October run used this assistant as the reasoning client through the local Python MCP SDK. It made real gateway calls without a separate LLM/provider call. An operator's separate dashboard session read server/key metadata and audit records to verify attribution; those credentials were not passed to the external MCP client. Existing order21 was not described as a today's order. Supplied/newly issued raw keys were held only in the live client's memory and are excluded from evidence files; that process closed after the revoked-key denial. The later independent control used an existing private operator test key. See [run report](evidence/manual-client/20261024-095606/report.md).

### K2 connection settings

Enter these in your **MCP client's server configuration**, not the browser address bar:

| Setting | Value |
|---|---|
| Transport | Streamable HTTP |
| URL | `https://dashboard-m10.urumi.test/mcp` — use this exact path, without a trailing slash |
| Authentication | Bearer token: B's full personal gateway key, entered privately |

If your client asks for a custom header instead of a bearer-token field, use header name `Authorization` and value `Bearer YOUR_KEY`; replace YOUR_KEY privately. A bearer-token field normally expects just the key, without typing Bearer again. Dashboard login alone does not authenticate this external-client endpoint.

A read-only check on 23 October returned HTTP 401 / UNAUTHENTICATED from the exact URL when no key was sent, confirming the route was present at that time. A browser page is not an MCP initialize/list/call check. If the MCP client itself returns NOT_FOUND, first compare its full URL/path with the exact URL above, then record the error without revealing the key.

## 7. Audit records

| ID | What to do | Expected result |
|---|---|---|
| A1 | After Q1, Q2 and Q6, open Audit as A and click Refresh audit. Match the chat's audit/request IDs. | Correct user, server, original/public tool, UTC timestamp, duration and outcome for each tool attempt. |
| A2 | Repeat after B's external-client calls and revoked-key denial. | B attributed correctly when identifiable. Bad unknown credentials must not invent an identity. |
| A3 | Filter by outcome and server UUID; as admin also filter by user UUID. Check pagination. | Only matching records; pages work without showing another member's data to B. |
| A4 | Compare chat steps with audit rows. | One record per actual tool attempt, not necessarily one per chat message. A two-server answer normally requires several records. |

The order view uses shop time; audit timestamps display UTC. Different displayed hours do not by themselves mean attribution/date handling is wrong.

## 8. Disabled or unavailable servers

| ID | What to do | Expected result |
|---|---|---|
| F1 | As A, note Inventory's current enabled state, disable it, and refresh Servers. Refresh/reconnect the external client and send a new chat message. | Status Disabled; its tools disappear from fresh gateway/chat catalogs. An old preview must not be treated as current availability. |
| F2 | While disabled, ask Q7 and directly call the previously listed Inventory tool from the external client. Also ask Q1. | No successful Inventory execution or fabricated warehouse result. A direct stale tool call is rejected. WooCommerce still works. |
| F3 | Restore Inventory's previous enabled state and refresh discovery. Repeat Q7. | Tools return and the real sample lookup succeeds again. |
| F4 | Operator-assisted: delete only the owned Inventory Pod in the `urumi-m10` namespace, observe replacement and test Q1/Q7. | Remaining servers work. Inventory becomes Unreachable during an observable outage, then recovers. If restart is too fast, use the reviewed sustained-outage method below. **Succeeded — 25 October2026:** owned Pod deleted with UID precondition; actual Unreachable and safe Inventory failure observed while Woo succeeded; different replacement Ready/Connected and Bengaluru12 recovered. Real MCP equivalents of Q1/Q7; no new chat/provider call. [Evidence](evidence/manual-faults/20261025-152820/report.md). |
| F5 | Operator-assisted: temporarily scale only the owned Inventory Deployment to zero, then restore its **recorded** original replica count. | Unreachable and safe failure while down; Woo still works; restored Inventory becomes Ready/Connected and Q7 succeeds. **Succeeded — 25 October2026:** Inventory replicas **1 → 0 → 1**; Unreachable/safe failure at zero, Woo call succeeded, then new Inventory Pod Ready/Connected and Bengaluru12 returned. Other six Pods, workload specifications, three PVCs and registry configuration preserved. [Evidence](evidence/manual-faults/20261025-152820/report.md). |

Use [the controlled demo procedure](demo-checklist.md) and [operations](operations.md) for F4/F5. The dated F4/F5 results above record an executed run; unmarked instructions do not imply execution. Do not delete the cluster, disks, namespaces, or the original shop. Restore every changed server/replica state afterward.

## 9. Direct tool validation — use MCP Inspector or another active MCP client

Chat may correct bad inputs before calling a tool. Use a **direct gateway tool call** to prove backend validation. Select the actual discovered prefixed tool name; send these JSON arguments.

| Tool / arguments | Expected result |
|---|---|
| list_products: `{"page":1,"per_page":1}`; follow later pages | Small pages work, final has_more=false. Empty result pages are not fabricated products. |
| get_order: `{"order_id":0}` and `{"order_id":"abc"}` | Invalid argument rejected before a shop REST request. |
| get_order: a positive order ID confirmed absent from the test shop | Safe order-not-found error. |
| create_product: `{"name":"QA Invalid","regular_price":"-1.00"}` | Rejected; no product created. |
| create_product: `{"name":"QA Invalid","regular_price":299.00}` | Rejected: price must be a decimal string. |
| create_product: Q2's existing SKU with otherwise valid fields | Clear duplicate-SKU error; existing product unchanged. |
| update_order_status: real disposable order ID and `"status":"not-a-status"` | Rejected; order status unchanged. |
| list_orders: `{"created_from":"2026-10-21T12:00:00"}` | Missing timezone rejected. Also test reversed start/end dates. |

For every failure, check the safe error and appropriate audit record; compare shop state after invalid write attempts. Use an explicitly absent ID, not a guess that could refer to a real order.

## 10. Technical checks to finish with an operator

These require API/cluster inspection or controlled fixtures. They complete coverage that clicking around cannot prove.

| ID | Check | Expected result |
|---|---|---|
| T1 | Send an admin API request as B; request A's key/audit data directly; submit a state-changing browser request with missing/wrong CSRF or untrusted Origin. | Backend denies access even if UI restrictions are bypassed. |
| T2 | Inspect stored personal API keys and password records without exposing values. Check upstream credentials in Secret references and browser responses. | Personal keys/passwords hashed; upstream/provider secrets server-side; client key never passed upstream. |
| T3 | From a labelled permitted gateway caller and an unrelated test Pod, try the Woo MCP connection; inspect Service/Ingress and Secret RBAC. | Gateway path allowed, unrelated Pod denied; no public Woo MCP/database route; backend Secret permissions limited to intended scope. |
| T4 | Use controlled servers to test bearer/custom-header auth, duplicate tool names, malformed replies, and a slow server. | Correct server routing, safe bounded failure, no credential leak; healthy peers remain usable. Learn alone cannot prove API-key auth. |
| T5 | Register a blocked destination such as loopback/cloud metadata or an unapproved internal URL using the admin API. Test redirects/DNS policy using controlled fixtures. | URL policy rejects unsafe destinations; no fetch to those destinations. Do not relax allowlists to pass a test. |
| T6 | Test before/exactly-at/after IST midnight, inclusive date bounds, multi-page orders and a provider/tool timeout. | Correct interval/results; limits/partial answers and uncertain writes reported honestly; no silent write retry or paid fallback. |
| T7 | Record product/order/image and account/key/revocation/registry/audit identities. Restart WordPress, MariaDB, backend and PostgreSQL separately, waiting for each recovery. | Shop and platform state persist, revoked keys stay revoked, images still load, no duplicate built-in Woo entry. |
| T8 | Review all three Bound PVCs, workload probes/resources and actual image identities; exercise clean-source install and isolated backup restore using the reviewed procedures. Compare local/prod chart renders. | Reproducible release, retained data and restore evidence; same chart with values-only environment differences. A render is not a live VPS deployment. |

A read-only inventory command, from repository-root PowerShell:

```powershell
./scripts/demo.ps1 -Step Inventory -Context k3d-urumi -Kubeconfig .tools/m1/kubeconfig.yaml -Namespace urumi-m10 -Release urumi-m10
```

This reads the guarded M10 target; it does not run the tests above or change shop data. See [operations](operations.md) before any fault/restart/restore action.

## Record your results

| Test ID | PASS / FAIL / BLOCKED | Actual result and evidence |
|---|---|---|
| Example: Q2 | Fill after testing | Product ID, actual tool name/outcome, matching audit ID, safe screenshot. |
| Q10 | **Succeeded — user-reported, 26 October 2026** | User confirmed completing the full manual checklist successfully. No new operator-run prompt/audit trace was supplied for this sign-off. Earlier failed request `348ed464-5f35-445f-9aa5-4180c0adf8a6` and investigation remain in the [historical finding](evidence/manual/q10-learn-chat-limit.md). |

**Manual acceptance, 26 October 2026:** the maintainer reported that all manual checklist testing was completed and everything worked. This records user-reported acceptance; it does not relabel every row as newly executed by the automation or replace earlier evidence. See [acceptance record](evidence/manual-acceptance-20261026.json).

For a quick first pass, do **L1–L4, S1–S3, W1–W3, Q1–Q11, U1–U4, K1–K3 and A1–A2**. Then run the permission, revocation, failure and technical checks. Revoke only test keys and use only disposable test orders for status changes.

**Success means:** observed tool calls match actual shop/warehouse/documentation results and the right person's audit records. Do not mark a test PASS just because chat sounds correct. This checklist does not record video, publish the repository, or submit the assignment.

References within this project: [demo requirements](demo-checklist.md), [M10 acceptance criteria](modules/m10-spec.md#8-acceptance-checks-and-required-evidence), [README target/setup](../README.md), [Inventory sample data](../services/sample_mcps/data/inventory.json).
