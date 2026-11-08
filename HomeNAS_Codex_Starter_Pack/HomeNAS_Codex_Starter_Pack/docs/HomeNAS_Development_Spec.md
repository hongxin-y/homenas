# HomeNAS Dashboard — 技术开发规格书

**版本：** 1.0  
**目标环境：** Debian 13 / Linux 6.12 / Intel i7-7700HQ（4C/8T）  
**部署：** Debian 原生 systemd  
**默认语言：** 简体中文

## 1. 项目定位

HomeNAS 是现有 Debian NAS 的轻量级管理与监控面板，负责：

1. 系统与硬件监控：CPU、内存、温度、功耗、磁盘、网络。
2. VPN 状态与管理：Mihomo 管理、Tailscale 状态监控。
3. 现有服务监控：Seafile CE、systemd 服务、可选 Docker 容器。
4. 服务资产清单：记录 NAS 上部署了哪些服务、部署方式、运行状态和访问入口。
5. 告警与历史指标。

HomeNAS 不负责其他服务的业务逻辑，不负责安装、升级或卸载其他应用。

### 本期不做

- AI PPT 后端或客户端。
- Seafile Android Fork 改造。
- Seafile 用户认证替代或统一身份平台。
- Tailscale 重装、重新配置或 ACL 修改。
- Mihomo 重装或覆盖现有配置。
- Docker 编排平台或应用商店。
- 任意 Shell / 任意命令执行。
- 磁盘分区、格式化、文件系统修复、RAID 操作。
- 自动开放公网端口或修改路由器。

未来自研应用只通过 Service Inventory 登记和监控，不由 HomeNAS 托管。

## 2. 已知环境与必须验证的事实

已知：

- Debian 13，Linux Kernel 6.12.113。
- Intel Core i7-7700HQ，4 核 8 线程。
- 笔记本电脑改造 NAS，带内置电池。
- Seafile Community Edition。
- Mihomo / Clash Meta 已集成。
- Tailscale 已部署，远程访问已经可用。
- `/sys/class/powercap` 有 RAPL domain 目录，但没有可用的 `energy_uj` 文件。
- `perf` 的 RAPL PMU 事件可读取：
  - `power/energy-pkg/`
  - `power/energy-cores/`
  - `power/energy-gpu/`
  - `power/energy-ram/`
  - `power/energy-psys/`

Codex 必须在目标 NAS 主机上重新验证。若 Codex 运行环境不是 NAS 本机，不能把开发电脑环境误认为 NAS 环境。

以下内容不得预设，必须审计确认：

- Seafile 实际部署方式、服务名称、端口和数据路径。
- Mihomo Controller 地址、监听范围和 Secret 位置。
- Tailscale 二进制路径和服务名。
- 是否安装 Docker。
- 是否已有 Nginx、Caddy 或其他反向代理。
- SMART 是否可由非 root 用户读取。
- 温度传感器是否可用。
- 当前磁盘分区、挂载点和可用空间。

## 3. 页面与导航

左侧导航：

1. 总览 Overview
2. 系统 System
3. 功耗 Power
4. 存储 Storage
5. 网络 Network
6. VPN
   - Mihomo
   - Tailscale
7. 服务 Services
8. 告警 Alerts
9. 设置 Settings

中文为默认语言。桌面优先，同时兼容平板和手机浏览器。风格专业、克制、信息层级清晰。

### 3.1 总览

展示：

- CPU 总使用率、内存使用率、CPU 温度、CPU Package 功耗。
- 磁盘使用率、网络实时上传 / 下载。
- Seafile、Mihomo、Tailscale、HomeNAS 状态。
- 当前告警数量。

实时图表：
- CPU 使用率：最近 5 分钟。
- CPU Package 功耗：最近 5 分钟。
- 网络上下行：最近 5 分钟。

### 3.2 系统监控

CPU：总使用率、每核心使用率、频率（可用时）、Load Average。  
内存：总量、已用、可用、缓存、Swap。  
温度：CPU、主板（如有传感器）、硬盘（如支持）。  
系统：Uptime、Debian 版本、Kernel 版本、CPU 型号。  
进程：CPU TOP 10、内存 TOP 10。

所有指标必须来自真实采集。不可用时显示 `Unavailable`，不得用估算值填充。

### 3.3 功耗监控

使用 `perf` 作为 RAPL 主要采集方式，不再把 sysfs `energy_uj` 作为前置条件。

已验证可用的事件候选：
- Package
- Cores
- GPU
- DRAM
- PSys

诊断命令：

```bash
sudo perf stat -a -I 1000 \
  -e power/energy-pkg/ \
  -e power/energy-cores/ \
  -e power/energy-gpu/ \
  -e power/energy-ram/ \
  -e power/energy-psys/ \
  -- sleep 10
```

正式 Collector 应使用长生命周期采集进程或等效低开销机制，不允许每秒启动一个新的 perf 进程。

先验证目标 perf 版本的机器可读输出，再实现解析器。优先评估 `perf stat -x,` 等格式；不要用固定列号解析人类可读文本。

计算：

\[
P_W = \frac{\Delta E_J}{\Delta t_s}
\]

\[
E_{kWh} = \frac{\sum \Delta E_J}{3,600,000}
\]

规则：
- Package 是主要 CPU 封装功耗指标。
- Cores、GPU、DRAM 是不同 RAPL domain，不得与 Package 简单相加。
- PSys 标记为实验性指标，未通过独立功率计验证前不得宣称为整机插座输入功率。
- 不得把 CPU Package 功耗标记为整机功耗。
- 不得用 CPU Package 数据推算精确民用电费。
- 不要求用户拔掉 AC 适配器。
- 使用实际采样时间差。
- 处理权限不足、事件不存在、采样缺失、计数器重置和 Collector 重启。
- 缺失值存为 NULL / unavailable，而不是 0。

电池数据通过 `/sys/class/power_supply/` 读取（如可用）：状态、电量百分比、电压、电流、电荷或能量字段。电池满电且 `current_now=0` 不代表整机没有耗电，也不能据此推算 AC 输入功率。

### 3.4 存储监控

发现物理磁盘、分区、文件系统和挂载点。

采集：型号、容量、使用率、温度、SMART 健康状态、通电时间、读写速率、IOPS（可可靠获得时）。

SMART 重点属性：
- Reallocated Sector Count。
- Current Pending Sector。
- Offline Uncorrectable。
- Device error log。
- NVMe Critical Warning。
- NVMe Media Errors。

只读原则：不格式化、不分区、不执行 `wipefs`、不执行文件系统修复、不做 RAID 重建、不改变挂载配置。

SMART 需要高权限时，优先使用经过评估的窄权限辅助机制。不得给 Web API root 权限，不得配置 `sudo smartctl *` 这种宽泛免密规则，也不得把普通 Web 用户加入具有广泛磁盘访问权限的组。

### 3.5 网络监控

按网卡采集：接口名称、IPv4/IPv6、MAC、上传/下载速率、累计字节、错误包和 TCP 连接数量（可用时）。

区分物理网卡、Tailscale 虚拟接口、Loopback 和其他虚拟接口。不要把物理网卡和 Tailscale 虚拟网卡计数简单相加作为总流量。处理接口重命名、消失、系统重启和计数器归零。

### 3.6 VPN

Mihomo 与 Tailscale 是不同用途：
- Mihomo：NAS 出站代理。
- Tailscale：设备到家庭 NAS 的远程访问网络。

#### Mihomo 第一阶段只读

运行状态、版本、代理模式、代理组、节点列表、当前选中节点、延迟、实时流量、当前连接、Provider 状态。

第二阶段在只读集成稳定后，再考虑切换代理组节点、测试节点延迟、关闭单个连接、切换 Rule / Global / Direct 模式。

安全：
- Controller Secret 只存服务器端。
- 浏览器不得持有 Secret。
- 后端只开放固定、白名单化的业务接口。
- 不允许前端代理任意 Controller URL。
- 不允许任意 YAML 编辑。
- 所有控制操作必须有管理员权限和审计记录。
- 第一阶段不得自动修改 Mihomo 配置、重启服务或刷新 Provider。

#### Tailscale 第一阶段只读

本机在线状态、本机 Tailscale IP、版本、Peer 列表、在线/离线、Last seen、可获得的连接类型或延迟信息。

只调用只读状态命令或受支持接口。不得执行 `tailscale up/down/logout`，不得更改 ACL、路由、Auth Key 或 Tailnet 设置。

### 3.7 服务资产清单

发现来源：
1. systemd 服务。
2. Docker 容器（仅在 Docker 已安装时）。
3. 手动注册 YAML manifest。
4. HTTP Health Check。

每项展示名称、描述、分类、部署方式、版本（可获得时）、运行状态、Uptime、CPU/内存（可可靠关联时）、健康检查、访问入口、数据目录元信息、发现来源、身份确认状态。

端口扫描只能作为辅助线索，不能仅凭开放端口断定服务身份。

首批登记 Seafile CE、Mihomo、Tailscale、HomeNAS API、HomeNAS Collector 和其他实际发现的服务。

Docker 不存在时显示 Not Installed / Unavailable，不得导致整体功能失败。

不开发安装、启动、停止、卸载、升级其他应用的通用管理器。

### 3.8 Seafile CE 状态

只监控 HTTP 健康检查、相关 systemd/Docker 状态（按真实部署方式）、版本（可获取时）、可用性和相关进程。

不要修改 Seafile 数据库、内部存储结构、用户、资料库或配置。不要为 HomeNAS 重新实现 Seafile 登录。

### 3.9 告警

默认阈值（可配置）：
- 磁盘使用率 warning：85%。
- 磁盘使用率 critical：95%。
- CPU 温度 warning：85°C。
- CPU 温度 critical：95°C。
- 内存使用率 warning：90%。
- SMART 异常。
- Seafile 健康检查失败。
- Mihomo 不可用。
- Tailscale 本机离线。
- 已登记服务健康检查失败。

告警必须去重，包含严重级别、首次发生时间、最近发生时间、恢复时间、确认状态和历史记录。增加持续时间阈值与恢复滞回，避免短暂波动反复告警。第一版仅站内告警，ntfy 等推送作为后续可选项。

## 4. 技术架构

前端：
- Vue 3、TypeScript、Vite、Naive UI、ECharts。

后端：
- Python、FastAPI、Pydantic、SQLAlchemy（或等价轻量数据访问层）、SQLite。

采集：
- psutil、perf、sysfs、smartmontools、nvme-cli、lsblk/findmnt、systemd、Mihomo Controller API、Tailscale CLI。

部署：
- 原生 systemd。
- 不强制 Docker。
- 不使用 Kubernetes。
- 第一版不引入 Redis / Celery。

### 4.1 进程分离

建议：
- `homenas-api.service`
- `homenas-collector.service`

API 非 root，处理认证、查询、配置、告警和服务清单，不直接执行任意系统命令。

Collector 后台采集指标，不对外监听管理端口，仅获取实际需要的最小权限。

perf 优先评估 `CAP_PERFMON` 或其他窄权限方案，并在目标主机实测。不得未经评估修改全局 `perf_event_paranoid`。

SMART 若需要 root，使用固定命令、设备白名单和严格输入校验的辅助方案；不得给 Collector/API 一个可任意执行命令的 root 通道。

### 4.2 访问方式

目标访问范围：家庭局域网、现有 Tailscale Tailnet。

优先复用现有反向代理（若存在且适合）。

默认安全原则：
- 默认监听 `127.0.0.1`，经现有反向代理访问；或审计后绑定明确 LAN/Tailscale 私有地址。
- 不默认绑定 `0.0.0.0`。
- 不新增公网端口映射。
- 不自动改防火墙。
- 不自动改 Tailscale ACL。
- 不覆盖现有 Seafile 反向代理配置。

## 5. 数据模型与保留策略

SQLite 使用 WAL。所有时间戳 UTC 保存，前端转本地时间。

建议数据：
- `metric_samples`
- `metric_aggregates`
- `energy_records`
- `network_records`
- `disk_records`
- `service_registry`
- `service_status`
- `alerts`
- `alert_events`
- `users`
- `sessions`
- `audit_logs`
- `settings`

建议保留：

| 数据 | 保留 |
|---|---:|
| 1 秒实时缓存 | 内存 ring buffer，约 5 分钟 |
| 5 秒聚合 | 7 天 |
| 1 分钟聚合 | 90 天 |
| 1 小时聚合 | 2 年 |
| 每日能耗汇总 | 长期 |

不要把每秒所有指标永久写入 SQLite。使用单写入队列、批量写入、索引和后台清理，避免采集线程被数据库写入阻塞。

缺失数据使用 NULL，并保留 quality/source 信息。

## 6. 安全与权限

认证：
- 初始仅一个本地管理员。
- 使用 Argon2id 或同等级安全密码哈希。
- Session Cookie 使用 HttpOnly、SameSite；HTTPS 下启用 Secure。
- 登录限速。
- 禁止公开注册。
- 若采用 Cookie Session，所有写操作必须防 CSRF。
- 不把密码、Session Token、Mihomo Secret 写入日志。

权限：
- 普通页面只读。
- Mihomo 控制功能仅管理员。
- 系统控制能力第一版不开放。
- 所有变更操作写入审计日志。

运行：
- API 非 root。
- Collector 最小权限。
- 不暴露 Docker Socket。
- 不提供任意 Shell。
- 不把数据库暴露到网络。
- 不允许前端传入任意命令参数。

## 7. 部署与更新

建议目录（最终按磁盘布局确认）：

```text
/opt/homenas/
  backend/
  frontend/
  venv/
  scripts/

/etc/homenas/
  config.yaml
  secrets/

/var/lib/homenas/
  homenas.db
  backups/

/var/log/homenas/
```

不得假定 `/var/lib` 或 `/srv` 位于大容量数据盘。Phase 0 必须检查现有分区和可用空间。

手动更新脚本流程：
1. 备份数据库和配置。
2. 获取新代码。
3. 更新依赖。
4. 构建前端。
5. 执行数据库迁移。
6. 重启 HomeNAS 自身服务。
7. 执行健康检查。
8. 失败时回滚上一版本。

不需要自动更新服务。

## 8. 测试要求

至少包含：
- Collector 单元测试。
- perf 输出解析测试（真实主机样例和模拟异常样例）。
- 缺失传感器测试。
- 计数器重置测试。
- SQLite WAL 测试。
- 网络接口重命名/消失测试。
- Mihomo API 不可用测试。
- Tailscale 未安装测试。
- Docker 未安装测试。
- Seafile 不可用测试。
- SMART 权限不足测试。
- 登录与权限测试。
- 告警去重和恢复测试。
- 更新失败回滚测试。

服务不存在或指标不可用时，整个 Dashboard 必须继续工作。

## 9. Codex 执行纪律

1. 先完成 Phase 0 只读环境审计。
2. 先判断 Codex 终端是否位于 NAS 本机。
3. 不得将开发电脑环境误认为 NAS 环境。
4. 不得擅自安装、卸载或升级现有服务。
5. 不得修改 Seafile、Mihomo、Tailscale、反向代理、防火墙、路由、磁盘分区。
6. 对任何需要 root 或会影响现有服务、网络、磁盘、反向代理的改动，先说明准确命令、影响和回滚方式，并等待用户批准。
7. 审计完成后，不要停留在文档阶段；按 Phase 1 开始创建可运行代码。
8. 每个阶段都要有测试、部署说明和回滚方案。
9. 不要引入不必要组件。
10. 目标是低资源占用、长期稳定、易维护。

最终验收：HomeNAS 可独立运行，展示真实系统和功耗数据，监控存储、网络、Mihomo、Tailscale、Seafile，维护服务资产清单和告警，不破坏任何现有 NAS 服务。
