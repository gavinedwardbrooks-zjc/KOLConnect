(function registerDashboardPage(global) {
  "use strict";

  let resources = null;
  let requestController = null;
  let dashboardData = null;
  let lifecycleId = 0;
  const charts = new Map();
  const CHART_COLORS = ["#e56b46", "#2f7d6d", "#e9a23b", "#5574b9", "#b65d7a", "#717171"];

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
    setText("dashboard-spend", formatNumber(overview.cooperation_spend));
    setText("dashboard-average-roi", formatNumber(overview.average_roi));
    setText("dashboard-campaigns", formatNumber(cooperation.total_campaigns));
    setText("dashboard-total-cost", formatNumber(cooperation.total_cost));
    setText("dashboard-total-views", formatNumber(cooperation.total_views));
    setText("dashboard-cooperation-roi", formatNumber(cooperation.average_roi));

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

  function handleDashboardClick(event) {
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
      await loadDashboard();
    },

    bind() {
      if (!resources || resources.disposed) return;
      resources.listen(element("dashboard-refresh"), "click", () => loadDashboard());
      resources.listen(document.querySelector('.page[data-page="dashboard"]'), "click", handleDashboardClick);
    },

    unbind() {
      lifecycleId += 1;
      requestController?.abort();
      requestController = null;
      resources?.cleanup();
      resources = null;
      dashboardData = null;
      destroyCharts();
    },
  };

  global.KOLConnectPages.registerPage("dashboard", page);
})(window);
