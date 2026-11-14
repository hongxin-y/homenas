# 部署模板（未执行）

`systemd/` 下的 unit 仅是未来在目标 NAS 上评审后的模板，本次没有复制、启用或重启任何 unit。当前本地版为便于单进程测试，API 内嵌 Collector；如果未来启用独立 Collector，需要先完成快照/IPC 接口切换，不能直接同时启用两个采集循环。

模板默认：

- 使用专用非 root 用户 `homenas`。
- API 只监听 `127.0.0.1:8787`，通过现有反向代理接入。
- 采用 `NoNewPrivileges`、`ProtectSystem=strict`、`ProtectHome` 和固定可写目录。
- 没有 Docker Socket、任意 Shell 或磁盘写入权限。
- Perf RAPL 采集通过独立的 `homenas-perf-helper.service` 运行固定的 root perf 子进程，并只通过 `/run/homenas-perf/perf.sock` 转发机器可解析输出；HomeNAS API 仍以非 root 用户运行。这样不需要降低 `kernel.perf_event_paranoid`，也不把 `CAP_SYS_ADMIN` 交给 Web API。

本地 NAS 预览若要启用该方案，需要一并评审并安装 `homenas-perf-helper.service.example` 和 `homenas-preview-capperf.service.example`，以及 root-owned `/usr/local/libexec/homenas-perf-helper.py`。前者只运行固定的五个 RAPL 事件，后者仍以 `hongxin` 运行。安装前需停用同端口的用户级 `homenas-preview.service`；回滚时先停止预览 unit，再停止 helper、移除 helper 文件和 unit，最后恢复用户级服务即可。

目标 NAS 上需要先完成 perf、SMART、Seafile、Mihomo Controller 和反向代理的权限/路径审计，再另行提交具体安装、影响和回滚方案。未经批准不得执行这些模板。

