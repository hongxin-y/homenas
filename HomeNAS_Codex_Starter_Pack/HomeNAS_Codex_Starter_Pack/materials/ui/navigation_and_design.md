# HomeNAS UI Navigation & Design Notes

## Navigation
- 总览
- 系统
- 功耗
- 存储
- 网络
- VPN
  - Mihomo
  - Tailscale
- 服务
- 告警
- 设置

## Design direction
- Dark-first professional operations dashboard.
- Chinese default labels.
- Responsive desktop/tablet/mobile.
- Clear hierarchy: summary first, detail on secondary pages.
- Consistent spacing, typography and chart units.
- Avoid decorative gradients, excessive animation and too many cards.
- Show units explicitly: %, °C, W, J, kWh, MiB/s, GiB.
- Distinguish measured values, estimates and unavailable values.
- Show sample time / last updated time.
- Unknown is neutral, not healthy.
- Red for critical; amber for warning; green only for verified healthy state.

## Overview layout
1. Top status row: NAS online, uptime, last update.
2. Metric cards: CPU, RAM, temperature, Package power, disk, network.
3. Time-series charts: CPU, Package power, network traffic.
4. Service status: Seafile, Mihomo, Tailscale, HomeNAS, registered services.
5. Active alerts and recent events.

## Power page
- Main chart: Package watts over time.
- Separate domain series or tabs for Cores, GPU, DRAM and PSys.
- Domain labels must explain that domains are not additive.
- PSys is experimental until independently validated.
- Daily energy is RAPL-domain energy, not wall-socket energy.
- Never show a precise electricity bill from CPU Package readings.

## Storage page
- Disk cards with model, capacity, temperature and SMART state.
- Filesystem cards with used/free/total.
- Detail view for SMART attributes.
- No destructive controls.

## VPN page
Separate Mihomo and Tailscale sections. Explain that outbound proxy and remote access VPN are different functions.

## Services page
Columns:
- Name
- Category
- Deployment
- Discovery source
- Status
- Health
- CPU / RAM (if attributable)
- Last checked
- Access URL

Unknown service identity must be labelled unclassified.
