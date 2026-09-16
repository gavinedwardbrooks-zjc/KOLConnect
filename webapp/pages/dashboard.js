(function registerDashboardPage(global) {
  "use strict";

  let resources = null;
  let requestController = null;
  let riskController = null;
  let analyticsController = null;
  let geographyController = null;
  let roiTrendController = null;
  let dashboardData = null;
  let lifecycleId = 0;
  const charts = new Map();
  const CHART_COLORS = ["#e56b46", "#2f7d6d", "#e9a23b", "#5574b9", "#b65d7a", "#717171"];
  const DASHBOARD_LAYOUT_KEY = "kolconnect-dashboard-layout-v2";
  const MODULES = [
    { id: "today", label: "今日待处理", description: "可直接进入待联系或数据过期对象", essential: true },
    { id: "missing_info", label: "待补充信息", description: "账号邮箱与达人基础资料缺口" },
    { id: "campaigns", label: "Campaign 概览", description: "项目成员与发布进度" },
    { id: "creator_overview", label: "达人数据概览", description: "Creator 与平台账号构成" },
    { id: "data_freshness", label: "数据更新状态", description: "快照新鲜度与现有趋势" },
    { id: "geography", label: "地区与语言", description: "已录入 Creator 基础资料分布" },
    { id: "roi", label: "ROI / Performance", description: "仅展示已录入的表现数据" },
  ];

  function defaultLayout() {
    return { version: 2, order: MODULES.map(module => module.id), visible: Object.fromEntries(MODULES.map(module => [module.id, true])) };
  }

  function readLayout() {
    const fallback = defaultLayout();
    try {
      const saved = JSON.parse(global.localStorage?.getItem(DASHBOARD_LAYOUT_KEY) || "null");
      if (!saved || !Array.isArray(saved.order) || typeof saved.visible !== "object") return fallback;
      const known = new Set(MODULES.map(module => module.id));
      const order = [...new Set(saved.order.filter(id => known.has(id) && id !== "today"))];
      order.unshift("today");
      MODULES.forEach(module => { if (!order.includes(module.id)) order.push(module.id); });
      const visible = Object.fromEntries(MODULES.map(module => [module.id, module.essential || saved.visible[module.id] !== false]));
      return { version: 2, order, visible };
    } catch (_) { return fallback; }
  }

  function saveLayout(layout) {
    global.localStorage?.setItem(DASHBOARD_LAYOUT_KEY, JSON.stringify(layout));
    global.dispatchEvent?.(new global.Event("kolconnect-dashboard-layout-changed"));
  }

  function applyDashboardLayout() {
    const container = element("dashboard-v2-modules");
    if (!container) return;
    const layout = readLayout();
    const byId = new Map([...container.querySelectorAll("[data-dashboard-v2-module]")].map(node => [node.dataset.dashboardV2Module, node]));
    layout.order.forEach(id => {
      const node = byId.get(id);
      if (!node) return;
      node.hidden = layout.visible[id] === false;
      container.appendChild(node);
    });
  }

  function updateLayout(mutator) {
    const layout = readLayout();
    mutator(layout);
    saveLayout(layout);
    applyDashboardLayout();
  }

  function element(id) {
    return document.getElementById(id);
  }

  function getApp() {
    if (!global.KOLConnectApp) throw new Error("KOLConnect application helpers are unavailable.");
    return global.KOLConnectApp;
  }

  function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "--";
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(number);
  }

  function formatTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  function formatChange(change) {
    if (!change || !change.metric) return "暂无趋势数据";
    const metric = change.metric === "median_views" ? "中位播放" : "粉丝";
    const direction = change.direction === "growth" ? "增长" : "下降";
    return `${metric}${direction} ${formatNumber(Math.abs(Number(change.delta) || 0))}`;
  }

  function setText(id, value) {
    const target = element(id);
    if (target) target.textContent = value;
  }

  function formatMoneyTotal(total, totalsByCurrency, unknownTotal) {
    const groups = Object.entries(totalsByCurrency || {})
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([currency, amount]) => `${currency} ${formatNumber(amount)}`);
    if (unknownTotal != null) groups.push(`未标币种 ${formatNumber(unknownTotal)}`);
    return groups.length ? groups.join(" · ") : formatNumber(total);
  }

  function formatPercent(value) {
    if (value == null || value === "") return "--";
    const number = Number(value);
    return Number.isFinite(number) ? `${formatNumber(number)}%` : "--";
  }

  function setChartEmpty(id, isEmpty) {
    const target = element(id);
    if (target) target.hidden = !isEmpty;
  }

  function destroyChart(id) {
    const chart = charts.get(id);
    if (chart) chart.destroy();
    charts.delete(id);
  }

  function destroyCharts() {
    [...charts.keys()].forEach(destroyChart);
  }

  function chartRows(rows, labelField) {
    return (Array.isArray(rows) ? rows : [])
      .map(row => ({ label: String(row?.[labelField] || "Other/Unknown"), count: Number(row?.count) || 0 }))
      .filter(row => row.count > 0);
  }

  function renderChart(id, emptyId, config, hasData) {
    destroyChart(id);
    setChartEmpty(emptyId, !hasData);
    if (!hasData || typeof global.Chart !== "function") return;
    const canvas = element(id);
    if (!canvas?.getContext) return;
    charts.set(id, new global.Chart(canvas.getContext("2d"), config));
  }

  function renderVisualizations(data) {
    const platform = chartRows(data?.platform_distribution, "platform");
    renderChart("dashboard-platform-chart", "dashboard-platform-chart-empty", {
      type: "doughnut",
      data: {
        labels: platform.map(row => row.label),
        datasets: [{ data: platform.map(row => row.count), backgroundColor: CHART_COLORS, borderWidth: 0 }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } },
    }, platform.length > 0);

    const statuses = chartRows(data?.creator_status_distribution, "status");
    renderChart("dashboard-status-chart", "dashboard-status-chart-empty", {
      type: "bar",
      data: {
        labels: statuses.map(row => row.label),
        datasets: [{ label: "达人数量", data: statuses.map(row => row.count), backgroundColor: "#2f7d6d", borderRadius: 6 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } },
      },
    }, statuses.length > 0);

    const trend = (Array.isArray(data?.creator_growth_trend) ? data.creator_growth_trend : [])
      .filter(row => typeof row?.date === "string")
      .map(row => ({ date: row.date, count: Number(row.count) || 0 }));
    renderChart("dashboard-growth-chart", "dashboard-growth-chart-empty", {
      type: "line",
      data: {
        labels: trend.map(row => row.date.slice(5)),
        datasets: [{ label: "新增达人", data: trend.map(row => row.count), borderColor: "#e56b46", backgroundColor: "rgba(229, 107, 70, 0.16)", fill: true, tension: 0.32, pointRadius: 2 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 6 } } },
      },
    }, trend.some(row => row.count > 0));
  }

  function renderCreatorList(id, records, emptyText, reasonForRecord) {
    const target = element(id);
    if (!target) return;
    target.replaceChildren();
    const values = Array.isArray(records) ? records : [];
    if (!values.length) {
      const empty = document.createElement("p");
      empty.className = "dashboard-empty";
      empty.textContent = emptyText;
      target.appendChild(empty);
      return;
    }

    values.forEach(record => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "dashboard-list-item";
      const creatorId = record.creator_id || record.analysis_id;
      if (creatorId) item.dataset.dashboardCreatorId = String(creatorId);
      const campaignId = record.campaign_id;
      if (campaignId) item.dataset.dashboardCampaignId = String(campaignId);

      const title = document.createElement("strong");
      title.textContent = record.creator_name || "未命名达人";
      const detail = document.createElement("span");
      detail.textContent = `${record.platform || "--"} · ${reasonForRecord(record)}`;
      item.append(title, detail);
      target.appendChild(item);
    });
  }

  function renderDashboard(data) {
    const overview = data?.overview || {};
    const health = data?.creator_health || {};
    const cooperation = data?.cooperation_performance || {};
    const actionItems = data?.action_items || {};

    setText("dashboard-total-creators", formatNumber(overview.total_creators));
    setText("dashboard-new-creators", formatNumber(overview.new_creators_7d));
    setText("dashboard-discovered", formatNumber(overview.discovered_count));
    setText("dashboard-cooperating", formatNumber(overview.cooperating_count));
    setText("dashboard-spend", formatMoneyTotal(
      overview.cooperation_spend,
      overview.cooperation_spend_by_currency,
      overview.cooperation_spend_unknown_currency,
    ));
    setText("dashboard-average-roi", formatNumber(overview.average_roi));
    setText("dashboard-campaigns", formatNumber(cooperation.total_campaigns));
    setText("dashboard-total-cost", formatMoneyTotal(
      cooperation.total_cost,
      cooperation.cost_totals_by_currency,
      cooperation.cost_unknown_currency_total,
    ));
    setText("dashboard-total-views", formatNumber(cooperation.total_views));
    setText("dashboard-cooperation-roi", formatNumber(cooperation.average_roi));
    renderHealthSummary(data?.health_summary);
    renderV2Health(data?.health_summary);
    renderV2Dashboard(data);

    renderCreatorList("dashboard-rising-creators", health.rising_creators, "暂无上升达人。", record => formatChange(record.change));
    renderCreatorList("dashboard-falling-creators", health.falling_creators, "暂无下滑达人。", record => formatChange(record.change));
    renderCreatorList("dashboard-expired-creators", health.expired_creators, "暂无过期数据。", record => `最近分析：${formatTime(record.last_analysis_time)}`);
    renderCreatorList("dashboard-action-expired", actionItems.expired_creators, "暂无需要更新的数据。", record => `已过期 ${record.freshness?.days ?? "--"} 天`);
    renderCreatorList("dashboard-pending-contact", actionItems.pending_contact, "暂无待联系达人。", () => "状态：待联系");
    renderCreatorList("dashboard-incomplete-cooperations", actionItems.incomplete_cooperations, "暂无待复盘事项。", record => `Campaign：${record.campaign || "未命名 Campaign"}`);
    renderCreatorList("dashboard-top-creators", cooperation.top_creators, "暂无合作数据。", record => {
      const roi = record.average_roi == null ? "ROI 暂无" : `ROI ${formatNumber(record.average_roi)}`;
      return `${record.campaign_count || 0} 个 Campaign · ${roi}`;
    });
    renderVisualizations(data);
  }

  function readableHomepage(record) {
    const rawUrl = String(record?.profile_url || "").trim();
    if (!rawUrl) return "主页链接未录入";
    try {
      const url = new URL(rawUrl);
      const host = url.hostname.replace(/^www\./i, "");
      const path = url.pathname.replace(/\/$/, "");
      return `${host}${path}` || host;
    } catch (_) {
      return rawUrl;
    }
  }

  function appendEmpty(target, text) {
    const empty = document.createElement("p");
    empty.className = "dashboard-empty";
    empty.textContent = text;
    target.appendChild(empty);
  }

  function renderV2Today(actionItems) {
    const target = element("dashboard-v2-today-list");
    if (!target) return;
    target.replaceChildren();
    const groups = [
      { label: "数据过期", records: actionItems?.expired_creators, reason: record => `已过期 ${record?.freshness?.days ?? "--"} 天` },
      { label: "待联系", records: actionItems?.pending_contact, reason: () => "等待建立联系" },
    ];
    const hasRecords = groups.some(group => Array.isArray(group.records) && group.records.length);
    if (!hasRecords) {
      appendEmpty(target, "暂无需要优先处理的事项。");
      return;
    }
    groups.forEach(group => (Array.isArray(group.records) ? group.records : []).forEach(record => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "dashboard-v2-action-item";
      if (record.creator_id) item.dataset.dashboardCreatorId = String(record.creator_id);
      if (record.campaign_id) item.dataset.dashboardCampaignId = String(record.campaign_id);
      const label = document.createElement("span");
      label.textContent = group.label;
      const title = document.createElement("strong");
      title.textContent = record.creator_name || record.campaign || "未命名对象";
      const detail = document.createElement("small");
      detail.textContent = `${record.platform || "--"} · ${group.reason(record)}`;
      item.append(label, title, detail);
      target.appendChild(item);
    }));
  }

  function renderV2Campaigns(campaigns) {
    const target = element("dashboard-v2-campaign-list");
    if (!target) return;
    target.replaceChildren();
    const rows = Array.isArray(campaigns) ? campaigns.slice(0, 6) : [];
    if (!rows.length) {
      appendEmpty(target, "暂无 Campaign。");
      return;
    }
    rows.forEach(campaign => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "dashboard-v2-campaign-item";
      item.dataset.dashboardCampaignId = String(campaign.campaign_id || "");
      const title = document.createElement("strong");
      title.textContent = campaign.name || "未命名 Campaign";
      const detail = document.createElement("span");
      detail.textContent = `${campaign.status || "--"} · ${formatNumber(campaign.creator_count)} 位达人 · 已发布 ${formatNumber(campaign.published_count)}`;
      item.append(title, detail);
      target.appendChild(item);
    });
  }

  function renderV2PlatformAccounts(rows) {
    const target = element("dashboard-v2-platform-list");
    if (!target) return;
    target.replaceChildren();
    const values = Array.isArray(rows) ? rows : [];
    if (!values.length) {
      appendEmpty(target, "暂无平台账号数据。");
      return;
    }
    values.forEach(row => {
      const item = document.createElement("div");
      item.className = "dashboard-v2-platform-row";
      const platform = document.createElement("span");
      platform.textContent = row.platform || "其他";
      const count = document.createElement("strong");
      count.textContent = `${formatNumber(row.count)} 个账号`;
      item.append(platform, count);
      target.appendChild(item);
    });
  }

  function renderV2Dashboard(data) {
    const snapshot = data?.dashboard_v2 || {};
    const overview = data?.overview || {};
    const missing = snapshot.missing || {};
    setText("dashboard-v2-creator-count", formatNumber(snapshot.creator_count));
    setText("dashboard-v2-account-count", formatNumber(snapshot.account_count));
    setText("dashboard-v2-campaign-count", formatNumber((snapshot.campaigns || []).length));
    setText("dashboard-v2-spend", formatMoneyTotal(overview.cooperation_spend, overview.cooperation_spend_by_currency, overview.cooperation_spend_unknown_currency));
    setText("dashboard-v2-roi", formatPercent(overview.average_roi));
    setText("dashboard-v2-missing-email", formatNumber((missing.email_accounts || []).length));
    setText("dashboard-v2-missing-country", formatNumber((missing.country_creators || []).length));
    setText("dashboard-v2-missing-language", formatNumber((missing.language_creators || []).length));
    setText("dashboard-v2-missing-content-type", formatNumber((missing.content_type_creators || []).length));
    renderV2Today(data?.action_items || {});
    renderV2Campaigns(snapshot.campaigns);
    renderV2PlatformAccounts(snapshot.platform_accounts);
  }

  function renderV2Health(summary) {
    const total = Number(summary?.total);
    const score = Number(summary?.score);
    setText("dashboard-v2-health-score", Number.isFinite(total) && total > 0 && Number.isFinite(score) ? `${formatNumber(score)} 分` : "暂无数据");
    setText("dashboard-v2-health-healthy", formatNumber(summary?.healthy || 0));
    setText("dashboard-v2-health-warning", formatNumber(summary?.warning || 0));
    setText("dashboard-v2-health-critical", formatNumber(summary?.critical || 0));
  }

  function renderDrawerRows() {
    const state = global.__kolconnectDashboardV2Drawer;
    const target = element("dashboard-v2-drawer-list");
    const query = String(element("dashboard-v2-drawer-search")?.value || "").trim().toLocaleLowerCase();
    if (!state || !target) return;
    target.replaceChildren();
    const rows = state.rows.filter(row => [row.creator_name, row.platform, row.username, row.profile_url, row.country, row.language]
      .some(value => String(value || "").toLocaleLowerCase().includes(query)));
    setText("dashboard-v2-drawer-count", `共 ${formatNumber(rows.length)} ${state.unit}`);
    if (!rows.length) {
      appendEmpty(target, "没有符合当前搜索条件的对象。");
      return;
    }
    rows.forEach(row => {
      const item = document.createElement("article");
      item.className = "dashboard-v2-drawer-item";
      const title = document.createElement("strong");
      title.textContent = row.creator_name || "未命名达人";
      const account = document.createElement("span");
      account.textContent = [row.platform, row.username ? `@${row.username.replace(/^@/, "")}` : ""].filter(Boolean).join(" · ") || "账号信息未录入";
      const context = document.createElement("small");
      context.textContent = [row.country, row.language].filter(Boolean).join(" · ") || "国家/语言待补充";
      const actions = document.createElement("div");
      actions.className = "dashboard-v2-drawer-item-actions";
      if (row.profile_url) {
        const link = document.createElement("a");
        link.href = row.profile_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = readableHomepage(row);
        actions.appendChild(link);
      }
      const view = document.createElement("button");
      view.type = "button";
      view.className = "text-btn";
      view.textContent = "查看达人";
      view.dataset.dashboardCreatorId = String(row.creator_id || "");
      actions.appendChild(view);
      item.append(title, account, context, actions);
      target.appendChild(item);
    });
  }

  function openDrawer(kind) {
    const snapshot = dashboardData?.dashboard_v2 || {};
    const missing = snapshot.missing || {};
    const configurations = {
      "missing-email": { title: "缺少邮箱的账号", rows: missing.email_accounts || [], unit: "个账号", primary: "批量补全邮箱" },
      "missing-country": { title: "缺少国家/地区的达人", rows: missing.country_creators || [], unit: "位达人" },
      "missing-language": { title: "缺少语言的达人", rows: missing.language_creators || [], unit: "位达人" },
      "missing-content-type": { title: "缺少内容类型的达人", rows: missing.content_type_creators || [], unit: "位达人" },
    };
    const config = configurations[kind];
    if (!config) return;
    global.__kolconnectDashboardV2Drawer = config;
    setText("dashboard-v2-drawer-title", config.title);
    const search = element("dashboard-v2-drawer-search");
    if (search) search.value = "";
    const primary = element("dashboard-v2-drawer-primary");
    if (primary) {
      primary.hidden = !config.primary;
      primary.textContent = config.primary || "";
      primary.dataset.dashboardV2DrawerPrimary = kind;
    }
    const drawer = element("dashboard-v2-drawer");
    if (drawer) drawer.hidden = false;
    renderDrawerRows();
    search?.focus();
  }

  function closeDrawer() {
    const drawer = element("dashboard-v2-drawer");
    if (drawer) drawer.hidden = true;
    global.__kolconnectDashboardV2Drawer = null;
  }

  function renderHealthSummary(summary) {
    const total = Number(summary?.total);
    const hasHealthData = Number.isFinite(total) && total > 0;
    const healthy = Number(summary?.healthy) || 0;
    const warning = Number(summary?.warning) || 0;
    const critical = Number(summary?.critical) || 0;
    const score = Number(summary?.score);
    setText("dashboard-health-score", hasHealthData && Number.isFinite(score) ? formatNumber(score) : "--");
    const emptyState = element("dashboard-health-empty");
    if (emptyState) emptyState.hidden = hasHealthData;
    setText("dashboard-health-healthy", formatNumber(healthy));
    setText("dashboard-health-warning", formatNumber(warning));
    setText("dashboard-health-critical", formatNumber(critical));
    const distribution = [
      ["dashboard-health-healthy-bar", healthy],
      ["dashboard-health-warning-bar", warning],
      ["dashboard-health-critical-bar", critical],
    ];
    distribution.forEach(([id, count]) => {
      const bar = element(id);
      if (bar) bar.style.width = hasHealthData ? `${Math.max(0, count) / total * 100}%` : "0%";
    });
  }

  function renderRiskSummary(data, failed = false) {
    const summary = data?.summary || {};
    setText("dashboard-risk-high", failed ? "--" : formatNumber(summary.high || 0));
    setText("dashboard-risk-medium", failed ? "--" : formatNumber(summary.medium || 0));
    setText("dashboard-risk-low", failed ? "--" : formatNumber(summary.low || 0));
    const error = element("dashboard-risk-error");
    if (error) error.hidden = !failed;
  }

  function renderPlatformAnalytics(data, failed = false) {
    const rows = Array.isArray(data?.platforms) ? data.platforms : [];
    const byPlatform = new Map(rows.map(row => [String(row?.platform || ""), row]));
    const labels = { tiktok: "TikTok", instagram: "Instagram", youtube: "YouTube" };
    const chartRows = [];
    Object.entries(labels).forEach(([platform, label]) => {
      const row = byPlatform.get(platform) || {};
      setText(`platform-${platform}-creators`, formatNumber(row.creator_count || 0));
      setText(`platform-${platform}-followers-median`, row.followers_median == null ? "--" : formatNumber(row.followers_median));
      setText(`platform-${platform}-followers-average`, row.followers_average == null ? "--" : formatNumber(row.followers_average));
      setText(`platform-${platform}-relations`, formatNumber(row.campaign_creator_count || 0));
      setText(`platform-${platform}-publish-rate`, formatPercent(row.publish_rate));
      setText(`platform-${platform}-views`, formatNumber(row.views_total || 0));
      setText(`platform-${platform}-likes`, formatNumber(row.likes_total || 0));
      setText(`platform-${platform}-comments`, formatNumber(row.comments_total || 0));
      setText(`platform-${platform}-engagement`, formatPercent(row.visible_engagement_rate));
      setText(`platform-${platform}-cost`, formatMoneyTotal(
        row.cost_total,
        row.cost_totals_by_currency,
        row.cost_unknown_currency_total,
      ));
      setText(`platform-${platform}-roi`, row.recorded_roi_average == null ? "--" : formatNumber(row.recorded_roi_average));
      chartRows.push({ label, row });
    });

    const hasChartData = chartRows.some(({ row }) =>
      Number(row.creator_count) > 0 || Number(row.campaign_creator_count) > 0
    );
    renderChart("dashboard-platform-analytics-chart", "dashboard-platform-analytics-empty", {
      type: "bar",
      data: {
        labels: chartRows.map(item => item.label),
        datasets: [
          { label: "达人", data: chartRows.map(item => Number(item.row.creator_count) || 0), backgroundColor: "#2f7d6d", borderRadius: 5 },
          { label: "合作", data: chartRows.map(item => Number(item.row.campaign_creator_count) || 0), backgroundColor: "#5574b9", borderRadius: 5 },
          { label: "已发布", data: chartRows.map(item => Number(item.row.published_count) || 0), backgroundColor: "#e56b46", borderRadius: 5 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } },
      },
    }, hasChartData);
    const error = element("dashboard-platform-analytics-error");
    if (error) error.hidden = !failed;
  }

  function renderRanking(id, rows, includeActive) {
    const target = element(id);
    if (!target) return;
    target.replaceChildren();
    const values = Array.isArray(rows) ? rows : [];
    if (!values.length) {
      const empty = document.createElement("p");
      empty.className = "dashboard-empty";
      empty.textContent = "暂无数据";
      target.appendChild(empty);
      return;
    }
    values.forEach(row => {
      const item = document.createElement("div");
      item.className = "dashboard-ranking-row";
      const label = document.createElement("span");
      label.textContent = String(row?.name || "Unknown");
      const value = document.createElement("strong");
      value.textContent = formatNumber(row?.creator_count || 0);
      item.appendChild(label);
      item.appendChild(value);
      if (includeActive) {
        const active = document.createElement("small");
        active.textContent = `活跃 ${formatNumber(row?.active_creator_count || 0)}`;
        item.appendChild(active);
      }
      target.appendChild(item);
    });
  }

  function renderGeographyAnalytics(data, failed = false) {
    renderRanking("dashboard-country-list", data?.countries, true);
    renderRanking("dashboard-language-list", data?.languages, false);
    renderRanking("dashboard-v2-country-list", data?.countries, true);
    renderRanking("dashboard-v2-language-list", data?.languages, false);
    const error = element("dashboard-geography-error");
    if (error) error.hidden = !failed;
  }

  function renderRecordedRoiTrend(data, failed = false) {
    const trend = (Array.isArray(data?.trend) ? data.trend : [])
      .filter(row => typeof row?.month === "string")
      .map(row => ({ ...row, average_recorded_roi: row.average_recorded_roi == null ? null : Number(row.average_recorded_roi) }));
    const latest = trend.length ? trend[trend.length - 1].average_recorded_roi : null;
    setText("dashboard-roi-latest", Number.isFinite(latest) ? formatNumber(latest) : "--");
    setText("dashboard-v2-roi-latest", Number.isFinite(latest) ? `${formatNumber(latest)}%` : "暂无已录入 ROI");
    renderChart("dashboard-roi-trend-chart", "dashboard-roi-trend-empty", {
      type: "line",
      data: {
        labels: trend.map(row => row.month),
        datasets: [{
          label: "Average recorded ROI",
          data: trend.map(row => Number.isFinite(row.average_recorded_roi) ? row.average_recorded_roi : null),
          borderColor: "#b65d7a",
          backgroundColor: "rgba(182, 93, 122, 0.14)",
          fill: true,
          tension: 0.28,
          spanGaps: false,
          pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } } },
      },
    }, trend.some(row => Number.isFinite(row.average_recorded_roi)));
    const error = element("dashboard-roi-trend-error");
    if (error) error.hidden = !failed;
  }

  function isCurrentLifecycle(expectedLifecycle, controller) {
    return Boolean(
      resources
      && !resources.disposed
      && expectedLifecycle === lifecycleId
      && !controller.signal.aborted,
    );
  }

  async function loadDashboard() {
    if (!resources) return;
    const expectedLifecycle = lifecycleId;
    requestController?.abort();
    const controller = resources.createAbortController();
    requestController = controller;

    try {
      const data = await global.KOLConnectAPI.get("/api/dashboard", { signal: controller.signal });
      if (!isCurrentLifecycle(expectedLifecycle, controller)) return;
      dashboardData = data;
      renderDashboard(dashboardData);
    } catch (error) {
      if (error?.name === "AbortError" || !isCurrentLifecycle(expectedLifecycle, controller)) return;
      getApp().showError(error);
    } finally {
      if (requestController === controller) requestController = null;
    }
  }

  async function loadRisks() {
    if (!resources) return;
    const expectedLifecycle = lifecycleId;
    riskController?.abort();
    const controller = resources.createAbortController();
    riskController = controller;
    try {
      const data = await global.KOLConnectAPI.get("/api/risks", { signal: controller.signal });
      if (!isCurrentLifecycle(expectedLifecycle, controller)) return;
      renderRiskSummary(data);
    } catch (error) {
      if (error?.name !== "AbortError" && isCurrentLifecycle(expectedLifecycle, controller)) {
        renderRiskSummary(null, true);
      }
    } finally {
      if (riskController === controller) riskController = null;
    }
  }

  async function loadPlatformAnalytics() {
    if (!resources) return;
    const expectedLifecycle = lifecycleId;
    analyticsController?.abort();
    const controller = resources.createAbortController();
    analyticsController = controller;
    try {
      const data = await global.KOLConnectAPI.get("/api/analytics/platforms", { signal: controller.signal });
      if (!isCurrentLifecycle(expectedLifecycle, controller)) return;
      renderPlatformAnalytics(data);
    } catch (error) {
      if (error?.name !== "AbortError" && isCurrentLifecycle(expectedLifecycle, controller)) {
        renderPlatformAnalytics(null, true);
      }
    } finally {
      if (analyticsController === controller) analyticsController = null;
    }
  }

  async function loadGeographyAnalytics() {
    if (!resources) return;
    const expectedLifecycle = lifecycleId;
    geographyController?.abort();
    const controller = resources.createAbortController();
    geographyController = controller;
    try {
      const data = await global.KOLConnectAPI.get("/api/analytics/geography", { signal: controller.signal });
      if (!isCurrentLifecycle(expectedLifecycle, controller)) return;
      renderGeographyAnalytics(data);
    } catch (error) {
      if (error?.name !== "AbortError" && isCurrentLifecycle(expectedLifecycle, controller)) {
        renderGeographyAnalytics(null, true);
      }
    } finally {
      if (geographyController === controller) geographyController = null;
    }
  }

  async function loadRecordedRoiTrend() {
    if (!resources) return;
    const expectedLifecycle = lifecycleId;
    roiTrendController?.abort();
    const controller = resources.createAbortController();
    roiTrendController = controller;
    try {
      const data = await global.KOLConnectAPI.get("/api/analytics/roi-trend", { signal: controller.signal });
      if (!isCurrentLifecycle(expectedLifecycle, controller)) return;
      renderRecordedRoiTrend(data);
    } catch (error) {
      if (error?.name !== "AbortError" && isCurrentLifecycle(expectedLifecycle, controller)) {
        renderRecordedRoiTrend(null, true);
      }
    } finally {
      if (roiTrendController === controller) roiTrendController = null;
    }
  }

  function handleDashboardClick(event) {
    const drawerClose = event.target.closest?.("[data-dashboard-v2-drawer-close]");
    if (drawerClose) {
      closeDrawer();
      return;
    }
    const customization = event.target.closest?.("#dashboard-v2-customize");
    if (customization) {
      getApp().navigate("settings").catch(getApp().showError);
      return;
    }
    const open = event.target.closest?.("[data-dashboard-v2-open]")?.dataset.dashboardV2Open;
    if (open?.startsWith("missing-")) {
      openDrawer(open);
      return;
    }
    if (open === "campaigns") {
      getApp().navigate("campaigns").catch(getApp().showError);
      return;
    }
    if (open === "accounts") {
      getApp().navigate("creator-library").catch(getApp().showError);
      return;
    }
    const primary = event.target.closest?.("[data-dashboard-v2-drawer-primary]");
    if (primary?.dataset.dashboardV2DrawerPrimary === "missing-email") {
      getApp().navigate("scrape").then(() => {
        const source = document.querySelector('input[name="email-source"][value="creator_library"]');
        if (!source) return;
        source.checked = true;
        source.dispatchEvent(new Event("change", { bubbles: true }));
      }).catch(getApp().showError);
      closeDrawer();
      return;
    }
    const campaignItem = event.target.closest?.("[data-dashboard-campaign-id]");
    const campaignId = campaignItem?.dataset.dashboardCampaignId;
    if (campaignId) {
      getApp().navigate("campaign-detail", { campaignId }).catch(getApp().showError);
      return;
    }
    const item = event.target.closest?.("[data-dashboard-creator-id]");
    const creatorId = item?.dataset.dashboardCreatorId;
    if (!creatorId) return;
    getApp().navigate("creator-library-detail", { creatorId }).catch(getApp().showError);
  }

  const page = {
    async load() {
      resources?.cleanup();
      destroyCharts();
      resources = global.KOLConnectPageResources.create();
      lifecycleId += 1;
      dashboardData = null;
      closeDrawer();
      applyDashboardLayout();
      await Promise.all([
        loadDashboard(), loadRisks(), loadPlatformAnalytics(),
        loadGeographyAnalytics(), loadRecordedRoiTrend(),
      ]);
    },

    bind() {
      if (!resources || resources.disposed) return;
      resources.listen(element("dashboard-refresh"), "click", () => Promise.all([
        loadDashboard(), loadPlatformAnalytics(), loadGeographyAnalytics(), loadRecordedRoiTrend(),
      ]));
      resources.listen(document.querySelector('.page[data-page="dashboard"]'), "click", handleDashboardClick);
      resources.listen(element("dashboard-v2-drawer"), "click", handleDashboardClick);
      resources.listen(element("dashboard-v2-drawer-search"), "input", renderDrawerRows);
    },

    unbind() {
      lifecycleId += 1;
      requestController?.abort();
      requestController = null;
      riskController?.abort();
      riskController = null;
      analyticsController?.abort();
      analyticsController = null;
      geographyController?.abort();
      geographyController = null;
      roiTrendController?.abort();
      roiTrendController = null;
      resources?.cleanup();
      resources = null;
      dashboardData = null;
      closeDrawer();
      applyDashboardLayout();
      destroyCharts();
    },
  };

  global.KOLConnectPages.registerPage("dashboard", page);
  global.KOLConnectDashboardPreferences = {
    modules: () => MODULES.map(module => ({ ...module })),
    get: readLayout,
    setVisible(id, visible) { updateLayout(layout => { if (layout.visible[id] !== undefined && !MODULES.find(module => module.id === id)?.essential) layout.visible[id] = Boolean(visible); }); },
    move(id, direction) { updateLayout(layout => {
      if (id === "today") return;
      const index = layout.order.indexOf(id);
      const next = index + direction;
      if (index >= 0 && next > 0 && next < layout.order.length) [layout.order[index], layout.order[next]] = [layout.order[next], layout.order[index]];
    }); },
    reset() { saveLayout(defaultLayout()); applyDashboardLayout(); },
    apply: applyDashboardLayout,
  };
})(window);
