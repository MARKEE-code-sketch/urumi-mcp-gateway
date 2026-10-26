Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding
   Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask. 2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
   Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
   Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
   Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**CRITICAL RULES**

Please always explain the user in simpler terms. The coding must be simple, precise and upto the point, nothing fancy until mentioned. Always keep the human in the loop for any critical decision. for any module you make, make sure the user learns along with you, everything from the tech stack you are using to the coding part always walk the user through it. Explain it in the simplest way possible because the tech stack is new to the user. First provide a summary of what we are trying to do i.e.- WHAT, WHY AND HOW and then we will proceed further.Use plan mode to develop any feature.

Also make sure to break up everything in modules and then implement each module, doing that help us to test a particular module. for ex- You developed a retiever then you need to test is properly using seperate tesing module(use libraries like deepeval for that and use metrics-i.e. here recall@k and precision@k ) and properly evaluate the module and tell me the results at the end and then only proceed to next module

and also keep names for each module, for ex- retriever.py, I want you to develop each module independently and then wire them up by using an orchestrator. follow proper system design principle.

Use skills and plugins wherever possible.

WE WILL FOLLOW PROPER SDLC(SOFTWARE DEVELOPMENT LIFE CYCLE FLOW)->

SPEC PLAN( DEFINING FUNCTIONAL & TECH REQUIREMENTS)-> REVIEW -> DESIGN -> REVIEW -> IMPLEMENT ->REVIEW

AFTER THIS
TESTING

USE SUBAGENTS FOR EACH PHASE WHEN POSSIBLE.

## Urumi AI FDE Internship: MCP Gateway on Kubernetes

### Source of truth and scope

- Treat `Urumi AI FDE Internship - Round 1_ MCP Gateway on Kubernetes.docx` as the single product specification for this project. Do not import requirements from other assignments.
- Build the required core first: one WooCommerce store with persistent database/content, a self-written WooCommerce MCP server, a dashboard/backend gateway aggregating at least three Streamable HTTP MCP servers, team roles and individually revocable hashed API keys, per-call audit records, and a dashboard chat agent that uses the gateway as the signed-in user.
- The required system runs entirely on local Kubernetes and uses the same Helm charts for a production-like VPS/k3s deployment, with environment differences supplied through Helm values. Helm is mandatory; Kustomize is out of scope.
- The multi-store provisioning platform is an optional bonus. Do not start it until the mandatory single-store definition of done works end to end and the user approves that next scope.
- Do not invent requirements or silently resolve decisions that materially affect security, architecture, cost, or scope. Explain the evidence, choices, and tradeoffs simply, then ask the user.
- The maintainer authorized public publication of the application source, Helm charts, tests and sanitized documentation on 26 October 2026. Keep credentials, machine-specific operator inputs, raw browser captures and the original product brief out of the public repository. General behavioral guidelines remain unchanged.

### Learning and spec-driven development

- The user is learning Kubernetes from the beginning and knows Docker. Explain new Kubernetes concepts by connecting them to familiar Docker ideas, in plain language, before relying on them in a decision or implementation.
- For every proposed component or module, explain WHAT it does, WHY it is needed, HOW requests/data move through it, which files/resources own it, and how it will be checked. Teach the user enough to explain the code and system in an interview.
- Follow this order: understand the assignment and open questions; write/review a specification and plan; design/review; implement/review one module at a time; test; then integrate and run end-to-end acceptance checks. Use Plan mode for feature planning when available.
- Before application implementation, create `blueprint.md` with scope, traceability, architecture, modules, file/resource ownership, tests, evidence, risks, open decisions, and measurable done criteria. Get explicit user approval for the blueprint before application code.
- Keep the user in the loop at each approval gate. After each module, present its purpose, changes, commands and results, evidence, and remaining gaps; get approval before moving to the next module. Do not wire modules together before their individual review gates; integrate in a named final integration module.
- Documentation, read-only inspection, and the currently requested project-instruction/skill configuration work may happen before blueprint approval. Do not treat that as permission to implement application features.
- Prefer the smallest design that meets the assignment. Do not start optional differentiators until the mandatory core works and the user approves the added scope.

### Required blueprint content

`blueprint.md` must include:

- Plain-language goal, mandatory scope, optional scope, exclusions, assumptions, unresolved questions, and definition of done.
- Traceability from each mandatory assignment requirement and each definition-of-done demo step to its module, implementation task, test/acceptance check, and final evidence.
- A beginner-friendly architecture and request/data-flow explanation, including how Docker concepts map to Pods, Deployments, Services, Ingress, ConfigMaps, Secrets, PersistentVolumes/Claims, probes, namespaces, and Helm where those are used.
- Chosen stack and component boundaries, with simple reasons and real alternatives/tradeoffs; identify which components are Kubernetes workloads and which are cluster resources.
- Independently testable modules with named files/resources, owner, inputs/outputs, dependencies, and module-specific acceptance gates. Include a final integration/orchestrator module.
- Helm chart structure and local/production values plan; local domain/Ingress approach; persistent store database and WordPress-content plan; secret handling; readiness/liveness probes and resource requests/limits for workloads.
- MCP protocol and trust boundaries: Streamable HTTP, gateway-to-upstream connections, tool listing/routing and collision naming, timeouts and partial upstream failure, internal-only WooCommerce MCP exposure, and proof that clients/browser never receive upstream credentials.
- Team roles, hashed per-user API keys and revocation, authorization, audit fields and dashboard evidence; chat tool loop acting as the current user; LLM/provider secret handling.
- Three upstream MCP servers (WooCommerce plus two chosen servers), with selection rationale and safe, reproducible local connectivity assumptions.
- Test plan for local Kubernetes deployment, each module, gateway behavior, role/key security, audit attribution, chat, failure isolation, persistence, and external MCP client configuration. Use appropriate checks; do not force unrelated metrics.
- End-to-end demo evidence for two users: storefront checkout and visible order; user A creates product and asks about today's order; user B connects using only gateway URL/key, asks the same question, and runs a cross-server prompt; revoke key; disable server; kill upstream Pod and show remaining services work and status is unreachable; inspect attributed audit events.
- Production-like VPS/k3s deployability using the same chart and values-only environment changes is mandatory. Include DNS/Ingress/storage/secrets notes and upgrade/rollback guidance. Actually deploying to a VPS is listed as a stand-out item; TLS with cert-manager is optional.
- Security/threat model for credentials, untrusted upstream servers/tool descriptions, SSRF when registering URLs, member-to-member boundaries, Kubernetes RBAC, network access/isolation, and container privileges, distinguishing mandatory requirements from optional hardening ideas in the assignment.
- Submission checklist: README local and VPS setup, source for dashboard/backend/gateway/WooCommerce MCP/chat, Helm chart and values, system-design/tradeoffs note, threat-model note, optional-item index, demo video, repository, and submission form.
- Risks, evidence needed before decisions, and measurable project-level success criteria. Do not claim a flow works without observed test/demo evidence.

### Implementation and verification discipline

- The WooCommerce MCP server must be written for this assignment; do not install an existing WooCommerce MCP server or plugin.
- Keep WooCommerce MCP internal to the cluster and allow the gateway to be its caller. Route chat and external client tool use through the gateway; they must not call upstream MCP servers directly.
- Store WordPress content and its database persistently. Put credentials in Kubernetes Secrets (or a documented secure production secret mechanism), never hardcode them. Hash gateway API keys at rest and revoke them effectively.
- Give every workload readiness and liveness checks and resource requests/limits. Document and verify which endpoints are public and which are cluster-internal.
- Test a module independently before integration. Report exact commands, observed outputs, and evidence artifacts; distinguish verified results, assumptions, and unverified gaps.
- For Kubernetes behavior, provide inspectable evidence (for example, resource status, logs, probes, service/Ingress reachability, persistence across restart, and controlled failure tests). A successful build or unit test is not proof of a working cluster deployment.
- Preserve a chronological prompt/workflow log suitable for the submission and include relevant `.agents` configuration without secrets or machine-specific credentials.
- The assignment deadline is two weeks; prioritize a complete mandatory core over unfinished bonus features.

### Evidence and communication

- Use simple, beginner-friendly language throughout and define Kubernetes/MCP terms the first time they matter.
- Separate verified observations, assumptions, decisions awaiting approval, and open gaps.
- After each module, report exact commands, results, evaluation output and evidence, plus remaining limitations. Do not claim end-to-end success until the two-user definition-of-done flow is demonstrated.
