# Local HTTPS preparation

The local certificate protects browser login and gateway traffic at `dashboard-m10.urumi.test`. It also covers `shop-m10.urumi.test` for the separate production transport check; it does not change WordPress's canonical URL by itself. Existing `urumi` shop storage and hostnames remain unchanged.

Run from the repository root in PowerShell:

```powershell
./.tools/m10/venv/Scripts/python.exe scripts/m10/local_https.py
```

The helper uses the already pinned `cryptography==46.0.5`, creates a fresh private `.tools/operator/m10/tls` directory and refuses to replace an existing directory. It creates a one-year CA with critical DNS name constraints for subdomains of `.urumi.test` and no subordinate CA permission. The server certificate lasts 30 days and has exactly the two names above. Private keys stay under ignored `.tools`; do not copy them into evidence or submission. Windows does not implement POSIX file modes: the operator must restrict this directory's Windows ACL to the current user and SYSTEM before storing or using private keys. Do not upload the CA private key to Kubernetes.

Trust installation is a separate operator step, already authorized by the user for this local setup. Import **only** `ca.pem` into `Cert:\CurrentUser\Root`, record its exact SHA-1 thumbprint from metadata, and verify the installed certificate's SHA-256 matches metadata. This changes trust for the current Windows account, not all users. A local CA is still a sensitive signing identity: protect its private key. Critical name constraints limit the intended DNS scope; verify the actual Windows chain and browser hostname checks rather than assuming every client enforces trust identically. Python/Node/MCP clients may require an explicit CA bundle because their trust stores differ. Never disable certificate checks.

The hosts file needs only `127.0.0.1 dashboard-m10.urumi.test shop-m10.urumi.test`. Preserve all existing lines and add an identified project block only after checking conflicts. Updating Windows hosts may require elevation. Expose the existing cluster load balancer's HTTPS port on loopback 443 without recreating the cluster; verify the installed k3d command supports the update, port availability and existing shop health first. Create a Kubernetes TLS Secret in the **new** release namespace from `tls.crt` and `tls.key`; never print Secret data.

Verify a normal trusted request and real browser navigation without certificate overrides. Record SANs, expiry, thumbprints, selected trust store and success/error metadata only. A successful certificate generation test is not proof of browser or deployed HTTPS success.

Rollback: remove only the certificate at `Cert:\CurrentUser\Root\<recorded-thumbprint>` after checking its exact identity; remove only the added hosts block and TLS Secret belonging to this test release. Remove the added loopback mapping only if supported and its ownership is verified. Do not delete the cluster or retained shop disks. Remove private files only after they are no longer in use and the resolved target is checked to remain under this project's `.tools/operator/m10/tls`.
