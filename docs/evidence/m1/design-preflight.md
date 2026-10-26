# M1 design: read-only machine inspection

**Date:** 14 October 2026. **Scope:** Inventory only, not M1 acceptance testing.

Launched PowerShell through the alternate workspace tool, with no installations, host edits, or Docker/Kubernetes mutations.

## Commands

~~~powershell
Get-Command docker,k3d,kubectl,helm -ErrorAction SilentlyContinue | Select-Object Name,Source | ConvertTo-Json
Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json
Get-NetTCPConnection -State Listen -LocalPort 80,8080 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort | ConvertTo-Json
docker version --format '{{json .}}'
kubectl version --client -o json
~~~

## Observed output summary

- docker.exe found under Docker Desktop resources/bin; client version 29.6.1, Windows amd64, server null.
- kubectl.exe found under Docker Desktop resources/bin; v1.36.1, Windows amd64.
- k3d and Helm not listed on the checked PATH.
- Get-CimInstance returned Access denied (HRESULT 0x80041003). No memory capacity established.
- No listener data printed for ports 80/8080; errors were suppressed by the inventory command, so port availability is unverified.
- Docker warning: unable to open user .docker/config.json (access denied). Docker engine named pipe access also denied. No credential file contents were inspected.

## Limits

This proves CLI presence and client versions only. It does not prove Docker is stopped, usable from the user's terminal, or ready to create a cluster. The tool identity may have different access from the user. Repeat the bounded preflight in the user's PowerShell terminal if needed. No permission/ACL/firewall changes were attempted.
