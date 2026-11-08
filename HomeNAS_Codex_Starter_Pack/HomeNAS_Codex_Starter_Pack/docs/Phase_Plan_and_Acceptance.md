# HomeNAS — Phase Plan & Acceptance Checklist

## Phase 0 — Read-only environment audit

### Inspect

- Confirm the shell is on the Debian NAS, not the Codex workstation.
- Debian/kernel/CPU/RAM.
- Disk topology, filesystems, mount points, free space.
- SMART and NVMe tool availability.
- perf version, permissions and RAPL events.
- Temperature sensors.
- Network interfaces and addresses.
- Tailscale status and binary path.
- Mihomo process and controller configuration location (do not print secrets).
- Seafile deployment type, service names and health endpoint.
- Docker availability.
- Existing reverse proxy and listener ports.
- Existing firewall state (read-only).

### Deliverables

- `docs/environment-report.md`
- `docs/service-inventory-initial.md`
- `docs/network-and-access-report.md`
- `docs/risks-and-decisions.md`

### Acceptance

- No existing configuration changed.
- No packages installed.
- No services restarted.
- No firewall or route changed.
- Report distinguishes confirmed facts from unknowns.

## Phase 1 — Foundation and Overview

- Vue 3 + TypeScript + Vite + Naive UI.
- FastAPI backend.
- SQLite WAL and migrations.
- Local administrator authentication.
- Responsive sidebar and Overview page.
- API/Collector systemd units.
- Health endpoint and basic logs.

Acceptance:
- HomeNAS starts and restarts independently.
- Login works.
- Overview displays actual CPU/RAM/system uptime.
- No existing service is modified.
- Data survives HomeNAS restart.

## Phase 2 — System and Power

- CPU per-core and total.
- Memory and Swap.
- Temperature sensors.
- Battery telemetry.
- perf RAPL collector.
- Power history and charts.
- Missing-data quality indicators.

Acceptance:
- Package power is read from verified perf events.
- Actual elapsed time is used.
- Invalid or missing values are not shown as zero.
- Package is not mislabeled as whole-system power.
- Collector restart does not corrupt historical data.

## Phase 3 — Storage and Network

- Disk and partition discovery.
- Filesystem usage.
- SMART read-only data.
- Per-interface network counters.
- Traffic charts.

Acceptance:
- No disk write/repair operation is possible from UI.
- Permission errors are shown accurately.
- Physical and virtual interface traffic is not blindly double-counted.

## Phase 4 — VPN

First: read-only Mihomo and Tailscale status.

Then, only after explicit approval and successful read-only validation:
- Mihomo node/group selection.
- Delay testing.
- Connection close.
- Proxy mode switch.

Acceptance:
- Mihomo Secret never reaches browser.
- Tailscale configuration is unchanged.
- Mihomo configuration is not overwritten.
- All control actions are audited.

## Phase 5 — Services and Alerts

- systemd discovery.
- Optional Docker discovery.
- Manual service manifest registration.
- Health checks.
- Resource usage where attribution is reliable.
- Alert thresholds and history.

Acceptance:
- Unknown services are labelled unclassified.
- Port scan does not establish service identity.
- Missing Docker does not break dashboard.
- Alerts deduplicate and recover correctly.

## Phase 6 — Release hardening

- Backup/restore.
- Update script.
- Rollback.
- Log rotation.
- Database retention.
- CPU/RAM overhead measurement.
- Mobile browser verification.
- Security review.

## Release gate

Do not call the project complete until:

- HomeNAS works without Seafile.
- HomeNAS works without Mihomo.
- HomeNAS works without Tailscale.
- HomeNAS works without Docker.
- Missing sensors do not crash the application.
- Existing services remain unchanged.
- LAN and existing Tailnet access work as configured.
- No public management port is introduced.
- Database and configuration can be backed up and restored.
