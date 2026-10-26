# Tools preview repair and dashboard design review

22 October 2026. The canonical backend tool field is `gateway_name`. The frontend and its fixture previously expected `name`, producing the user's reported response-shape error. Types, strict validation, rendering and fixture now agree with the backend. No backend contract was changed.

Verification: TypeScript and production build passed; 22 API tests and one focused fixture-browser test passed. The independent review and immutable image deployment are recorded in this directory. All seven workloads were Ready; other six Pod identities and three persistent claim identities were preserved.

Root ran `node scripts/m8/check-live-tools.mjs` against the actual HTTPS dashboard with normal certificate validation. Both admin and member accounts successfully viewed Microsoft Learn's three tools, Inventory's one tool and WooCommerce's five tools. All nine names used their canonical gateway prefixes; neither account displayed the response-shape error. See [live-browser.json](live-browser.json). Credentials were loaded privately, never included in output or browser traces. No shop writes or provider calls were needed.

At the time of this repair, a separate sample design preview was inspected in Chromium at desktop and 390 px; the mobile document width matched the viewport. That rejected preview was removed during the user-requested cleanup on 23 October 2026. At the repair stage, the application still used plain-text chat and schema JSON; the subsequently approved redesign is documented in the [M8 design amendment](../../../modules/m8-dashboard-refresh.md).

Historical M8 fixture network metadata was refreshed by the focused harness; it is not a preserved original-run record. Current repair evidence is kept here separately.
