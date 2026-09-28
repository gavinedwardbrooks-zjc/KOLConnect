(function registerCreatorLibraryDetailPage(global) {
  "use strict";

  const DETAIL_TABS = new Set(["overview", "content", "history"]);

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

  function t(key, values) {
    return pageContext?.ui?.t?.(key, values) || global.KOLConnectI18n?.t(key, values) || key;
  }

  function showError(error) {
    if (error?.name !== "AbortError") pageContext?.ui.showError(error);
  }

  function formatMetric(value) {
    if (value === null || value === undefined || value === "") return "--";
    const number = Number(value);
    const locale = global.KOLConnectI18n?.getLocale?.() === "en" ? "en-US" : "zh-CN";
    return Number.isFinite(number) ? number.toLocaleString(locale) : String(value);
  }

  function formatTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    const locale = global.KOLConnectI18n?.getLocale?.() === "en" ? "en-US" : "zh-CN";
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(locale);
  }

  function formatFreshness(freshness) {
    if (!freshness || freshness.status === "unknown") return t("creatorAnalysisTimeUnknown");
    const days = Number(freshness.days || 0);
    if (freshness.status === "fresh") return t("creatorFreshnessFresh", { days });
    if (freshness.status === "update_recommended") return t("creatorFreshnessUpdate", { days });
    return t("creatorFreshnessStale", { days });
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
      return String(account?.profile_url || account?.account_uid || t("creatorAccount"));
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
    setText("creator-account-count", t("creatorAccountCount", { count: accounts.length }));
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
      platform.textContent = String(account?.platform || t("creatorUnknownPlatform"));
      const identity = document.createElement("strong");
      identity.textContent = accountIdentity(account);
      const followers = document.createElement("small");
      followers.textContent = t("creatorFollowers", { count: formatMetric(account?.followers) });
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
    appendHistoryStat(summary, t("creatorHistoryCooperations"), formatMetric(data?.cooperation_count), t("creatorHistoryCooperationsHint"));
    appendHistoryStat(summary, t("creatorHistoryCampaigns"), formatMetric(data?.historical_campaign_count), t("creatorHistoryCampaignsHint"));
    appendHistoryStat(summary, t("creatorHistoryAverageViews"), formatMetric(data?.average_latest_views), t("creatorHistoryCoverage", { valid: data?.valid_publication_views_count || 0, total: data?.total_historical_publications || 0 }));
    appendHistoryStat(summary, t("creatorHistoryAverageEngagement"), data?.average_latest_er == null ? "--" : `${formatMetric(data.average_latest_er)}%`, t("creatorHistoryCoverage", { valid: data?.valid_publication_er_count || 0, total: data?.total_historical_publications || 0 }));

    const moneyTitle = document.createElement("h3");
    moneyTitle.textContent = t("creatorHistoryMoneyEfficiency");
    const moneyText = document.createElement("p");
    moneyText.textContent = t("creatorHistoryMoneySummary", { cost: formatCurrencyGroups(data?.total_cost_by_currency), quote: formatCurrencyGroups(data?.total_quote_by_currency), unknownCost: data?.unknown_currency_records?.cost || 0, unknownQuote: data?.unknown_currency_records?.quote || 0 });
    money.append(moneyTitle, moneyText);
    Object.entries(data?.efficiency_by_currency || {}).forEach(([currency, values]) => {
      const line = document.createElement("p");
      line.textContent = t("creatorHistoryEfficiency", { currency, cpv: formatMetric(values?.cpv), cpe: formatMetric(values?.cpe) });
      money.appendChild(line);
    });
    const roi = document.createElement("p");
    roi.textContent = t("creatorHistoryRoiUnavailable");
    money.appendChild(roi);

    const campaignTitle = document.createElement("h3");
    campaignTitle.textContent = t("creatorHistoryCampaigns");
    campaigns.appendChild(campaignTitle);
    const history = Array.isArray(data?.historical_campaigns) ? data.historical_campaigns : [];
    if (!history.length) {
      const unavailable = document.createElement("p");
      unavailable.textContent = t("creatorHistoryNoCampaigns");
      campaigns.appendChild(unavailable);
    } else {
      const list = document.createElement("ul");
      history.forEach(item => {
        const entry = document.createElement("li");
        entry.textContent = `${item.campaign_name || item.campaign_id} · ${item.campaign_status || "--"} · ${item.start_date || t("creatorHistoryDateUnknown")}`;
        list.appendChild(entry);
      });
      campaigns.appendChild(list);
    }
  }

  function summaryMetric(measurement) {
    if (!measurement || measurement.value === null || measurement.value === undefined || measurement.value === "") return "--";
    const source = measurement.source === "creator_snapshot" ? t("creatorSummarySourceSnapshot") : t("creatorSummarySourceInsights");
    const measuredAt = measurement.measured_at ? ` · ${formatTime(measurement.measured_at)}` : ` · ${t("creatorSummaryTimeUnknown")}`;
    return `${formatMetric(measurement.value)} · ${source}${measuredAt}`;
  }

  function summaryFreshnessLabel(status) {
    return {
      fresh: t("creatorFreshnessRecent"),
      update_recommended: t("creatorFreshnessRecommended"),
      stale: t("creatorFreshnessStaleDecision"),
      unknown: t("creatorFreshnessUnknown"),
    }[status] || t("creatorFreshnessUnknown");
  }

  function resetAISummary() {
    summaryController?.abort();
    summaryController = null;
    intelligence = null;
    const button = element("creator-ai-summary-generate");
    if (button) {
      button.disabled = false;
      button.textContent = t("creatorSummaryGenerate");
    }
    setText("creator-ai-summary-status", t("creatorSummaryPrompt"));
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
      [t("creatorFieldCountry"), intelligence.audience_signals?.country],
      [t("creatorFieldLanguage"), intelligence.audience_signals?.language],
      [t("creatorFieldPlatform"), (intelligence.audience_signals?.platforms || []).join(" · ")],
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
      [t("creatorFieldName"), profile.name],
      [t("creatorFieldPlatform"), profile.platform],
      [t("creatorFieldFollowers"), profile.followers],
      [t("creatorFieldCountry"), profile.country],
      [t("creatorFieldLanguage"), profile.language],
      [t("creatorFieldContentType"), profile.content_category],
    ]);
    renderDefinitionList(element("creator-ai-summary-performance"), [
      [t("creatorFieldAverageViews"), summaryMetric(performance.average_views)],
      [t("creatorFieldMedianViews"), summaryMetric(performance.median_views)],
      [t("creatorFieldVideoCount"), summaryMetric(performance.video_count)],
      [t("creatorFieldScore"), summaryMetric(performance.creator_score)],
      [t("creatorFieldStability"), summaryMetric(performance.stability)],
    ]);
    const statusLabel = { sufficient: t("creatorDataSufficient"), partial: t("creatorDataPartial"), insufficient: t("creatorDataInsufficient") }[dataStatus] || t("creatorDataInsufficient");
    setText("creator-ai-summary-data-status", statusLabel);
    setText("creator-ai-summary-freshness", summaryFreshnessLabel(freshnessStatus));
    renderList("creator-ai-summary-observations", observations, t("creatorSummaryNoFacts"));
    renderList(
      "creator-ai-summary-limitations",
      limitations.map(item => item?.message).filter(Boolean),
      t("creatorSummaryNoLimits"),
    );
    renderIntelligence(intelligence);
    if (dataStatus === "insufficient") {
      setText("creator-ai-summary-status", t("creatorSummaryInsufficient"));
    } else if (freshnessStatus === "stale") {
      setText("creator-ai-summary-status", t("creatorFreshnessStaleDecision"));
    } else {
      setText("creator-ai-summary-status", dataStatus === "partial" ? t("creatorSummaryPartial") : t("creatorSummaryComplete"));
    }
    const button = element("creator-ai-summary-generate");
    if (button) button.textContent = t("creatorSummaryRegenerate");
  }

  async function generateAISummary() {
    const currentLifecycle = lifecycleId;
    const button = element("creator-ai-summary-generate");
    summaryController?.abort();
    summaryController = pageContext.resources.createAbortController();
    if (button) button.disabled = true;
    setText("creator-ai-summary-status", t("creatorSummaryGenerating"));
    try {
      const data = await pageContext.api.get(
        `/api/creator-library/${encodeURIComponent(creatorId)}/ai-summary`,
        { signal: summaryController.signal },
      );
      if (!pageContext || currentLifecycle !== lifecycleId) return;
      renderAISummary(data);
    } catch (error) {
      if (error?.name !== "AbortError" && pageContext && currentLifecycle === lifecycleId) {
        setText("creator-ai-summary-status", t("creatorSummaryUnavailable"));
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
      link.textContent = video.video_url || video.video_key || t("creatorVideo");
      const metric = document.createElement("span");
      metric.textContent = t("creatorVideoMetrics", { views: video.views || "--", likes: video.likes || "--", comments: video.comments || "--" });
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
    errorMessage.textContent = error ? (error.message || t("creatorCampaignLoadFailed")) : "";
    empty.hidden = creatorCampaigns.length > 0 || Boolean(error);
    creatorCampaigns.forEach(campaign => {
      const row = document.createElement("tr");
      [
        campaign.name || t("dashboardUnnamedCampaign"),
        campaign.product_name || "--",
        campaign.status || "--",
        campaign.platform || "--",
        campaign.start_date && campaign.end_date ? t("creatorDateRange", { start: campaign.start_date, end: campaign.end_date }) : (campaign.start_date || campaign.end_date || "--"),
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
      action.textContent = t("creatorCampaignView");
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
    const displayName = String(record.creator_name || creator.creator_name || "").trim()
      || (account ? accountIdentity(account) : t("dashboardUnnamedCreator"));

    renderAccountSwitcher(data);

    setText(
      "creator-library-detail-summary",
      `${displayName} · ${displayedPlatform || "--"} · ${displayedProfileUrl || "--"}`,
    );
    setText("creator-library-detail-level", record.insight_level || "insufficient");
    setText(
      "creator-library-data-meta",
      t("creatorDataMeta", { updatedAt: formatTime(accountUpdatedAt), source: accountSource, analyzedAt: formatTime(displayedAnalyzedAt) }),
    );
    setText(
      "creator-library-freshness",
      formatFreshness(hasAccount && accountAnalyzedAt ? accountFreshness(accountAnalyzedAt) : trend.freshness),
    );
    renderDefinitionList(element("creator-library-basic"), [
      [t("creatorFieldName"), displayName],
      [t("creatorFieldPlatform"), displayedPlatform],
      [t("creatorAccount"), account ? accountIdentity(account) : ""],
      [t("creatorFieldProfileUrl"), displayedProfileUrl],
      [t("creatorFieldEmail"), account?.account_email || record.account_email || ""],
      [t("creatorFieldFollowers"), accountFollowers],
      [t("creatorFieldCountry"), record.country],
      [t("creatorFieldLanguage"), record.language],
      [t("creatorFieldContentType"), record.content_category || analysis.content_category],
      [t("creatorFieldBio"), record.bio || creator.bio],
    ]);
    renderDefinitionList(element("creator-library-video-metrics"), [
      [t("creatorFieldSampleSize"), formatMetric(videoAnalysis.sample_size)],
      [t("creatorFieldAverageViews"), formatMetric(accountAverageViews)],
      [t("creatorFieldMedianViews"), formatMetric(accountMedianViews)],
      [t("creatorFieldMaxViews"), formatMetric(videoAnalysis.max_views)],
      [t("creatorFieldMinViews"), formatMetric(videoAnalysis.min_views)],
      [t("creatorFieldViewStability"), formatMetric(videoAnalysis.view_stability)],
      [t("creatorFieldViewCoverage"), `${Math.round(Number(videoAnalysis.view_coverage || 0) * 100)}%`],
    ]);
    setText("creator-library-recommendation", insight.recommendation || t("creatorManualReview"));
    renderList("creator-library-strengths", insight.strengths, t("creatorNoStrengths"));
    renderList("creator-library-risks", insight.risks, t("creatorNoRisks"));
    renderSnapshots(data);
    renderVideos(analysis);
    renderHistoricalPerformance();
    const archiveButton = element("creator-library-detail-archive");
    if (archiveButton) archiveButton.textContent = archived ? t("creatorRestore") : t("creatorArchive");
    ["creator-library-detail-edit", "creator-library-detail-add-campaign", "creator-library-detail-similar", "creator-library-detail-task"].forEach(id => {
      const button = element(id);
      if (button) button.disabled = archived;
    });
    setDetailTab(pageContext.state.creatorLibrary.detailTab);
  }

  function clearRenderedDetail(message = t("creatorDataLoading")) {
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
    if (!task?.id) throw new Error(t("creatorReviewTaskMissing"));
    context.state.currentTaskId = task.id;
    context.state.currentTask = task;
    context.state.review.taskId = task.id;
    global.localStorage.setItem("kolconnect.currentTaskId", task.id);
    await context.navigate("review");
    context.ui.showSaved(data.message || t("creatorReviewTaskOpened"));
  }

  function listen(id, type, listener) {
    const target = element(id);
    if (target) pageContext.resources.listen(target, type, listener);
  }

  function openCampaignModal() {
    if (!detail?.record || detail.record.archived_at) throw new Error(t("creatorArchivedCampaignBlocked"));
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
    emptyOption.textContent = t("creatorNoAgency");
    select.appendChild(emptyOption);
    agencies.forEach(agency => {
      const option = document.createElement("option");
      option.value = String(agency.agency_id || "");
      option.textContent = String(agency.name || agency.agency_id || t("creatorUnnamedAgency"));
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
      empty.textContent = t("creatorNoAccounts");
      list.replaceChildren(empty);
      return;
    }
    list.replaceChildren(...accounts.map(account => {
      const row = document.createElement("div");
      row.className = "creator-edit-account-row";
      const identity = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `${account?.platform || t("creatorUnknownPlatform")} · ${accountIdentity(account)}`;
      const open = document.createElement("a");
      const profileUrl = String(account?.profile_url || "");
      open.href = profileUrl || "#";
      open.target = "_blank";
      open.rel = "noopener noreferrer";
      open.textContent = profileUrl.replace(/^https?:\/\//i, "") || t("creatorProfileUrlUnavailable");
      identity.append(title, open);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "soft-btn compact-btn";
      remove.dataset.creatorEditAccountUid = String(account?.account_uid || "");
      remove.textContent = t("creatorUnlinkAccount");
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
      if (error?.name !== "AbortError") showEditMessage(error.message || t("creatorAgencyLoadFailed"));
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
      pageContext.ui.showSaved(t("creatorProfileSaved"));
    } catch (error) {
      if (error?.name !== "AbortError") showEditMessage(error.message || t("creatorProfileSaveFailed"));
    } finally {
      if (saveButton) saveButton.disabled = false;
    }
  }

  async function changeArchiveState() {
    if (!detail?.record) return;
    const archived = Boolean(detail.record.archived_at);
    const message = archived
      ? t("creatorRestoreConfirm")
      : t("creatorArchiveConfirm");
    if (!global.confirm(message)) return;
    await pageContext.api.patch(
      `/api/creator-library/${encodeURIComponent(creatorId)}`,
      { archived_at: archived ? null : new Date().toISOString() },
      { signal: pageContext.resources.signal },
    );
    await loadDetail();
    pageContext.ui.showSaved(archived ? t("creatorRestored") : t("creatorArchived"));
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
    if (!profileUrl) return showEditMessage(t("creatorProfileUrlRequired"));
    showEditMessage("");
    try {
      const result = await pageContext.api.post(
        `/api/creator-library/${encodeURIComponent(creatorId)}/accounts`,
        { profile_url: profileUrl }, { signal: pageContext.resources.signal },
      );
      if (input) input.value = "";
      await loadDetail();
      renderEditableAccounts();
      pageContext.ui.showSaved(result?.created === false ? t("creatorAccountAlreadyLinked") : t("creatorAccountLinked"));
    } catch (error) {
      const data = error?.responseData || {};
      if (data?.conflict === "ACCOUNT_OWNED_BY_OTHER_CREATOR") {
        const owner = data.owner || {};
        showEditMessage(t("creatorAccountOwnedBy", { creator: owner.creator_name || owner.creator_id || t("creatorAnotherCreator") }));
        const message = element("creator-edit-message");
        const view = document.createElement("button");
        view.type = "button";
        view.className = "soft-btn compact-btn";
        view.textContent = t("creatorViewExistingCreator");
        view.addEventListener("click", () => pageContext.navigate("creator-library-detail", { creatorId: owner.creator_id }));
        const merge = document.createElement("button");
        merge.type = "button";
        merge.className = "soft-btn compact-btn";
        merge.textContent = t("creatorMergeCreator");
        merge.addEventListener("click", () => mergeModal.open(detail.record, {
          secondaryCreatorId: owner.creator_id,
          onMerged: loadDetail,
        }).catch(showError));
        message?.append(" ", view, " ", merge);
      } else if (error?.name !== "AbortError") showEditMessage(error.message || t("creatorAccountLinkFailed"));
    }
  }

  async function removeCreatorAccount(event) {
    const button = event.target.closest("[data-creator-edit-account-uid]");
    const accountUid = String(button?.dataset?.creatorEditAccountUid || "");
    if (!accountUid || !global.confirm(t("creatorAccountRemoveConfirm"))) return;
    try {
      await pageContext.api.delete(
        `/api/creator-library/${encodeURIComponent(creatorId)}/accounts/${encodeURIComponent(accountUid)}`,
        { signal: pageContext.resources.signal },
      );
      await loadDetail();
      renderEditableAccounts();
      pageContext.ui.showSaved(t("creatorAccountRemoved"));
    } catch (error) {
      if (error?.name !== "AbortError") showEditMessage(error.message || t("creatorAccountRemoveBlocked"));
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
      t("creatorSimilarityMethod"),
    );
  }

  function renderSimilarCandidates(result) {
    const container = element("creator-library-similar-results");
    if (!container) return;
    const candidates = Array.isArray(result?.candidates) ? result.candidates : [];
    if (!candidates.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = t("creatorNoSimilarCandidates");
      container.replaceChildren(empty);
      return;
    }
    container.replaceChildren(...candidates.map(candidate => {
      const item = document.createElement("div");
      item.className = "creator-library-similar-item";
      const identity = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = String(candidate?.creator_name || t("dashboardUnnamedCreator"));
      const summary = document.createElement("span");
      const score = candidate?.base_similarity_score;
      summary.textContent = typeof score === "number" && Number.isFinite(score)
        ? t("creatorSimilarityScore", { score: score.toFixed(2), weight: candidate.available_nominal_weight })
        : t("creatorSimilarityUnavailable");
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
        evidence.textContent = t("creatorHistoricalEvidence", { cooperations: history.cooperation_count, publications: history.publication_count, views: formatMetric(history.average_latest_views), er: history.average_latest_er == null ? "--" : `${formatMetric(history.average_latest_er)}%` });
        identity.appendChild(evidence);
      }
      const labels = { tag: t("creatorDimensionTag"), content: t("creatorDimensionContent"), followers: t("creatorDimensionFollowers"), price: t("creatorDimensionPrice"),
        engagement: t("creatorDimensionEngagement"), country_language: t("creatorDimensionCountryLanguage"), platform: t("creatorDimensionPlatform") };
      const missing = Array.isArray(candidate?.unavailable_dimensions) ? candidate.unavailable_dimensions : [];
      const unavailable = document.createElement("small");
      unavailable.textContent = missing.length
        ? t("creatorSimilarityExcluded", { dimensions: missing.map(key => labels[key] || key).join("、") }) : t("creatorSimilarityAllComparable");
      identity.appendChild(unavailable);
      const geoMissing = candidate?.dimensions?.country_language?.evidence?.unavailable || [];
      if (geoMissing.length) {
        const subMissing = document.createElement("small");
        subMissing.textContent = t("creatorCountryLanguageMissing", { dimensions: geoMissing.map(key => key === "country" ? t("creatorFieldCountry") : t("creatorFieldLanguage")).join("、") });
        identity.appendChild(subMissing);
      }
      const ai = result?.ai?.explanations?.find(row => row.creator_id === candidate.creator_id);
      if (ai?.text) {
        const aiText = document.createElement("p");
        aiText.textContent = t("creatorAiSupplement", { text: ai.text });
        identity.appendChild(aiText);
      }
      const action = document.createElement("button");
      action.type = "button";
      action.className = "soft-btn";
      action.dataset.similarCreatorId = String(candidate?.creator_id || "");
      action.textContent = t("dashboardViewCreator");
      item.append(identity, action);
      return item;
    }));
  }

  async function loadSimilarCandidates() {
    if (!creatorId || !pageContext?.api || detail?.record?.archived_at) return;
    const currentLifecycle = lifecycleId;
    const card = element("creator-library-similar-card");
    if (card) card.hidden = false;
    setText("creator-library-similar-status", t("creatorSimilaritySearching"));
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
        t("creatorSimilaritySummary", { total: Number(result?.total || 0), shown: result?.candidates?.length || 0 }),
      );
    } catch (error) {
      if (error?.name === "AbortError" || !pageContext || currentLifecycle !== lifecycleId || requestController !== similarController) return;
      renderSimilarCandidates({ candidates: [] });
      setText("creator-library-similar-status", error?.message || t("creatorSimilarityFailed"));
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
        clearRenderedDetail(t("creatorMissingId"));
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
