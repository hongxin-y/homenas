# HomeNAS 项目约定

本项目遵循上级 `D:\Repos\AGENTS.md` 的通用约定。

- 仅做只读主机采集，不修改 Seafile、Mihomo、Tailscale、反向代理、防火墙、路由或磁盘配置。
- 运行时数据库、缓存和日志写入 `runtime/`，不进入源码版本控制。
- API 默认只监听 `127.0.0.1`，不得为了本地演示绑定公网地址。
- 任何需要 root、systemd、网络或现有服务变更的操作必须先停下并给出影响与回滚方案。
- 采集不到的值使用 `null`/`Unavailable`，不能用 0 伪造。

