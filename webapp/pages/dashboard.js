(function registerDashboardPage(global) {
  "use strict";

  let resources = null;
  let requestController = null;
  let dashboardData = null;
  let lifecycleId = 0;

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
    const item = event.target.closest?.("[data-dashboard-creator-id]");
    const creatorId = item?.dataset.dashboardCreatorId;
    if (!creatorId) return;
    getApp().navigate("creator-library-detail", { creatorId }).catch(getApp().showError);
  }

  const page = {
    async load() {
      resources?.cleanup();
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
    },
  };

  global.KOLConnectPages.registerPage("dashboard", page);
})(window);
