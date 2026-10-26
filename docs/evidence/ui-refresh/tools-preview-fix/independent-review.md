# Tools preview contract fix review

**Verdict: NO BLOCKER.** Reviewed `frontend/src/api.ts`, `types.ts`, `pages/Servers.tsx`, focused API/browser regressions, the controlled fixture and actual `backend/gateway/discovery.py` contract.

The backend preview intentionally exposes `gateway_name`, while MCP protocol lists use `name`. The UI had incorrectly required the MCP field in this browser API response. The fix consumes canonical `gateway_name` in the type, runtime shape check and rendered heading/key. It preserves the backend contract and the existing escaped text/schema rendering. Three focused regressions accept the canonical object without `name` and reject missing/numeric `gateway_name`, even when an incorrect `name` is present. The fixture/browser expectation now matches that real browser API. No backend, CSS, Markdown, dependency or authorization change is needed.

Root reported 22 API checks, TypeScript/build and one focused fixture-browser check passing before this review. Docker verification below performs its own typecheck/build. Actual authenticated admin/member preview verification remains the root's live browser responsibility.

The recent fixture-browser harness refreshed historical `docs/evidence/m8/network-summary.json` (and potentially fixture network metadata); it must not be presented as the original frozen M8 run. This fix keeps new image/deployment evidence in this separate directory and does not relabel refreshed metadata as historical evidence.
