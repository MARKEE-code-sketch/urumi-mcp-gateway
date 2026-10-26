# M10 independent concrete-design review

Reviewed 20 October 2026. Verdict: **READY FOR USER REVIEW** for the routine composition in M10 section 12. This is an independent engineering review, not user acceptance or permission for live deployment.

## Grounding

Read the assignment DOCX, AGENTS.md, the specification-review skill, approved blueprint M10, M10 specification and section 12, verification/deployment design notes, workflow history, and existing account, database, registry/Secret, gateway and chat factories. No application source was edited. No cluster/network/provider operation or credential read was performed.

## Findings

- One real backend process composes existing account, gateway and chat services; no production fixture or alternate authentication path is introduced.
- Exact root MCP dispatch retains the guard's original path and protocol body limit. Browser API/chat retain their own cookie, Origin, CSRF and body protections.
- Explicitly entering the gateway child lifespan avoids missing MCP initialization or duplicate discovery/router ownership.
- Startup uses supported migrations and exclusive ownership, persisted installation labels for Secrets, audit/credential recovery, and local readiness checks. Remote upstream outages remain isolated.
- Schema 3 adds an atomic installation marker independent of the deletable Woo server row. Existing edits, disable and deliberate removal survive restart; no hidden admin principal is needed.
- Shutdown specifies a real bounded worker drain and nonzero termination without ordinary owner release when work remains. That is stronger than executor shutdown alone and preserves honest interrupted-write recovery.
- No optional scope or new database/framework/authentication system is introduced. Actual deployment, machine trust, private inputs, client setup and current provider-plan confirmation remain separate decisions.

## Implementation checks required

Test exact routes and real MCP initialization; body-budget separation; child lifespan once; startup failure cleanup; supported migrations; atomic marker rollback/adoption/deletion; no ready-before-recovery window; owner-loss fencing; bounded successful and undrained shutdown; and empty-provider-key behavior without provider requests. Schema expectations in old readiness tests and M9 historical missing-entrypoint/source-image assertions must be adapted using explicit isolated roots rather than deleting negative coverage.

The deployment notes remain a proposal. The separate target, trusted hostnames, private certificate/Secret inputs, operator bootstrap and live client/provider procedures are not authorized by this review. Unit/contract tests will not close C10 runtime or complete-user-flow acceptance criteria.
