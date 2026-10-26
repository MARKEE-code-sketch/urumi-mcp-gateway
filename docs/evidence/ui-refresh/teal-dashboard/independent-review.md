# Independent source review — approved teal dashboard

Date: 22 October 2026. Scope: read-only review of the other agents' application shell, chat, answer renderer, audit presentation, stylesheet, local assets and dependency metadata. The reviewer implemented Servers/ToolInputs earlier; those files are not independently accepted by this review. No cluster action or additional test run was performed in this phase.

Verdict: **PASS with one low-priority stylesheet correction**. No blocking defect identified in the reviewed source. Browser layout and real deployment remain separate evidence owned by the root agent.

| Area | Observed evidence and assessment |
|---|---|
| Untrusted Markdown | `frontend/src/components/ChatAnswer.tsx:23-29` uses `skipHtml`, removes Markdown images, accepts only deliberate HTTP/HTTPS/mailto links and creates semantic tables. No `dangerouslySetInnerHTML`, raw HTML plugin, image fetching or API envelope rendering is introduced. Exact answer prose remains the source of displayed content. |
| CSP and alignment | The renderer converts table alignment to three fixed CSS classes; no inline style attribute is forwarded. `frontend/nginx.conf` retains same-origin script/style/connect/image policy, object denial and framing/base restrictions. Local stylesheet/font/SVG imports fit this policy. |
| Roles and private state | `frontend/src/App.tsx:36-47` clears sessions, selected owners and pending state and aborts active API work. View-generation guards remain at lines 163-165 and 207. Members retains the explicit admin gate at lines 220-233; the sidebar also hides the member link for members. Key ownership and existing API/CSRF layer are preserved. |
| Chat lifecycle | `frontend/src/pages/Chat.tsx:87-108` retains the synchronous duplicate-submission guard, bounded ten-exchange state, ordinary API dispatch and pending cleanup. Prompt buttons only insert text. No persistent history, automatic replay or upstream/provider fetch was added. Context is derived from the server API, with page/stale/stored-status explanations rather than invented availability metrics. |
| Visible warnings | `frontend/src/pages/Chat.tsx:27-29` leaves failed/limit, unsuccessful tool and uncertain-effect warnings outside disclosures. `frontend/src/pages/Audit.tsx:77-81` leaves timeout/unknown remote-effect warnings and safe error summaries visible before the record-details disclosure. Running/timeout semantics remain in the audit introduction. |
| Responsive and keyboard structure | Styles include minimum-width grid tracks, contained Markdown-table/code scrolling, responsive navigation/server/chat layouts, visible keyboard focus and reduced-motion rules. The answer-table region is focusable and named. Source inspection supports the design but does not prove screenshot quality or actual viewport geometry. |
| Assets and encoding | Parsed every local source SVG as XML; found no script, foreignObject, image/use references, event attributes or href references. Figtree and icon license files are local. UTF-8 reads of the four reviewed TSX files found no U+00C2, U+00C3 or replacement-character encoding corruption. |
| Dependencies | Installed package metadata and exact manifest pins are `react-markdown` 10.1.0 and `remark-gfm` 4.0.1, both MIT. React Markdown's React peer requirement is >=18, satisfied by React 19.2.4. This metadata check does not claim a vulnerability audit. |

Low-priority finding: `frontend/src/styles.css:946` and `:1080` use `.schema-constraints dl>div`, while the component's structure is `<dl className="schema-constraints"><div>`. Use `.schema-constraints>div` so the intended narrower constraint labels and mobile block layout apply. Root was notified; reviewer did not modify source.

This review does not create a new approval gate. The user's implementation authorization remains in effect. Root's unit/browser/build/deployment outputs must be reported with their actual scope and results.
