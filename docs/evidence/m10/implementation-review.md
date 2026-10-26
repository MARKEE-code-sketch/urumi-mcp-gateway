# M10 independent implementation review

Reviewed 20 October 2026. **Source review: no unresolved blocking defect found in the controlled composition scope. Full M10 acceptance remains NOT COMPLETE.** User acceptance is pending.

## Scope and grounding

Reviewed the assignment, AGENTS.md, blueprint, M10 specification/design, new backend entry point/orchestrator, database migration and readiness changes, API adapter integration, chat cancellation correction, release Docker stages, chart configuration, M10 checker/target guards, M9 staged-build/history corrections, tests and demo guide. This reviewer did not mutate application source, deploy a release, inspect private credentials, call a provider or change machine trust.

## Findings corrected during review

1. Ordinary account API workers were initially outside the shutdown worker inventory. A pinned-environment cancellation experiment confirmed that a cancelled ASGI task can finish while its AnyIO blocking thread continues. The implementation now injects tracked bounded adapters for the complete synchronous API actions, including caller validation, and lifecycle work. Regression cases hold real API threads open through request cancellation and verify database ownership is released only after the actual work ends.
2. An unexpected owner-monitor exception could initially skip cleanup. The implementation now preserves the error and performs independent cleanup; a regression verifies owner-resource closure.
3. Composing chat under the existing API middleware exposed a cancellation interaction in Starlette disconnect probing. The watcher now observes its task cancellation state; the composed real MCP/API/chat route check exercises the formerly hanging completion path.
4. The M9 package checker formerly expected absent runtime entry points in the current checkout. Its negative now runs from an explicit missing-source staging root before Docker; historical M6 image comparisons are labelled historical observations and do not claim current source parity.

## Verified source properties

- The final executable uses the real factories and one worker. Release image stages exclude historical check scripts; explicit checks-stage callers remain supported.
- Cookie/Origin/CSRF browser identity and personal-key MCP identity stay separate. Exact root dispatch retains MCP guard authentication and path. Chat shares the same router.
- Startup recovers persisted work before readiness, uses the installation UUID for Secret ownership and initializes Woo in one transaction. A separate durable marker preserves deliberate removal and existing administrator changes.
- Shutdown tracks requests, API/lifecycle/router/discovery/lock/chat workers and finalizers. Undrained work requests process termination without normal owner release, preserving recovery uncertainty.
- The read-only target helper requires explicit scoped inputs/ownership and saves allowlisted metadata. Controlled checks do not auto-deploy, access old destructive database fixtures or fabricate live acceptance.

## Evidence boundary and remaining work

Focused controlled tests, package tests and separate PostgreSQL checks support the implementation. Raw runner outputs and the final report own their exact counts and commands; this review does not replace them. Actual shop, Kubernetes Secret API, trusted stable HTTPS, provider, three real upstreams, external client natural-language behavior, persistence/recovery, network enforcement and D1-D10 still require their corresponding observed evidence. No C10 live criterion is promoted to PASS by source review or simulated remote adapters.

The proposed fresh deployment target, private input/trust procedure, operator bootstrap, external client and current provider-plan confirmation remain separate decisions before those actions. Keep the retained shop intact and preserve historical evidence.
