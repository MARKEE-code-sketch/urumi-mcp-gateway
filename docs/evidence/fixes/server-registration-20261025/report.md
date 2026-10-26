# Add server outage and recovery

Observed25October2026 on the existing local `urumi-m10` release. User reported “Unexpected response format” followed by the uncertain-change warning when adding a gateway server.

## Cause and recovery

The gateway API returned HTTP503 `text/plain`, body `no available server`. Backend readiness was503 while liveness remained200. Registry inspection found one prepared, disabled new registration: **Expense Tracker**, slug`et`, ID`e11fbef6-6201-495d-8453-6b8f78e072d6`. Its credential-storage operation had not committed.

The live Kubernetes API endpoint was `172.18.0.3:6443`, while the deployed backend egress policy permitted only `172.18.0.2/32` on that port. An in-Pod API request failed with connection refused. Updating only `backend.networkPolicy.apiServerCidrs` to the observed `.3/32` restored API access: an authenticated GET for an intentionally absent owned-pattern Secret returned404 / NotFound. No broader private/public access was allowed. The mounted service-account token was not expired; token-handling application code was not changed.

Restarted only backend. Existing startup recovery rolled back the prepared new registration and cleared the pending operation. Original three server IDs, user/key identities and revocation metadata, audit count, all three PVC identities and the other six Pod identities were preserved at recovery. The Expense Tracker credentials must be entered again after recovery; the agent did not recreate that registration or copy its credential.

## Dashboard correction

For non-JSON502/503/504 responses, `frontend/src/api.ts` now displays “The gateway is temporarily unavailable. Please try again shortly.” It retains HTTP status, the uncertain-write flag and no automatic retry. Other malformed replies retain their existing error behavior. No raw proxy body is exposed.

Only frontend source and regression tests changed; backend application code, Secrets policy/RBAC and readiness/recovery architecture stayed intact. Built/deployed dashboard image `urumi/dashboard:m8-server-errors` with immutable image identity and deployed asset/source checks. The exact environment CIDR was repaired through Helm values, not a chart-wide network relaxation.

## Observed checks

- Before frontend fix: six expected outage-message regressions failed;25API tests passed. After fix:31API tests passed.
- Full frontend suite: **49 tests passed**. TypeScript and production build passed.
- Controlled frontend browser suite: **17 passed in31.3s**.
- Live HTTPS browser: admin login; disabled Learn alias with dummy bearer credential created201, edited200 while retaining credential, removed204. Original three registrations restored. This exercises actual Secret storage without forwarding the dummy credential to an upstream.
- Live browser network interception reproduced a plain-text503 on Add server. Correct new message and uncertain-change warning displayed; exactly one attempted request, no automatic retry. Interception did not send that request to backend.
- Browser harness was adjusted to treat204 as empty and await actual list refresh before assertions. Those were harness races, not additional application failures. Every created test alias was removed; final registration state is checked separately.

Primary evidence: [before recovery](before-recovery.json), [recovery](recovery.json), [build](build.json), [runtime/image checks](runtime.json), [live browser](browser.json), [created alias](server-created.png), [outage feedback](outage-feedback.png).

## Commands and limits

```powershell
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:browser
node scripts\m8\check-server-registration.mjs
```

Local recovery used scoped read-only `kubectl`/SQL metadata inspection, current effective Helm values with only the exact API CIDR changed, and `kubectl rollout restart/status deployment/urumi-m10-backend`. Dashboard image build/import/immutable upgrade helper commands and exact image hashes are retained in build/runtime evidence; private values remain outside submission artifacts.

Local API addresses may change again on Docker/k3d restart. Startup/operations instructions now explain the endpoint/allowlist comparison. This one-time repair does not claim automatic address reconciliation. Expense Tracker's actual external endpoint/authentication was not exercised; no real user credential was requested or reused. Q10 is tracked separately.

Final combined verification after Q10 deployment:7workloadsReady,3existingPVCsBound, zero pending operations and zero `qa-reg-*` aliases. A user-added Context7 registration appeared during follow-up and was left untouched; the live alias test's original-three comparison describes its earlier check, not a claim that later user additions were removed. See [final state](../final-state-20261025.json) and [credential scan](../artifact-scan-20261025.json).
