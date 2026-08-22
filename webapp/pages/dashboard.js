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
    setText("dashboard-spend", formatNumber(overview.cooperation_spend));
    setText("dashboard-average-roi", formatNumber(overview.average_roi));
    setText("dashboard-campaigns", formatNumber(cooperation.total_campaigns));
    setText("dashboard-total-cost", formatNumber(cooperation.total_cost));
    setText("dashboard-total-views", formatNumber(cooperation.total_views));
    setText("dashboard-cooperation-roi", formatNumber(cooperation.average_roi));
    renderHealthSummary(data?.health_summary);

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
      setText(`platform-${platform}-cost`, formatNumber(row.cost_total || 0));
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
    const error = element("dashboard-geography-error");
    if (error) error.hidden = !failed;
  }

  function renderRecordedRoiTrend(data, failed = false) {
    const trend = (Array.isArray(data?.trend) ? data.trend : [])
      .filter(row => typeof row?.month === "string")
      .map(row => ({ ...row, average_recorded_roi: row.average_recorded_roi == null ? null : Number(row.average_recorded_roi) }));
    const latest = trend.length ? trend[trend.length - 1].average_recorded_roi : null;
    setText("dashboard-roi-latest", Number.isFinite(latest) ? formatNumber(latest) : "--");
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
      destroyCharts();
    },
  };

  global.KOLConnectPages.registerPage("dashboard", page);
})(window);
