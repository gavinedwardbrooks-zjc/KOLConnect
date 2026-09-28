(function registerProductsPage(global) {
  "use strict";

  let resources = null;
  let listController = null;
  let products = [];
  let includeArchived = false;
  let editingProductId = null;
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

  function t(key, values) {
    return getApp().t?.(key, values) || global.KOLConnectI18n?.t(key, values) || key;
  }

  function isArchived(product) {
    return Boolean(String(product?.archived_at || "").trim());
  }

  function formatDate(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat(global.KOLConnectI18n?.getLocale?.() === "en" ? "en-US" : "zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function createCell(value, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = value;
    return cell;
  }

  function createAction(action, productId, label, className = "mini-btn") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.dataset.productAction = action;
    button.dataset.productId = productId;
    button.textContent = label;
    return button;
  }

  function setListState(state, message = "") {
    const loading = element("product-list-loading");
    const error = element("product-list-error");
    const errorMessage = element("product-list-error-message");
    const empty = element("product-list-empty");
    const table = element("product-list-table-wrap");
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

  function renderProducts() {
    const body = element("product-list-body");
    const count = element("product-list-count");
    if (!body || !count) return;
    body.replaceChildren();
    count.textContent = t("productCount", { count: products.length, plural: products.length === 1 ? "" : "s" });

    if (!products.length) {
      setListState("empty");
      return;
    }

    products.forEach(product => {
      const archived = isArchived(product);
      const row = document.createElement("tr");
      row.dataset.productId = String(product.product_id || "");
      row.appendChild(createCell(String(product.name || "--"), "product-name-cell"));
      row.appendChild(createCell(String(product.company_name || "--")));
      row.appendChild(createCell(String(Math.max(0, Number(product.campaigns_count) || 0))));
      row.appendChild(createCell(formatDate(product.created_at)));
      row.appendChild(createCell(formatDate(product.updated_at)));

      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      status.className = "status-pill";
      status.dataset.status = archived ? "archived" : "success";
      status.textContent = archived ? "Archived" : "Active";
      statusCell.appendChild(status);
      row.appendChild(statusCell);

      const actionsCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "product-row-actions";
      if (archived) {
        actions.appendChild(createAction("restore", product.product_id, t("productRestore")));
      } else {
        actions.appendChild(createAction("edit", product.product_id, t("productEdit")));
        actions.appendChild(createAction("archive", product.product_id, t("productArchive"), "mini-btn danger"));
      }
      actionsCell.appendChild(actions);
      row.appendChild(actionsCell);
      body.appendChild(row);
    });
    setListState("loaded");
  }

  function resetForm() {
    editingProductId = null;
    element("product-form-title").textContent = t("productCreate");
    element("product-name").value = "";
    element("product-company-name").value = "";
    element("product-note").value = "";
    element("product-form-error").hidden = true;
    element("product-form-error").textContent = "";
  }

  function closeForm() {
    resetForm();
    element("product-form-card").hidden = true;
  }

  function openCreateForm() {
    resetForm();
    element("product-form-card").hidden = false;
    element("product-name").focus();
  }

  function openEditForm(productId) {
    const product = products.find(item => String(item.product_id) === String(productId));
    if (!product || isArchived(product)) return;
    editingProductId = String(product.product_id);
    element("product-form-title").textContent = t("productEdit");
    element("product-name").value = String(product.name || "");
    element("product-company-name").value = String(product.company_name || "");
    element("product-note").value = String(product.note || "");
    element("product-form-error").hidden = true;
    element("product-form-card").hidden = false;
    element("product-name").focus();
  }

  function showFormError(message) {
    const error = element("product-form-error");
    error.textContent = message;
    error.hidden = false;
  }

  function setSaving(value) {
    saving = value;
    const saveButton = element("product-form-save");
    if (saveButton) {
      saveButton.disabled = value;
      saveButton.textContent = value ? t("productSaving") : t("productSave");
    }
  }

  async function loadProducts() {
    if (!resources) return;
    const currentLifecycle = lifecycleId;
    listController?.abort();
    listController = resources.createAbortController();
    setListState("loading");
    element("product-list-count").textContent = "--";
    const url = includeArchived ? "/api/products?include_archived=true" : "/api/products";
    try {
      const data = await global.KOLConnectAPI.get(url, { signal: listController.signal });
      if (!resources || currentLifecycle !== lifecycleId) return;
      products = Array.isArray(data.products) ? data.products : [];
      renderProducts();
    } catch (error) {
      if (error?.name === "AbortError" || currentLifecycle !== lifecycleId) return;
      products = [];
      element("product-list-count").textContent = t("productCount", { count: 0, plural: "s" });
      setListState("error", error.message || t("productListLoadFailed"));
    }
  }

  async function saveProduct(event) {
    event.preventDefault();
    if (saving || !resources) return;
    const name = element("product-name").value.trim();
    const companyName = element("product-company-name").value.trim();
    const note = element("product-note").value.trim();
    if (!name) return showFormError(t("productNameRequired"));
    if (!companyName) return showFormError(t("productCompanyRequired"));

    setSaving(true);
    try {
      const payload = { name, company_name: companyName, note };
      if (editingProductId) {
        await global.KOLConnectAPI.patch(
          `/api/products/${encodeURIComponent(editingProductId)}`,
          payload,
          { signal: resources.signal },
        );
      } else {
        await global.KOLConnectAPI.post("/api/products", payload, { signal: resources.signal });
      }
      getApp().showSaved(editingProductId ? t("productUpdated") : t("productCreated"));
      closeForm();
      await loadProducts();
    } catch (error) {
      if (error?.name !== "AbortError") showFormError(error.message || t("productSaveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function changeArchiveState(productId, archived) {
    if (mutationInProgress || !resources) return;
    const message = archived
      ? t("productArchiveConfirm")
      : t("productRestoreConfirm");
    if (!global.confirm(message)) return;

    mutationInProgress = true;
    try {
      await global.KOLConnectAPI.patch(
        `/api/products/${encodeURIComponent(productId)}`,
        { archived_at: archived ? new Date().toISOString() : null },
        { signal: resources.signal },
      );
      getApp().showSaved(archived ? t("productArchived") : t("productRestored"));
      if (editingProductId === String(productId)) closeForm();
      await loadProducts();
    } catch (error) {
      if (error?.name !== "AbortError") getApp().showError(error);
    } finally {
      mutationInProgress = false;
    }
  }

  async function handleListAction(event) {
    const button = event.target.closest("[data-product-action]");
    if (!button) return;
    const productId = button.dataset.productId;
    if (button.dataset.productAction === "edit") openEditForm(productId);
    if (button.dataset.productAction === "archive") await changeArchiveState(productId, true);
    if (button.dataset.productAction === "restore") await changeArchiveState(productId, false);
  }

  function listen(id, type, listener) {
    const target = element(id);
    if (target) resources.listen(target, type, listener);
  }

  const productPage = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      lifecycleId += 1;
      closeForm();
      element("product-include-archived").checked = includeArchived;
      await loadProducts();
    },

    bind() {
      listen("product-create-open", "click", openCreateForm);
      listen("product-form-cancel", "click", closeForm);
      listen("product-form", "submit", saveProduct);
      listen("product-list-body", "click", handleListAction);
      listen("product-list-retry", "click", loadProducts);
      listen("product-include-archived", "change", async event => {
        includeArchived = Boolean(event.target.checked);
        await loadProducts();
      });
    },

    unbind() {
      lifecycleId += 1;
      resources?.cleanup();
      resources = null;
      listController = null;
      saving = false;
      mutationInProgress = false;
      closeForm();
    },
  };

  global.KOLConnectPages.registerPage("products", productPage);
})(window);
