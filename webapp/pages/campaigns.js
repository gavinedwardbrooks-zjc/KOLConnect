(function registerCampaignsPage(global) {
  "use strict";

  const STATUS_LABELS = Object.freeze({
    draft: "Draft",
    sourcing: "Sourcing",
    running: "Running",
    completed: "Completed",
    archived: "状态待确认",
  });

  let resources = null;
  let listController = null;
  let productsController = null;
  let campaigns = [];
  let products = [];
  let editingCampaignId = null;
  let saving = false;
  let mutationInProgress = false;
  let lifecycleId = 0;

  function element(id) {
    return document.getElementById(id);
  }

  function getApp() {
    if (!global.KOLConnectApp) throw new Error("KOLConnect application helpers are unavailable.");
    return global.KOLConnectApp;
  }

  function isArchived(campaign) {
    return Boolean(String(campaign?.archived_at || "").trim());
  }

  function createCell(value, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = value;
    return cell;
  }

  function createAction(action, campaignId, label, className = "mini-btn") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.dataset.campaignAction = action;
    button.dataset.campaignId = campaignId;
    button.textContent = label;
    return button;
  }

  function formatBudget(value) {
    if (value === "" || value == null) return "--";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(number);
  }

  function setListState(state, message = "") {
    const loading = element("campaign-list-loading");
    const error = element("campaign-list-error");
    const errorMessage = element("campaign-list-error-message");
    const empty = element("campaign-list-empty");
    const table = element("campaign-list-table-wrap");
    const hasError = state === "error";
    if (loading) loading.hidden = state !== "loading";
    if (error) {
      error.hidden = !hasError;
      error.style.display = hasError ? "" : "none";
    }
    if (errorMessage) errorMessage.textContent = hasError ? message : "";
    if (empty) empty.hidden = state !== "empty";
    if (table) table.hidden = state !== "loaded";
  }

  function renderCampaigns() {
    const body = element("campaign-list-body");
    const count = element("campaign-list-count");
    if (!body || !count) return;
    body.replaceChildren();
    count.textContent = `${campaigns.length} 个 Campaign`;

    if (!campaigns.length) {
      setListState("empty");
      return;
    }

    campaigns.forEach(campaign => {
      const archived = isArchived(campaign);
      const row = document.createElement("tr");
      row.dataset.campaignId = String(campaign.campaign_id || "");
      row.appendChild(createCell(String(campaign.name || "--"), "campaign-name-cell"));
      row.appendChild(createCell(String(campaign.product_name || "--")));
      row.appendChild(createCell(String(Math.max(0, Number(campaign.creators_count) || 0))));

      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      const statusValue = String(campaign.status || "draft");
      status.className = "status-pill";
      status.dataset.status = statusValue;
      status.textContent = STATUS_LABELS[statusValue] || statusValue;
      statusCell.appendChild(status);
      row.appendChild(statusCell);

      const archiveCell = document.createElement("td");
      const archiveStatus = document.createElement("span");
      archiveStatus.className = "status-pill";
      archiveStatus.dataset.status = archived ? "archived" : "active";
      archiveStatus.textContent = archived ? "Archived" : "Active";
      archiveCell.appendChild(archiveStatus);
      row.appendChild(archiveCell);

      row.appendChild(createCell(String(campaign.platform || "--")));
      row.appendChild(createCell(formatBudget(campaign.budget)));
      row.appendChild(createCell(String(campaign.start_date || "--")));
      row.appendChild(createCell(String(campaign.end_date || "--")));
      row.appendChild(createCell(String(campaign.owner || "--")));

      const actionsCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "campaign-row-actions";
      actions.appendChild(createAction("detail", campaign.campaign_id, "查看"));
      if (archived) {
        actions.appendChild(createAction("restore", campaign.campaign_id, "恢复"));
      } else {
        actions.appendChild(createAction("edit", campaign.campaign_id, "编辑"));
        actions.appendChild(createAction("archive", campaign.campaign_id, "归档", "mini-btn danger"));
      }
      actionsCell.appendChild(actions);
      row.appendChild(actionsCell);
      body.appendChild(row);
    });
    setListState("loaded");
  }

  function appendOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }

  function renderProductOptions() {
    const filter = element("campaign-product-filter");
    const formSelect = element("campaign-product-id");
    if (!filter || !formSelect) return;
    const filterValue = filter.value;
    const formValue = formSelect.value;
    filter.replaceChildren();
    formSelect.replaceChildren();
    appendOption(filter, "", "全部产品");
    appendOption(formSelect, "", "请选择产品");
    products.forEach(product => {
      const label = product.company_name
        ? `${product.name || "未命名产品"} · ${product.company_name}`
        : String(product.name || "未命名产品");
      appendOption(filter, String(product.product_id || ""), label);
      appendOption(formSelect, String(product.product_id || ""), label);
    });
    filter.value = filterValue;
    formSelect.value = formValue;
    filter.disabled = products.length === 0;
    element("campaign-create-open").disabled = products.length === 0;
  }

  function showProductsError(message = "") {
    const error = element("campaign-products-error");
    error.textContent = message;
    error.hidden = !message;
  }

  async function loadProducts() {
    if (!resources) return;
    const currentLifecycle = lifecycleId;
    productsController?.abort();
    productsController = resources.createAbortController();
    try {
      const data = await global.KOLConnectAPI.get("/api/products", { signal: productsController.signal });
      if (!resources || currentLifecycle !== lifecycleId) return;
      products = Array.isArray(data.products) ? data.products : [];
      showProductsError("");
      renderProductOptions();
    } catch (error) {
      if (error?.name === "AbortError" || currentLifecycle !== lifecycleId) return;
      products = [];
      renderProductOptions();
      showProductsError(error.message || "产品选项加载失败，暂时无法创建或筛选 Campaign。");
    }
  }

  function campaignListUrl() {
    const params = new URLSearchParams();
    const productId = element("campaign-product-filter")?.value || "";
    const status = element("campaign-status-filter")?.value || "";
    const startDateFrom = element("campaign-start-date-from")?.value || "";
    const startDateTo = element("campaign-start-date-to")?.value || "";
    const includeArchived = Boolean(element("campaign-include-archived")?.checked);
    if (productId) params.set("product_id", productId);
    if (status) params.set("status", status);
    if (startDateFrom) params.set("start_date_from", startDateFrom);
    if (startDateTo) params.set("start_date_to", startDateTo);
    if (includeArchived) params.set("include_archived", "true");
    const query = params.toString();
    return query ? `/api/campaigns?${query}` : "/api/campaigns";
  }

  async function loadCampaigns() {
    if (!resources) return;
    const currentLifecycle = lifecycleId;
    listController?.abort();
    listController = resources.createAbortController();
    setListState("loading");
    element("campaign-list-count").textContent = "--";
    try {
      const data = await global.KOLConnectAPI.get(campaignListUrl(), { signal: listController.signal });
      if (!resources || currentLifecycle !== lifecycleId) return;
      if (!Array.isArray(data.campaigns)) {
        throw new Error("Campaign 列表响应格式异常，请稍后重试。");
      }
      campaigns = data.campaigns;
      renderCampaigns();
    } catch (error) {
      if (error?.name === "AbortError" || currentLifecycle !== lifecycleId) return;
      campaigns = [];
      element("campaign-list-count").textContent = "0 个 Campaign";
      setListState("error", error.message || "Campaign 列表加载失败，请稍后重试。");
    }
  }

  function resetForm() {
    editingCampaignId = null;
    element("campaign-form-title").textContent = "创建 Campaign";
    element("campaign-name").value = "";
    element("campaign-product-id").value = "";
    element("campaign-status").value = "draft";
    element("campaign-platform").value = "";
    element("campaign-country").value = "";
    element("campaign-country").disabled = false;
    element("campaign-country-edit-note").hidden = true;
    element("campaign-budget").value = "";
    element("campaign-start-date").value = "";
    element("campaign-end-date").value = "";
    element("campaign-owner").value = "";
    element("campaign-goal").value = "";
    element("campaign-form-error").hidden = true;
    element("campaign-form-error").textContent = "";
  }

  function closeForm() {
    resetForm();
    element("campaign-form-card").hidden = true;
  }

  function openCreateForm() {
    resetForm();
    element("campaign-form-card").hidden = false;
    element("campaign-name").focus();
  }

  function openEditForm(campaignId) {
    const campaign = campaigns.find(item => String(item.campaign_id) === String(campaignId));
    if (!campaign || isArchived(campaign)) return;
    editingCampaignId = String(campaign.campaign_id);
    element("campaign-form-title").textContent = "编辑 Campaign";
    element("campaign-name").value = String(campaign.name || "");
    element("campaign-product-id").value = String(campaign.product_id || "");
    element("campaign-status").value = String(campaign.status || "draft");
    element("campaign-platform").value = String(campaign.platform || "");
    element("campaign-country").value = String(campaign.country || "");
    element("campaign-country").disabled = true;
    element("campaign-country-edit-note").hidden = false;
    element("campaign-budget").value = campaign.budget == null ? "" : String(campaign.budget);
    element("campaign-start-date").value = String(campaign.start_date || "");
    element("campaign-end-date").value = String(campaign.end_date || "");
    element("campaign-owner").value = String(campaign.owner || "");
    element("campaign-goal").value = String(campaign.goal || "");
    element("campaign-form-error").hidden = true;
    element("campaign-form-card").hidden = false;
    element("campaign-name").focus();
  }

  function showFormError(message) {
    const error = element("campaign-form-error");
    error.textContent = message;
    error.hidden = false;
  }

  function setSaving(value) {
    saving = value;
    const button = element("campaign-form-save");
    button.disabled = value;
    button.textContent = value ? "正在保存..." : "保存 Campaign";
  }

  function campaignPayload() {
    return {
      name: element("campaign-name").value.trim(),
      product_id: element("campaign-product-id").value,
      status: element("campaign-status").value || "draft",
      platform: element("campaign-platform").value,
      budget: element("campaign-budget").value.trim(),
      start_date: element("campaign-start-date").value,
      end_date: element("campaign-end-date").value,
      owner: element("campaign-owner").value.trim(),
      goal: element("campaign-goal").value.trim(),
    };
  }

  async function saveCampaign(event) {
    event.preventDefault();
    if (saving || !resources) return;
    const payload = campaignPayload();
    if (!payload.name) return showFormError("请输入 Campaign 名称。");
    if (!payload.product_id) return showFormError("请选择产品。");

    setSaving(true);
    try {
      if (editingCampaignId) {
        await global.KOLConnectAPI.patch(
          `/api/campaigns/${encodeURIComponent(editingCampaignId)}`,
          payload,
          { signal: resources.signal },
        );
      } else {
        await global.KOLConnectAPI.post(
          "/api/campaigns",
          { ...payload, country: element("campaign-country").value.trim() },
          { signal: resources.signal },
        );
      }
      getApp().showSaved(editingCampaignId ? "Campaign 已更新。" : "Campaign 已创建。");
      closeForm();
      await loadCampaigns();
    } catch (error) {
      if (error?.name !== "AbortError") showFormError(error.message || "Campaign 保存失败。");
    } finally {
      setSaving(false);
    }
  }

  async function changeArchiveState(campaignId, archived) {
    if (mutationInProgress || !resources) return;
    const message = archived
      ? "归档后，该 Campaign 将从默认列表隐藏，已有达人合作数据不会删除。"
      : "恢复后，该 Campaign 将重新显示，原有业务状态和达人合作数据保持不变。";
    if (!global.confirm(message)) return;

    mutationInProgress = true;
    try {
      await global.KOLConnectAPI.patch(
        `/api/campaigns/${encodeURIComponent(campaignId)}`,
        { archived_at: archived ? new Date().toISOString() : null },
        { signal: resources.signal },
      );
      getApp().showSaved(archived ? "Campaign 已归档。" : "Campaign 已恢复，业务状态未改变。");
      if (editingCampaignId === String(campaignId)) closeForm();
      await loadCampaigns();
    } catch (error) {
      if (error?.name !== "AbortError") getApp().showError(error);
    } finally {
      mutationInProgress = false;
    }
  }

  async function handleListAction(event) {
    const button = event.target.closest("[data-campaign-action]");
    if (!button) return;
    const campaignId = button.dataset.campaignId;
    if (button.dataset.campaignAction === "detail") {
      await global.KOLConnectPages.navigate("campaign-detail", { campaignId });
      return;
    }
    if (button.dataset.campaignAction === "edit") openEditForm(campaignId);
    if (button.dataset.campaignAction === "archive") await changeArchiveState(campaignId, true);
    if (button.dataset.campaignAction === "restore") await changeArchiveState(campaignId, false);
  }

  function listen(id, type, listener) {
    const target = element(id);
    if (target) resources.listen(target, type, listener);
  }

  const campaignsPage = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      lifecycleId += 1;
      closeForm();
      await Promise.all([loadProducts(), loadCampaigns()]);
    },

    bind() {
      listen("campaign-create-open", "click", openCreateForm);
      listen("campaign-form-cancel", "click", closeForm);
      listen("campaign-form", "submit", saveCampaign);
      listen("campaign-list-body", "click", handleListAction);
      listen("campaign-list-retry", "click", loadCampaigns);
      listen("campaign-product-filter", "change", loadCampaigns);
      listen("campaign-status-filter", "change", loadCampaigns);
      listen("campaign-include-archived", "change", loadCampaigns);
      listen("campaign-date-filter-apply", "click", loadCampaigns);
    },

    unbind() {
      lifecycleId += 1;
      resources?.cleanup();
      resources = null;
      listController = null;
      productsController = null;
      saving = false;
      mutationInProgress = false;
      closeForm();
    },
  };

  global.KOLConnectPages.registerPage("campaigns", campaignsPage);
})(window);
