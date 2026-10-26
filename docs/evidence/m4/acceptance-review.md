# Independent M4 acceptance review

**Verdict:** PASS for M4-01 through M4-08, 16 October 2026. User module acceptance remains pending; no M10 integration claim.

The independent read-only reviewer inspected Inventory, the standalone probe, controlled fixtures/tests, Helm resources, the cluster runner, saved command/results artifacts and the final report. The reviewer did not rerun those runtime commands personally; the implementation agent executed them and the reviewer assessed the recorded evidence.

Source review found and resolved two boundary issues before final verification: post-start timeout responses could duplicate ASGI response headers (now the stateless JSON endpoint explicitly accepts only POST, with tracked response-started behavior), and raw HTTP byte caps could be bypassed by decompression (now request identity encoding and reject compressed replies before parsing). Actual TCP tests cover the first boundary and byte/encoding regression checks cover the second.

Observed evidence supports exact M0 discovery/annotations and safe fixture/input behavior; host10 and Linux10 passing test methods; controlled bearer/header missing/wrong/valid cases and duplicate names; finite failure/limit checks; internal-only Ready resources; actual allowed-denied-allowed calls; the same bad-probe Pod's restartCount1 plus liveness404/kubelet Killing events; restored successful call; and complete owned-namespace cleanup with identical existing store resource/PVC identities.

The reviewer read the actual in-cluster Microsoft Learn result, confirmed useful readiness gating/liveness restart documentation, three actual discovered tools and negotiated protocol `2025-06-18`. This is a real unauthenticated hosted call, distinct from controlled fixtures and from unverified authenticated-hosted compatibility. All saved M4 evidence files were checked for both artificial fixture sentinel values with zero matches. The implementation agent saved its separate reproducible scan result in `redaction-review.json`.

The final report was corrected to describe the observed unrelated connection as **ConnectionRefusedError after successful DNS resolution**, not a timeout. It accurately preserves the initial OCI-index comparison failure and corrected exact-config verification, and distinguishes the later host-only closed-port assertion from the test snapshot inside the image. No runtime application/probe/client source changed after the checked build.

Remaining boundaries: real gateway routing/credential injection/aliases, user keys/audits, chat, cross-server prompts and the final two-user flow require their later modules; production deployment and a real authenticated hosted server have not been demonstrated by M4. No blocking M4 source or evidence findings remain.
