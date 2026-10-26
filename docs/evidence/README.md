# Evidence scope

This directory publishes sanitized text reports, protocol/audit records, test summaries and historical reviews. Later user-reported acceptance is recorded separately from independently observed checks. Historical failures are retained rather than relabelled as newly passing runs.

Browser screenshots remain in the local workspace and are excluded from the public source repository: captures may contain account, invitation or checkout information. References to those images in historical reports describe locally retained evidence, not files delivered in this repository. Architecture images and source UI assets are published separately.

Private operator inputs, full API keys, OAuth tokens, kubeconfigs, certificates/private keys, environment files and database backups are not part of this source handoff. A passing known-secret scan is not a guarantee that every unknown secret can be detected.
