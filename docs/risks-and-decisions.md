# 风险与决策

+## 已做决策
+
+1. 先完成 Phase 0 只读审计，再考虑 NAS 部署。
+2. API 和 Collector 分离；本地版 Collector 使用 psutil，perf/RAPL 仅保留解析器和诊断状态。
+3. 缺失值使用 `null`/`Unavailable`，不以 0 代替。
+4. Mihomo、Tailscale、Seafile、SMART、Docker 均为可选依赖，缺失时页面继续工作。
+5. 所有管理能力当前关闭；没有任意命令执行、YAML 编辑、服务重启、路由或防火墙修改。
+
+## 待目标 NAS 审计后决定
+
+- perf 权限、RAPL 事件和长生命周期采集方案。
+- SMART/nvme 的窄权限读取方案。
+- Seafile 的实际健康端点和部署方式。
+- Mihomo Controller 地址、只读 API 白名单和 Secret 存放位置。
+- 现有反向代理接入位置。
+
+## 回滚
+
+当前没有 NAS 变更；停止本地 uvicorn 进程并删除 `runtime/` 即可清理本地运行状态。未来任何 NAS 变更必须先备份自身配置、明确影响和回滚命令，并单独批准。
