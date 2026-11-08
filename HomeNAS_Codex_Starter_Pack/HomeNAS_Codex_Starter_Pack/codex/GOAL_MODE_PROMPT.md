# Codex Goal Mode — HomeNAS Dashboard

## Goal

Build and deploy a lightweight HomeNAS Dashboard on the existing Debian 13 NAS.

Use `docs/HomeNAS_Development_Spec.md` as the authoritative product and technical specification. Use `docs/Architecture_and_Data_Flow.md` and `docs/Phase_Plan_and_Acceptance.md` as supporting references. Use `materials/` as starter templates, not as assumptions about the live machine.

The product scope is ONLY HomeNAS:
- System monitoring.
- RAPL power monitoring through `perf`.
- Storage and SMART monitoring.
- Network monitoring.
- Mihomo monitoring and, after approval, limited safe controls.
- Tailscale read-only status.
- Seafile CE health monitoring.
- Service Inventory.
- Alerts.
- Local administrator authentication.

Do not implement AI PPT, Seafile Android changes, an application marketplace, general-purpose Docker orchestration, or a replacement identity provider.

## Execution strategy

### Step 1 — Establish where you are running

Before touching anything, verify `hostname`, `uname -a`, `/etc/os-release`, and the current working environment.

Determine whether your terminal is connected to the actual Debian NAS. Do not treat the Codex workstation or a container as the NAS. If this is not the NAS host and no authorized remote shell is available, stop host-specific actions and ask for the correct connection/context.

### Step 2 — Read the project pack

Read all three documents under `docs/`. Inspect the example configuration, systemd units, SQL reference, API outline, UI notes and read-only audit script under `materials/`.

Do not blindly copy example ports, paths, service names, network interfaces or health-check URLs. Discover the actual environment first.

### Step 3 — Phase 0 audit, read-only

Run `materials/scripts/host_audit_readonly.sh` or perform equivalent read-only checks.

Produce:
- `docs/environment-report.md`
- `docs/service-inventory-initial.md`
- `docs/network-and-access-report.md`
- `docs/risks-and-decisions.md`

The audit must not:
- Install packages.
- Modify configuration.
- Restart or stop services.
- Change firewall, routing, Tailscale, Mihomo or Seafile.
- Change disk partitions or filesystems.
- Create users or directories on the NAS.
- Expose secrets in output.

Do not print Mihomo Secret, API keys, passwords, session cookies or private keys. If a configuration file must be inspected, inspect only non-secret fields and redact values.

### Step 4 — Implement incrementally

After Phase 0, implement a working HomeNAS rather than stopping at planning documents.

Recommended order:
1. Repository structure and backend/frontend foundation.
2. SQLite schema, migrations and local admin login.
3. systemd deployment for HomeNAS only.
4. Overview with CPU, RAM and uptime.
5. System and temperature metrics.
6. perf RAPL collector and Power page.
7. Storage and SMART read-only monitoring.
8. Network metrics.
9. Read-only Mihomo and Tailscale pages.
10. Seafile health monitoring.
11. Service Inventory.
12. Alerts.
13. Backup, update and rollback.

Keep each phase runnable and testable.

### Step 5 — Protect the existing NAS

The following are protected existing services/configurations:
- Seafile CE.
- Mihomo / Clash Meta.
- Tailscale.
- Existing reverse proxy.
- Existing firewall and routes.
- Existing storage layout and data.

Do not reinstall, overwrite, migrate, restart, reconfigure or remove any of them.

Do not expose a new public port. Prefer the existing reverse proxy or a private interface selected after audit. Default to loopback binding unless the actual LAN/Tailscale access design has been confirmed.

Any change that requires root or may affect an existing service, network, disk, firewall, reverse proxy or third-party configuration must be presented with:
1. Exact proposed commands/files.
2. Why the change is needed.
3. Expected impact.
4. Rollback procedure.

Wait for explicit user approval before applying such changes.

### Step 6 — Engineering constraints

- API must run as a non-root user.
- Collector must be separate and have minimum necessary privileges.
- Never provide arbitrary shell execution.
- Never expose Docker Socket.
- Never send Mihomo Secret to frontend.
- Do not use unrestricted sudo rules.
- Use `CAP_PERFMON` only if validated and actually required.
- SMART access must use a narrow, reviewed permission strategy.
- Use SQLite WAL and batch writes.
- Use UTC timestamps.
- Missing metrics are NULL/unavailable, not zero.
- Do not sum overlapping RAPL domains.
- Do not label CPU Package power as whole-system input power.
- No Redis, Celery, Kubernetes or mandatory Docker in v1.
- Do not introduce dependencies without a clear need.

### Step 7 — Test and verify

Run automated tests and real host checks where safe.

At each phase report:
- Files created/changed.
- Features completed.
- Tests executed and results.
- Deployment state.
- CPU and memory overhead.
- Security review.
- Remaining issues.
- Rollback procedure.

Do not claim a service is deployed unless it has actually been started and health-checked on the NAS.

## Definition of done

HomeNAS is complete when it:
- Runs independently of Seafile, Mihomo, Tailscale and Docker.
- Displays real system, power, storage and network metrics.
- Monitors existing Mihomo, Tailscale and Seafile without altering them.
- Maintains a service inventory.
- Provides deduplicated alerts.
- Works from the LAN and existing Tailnet path.
- Has local admin authentication.
- Has backup, update and rollback procedures.
- Does not expose a public management port.
- Does not disrupt any existing NAS service.

Start now with Step 1 and Phase 0. Do not make changes to the existing NAS during the audit.
