# M8 dashboard refresh — specification and design for review

**Status:** Approved for implementation on 22 October 2026. The user selected option A, [Urumi Workspace](../design/professional/index.html), with teal/light green replacing the orange/coral accent. This includes the functional formatting and input presentation described below. Rejected directions and the Omni comparison were removed during the user-requested cleanup on 23 October 2026.  
**Date:** 22 October 2026.  
**Scope:** A focused amendment to [M8](m8-spec.md), prompted by the user's real dashboard screenshots. No additional project module or parallel plan is introduced.

The [retained chosen design preview](../design/professional/index.html) records the original coral direction. The implemented dashboard uses teal/light green; see the [implementation and verification report](../evidence/ui-refresh/teal-dashboard/report.md). The preview contains sample content only and is a design record, not deployed application evidence.

## WHAT, WHY and HOW

**WHAT:** Fix the admin tool-preview contract, refresh the existing dashboard screens, and turn chat answers into readable paragraphs, lists and aligned tables. Put technical references behind disclosures while retaining important warnings.

**WHY:** The real tool-preview API returns `gateway_name`, while the original frontend/fixture expected `name`. That discrepancy explains the response-shape failure. The original M8 design deliberately used plain text, so Markdown from the model displays as punctuation. The current page also gives UUIDs and troubleshooting metadata as much prominence as the answer.

**HOW:** Keep React, TypeScript, Vite, native CSS, existing backend APIs and the existing Helm deployment. Introduce a small safe answer-rendering component and shared presentation patterns. Test each behavior independently, then verify the rebuilt dashboard in the local Kubernetes release. Backend authorization and gateway execution remain authoritative.

## Design direction

The approved direction uses a white full sidebar, clean white workspace, charcoal text, locally hosted Figtree typography and one consistent Phosphor icon family. Teal actions and light green selected states replace the prototype's coral accent. The proposed Urumi mark and matching favicon use the same teal identity. Spacing, input sizes, borders, focus rings and status labels are consistent across screens. Font and icon licenses are retained locally; runtime requires no remote fonts or assets.

The dashboard retains five areas: Chat, Servers, Members, Gateway keys and Activity (the existing audit view). Members remains admin-only. Chat appears first in the preview because it demonstrates the reported problem; implementation should preserve existing application routes and default entry behavior unless reviewed separately. No new analytics overview or invented metrics are added.

Public layout references: [Carbon UI shell](https://carbondesignsystem.com/components/UI-shell/usage/) for navigation hierarchy and [Dribbble dashboard exploration](https://dribbble.com/search/dashboard) for general density and composition. The preview is an original local composition, not a copied template. No reference assets, brand marks, screenshots or source files are imported. This design does not claim to use Carbon components.

| Screen or component | Proposed behavior | Existing ownership |
|---|---|---|
| Application shell | Branded sidebar, clear current-page state, account and role, quieter logout, mobile navigation that stays usable at 390 px. | `frontend/src/App.tsx`, `styles.css` |
| Chat answer | Proper paragraphs, headings, emphasis, lists, code and semantic GFM tables. Horizontal scrolling is contained within wide tables/code blocks. No raw HTML rendering. | `pages/Chat.tsx`, new `components/ChatAnswer.tsx` |
| Chat composer | Labelled multiline input, clear send state, independent-message/history guidance, optional prompt insertion that never submits automatically. Existing size/deadline limits remain. | `pages/Chat.tsx` |
| Tool activity | Compact actual outcome summary; expand for exact tool names and outcomes; separate disclosure for request/call/server/audit IDs and durations. Failed, partial, limit, timeout and uncertain-effect warnings remain visible. | `pages/Chat.tsx` |
| Server list | Status labels with text and color, truthful stored timestamps, clear add/refresh actions, quieter editing and destructive actions. No manual-ping claim. | `pages/Servers.tsx` |
| Tool preview | Use canonical `gateway_name`, description and readable input name/type/required/constraint rows. Empty/disabled/stale/error states remain explicit. More complex constraints use bounded readable disclosures, never a raw JSON dump. No tool-execution form is added. | `types.ts`, `api.ts`, `pages/Servers.tsx` |
| Members | Clear people/role/action table, existing invitation form and once-only invitation result. No new role editor or email workflow. | `pages/Members.tsx` |
| Gateway keys | Clear owner, client endpoint, label field, status and revocation; once-only raw key display retains deliberate copy/dismiss behavior. | `pages/Keys.tsx`, `components/OneTimeValue.tsx` |
| Activity | Scannable actual outcomes and tool names; timestamps and filters remain usable; expand for full identifiers and safe diagnostic fields. No argument/result dump. | `pages/Audit.tsx` |

The prototype's product rows reproduce the user's example for visual review. Its server statuses, people, activity rows and dates are representative samples, not observations of current deployment state. Sample tool parameters demonstrate layout only; implementation must use actual returned schemas rather than hardcoded limits or defaults.

## Contract repair and dependency decision

The tool preview repair uses the actual API field `gateway_name` consistently in frontend types, validation, rendering and fixtures. It must not relax validation to accept arbitrary shapes or silently invent missing names. Add a regression case with a realistic backend-shaped tool page for both roles. The repair can proceed independently as the user-requested bug fix; the wider redesign remains at this review gate.

Answer rendering uses reviewed, exact pins `react-markdown` 10.1.0 and `remark-gfm` 4.0.1, both MIT licensed and compatible with the existing React 19 application. These libraries parse formatting into React elements; they do not change the provider or execute model-supplied markup. Existing React/TypeScript/CSS remain the UI stack, without a second component framework.

This amendment replaces the original M8 plain-text answer choice only after design approval. It does not replace the original identity, authorization, secret handling, independent-message or audit contracts.

## Safety and truthful output

- Never use `dangerouslySetInnerHTML`, execute raw HTML, embed model-supplied images, load remote assets, or automatically visit links. Raw HTML is suppressed; Markdown images are disabled. Limit link schemes, label links clearly and open only on deliberate user action. The final production CSP stays restrictive.
- Model output and tool descriptions remain untrusted. Markdown formatting does not make claims reliable; preserve the actual answer, tool outcomes and uncertainty without changing prices, inventing summaries or inferring successful actions.
- If an answer is plain prose, render it naturally. If it contains JSON-like text, never expose raw tool objects or the API envelope as UI output. Do not introduce a speculative general-purpose JSON-to-table parser; readable structured answers should come from safe semantic formatting and existing known contracts. Actual product IDs requested by the user remain visible.
- The current chat API returns one final response. While pending, show a neutral processing state, not invented live stages or a running tool timeline. Only render individual attempts from the returned `tool_calls`.
- Preserve CSRF, same-origin requests, role gates, session cleanup, bounded state, cancellation behavior, duplicate-submit protection and no automatic replay of writes. A local timeout must never imply remote rollback.
- Technical identifiers remain available in accessible disclosures. Important errors, unsuccessful attempts and possible remote effects cannot be hidden solely inside a closed diagnostics section.
- Keep credentials out of source, screenshots and traces. No external design upload, public publishing, provider change, paid service, persistent conversation, direct upstream request, database migration or multi-store scope is introduced.

## Verification and review gates

1. **Contract repair:** Canonical backend-shaped admin/member tool previews render; malformed or oversized data is still rejected. Fixture pages use the actual field names. Verify the repaired view against the real local gateway separately from fixture tests.
2. **Answer renderer:** User screenshot text produces real emphasis and a semantic three-column product table. Verify lists, code, Unicode/INR, long cells and plain text. Hostile HTML, scripts, image Markdown and unsafe links produce no executable markup or unsolicited network request.
3. **State behavior:** Existing roles, one-time key/invite values, logout/session replacement, CSRF, duplicate-submit, lost-response and uncertain-write checks still pass. Expansion never exposes raw secrets or tool result objects.
4. **Visual and accessibility review:** Inspect real Chromium screenshots at desktop and 390 px. Keyboard reaches navigation, composer, table scroll and disclosures; focus is visible; status is understandable without color; long tool names do not cause page-wide horizontal overflow. Respect reduced motion.
5. **Local deployment:** Build the production dashboard, use the same chart with an immutable updated image reference, verify the owned dashboard workload and real admin/member flows, and preserve store/backend/PVC identities. A successful build alone is not live visual proof.

Review the local preview first, including Servers → View tools and Chat → Tool activity → Request and audit details. After user approval, implement and test the narrow components, then deploy and present observed evidence and remaining gaps. Existing historical M8/M10 evidence remains historical; this amendment must produce fresh evidence rather than silently rewriting old results.
