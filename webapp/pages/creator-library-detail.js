(function registerCreatorLibraryDetailPage(global) {
  "use strict";

  const DETAIL_TABS = new Set(["overview", "content", "history", "cooperations"]);

  let pageContext = null;
  let detailController = null;
  let campaignsController = null;
  let editController = null;
  let campaignModal = null;
  let creatorId = "";
  let detail = null;
  let creatorCampaigns = [];
  let lifecycleId = 0;

  function element(id) {
    return document.getElementById(id);
  }

  function valueOf(id, fallback = "") {
    const target = element(id);
    return target ? (target.value ?? fallback) : fallback;
  }

  function setValue(id, value) {
    const target = element(id);
    if (target) target.value = value ?? "";
  }

  function setText(id, value) {
    const target = element(id);
    if (target) target.textContent = String(value ?? "");
  }

  function showError(error) {
    if (error?.name !== "AbortError") pageContext?.ui.showError(error);
  }

  function formatMetric(value) {
    if (value === null || value === undefined || value === "") return "--";
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString() : String(value);
  }

  function formatTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  function formatFreshness(freshness) {
    if (!freshness || freshness.status === "unknown") return "分析时间未知";
    const days = Number(freshness.days || 0);
    if (freshness.status === "fresh") return `最新（${days} 天前）`;
    if (freshness.status === "update_recommended") return `建议更新（${days} 天前）`;
    return `数据过期（${days} 天前）`;
  }

  function renderList(id, items, emptyText) {
    const list = element(id);
    if (!list) return;
    const values = Array.isArray(items) && items.length ? items : [emptyText];
    list.replaceChildren(...values.map(value => {
      const item = document.createElement("li");
      item.textContent = value;
      return item;
    }));
  }

  function renderDefinitionList(target, entries) {
    if (!target) return;
    target.replaceChildren(...entries.flatMap(([term, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      if (typeof value === "string" && /^https?:\/\//i.test(value)) {
        const link = document.createElement("a");
        link.href = value;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = value;
        dd.appendChild(link);
      } else {
        dd.textContent = value || "--";
      }
      return [dt, dd];
    }));
  }

  function setDetailTab(tab) {
    const state = pageContext.state.creatorLibrary;
    state.detailTab = DETAIL_TABS.has(tab) ? tab : "overview";
    document.querySelectorAll(".detail-tab").forEach(button => {
      button.classList.toggle("active", button.dataset.detailTab === state.detailTab);
    });
    document.querySelectorAll(".detail-panel").forEach(panel => {
      panel.hidden = panel.dataset.detailPanel !== state.detailTab;
    });
  }

  function renderCooperations(data) {
    const statistics = data.cooperation_statistics || {};
    const cooperations = Array.isArray(data.cooperations) ? data.cooperations : [];
    setText("cooperation-stat-count", String(statistics.cooperation_count || 0));
    setText("cooperation-stat-spend", formatMetric(statistics.total_spend));
    setText("cooperation-stat-views", formatMetric(statistics.average_views));
    setText("cooperation-stat-roi", formatMetric(statistics.average_roi));
    const body = element("creator-cooperations-body");
    const empty = element("creator-cooperations-empty");
    if (!body || !empty) return;
    body.replaceChildren();
    empty.hidden = cooperations.length > 0;
    cooperations.forEach(cooperation => {
      const row = document.createElement("tr");
      [
        cooperation.campaign || "--",
        cooperation.platform || "--",
        cooperation.contact_date || "--",
        formatMetric(cooperation.price),
        formatMetric(cooperation.published_count),
        formatMetric(cooperation.total_views),
        formatMetric(cooperation.average_views),
        formatMetric(cooperation.roi),
        cooperation.result || "--",
        cooperation.note || "--",
      ].forEach(value => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function renderSnapshots(data) {
    const body = element("creator-library-snapshots");
    const empty = element("creator-library-snapshots-empty");
    if (!body || !empty) return;
    const snapshots = Array.isArray(data.snapshots) ? data.snapshots : [];
    body.replaceChildren();
    empty.hidden = snapshots.length > 0;
    snapshots.forEach(snapshot => {
      const row = document.createElement("tr");
      [
        formatTime(snapshot.captured_at),
        snapshot.followers || "--",
        formatMetric(snapshot.average_views),
        formatMetric(snapshot.median_views),
        formatMetric(snapshot.creator_score),
        snapshot.insight_level || "--",
      ].forEach(value => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function renderVideos(analysis) {
    const videos = element("creator-library-videos");
    if (!videos) return;
    videos.replaceChildren(...(Array.isArray(analysis.videos) ? analysis.videos : []).map(video => {
      const item = document.createElement("div");
      item.className = "creator-analysis-video";
      const link = document.createElement("a");
      link.href = video.video_url || "#";
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = video.video_url || video.video_key || "视频";
      const metric = document.createElement("span");
      metric.textContent = `播放 ${video.views || "--"} · 点赞 ${video.likes || "--"} · 评论 ${video.comments || "--"}`;
      item.append(link, metric);
      return item;
    }));
  }

  function renderCreatorCampaigns(error = null) {
    const body = element("creator-campaigns-body");
    const empty = element("creator-campaigns-empty");
    const errorMessage = element("creator-campaigns-error");
    if (!body || !empty || !errorMessage) return;
    body.replaceChildren();
    errorMessage.hidden = !error;
    errorMessage.textContent = error ? (error.message || "Campaign 数据加载失败。") : "";
    empty.hidden = creatorCampaigns.length > 0 || Boolean(error);
    creatorCampaigns.forEach(campaign => {
      const row = document.createElement("tr");
      [
        campaign.name || "未命名 Campaign",
        campaign.product_name || "--",
        campaign.status || "--",
        campaign.platform || "--",
        [campaign.start_date, campaign.end_date].filter(Boolean).join(" 至 ") || "--",
      ].forEach(value => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });
      const actionCell = document.createElement("td");
      const action = document.createElement("button");
      action.type = "button";
      action.className = "soft-btn compact-btn";
      action.dataset.creatorCampaignId = String(campaign.campaign_id || "");
      action.textContent = "查看 Campaign";
      actionCell.appendChild(action);
      row.appendChild(actionCell);
      body.appendChild(row);
    });
  }

  function render(data) {
    const record = data.record || {};
    const analysis = data.analysis || {};
    const creator = analysis.creator || {};
    const videoAnalysis = analysis.video_analysis || {};
    const insight = analysis.creator_insight || {};
    const trend = data.trend || {};
    const archived = Boolean(record.archived_at);

    setText(
      "creator-library-detail-summary",
      `${record.creator_name || "未命名达人"} · ${record.platform || "--"} · ${record.profile_url || "--"}`,
    );
    setText("creator-library-detail-level", record.insight_level || "insufficient");
    setText(
      "creator-library-data-meta",
      `数据更新时间：${formatTime(record.data_updated_at)} · 来源：${record.source || "--"} · 最近分析时间：${formatTime(record.last_analysis_time || record.analysis_time)}`,
    );
    setText("creator-library-freshness", formatFreshness(trend.freshness));
    renderDefinitionList(element("creator-library-basic"), [
      ["达人名称", creator.creator_name],
      ["平台", creator.platform],
      ["主页链接", creator.profile_url],
      ["粉丝数", creator.followers],
      ["内容类型", analysis.content_category],
      ["简介", creator.bio],
    ]);
    renderDefinitionList(element("creator-library-video-metrics"), [
      ["样本数量", formatMetric(videoAnalysis.sample_size)],
      ["平均播放", formatMetric(videoAnalysis.average_views)],
      ["中位播放", formatMetric(videoAnalysis.median_views)],
      ["最高播放", formatMetric(videoAnalysis.max_views)],
      ["最低播放", formatMetric(videoAnalysis.min_views)],
      ["播放稳定性", formatMetric(videoAnalysis.view_stability)],
      ["播放完整率", `${Math.round(Number(videoAnalysis.view_coverage || 0) * 100)}%`],
    ]);
    setText("creator-library-recommendation", insight.recommendation || "请结合主页内容进行人工判断。");
    renderList("creator-library-strengths", insight.strengths, "暂无优势结论。");
    renderList("creator-library-risks", insight.risks, "暂无风险结论。");
    renderSnapshots(data);
    renderCooperations(data);
    renderVideos(analysis);
    const archiveButton = element("creator-library-detail-archive");
    if (archiveButton) archiveButton.textContent = archived ? "恢复达人" : "归档达人";
    ["creator-library-detail-edit", "creator-library-detail-add-campaign", "creator-library-detail-task"].forEach(id => {
      const button = element(id);
      if (button) button.disabled = archived;
    });
    setDetailTab(pageContext.state.creatorLibrary.detailTab);
  }

  function clearRenderedDetail(message = "正在加载达人资料...") {
    setText("creator-library-detail-summary", message);
    setText("creator-library-detail-level", "--");
    setText("creator-library-data-meta", "--");
    setText("creator-library-freshness", "--");
    [
      "creator-library-basic",
      "creator-library-video-metrics",
      "creator-library-strengths",
      "creator-library-risks",
      "creator-library-snapshots",
      "creator-cooperations-body",
      "creator-library-videos",
    ].forEach(id => element(id)?.replaceChildren());
  }

  async function loadDetail() {
    const currentLifecycle = lifecycleId;
    detailController?.abort();
    campaignsController?.abort();
    detailController = pageContext.resources.createAbortController();
    campaignsController = pageContext.resources.createAbortController();
    const detailRequest = pageContext.api.get(`/api/creator-library/${encodeURIComponent(creatorId)}`, {
      signal: detailController.signal,
    });
    const campaignsRequest = pageContext.api.get(
      `/api/campaigns?creator_id=${encodeURIComponent(creatorId)}`,
      { signal: campaignsController.signal },
    );
    const [detailResult, campaignsResult] = await Promise.allSettled([detailRequest, campaignsRequest]);
    const requestedCreatorId = String(pageContext?.params?.creatorId || "").trim();
    if (!pageContext || currentLifecycle !== lifecycleId || creatorId !== requestedCreatorId) return;
    if (detailResult.status === "rejected") throw detailResult.reason;
    const data = detailResult.value;
    detail = data;
    if (campaignsResult.status === "fulfilled") {
      creatorCampaigns = Array.isArray(campaignsResult.value.campaigns) ? campaignsResult.value.campaigns : [];
      renderCreatorCampaigns();
    } else if (campaignsResult.reason?.name !== "AbortError") {
      creatorCampaigns = [];
      renderCreatorCampaigns(campaignsResult.reason);
    }
    render(data);
  }

  async function reloadCreatorCampaigns() {
    const currentLifecycle = lifecycleId;
    campaignsController?.abort();
    campaignsController = pageContext.resources.createAbortController();
    try {
      const data = await pageContext.api.get(
        `/api/campaigns?creator_id=${encodeURIComponent(creatorId)}`,
        { signal: campaignsController.signal },
      );
      if (!pageContext || currentLifecycle !== lifecycleId) return;
      creatorCampaigns = Array.isArray(data.campaigns) ? data.campaigns : [];
      renderCreatorCampaigns();
    } catch (error) {
      if (error?.name !== "AbortError" && pageContext && currentLifecycle === lifecycleId) {
        renderCreatorCampaigns(error);
      }
    }
  }

  async function openCollaborationTask() {
    if (detail?.record?.archived_at) return;
    const context = pageContext;
    const data = await context.api.post(
      `/api/creator-library/${encodeURIComponent(creatorId)}/create-task`,
      {},
      { signal: context.resources.signal },
    );
    const task = data.task;
    if (!task?.id) throw new Error("未找到关联的审核任务。");
    context.state.currentTaskId = task.id;
    context.state.currentTask = task;
    context.state.review.taskId = task.id;
    global.localStorage.setItem("kolconnect.currentTaskId", task.id);
    await context.navigate("review");
    context.ui.showSaved(data.message || "已打开关联的审核任务。");
  }

  function listen(id, type, listener) {
    const target = element(id);
    if (target) pageContext.resources.listen(target, type, listener);
  }

  function openCampaignModal() {
    if (!detail?.record || detail.record.archived_at) throw new Error("已归档达人需恢复后才能加入 Campaign。");
    return campaignModal.open(detail.record, { onCreated: reloadCreatorCampaigns });
  }

  function closeEditModal() {
    const modal = element("creator-edit-modal");
    if (modal) modal.hidden = true;
    const message = element("creator-edit-message");
    if (message) {
      message.hidden = true;
      message.textContent = "";
    }
  }

  function showEditMessage(message) {
    const target = element("creator-edit-message");
    if (!target) return;
    target.textContent = message;
    target.hidden = !message;
  }

  function renderAgencyOptions(agencies, selectedAgencyId) {
    const select = element("creator-edit-agency");
    if (!select) return;
    select.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "No Agency";
    select.appendChild(emptyOption);
    agencies.forEach(agency => {
      const option = document.createElement("option");
      option.value = String(agency.agency_id || "");
      option.textContent = String(agency.name || agency.agency_id || "Unnamed Agency");
      select.appendChild(option);
    });
    select.value = String(selectedAgencyId || "");
  }

  async function openEditModal() {
    if (!detail?.record || detail.record.archived_at) return;
    const record = detail.record;
    const analysis = detail.analysis || {};
    const creator = analysis.creator || {};
    setValue("creator-edit-name", record.creator_name || creator.creator_name);
    setValue("creator-edit-platform", record.platform || creator.platform);
    setValue("creator-edit-profile-url", record.profile_url || creator.profile_url);
    setValue("creator-edit-followers", record.followers || creator.followers);
    setValue("creator-edit-content-category", record.content_category || analysis.content_category);
    setValue("creator-edit-bio", record.bio || creator.bio);
    renderAgencyOptions([], record.agency_id);
    element("creator-edit-modal").hidden = false;
    showEditMessage("");

    editController?.abort();
    editController = pageContext.resources.createAbortController();
    try {
      const data = await pageContext.api.get("/api/local/agencies", { signal: editController.signal });
      if (!pageContext || element("creator-edit-modal")?.hidden) return;
      renderAgencyOptions(Array.isArray(data.agencies) ? data.agencies : [], record.agency_id);
    } catch (error) {
      if (error?.name !== "AbortError") showEditMessage(error.message || "Agency 列表加载失败。");
    }
  }

  async function saveCreatorProfile(event) {
    event.preventDefault();
    if (!detail?.record || detail.record.archived_at) return;
    const saveButton = element("creator-edit-save");
    if (saveButton) saveButton.disabled = true;
    showEditMessage("");
    try {
      await pageContext.api.patch(
        `/api/creator-library/${encodeURIComponent(creatorId)}`,
        {
          creator_name: valueOf("creator-edit-name").trim(),
          profile_url: valueOf("creator-edit-profile-url").trim(),
          followers: valueOf("creator-edit-followers").trim(),
          content_category: valueOf("creator-edit-content-category").trim(),
          bio: valueOf("creator-edit-bio").trim(),
          agency_id: valueOf("creator-edit-agency").trim(),
        },
        { signal: pageContext.resources.signal },
      );
      closeEditModal();
      await loadDetail();
      pageContext.ui.showSaved("达人资料已保存。");
    } catch (error) {
      if (error?.name !== "AbortError") showEditMessage(error.message || "达人资料保存失败。");
    } finally {
      if (saveButton) saveButton.disabled = false;
    }
  }

  async function changeArchiveState() {
    if (!detail?.record) return;
    const archived = Boolean(detail.record.archived_at);
    const message = archived
      ? "恢复该达人到默认达人库？"
      : "归档后，达人将从默认列表隐藏，Campaign、Snapshot 和 Insight 数据会保留。";
    if (!global.confirm(message)) return;
    await pageContext.api.patch(
      `/api/creator-library/${encodeURIComponent(creatorId)}`,
      { archived_at: archived ? null : new Date().toISOString() },
      { signal: pageContext.resources.signal },
    );
    await loadDetail();
    pageContext.ui.showSaved(archived ? "达人已恢复。" : "达人已归档。");
  }

  function handleCampaignAction(event) {
    const button = event.target.closest("[data-creator-campaign-id]");
    if (!button) return;
    const campaignId = String(button.dataset.creatorCampaignId || "").trim();
    if (campaignId) pageContext.navigate("campaign-detail", { campaignId }).catch(showError);
  }

  const creatorLibraryDetailPage = {
    async load(context) {
      if (!context?.state || !context.api || !context.resources || !context.params) {
        throw new Error("Creator detail page context is incomplete.");
      }
      pageContext = context;
      lifecycleId += 1;
      context.state.creatorLibrary ||= {};
      context.state.creatorLibrary.detailTab = DETAIL_TABS.has(context.state.creatorLibrary.detailTab)
        ? context.state.creatorLibrary.detailTab
        : "overview";
      creatorId = String(context.params.creatorId || "").trim();
      detail = null;
      creatorCampaigns = [];
      campaignModal = global.KOLConnectCreatorCampaignModal.create(context);
      clearRenderedDetail();
      renderCreatorCampaigns();
      if (!creatorId) {
        clearRenderedDetail("缺少 Creator ID，请返回达人库重新进入。");
        throw new Error("Creator ID is required.");
      }
      await loadDetail();
    },

    bind() {
      campaignModal.bind();
      document.querySelectorAll(".detail-tab").forEach(button => {
        pageContext.resources.listen(button, "click", () => setDetailTab(button.dataset.detailTab));
      });
      listen("creator-library-detail-back", "click", () => pageContext.navigate("creator-library"));
      listen("creator-library-detail-edit", "click", () => openEditModal().catch(showError));
      listen("creator-library-detail-archive", "click", () => changeArchiveState().catch(showError));
      listen("creator-library-detail-add-campaign", "click", () => openCampaignModal().catch(showError));
      listen("creator-library-detail-task", "click", () => openCollaborationTask().catch(showError));
      listen("creator-campaigns-body", "click", handleCampaignAction);
      listen("creator-edit-modal-close", "click", closeEditModal);
      listen("creator-edit-cancel", "click", closeEditModal);
      listen("creator-edit-form", "submit", saveCreatorProfile);
    },

    unbind() {
      lifecycleId += 1;
      campaignModal?.destroy();
      pageContext?.resources.cleanup();
      pageContext = null;
      detailController = null;
      campaignsController = null;
      editController = null;
      campaignModal = null;
      creatorId = "";
      detail = null;
      creatorCampaigns = [];
      closeEditModal();
    },
  };

  global.KOLConnectPages.registerPage("creator-library-detail", creatorLibraryDetailPage);
})(window);
