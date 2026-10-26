# M10 independent restart persistence review

**Verdict: PASS for C10-12 / D10 restart persistence scope.** This review covers the owned fresh `urumi-m10` release only; packet-level isolation, backup restore and final user-flow acceptance are separate evidence.

After root confirmed the encrypted consistent backup capture was complete, all browser activity was closed and the restart window was clear, the reviewer ran from workspace-root PowerShell:

```powershell
.tools/m10/venv/Scripts/python.exe scripts/m10/persistence_checks.py --restart-owned-demo
```

The command completed with **PASS, four restarts**. [persistence.json](persistence.json) contains actual command arrays and exit codes, before/after records, Pod UID transitions, recovery timings, unchanged PVC identities and original-shop UID comparisons. The helper refuses other namespaces/contexts, verifies `urumi.dev/module=m10`, checks exact controller name/UID ownership and template instance/component labels, then deletes each exact Pod with an atomic UID precondition. It never deletes storage or changes replica counts.

| Sequential restart | Actual replacement verified | New Pod Ready | Whole release recovery |
|---|---|---|---|
| WordPress | Different Pod UID | 10.82 seconds | All seven components Ready; selected data unchanged |
| MariaDB | Different UID for the same StatefulSet ordinal name | 12.48 seconds | All seven components Ready; selected data unchanged |
| Backend | Different Pod UID | 10.47 seconds | All seven components Ready; selected data unchanged |
| Platform PostgreSQL | Different Pod UID | 3.77 seconds | All seven components Ready; selected data unchanged |

Times measure the replacement wait after the delete command completes; they exclude the separately recorded full-release Ready wait and subsequent data queries. They are not a claim of zero service downtime.

After **each** restart, direct read-only application/database queries verified:

- Product 12 (`Urumi Demo Product`, INR 499.00, SKU `DEMO-001`) and product 18 (`M10 Browser Demo Notebook`, INR 129, SKU `M10-BROWSER-NOTEBOOK`) retained matching IDs/name/price/SKU.
- Order 16 remained completed with total INR 499.00 and product 12; order 19 remained processing with total INR 129.00 and product 18. No customer details were exported.
- Uploaded attachment 13 remained 216 bytes with SHA256 `f1d689bba3617d9af0d58e93b1a909b1f3ff16b2962ed6a27e9a728dc0e8aeb3`.
- Exact IDs/roles for three users; IDs/ownership/revocation flags for eleven API keys; IDs/slugs/enabled flags for three servers; all 46 existing audit records and attribution/outcomes; and the single Woo initialization marker were identical. No raw keys, token/password hashes, sessions, credentials or upstream Secret data were queried/exported.
- The same three PVC UIDs remained Bound: MariaDB data, WordPress content and platform data. All seven original `urumi` Pod/PVC/Service UIDs matched the saved pre-deployment baseline both before and after the run.

All seven components were Ready at the final checked recovery; all four faults were restored by their existing controllers. The root was notified that traffic could resume. This proves preservation of the selected actual test records/content and administrative state through these separate live restarts; it does not prove a complete disaster restore, all possible records, VPS behavior or every M10 acceptance criterion.
