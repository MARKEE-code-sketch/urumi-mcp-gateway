# Final demonstration checklist

This guide describes the repeatable demonstration. Current observed results are in the [M10 acceptance ledger](evidence/m10/acceptance-results.json); a checkbox here is not a test result. Record actual results against [M10 acceptance criteria](modules/m10-spec.md#8-acceptance-checks-and-required-evidence). Do not use the M8 fixture as the application.

## Prepare an explicit target

Record the accepted Kubernetes context, application namespace, Helm release, separate credential namespace, shop URL and dashboard HTTPS URL. Check hostname resolution and certificate trust in the browser and the chosen clients. Review source/image identities, all three persistent claims, readiness, resource limits and recovery point. Keep credentials and backups private. Obtain current Groq free-plan confirmation before provider calls. Confirm Codex and MCP Inspector availability without installing or charging for replacements silently.

The user approved the fresh `urumi-m10` target, HTTPS setup and free-plan Groq use. It is separate from the retained `urumi` shop. No command here authorizes upgrading the old release or deleting disks. Before and after live checks, record retained resource identities and verify that they remain intact.

Repository-root PowerShell, after the pinned environment exists:

```powershell
./scripts/demo.ps1 -Step Guide
# Replace every placeholder with the accepted target; no default target is assumed.
./scripts/demo.ps1 -Step Inventory -Context REVIEWED_CONTEXT -Kubeconfig REVIEWED_KUBECONFIG -Namespace REVIEWED_NAMESPACE -Release REVIEWED_RELEASE
```

The inventory step only reads selected metadata from an owned `urumi-m10` namespace labelled `urumi.dev/module=m10`. It does not register upstreams, create accounts, call tools, inspect Secret values, create test orders or record video. A live installation procedure must first be reviewed and exercised separately.

## Record the required two-user flow

1. **D1 / C10-04:** In the actual storefront, add a labelled test product to the cart and complete cash-on-delivery checkout using synthetic customer details. Show the same order ID in Woo admin. Do not capture real customer information.
2. **D2-D3 / C10-05:** Sign in as admin A. Show the built-in Woo entry and the configured Inventory and Microsoft Learn servers. Ask real chat to create the approved exact product name/price. Show its actual tool activity, public product and matching audit. Create the manual order, ask about today's orders and verify inclusion using Asia/Kolkata date boundaries.
3. **D4 / C10-06:** Invite member B through the real dashboard; redeem the invitation and issue B's own key. Configure the selected external AI client with only the gateway HTTPS URL and B's key. Mask the key; use placeholders in saved configuration. Show all three upstream catalogs and an actual tool-backed answer to today's orders. Inspector protocol operations alone do not prove the natural-language answer.
4. **D5 / C10-07:** First check that disposable shop SKU `DEMO-001` does not conflict with an existing real product. Prepare it explicitly. Ask: "Find SKU DEMO-001 in our shop, tell me its price, and check its warehouse availability." Show actual Woo plus Inventory calls attributed to B. Explain that Inventory is sample warehouse data. Separately demonstrate a discovered Microsoft Learn call through the gateway with a matching audit.
5. **D6 / C10-08:** Keep B's MCP connection open. Revoke its selected key as admin, then make the next request on that connection. Show denial and no upstream execution. A second active control key must still work. Do not save any raw key.
6. **D7 / C10-09:** Record the selected upstream's prior enabled state. Disable it, refresh chat and client catalogs, demonstrate that its former tool name is rejected and a healthy peer still works. Restore its prior enabled state and verify recovery. Record any client refresh/reconnect requirement.
7. **D8 / C10-10:** Root records the owned upstream Deployment/Pod and replica count before a controlled failure. Delete only that Pod; if replacement is too fast to observe failure, use the separately reviewed scale-to-zero method. Show Unreachable, a healthy server's successful call and restored readiness/replicas afterward. Never delete the cluster or disks as a retry.
8. **D9 / C10-11:** Show attributable user/server/tool/UTC timestamp/duration/outcome and safe audit identifiers for every attempt, including denial/error/timeout/unknown. Demonstrate that B cannot use admin APIs or inspect another member's keys/audits. Unknown callers must not receive invented identities.
9. **D10 / C10-12:** Record product/order/content IDs and platform account/key/revocation/registry/audit state, then separately restart the reviewed store/database and backend/PostgreSQL workloads. Verify the same data and PVC identities afterward. Do not stop all components at once or claim restart persistence proves backup restore.

## Complete the remaining acceptance evidence

Prove all five Woo tools against disposable data, including a labelled test order's status before/after. Verify real CSRF/Origin and ownership boundaries, actual gateway-only network access and scoped Secret RBAC with explicitly owned diagnostic resources. Observe the real provider loop after confirmation. Reproduce installation from clean source with private inputs, restore one consistent private backup into a separate isolated target, and demonstrate the production-shaped TLS/OAuth read/write path. Local profile rendering does not prove those flows or a VPS deployment.

For each criterion record PASS, FAIL, BLOCKED or NOT RUN, exact command/target/time, safe identifiers, evidence path and limitation. Preserve uncertainty after interrupted writes; do not replay them automatically. Restore controlled server/replica changes and remove only owned temporary diagnostic resources.

## Private handoff and video outline

Suggested order: architecture and trust boundaries; healthy installation; D1-D10; security/failure/persistence evidence; clean-install/restore/production notes; limits and tradeoffs. Prepare the source/chart/docs/evidence index and check for credentials, invitation fragments, cookies, raw provider payloads, dumps and machine-specific configuration. Save only redacted screenshots; disable automatic unmasked browser traces/HAR/video capture. The final review must cover all eighteen acceptance criteria and earlier required gaps.

Recording, repository upload, publication and form submission require a later explicit instruction. Keep the assignment private. No optional multi-store work or live VPS is necessary for the mandatory core.
