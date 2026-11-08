# HomeNAS Codex Starter Pack

版本：1.0

## 包内结构

- `docs/HomeNAS_Development_Spec.md`：完整开发规格书。
- `docs/Architecture_and_Data_Flow.md`：系统架构和数据流。
- `docs/Phase_Plan_and_Acceptance.md`：开发阶段与验收清单。
- `codex/GOAL_MODE_PROMPT.md`：可直接粘贴给 Codex Goal 模式的指令。
- `materials/`：配置示例、服务 manifest、systemd 模板、SQL 参考、API 草案、UI 指南和只读审计脚本。

## 使用顺序

1. 解压。
2. 把整个目录交给 Codex，或在项目仓库中放入 `docs/`、`materials/`。
3. 在 Codex Goal 模式粘贴 `codex/GOAL_MODE_PROMPT.md`。
4. 先完成 Phase 0 只读环境审计。
5. 审阅环境报告后，再批准 HomeNAS 自身的部署改动。

## 重要边界

本包只针对 HomeNAS。AI PPT、Seafile Android、Seafile 身份认证改造不在本期范围。

不得擅自修改 Seafile、Mihomo、Tailscale、反向代理、防火墙、路由、磁盘分区或现有数据。

审计输出可能包含主机名、IP、设备型号和服务信息，分享前请检查并脱敏。
