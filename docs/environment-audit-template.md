# Phase 0 环境审计模板

真实 NAS 审计必须在目标主机上执行，不能把开发电脑结果当作 NAS 事实。建议记录：

- Debian/Linux 版本、Kernel、CPU、内存、运行时间。
- 磁盘拓扑、文件系统、挂载点和可用空间。
- `perf` 版本、RAPL 事件、权限结果和电池/温度传感器。
- SMART/NVMe 工具和权限结果。
- 物理、VPN、容器接口及累计计数器。
- Mihomo、Tailscale、Seafile、Docker、systemd 和反向代理状态。

审计报告可能含主机名、IP、设备型号、服务路径和端口，默认作为本地私密产物保存，不应直接发布到 public repository。

本项目的只读审计脚本：

```powershell
python scripts\audit_environment.py
```

