---
name: mcp-kubernetes-acceptance-qa
description: Audit an implemented Urumi MCP Gateway deployment against its approved requirements using Kubernetes, Helm, MCP, security, and end-to-end evidence. Use for module or system acceptance reviews, not for designing or implementing features.
---

# MCP and Kubernetes Acceptance QA

Review whether the implemented system demonstrates the approved requirements. Explain findings simply, including what Kubernetes resource or MCP action is involved and why the evidence proves (or does not prove) the behavior.

## Required inputs

- The assignment DOCX and `AGENTS.md`.
- The approved `blueprint.md` and the module's approved implementation scope.
- Access to the target cluster/application or concrete command output, logs, screenshots, and client evidence.
- The planned acceptance steps, including which actions may change cluster state.

If required evidence is missing, mark the affected check `BLOCKED`; do not infer success from source code, a build, or unit tests.

## Audit workflow

1. Map each applicable requirement and approved module criterion to a check.
2. Record the exact command/action, environment, expected result, observed result, and evidence location.
3. Inspect relevant Helm release and Kubernetes resource state: workload readiness, probes, resource requests/limits, Services, Ingress, Secrets references, and persistent storage.
4. Verify MCP behavior where evidence is available: Streamable HTTP connection, aggregated tool listing, collision naming, correct routing, timeout/error behavior, and continued operation when one upstream is unavailable.
5. Verify access boundaries: WooCommerce MCP is not externally reachable; gateway clients do not receive upstream credentials; API-key revocation and role rules take effect; audit entries identify the right user/server/tool and outcome.
6. Review the approved two-user definition-of-done flow: storefront checkout and order visibility; user A's chat product/order tasks; user B's external MCP connection with only gateway URL and key; cross-server tool use; key revocation; disabling an upstream; upstream Pod failure while other servers continue; and corresponding audit records.
7. Run state-changing or disruptive checks only when they are part of the approved acceptance plan. Before deleting, upgrading, or disrupting resources, verify the target and intended recovery steps.
8. Report `PASS`, `FAIL`, or `BLOCKED` for each check, defects by impact, exact missing evidence, and the smallest next check or correction.

## Evidence rules

- A healthy Pod alone does not prove the application is usable; a successful build does not prove Kubernetes deployment; tool-list output does not prove correct tool calls or authorization.
- A passing local test does not prove VPS readiness. Confirm production-like deployability uses the same Helm chart with environment values, and label an actual VPS deployment separately if it has not been performed.
- Distinguish observed facts from assumptions and recommendations. Never claim the overall definition of done passes unless the full required two-user flow has been demonstrated.
- Do not modify application code, Helm resources, live systems, or data as part of a review. Provide a targeted change request for fixes; implementation proceeds through the project's approval gates.
