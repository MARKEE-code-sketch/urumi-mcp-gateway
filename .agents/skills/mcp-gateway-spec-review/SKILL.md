---
name: mcp-gateway-spec-review
description: Review a specification, architecture, or implementation prompt for the Urumi MCP Gateway on Kubernetes before application code is written. Use to check scope, design, module boundaries, and acceptance criteria against the assignment.
---

# MCP Gateway Specification Review

Help the user shape a small, testable implementation plan for the Urumi AI FDE assignment. Explain Kubernetes and MCP terms in beginner-friendly language, relating Kubernetes ideas to Docker when useful.

## Grounding

Before reviewing, read:

1. `Urumi AI FDE Internship - Round 1_ MCP Gateway on Kubernetes.docx` as the product source of truth.
2. `AGENTS.md` for project scope, learning needs, workflow, and approval gates.
3. `blueprint.md` if it exists; treat it as approved only when the user has explicitly approved it.
4. Relevant prompt/workflow log entries if they exist.

Do not import requirements from other projects. Separate mandatory requirements, optional bonus work, user-approved choices, assumptions, and unanswered questions.

## Review workflow

1. Explain the proposal in WHAT / WHY / HOW terms, including the user-visible result and the request or data path.
2. Trace each proposed behavior to the assignment or label it as a decision that still needs user approval.
3. Check boundaries and security responsibilities across dashboard, backend/gateway, upstream MCP servers, WooCommerce, and Kubernetes resources.
4. Define the smallest independently testable module: purpose, files/resources, inputs, outputs, dependencies, and excluded behavior.
5. Specify module-level checks and observable evidence. Include cluster or real MCP evidence when unit tests alone cannot prove the behavior.
6. Identify design tradeoffs and risks in plain language. Ask the user about decisions that materially change scope, cost, security, or architecture.
7. Return a review verdict: `READY FOR USER REVIEW`, `REVISE`, or `BLOCKED`, with reasons and open questions.
8. If requested, produce one copy-paste implementation prompt scoped to the reviewed module. Require the implementer to stop after that module's checks and report exact commands, evidence, and gaps.

## Assignment invariants to check

- Helm is required; local Kubernetes and same-chart production-like VPS/k3s deployability are required. Environment differences belong in Helm values.
- The WooCommerce MCP server is custom-written for the assignment, uses Streamable HTTP, and is internal to the cluster; gateway-mediated access is the path for chat and external clients.
- The gateway aggregates at least three upstream servers, handles tool-name collisions, and isolates slow/unreachable upstreams with timeouts and clear errors.
- Upstream credentials stay server-side. Per-user gateway keys are hashed and revocable; tool calls are attributed in the audit log.
- Workloads need persistence where required, readiness/liveness checks, resource requests/limits, and Kubernetes Secrets for credentials.
- Multi-store provisioning is optional and must wait until the mandatory core works and the user approves it.

Do not write application code, silently approve the blueprint, authorize the next module, or expand the assignment scope. The user makes approval decisions.
