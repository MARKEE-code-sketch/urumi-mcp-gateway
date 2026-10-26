# F4/F5: Inventory failure isolation

Observed **25 October 2026, 15:28–15:29 UTC** against exact context `k3d-urumi`, namespace/release `urumi-m10`. User authorized deleting only the owned Inventory Pod and temporarily scaling only its Deployment to zero, restoring the recorded original replica count.

## Results

| Check | Result | Actual observations |
|---|---|---|
| F4 | **Succeeded** | Deleted only `urumi-m10-inventory-mcp-58bcd997b7-774wj` using an atomic UID precondition. Its next gateway Inventory call failed safely with `UPSTREAM_UNAVAILABLE`; recorded server status became **Unreachable / CONNECTION_FAILED** at15:28:29Z. A concurrent WooCommerce product-list call succeeded. Kubernetes created a different Ready Pod, recorded status returned Connected, and Inventory returned Bengaluru12 again. No sustained-outage fallback was needed for F4. |
| F5 | **Succeeded** | Recorded original replica count **1**, scaled only `urumi-m10-inventory-mcp` to **0**, waited until its Pods were absent, and observed **Unreachable / CONNECTION_FAILED** at15:28:54Z. Inventory failed safely while WooCommerce still succeeded. Restored exactly **1**, observed a new Ready Pod and Connected registry status, then Inventory returned `DEMO-001`, Bengaluru, quantity12. |

Final Inventory Pod: `urumi-m10-inventory-mcp-58bcd997b7-ssvvr`, UID `3febe315-a145-4b25-a2f5-917abc048df4`. Original Deployment UID was retained. All seven workloads ended with one Ready replica.

## Audit proof

Every one of the nine actual gateway calls matched an API-key audit for the existing member test key. No new keys or provider calls were required.

| Stage | Tool outcome | Audit ID |
|---|---|---|
| F4 Pod loss | Inventory error / UPSTREAM_UNAVAILABLE | `637e0edc-f43f-4f78-9f89-fac45450f11d` |
| F4 Pod replacement | WooCommerce success | `a7b1969a-f455-4d03-a704-10e8964ea871` |
| F4 recovered | Inventory success | `8786b7d1-e7fb-4e54-b894-0927e81c5aff` |
| F5 zero replicas | Inventory error / UPSTREAM_UNAVAILABLE | `c3a849f0-4a80-41f8-bda5-0da75c6fdf4e` |
| F5 zero replicas | WooCommerce success | `302e2014-3b8c-4385-b611-559d9e475964` |
| F5 recovered | Inventory success | `dcf56dab-2a52-467b-82a2-c816be7e340e` |

[results.json](results.json) contains all nine call arguments/results, exact request/user/key/server/audit IDs, timestamps, error codes, Pod identities, registry observations and before/after snapshots. The failures returned safe errors rather than fabricated inventory results.

## Scope and restoration checks

- Same namespace identity and all three Bound PVC identities.
- Same specifications and UIDs for all seven workloads, including restored Inventory replica count1.
- Other six Pod identities/readiness unchanged.
- Registry IDs, URLs, authentication modes and enabled settings unchanged.
- Product-list response identical before and after; all shop calls read-only.
- No image, secret, deployment-template, schema, shop-record, user/key or server-registration changes; normal audit records were added. No cluster/namespace/disk deletion.
- Replica restoration was guarded in `finally`, including an uncertain scale response. Recorded final status is Connected and the replacement Pod is Ready.

These checks used a real external Streamable HTTP MCP client for the tool equivalents of **Q1** (`woocommerce__list_products`) and **Q7** (`inventory__lookup_sku`). They did not call a new LLM/chat planner, so this report does not claim new natural-language answer rendering or provider behavior during the outage. No Learn/Context7 availability claim is required; the healthy peer proven here is WooCommerce. No overall M10 acceptance or VPS claim.

## Commands and guards

Successful command, from repository-root PowerShell:

```powershell
.tools\m10\venv\Scripts\python.exe scripts\m10\manual-inventory-faults.py
```

The helper reuses the reviewed `OwnedInventory` guard: exact kubeconfig/context, namespace ownership label, namespace UID, Helm release annotations, Inventory selector labels and Deployment identity. The Pod deletion uses `kubectl delete --raw /api/v1/namespaces/urumi-m10/pods/OWNED_POD -f -` with `DeleteOptions.preconditions.uid`; no other Pod is selected. Scaling uses `kubectl patch deployment urumi-m10-inventory-mcp --type=json` with tests for Deployment UID/resourceVersion/current replicas before replacing replicas. Exact selected/deleted/replacement identifiers are in results.json; do not copy old Pod names into a new run.

The first attempted command used `.venv\Scripts\python.exe`; it failed before any check or mutation because that environment now has MCP2.3.0, whose exports differ from the project's pinned acceptance dependencies. The successful run used the existing `.tools/m10/venv` with MCP1.26.0. No dependencies were installed or changed for this test.

Raw-key pattern scan of results.json was clean. Credentials were read from existing private operator files only; no full key/password or Secret content was written to evidence.
