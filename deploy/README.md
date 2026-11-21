# 部署模板（未执行）

`systemd/` 下的 unit 仅是未来在目标 NAS 上评审后的模板，本次没有复制、启用或重启任何 unit。当前本地版为便于单进程测试，API 内嵌 Collector；如果未来启用独立 Collector，需要先完成快照/IPC 接口切换，不能直接同时启用两个采集循环。

模板默认：

- 使用专用非 root 用户 `homenas`。
- API 只监听 `127.0.0.1:8787`，通过现有反向代理接入。
- 采用 `NoNewPrivileges`、`ProtectSystem=strict`、`ProtectHome` 和固定可写目录。
- 没有 Docker Socket、任意 Shell 或磁盘写入权限。
- Perf RAPL 采集通过独立的 `homenas-perf-helper.service` 运行固定的 root perf 子进程，并只通过 `/run/homenas-perf/perf.sock` 转发机器可解析输出；HomeNAS API 仍以非 root 用户运行。这样不需要降低 `kernel.perf_event_paranoid`，也不把 `CAP_SYS_ADMIN` 交给 Web API。
- 电费估算默认使用上海居民一户一表分时电价一档：峰时 06:00–22:00、谷时 22:00–06:00；用 `HOMENAS_ELECTRICITY_TARIFF_TIER=1|2|3` 选择年度档位。时间段和年化统计只按 CPU Package 能耗计算，并按北京时间拆分峰/谷。`HOMENAS_ELECTRICITY_PRICE_CNY_PER_KWH` 仅作为没有分时明细时的平价后备值。
- Mihomo 节点切换和单条规则运行时启停接口需要单独设置 `HOMENAS_ENABLE_MIHOMO_MUTATIONS=1`；当前预览 unit 默认不设置该变量。节点切换会实时改变流量路径，可切回上一个节点；规则启停通过 Mihomo `/rules/disable`，核心重启后恢复配置文件状态。若配置文件可由 API 用户写入，规则编辑器会先把原配置备份到 `runtime/mihomo-backups/`，再原子替换顶层 `rules` 列表并请求 Controller `/configs` reload；reload 失败会自动回滚。
- 当前 NAS 的配置是 `root:root 600`，因此推荐使用 `homenas-mihomo-helper.service.example`：它是一个固定路径、固定操作的 root helper，只接受规则数组，通过 `/run/homenas-mihomo/rules.sock` 给 `hongxin` API 使用；它自己负责备份、原子写回和 `/configs?force=true` reload，API 进程仍保持 `hongxin`，不会拿到 root 或 Mihomo Secret。helper 的写权限只覆盖 `/etc/mihomo` 和 `/var/lib/homenas`，启用前仍需审查订阅是否会覆盖本地 rules 以及 Controller Secret 的实际路径。

本地 NAS 预览若要启用该方案，需要一并评审并安装 `homenas-perf-helper.service.example`、`homenas-mihomo-helper.service.example` 和 `homenas-preview-capperf.service.example`，以及 root-owned `/usr/local/libexec/homenas-perf-helper.py`、`/usr/local/libexec/homenas-mihomo-helper.py`。前者只运行固定的五个 RAPL 事件，Mihomo helper 只处理固定的 rules 写回，预览 API 仍以 `hongxin` 运行。安装前需停用同端口的用户级 `homenas-preview.service`；回滚时先停止预览 unit，再停止 Mihomo helper 和 perf helper，移除 helper 文件和 unit，最后恢复用户级服务即可。helper 自己写入的 Mihomo 备份保留在 `/var/lib/homenas/mihomo-backups`，需要另行清理时再做。

在已经安装的预览 unit 上，只有完成影响与回滚评审并收到明确授权后才执行：

```ini
# sudo systemctl edit homenas-preview-capperf.service
[Service]
Environment=HOMENAS_ENABLE_MIHOMO_MUTATIONS=1
Environment=HOMENAS_MIHOMO_HELPER_SOCKET=/run/homenas-mihomo/rules.sock
```

保存后执行 `sudo systemctl daemon-reload && sudo systemctl restart homenas-preview-capperf.service`。回滚时删除该 drop-in 中的环境变量并重启 HomeNAS，再停止 helper；这不会自动修改已经写入的 Mihomo 配置，必要时用 helper 生成的备份恢复。规则按钮控制的是持久化 rules，Mihomo reload 失败时会自动回滚。

root helper 的安装、启用、重启或修改 `/etc/mihomo` 都属于高权限/现有服务变更，本仓库只提供模板，必须先给出具体影响和回滚方案并获得明确授权。

目标 NAS 上需要先完成 perf、SMART、Seafile、Mihomo Controller 和反向代理的权限/路径审计，再另行提交具体安装、影响和回滚方案。未经批准不得执行这些模板。

