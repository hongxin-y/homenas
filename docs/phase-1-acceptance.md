# Phase 1 本地验收记录

日期：2026-11-08（Asia/Shanghai）

## 修改文件范围

- `backend/homenas/`：配置、SQLite WAL、认证、采集器、指标采集、FastAPI API 和离线 fallback server。
- `backend/tests/`：指标解析、计数器重置、网络分类、SQLite WAL、API 和 fallback smoke 测试。
- `frontend/`：响应式中文单页面板，含登录、总览、系统、功耗、存储、网络、VPN、服务、告警页面。
- `frontend/src/main.ts`、`frontend/package.json`：TypeScript 前端源码和离线可复现构建配置；当前 UI 保持零运行时依赖，避免本地测试依赖 CDN。
- `deploy/systemd/`：非 root API/Collector unit 模板，仅保存未执行的部署形态。
- `backend/homenas/integrations.py`：固定参数、超时、只读的 Tailscale/Mihomo/Seafile/systemd/Docker 探测。
- `scripts/audit_environment.py`：只读环境审计。
- `scripts/smoke_test.py`：不依赖联网安装的本地验收脚本。
- `docs/`：脱敏后的 Phase 0 说明、服务资产清单、网络访问、风险和本记录；真实主机审计原件保存在本地 Artifacts，不进入公开仓库。

## 功能状态

| 能力 | 状态 | 说明 |
|---|---|---|
| 总览 | 已完成 | CPU、内存、温度、存储、网络、服务和告警 |
| 系统 | 已完成 | CPU、每核心、内存、Swap、运行时间、平台信息 |
| 功耗 | 第一版只读 | perf/RAPL 解析器已实现；本地未启动特权 collector，显示 Unavailable |
| 存储 | 已完成 | 文件系统只读使用率；SMART 明确显示待 NAS 审计 |
| 网络 | 已完成 | 物理、虚拟、Tailscale、loopback 分开，首个采样显示等待采样 |
| VPN | 第一版只读 | Mihomo/Tailscale 只做固定二进制探测，不读取 Secret、不执行控制命令 |
| 服务清单 | 已完成 | 固定白名单条目，外部部署信息未知时显示 unknown |
| 告警 | 已完成 | 内存、温度、文件系统阈值；SQLite 去重、恢复时间和 alert_events 历史 |
| 本地认证 | 已完成 | 管理员登录、HttpOnly SameSite session cookie；默认仅回环地址 |

## 测试结果

- `python scripts\\smoke_test.py`：通过。
- Smoke 覆盖 perf CSV 缺失值、计数器归零、网络采集、SQLite 数据路径、健康端点、登录和总览端点。
- FastAPI/pytest 依赖因当前开发环境无法连接 PyPI 未安装；对应代码和测试已保留，联网环境执行 `python -m pip install -e ".[test]"` 后可运行。
- 本地 fallback server 已用 `127.0.0.1:8788` 手动检查：健康端点 200、静态首页 200、登录成功、总览返回 CPU/存储数据。
- `npm run --prefix frontend typecheck`：通过。
- `npm run --prefix frontend build`：通过。

## 真实 NAS Phase 0

- 通过现有 `ssh nas` 完成一次性只读审计；真实主机报告为本地产物，不进入公开仓库。
- 已确认 Debian 13、i7-7700HQ、RAPL 事件、Mihomo/Tailscale/Docker 服务和数据盘使用率；perf 权限、SMART、Seafile 健康端点和 Docker 容器清单仍按报告标记为受限或未知。
- 未修改 NAS 文件、权限、sysctl、systemd、服务、端口、防火墙、路由或网络接口。

## 部署与开销

- NAS 部署：未执行。没有修改 systemd、反向代理、端口、防火墙、路由、磁盘或现有服务。
- 本地服务：可用 `scripts\\run-local.ps1` 启动；无 FastAPI 时自动使用标准库 fallback。
- 资源开销：采集周期默认为 5 秒，内存实时缓存最多 60 个快照，SQLite 只写少量聚合指标。本地 Windows fallback 进程短时观测约 32.8 MiB working set、20.4 MiB private memory、约 1.66 CPU 秒；这不是 NAS 长期基准，目标主机上线前仍需补测。

## 安全检查

- API 默认绑定 `127.0.0.1`。
- 没有任意 Shell API、YAML 编辑、服务启停、磁盘修复或网络配置接口。
- Mihomo Secret 不读取、不写日志、不下发浏览器。
- 登录 session 使用 HttpOnly、SameSite cookie；前端不把 session token 写入 localStorage。
- 缺失外部服务不会导致整个 Dashboard 失败；缺失值保持 `null`/`Unavailable`。

## 回滚与遗留

- 当前只删除本地 `runtime/` 和停止本地进程即可回滚；NAS 没有变更。
- 遗留：目标 Debian NAS 本机审计、perf 长生命周期采集、SMART 窄权限方案、Mihomo Controller 白名单、Tailscale/Seafile 健康端点、反向代理接入、真实机 CPU/RAM 基准。
- 前端当前使用 TypeScript + 零运行时依赖 DOM 渲染以保证离线本地验收；Vue 3 包不在当前 npm 离线缓存中，未强行引入无法构建的依赖。API、数据模型和页面边界已保持可迁移到 Vue 3。

