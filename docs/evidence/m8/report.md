# M8 implementation report

**Status, 19 October 2026:** Independent acceptance review **12/12 PASS** for the approved fixture/browser/static-runtime scope. User module acceptance remains pending. See [review](acceptance-review.md) and [results](acceptance-results.json); real integration remains M10.

M8 implements the seven approved React pages: Login, invitation redemption, server/tool status and management, members/invitations, explicit-owner gateway keys, audit and transient chat. All browser API requests use the same dashboard origin and session cookie; authenticated changes include CSRF. The browser never contacts upstream MCP servers or Groq.

The client enforces bounded requests/responses and deadlines, generation-based obsolete-response rejection, verified session entry, explicit role navigation, transient sensitive values, safe text rendering and honest lost-response messages. Writes are never replayed automatically. Logout clears local data first and serializes server logout before allowing another account to log in. Unknown/timeout tool effects remain visible.

Source is formatted for reading. Runtime dependencies are React/React DOM only; direct build/test dependencies are exactly pinned in `frontend/package.json` and the generated lockfile. The one-off pinned Prettier formatter is not an application dependency. `frontend/Dockerfile` pins approved Node 24.18.0 and NGINX unprivileged 1.30.6 Alpine by immutable digest.

## Observed host checks

- Clean locked `npm ci`: PASS, 157 packages, 42 seconds. npm reported its esbuild lifecycle-script review warning; no project dependency changed to suppress it. Subsequent observed build determines whether required tooling actually works.
- Strict TypeScript: PASS.
- Unit/component suite: 23 PASS in 4.58 seconds (19 API and four display/lifecycle checks).
- Production build: PASS, final 2.67 seconds; 42 source modules, JavaScript 223.06 kB (69.86 kB gzip), CSS 2.73 kB. Final static assets match the frozen application source.
- Real Chromium: **16 distinct host fixture cases PASS**: final complete fourteen-case run passed in 21.3 seconds; the subsequently requested member-own-key/member-only-audit case passed in a focused run in 14.4 seconds (2.9 seconds inside the test). A final targeted disabled/never-checked empty-preview case passed in 8.5 seconds (1.0 second inside the test). The full fifteen-case cluster run is separate runtime evidence. The three host logs make this split explicit.

Exact outputs live alongside this report. `runbook.md` gives reproducible PowerShell commands, boundaries and runtime cleanup rules. The root runtime checker has also completed the isolated Kubernetes checks below. The independent review records its own acceptance verdict separately.

## Scope and remaining gates

All current screen interactions use the separate controlled Python API fixture. It reproduces session cookie/CSRF and role redaction, credential omission/replacement/clear, one-use/expired invitation conflicts, unique key metadata and safe chat/audit outcomes. The actual M5/M6/M7 adapters are not wired or accepted by these fixture results.

Host and isolated runtime checks have passed. Independent acceptance review and user module acceptance remain separate gates; the reviewer maintains its own acceptance result. Host app/fixture source and both built images remain frozen. M10 owns real integrated browser/backend/store/provider proof. No VPS, machine certificate trust change, provider call or optional scope was started.


## What the tests established

The 23 unit/component checks exercise actual request encoding, UTF-8 limits, schema/response bounds, safe nullable shapes, current/obsolete 401 behavior, lost-write uncertainty, deadline cancellation, no replay, synchronous invalid filters, stale read delivery, disclosure copy failure and confirmation focus restoration.

The 16 distinct host real-browser cases cover both roles, HttpOnly cookie access, required CSRF, server status/preview/injection escaping, exact credential and CRUD requests, admin-targeted and member-own keys, one-time disclosures/revocation, malformed/expired/consumed invitation links, all six audit outcomes and member-only server responses, chat answers/attempts/partial and unknown effects, overload/provider/disconnect failures, lost issuance without replay, serialized delayed logout/account switch, stale preview rejection, keyboard interaction and 1440x900/390x844 layouts.

Initial failures were corrected before this final result: select/text-area labels needed explicit accessible names; a second invitation fragment on an already mounted invitation page needed capture/removal and a fresh redemption component; obsolete API 401s and pending-write callbacks needed generation guards; logout needed serialization before another login; malformed success shapes and oversized rejected transfers needed explicit safe rejection/cancellation. These were implementation defects found by checks/review, rather than skipped acceptance cases.

`desktop.png` and `mobile.png` contain dummy account metadata only, after disclosures are dismissed or masked. Browser-wide `network-summary.json` contains sanitized host/cluster metadata including the final host-only preview case with only allowlisted metadata. It asserts same-origin destinations, no Authorization header, and fragment removal before API effects. No cookie, CSRF token, credential value, password, invitation token or raw key is saved in those records.


## Observed isolated Kubernetes runtime

The owned `urumi-m8-check` release ran the frozen dashboard and separate fixture/proxy image. Both actual Pods were Ready with zero restarts, bounded resources, non-root identities, read-only filesystems, dropped capabilities, no ServiceAccount token and live/readiness checks. The recorded Pod image IDs matched the SHA256 of actual Docker-exported configuration bytes:

- `urumi/dashboard:m8`: `sha256:3594864039effe302c5a0d5b381cd2c90836eef30bffdc872e9e57e3c9905a3d`.
- `urumi/dashboard-fixture:m8`: `sha256:83dbd6f6517b0f99ce0e82de78b4b2dbb1f8dfcbcdb307e127dd673035a1df1c`.

The cluster-served `index.html`, JavaScript and CSS matched the frozen host build byte for byte. Static health responses, security/cache headers, and missing/API route 404 behavior were observed. Chromium ran the complete fifteen-case suite through the actual cluster-served assets: **15 PASS in 30.0 seconds**. The later sixteenth host-only preview check uses the same frozen application; it was not retrospectively counted as a cluster run.

`runtime-verification.json`, `runtime-asset-check.json`, `cluster-resources.json`, `cluster-browser-output.txt`, `image-identity-*.json` and `cluster-commands.json` contain inspectable raw evidence. `cluster-results.json` deliberately retains `PASS_RUNTIME_REVIEW_PENDING` as the runner's historical result; derived independent acceptance does not rewrite that history.

Cleanup removed only the owned labelled test namespace. All seven pre-existing shop Pod/PVC/Service identities remained unchanged; the original release was not upgraded. Port-forward cleanup was confirmed, with loopback port 18080 closed afterward. The runner later gained port-occupation/live-process guards; its Python compilation passed. That guard-only edit is a host checker change after the observed runtime, not an application/image change or a claimed repeated cluster run.

Two attempted k3d imports using the Windows archive path returned zero while importing no images. Importing the existing Docker **image tags** succeeded in 16 seconds. Actual exported configuration hashes and actual Pod image IDs, rather than an import command's exit code, establish which images ran. This operational limitation is retained instead of being hidden as a successful archive import.

No real backend adapter/provider/shop-write flow was exercised. These are fixture-backed browser and static runtime results. M10 still owns real integration and final two-user acceptance; user module acceptance remains pending.
