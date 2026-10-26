# Manual external-client checks K2-K4

Observed24October2026. Target: `https://dashboard-m10.urumi.test/mcp`, Streamable HTTP with normal local-CA certificate verification. The user supplied a personal gateway key and requested K2-K4, then preparation for a user-controlled K5 revocation.

## Results

| Check | Result | Observed evidence |
|---|---|---|
| K2 | Succeeded | Member-owned key; 9 actual tools across WooCommerce, Inventory and Learn, all 3 enabled servers. External client receives only the gateway address/key and local TLS trust, no upstream credentials/admin login. |
| K3 | Succeeded | `woocommerce__list_orders` over24October00:00 through23:59:59.999999 Asia/Kolkata returned no orders. Separate `woocommerce__get_order` retrieved existing21. `woocommerce__list_products` found DEMO-001 at INR499.00. `inventory__lookup_sku` returned sample warehouse Bengaluru12. Four success audits identify member B `b22d3f72-c947-4101-9068-6d7024494aa5`, the selected key, API-key authentication and corresponding public/upstream tools. |
| K4 | Succeeded | Separate HTTP clients sent real MCP initialize/tools-call messages with missing/wrong credentials: all4 requests returned401 / UNAUTHENTICATED. The2 tool-call denials have audit records with no invented user and no upstream/server dispatch. |
| K5 | Succeeded | Original user's revoked key confirmed HTTP401 / KEY_REVOKED. A complete controlled repeat kept two newly issued B clients open, revoked only the test-selected key, observed its next-call denial without upstream dispatch, and observed the same control client's next call succeed. Exact audits identify B; both temporary keys revoked after testing. B browser/chat survival is user-confirmed, not independently browser-retested in this continuation. [Complete repeat evidence](k5-verification.json). |

All structured safe tool results, arguments, exact audit/request IDs and negative-response codes are recorded in [results.json](results.json). No raw keys, password, cookies or upstream credentials appear in evidence. The selected key's public identifier/prefix is metadata, not its authentication secret.

## Method and limitations

The assistant chose tools to answer the Q4/Q11 requests and used the installed MCP SDK as a real external protocol client. There was no separate paid/provider LLM call, no checkout and no shop write. The member B for this test is the actual owner of the user's supplied key, rather than assuming the older seeded member account. A separate operator dashboard session read metadata/audits and issued only the explicitly planned control key; the external client itself did not receive its login credentials.

Today had no orders, so the result correctly separates today's empty interval from the pre-existing disposable order21. This test does not establish that an order placed on a prior day is a today's order. It is not a new complete M10 acceptance or deployment test.

Repository-root PowerShell command:

```powershell
.\.venv\Scripts\python.exe scripts\m10\manual-external-client.py
```

The selected key was entered through a hidden password prompt. The process printed safe results and waited for an explicit `CHECK` command after the user's revocation; it did not revoke the selected key automatically. On CHECK, the server rejected the original session's tool call. The SDK's transport task group then shut down with an ExceptionGroup, interrupting the remaining scripted checks; this was distinguished from the application's correct rejection using the actual audit record. A separate operator check verified an already-existing control credential still succeeds, without saving it to evidence. This initial sequence did not establish post-revocation execution for the originally issued `ugw_acf44edd` control, and that limitation is retained in results.json.

## Complete K5 repeat

The user then requested an actual confirming client test and confirmed B's browser/chat remains usable. Ran:

```powershell
.\.venv\Scripts\python.exe scripts\m10\verify-k5.py
```

The helper confirmed the user's original key returns401 / KEY_REVOKED. It issued two disposable keys for the same member B, connected two real Streamable HTTP SDK clients, and successfully called Inventory from both. With both ClientSessions still open, it revoked only its new test-selected key. That same selected client's next Inventory call was denied and audited with no upstream dispatch. The same control ClientSession then successfully returned `DEMO-001`, Bengaluru12. Its two success audits bracket the selected denial; all four records identify B/API-key authentication. The selected client's expected transport shutdown was isolated to its own task, allowing the independent control to be tested. Both disposable keys were revoked during cleanup. No shop data, other existing keys or provider calls were changed.

[k5-verification.json](k5-verification.json) preserves the exact original-key HTTP response code/request ID, selected/control IDs, same-session observations, audit IDs and cleanup results. Its browser/chat field explicitly identifies the evidence as the user's confirmation rather than a new operator browser test. This complete controlled repeat closes the earlier external-client/control gap, so K5 is now Succeeded; it does not retroactively claim the earlier `ugw_acf44edd` key was retested.
