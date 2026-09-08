(function registerCampaignDetailPage(global) {
  "use strict";

  const STAGE_LABELS = Object.freeze({
    pending_contact: "待联系",
    contacted: "已联系",
    quoted: "已报价",
    negotiating: "谈判中",
    agreed: "已确认",
    executing: "执行中",
    completed: "已完成",
    rejected: "已拒绝",
  });

  const STATUS_LABELS = Object.freeze({
    draft: "Draft",
    sourcing: "Sourcing",
    running: "Running",
    completed: "Completed",
  });

  let resources = null;
  let campaignController = null;
  let relationsController = null;
  let creatorsController = null;
  let accountsController = null;
  let campaignId = "";
  let campaign = null;
  let relations = [];
  let missingPublishLinks = [];
  let missingPublishError = "";
  let publicationObservations = new Map();
  let campaignPerformance = null;
  let publicationRefreshPending = false;
  let googleSheetsSyncPending = false;
  let creators = [];
  let creatorsLoaded = false;
  let editingRelationId = null;
  let saving = false;
  let deleting = false;
  let lifecycleId = 0;
  const accountCache = new Map();

  function element(id) {
    return document.getElementById(id);
  }

  function setText(id, value) {
    const target = element(id);
    if (target) target.textContent = String(value ?? "");
  }

  function getApp() {
    if (!global.KOLConnectApp) throw new Error("KOLConnect application helpers are unavailable.");
    return global.KOLConnectApp;
  }

  function isArchived() {
    return Boolean(String(campaign?.archived_at || "").trim());
  }

  function valueOrDash(value) {
    if (value === "" || value == null) return "--";
    return String(value);
  }

  function formatNumber(value) {
    if (value === "" || value == null) return "--";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(number);
  }

  function formatMoney(value, currency) {
    const amount = formatNumber(value);
    if (amount === "--") return amount;
    const code = String(currency || "").trim().toUpperCase();
    return code ? `${code} ${amount}` : amount;
  }

  function safeHttpUrl(value) {
    try {
      const url = new URL(String(value || ""));
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function createCell(value, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = value;
    return cell;
  }

  function createBadge(label, status) {
    const badge = document.createElement("span");
    badge.className = "status-pill";
    badge.dataset.status = status;
    badge.textContent = label;
    return badge;
  }

  function setDetailState(state, message = "") {
    const loading = element("campaign-detail-loading");
    const error = element("campaign-detail-error");
    const content = element("campaign-detail-content");
    if (loading) loading.hidden = state !== "loading";
    if (error) error.hidden = state !== "error";
    if (content) content.hidden = state !== "loaded" && !(state === "error" && campaign);
    if (message && element("campaign-detail-error-message")) {
      element("campaign-detail-error-message").textContent = message;
    }
  }

  function appendOverviewItem(label, value) {
    const item = document.createElement("div");
    item.className = "campaign-detail-overview-item";
    const labelElement = document.createElement("span");
    labelElement.textContent = label;
    const valueElement = document.createElement("strong");
    valueElement.textContent = valueOrDash(value);
    item.append(labelElement, valueElement);
    element("campaign-detail-overview").appendChild(item);
  }

  function renderOverview() {
    element("campaign-detail-title").textContent = campaign?.name || "Campaign 详情";
    element("campaign-detail-subtitle").textContent = campaign?.product_name
      ? `${campaign.product_name} · Campaign 执行与合作记录`
      : "Campaign 执行与合作记录";

    const overview = element("campaign-detail-overview");
    overview.replaceChildren();
    appendOverviewItem("产品", campaign?.product_name);
    appendOverviewItem("国家/地区", campaign?.country);
    const platforms = Array.isArray(campaign?.platforms) ? campaign.platforms : [];
    appendOverviewItem("平台", platforms.length ? platforms.join("、") : "不限平台");
    appendOverviewItem("开始日期", campaign?.start_date);
    appendOverviewItem("结束日期", campaign?.end_date);
    appendOverviewItem("预算", formatNumber(campaign?.budget));
    appendOverviewItem("负责人", campaign?.owner);
    appendOverviewItem("创建时间", campaign?.created_at);
    element("campaign-detail-goal").textContent = valueOrDash(campaign?.goal);

    const badges = element("campaign-detail-badges");
    badges.replaceChildren();
    const status = String(campaign?.status || "draft");
    badges.appendChild(createBadge(STATUS_LABELS[status] || status, status));
    badges.appendChild(createBadge(isArchived() ? "Archived" : "Active", isArchived() ? "archived" : "active"));

    element("campaign-detail-readonly").hidden = !isArchived();
    element("campaign-creator-add-open").disabled = isArchived();
  }

  function parsePublishLinks(value) {
    if (Array.isArray(value)) return value.map(item => String(item || "").trim()).filter(Boolean);
    const text = String(value || "").trim();
    if (!text) return [];
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) return parsed.map(item => String(item || "").trim()).filter(Boolean);
    } catch (_error) {
      // Legacy values may be newline- or comma-separated text.
    }
    return text.split(/\r?\n|,/).map(item => item.trim()).filter(Boolean);
  }

  function appendLinksCell(row, linksValue) {
    const cell = document.createElement("td");
    const links = parsePublishLinks(linksValue)
      .map(safeHttpUrl)
      .filter(Boolean);
    if (!links.length) {
      cell.textContent = "--";
    } else {
      const container = document.createElement("div");
      container.className = "campaign-publish-links";
      links.forEach((url, index) => {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = links.length === 1 ? "查看发布内容" : `发布内容 ${index + 1}`;
        container.appendChild(link);
      });
      cell.appendChild(container);
    }
    row.appendChild(cell);
  }

  function renderRelations() {
    const body = element("campaign-creator-list-body");
    const empty = element("campaign-creator-empty");
    const table = element("campaign-creator-table-wrap");
    body.replaceChildren();
    element("campaign-creator-count").textContent = `${relations.length} 位达人`;
    empty.hidden = relations.length !== 0;
    table.hidden = relations.length === 0;

    relations.forEach(relation => {
      const row = document.createElement("tr");
      row.dataset.campaignCreatorId = String(relation.id || "");
      row.appendChild(createCell(valueOrDash(relation.creator_name), "campaign-creator-name-cell"));
      row.appendChild(createCell(valueOrDash(relation.agency_name)));

      const accountCell = document.createElement("td");
      const accountUrl = safeHttpUrl(relation.account_url);
      if (accountUrl) {
        const accountLink = document.createElement("a");
        accountLink.href = accountUrl;
        accountLink.target = "_blank";
        accountLink.rel = "noopener noreferrer";
        accountLink.textContent = "查看账号";
        accountCell.appendChild(accountLink);
      } else {
        accountCell.textContent = "--";
      }
      row.appendChild(accountCell);
      row.appendChild(createCell(valueOrDash(relation.account_platform)));

      const stageCell = document.createElement("td");
      const stage = String(relation.stage || "pending_contact");
      stageCell.appendChild(createBadge(STAGE_LABELS[stage] || stage, stage));
      row.appendChild(stageCell);
      row.appendChild(createCell(formatMoney(relation.creator_quote, relation.quote_currency)));
      row.appendChild(createCell(formatMoney(relation.cost, relation.cost_currency)));
      appendLinksCell(row, relation.publish_links);
      row.appendChild(createCell(formatNumber(relation.views)));
      row.appendChild(createCell(formatNumber(relation.roi)));

      const actionCell = document.createElement("td");
      if (!isArchived()) {
        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "mini-btn";
        editButton.dataset.campaignCreatorAction = "edit";
        editButton.dataset.campaignCreatorId = String(relation.id || "");
        editButton.textContent = "编辑";
        actionCell.appendChild(editButton);
      }
      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "mini-btn danger";
      removeButton.dataset.campaignCreatorAction = "remove";
      removeButton.dataset.campaignCreatorId = String(relation.id || "");
      removeButton.textContent = "移除";
      actionCell.appendChild(removeButton);
      row.appendChild(actionCell);
      body.appendChild(row);
    });
  }

  function renderMissingPublishLinks() {
    const body = element("campaign-missing-publish-body");
    const empty = element("campaign-missing-publish-empty");
    const table = element("campaign-missing-publish-table-wrap");
    const count = element("campaign-missing-publish-count");
    if (!body || !empty || !table || !count) return;
    body.replaceChildren();
    count.textContent = missingPublishError ? "--" : `${missingPublishLinks.length} 条`;
    empty.textContent = missingPublishError
      ? "缺失发布信息暂不可用，请稍后重试。"
      : "暂无缺失发布信息。";
    empty.hidden = missingPublishLinks.length !== 0 && !missingPublishError;
    table.hidden = missingPublishLinks.length === 0;
    missingPublishLinks.forEach(record => {
      const row = document.createElement("tr");
      row.appendChild(createCell(valueOrDash(record.campaign_name || record.campaign_id)));
      row.appendChild(createCell(valueOrDash(record.creator_name || record.creator_id)));
      row.appendChild(createCell(valueOrDash(record.stage)));
      row.appendChild(createCell(valueOrDash(record.publish_date)));
      row.appendChild(createCell(valueOrDash(record.publish_links)));
      row.appendChild(createCell(String(record.risk_level || "").toUpperCase() || "--"));
      body.appendChild(row);
    });
  }

  function metricText(value) {
    return value === null || value === undefined || value === "" ? "—" : formatNumber(value);
  }

  function coverageText(coverage) {
    return `${coverage?.valid_count || 0} / ${coverage?.total_publications || 0} 条有数据`;
  }

  function currencyGroupsText(groups) {
    const entries = Object.entries(groups || {});
    return entries.length
      ? entries.map(([currency, amount]) => `${currency} ${formatNumber(amount)}`).join(" · ")
      : "—";
  }

  function appendPerformanceHighlight(label, value, detail = "") {
    const container = element("campaign-performance-highlights");
    if (!container) return;
    const item = document.createElement("article");
    const title = document.createElement("small");
    const primary = document.createElement("strong");
    const context = document.createElement("span");
    title.textContent = label;
    primary.textContent = value || "—";
    context.textContent = detail;
    item.append(title, primary, context);
    container.appendChild(item);
  }

  function renderCampaignPerformanceAnalytics() {
    const data = campaignPerformance;
    const totals = data?.totals || {};
    ["views", "likes", "comments"].forEach(metric => {
      setText(`campaign-performance-total-${metric}`, metricText(totals[metric]?.total));
      setText(`campaign-performance-${metric}-coverage`, coverageText(totals[metric]));
    });
    setText("campaign-performance-average-er", data?.average_er == null ? "—" : `${formatNumber(data.average_er)}%`);
    setText("campaign-performance-er-coverage", `${data?.valid_er_count || 0} / ${data?.total_publications || 0} 条有数据`);

    const highlights = element("campaign-performance-highlights");
    if (highlights) highlights.replaceChildren();
    appendPerformanceHighlight("Top Creator", data?.top_creator?.creator_name, data?.top_creator ? `累计播放 ${formatNumber(data.top_creator.views)}` : "暂无可用播放数据");
    appendPerformanceHighlight("Top Video", data?.top_video?.creator_name, data?.top_video ? `${data.top_video.publication_id} · 播放 ${formatNumber(data.top_video.views)}` : "暂无可用播放数据");
    appendPerformanceHighlight("最高互动率", data?.highest_er?.creator_name, data?.highest_er ? `${data.highest_er.publication_id} · ${formatNumber(data.highest_er.engagement_rate)}%` : "暂无可用互动率");
    const fastest = data?.fastest_growing;
    appendPerformanceHighlight(
      "最快增长（播放/天）",
      fastest?.creator_name,
      fastest ? `${formatNumber(fastest.growth_rate)} / 天 · ${fastest.start_observed_at} 至 ${fastest.end_observed_at}` : "至少需要两个不同时间的播放观察",
    );
    setText(
      "campaign-performance-money",
      `确认成本：${currencyGroupsText(data?.total_cost_by_currency)} · 历史报价：${currencyGroupsText(data?.total_quote_by_currency)} · 未知币种成本/报价记录 ${data?.unknown_currency_records?.cost || 0}/${data?.unknown_currency_records?.quote || 0}（不纳入币种汇总） · ROI：—（缺少权威回报数据）`,
    );

    const trends = element("campaign-performance-trends");
    if (!trends) return;
    trends.replaceChildren();
    (Array.isArray(data?.publications) ? data.publications : []).forEach(publication => {
      const series = Array.isArray(publication.series) ? publication.series : [];
      if (!series.length) return;
      const section = document.createElement("section");
      const heading = document.createElement("h3");
      heading.textContent = `${publication.creator_name || "未命名达人"} · ${publication.platform || "未知平台"}`;
      const identity = document.createElement("small");
      identity.textContent = `${publication.publication_id} · ${publication.actual_account_uid || "账号未记录"}`;
      const table = document.createElement("table");
      table.className = "campaign-performance-trend-table";
      const head = document.createElement("thead");
      const headRow = document.createElement("tr");
      ["观察时间", "播放", "点赞", "评论", "互动率"].forEach(label => headRow.appendChild(createCell(label)));
      head.appendChild(headRow);
      const body = document.createElement("tbody");
      series.forEach(point => {
        const row = document.createElement("tr");
        [point.observed_at, point.views, point.likes, point.comments, point.engagement_rate == null ? null : `${point.engagement_rate}%`]
          .forEach(value => row.appendChild(createCell(metricText(value))));
        body.appendChild(row);
      });
      table.append(head, body);
      section.append(heading, identity, table);
      const growth = document.createElement("p");
      growth.className = "hint";
      growth.textContent = [["views", "播放"], ["likes", "点赞"], ["comments", "评论"], ["engagement_rate", "ER（百分点）"]]
        .map(([metric, label]) => {
          const delta = publication.growth?.[metric];
          if (!delta) return `${label}增长 —`;
          const percentage = delta.percentage == null ? "百分比不可用" : `${formatNumber(delta.percentage)}%`;
          return `${label}增长 ${formatNumber(delta.absolute)} (${percentage}) · ${delta.start_observed_at} 至 ${delta.end_observed_at}${delta.status === "decrease" ? " · 观察值下降" : ""}`;
        }).join("；");
      section.appendChild(growth);
      trends.appendChild(section);
    });
  }

  async function reloadCampaignPerformanceAnalytics() {
    if (!resources || !campaignId) return;
    const currentLifecycle = lifecycleId;
    try {
      const data = await global.KOLConnectAPI.get(
        `/api/campaigns/${encodeURIComponent(campaignId)}/performance`,
        { signal: resources.signal },
      );
      if (!resources || currentLifecycle !== lifecycleId) return;
      campaignPerformance = data;
    } catch (error) {
      if (!resources || currentLifecycle !== lifecycleId) return;
      if (error?.name === "AbortError") throw error;
      campaignPerformance = null;
    }
    renderCampaignPerformanceAnalytics();
  }

  function allPublications() {
    return relations.flatMap(relation => (
      Array.isArray(relation.publications)
        ? relation.publications.map(publication => ({ relation, publication }))
        : []
    ));
  }

  function renderPublicationPerformance() {
    const list = element("campaign-publication-performance-list");
    const empty = element("campaign-publication-performance-empty");
    const count = element("campaign-publication-performance-count");
    const refreshAll = element("campaign-publications-refresh-all");
    if (!list || !empty || !count || !refreshAll) return;
    const publications = allPublications();
    list.replaceChildren();
    count.textContent = `${publications.length} 条`;
    empty.hidden = publications.length !== 0;
    refreshAll.disabled = publicationRefreshPending || publications.length === 0;
    publications.forEach(({ relation, publication }) => {
      const publicationId = String(publication.publication_id || "");
      const observation = publicationObservations.get(publicationId) || null;
      const card = document.createElement("article");
      card.className = "campaign-publication-performance-card";
      card.dataset.publicationPerformance = publicationId;

      const heading = document.createElement("div");
      heading.className = "campaign-publication-performance-heading";
      const identity = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = relation.creator_name || "未命名达人";
      const meta = document.createElement("small");
      meta.textContent = `${publication.platform || "未知平台"} · ${observation ? `最近检查 ${observation.observed_at}` : "尚未检查"}`;
      identity.append(title, meta);
      const refresh = document.createElement("button");
      refresh.type = "button";
      refresh.className = "soft-btn compact-btn";
      refresh.dataset.publicationRefresh = publicationId;
      refresh.dataset.campaignCreatorId = String(relation.id || "");
      refresh.disabled = publicationRefreshPending;
      refresh.textContent = "刷新";
      heading.append(identity, refresh);

      const metrics = document.createElement("div");
      metrics.className = "campaign-publication-metrics";
      [
        ["播放", observation?.views], ["点赞", observation?.likes],
        ["评论", observation?.comments], ["分享", observation?.shares],
        ["互动率", observation?.engagement_rate == null ? null : `${observation.engagement_rate}%`],
      ].forEach(([label, value]) => {
        const item = document.createElement("span");
        const labelNode = document.createElement("small");
        labelNode.textContent = label;
        const valueNode = document.createElement("b");
        valueNode.textContent = metricText(value);
        item.append(labelNode, valueNode);
        metrics.appendChild(item);
      });
      const source = document.createElement("small");
      source.className = "hint";
      source.textContent = observation
        ? `来源 ${observation.source} · 置信度 ${observation.confidence}`
        : "追踪状态：Unavailable";
      card.append(heading, metrics, source);
      list.appendChild(card);
    });
  }

  function hydrateLatestPublicationObservations() {
    publicationObservations = new Map(
      (Array.isArray(campaignPerformance?.publications) ? campaignPerformance.publications : [])
        .map(publication => {
          const series = Array.isArray(publication.series) ? publication.series : [];
          return [String(publication.publication_id || ""), series[series.length - 1] || null];
        }),
    );
  }

  function setPublicationStatus(message, isError = false) {
    const status = element("campaign-publication-performance-status");
    if (!status) return;
    status.hidden = !message;
    status.textContent = message || "";
    status.className = `campaign-form-error${isError ? "" : " is-success"}`;
  }

  async function refreshPublication(relationId, publicationId) {
    if (publicationRefreshPending || !resources) return;
    publicationRefreshPending = true;
    setPublicationStatus("");
    renderPublicationPerformance();
    try {
      const result = await global.KOLConnectAPI.post(
        `/api/campaign-creators/${encodeURIComponent(relationId)}/publications/${encodeURIComponent(publicationId)}/refresh`,
        {}, { signal: resources.signal },
      );
      if (result.observation) publicationObservations.set(publicationId, result.observation);
      await reloadCampaignPerformanceAnalytics();
      setPublicationStatus(
        result.status === "SUCCESS" ? "发布内容指标已刷新。" : `暂不可刷新：${result.reason || result.status}`,
        result.status !== "SUCCESS",
      );
    } catch (error) {
      if (error?.name !== "AbortError") setPublicationStatus(error.message || "刷新失败。", true);
    } finally {
      publicationRefreshPending = false;
      renderPublicationPerformance();
    }
  }

  async function refreshAllPublications() {
    if (publicationRefreshPending || !resources || !campaignId) return;
    publicationRefreshPending = true;
    setPublicationStatus("");
    renderPublicationPerformance();
    try {
      const result = await global.KOLConnectAPI.post(
        `/api/campaigns/${encodeURIComponent(campaignId)}/publications/refresh`,
        {}, { signal: resources.signal },
      );
      result.results?.forEach(item => {
        if (item.observation) publicationObservations.set(String(item.publication_id || ""), item.observation);
      });
      await reloadCampaignPerformanceAnalytics();
      setPublicationStatus(
        result.status === "SUCCESS"
          ? "全部发布内容指标已刷新。"
          : `批量刷新 ${result.status || "FAILED"}：成功 ${result.succeeded || 0}，未完成 ${result.failed || 0}。`,
        result.status !== "SUCCESS",
      );
    } catch (error) {
      if (error?.name !== "AbortError") setPublicationStatus(error.message || "批量刷新失败。", true);
    } finally {
      publicationRefreshPending = false;
      renderPublicationPerformance();
    }
  }

  function handlePublicationPerformanceClick(event) {
    const button = event.target?.closest?.("[data-publication-refresh]");
    if (button) refreshPublication(button.dataset.campaignCreatorId, button.dataset.publicationRefresh);
  }

  async function loadDetail() {
    if (!resources || !campaignId) return;
    const currentLifecycle = lifecycleId;
    campaignController?.abort();
    relationsController?.abort();
    campaignController = resources.createAbortController();
    relationsController = resources.createAbortController();
    setDetailState("loading");
    missingPublishError = "";

    try {
      const [campaignData, relationsData, publishingData, performanceData] = await Promise.all([
        global.KOLConnectAPI.get(`/api/campaigns/${encodeURIComponent(campaignId)}`, {
          signal: campaignController.signal,
        }),
        global.KOLConnectAPI.get(`/api/campaigns/${encodeURIComponent(campaignId)}/creators`, {
          signal: relationsController.signal,
        }),
        global.KOLConnectAPI.get(`/api/campaigns/${encodeURIComponent(campaignId)}/missing-publish-links`, {
          signal: relationsController.signal,
        }).catch(error => {
          if (error?.name === "AbortError") throw error;
          missingPublishError = "missing_publish_links_unavailable";
          return { missing_publish_links: [] };
        }),
        global.KOLConnectAPI.get(`/api/campaigns/${encodeURIComponent(campaignId)}/performance`, {
          signal: relationsController.signal,
        }).catch(error => {
          if (error?.name === "AbortError") throw error;
          return null;
        }),
      ]);
      if (!resources || currentLifecycle !== lifecycleId) return;
      campaign = campaignData.campaign || null;
      relations = Array.isArray(relationsData.campaign_creators)
        ? relationsData.campaign_creators
        : [];
      missingPublishLinks = Array.isArray(publishingData.missing_publish_links)
        ? publishingData.missing_publish_links
        : [];
      campaignPerformance = performanceData;
      hydrateLatestPublicationObservations();
      if (!campaign) throw new Error("Campaign 数据不存在。");
      if (isArchived()) closeCreatorForm();
      renderOverview();
      renderRelations();
      renderMissingPublishLinks();
      renderCampaignPerformanceAnalytics();
      renderPublicationPerformance();
      setDetailState("loaded");
    } catch (error) {
      if (error?.name === "AbortError" || currentLifecycle !== lifecycleId) return;
      if (!campaign) {
        relations = [];
        missingPublishLinks = [];
      }
      setDetailState(
        "error",
        error?.status === 404
          ? "Campaign 不存在或已删除。"
          : "Campaign 详情加载失败，请稍后重试。",
      );
    }
  }

  function appendOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }

  function renderCreatorOptions(selectedId = "") {
    const select = element("campaign-creator-id");
    select.replaceChildren();
    appendOption(select, "", "请选择达人");
    const assigned = new Set(relations.map(item => String(item.creator_id || "")));
    creators
      .filter(creator => !assigned.has(String(creator.creator_id || "")) || String(creator.creator_id) === String(selectedId))
      .forEach(creator => {
        const name = creator.creator_name || "未命名达人";
        const platform = creator.platform ? ` · ${creator.platform}` : "";
        appendOption(select, String(creator.creator_id || ""), `${name}${platform}`);
      });
    select.value = String(selectedId || "");
  }

  async function loadCreatorOptions() {
    if (creatorsLoaded || !resources) return;
    const currentLifecycle = lifecycleId;
    creatorsController?.abort();
    creatorsController = resources.createAbortController();
    const select = element("campaign-creator-id");
    select.disabled = true;
    select.replaceChildren();
    appendOption(select, "", "正在加载达人...");
    try {
      const data = await global.KOLConnectAPI.get("/api/creator-library", {
        signal: creatorsController.signal,
      });
      if (!resources || currentLifecycle !== lifecycleId) return;
      creators = Array.isArray(data.records) ? data.records : [];
      creatorsLoaded = true;
      renderCreatorOptions();
      select.disabled = false;
    } catch (error) {
      if (error?.name === "AbortError" || currentLifecycle !== lifecycleId) return;
      select.replaceChildren();
      appendOption(select, "", "达人列表加载失败");
      showFormError(error.message || "达人列表加载失败，请稍后重试。");
    }
  }

  function campaignPlatforms() {
    if (Array.isArray(campaign?.platforms)) return campaign.platforms;
    return campaign?.platform ? [campaign.platform] : [];
  }

  function eligibleAccounts(accounts) {
    const platforms = campaignPlatforms();
    return platforms.length
      ? accounts.filter(account => platforms.includes(String(account?.platform || "")))
      : accounts;
  }

  function renderAccountOptions(accounts, selectedIds = []) {
    const select = element("campaign-creator-account-id");
    const picker = element("campaign-account-picker");
    const optionsContainer = element("campaign-account-options");
    const selected = new Set(
      Array.isArray(selectedIds) ? selectedIds.map(String) : [String(selectedIds || "")],
    );
    const eligible = eligibleAccounts(accounts);
    select.replaceChildren();
    optionsContainer?.replaceChildren();
    eligible.forEach(account => {
      const platform = account.platform || "未知平台";
      const profile = account.username
        ? `@${String(account.username).replace(/^@/, "")}`
        : account.profile_url || account.account_uid || account.account_id || "";
      const accountId = String(account.account_id || "");
      const labelText = `${platform} · ${profile}`;
      appendOption(select, accountId, labelText);
      const option = select.options?.[select.options.length - 1];
      if (option) option.selected = selected.has(accountId);
      if (optionsContainer) {
        const label = document.createElement("label");
        label.className = "campaign-account-option";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = accountId;
        checkbox.checked = selected.has(accountId);
        checkbox.addEventListener("change", () => {
          if (option) option.selected = checkbox.checked;
          label.className = `campaign-account-option${checkbox.checked ? " is-selected" : ""}`;
          updateAccountSelectionSummary();
        });
        const text = document.createElement("span");
        text.textContent = labelText;
        label.className = `campaign-account-option${checkbox.checked ? " is-selected" : ""}`;
        label.append(checkbox, text);
        optionsContainer.appendChild(label);
      }
    });
    if (!Array.isArray(selectedIds) && selectedIds) select.value = String(selectedIds);
    select.disabled = eligible.length === 0;
    if (picker) {
      picker.classList.toggle("is-disabled", eligible.length === 0);
      if (!eligible.length) picker.open = false;
    }
    updateAccountSelectionSummary(eligible.length);
  }

  function updateAccountSelectionSummary(eligibleCount = null) {
    const select = element("campaign-creator-account-id");
    const summary = element("campaign-account-summary");
    if (!summary) return;
    const selected = Array.from(select?.selectedOptions || []);
    if (selected.length === 1) {
      summary.textContent = `已选择：${selected[0].textContent || selected[0].text || selected[0].value}`;
    } else if (selected.length > 1) {
      summary.textContent = `已选择 ${selected.length} 个账号`;
    } else {
      const count = eligibleCount == null ? Number(select?.options?.length || 0) : eligibleCount;
      summary.textContent = count ? "请选择计划发布账号" : "该达人暂无符合平台的账号";
    }
  }

  function handleAccountPickerClickOutside(event) {
    const picker = element("campaign-account-picker");
    if (picker?.open && !picker.contains(event.target)) picker.open = false;
  }

  async function loadAccounts(creatorId, selectedId = "") {
    const normalizedId = String(creatorId || "");
    if (!normalizedId) {
      renderAccountOptions([]);
      return;
    }
    if (accountCache.has(normalizedId)) {
      renderAccountOptions(accountCache.get(normalizedId), selectedId);
      return;
    }

    const currentLifecycle = lifecycleId;
    accountsController?.abort();
    accountsController = resources.createAbortController();
    const select = element("campaign-creator-account-id");
    select.disabled = true;
    select.replaceChildren();
    appendOption(select, "", "正在加载账号...");
    try {
      const data = await global.KOLConnectAPI.get(
        `/api/creator-library/${encodeURIComponent(normalizedId)}`,
        { signal: accountsController.signal },
      );
      if (!resources || currentLifecycle !== lifecycleId) return;
      const accounts = Array.isArray(data.accounts) ? data.accounts : [];
      accountCache.set(normalizedId, accounts);
      if (String(element("campaign-creator-id").value || "") !== normalizedId) return;
      renderAccountOptions(accounts, selectedId);
    } catch (error) {
      if (error?.name === "AbortError" || currentLifecycle !== lifecycleId) return;
      renderAccountOptions([]);
      showFormError(error.message || "达人账号加载失败，请稍后重试。");
    }
  }

  function resetFormValues() {
    element("campaign-creator-stage").value = "pending_contact";
    element("campaign-creator-quote-currency").value = "";
    element("campaign-creator-quote-unit-amount").value = "";
    element("campaign-creator-quote-quantity").value = "";
    element("campaign-creator-quote-unit").value = "";
    element("campaign-creator-quote").value = "";
    element("campaign-creator-cost").value = "";
    element("campaign-creator-cost-currency").value = "";
    element("campaign-creator-publish-links").value = "";
    setPublicationRows([]);
    setPlannedDates([]);
    element("campaign-creator-views").value = "";
    element("campaign-creator-likes").value = "";
    element("campaign-creator-comments").value = "";
    element("campaign-creator-roi").value = "";
    element("campaign-creator-performance-note").value = "";
    element("campaign-creator-form-error").hidden = true;
    element("campaign-creator-form-error").textContent = "";
  }

  function closeCreatorForm() {
    editingRelationId = null;
    resetFormValues();
    const creatorSelect = element("campaign-creator-id");
    creatorSelect.replaceChildren();
    appendOption(creatorSelect, "", "请选择达人");
    creatorSelect.disabled = false;
    renderAccountOptions([]);
    element("campaign-creator-form-card").hidden = true;
  }

  async function openAddForm() {
    if (isArchived()) return;
    closeCreatorForm();
    element("campaign-creator-form-title").textContent = "添加达人";
    element("campaign-creator-form-card").hidden = false;
    await loadCreatorOptions();
    renderCreatorOptions();
  }

  function assignFormValue(id, value) {
    element(id).value = value === "" || value == null ? "" : String(value);
  }

  function updateStructuredQuoteTotal() {
    const amount = Number(element("campaign-creator-quote-unit-amount").value);
    const quantity = Number(element("campaign-creator-quote-quantity").value);
    element("campaign-creator-quote").value = (
      Number.isFinite(amount) && amount >= 0 && Number.isInteger(quantity) && quantity > 0
    ) ? String(amount * quantity) : "";
  }

  function createPlannedDateRow(value = "", removable = true) {
    const row = document.createElement("div");
    row.className = "campaign-planned-date-row";
    const input = document.createElement("input");
    input.type = "date";
    if (!removable) input.id = "campaign-creator-publish-date";
    input.value = String(value || "");
    input.dataset.plannedPublishDate = "";
    row.appendChild(input);
    if (removable) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "soft-btn compact-btn";
      remove.dataset.removePlannedDate = "";
      remove.textContent = "移除";
      row.appendChild(remove);
    }
    return row;
  }

  function setPlannedDates(values) {
    const list = element("campaign-planned-date-list");
    if (!list) {
      if (element("campaign-creator-publish-date")) {
        element("campaign-creator-publish-date").value = values?.[0] || "";
      }
      return;
    }
    const dates = Array.isArray(values) && values.length ? values : [""];
    list.replaceChildren(...dates.map((value, index) => createPlannedDateRow(value, index > 0)));
  }

  function plannedDates() {
    const list = element("campaign-planned-date-list");
    const inputs = list?.querySelectorAll?.("[data-planned-publish-date]");
    if (inputs?.length) return [...inputs].map(input => input.value).filter(Boolean);
    const legacy = element("campaign-creator-publish-date")?.value || "";
    return legacy ? [legacy] : [];
  }

  function selectedAccountIds() {
    const select = element("campaign-creator-account-id");
    const selected = Array.from(select?.selectedOptions || [])
      .map(option => String(option.value || ""))
      .filter(Boolean);
    if (selected.length) return selected;
    return select?.value ? [String(select.value)] : [];
  }

  function createPublicationRow(publication = {}) {
    const row = document.createElement("div");
    row.className = "campaign-publication-row";
    row.dataset.publicationRow = "";

    const url = document.createElement("input");
    url.type = "url";
    url.placeholder = "https://...";
    url.value = publication.actual_publish_url || "";
    url.dataset.publicationUrl = "";

    const account = document.createElement("select");
    account.dataset.publicationAccount = "";
    appendOption(account, "", "实际账号未知");
    const creatorId = String(element("campaign-creator-id")?.value || "");
    (accountCache.get(creatorId) || []).forEach(item => {
      const accountId = String(item.account_id || "");
      appendOption(account, accountId, `${item.platform || "未知平台"} · ${item.username || item.profile_url || accountId}`);
    });
    account.value = publication.actual_account_id || "";

    const publishedAt = document.createElement("input");
    publishedAt.type = "datetime-local";
    publishedAt.value = String(publication.actual_published_at || "").replace(/Z$/, "");
    publishedAt.dataset.publicationPublishedAt = "";

    const observed = document.createElement("small");
    observed.className = "hint";
    observed.textContent = publication.observed_at
      ? `记录于 ${publication.observed_at}`
      : "保存时记录观察时间";

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "soft-btn compact-btn";
    remove.dataset.removePublication = "";
    remove.textContent = "移除";
    row.dataset.publicationId = publication.publication_id || "";
    row.append(url, account, publishedAt, observed, remove);
    return row;
  }

  function setPublicationRows(publications) {
    const list = element("campaign-publication-list");
    if (!list) return;
    const values = Array.isArray(publications) ? publications : [];
    list.replaceChildren(...values.map(createPublicationRow));
  }

  function publicationPayload() {
    const list = element("campaign-publication-list");
    const rows = list?.querySelectorAll?.("[data-publication-row]");
    if (!rows) {
      return parsePublishLinks(element("campaign-creator-publish-links").value).map(url => ({
        actual_publish_url: url,
        actual_account_id: "",
        actual_published_at: "",
        observed_at: "",
        source: "legacy",
      }));
    }
    return [...rows].map(row => ({
      publication_id: row.dataset.publicationId || "",
      actual_publish_url: row.querySelector?.("[data-publication-url]")?.value?.trim() || "",
      actual_account_id: row.querySelector?.("[data-publication-account]")?.value || "",
      actual_published_at: row.querySelector?.("[data-publication-published-at]")?.value || "",
      source: "manual",
    })).filter(item => item.actual_publish_url);
  }

  async function openEditForm(relationId) {
    if (isArchived()) return;
    const relation = relations.find(item => String(item.id) === String(relationId));
    if (!relation) return;
    closeCreatorForm();
    editingRelationId = String(relation.id);
    element("campaign-creator-form-title").textContent = `编辑合作记录 · ${relation.creator_name || "达人"}`;
    const creatorSelect = element("campaign-creator-id");
    creatorSelect.replaceChildren();
    appendOption(creatorSelect, String(relation.creator_id || ""), relation.creator_name || "未命名达人");
    creatorSelect.value = String(relation.creator_id || "");
    creatorSelect.disabled = true;
    assignFormValue("campaign-creator-stage", relation.stage || "pending_contact");
    assignFormValue("campaign-creator-quote-currency", relation.quote_currency);
    assignFormValue("campaign-creator-quote-unit-amount", relation.quote_unit_amount);
    assignFormValue("campaign-creator-quote-quantity", relation.quote_quantity);
    assignFormValue("campaign-creator-quote-unit", relation.quote_unit);
    assignFormValue("campaign-creator-quote", relation.creator_quote);
    assignFormValue("campaign-creator-cost", relation.cost);
    assignFormValue("campaign-creator-cost-currency", relation.cost_currency);
    assignFormValue("campaign-creator-publish-links", parsePublishLinks(relation.publish_links).join("\n"));
    setPlannedDates(
      Array.isArray(relation.planned_publish_dates)
        ? relation.planned_publish_dates
        : [relation.publish_date].filter(Boolean),
    );
    assignFormValue("campaign-creator-views", relation.views);
    assignFormValue("campaign-creator-likes", relation.likes);
    assignFormValue("campaign-creator-comments", relation.comments);
    assignFormValue("campaign-creator-roi", relation.roi);
    assignFormValue("campaign-creator-performance-note", relation.performance_note);
    element("campaign-creator-form-card").hidden = false;
    await loadAccounts(
      relation.creator_id,
      Array.isArray(relation.account_ids) ? relation.account_ids : relation.account_id,
    );
    setPublicationRows(Array.isArray(relation.publications) ? relation.publications : []);
  }

  function showFormError(message) {
    const error = element("campaign-creator-form-error");
    error.textContent = message;
    error.hidden = false;
  }

  function formPayload() {
    const accountIds = selectedAccountIds();
    const dates = plannedDates();
    const publications = publicationPayload();
    return {
      account_id: accountIds[0] || "",
      account_ids: accountIds,
      stage: element("campaign-creator-stage").value || "pending_contact",
      quote_currency: element("campaign-creator-quote-currency").value.trim().toUpperCase(),
      quote_unit_amount: element("campaign-creator-quote-unit-amount").value.trim(),
      quote_quantity: element("campaign-creator-quote-quantity").value.trim(),
      quote_unit: element("campaign-creator-quote-unit").value,
      creator_quote: element("campaign-creator-quote").value.trim(),
      cost: element("campaign-creator-cost").value.trim(),
      cost_currency: element("campaign-creator-cost-currency").value.trim().toUpperCase(),
      publications,
      publish_links: publications.map(item => item.actual_publish_url),
      publish_date: dates[0] || "",
      planned_publish_dates: dates,
      views: element("campaign-creator-views").value.trim(),
      likes: element("campaign-creator-likes").value.trim(),
      comments: element("campaign-creator-comments").value.trim(),
      roi: element("campaign-creator-roi").value.trim(),
      performance_note: element("campaign-creator-performance-note").value.trim(),
    };
  }

  function setSaving(value) {
    saving = value;
    const button = element("campaign-creator-form-save");
    button.disabled = value;
    button.textContent = value ? "正在保存..." : "保存合作记录";
  }

  async function saveRelation(event) {
    event.preventDefault();
    if (saving || !resources || isArchived()) return;
    const payload = formPayload();
    if (!payload.account_ids.length) return showFormError("请选择本次合作使用的执行账号。");
    if (!editingRelationId && !element("campaign-creator-id").value) {
      return showFormError("请选择要加入 Campaign 的达人。");
    }

    setSaving(true);
    try {
      if (editingRelationId) {
        await global.KOLConnectAPI.patch(
          `/api/campaign-creators/${encodeURIComponent(editingRelationId)}`,
          payload,
          { signal: resources.signal },
        );
        getApp().showSaved("达人合作记录已更新。");
      } else {
        await global.KOLConnectAPI.post(
          `/api/campaigns/${encodeURIComponent(campaignId)}/creators`,
          { ...payload, creator_id: element("campaign-creator-id").value },
          { signal: resources.signal },
        );
        getApp().showSaved("达人已加入 Campaign。");
      }
      closeCreatorForm();
      await loadDetail();
    } catch (error) {
      if (error?.name !== "AbortError") showFormError(error.message || "合作记录保存失败。");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreatorChange() {
    await loadAccounts(element("campaign-creator-id").value);
  }

  function handlePlannedDateClick(event) {
    if (event.target?.id === "campaign-planned-date-add") {
      element("campaign-planned-date-list")?.appendChild(createPlannedDateRow("", true));
      return;
    }
    const remove = event.target?.closest?.("[data-remove-planned-date]");
    if (remove) remove.parentElement?.remove();
  }

  function handlePublicationClick(event) {
    if (event.target?.id === "campaign-publication-add") {
      element("campaign-publication-list")?.appendChild(createPublicationRow());
      return;
    }
    const remove = event.target?.closest?.("[data-remove-publication]");
    if (remove) remove.parentElement?.remove();
  }

  async function removeRelation(relationId) {
    if (deleting || !resources) return;
    const relation = relations.find(item => String(item.id || "") === String(relationId || ""));
    const creatorName = relation?.creator_name || "该达人";
    if (!global.confirm(`确认从 Campaign 移除“${creatorName}”？达人资料和其他 Campaign 关系将保留。`)) return;
    deleting = true;
    try {
      await global.KOLConnectAPI.delete(
        `/api/campaign-creators/${encodeURIComponent(relationId)}`,
        { signal: resources.signal },
      );
      getApp().showSaved("达人已从 Campaign 移除，达人资料保持不变。");
      closeCreatorForm();
      await loadDetail();
    } catch (error) {
      if (error?.name !== "AbortError") getApp().showError(error);
    } finally {
      deleting = false;
    }
  }

  async function deleteCampaign() {
    if (deleting || !resources || !campaignId) return;
    if (!global.confirm("删除 Campaign 后，该 Campaign 与达人关系会被删除，但达人资料不会删除。")) return;
    deleting = true;
    try {
      await global.KOLConnectAPI.delete(
        `/api/campaigns/${encodeURIComponent(campaignId)}`,
        { signal: resources.signal },
      );
      getApp().showSaved("Campaign 已删除，达人资料保持不变。");
      await global.KOLConnectPages.navigate("campaigns");
    } catch (error) {
      if (error?.name !== "AbortError") getApp().showError(error);
    } finally {
      deleting = false;
    }
  }

  async function syncGoogleSheetsReport() {
    if (googleSheetsSyncPending || !campaignId || !resources) return;
    googleSheetsSyncPending = true;
    const button = element("campaign-google-sheets-sync");
    if (button) {
      button.disabled = true;
      button.textContent = "正在同步...";
    }
    const requestedCampaignId = campaignId;
    const requestedLifecycle = lifecycleId;
    try {
      const result = await global.KOLConnectAPI.post(
        `/api/campaigns/${encodeURIComponent(campaignId)}/google-sheets-sync`,
        {}, { signal: resources.signal },
      );
      if (!resources || requestedLifecycle !== lifecycleId || requestedCampaignId !== campaignId) return;
      if (result.status !== "SUCCESS") {
        throw new Error(
          result.status === "PARTIAL"
            ? "Google Sheets 报告仅部分写入，请检查各工作表状态后重试。"
            : `Google Sheets 报告同步失败：${result.error || result.status || "UNKNOWN"}`,
        );
      }
      const detail = (result.worksheets || [])
        .map(item => `${item.worksheet}: ${item.row_count ?? 0} 行`).join("；");
      getApp().showSaved(`Google Sheets 报告同步成功。${detail}`);
    } catch (error) {
      if (error?.name !== "AbortError") getApp().showError(error);
    } finally {
      googleSheetsSyncPending = false;
      if (button) {
        button.disabled = false;
        button.textContent = "同步报告到 Google Sheets";
      }
    }
  }

  async function handleListAction(event) {
    const button = event.target.closest("[data-campaign-creator-action]");
    if (!button) return;
    if (button.dataset.campaignCreatorAction === "edit") {
      await openEditForm(button.dataset.campaignCreatorId);
    } else if (button.dataset.campaignCreatorAction === "remove") {
      await removeRelation(button.dataset.campaignCreatorId);
    }
  }

  function listen(id, type, listener) {
    const target = element(id);
    if (target) resources.listen(target, type, listener);
  }

  const campaignDetailPage = {
    async load(context) {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      lifecycleId += 1;
      campaignId = String(context?.campaignId || "").trim();
      campaign = null;
      relations = [];
      missingPublishLinks = [];
      missingPublishError = "";
      publicationObservations = new Map();
      campaignPerformance = null;
      publicationRefreshPending = false;
      googleSheetsSyncPending = false;
      creators = [];
      creatorsLoaded = false;
      accountCache.clear();
      closeCreatorForm();
      if (!campaignId) {
        setDetailState("error", "缺少 Campaign ID，请返回列表重新进入。");
        return;
      }
      await loadDetail();
    },

    bind() {
      listen("campaign-detail-back", "click", () => global.KOLConnectPages.navigate("campaigns"));
      listen("campaign-detail-delete", "click", deleteCampaign);
      listen("campaign-google-sheets-sync", "click", syncGoogleSheetsReport);
      listen("campaign-detail-retry", "click", loadDetail);
      listen("campaign-creator-add-open", "click", openAddForm);
      listen("campaign-creator-form-cancel", "click", closeCreatorForm);
      listen("campaign-creator-form", "submit", saveRelation);
      listen("campaign-creator-id", "change", handleCreatorChange);
      listen("campaign-creator-quote-unit-amount", "input", updateStructuredQuoteTotal);
      listen("campaign-creator-quote-quantity", "input", updateStructuredQuoteTotal);
      listen("campaign-planned-date-add", "click", handlePlannedDateClick);
      listen("campaign-planned-date-list", "click", handlePlannedDateClick);
      listen("campaign-publication-add", "click", handlePublicationClick);
      listen("campaign-publication-list", "click", handlePublicationClick);
      listen("campaign-publication-performance-list", "click", handlePublicationPerformanceClick);
      listen("campaign-publications-refresh-all", "click", refreshAllPublications);
      listen("campaign-creator-list-body", "click", handleListAction);
      if (document?.addEventListener) resources.listen(document, "click", handleAccountPickerClickOutside);
    },

    unbind() {
      lifecycleId += 1;
      resources?.cleanup();
      resources = null;
      campaignController = null;
      relationsController = null;
      creatorsController = null;
      accountsController = null;
      campaignId = "";
      campaign = null;
      relations = [];
      missingPublishLinks = [];
      publicationObservations = new Map();
      campaignPerformance = null;
      publicationRefreshPending = false;
      creators = [];
      creatorsLoaded = false;
      accountCache.clear();
      saving = false;
      deleting = false;
      googleSheetsSyncPending = false;
      closeCreatorForm();
    },
  };

  global.KOLConnectPages.registerPage("campaign-detail", campaignDetailPage);
})(window);
