(function registerCreatorLibraryDetailPage(global) {
  "use strict";

  const DETAIL_TABS = new Set(["overview", "content", "history", "cooperations"]);

  let pageContext = null;
  let detailController = null;
  let campaignsController = null;
  let editController = null;
  let summaryController = null;
  let similarController = null;
  let campaignModal = null;
  let mergeModal = null;
  let creatorId = "";
  let detail = null;
  let intelligence = null;
  let creatorCampaigns = [];
  let historicalPerformance = null;
  let selectedAccountKey = "";
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

  function accountKey(account) {
    return String(account?.account_id || account?.account_uid || account?.profile_url || "");
  }

  function accountIdentity(account) {
    const username = String(account?.username || "").trim();
    if (username) return username.startsWith("@") ? username : `@${username}`;
    try {
      const url = new URL(String(account?.profile_url || ""));
      return url.pathname.replace(/^\/+|\/+$/g, "") || url.hostname;
    } catch (_error) {
      return String(account?.profile_url || account?.account_uid || "账号");
    }
  }

  function accountSnapshot(data, account) {
    const uid = String(account?.account_uid || "");
    if (!uid) return null;
    return (Array.isArray(data?.snapshots) ? data.snapshots : []).find(
      snapshot => String(snapshot?.account_uid || "") === uid,
    ) || null;
  }

  function selectedAccount(data) {
    const accounts = Array.isArray(data?.accounts) ? data.accounts : [];
    return accounts.find(account => accountKey(account) === selectedAccountKey) || null;
  }

  function resolveDefaultAccount(data) {
    const accounts = Array.isArray(data?.accounts) ? data.accounts : [];
    const params = pageContext?.params || {};
    const preferred = String(params.accountId || params.account_id || params.profileUrl || "");
    const recordUid = String(data?.record?.account_uid || "");
    const recordPlatform = String(data?.record?.platform || "").trim().toLowerCase();
    const account = (preferred && accounts.find(item => (
      String(item?.account_id || "") === preferred
      || String(item?.profile_url || "") === preferred
    ))) || (recordUid && accounts.find(item => String(item?.account_uid || "") === recordUid))
      || accounts.find(item => String(item?.platform || "").trim().toLowerCase() === recordPlatform)
      || accounts[0];
    selectedAccountKey = accountKey(account);
  }

  function accountFreshness(timestamp) {
    if (!timestamp) return { status: "unknown", days: null };
    const captured = new Date(timestamp);
    if (Number.isNaN(captured.getTime())) return { status: "unknown", days: null };
    const days = Math.max(0, Math.floor((Date.now() - captured.getTime()) / 86400000));
    return {
      status: days <= 7 ? "fresh" : days <= 30 ? "update_recommended" : "stale",
      days,
    };
  }

  function renderAccountSwitcher(data) {
    const container = element("creator-account-options");
    const empty = element("creator-account-empty");
    const accounts = Array.isArray(data?.accounts) ? data.accounts : [];
    setText("creator-account-count", `${accounts.length} 个`);
    if (empty) empty.hidden = accounts.length !== 0;
    if (!container) return;
    container.replaceChildren(...accounts.map(account => {
      const button = document.createElement("button");
      const key = accountKey(account);
      button.type = "button";
      button.className = "creator-account-option";
      button.dataset.creatorAccountKey = key;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(key === selectedAccountKey));
      if (key === selectedAccountKey) button.classList.add("active");
      const platform = document.createElement("span");
      platform.textContent = String(account?.platform || "未知平台");
      const identity = document.createElement("strong");
      identity.textContent = accountIdentity(account);
      const followers = document.createElement("small");
      followers.textContent = `粉丝 ${formatMetric(account?.followers)}`;
      button.append(platform, identity, followers);
      return button;
    }));
  }

  function handleAccountSwitch(event) {
    const button = event.target.closest("[data-creator-account-key]");
    if (!button || !detail) return;
    const key = String(button.dataset.creatorAccountKey || "");
    if (!key || key === selectedAccountKey) return;
    selectedAccountKey = key;
    render(detail);
    renderIntelligence(intelligence);
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

  function appendHistoryStat(container, label, value, detail = "") {
    const item = document.createElement("article");
    const title = document.createElement("small");
    const metric = document.createElement("strong");
    const context = document.createElement("span");
    title.textContent = label;
    metric.textContent = value;
    context.textContent = detail;
    item.append(title, metric, context);
    container.appendChild(item);
  }

  function formatCurrencyGroups(groups) {
    const entries = Object.entries(groups || {});
    return entries.length
      ? entries.map(([currency, amount]) => `${currency} ${formatMetric(amount)}`).join(" · ")
      : "--";
  }

  function renderHistoricalPerformance() {
    const data = historicalPerformance;
    const summary = element("creator-history-performance-summary");
    const money = element("creator-history-performance-money");
    const campaigns = element("creator-history-campaigns");
    const empty = element("creator-history-performance-empty");
    if (!summary || !money || !campaigns || !empty) return;
    summary.replaceChildren();
    money.replaceChildren();
    campaigns.replaceChildren();
    const hasHistory = Boolean(data && (data.cooperation_count || data.publication_count));
    empty.hidden = hasHistory;
    appendHistoryStat(summary, "合作次数", formatMetric(data?.cooperation_count), "按 CampaignCreator 去重");
    appendHistoryStat(summary, "历史 Campaign", formatMetric(data?.historical_campaign_count), "按 campaign_id 去重");
    appendHistoryStat(summary, "平均播放", formatMetric(data?.average_latest_views), `${data?.valid_publication_views_count || 0} / ${data?.total_historical_publications || 0} 条有数据`);
    appendHistoryStat(summary, "平均互动率", data?.average_latest_er == null ? "--" : `${formatMetric(data.average_latest_er)}%`, `${data?.valid_publication_er_count || 0} / ${data?.total_historical_publications || 0} 条有数据`);

    const moneyTitle = document.createElement("h3");
    moneyTitle.textContent = "金额与效率";
    const moneyText = document.createElement("p");
    moneyText.textContent = `确认成本：${formatCurrencyGroups(data?.total_cost_by_currency)} · 历史报价：${formatCurrencyGroups(data?.total_quote_by_currency)} · 未知币种成本/报价记录 ${data?.unknown_currency_records?.cost || 0}/${data?.unknown_currency_records?.quote || 0}（不纳入币种汇总）`;
    money.append(moneyTitle, moneyText);
    Object.entries(data?.efficiency_by_currency || {}).forEach(([currency, values]) => {
      const line = document.createElement("p");
      line.textContent = `${currency} · CPV ${formatMetric(values?.cpv)} · CPE ${formatMetric(values?.cpe)}`;
      money.appendChild(line);
    });
    const roi = document.createElement("p");
    roi.textContent = "ROI：--（缺少权威回报数据）";
    money.appendChild(roi);

    const campaignTitle = document.createElement("h3");
    campaignTitle.textContent = "历史 Campaign";
    campaigns.appendChild(campaignTitle);
    const history = Array.isArray(data?.historical_campaigns) ? data.historical_campaigns : [];
    if (!history.length) {
      const unavailable = document.createElement("p");
      unavailable.textContent = "暂无 Campaign 历史。";
      campaigns.appendChild(unavailable);
    } else {
      const list = document.createElement("ul");
      history.forEach(item => {
        const entry = document.createElement("li");
        entry.textContent = `${item.campaign_name || item.campaign_id} · ${item.campaign_status || "--"} · ${item.start_date || "日期未记录"}`;
        list.appendChild(entry);
      });
      campaigns.appendChild(list);
    }
  }

  function summaryMetric(measurement) {
    if (!measurement || measurement.value === null || measurement.value === undefined || measurement.value === "") return "--";
    const source = measurement.source === "creator_snapshot" ? "Snapshot" : "Insights";
    const measuredAt = measurement.measured_at ? ` · ${formatTime(measurement.measured_at)}` : " · 时间未知";
    return `${formatMetric(measurement.value)} · ${source}${measuredAt}`;
  }

  function summaryFreshnessLabel(status) {
    return {
      fresh: "数据较新",
      update_recommended: "建议更新数据",
      stale: "数据更新时间较早，请在决策前重新采集",
      unknown: "数据更新时间未知",
    }[status] || "数据更新时间未知";
  }

  function resetAISummary() {
    summaryController?.abort();
    summaryController = null;
    intelligence = null;
    const button = element("creator-ai-summary-generate");
    if (button) {
      button.disabled = false;
      button.textContent = "生成摘要";
    }
    setText("creator-ai-summary-status", "点击“生成摘要”查看本地确定性分析。");
    const content = element("creator-ai-summary-content");
    if (content) content.hidden = true;
    [
      "creator-ai-summary-profile",
      "creator-ai-summary-performance",
      "creator-ai-summary-observations",
      "creator-ai-summary-limitations",
      "creator-intelligence-audience",
    ].forEach(id => element(id)?.replaceChildren());
    [
      "creator-intelligence-ai-tags", "creator-intelligence-categories",
      "creator-intelligence-content-signals", "creator-intelligence-follower-band",
      "creator-intelligence-engagement-band", "creator-intelligence-price-band",
      "creator-intelligence-confidence",
    ].forEach(id => setText(id, "--"));
  }

  function renderIntelligence(intelligence) {
    if (!intelligence || typeof intelligence !== "object") return;
    const account = selectedAccount(detail);
    const accountSignal = (Array.isArray(intelligence.accounts) ? intelligence.accounts : []).find(
      item => String(item?.account_uid || "") === String(account?.account_uid || ""),
    );
    setText("creator-intelligence-ai-tags", (intelligence.ai_tags || []).join(" · ") || "--");
    setText("creator-intelligence-categories", (intelligence.content_categories || []).join(" · ") || "--");
    renderDefinitionList(element("creator-intelligence-audience"), [
      ["国家", intelligence.audience_signals?.country],
      ["语言", intelligence.audience_signals?.language],
      ["平台", (intelligence.audience_signals?.platforms || []).join(" · ")],
    ]);
    setText(
      "creator-intelligence-content-signals",
      (intelligence.content_signals || []).map(item => item?.value).filter(Boolean).join(" · ") || "--",
    );
    setText("creator-intelligence-follower-band", accountSignal?.follower_band || intelligence.follower_band || "unavailable");
    setText("creator-intelligence-engagement-band", intelligence.engagement_band || "unavailable");
    setText("creator-intelligence-price-band", intelligence.price_band || "unavailable");
    setText("creator-intelligence-confidence", intelligence.confidence || "insufficient");
  }

  function renderAISummary(data) {
    intelligence = data?.intelligence || null;
    const profile = data?.profile || {};
    const performance = data?.performance || {};
    const limitations = Array.isArray(data?.limitations) ? data.limitations : [];
    const observations = Array.isArray(data?.observations) ? data.observations : [];
    const dataStatus = data?.data_status || "insufficient";
    const freshnessStatus = data?.freshness?.status || "unknown";
    const content = element("creator-ai-summary-content");
    if (content) content.hidden = false;
    renderDefinitionList(element("creator-ai-summary-profile"), [
      ["达人名称", profile.name],
      ["平台", profile.platform],
      ["粉丝数", profile.followers],
      ["国家/地区", profile.country],
      ["语言", profile.language],
      ["内容类型", profile.content_category],
    ]);
    renderDefinitionList(element("creator-ai-summary-performance"), [
      ["平均播放", summaryMetric(performance.average_views)],
      ["中位播放", summaryMetric(performance.median_views)],
      ["视频数量", summaryMetric(performance.video_count)],
      ["Creator Score", summaryMetric(performance.creator_score)],
      ["稳定性", summaryMetric(performance.stability)],
    ]);
    const statusLabel = { sufficient: "数据较完整", partial: "部分数据可用", insufficient: "数据不足" }[dataStatus] || "数据不足";
    setText("creator-ai-summary-data-status", statusLabel);
    setText("creator-ai-summary-freshness", summaryFreshnessLabel(freshnessStatus));
    renderList("creator-ai-summary-observations", observations, "暂无可展示的事实摘要。");
    renderList(
      "creator-ai-summary-limitations",
      limitations.map(item => item?.message).filter(Boolean),
      "当前未发现额外数据限制。",
    );
    renderIntelligence(intelligence);
    if (dataStatus === "insufficient") {
      setText("creator-ai-summary-status", "数据不足。当前缺少可用于表现分析的数据。");
    } else if (freshnessStatus === "stale") {
      setText("creator-ai-summary-status", "数据更新时间较早，请在决策前重新采集");
    } else {
      setText("creator-ai-summary-status", dataStatus === "partial" ? "摘要已生成，部分数据仍待补充。" : "摘要已生成。");
    }
    const button = element("creator-ai-summary-generate");
    if (button) button.textContent = "重新生成";
  }

  async function generateAISummary() {
    const currentLifecycle = lifecycleId;
    const button = element("creator-ai-summary-generate");
    summaryController?.abort();
    summaryController = pageContext.resources.createAbortController();
    if (button) button.disabled = true;
    setText("creator-ai-summary-status", "正在生成本地摘要...");
    try {
      const data = await pageContext.api.get(
        `/api/creator-library/${encodeURIComponent(creatorId)}/ai-summary`,
        { signal: summaryController.signal },
      );
      if (!pageContext || currentLifecycle !== lifecycleId) return;
      renderAISummary(data);
    } catch (error) {
      if (error?.name !== "AbortError" && pageContext && currentLifecycle === lifecycleId) {
        setText("creator-ai-summary-status", "摘要暂时无法生成，原始达人资料仍可正常查看");
      }
    } finally {
      if (button && pageContext && currentLifecycle === lifecycleId) button.disabled = false;
    }
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
    const account = selectedAccount(data);
    const snapshot = accountSnapshot(data, account);
    const hasAccount = Boolean(account);
    const accountFollowers = hasAccount
      ? (account.followers || snapshot?.followers || "")
      : (record.followers || creator.followers || "");
    const accountAverageViews = hasAccount ? snapshot?.average_views : videoAnalysis.average_views;
    const accountMedianViews = hasAccount ? snapshot?.median_views : videoAnalysis.median_views;
    const accountAnalyzedAt = snapshot?.captured_at || account?.last_scrape_time || "";
    const accountUpdatedAt = hasAccount
      ? (account?.updated_at || account?.last_scrape_time || "")
      : record.data_updated_at;
    const accountSource = hasAccount
      ? (account?.data_source || snapshot?.source || "--")
      : (record.source || "--");
    const selectedIsLegacyPrimary = hasAccount
      && String(account?.platform || "").trim().toLowerCase()
        === String(record.platform || "").trim().toLowerCase();
    const displayedPlatform = hasAccount ? account?.platform : creator.platform;
    const displayedProfileUrl = hasAccount
      ? (account?.profile_url || (selectedIsLegacyPrimary ? record.profile_url : ""))
      : creator.profile_url;
    const displayedAnalyzedAt = hasAccount
      ? accountAnalyzedAt
      : (record.last_analysis_time || record.analysis_time);

    renderAccountSwitcher(data);

    setText(
      "creator-library-detail-summary",
      `${record.creator_name || "未命名达人"} · ${displayedPlatform || "--"} · ${displayedProfileUrl || "--"}`,
    );
    setText("creator-library-detail-level", record.insight_level || "insufficient");
    setText(
      "creator-library-data-meta",
      `数据更新时间：${formatTime(accountUpdatedAt)} · 来源：${accountSource} · 最近分析时间：${formatTime(displayedAnalyzedAt)}`,
    );
    setText(
      "creator-library-freshness",
      formatFreshness(hasAccount && accountAnalyzedAt ? accountFreshness(accountAnalyzedAt) : trend.freshness),
    );
    renderDefinitionList(element("creator-library-basic"), [
      ["达人名称", record.creator_name || creator.creator_name],
      ["平台", displayedPlatform],
      ["账号", account ? accountIdentity(account) : ""],
      ["主页链接", displayedProfileUrl],
      ["粉丝数", accountFollowers],
      ["国家/地区", record.country],
      ["语言", record.language],
      ["内容类型", record.content_category || analysis.content_category],
      ["简介", record.bio || creator.bio],
    ]);
    renderDefinitionList(element("creator-library-video-metrics"), [
      ["样本数量", formatMetric(videoAnalysis.sample_size)],
      ["平均播放", formatMetric(accountAverageViews)],
      ["中位播放", formatMetric(accountMedianViews)],
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
    renderHistoricalPerformance();
    const archiveButton = element("creator-library-detail-archive");
    if (archiveButton) archiveButton.textContent = archived ? "恢复达人" : "归档达人";
    ["creator-library-detail-edit", "creator-library-detail-add-campaign", "creator-library-detail-similar", "creator-library-detail-task"].forEach(id => {
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
    resetAISummary();
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
    const historyRequest = pageContext.api.get(
      `/api/creator-library/${encodeURIComponent(creatorId)}/historical-performance`,
      { signal: detailController.signal },
    );
    const [detailResult, campaignsResult, historyResult] = await Promise.allSettled([
      detailRequest, campaignsRequest, historyRequest,
    ]);
    const requestedCreatorId = String(pageContext?.params?.creatorId || "").trim();
    if (!pageContext || currentLifecycle !== lifecycleId || creatorId !== requestedCreatorId) return;
    if (detailResult.status === "rejected") throw detailResult.reason;
    const data = detailResult.value;
    detail = data;
    historicalPerformance = historyResult.status === "fulfilled" ? historyResult.value : null;
    resolveDefaultAccount(data);
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

  function renderEditableAccounts() {
    const list = element("creator-edit-accounts-list");
    if (!list) return;
    const accounts = Array.isArray(detail?.accounts) ? detail.accounts : [];
    if (!accounts.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "暂无已关联的平台账号。";
      list.replaceChildren(empty);
      return;
    }
    list.replaceChildren(...accounts.map(account => {
      const row = document.createElement("div");
      row.className = "creator-edit-account-row";
      const identity = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `${account?.platform || "未知平台"} · ${accountIdentity(account)}`;
      const open = document.createElement("a");
      const profileUrl = String(account?.profile_url || "");
      open.href = profileUrl || "#";
      open.target = "_blank";
      open.rel = "noopener noreferrer";
      open.textContent = profileUrl.replace(/^https?:\/\//i, "") || "主页链接不可用";
      identity.append(title, open);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "soft-btn compact-btn";
      remove.dataset.creatorEditAccountUid = String(account?.account_uid || "");
      remove.textContent = "移除关联";
      row.append(identity, remove);
      return row;
    }));
  }

  async function openEditModal() {
    if (!detail?.record || detail.record.archived_at) return;
    const record = detail.record;
    const analysis = detail.analysis || {};
    const creator = analysis.creator || {};
    setValue("creator-edit-name", record.creator_name || creator.creator_name);
    setValue("creator-edit-country", record.country || creator.country);
    setValue("creator-edit-language", record.language || creator.language);
    setValue("creator-edit-whatsapp", record.whatsapp || creator.whatsapp);
    setValue("creator-edit-content-category", record.content_category || analysis.content_category);
    setValue("creator-edit-bio", record.bio || creator.bio);
    renderAgencyOptions([], record.agency_id);
    renderEditableAccounts();
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
          country: valueOf("creator-edit-country").trim(),
          language: valueOf("creator-edit-language").trim(),
          whatsapp: valueOf("creator-edit-whatsapp").trim(),
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

  async function addCreatorAccount() {
    const input = element("creator-edit-account-url");
    const profileUrl = String(input?.value || "").trim();
    if (!profileUrl) return showEditMessage("请输入主页链接。");
    showEditMessage("");
    try {
      const result = await pageContext.api.post(
        `/api/creator-library/${encodeURIComponent(creatorId)}/accounts`,
        { profile_url: profileUrl }, { signal: pageContext.resources.signal },
      );
      if (input) input.value = "";
      await loadDetail();
      renderEditableAccounts();
      pageContext.ui.showSaved(result?.created === false ? "该账号已经属于当前达人。" : "平台账号已关联。");
    } catch (error) {
      const data = error?.responseData || {};
      if (data?.conflict === "ACCOUNT_OWNED_BY_OTHER_CREATOR") {
        const owner = data.owner || {};
        showEditMessage(`该账号已属于【${owner.creator_name || owner.creator_id || "另一位达人"}】。`);
        const message = element("creator-edit-message");
        const view = document.createElement("button");
        view.type = "button";
        view.className = "soft-btn compact-btn";
        view.textContent = "查看现有达人";
        view.addEventListener("click", () => pageContext.navigate("creator-library-detail", { creatorId: owner.creator_id }));
        const merge = document.createElement("button");
        merge.type = "button";
        merge.className = "soft-btn compact-btn";
        merge.textContent = "合并达人";
        merge.addEventListener("click", () => mergeModal.open(detail.record, {
          secondaryCreatorId: owner.creator_id,
          onMerged: loadDetail,
        }).catch(showError));
        message?.append(" ", view, " ", merge);
      } else if (error?.name !== "AbortError") showEditMessage(error.message || "账号关联失败。");
    }
  }

  async function removeCreatorAccount(event) {
    const button = event.target.closest("[data-creator-edit-account-uid]");
    const accountUid = String(button?.dataset?.creatorEditAccountUid || "");
    if (!accountUid || !global.confirm("移除仅允许无历史引用的账号；已有合作或表现历史的账号会被安全保留。")) return;
    try {
      await pageContext.api.delete(
        `/api/creator-library/${encodeURIComponent(creatorId)}/accounts/${encodeURIComponent(accountUid)}`,
        { signal: pageContext.resources.signal },
      );
      await loadDetail();
      renderEditableAccounts();
      pageContext.ui.showSaved("平台账号已移除。");
    } catch (error) {
      if (error?.name !== "AbortError") showEditMessage(error.message || "该账号无法移除。");
    }
  }

  function clearSimilarCandidates() {
    similarController?.abort();
    similarController = null;
    const card = element("creator-library-similar-card");
    if (card) card.hidden = true;
    element("creator-library-similar-results")?.replaceChildren();
    setText(
      "creator-library-similar-status",
      "仅基于本地达人库的结构化证据评分；缺失维度不计零分。",
    );
  }

  function renderSimilarCandidates(result) {
    const container = element("creator-library-similar-results");
    if (!container) return;
    const candidates = Array.isArray(result?.candidates) ? result.candidates : [];
    if (!candidates.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "暂无具备可用匹配证据的本地达人。";
      container.replaceChildren(empty);
      return;
    }
    container.replaceChildren(...candidates.map(candidate => {
      const item = document.createElement("div");
      item.className = "creator-library-similar-item";
      const identity = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = String(candidate?.creator_name || "未命名达人");
      const summary = document.createElement("span");
      const score = candidate?.base_similarity_score;
      summary.textContent = typeof score === "number" && Number.isFinite(score)
        ? `相似度 ${score.toFixed(2)}% · 可用证据权重 ${candidate.available_nominal_weight}/100`
        : "相似度 -- · 可比证据不足";
      identity.append(name, summary);
      const reasons = document.createElement("ul");
      const explanations = Array.isArray(candidate?.why_recommended) ? candidate.why_recommended : [];
      explanations.forEach(reason => {
        const line = document.createElement("li");
        line.textContent = String(reason?.text || "");
        reasons.appendChild(line);
      });
      identity.appendChild(reasons);
      const history = candidate.historical_performance_evidence;
      if (history) {
        const evidence = document.createElement("small");
        evidence.textContent = `历史证据（不改变评分）：${history.cooperation_count} 次合作 · ${history.publication_count} 条发布 · 平均播放 ${formatMetric(history.average_latest_views)} · 平均 ER ${history.average_latest_er == null ? "--" : `${formatMetric(history.average_latest_er)}%`}`;
        identity.appendChild(evidence);
      }
      const labels = { tag: "标签", content: "内容", followers: "粉丝", price: "报价",
        engagement: "互动率", country_language: "国家/语言", platform: "平台" };
      const missing = Array.isArray(candidate?.unavailable_dimensions) ? candidate.unavailable_dimensions : [];
      const unavailable = document.createElement("small");
      unavailable.textContent = missing.length
        ? `未纳入评分：${missing.map(key => labels[key] || key).join("、")}` : "所有维度均有可比证据";
      identity.appendChild(unavailable);
      const geoMissing = candidate?.dimensions?.country_language?.evidence?.unavailable || [];
      if (geoMissing.length) {
        const subMissing = document.createElement("small");
        subMissing.textContent = `国家/语言缺项：${geoMissing.map(key => key === "country" ? "国家" : "语言").join("、")}`;
        identity.appendChild(subMissing);
      }
      const ai = result?.ai?.explanations?.find(row => row.creator_id === candidate.creator_id);
      if (ai?.text) {
        const aiText = document.createElement("p");
        aiText.textContent = `AI 补充说明（不改变评分）：${ai.text}`;
        identity.appendChild(aiText);
      }
      const action = document.createElement("button");
      action.type = "button";
      action.className = "soft-btn";
      action.dataset.similarCreatorId = String(candidate?.creator_id || "");
      action.textContent = "查看达人";
      item.append(identity, action);
      return item;
    }));
  }

  async function loadSimilarCandidates() {
    if (!creatorId || !pageContext?.api || detail?.record?.archived_at) return;
    const currentLifecycle = lifecycleId;
    const card = element("creator-library-similar-card");
    if (card) card.hidden = false;
    setText("creator-library-similar-status", "正在查找本地达人库候选...");
    similarController?.abort();
    similarController = pageContext.resources.createAbortController();
    const requestController = similarController;
    element("creator-library-similar-results")?.replaceChildren();
    try {
      const result = await pageContext.api.get(
        `/api/creator-library/${encodeURIComponent(creatorId)}/similar`,
        { signal: similarController.signal },
      );
      if (!pageContext || currentLifecycle !== lifecycleId || requestController !== similarController) return;
      renderSimilarCandidates(result);
      setText(
        "creator-library-similar-status",
        `本地候选 ${Number(result?.total || 0)} 个，展示 ${result?.candidates?.length || 0} 个；按确定性评分排序，缺失证据不计零分。`,
      );
    } catch (error) {
      if (error?.name === "AbortError" || !pageContext || currentLifecycle !== lifecycleId || requestController !== similarController) return;
      renderSimilarCandidates({ candidates: [] });
      setText("creator-library-similar-status", error?.message || "相似达人搜索失败。");
    }
  }

  function handleSimilarCreatorAction(event) {
    const button = event.target.closest("[data-similar-creator-id]");
    const candidateId = String(button?.dataset?.similarCreatorId || "").trim();
    if (candidateId) pageContext.navigate("creator-library-detail", { creatorId: candidateId }).catch(showError);
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
      historicalPerformance = null;
      creatorCampaigns = [];
      clearSimilarCandidates();
      campaignModal = global.KOLConnectCreatorCampaignModal.create(context);
      mergeModal = global.KOLConnectCreatorMergeModal.create(context);
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
      mergeModal.bind();
      document.querySelectorAll(".detail-tab").forEach(button => {
        pageContext.resources.listen(button, "click", () => setDetailTab(button.dataset.detailTab));
      });
      listen("creator-library-detail-back", "click", () => pageContext.navigate("creator-library"));
      listen("creator-library-detail-edit", "click", () => openEditModal().catch(showError));
      listen("creator-library-detail-archive", "click", () => changeArchiveState().catch(showError));
      listen("creator-library-detail-add-campaign", "click", () => openCampaignModal().catch(showError));
      listen("creator-library-detail-similar", "click", () => loadSimilarCandidates());
      listen("creator-library-detail-task", "click", () => openCollaborationTask().catch(showError));
      listen("creator-account-options", "click", handleAccountSwitch);
      listen("creator-ai-summary-generate", "click", () => generateAISummary().catch(showError));
      listen("creator-campaigns-body", "click", handleCampaignAction);
      listen("creator-library-similar-results", "click", handleSimilarCreatorAction);
      listen("creator-edit-modal-close", "click", closeEditModal);
      listen("creator-edit-cancel", "click", closeEditModal);
      listen("creator-edit-form", "submit", saveCreatorProfile);
      listen("creator-edit-account-add", "click", () => addCreatorAccount());
      listen("creator-edit-accounts-list", "click", removeCreatorAccount);
    },

    unbind() {
      lifecycleId += 1;
      campaignModal?.destroy();
      mergeModal?.destroy();
      pageContext?.resources.cleanup();
      pageContext = null;
      detailController = null;
      campaignsController = null;
      editController = null;
      summaryController?.abort();
      summaryController = null;
      similarController?.abort();
      similarController = null;
      campaignModal = null;
      mergeModal = null;
      creatorId = "";
      detail = null;
      historicalPerformance = null;
      creatorCampaigns = [];
      selectedAccountKey = "";
      closeEditModal();
    },
  };

  global.KOLConnectPages.registerPage("creator-library-detail", creatorLibraryDetailPage);
})(window);
