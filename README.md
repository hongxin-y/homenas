# HomeNAS Dashboard

HomeNAS 是一个只读优先的 NAS 监控面板第一版。它在本地开发电脑上运行真实的 CPU、内存、磁盘和网络采集；对 Linux NAS 上需要额外权限或外部服务的能力明确显示 `Unavailable`，不会把开发电脑误认为目标 NAS。

## 已完成

- Phase 0 只读环境审计报告（见 `docs/`）。
- FastAPI API、SQLite WAL、内存实时缓存和后台采集器。
- 本地管理员登录（默认仅绑定回环地址；本地演示密码为 `admin`，生产必须通过环境变量覆盖）。
- 总览、系统、功耗、电池、存储、网络、VPN、服务清单、告警接口和响应式中文界面。
- RAPL/perf CSV 解析器、计数器重置处理、缺失传感器处理和 API 测试。
- Mihomo、Tailscale、Seafile、Docker、SMART、perf 等外部能力均为只读探测；没有通用 Shell 执行接口。
- `frontend/src/main.ts` 提供 TypeScript 构建入口；当前浏览器 UI 不依赖 CDN，构建产物由 `npm run --prefix frontend build` 生成。

## 本地运行

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python scripts\audit_environment.py
$env:HOMENAS_ADMIN_PASSWORD = "change-this-local-password"
python -m uvicorn homenas.main:app --app-dir backend --host 127.0.0.1 --port 8787
```

前端构建依赖安装后执行：

```powershell
npm install --prefix frontend
npm run --prefix frontend build
```

打开 <http://127.0.0.1:8787>，使用 `admin` 和 `HOMENAS_ADMIN_PASSWORD` 登录。未设置变量时仅为本地演示默认值 `admin`。

运行测试：

```powershell
python -m pytest
python scripts\\smoke_test.py  # 无法联网安装 FastAPI 时的标准库 smoke test
npm run --prefix frontend typecheck
npm run --prefix frontend build
```

如果当前机器无法连接 PyPI，直接运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\run-local.ps1`。脚本会优先使用 FastAPI；依赖缺失时自动切换到同一 API 契约的标准库 fallback server，仍可完成页面、登录和总览接口的本地验收。

真实 NAS 服务探测默认关闭。只有在目标 NAS 上完成权限和配置审计后，才通过 `HOMENAS_ENABLE_EXTERNAL_PROBES=1` 开启固定的只读 Tailscale、Mihomo Controller、Seafile health、systemd 和 Docker 探测；浏览器不能传入命令、URL 或 Secret。

功耗页按 CPU Package RAPL 计算当前每小时、每日和年化电费，默认电价为 `0.60` 元/kWh，可通过 `HOMENAS_ELECTRICITY_PRICE_CNY_PER_KWH` 调整；日期区间查询仍只按 Package 计费，不把其他 RAPL domain 相加。VPN 页支持 Controller 节点切换的受控接口和规则草稿校验；`HOMENAS_ENABLE_MIHOMO_MUTATIONS` 默认关闭，保持 NAS 上 Mihomo 只读。

## 安全边界

项目暂不部署到 NAS，也不修改任何现有服务配置。Mihomo Secret 永远只作为服务器端配置存在，当前第一版甚至不读取 Secret；前端只收到固定业务状态。API 默认监听 `127.0.0.1`，后续若接入现有反向代理，需要在目标 NAS 审计后单独批准。

