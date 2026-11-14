(function () {
    "use strict";
    const state = { authenticated: false, page: "overview", data: null };
    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? "Unavailable").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] || c));
    const finite = (value) => Number.isFinite(Number(value));
    const bytes = (value) => {
        if (!finite(value))
            return "Unavailable";
        let n = Number(value);
        const units = ["B", "KiB", "MiB", "GiB", "TiB"];
        let i = 0;
        while (Math.abs(n) >= 1024 && i < units.length - 1) {
            n /= 1024;
            i++;
        }
        return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
    };
    const rate = (value) => finite(value) ? `${bytes(value)}/s` : "Unavailable";
    const energy = (value) => { if (!finite(value))
        return "Unavailable"; let n = Number(value); const units = ["J", "kJ", "MJ", "GJ"]; let i = 0; while (Math.abs(n) >= 1000 && i < units.length - 1) {
        n /= 1000;
        i++;
    } return `${n.toFixed(i ? 2 : 1)} ${units[i]}`; };
    const duration = (seconds) => {
        if (!finite(seconds))
            return "Unavailable";
        const s = Math.max(0, Number(seconds));
        const d = Math.floor(s / 86400);
        const h = Math.floor((s % 86400) / 3600);
        const m = Math.floor((s % 3600) / 60);
        return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
    };
    const percent = (value) => finite(value) ? `${Number(value).toFixed(1)}%` : "Unavailable";
    const fixed = (value, digits = 1) => finite(value) ? Number(value).toFixed(digits) : "Unavailable";
    const money = (value) => finite(value) ? `¥${Number(value).toFixed(2)}` : "Unavailable";
    const display = (value) => typeof value === "object" && value !== null ? JSON.stringify(value) : String(value ?? "Unavailable");
    const pill = (status) => {
        const ok = ["healthy", "ok", "available", "detected", "reachable", "online"].includes(status);
        const bad = ["critical", "failed", "offline", "unreachable", "invalid-target"].includes(status);
        return `<span class="status-pill ${ok ? "ok" : bad ? "bad" : "warn"}">${ok ? "●" : "○"} ${esc(status || "unknown")}</span>`;
    };
    async function api(path, options = {}) {
        const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
        const response = await fetch(path, Object.assign({}, options, { headers, credentials: "same-origin" }));
        if (response.status === 401) {
            logout(false);
            throw new Error("需要登录");
        }
        if (!response.ok)
            throw new Error((await response.json().catch(() => ({ detail: response.statusText }))).detail || response.statusText);
        return response.json();
    }
    function loginView(show) { $("login-view").classList.toggle("hidden", !show); $("dashboard-view").classList.toggle("hidden", show); }
    function logout(callApi) { if (callApi)
        fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => { }); state.authenticated = false; state.data = null; loginView(true); }
    function metricCard(label, value, foot, color = "") { return `<article class="metric-card"><div class="metric-label">${label}</div><div class="metric-value ${color}">${value}</div><div class="metric-foot">${foot}</div></article>`; }
    function chart(history, series, unit) {
        const rows = (history || []).slice(-36);
        const all = series.flatMap((item) => rows.map((row) => Number(row[item.key])).filter(Number.isFinite));
        if (!all.length)
            return `<div class="empty">等待更多采样数据…</div>`;
        const width = 720;
        const height = 190;
        const left = 54;
        const right = 14;
        const top = 18;
        const bottom = 28;
        const plotWidth = width - left - right;
        const plotHeight = height - top - bottom;
        const max = Math.max(1, ...all);
        const x = (index) => left + (rows.length <= 1 ? plotWidth / 2 : index * plotWidth / (rows.length - 1));
        const y = (value) => top + plotHeight * (1 - value / max);
        const formatAxis = (value) => unit === "%" ? `${value.toFixed(0)}%` : unit === "W" ? `${value.toFixed(1)} W` : rate(value);
        const grid = [0, 0.5, 1].map((fraction) => `<line class="chart-grid" x1="${left}" x2="${width - right}" y1="${top + plotHeight * fraction}" y2="${top + plotHeight * fraction}" /><text class="chart-y-label" x="${left - 8}" y="${top + plotHeight * fraction + 4}" text-anchor="end">${formatAxis(max * (1 - fraction))}</text>`).join("");
        const lines = series.map((item) => {
            const segments = [];
            let segment = [];
            rows.forEach((row, index) => { const value = Number(row[item.key]); if (Number.isFinite(value))
                segment.push(`${x(index)},${y(value)}`);
            else if (segment.length) {
                segments.push(segment);
                segment = [];
            } });
            if (segment.length)
                segments.push(segment);
            return segments.map((points) => `<polyline class="chart-line ${item.color}" points="${points.join(" ")}" />`).join("");
        }).join("");
        const last = rows[rows.length - 1]?.timestamp ? new Date(rows[rows.length - 1].timestamp).toLocaleTimeString() : "";
        return `<div class="chart-shell"><div class="chart-unit">单位：${esc(unit)} · 最大刻度 ${esc(formatAxis(max))}</div><svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(series.map((item) => item.label).join("、"))}趋势图">${grid}${lines}<text class="chart-x-label" x="${left}" y="${height - 6}">较早</text><text class="chart-x-label" x="${width - right}" y="${height - 6}" text-anchor="end">${esc(last || "现在")}</text></svg><div class="legend">${series.map((item) => `<span><i class="${item.color}"></i>${esc(item.label)}（${esc(unit)}）</span>`).join("")}</div></div>`;
    }
    function alertList(alerts) {
        if (!alerts?.length)
            return `<div class="empty">当前没有活动告警</div>`;
        return `<div class="status-list">${alerts.map((a) => `<div class="status-row"><div><strong>${esc(a.title)}</strong><div class="metric-foot">${esc(a.detail || "")}</div></div>${pill(a.severity)}</div>`).join("")}</div>`;
    }
    function overview(data) {
        const s = data.system || {};
        const memory = s.memory || {};
        const filesystems = data.storage?.filesystems || [];
        const fs = filesystems.slice().sort((a, b) => Number(b.percent || 0) - Number(a.percent || 0))[0];
        const network = data.network || {};
        const battery = s.battery || {};
        const power = data.power || {};
        const batteryValue = battery.available && battery.percent != null ? `${fixed(battery.percent, 0)}%` : "Unavailable";
        const batteryFoot = battery.available ? (battery.charging ? "正在充电" : "电池供电") : "没有电池传感器";
        return `<div class="page-grid"><div class="metrics-grid">${metricCard("CPU 使用率", percent(s.cpu_percent), `${s.per_cpu_percent?.length || 0} 个逻辑线程`, "accent")}${metricCard("内存", percent(memory.percent), `${bytes(memory.used_bytes)} / ${bytes(memory.total_bytes)}`, "blue")}${metricCard("CPU 温度", s.temperature_c == null ? "Unavailable" : `${fixed(s.temperature_c)}°C`, s.temperature_source ? `来源 ${s.temperature_source}` : "没有温度传感器", s.temperature_c >= 85 ? "warn" : "")}${metricCard("电池电量", batteryValue, batteryFoot, battery.available && battery.percent < 20 ? "warn" : "")}${metricCard("Package 功耗", power.package_watts != null ? `${fixed(power.package_watts, 2)} W` : "Unavailable", power.available ? "sysfs 能量计" : (power.reason || "无能量计"), "warn")}${metricCard("存储", fs ? percent(fs.percent) : "Unavailable", fs ? `${esc(fs.mountpoint)} · ${bytes(fs.free_bytes)} 可用` : "没有可用文件系统", fs?.percent >= 85 ? "warn" : "")}${metricCard("物理网卡", rate(network.physical_rx_bytes_per_second), `上传 ${rate(network.physical_tx_bytes_per_second)}`, "blue")}</div><div class="two-col"><section class="panel"><div class="panel-head"><div><h3>实时资源</h3><p>最近采样 · CPU 与内存均为 %</p></div><span class="status-pill ok">● LIVE</span></div>${chart(data.history, [{ key: "cpu_percent", label: "CPU", color: "accent" }, { key: "memory_percent", label: "内存", color: "secondary" }], "%")}</section><section class="panel"><div class="panel-head"><div><h3>运行摘要</h3><p>采集器每 5 秒刷新</p></div></div><div class="data-row"><span>运行时间</span><strong>${duration(s.uptime_seconds)}</strong></div><div class="data-row"><span>系统负载</span><strong>${s.load_average?.length ? s.load_average.join(" / ") : "Unavailable"}</strong></div><div class="data-row"><span>TCP 连接</span><strong>${Object.values(network.tcp_connection_counts || {}).reduce((a, b) => a + Number(b || 0), 0) || "Unavailable"}</strong></div><div class="data-row"><span>电池状态</span><strong>${esc(batteryFoot)}</strong></div></section></div><div class="two-col"><section class="panel"><div class="panel-head"><div><h3>网络吞吐</h3><p>只汇总 physical 接口；单位自动换算为 B/s</p></div></div>${chart(data.history, [{ key: "rx", label: "下载", color: "accent" }, { key: "tx", label: "上传", color: "secondary" }], "B/s")}</section><section class="panel"><div class="panel-head"><div><h3>当前告警</h3><p>阈值告警自动去重</p></div></div>${alertList(data.alerts)}</section></div></div>`;
    }
    function systemPage(data) {
        const s = data.system || {};
        const memory = s.memory || {};
        const swap = s.swap || {};
        const battery = s.battery || {};
        const processes = s.top_processes || [];
        return `<div class="page-grid"><div class="two-col"><section class="panel"><div class="panel-head"><div><h3>系统信息</h3><p>来自 psutil 的只读采集</p></div></div><div class="data-row"><span>主机</span><strong>${esc(s.hostname)}</strong></div><div class="data-row"><span>平台</span><strong>${esc(s.platform)}</strong></div><div class="data-row"><span>内核</span><strong>${esc(s.kernel)}</strong></div><div class="data-row"><span>CPU</span><strong>${esc(s.cpu_model)}</strong></div><div class="data-row"><span>频率</span><strong>${s.cpu_frequency_mhz == null ? "Unavailable" : `${fixed(s.cpu_frequency_mhz)} MHz`}</strong></div><div class="data-row"><span>运行时间</span><strong>${duration(s.uptime_seconds)}</strong></div></section><section class="panel"><div class="panel-head"><div><h3>内存与 Swap</h3><p>Unavailable 表示平台不提供</p></div></div>${metricCard("内存", percent(memory.percent), `${bytes(memory.available_bytes)} 可用`, "blue")}${metricCard("Swap", percent(swap.percent), `${bytes(swap.used_bytes)} 已用`, "")}${metricCard("电池", battery.available && battery.percent != null ? `${fixed(battery.percent, 0)}%` : "Unavailable", battery.available ? (battery.charging ? "正在充电" : "电池供电") : "无电池传感器", "")}</section></div><section class="panel"><div class="panel-head"><div><h3>每核心使用率</h3><p>单位：%</p></div></div><div class="metrics-grid">${(s.per_cpu_percent || []).map((v, i) => metricCard(`Core ${i + 1}`, percent(v), "实时", v >= 85 ? "warn" : "accent")).join("") || `<div class="empty">Unavailable</div>`}</div></section><section class="panel"><div class="panel-head"><div><h3>高占用进程</h3><p>只显示进程名、PID 和资源比例，不提供结束进程操作</p></div></div><div class="table-wrap"><table><thead><tr><th>进程</th><th>PID</th><th>CPU</th><th>内存</th></tr></thead><tbody>${processes.map((p) => `<tr><td>${esc(p.name)}</td><td>${esc(p.pid)}</td><td>${percent(p.cpu_percent)}</td><td>${percent(p.memory_percent)}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">Unavailable</td></tr>`}</tbody></table></div></section></div>`;
    }
    function powerPage(data) {
        const power = data.power || {};
        const domains = Object.entries(power.domains || {});
        const daily = power.daily || {};
        const cost = power.cost || {};
        const currentCost = cost.current || {};
        const annualized = cost.annualized || {};
        const dailyCost = cost.daily || {};
        const dailyValue = daily.available && daily.total_kwh != null ? `${fixed(daily.total_kwh, 4)} kWh` : "Unavailable";
        const dailyFoot = daily.available && daily.total_wh != null ? `Package · ${fixed(daily.total_wh, 2)} Wh · ${daily.day}` : "没有有效 Package perf 区间";
        const currentRate = cost.current_rate_cny_per_kwh == null ? null : Number(cost.current_rate_cny_per_kwh);
        const currentBand = cost.current_band?.name || "上海居民分时";
        const selectedTier = cost.tariff?.tier || 1;
        return `<div class="page-grid"><div class="metrics-grid">${metricCard("Package 实时功率", power.package_watts == null ? "Unavailable" : `${fixed(power.package_watts, 2)} W`, "CPU 封装功耗，不是整机插座功耗", "warn")}${metricCard("Package 累计能耗", power.package_energy_wh == null ? "Unavailable" : `${fixed(power.package_energy_wh, 2)} Wh`, power.package_energy_kwh == null ? "当前采集进程" : `${fixed(power.package_energy_kwh, 4)} kWh`, "accent")}${metricCard("今日 Package 累计", dailyValue, dailyFoot, "blue")}${metricCard("当前每小时电费", money(currentCost.cny_per_hour), `${currentBand} · ${currentRate == null ? "Unavailable" : `¥${fixed(currentRate, 3)} / kWh`}`, "blue")}${metricCard("年化 Package 电费", money(annualized.cny), annualized.basis === "today_package" ? "按今日 Package 能耗年化" : "按当前功率年化", "warn")}${metricCard("采集状态", esc(power.collector_status || "unavailable"), esc(power.source || "Unavailable"), power.available ? "accent" : "warn")}</div><section class="panel"><div class="panel-head"><div><h3>功耗监控</h3><p>Perf RAPL 持续子进程 · 按实际 perf 时间戳计算间隔</p></div>${pill(power.available ? "available" : "unavailable")}</div><div class="notice">${esc(power.reason || power.semantics || "暂无功耗数据")}<br><span class="metric-foot">${esc(cost.price_source || "上海市居民一户一表分时电价")} · 当前${esc(currentBand)} · 第${esc(selectedTier)}档</span></div><div class="data-row"><span>当前 Package 功耗</span><strong>${power.package_watts == null ? "Unavailable" : `${fixed(power.package_watts, 2)} W`}</strong></div><div class="data-row"><span>当前每日估算电费</span><strong>${money(currentCost.cny_per_day)}</strong></div><div class="data-row"><span>今日实际 Package 电费</span><strong>${money(dailyCost.cny)}</strong></div><div class="data-row"><span>采集源</span><strong>${esc(power.source)}</strong></div><div class="data-row"><span>PSys</span><strong>${power.psys_experimental ? "实验性指标，不代表插座功耗" : "Unavailable"}</strong></div></section><section class="panel"><div class="panel-head"><div><h3>时间段电费估算</h3><p>上海居民一户一表分时电价：峰 06:00–22:00，谷 22:00–06:00；按年度用电档位选择。</p></div></div><form id="power-cost-form" class="inline-form"><label>开始 <input id="power-cost-start" type="date" value="${esc(daily.day || "")}" /></label><label>结束 <input id="power-cost-end" type="date" value="${esc(daily.day || "")}" /></label><label>年度档位 <select id="power-cost-tier"><option value="1" ${selectedTier === 1 ? "selected" : ""}>一档（0–3120 kWh）</option><option value="2" ${selectedTier === 2 ? "selected" : ""}>二档（3120–4800 kWh）</option><option value="3" ${selectedTier === 3 ? "selected" : ""}>三档（>4800 kWh）</option></select></label><button class="primary-button button-small" type="submit">查询</button></form><div id="power-cost-result" class="notice">选择日期后查询一段时间的 Package 能耗和电费。</div></section><section class="panel"><div class="panel-head"><div><h3>功耗趋势</h3><p>单位：W；Package 单独展示，不与其他 domain 相加</p></div></div>${chart(data.history, [{ key: "power_watts", label: "Package", color: "warn" }], "W")}</section><section class="panel"><div class="panel-head"><div><h3>RAPL 能量域</h3><p>有效区间按 Joules / 3600 计算 Wh；Cores、GPU、DRAM、PSys 不直接相加</p></div></div><div class="table-wrap"><table><thead><tr><th>Domain</th><th>状态</th><th>当前功率</th><th>累计 Joules</th><th>累计 Wh / kWh</th><th>采样间隔</th></tr></thead><tbody>${domains.map(([name, item]) => `<tr><td>${esc(name)}</td><td>${pill(item.available ? "available" : "unavailable")}</td><td>${item.watts == null ? "Unavailable" : `${fixed(item.watts, 2)} W`}</td><td>${item.energy_j == null ? "Unavailable" : energy(item.energy_j)}</td><td>${item.energy_wh == null ? "Unavailable" : `${fixed(item.energy_wh, 2)} Wh / ${fixed(item.energy_kwh, 4)} kWh`}</td><td>${item.elapsed_seconds == null ? "Unavailable" : `${fixed(item.elapsed_seconds, 3)} s`}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">等待 perf RAPL 采样</td></tr>`}</tbody></table></div></section></div>`;
    }
    function storagePage(data) {
        const storage = data.storage || {};
        const filesystems = storage.filesystems || [];
        const disks = storage.disks || [];
        return `<div class="page-grid"><section class="panel"><div class="panel-head"><div><h3>文件系统</h3><p>只读使用率；不提供格式化、分区或修复操作</p></div></div><div class="table-wrap"><table><thead><tr><th>设备</th><th>挂载点</th><th>文件系统</th><th>容量</th><th>使用率</th></tr></thead><tbody>${filesystems.map((x) => `<tr><td>${esc(x.device)}</td><td>${esc(x.mountpoint)}</td><td>${esc(x.fstype)}</td><td>${bytes(x.used_bytes)} / ${bytes(x.total_bytes)}</td><td><div class="usage-cell"><span>${percent(x.percent)}</span><span class="usage-track"><i style="width:${Math.min(100, Number(x.percent) || 0)}%"></i></span></div></td></tr>`).join("") || `<tr><td colspan="5" class="empty">Unavailable</td></tr>`}</tbody></table></div></section><section class="panel"><div class="panel-head"><div><h3>块设备</h3><p>lsblk 只读清单；SMART 未安装或无权限时保持 Unavailable</p></div></div><div class="table-wrap"><table><thead><tr><th>设备</th><th>类型</th><th>型号</th><th>容量</th><th>挂载点</th><th>只读</th></tr></thead><tbody>${disks.map((x) => `<tr><td>${esc(x.name)}</td><td>${esc(x.type)}</td><td>${esc(x.model || "—")}</td><td>${esc(x.size || "—")}</td><td>${esc((x.mountpoints || []).join(" · ") || "—")}</td><td>${x.read_only ? "是" : "否"}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Unavailable</td></tr>`}</tbody></table></div></section></div>`;
    }
    function networkPage(data) {
        const network = data.network || {};
        const connections = Object.entries(network.tcp_connection_counts || {});
        return `<div class="page-grid"><section class="panel"><div class="panel-head"><div><h3>网卡</h3><p>${esc(network.note)}</p></div></div><div class="table-wrap"><table><thead><tr><th>接口 / 地址</th><th>类型</th><th>下载</th><th>上传</th><th>累计接收</th><th>累计发送</th></tr></thead><tbody>${(network.interfaces || []).map((x) => `<tr><td><strong>${esc(x.name)}</strong><div class="metric-foot">${esc((x.ipv4 || []).concat(x.ipv6 || []).join(" · ") || "无地址")}</div></td><td>${esc(x.kind)}</td><td>${x.rx_bytes_per_second == null ? "等待采样" : rate(x.rx_bytes_per_second)}</td><td>${x.tx_bytes_per_second == null ? "等待采样" : rate(x.tx_bytes_per_second)}</td><td>${bytes(x.bytes_recv)}</td><td>${bytes(x.bytes_sent)}</td></tr>`).join("")}</tbody></table></div></section><section class="panel"><div class="panel-head"><div><h3>TCP 连接状态</h3><p>只读计数，不暴露连接目的地址</p></div></div><div class="data-grid">${connections.map(([name, count]) => `<div class="mini-stat"><span>${esc(name)}</span><strong>${esc(count)}</strong></div>`).join("") || `<div class="empty">Unavailable</div>`}</div></section></div>`;
    }
    function vpnPage(data) {
        const vpn = data.vpn || {};
        const mihomo = vpn.mihomo || {};
        const tailscale = vpn.tailscale || {};
        const rules = mihomo.rules?.rules || [];
        const groups = mihomo.proxies?.groups || [];
        const nodes = mihomo.proxies?.nodes || [];
        const peers = tailscale.peers || [];
        const mutationEnabled = mihomo.mutation_enabled === true;
        const draftRules = rules.map((rule) => [rule.type, rule.payload, rule.proxy].filter((value) => value != null && value !== "").join(",")).join("\n");
        const firstTarget = peers.find((peer) => peer.dns_name)?.dns_name || "127.0.0.1";
        const config = Object.entries(mihomo.config || {});
        return `<div class="page-grid"><div class="notice">Mihomo 数据通过 NAS 本机 Controller 获取；Secret 只留在服务器环境变量，不会发送到浏览器。当前配置变更${mutationEnabled ? "已显式启用" : "保持关闭"}。${esc(mihomo.mutation_detail || "")}</div><div class="two-col"><section class="panel"><div class="panel-head"><div><h3>Mihomo</h3><p>${esc(mihomo.detail)}</p></div>${pill(mihomo.controller_available ? "reachable" : mihomo.available ? "detected" : "unavailable")}</div><div class="data-row"><span>版本</span><strong>${esc(mihomo.version || "Unavailable")}</strong></div><div class="data-row"><span>模式</span><strong>${esc(mihomo.mode || "Unavailable")}</strong></div><div class="data-row"><span>规则数量</span><strong>${mihomo.rules?.count ?? "Unavailable"}</strong></div><div class="data-row"><span>节点 / 代理组</span><strong>${mihomo.proxies?.count ?? "Unavailable"} / ${mihomo.proxies?.group_count ?? "Unavailable"}</strong></div><div class="kv-grid">${config.map(([key, value]) => `<div class="mini-stat"><span>${esc(key)}</span><strong>${esc(display(value))}</strong></div>`).join("") || `<div class="empty">Controller 配置不可用</div>`}</div></section><section class="panel"><div class="panel-head"><div><h3>Tailscale</h3><p>${esc(tailscale.detail)}</p></div>${pill(tailscale.online === true ? "online" : tailscale.available ? (tailscale.online === false ? "offline" : "detected") : "unavailable")}</div><div class="data-row"><span>在线节点</span><strong>${tailscale.online_peer_count ?? "Unavailable"} / ${tailscale.peer_count ?? "Unavailable"}</strong></div><div class="data-row"><span>本机地址</span><strong>${tailscale.self_ip_available ? "已提供" : "Unavailable"}</strong></div><div class="peer-list">${peers.map((peer) => `<div class="status-row"><div><strong>${esc(peer.name)}</strong><div class="metric-foot">${esc(peer.dns_name || "无 DNS 名称")}</div></div>${pill(peer.online === true ? "online" : peer.online === false ? "offline" : "unknown")}</div>`).join("") || `<div class="empty">没有可用节点摘要</div>`}</div></section></div><section class="panel"><div class="panel-head"><div><h3>连通性检查</h3><p>可输入 NAS 可访问的 IP 或主机名；单次超时 2 秒</p></div></div><form id="ping-form" class="inline-form"><input id="ping-target" value="${esc(firstTarget)}" placeholder="例如 100.64.0.1 或 nas.example" autocomplete="off" /><button class="primary-button button-small" type="submit">Ping</button></form><div class="quick-targets">${peers.filter((peer) => peer.dns_name).slice(0, 6).map((peer) => `<button type="button" class="ghost-button button-small" data-ping-target="${esc(peer.dns_name)}">${esc(peer.name)}</button>`).join("")}</div><div id="ping-result" class="ping-result muted">选择节点或输入目标后执行 Ping。</div></section><section class="panel"><div class="panel-head"><div><h3>当前转发规则</h3><p>来自 Mihomo /rules，显示命中计数和最终动作；规则本身只读</p></div><span class="status-pill">${rules.length} 条</span></div><input id="vpn-rule-search" class="table-search" placeholder="筛选规则类型、域名或动作…" autocomplete="off" /><div class="table-wrap"><table><thead><tr><th>#</th><th>类型</th><th>匹配内容</th><th>动作</th><th>命中</th><th>最近命中</th></tr></thead><tbody>${rules.map((rule) => `<tr class="vpn-rule-row" data-search="${esc(`${rule.type || ""} ${rule.payload || ""} ${rule.proxy || ""}`.toLowerCase())}"><td>${esc(rule.index)}</td><td>${esc(rule.type)}</td><td class="rule-payload">${esc(rule.payload)}</td><td>${esc(rule.proxy)}</td><td>${esc(rule.hit_count ?? 0)}</td><td>${esc(rule.hit_at || "—")}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Controller 未返回规则</td></tr>`}</tbody></table></div></section><section class="panel"><div class="panel-head"><div><h3>代理组与节点</h3><p>节点切换按钮受服务端开关控制；当前 NAS 默认只读</p></div></div><div class="table-wrap"><table><thead><tr><th>代理组</th><th>类型</th><th>当前节点</th><th>切换节点</th><th>节点数</th></tr></thead><tbody>${groups.map((group) => `<tr><td>${esc(group.name)}</td><td>${esc(group.type)}</td><td>${esc(group.now || "—")}</td><td><select class="mihomo-node-select" data-mihomo-group="${esc(group.name)}" ${mutationEnabled ? "" : "disabled"}>${(group.nodes || []).map((node) => `<option value="${esc(node)}" ${node === group.now ? "selected" : ""}>${esc(node)}</option>`).join("")}</select><button type="button" class="ghost-button button-small" data-mihomo-select="${esc(group.name)}" ${mutationEnabled ? "" : "disabled"}>切换</button></td><td>${esc(group.node_count)}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">没有代理组</td></tr>`}</tbody></table></div><div class="table-wrap compact-table"><table><thead><tr><th>节点</th><th>类型</th><th>存活</th><th>UDP</th><th>延迟</th></tr></thead><tbody>${nodes.slice(0, 30).map((node) => `<tr><td>${esc(node.name)}</td><td>${esc(node.type)}</td><td>${node.alive == null ? "—" : node.alive ? "是" : "否"}</td><td>${node.udp == null ? "—" : node.udp ? "是" : "否"}</td><td>${node.delay_ms == null ? "—" : `${esc(node.delay_ms)} ms`}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">没有节点摘要</td></tr>`}</tbody></table></div><div id="mihomo-control-result" class="ping-result muted">${mutationEnabled ? "选择代理组和节点后执行切换。" : "节点切换已被服务端只读策略关闭。"}</div></section><section class="panel"><div class="panel-head"><div><h3>规则配置草稿</h3><p>可编辑、校验规则文本；当前不会写入 Mihomo 配置</p></div></div><textarea id="mihomo-rule-draft" rows="8" class="code-input">${esc(draftRules)}</textarea><button type="button" id="mihomo-rule-draft-submit" class="primary-button button-small">校验草稿</button><div id="mihomo-rule-draft-result" class="ping-result muted">规则格式示例：DOMAIN-SUFFIX,example.com,Proxy</div></section></div>`;
    }
    function servicesPage(data) {
        return `<div class="page-grid"><section class="panel"><div class="panel-head"><div><h3>服务资产清单</h3><p>端口线索不会单独证明服务身份</p></div></div><div class="table-wrap"><table><thead><tr><th>名称</th><th>分类</th><th>部署</th><th>状态</th><th>健康</th><th>来源</th></tr></thead><tbody>${(data.services || []).map((x) => `<tr><td>${esc(x.name)}</td><td>${esc(x.category)}</td><td>${esc(x.deployment)}</td><td>${pill(x.status)}</td><td>${esc(x.health)}</td><td>${esc(x.source)}</td></tr>`).join("")}</tbody></table></div></section><section class="panel"><div class="panel-head"><div><h3>Seafile CE</h3><p>只读 HTTP 健康检查</p></div>${pill(data.seafile?.healthy === true ? "healthy" : data.seafile?.healthy === false ? "failed" : "unknown")}</div><div class="notice">${esc(data.seafile?.detail || data.seafile?.reason || "未配置健康端点")}</div></section></div>`;
    }
    function pageContent(page, data) {
        if (page === "overview")
            return overview(data);
        if (page === "system")
            return systemPage(data);
        if (page === "power")
            return powerPage(data);
        if (page === "storage")
            return storagePage(data);
        if (page === "network")
            return networkPage(data);
        if (page === "vpn")
            return vpnPage(data);
        if (page === "services")
            return servicesPage(data);
        return `<div class="page-grid"><section class="panel"><div class="panel-head"><div><h3>告警中心</h3><p>站内告警 · 恢复状态保留在 SQLite</p></div></div>${alertList(data.alerts)}</section></div>`;
    }
    const titles = { overview: ["OVERVIEW", "总览"], system: ["SYSTEM", "系统"], power: ["POWER", "功耗"], storage: ["STORAGE", "存储"], network: ["NETWORK", "网络"], vpn: ["VPN", "VPN"], services: ["SERVICES", "服务"], alerts: ["ALERTS", "告警"] };
    function bindPageActions() {
        const costForm = document.getElementById("power-cost-form");
        const costResult = document.getElementById("power-cost-result");
        costForm?.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (!costResult)
                return;
            const start = document.getElementById("power-cost-start")?.value || "";
            const end = document.getElementById("power-cost-end")?.value || "";
            const tier = document.getElementById("power-cost-tier")?.value || "1";
            costResult.className = "notice";
            costResult.textContent = "正在计算…";
            try {
                const result = await api(`/api/power/cost?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&tier=${encodeURIComponent(tier)}`);
                const bands = Object.values(result.bands || {}).map((band) => `${esc(band.name)} ${fixed(band.kwh, 5)} kWh · ¥${fixed(band.cost_cny, 2)}`).join("；");
                costResult.innerHTML = result.available ? `Package 能耗 <strong>${fixed(result.package_kwh, 5)} kWh</strong> · 电费 <strong>¥${fixed(result.package_cost_cny, 2)}</strong> · ${esc(result.start)} 至 ${esc(result.end)}${bands ? `<br><span class="metric-foot">${bands}</span>` : ""}<br><span class="metric-foot">${esc(result.semantics)}</span>` : `该时间段没有有效 Package 采样。<br><span class="metric-foot">${esc(result.semantics)}</span>`;
            }
            catch (error) {
                costResult.className = "ping-result failure";
                costResult.textContent = error.message || "时间段计算失败";
            }
        });
        const pingForm = document.getElementById("ping-form");
        const target = document.getElementById("ping-target");
        const pingResult = document.getElementById("ping-result");
        const runPing = async (value) => {
            if (!target || !pingResult)
                return;
            if (value)
                target.value = value;
            const button = pingForm?.querySelector("button");
            if (button)
                button.disabled = true;
            pingResult.className = "ping-result muted";
            pingResult.textContent = "正在 Ping…";
            try {
                const result = await api("/api/vpn/ping", { method: "POST", body: JSON.stringify({ target: target.value }) });
                pingResult.className = `ping-result ${result.ok ? "success" : "failure"}`;
                pingResult.innerHTML = `${pill(result.status)} <strong>${esc(result.target)}</strong> · ${esc(result.detail)}${result.latency_ms == null ? "" : ` · ${fixed(result.latency_ms, 1)} ms`}`;
            }
            catch (error) {
                pingResult.className = "ping-result failure";
                pingResult.textContent = error.message || "Ping 失败";
            }
            finally {
                if (button)
                    button.disabled = false;
            }
        };
        pingForm?.addEventListener("submit", (event) => { event.preventDefault(); runPing(); });
        document.querySelectorAll("[data-ping-target]").forEach((button) => button.addEventListener("click", () => runPing(button.dataset.pingTarget)));
        const search = document.getElementById("vpn-rule-search");
        search?.addEventListener("input", () => { const query = search.value.trim().toLowerCase(); document.querySelectorAll(".vpn-rule-row").forEach((row) => row.classList.toggle("hidden", !!query && !(row.dataset.search || "").includes(query))); });
        const mihomoResult = document.getElementById("mihomo-control-result");
        document.querySelectorAll("[data-mihomo-select]").forEach((button) => button.addEventListener("click", async () => {
            const group = button.dataset.mihomoSelect || "";
            const select = Array.from(document.querySelectorAll("[data-mihomo-group]")).find((item) => item.dataset.mihomoGroup === group);
            const node = select?.value || "";
            if (!mihomoResult || !group || !node)
                return;
            button.setAttribute("disabled", "true");
            mihomoResult.className = "ping-result muted";
            mihomoResult.textContent = "正在切换节点…";
            try {
                const result = await api("/api/vpn/mihomo/select", { method: "POST", body: JSON.stringify({ group, node }) });
                mihomoResult.className = "ping-result success";
                mihomoResult.textContent = result.detail || "节点切换请求已发送";
                await refresh();
            }
            catch (error) {
                mihomoResult.className = "ping-result failure";
                mihomoResult.textContent = error.message || "节点切换失败";
            }
            finally {
                button.removeAttribute("disabled");
            }
        }));
        const draftButton = document.getElementById("mihomo-rule-draft-submit");
        const draftInput = document.getElementById("mihomo-rule-draft");
        const draftResult = document.getElementById("mihomo-rule-draft-result");
        draftButton?.addEventListener("click", async () => { if (!draftInput || !draftResult)
            return; draftButton.setAttribute("disabled", "true"); try {
            const result = await api("/api/vpn/mihomo/rules/draft", { method: "POST", body: JSON.stringify({ rules: draftInput.value.split("\n") }) });
            draftResult.className = `ping-result ${result.ok ? "success" : "failure"}`;
            draftResult.textContent = result.ok ? `草稿通过校验，共 ${result.count} 条；当前不会写入 Mihomo。` : (result.errors || []).join("；") || "规则草稿无效";
        }
        catch (error) {
            draftResult.className = "ping-result failure";
            draftResult.textContent = error.message || "规则校验失败";
        }
        finally {
            draftButton.removeAttribute("disabled");
        } });
    }
    function render() { if (!state.data)
        return; $("page-eyebrow").textContent = titles[state.page][0]; $("page-title").textContent = titles[state.page][1]; $("page-content").innerHTML = pageContent(state.page, state.data); $("nav-alert-count").textContent = String(state.data.alerts?.length || 0); $("last-updated").textContent = state.data.timestamp ? `更新于 ${new Date(state.data.timestamp).toLocaleTimeString()}` : "等待采集…"; bindPageActions(); }
    async function refresh() { try {
        state.data = await api("/api/overview");
        render();
    }
    catch (error) {
        if (state.authenticated)
            $("last-updated").textContent = error.message;
    } }
    $("login-form").addEventListener("submit", async (event) => { event.preventDefault(); $("login-error").textContent = ""; try {
        await api("/api/auth/login", { method: "POST", body: JSON.stringify({ username: $("username").value, password: $("password").value }) });
        state.authenticated = true;
        loginView(false);
        await refresh();
    }
    catch (error) {
        $("login-error").textContent = error.message;
    } });
    document.querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => { state.page = item.dataset.page || "overview"; document.querySelectorAll(".nav-item").forEach((x) => x.classList.toggle("active", x === item)); render(); }));
    $("refresh-button").addEventListener("click", refresh);
    $("logout-button").addEventListener("click", () => logout(true));
    api("/api/auth/me").then(() => { state.authenticated = true; loginView(false); return refresh(); }).catch(() => loginView(true));
    setInterval(() => { if (state.authenticated)
        refresh(); }, 5000);
})();
