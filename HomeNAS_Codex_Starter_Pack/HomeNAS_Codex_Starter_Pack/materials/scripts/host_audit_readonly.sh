#!/usr/bin/env bash
# HomeNAS Phase 0 host audit.
# Read-only: no package installation, file edits, service restarts or network changes.
# Review and redact output before sharing; it may contain hostnames, IPs, device models and service names.

set -u
export LC_ALL=C

section() { printf '\n\n========== %s ==========\n' "$1"; }
run_if() {
  local label="$1"; shift
  printf '\n--- %s ---\n' "$label"
  if command -v "$1" >/dev/null 2>&1; then "$@" 2>&1 || true
  else printf 'Not installed: %s\n' "$1"; fi
}

section "HOST IDENTITY"
run_if "hostname" hostname
run_if "kernel" uname -a
[ -r /etc/os-release ] && cat /etc/os-release

section "CPU AND MEMORY"
run_if "lscpu" lscpu
run_if "memory" free -h

section "BLOCK DEVICES AND FILESYSTEMS"
run_if "lsblk" lsblk -o NAME,SIZE,MODEL,TYPE,FSTYPE,MOUNTPOINTS
run_if "df" df -hT
run_if "findmnt" findmnt -o TARGET,SOURCE,FSTYPE,OPTIONS

section "THERMAL SENSORS"
if [ -d /sys/class/thermal ]; then
  for f in /sys/class/thermal/thermal_zone*/type /sys/class/thermal/thermal_zone*/temp; do
    [ -r "$f" ] && printf '%s: %s\n' "$f" "$(cat "$f" 2>/dev/null)"
  done
fi
run_if "sensors" sensors

section "POWER SUPPLY"
if [ -d /sys/class/power_supply ]; then
  for d in /sys/class/power_supply/*; do
    [ -d "$d" ] || continue
    echo "Device: $(basename "$d")"
    for f in type status capacity voltage_now current_now power_now energy_now charge_now; do
      [ -r "$d/$f" ] && printf '  %s: %s\n' "$f" "$(cat "$d/$f" 2>/dev/null)"
    done
  done
fi

section "PERF AND RAPL"
run_if "perf version" perf version
if command -v perf >/dev/null 2>&1; then
  echo "--- RAPL events ---"
  perf list 2>&1 | grep -E 'power/energy-(pkg|cores|gpu|ram|psys)' || true
  echo "--- Short read-only Package event probe (may fail due to permissions) ---"
  timeout 6 perf stat -a -I 1000 -x, -e power/energy-pkg/ -- sleep 3 2>&1 || true
fi
if [ -d /sys/class/powercap ]; then
  echo "--- powercap files ---"
  find /sys/class/powercap -maxdepth 3 -type f \\( -name name -o -name energy_uj \\) -print 2>/dev/null || true
fi

section "SMART AND NVME TOOLS"
run_if "smartctl version" smartctl --version
run_if "smartctl scan" smartctl --scan
run_if "nvme version" nvme version

section "NETWORK"
run_if "interfaces" ip -brief address
run_if "link counters" ip -s link

section "RELEVANT SYSTEMD SERVICES"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --no-pager --type=service --all 2>&1 | grep -Ei 'seafile|seahub|mihomo|clash|tailscale|nginx|caddy|apache|docker|homenas' || true
fi

section "TAILSCALE"
run_if "tailscale version" tailscale version
if command -v tailscale >/dev/null 2>&1; then
  echo "--- tailscale status (peer names and addresses may be sensitive) ---"
  tailscale status 2>&1 || true
fi

section "MIHOMO PROCESS (NO CONFIG CONTENT)"
if command -v pgrep >/dev/null 2>&1; then
  pgrep -a -x mihomo 2>/dev/null | sed -E 's/(--secret[ =])[^ ]+/\\1[REDACTED]/g' || true
  pgrep -a -x clash 2>/dev/null | sed -E 's/(--secret[ =])[^ ]+/\\1[REDACTED]/g' || true
fi

section "DOCKER"
run_if "docker version" docker version --format '{{.Server.Version}}'
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}' 2>&1 || true
fi

section "LISTENING PORTS"
run_if "ss listening sockets" ss -lntup

section "END"
echo "Audit finished. No configuration was intentionally modified."
echo "Review and redact hostnames, IPs, device details and service names before sharing."
