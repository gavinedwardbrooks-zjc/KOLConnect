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
    appendOverviewItem("平台", campaign?.platform);
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
      row.appendChild(createCell(formatNumber(relation.creator_quote)));
      row.appendChild(createCell(formatNumber(relation.cost)));
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
    count.textContent = `${missingPublishLinks.length} 条`;
    empty.hidden = missingPublishLinks.length !== 0;
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

  async function loadDetail() {
    if (!resources || !campaignId) return;
    const currentLifecycle = lifecycleId;
    campaignController?.abort();
    relationsController?.abort();
    campaignController = resources.createAbortController();
    relationsController = resources.createAbortController();
    setDetailState("loading");

    try {
      const [campaignData, relationsData, publishingData] = await Promise.all([
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
          return { missing_publish_links: [] };
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
      if (!campaign) throw new Error("Campaign 数据不存在。");
      if (isArchived()) closeCreatorForm();
      renderOverview();
      renderRelations();
      renderMissingPublishLinks();
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

  function renderAccountOptions(accounts, selectedId = "") {
    const select = element("campaign-creator-account-id");
    select.replaceChildren();
    appendOption(select, "", accounts.length ? "请选择执行账号" : "该达人暂无可用账号");
    accounts.forEach(account => {
      const platform = account.platform || "未知平台";
      const profile = account.profile_url || account.account_uid || account.account_id || "";
      appendOption(select, String(account.account_id || ""), `${platform} · ${profile}`);
    });
    select.value = String(selectedId || "");
    select.disabled = accounts.length === 0;
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
    element("campaign-creator-quote").value = "";
    element("campaign-creator-cost").value = "";
    element("campaign-creator-publish-links").value = "";
    element("campaign-creator-publish-date").value = "";
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
    assignFormValue("campaign-creator-quote", relation.creator_quote);
    assignFormValue("campaign-creator-cost", relation.cost);
    assignFormValue("campaign-creator-publish-links", parsePublishLinks(relation.publish_links).join("\n"));
    assignFormValue("campaign-creator-publish-date", relation.publish_date);
    assignFormValue("campaign-creator-views", relation.views);
    assignFormValue("campaign-creator-likes", relation.likes);
    assignFormValue("campaign-creator-comments", relation.comments);
    assignFormValue("campaign-creator-roi", relation.roi);
    assignFormValue("campaign-creator-performance-note", relation.performance_note);
    element("campaign-creator-form-card").hidden = false;
    await loadAccounts(relation.creator_id, relation.account_id);
  }

  function showFormError(message) {
    const error = element("campaign-creator-form-error");
    error.textContent = message;
    error.hidden = false;
  }

  function formPayload() {
    return {
      account_id: element("campaign-creator-account-id").value,
      stage: element("campaign-creator-stage").value || "pending_contact",
      creator_quote: element("campaign-creator-quote").value.trim(),
      cost: element("campaign-creator-cost").value.trim(),
      publish_links: parsePublishLinks(element("campaign-creator-publish-links").value),
      publish_date: element("campaign-creator-publish-date").value,
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
    if (!payload.account_id) return showFormError("请选择本次合作使用的执行账号。");
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
      listen("campaign-detail-retry", "click", loadDetail);
      listen("campaign-creator-add-open", "click", openAddForm);
      listen("campaign-creator-form-cancel", "click", closeCreatorForm);
      listen("campaign-creator-form", "submit", saveRelation);
      listen("campaign-creator-id", "change", handleCreatorChange);
      listen("campaign-creator-list-body", "click", handleListAction);
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
      creators = [];
      creatorsLoaded = false;
      accountCache.clear();
      saving = false;
      deleting = false;
      closeCreatorForm();
    },
  };

  global.KOLConnectPages.registerPage("campaign-detail", campaignDetailPage);
})(window);
