(function registerCreatorLibraryPage(global) {
  "use strict";

  function t(key, params) {
    return global.KOLConnectApp?.t?.(key, params)
      || global.KOLConnectI18n?.t?.(key, params)
      || key;
  }

  function statusLabel(status) {
    const keys = {
      discovered: "creatorStatusDiscovered",
      contacted: "creatorStatusContacted",
      negotiating: "creatorStatusNegotiating",
      cooperating: "creatorStatusCooperating",
      completed: "creatorStatusCompleted",
      rejected: "creatorStatusRejected",
    };
    return t(keys[status] || "creatorStatusDiscovered");
  }

  function createCreatorCampaignModal(context) {
    let creator = null;
    let campaigns = [];
    let accounts = [];
    let requestId = 0;
    let campaignsController = null;
    let detailController = null;
    let submitController = null;
    let onCreated = null;
    let bound = false;

    function modalElement(id) {
      return document.getElementById(id);
    }

    function setMessage(message, tone = "") {
      const target = modalElement("creator-campaign-modal-message");
      if (!target) return;
      target.hidden = !message;
      target.textContent = message || "";
      target.dataset.tone = tone;
    }

    function setSubmitState(disabled, label = t("creatorLibraryConfirmAdd")) {
      const button = modalElement("creator-campaign-submit");
      if (!button) return;
      button.disabled = disabled;
      button.textContent = label;
    }

    function setSelectOptions(select, options, placeholder) {
      if (!select) return;
      select.replaceChildren(new Option(placeholder, ""), ...options);
      select.value = "";
    }

    function selectedCampaign() {
      const campaignId = String(modalElement("creator-campaign-select")?.value || "");
      return campaigns.find(item => String(item.campaign_id || "") === campaignId) || null;
    }

    function accountLabel(account, preferredPlatform) {
      const platform = String(account.platform || t("creatorLibraryUnspecifiedPlatform"));
      const identity = account.username || account.profile_url || account.account_uid || account.account_id;
      const preferred = preferredPlatform && platform.toLowerCase() === preferredPlatform.toLowerCase();
      return `${platform} · ${identity || t("creatorLibraryUnnamedAccount")}${preferred ? t("creatorLibraryCampaignPlatformMatch") : ""}`;
    }

    function renderAccounts() {
      const select = modalElement("creator-campaign-account-select");
      const hint = modalElement("creator-campaign-account-hint");
      const platform = String(selectedCampaign()?.platform || "").trim();
      const sorted = [...accounts].sort((left, right) => {
        const leftMatch = platform && String(left.platform || "").toLowerCase() === platform.toLowerCase();
        const rightMatch = platform && String(right.platform || "").toLowerCase() === platform.toLowerCase();
        return Number(rightMatch) - Number(leftMatch);
      });
      const options = sorted.map(account => new Option(
        accountLabel(account, platform),
        String(account.account_id || ""),
      ));
      setSelectOptions(select, options, accounts.length ? t("creatorLibraryChooseAccount") : t("creatorLibraryNoAccounts"));
      if (accounts.length === 1) select.value = String(accounts[0].account_id || "");
      select.disabled = accounts.length === 0;
      if (hint) {
        hint.textContent = accounts.length === 0
          ? t("creatorLibraryNoAccountsHint")
          : accounts.length === 1
            ? t("creatorLibraryOneAccountHint")
            : platform
              ? t("creatorLibraryMatchingAccountHint", { platform })
              : t("creatorLibraryMultipleAccountsHint");
      }
      setSubmitState(accounts.length === 0 || campaigns.length === 0);
    }

    function renderCampaigns() {
      const select = modalElement("creator-campaign-select");
      const options = campaigns.map(campaign => new Option(
        [campaign.name, campaign.product_name, campaign.platform].filter(Boolean).join(" · "),
        String(campaign.campaign_id || ""),
      ));
      setSelectOptions(select, options, campaigns.length ? t("creatorLibraryChooseCampaign") : t("creatorLibraryNoCampaigns"));
      select.disabled = campaigns.length === 0;
      renderAccounts();
      if (!campaigns.length) setMessage(t("creatorLibraryNoCampaignsMessage"), "warning");
    }

    function close() {
      requestId += 1;
      campaignsController?.abort();
      detailController?.abort();
      submitController?.abort();
      campaignsController = null;
      detailController = null;
      submitController = null;
      creator = null;
      campaigns = [];
      accounts = [];
      onCreated = null;
      const modal = modalElement("creator-campaign-modal");
      if (modal) modal.hidden = true;
      setMessage("");
      setSelectOptions(modalElement("creator-campaign-select"), [], t("creatorLibraryChooseCampaign"));
      setSelectOptions(modalElement("creator-campaign-account-select"), [], t("creatorLibraryChooseAccount"));
      setSubmitState(true);
    }

    async function open(record, options = {}) {
      const creatorId = String(record?.creator_id || record?.analysis_id || "").trim();
      if (!creatorId) throw new Error(t("creatorLibraryMissingCreator"));
      close();
      const currentRequest = ++requestId;
      creator = { ...record, creator_id: creatorId };
      onCreated = typeof options.onCreated === "function" ? options.onCreated : null;
      const modal = modalElement("creator-campaign-modal");
      if (!modal) throw new Error(t("creatorLibraryCampaignModalMissing"));
      modal.hidden = false;
      modalElement("creator-campaign-creator-name").textContent = record.creator_name || t("unnamedCreator");
      modalElement("creator-campaign-agency-name").textContent = record.agency_name || "--";
      setMessage(t("creatorLibraryLoadCampaignFailed"), "loading");
      setSubmitState(true, t("creatorLibraryLoading"));
      campaignsController = context.resources.createAbortController();
      detailController = context.resources.createAbortController();
      try {
        const [campaignData, detailData] = await Promise.all([
          context.api.get("/api/campaigns", { signal: campaignsController.signal }),
          context.api.get(`/api/creator-library/${encodeURIComponent(creatorId)}`, {
            signal: detailController.signal,
          }),
        ]);
        if (currentRequest !== requestId || context.resources.signal.aborted) return;
        campaigns = Array.isArray(campaignData.campaigns) ? campaignData.campaigns : [];
        accounts = Array.isArray(detailData.accounts)
          ? detailData.accounts.filter(account => String(account.account_id || "").trim())
          : [];
        const detailRecord = detailData.record || {};
        modalElement("creator-campaign-creator-name").textContent = detailRecord.creator_name
          || creator.creator_name
          || t("unnamedCreator");
        modalElement("creator-campaign-agency-name").textContent = detailRecord.agency_name
          || creator.agency_name
          || "--";
        setMessage("");
        setSubmitState(false);
        renderCampaigns();
      } catch (error) {
        if (error?.name === "AbortError" || currentRequest !== requestId) return;
        setMessage(error.message || t("creatorLibraryLoadCampaignFailed"), "error");
        setSubmitState(true);
      }
    }

    async function submit(event) {
      event.preventDefault();
      if (!creator) return;
      const campaignId = String(modalElement("creator-campaign-select")?.value || "").trim();
      const accountId = String(modalElement("creator-campaign-account-select")?.value || "").trim();
      if (!campaignId) {
        setMessage(t("creatorLibraryCampaignSelectedRequired"), "warning");
        return;
      }
      if (!accounts.length) {
        setMessage(t("creatorLibraryNoAccountsHint"), "warning");
        return;
      }
      if (!accountId) {
        setMessage(t("creatorLibraryAccountSelectedRequired"), "warning");
        return;
      }
      submitController?.abort();
      submitController = context.resources.createAbortController();
      setMessage("");
      setSubmitState(true, t("creatorLibraryJoining"));
      try {
        const result = await context.api.post(
          `/api/campaigns/${encodeURIComponent(campaignId)}/creators`,
          { creator_id: creator.creator_id, account_id: accountId },
          { signal: submitController.signal },
        );
        const callback = onCreated;
        const creatorName = creator.creator_name || t("unnamedCreator");
        close();
        if (callback) await callback(result.campaign_creator);
        context.ui.showSaved(t("creatorLibraryCampaignAdded", { creator: creatorName }));
      } catch (error) {
        if (error?.name === "AbortError") return;
        setMessage(
          error?.status === 409 ? t("creatorLibraryCampaignAlreadyAdded") : (error.message || t("creatorLibraryCampaignAddFailed")),
          "error",
        );
        setSubmitState(false);
      }
    }

    function bind() {
      if (bound) return;
      bound = true;
      const modal = modalElement("creator-campaign-modal");
      context.resources.listen(modalElement("creator-campaign-modal-close"), "click", close);
      context.resources.listen(modalElement("creator-campaign-modal-cancel"), "click", close);
      context.resources.listen(modalElement("creator-campaign-select"), "change", renderAccounts);
      context.resources.listen(modalElement("creator-campaign-form"), "submit", submit);
      context.resources.listen(modal, "click", event => {
        if (event.target === modal) close();
      });
      if (typeof document.addEventListener === "function") {
        context.resources.listen(document, "keydown", event => {
          if (event.key === "Escape" && !modal?.hidden) close();
        });
      }
    }

    function destroy() {
      close();
      bound = false;
    }

    return Object.freeze({ open, bind, close, destroy });
  }

  global.KOLConnectCreatorCampaignModal = Object.freeze({
    create: createCreatorCampaignModal,
  });

  function createCreatorDeleteModal(context) {
    const IMPACT_LABEL_KEYS = Object.freeze({
      creators: "creatorDeleteCreators",
      creator_accounts: "creatorDeleteAccounts",
      videos: "creatorDeleteVideos",
      insights: "Insight",
      analysis_data: "Analysis",
      creator_snapshots: "Creator Snapshots",
      video_snapshots: "Video Snapshots",
      campaign_creators: "creatorDeleteCampaignRelations",
      follow_up_logs: "creatorDeleteFollowUpLogs",
      task_artifacts: "creatorDeleteTaskArtifacts",
      data_protection: "creatorDeleteProtectionRecords",
      legacy_sources: "creatorDeleteLegacySources",
      cooperations: "creatorDeleteCooperations",
      embedded_analysis_references: "creatorDeleteEmbeddedReferences",
      unmapped_task_artifacts: "creatorDeleteUnmappedArtifacts",
    });
    let creator = null;
    let impact = null;
    let loadingController = null;
    let deleteController = null;
    let requestId = 0;
    let submitting = false;
    let onDeleted = null;
    let bound = false;

    function modalElement(id) {
      return document.getElementById(id);
    }

    function setMessage(message, tone = "") {
      const target = modalElement("creator-delete-message");
      if (!target) return;
      target.hidden = !message;
      target.textContent = message || "";
      target.dataset.tone = tone;
    }

    function setButtons() {
      const confirm = modalElement("creator-delete-confirm");
      const refresh = modalElement("creator-delete-refresh");
      if (confirm) {
        confirm.disabled = submitting || !impact?.can_delete || !impact?.preview_fingerprint;
        confirm.textContent = submitting ? t("creatorDeleteSubmitting") : t("creatorDeleteConfirm");
      }
      if (refresh) refresh.disabled = submitting || !creator;
    }

    function impactCount(value) {
      if (value && typeof value === "object") return Number(value.total) || 0;
      return Number(value) || 0;
    }

    function renderImpact() {
      const list = modalElement("creator-delete-impact-list");
      const blockers = modalElement("creator-delete-blockers");
      if (list) {
        list.replaceChildren();
        const values = impact?.impact && typeof impact.impact === "object" ? impact.impact : {};
        Object.entries(IMPACT_LABEL_KEYS).forEach(([key, labelKey]) => {
          if (!Object.prototype.hasOwnProperty.call(values, key)) return;
          const item = document.createElement("li");
          const name = document.createElement("span");
          const count = document.createElement("strong");
          name.textContent = t(labelKey);
          count.textContent = String(impactCount(values[key]));
          item.append(name, count);
          list.appendChild(item);
        });
      }
      if (blockers) {
        blockers.replaceChildren();
        (impact?.blockers || []).forEach(blocker => {
          const item = document.createElement("li");
          item.textContent = blocker.message || blocker.code || t("creatorDeleteUnknownBlocker");
          blockers.appendChild(item);
        });
        blockers.hidden = !impact?.blockers?.length;
      }
      const state = modalElement("creator-delete-state");
      if (state) {
        state.textContent = impact?.can_delete
          ? t("creatorDeleteReady")
          : t("creatorDeleteBlocked");
        state.dataset.tone = impact?.can_delete ? "ready" : "blocked";
      }
      setButtons();
    }

    function close() {
      requestId += 1;
      loadingController?.abort();
      deleteController?.abort();
      loadingController = null;
      deleteController = null;
      creator = null;
      impact = null;
      submitting = false;
      onDeleted = null;
      const modal = modalElement("creator-delete-modal");
      if (modal) modal.hidden = true;
      setMessage("");
      modalElement("creator-delete-impact-list")?.replaceChildren();
      modalElement("creator-delete-blockers")?.replaceChildren();
      setButtons();
    }

    async function loadImpact(message = "") {
      if (!creator) return;
      loadingController?.abort();
      loadingController = context.resources.createAbortController();
      const currentRequest = ++requestId;
      impact = null;
      setMessage(message || t("creatorDeleteChecking"), message ? "warning" : "loading");
      setButtons();
      try {
        const result = await context.api.getCreatorDeleteImpact(
          creator.creator_id,
          { signal: loadingController.signal },
        );
        if (currentRequest !== requestId || context.resources.signal.aborted) return;
        impact = result;
        renderImpact();
        if (!message) setMessage("");
      } catch (error) {
        if (error?.name === "AbortError" || currentRequest !== requestId) return;
        setMessage(error.message || t("creatorDeleteLoadFailed"), "error");
        setButtons();
      }
    }

    async function open(record, options = {}) {
      const creatorId = String(record?.creator_id || record?.analysis_id || "").trim();
      if (!creatorId) throw new Error(t("creatorDeleteMissingCreator"));
      close();
      creator = { ...record, creator_id: creatorId };
      onDeleted = typeof options.onDeleted === "function" ? options.onDeleted : null;
      const modal = modalElement("creator-delete-modal");
      if (!modal) throw new Error(t("creatorDeleteModalMissing"));
      modal.hidden = false;
      modalElement("creator-delete-creator-name").textContent = record.creator_name || t("unnamedCreator");
      await loadImpact();
    }

    async function confirmDelete() {
      if (submitting || !creator || !impact?.can_delete || !impact?.preview_fingerprint) return;
      submitting = true;
      setMessage("");
      setButtons();
      deleteController?.abort();
      deleteController = context.resources.createAbortController();
      try {
        await context.api.deleteCreator(
          creator.creator_id,
          { confirm: true, preview_fingerprint: impact.preview_fingerprint },
          { signal: deleteController.signal },
        );
        const callback = onDeleted;
        close();
        if (callback) await callback();
        context.ui.showSaved(t("creatorDeleteSuccess"));
      } catch (error) {
        if (error?.name === "AbortError") return;
        submitting = false;
        const code = error?.responseData?.error || error?.message;
        if (code === "DELETE_PREVIEW_STALE") {
          await loadImpact(t("creatorDeleteStale"));
        } else if (code === "DELETE_BLOCKED") {
          await loadImpact(t("creatorDeleteNewBlocker"));
        } else if (code === "SHARED_STORAGE_LOCK_TIMEOUT") {
          impact = null;
          setMessage(t("creatorDeleteStorageLocked"), "warning");
          setButtons();
        } else if (code === "CREATOR_NOT_FOUND") {
          const callback = onDeleted;
          close();
          if (callback) await callback();
          context.ui.showSaved(t("creatorDeleteNotFound"));
        } else {
          impact = null;
          setMessage(t("creatorDeleteFailed"), "error");
          setButtons();
        }
      }
    }

    function bind() {
      if (bound) return;
      bound = true;
      const modal = modalElement("creator-delete-modal");
      context.resources.listen(modalElement("creator-delete-close"), "click", close);
      context.resources.listen(modalElement("creator-delete-cancel"), "click", close);
      context.resources.listen(modalElement("creator-delete-refresh"), "click", () => loadImpact());
      context.resources.listen(modalElement("creator-delete-confirm"), "click", confirmDelete);
      context.resources.listen(modal, "click", event => {
        if (event.target === modal && !submitting) close();
      });
    }

    function destroy() {
      close();
      bound = false;
    }

    return Object.freeze({ open, bind, close, destroy });
  }

  global.KOLConnectCreatorDeleteModal = Object.freeze({
    create: createCreatorDeleteModal,
  });

  let pageContext = null;
  let listController = null;
  let campaignModal = null;
  let deleteModal = null;
  let mergeModal = null;
  let lifecycleId = 0;
  let filterRequestId = 0;
  const VIEW_MODE_STORAGE_KEY = "creator_library_view_mode";
  const PAGE_SIZES = Object.freeze({ card: [12, 24, 48], table: [25, 50, 100] });
  const DEFAULT_PAGE_SIZE = Object.freeze({ card: 24, table: 50 });
  const XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  const IMPORT_ERROR_KEYS = Object.freeze({
    MISSING_REQUIRED_FIELD: "creatorImportMissingRequired",
    INVALID_PLATFORM: "creatorImportInvalidPlatform",
    INVALID_PROFILE_URL: "creatorImportInvalidProfileUrl",
    DUPLICATE_IN_FILE: "creatorImportDuplicateInFile",
    UNKNOWN_AGENCY: "creatorImportUnknownAgency",
  });

  function element(id) {
    return document.getElementById(id);
  }

  function libraryState() {
    return pageContext.state.creatorLibrary;
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

  function formatTrend(change) {
    if (!change || change.status === "no_history") return t("creatorImportNoHistory");
    if (change.status !== "available" || change.delta === null || change.delta === undefined) return "--";
    const amount = formatMetric(Math.abs(Number(change.delta)));
    if (change.direction === "growth") return t("creatorTrendGrowth", { amount });
    if (change.direction === "decline") return t("creatorTrendDecline", { amount });
    return t("creatorTrendNoChange");
  }

  function renderOptions(id, values, label) {
    const select = element(id);
    if (!select) return;
    const selected = select.value;
    select.replaceChildren(new Option(label, ""));
    [...new Set(values.filter(Boolean))].sort().forEach(value => {
      select.add(new Option(value, value));
    });
    select.value = [...select.options].some(option => option.value === selected) ? selected : "";
  }

  function valueOf(id, fallback = "") {
    const target = element(id);
    return target ? (target.value ?? fallback) : fallback;
  }

  function readFilters() {
    return {
      search: valueOf("creator-library-search").trim(),
      country: valueOf("creator-library-country"),
      language: valueOf("creator-library-language"),
      content_category: valueOf("creator-library-category"),
      agency_id: valueOf("creator-library-agency"),
      tag: valueOf("creator-library-tag"),
      ai_tag: valueOf("creator-library-ai-tag"),
      followers_min: valueOf("creator-library-followers-min").trim(),
      followers_max: valueOf("creator-library-followers-max").trim(),
      insight_level: valueOf("creator-library-level"),
      status: valueOf("creator-library-status"),
    };
  }

  function renderPageSizeOptions() {
    const state = libraryState();
    const select = element("creator-library-page-size");
    if (!select) return;
    const sizes = PAGE_SIZES[state.viewMode];
    if (!sizes.includes(state.pageSize)) state.pageSize = DEFAULT_PAGE_SIZE[state.viewMode];
    select.replaceChildren(...sizes.map(size => new Option(String(size), String(size))));
    select.value = String(state.pageSize);
  }

  function createPageButton(label, page, disabled = false, active = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.dataset.creatorPage = String(page);
    button.disabled = disabled;
    button.classList.toggle("active", active);
    return button;
  }

  function visiblePageNumbers(current, pages) {
    if (pages <= 7) return Array.from({ length: pages }, (_value, index) => index + 1);
    return [...new Set([1, 2, current - 1, current, current + 1, pages - 1, pages])]
      .filter(page => page >= 1 && page <= pages)
      .sort((left, right) => left - right);
  }

  function renderPagination() {
    const state = libraryState();
    const pagination = element("creator-library-pagination");
    const summary = element("creator-library-page-summary");
    const buttons = element("creator-library-page-buttons");
    if (!pagination || !summary || !buttons) return;
    pagination.hidden = state.total === 0;
    buttons.replaceChildren();
    if (!state.total) return;

    const start = (state.page - 1) * state.pageSize + 1;
    const end = Math.min(start + state.records.length - 1, state.total);
    summary.textContent = t("creatorLibraryPageSummary", { start, end, total: state.total });
    buttons.appendChild(createPageButton(t("creatorLibraryPrevious"), state.page - 1, state.page <= 1));
    const pageNumbers = visiblePageNumbers(state.page, state.pages);
    pageNumbers.forEach((page, index) => {
      if (index > 0 && page - pageNumbers[index - 1] > 1) {
        const gap = document.createElement("span");
        gap.textContent = "…";
        buttons.appendChild(gap);
      }
      buttons.appendChild(createPageButton(String(page), page, false, page === state.page));
    });
    buttons.appendChild(createPageButton(t("creatorLibraryNext"), state.page + 1, state.page >= state.pages));
  }

  function createAction(label, action, creatorId, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.dataset.creatorAction = action;
    button.dataset.creatorId = creatorId;
    button.textContent = label;
    return button;
  }

  function recordId(record) {
    return String(record?.creator_id || record?.analysis_id || "");
  }

  function displayCreatorName(record) {
    const name = String(record?.creator_name || "").trim();
    if (name) return name;
    const username = String(record?.account_username || "").trim();
    return username ? (username.startsWith("@") ? username : `@${username}`) : t("unnamedCreator");
  }

  function selectedCreatorIds() {
    return libraryState().selectedCreatorIds instanceof Set
      ? libraryState().selectedCreatorIds
      : new Set();
  }

  function updateSelectionControls() {
    const state = libraryState();
    const selected = selectedCreatorIds();
    const currentIds = state.records.map(recordId).filter(Boolean);
    const selectAll = element("creator-library-select-all");
    const selectedCount = element("creator-library-selected-count");
    const exportButton = element("creator-library-export");
    const batchCampaignButton = element("creator-library-batch-campaign");
    if (selectAll) {
      selectAll.checked = currentIds.length > 0 && currentIds.every(id => selected.has(id));
      selectAll.indeterminate = currentIds.some(id => selected.has(id)) && !selectAll.checked;
      selectAll.disabled = currentIds.length === 0;
    }
    if (selectedCount) selectedCount.textContent = t("creatorLibrarySelectedCount", { count: selected.size });
    if (exportButton) {
      exportButton.disabled = selected.size === 0;
      exportButton.textContent = selected.size ? t("creatorLibraryExportSelectedCount", { count: selected.size }) : t("creatorLibraryExportSelected");
    }
    if (batchCampaignButton) {
      batchCampaignButton.disabled = selected.size === 0 || Boolean(state.batchCampaignSubmitting);
      batchCampaignButton.textContent = selected.size
        ? t("creatorLibraryCampaignSelectedCount", { count: selected.size })
        : t("creatorLibraryChooseCampaign");
    }
  }

  function createSelectionControl(creatorId) {
    const label = document.createElement("label");
    label.className = "creator-card-select";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.ariaLabel = t("creatorLibrarySelectCreator");
    input.dataset.creatorSelectId = creatorId;
    input.checked = selectedCreatorIds().has(creatorId);
    label.append(input);
    return label;
  }

  function createCardMetadata(label, value, kind) {
    if (value === null || value === undefined || String(value).trim() === "") return null;
    const metadata = document.createElement("span");
    metadata.className = "creator-card-metadata";
    metadata.dataset.creatorMetadata = kind;
    metadata.textContent = `${label} ${String(value).trim()}`;
    return metadata;
  }

  function insightLabel(value) {
    const insight = String(value || "insufficient").trim();
    return insight === "insufficient" ? t("creatorLibraryInsufficientData") : insight;
  }

  function renderCards(records) {
    const cards = element("creator-library-cards");
    cards.replaceChildren();
    records.forEach(record => {
      const creatorId = recordId(record);
      const archived = Boolean(record.archived_at);
      const card = document.createElement("article");
      card.className = "creator-card";

      const identity = document.createElement("div");
      identity.className = "creator-card-identity";
      const avatar = document.createElement("div");
      avatar.className = `creator-card-avatar platform-${String(record.platform || "other").toLowerCase()}`;
      avatar.textContent = String(displayCreatorName(record) || record.platform || "K").trim().slice(0, 1).toUpperCase();
      const identityText = document.createElement("div");
      const title = document.createElement("h2");
      title.textContent = displayCreatorName(record);
      const subtitle = document.createElement("p");
      subtitle.textContent = record.platform || t("creatorLibraryUnspecifiedPlatform");
      identityText.append(title, subtitle);
      identity.append(avatar, identityText);

      const metadata = document.createElement("div");
      metadata.className = "creator-card-metadata-list";
      [
        createCardMetadata(t("creatorLibraryCountry"), record.country, "country"),
        createCardMetadata(t("creatorLibraryLanguage"), record.language, "language"),
        createCardMetadata(t("creatorLibraryCategory"), record.content_category, "content-category"),
        createCardMetadata(t("creatorLibraryEmail"), record.account_email, "email"),
      ].filter(Boolean).forEach(item => metadata.appendChild(item));

      const tags = document.createElement("div");
      tags.className = "creator-card-tags";
      [
        insightLabel(record.insight_level),
        statusLabel(record.status),
      ].filter(Boolean).forEach((label, index) => {
        const tag = document.createElement("span");
        tag.className = index === 0 ? "creator-card-level" : "creator-card-tag";
        tag.textContent = label;
        tags.appendChild(tag);
      });

      const metrics = document.createElement("div");
      metrics.className = "creator-card-metrics";
      [
        [t("creatorLibraryFollowers"), record.followers || "--"],
        [t("creatorLibraryAverageViews"), formatMetric(record.average_views)],
      ].forEach(([label, value]) => {
        const metric = document.createElement("div");
        const metricLabel = document.createElement("span");
        const metricValue = document.createElement("strong");
        metricLabel.textContent = label;
        metricValue.textContent = value;
        metric.append(metricLabel, metricValue);
        metrics.appendChild(metric);
      });

      const actions = document.createElement("div");
      actions.className = "creator-card-actions";
      const primaryActions = document.createElement("div");
      primaryActions.className = "creator-card-primary-actions";
      primaryActions.appendChild(createAction(t("creatorLibraryViewCreator"), "detail", creatorId, "soft-btn creator-card-action"));
      if (archived) {
        primaryActions.appendChild(createAction(t("creatorLibraryRestoreCreator"), "restore", creatorId, "primary-btn creator-card-action"));
      } else {
        primaryActions.append(
          createAction(t("creatorLibraryChooseCampaign"), "campaign", creatorId, "primary-btn creator-card-action"),
        );
      }
      const moreActions = document.createElement("details");
      moreActions.className = "creator-card-more";
      const moreToggle = document.createElement("summary");
      moreToggle.textContent = t("creatorLibraryMore");
      const moreMenu = document.createElement("div");
      moreMenu.className = "creator-card-more-menu";
      if (!archived) {
        moreMenu.appendChild(createAction(t("creatorLibraryArchiveCreator"), "archive", creatorId, "soft-btn creator-card-action"));
      }
      moreMenu.appendChild(createAction(t("creatorLibraryMergeCreator"), "merge", creatorId, "soft-btn creator-card-action"));
      moreMenu.appendChild(createAction(t("creatorLibraryDeleteCreator"), "delete", creatorId, "soft-btn danger creator-card-action"));
      moreActions.append(moreToggle, moreMenu);
      actions.append(primaryActions, moreActions);
      card.append(createSelectionControl(creatorId), identity, metadata, tags, metrics, actions);
      cards.appendChild(card);
    });
  }

  function renderTable(records) {
    const body = element("creator-library-body");
    body.replaceChildren();
    records.forEach(record => {
      const creatorId = recordId(record);
      const archived = Boolean(record.archived_at);
      const row = document.createElement("tr");
      const selectionCell = document.createElement("td");
      selectionCell.appendChild(createSelectionControl(creatorId));
      row.appendChild(selectionCell);
      const values = [
        displayCreatorName(record),
        record.platform || "--",
        "link",
        record.account_email || "--",
        record.followers || "--",
        record.content_category || "--",
        record.agency_name || "--",
        record.insight_level || "insufficient",
        formatMetric(record.average_views),
        formatMetric(record.median_views),
        formatTrend(record.trend?.changes?.followers),
        formatTrend(record.trend?.changes?.median_views),
        formatTrend(record.trend?.changes?.creator_score),
        formatTime(record.last_analysis_time || record.analysis_time),
        formatTime(record.data_updated_at),
      ];
      values.forEach(value => {
        const cell = document.createElement("td");
        if (value === "link") {
          const link = document.createElement("a");
          link.href = record.profile_url || "#";
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = record.profile_url || "--";
          cell.appendChild(link);
        } else {
          cell.textContent = value;
        }
        row.appendChild(cell);
      });

      const statusCell = document.createElement("td");
      if (archived) {
        const archivedLabel = document.createElement("span");
        archivedLabel.className = "status-pill";
        archivedLabel.dataset.status = "archived";
        archivedLabel.textContent = t("creatorLibraryArchived");
        statusCell.appendChild(archivedLabel);
      } else {
        const statusSelect = document.createElement("select");
        statusSelect.dataset.creatorStatusId = creatorId;
        ["discovered", "contacted", "negotiating", "cooperating", "completed", "rejected"].forEach(value => {
          statusSelect.add(new Option(statusLabel(value), value, false, value === record.status));
        });
        statusCell.appendChild(statusSelect);
      }
      row.appendChild(statusCell);

      const actions = document.createElement("td");
      actions.appendChild(createAction(t("creatorLibraryViewAnalysis"), "detail", creatorId, "soft-btn compact-btn"));
      if (archived) {
        actions.appendChild(createAction(t("creatorLibraryRestore"), "restore", creatorId, "soft-btn compact-btn"));
      } else {
        actions.append(
          createAction(t("creatorLibraryChooseCampaign"), "campaign", creatorId, "soft-btn compact-btn"),
          createAction(t("creatorLibraryCreateTask"), "task", creatorId, "primary-btn compact-btn"),
          createAction(t("creatorLibraryArchive"), "archive", creatorId, "soft-btn compact-btn"),
        );
      }
      actions.appendChild(createAction(t("creatorLibraryMergeCreator"), "merge", creatorId, "soft-btn compact-btn"));
      actions.appendChild(createAction(t("creatorLibraryDeleteCreator"), "delete", creatorId, "soft-btn danger compact-btn"));
      row.appendChild(actions);
      body.appendChild(row);
    });
  }

  function render() {
    const state = libraryState();
    const body = element("creator-library-body");
    const empty = element("creator-library-empty");
    const cards = element("creator-library-cards");
    const tableWrap = element("creator-library-table-wrap");
    if (!body || !empty || !cards || !tableWrap) return;

    const options = state.filterOptions || {};
    renderOptions("creator-library-category", options.content_category || [], t("creatorLibraryAllContentCategories"));
    renderOptions("creator-library-country", options.country || [], t("creatorLibraryAllCountries"));
    renderOptions("creator-library-language", options.language || [], t("creatorLibraryAllLanguages"));
    renderOptions("creator-library-tag", options.tag || [], t("creatorLibraryAllTags"));
    renderOptions("creator-library-ai-tag", options.ai_tag || [], t("creatorLibraryAllAiTags"));
    const records = state.records;
    empty.hidden = records.length > 0;
    cards.hidden = state.viewMode !== "card" || records.length === 0;
    tableWrap.hidden = state.viewMode !== "table" || records.length === 0;
    element("creator-library-card-view").classList.toggle("active", state.viewMode === "card");
    element("creator-library-table-view").classList.toggle("active", state.viewMode === "table");
    cards.replaceChildren();
    body.replaceChildren();
    if (state.viewMode === "card") renderCards(records);
    else renderTable(records);
    updateSelectionControls();
    renderPagination();
  }

  async function loadRecords() {
    const currentLifecycle = lifecycleId;
    listController?.abort();
    listController = pageContext.resources.createAbortController();
    const state = libraryState();
    const includeArchived = state.filters.status === "archived";
    const query = [
      `page=${state.page}`,
      `page_size=${state.pageSize}`,
      `sort=${encodeURIComponent(state.sort)}`,
      `order=${encodeURIComponent(state.order)}`,
    ];
    if (includeArchived) query.push("include_archived=true");
    Object.entries(state.filters).forEach(([key, value]) => {
      if (value) query.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
    });
    const url = `/api/creator-library?${query.join("&")}`;
    const data = await pageContext.api.get(url, { signal: listController.signal });
    if (!pageContext || currentLifecycle !== lifecycleId) return;
    state.total = Number(data.total) || 0;
    state.pages = Number(data.pages) || 0;
    if (state.pages > 0 && state.page > state.pages) {
      state.page = state.pages;
      return loadRecords();
    }
    state.page = Number(data.page) || state.page;
    state.pageSize = Number(data.page_size) || state.pageSize;
    state.filterOptions = data.filter_options && typeof data.filter_options === "object"
      ? data.filter_options
      : {};
    state.records = Array.isArray(data.creators)
      ? data.creators
      : Array.isArray(data.records) ? data.records : [];
    render();
  }

  async function loadAgencyOptions() {
    const data = await pageContext.api.get("/api/local/agencies", {
      signal: pageContext.resources.signal,
    });
    const select = element("creator-library-agency");
    if (!select) return;
    const selected = select.value;
    const options = (Array.isArray(data.agencies) ? data.agencies : [])
      .filter(agency => agency?.agency_id)
      .sort((left, right) => String(left.name || "").localeCompare(String(right.name || "")))
      .map(agency => new Option(agency.name || agency.agency_id, agency.agency_id));
    select.replaceChildren(new Option(t("creatorLibraryAllAgencies"), ""), ...options);
    select.value = options.some(option => option.value === selected) ? selected : "";
  }

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return global.btoa(binary);
  }

  function desktopFileBridge() {
    return global.pywebview?.api?.save_xlsx || null;
  }

  async function saveXlsxResponse(response, filename) {
    const saveXlsx = desktopFileBridge();
    if (saveXlsx) {
      const result = await saveXlsx(filename, arrayBufferToBase64(await response.arrayBuffer()));
      if (result?.saved === true) return { saved: true, desktop: true, path: result.path };
      if (result?.canceled === true) return { saved: false, canceled: true };
      throw new Error(result?.error || t("creatorLibraryFileSaveFailed"));
    }
    const objectUrl = global.URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove?.();
    global.URL.revokeObjectURL(objectUrl);
    return { saved: true, desktop: false, path: null };
  }

  async function downloadBinary(url, filename) {
    const response = await global.fetch(url, { cache: "no-store", signal: pageContext.resources.signal });
    if (!response.ok) throw new Error(t("creatorLibraryDownloadFailed"));
    return saveXlsxResponse(response, filename);
  }

  async function downloadImportTemplate() {
    try {
      const result = await downloadBinary("/api/creator-library/import-template", "KOLConnect_Creator_Import_Template.xlsx");
      if (result.desktop && result.saved) pageContext.ui.showSaved(t("creatorLibraryTemplateSaved", { path: result.path }));
    } catch (error) {
      showError(error);
    }
  }

  async function exportSelectedCreators() {
    const creatorIds = [...selectedCreatorIds()];
    if (!creatorIds.length) return;
    try {
      const response = await global.fetch("/api/creator-library/export", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        signal: pageContext.resources.signal,
        body: JSON.stringify({ creator_ids: creatorIds }),
      });
      if (!response.ok) throw new Error(t("creatorLibraryExportFailed"));
      const result = await saveXlsxResponse(response, "KOLConnect_Creator_Export.xlsx");
      if (result.canceled) return;
      pageContext.ui.showSaved(
        result.desktop ? t("creatorLibraryExportSaved", { path: result.path }) : t("creatorLibraryExported", { count: creatorIds.length }),
      );
    } catch (error) {
      showError(error);
    }
  }

  function batchCampaignElement(id) {
    return element(`creator-library-batch-campaign-${id}`);
  }

  function setBatchCampaignMessage(message, tone = "") {
    const target = batchCampaignElement("message");
    if (!target) return;
    target.hidden = !message;
    target.textContent = message || "";
    target.dataset.tone = tone;
  }

  function setBatchCampaignSubmit(disabled, label = t("creatorLibraryConfirmAdd")) {
    const button = batchCampaignElement("submit");
    if (!button) return;
    button.disabled = disabled;
    button.textContent = label;
  }

  function closeBatchCampaignModal() {
    const modal = element("creator-library-batch-campaign-modal");
    if (modal) modal.hidden = true;
    setBatchCampaignMessage("");
    setBatchCampaignSubmit(false);
  }

  async function openBatchCampaignModal() {
    const creatorIds = [...selectedCreatorIds()];
    if (!creatorIds.length) return;
    const modal = element("creator-library-batch-campaign-modal");
    const select = batchCampaignElement("select");
    if (!modal || !select) return;
    modal.hidden = false;
    batchCampaignElement("count").textContent = t("creatorLibraryBatchSelected", { count: creatorIds.length });
    select.replaceChildren(new Option(t("creatorLibraryLoading"), ""));
    select.disabled = true;
    setBatchCampaignMessage("");
    setBatchCampaignSubmit(true, t("creatorLibraryLoading"));
    try {
      const data = await pageContext.api.get("/api/campaigns", {
        signal: pageContext.resources.signal,
      });
      const campaigns = Array.isArray(data.campaigns) ? data.campaigns : [];
      const options = campaigns.map(campaign => new Option(
        [campaign.name, campaign.product_name, campaign.platform].filter(Boolean).join(" · "),
        String(campaign.campaign_id || ""),
      ));
      select.replaceChildren(new Option(
        options.length ? t("creatorLibraryChooseCampaign") : t("creatorLibraryNoCampaigns"), ""
      ), ...options);
      select.disabled = options.length === 0;
      setBatchCampaignSubmit(options.length === 0);
      if (!options.length) setBatchCampaignMessage(t("creatorLibraryNoCampaignsMessage"), "warning");
    } catch (error) {
      if (error?.name === "AbortError") return;
      setBatchCampaignMessage(error.message || t("creatorLibraryLoadCampaignFailed"), "error");
      setBatchCampaignSubmit(true);
    }
  }

  function batchSummary(result) {
    return [
      t("creatorLibraryBatchAdded", { count: Number(result.added) || 0 }),
      t("creatorLibraryBatchRestored", { count: Number(result.restored) || 0 }),
      t("creatorLibraryBatchPresent", { count: Number(result.already_present) || 0 }),
      t("creatorLibraryBatchFailed", { count: Number(result.failed) || 0 }),
    ].join(", ");
  }

  async function submitBatchCampaign(event) {
    event.preventDefault();
    const state = libraryState();
    if (state.batchCampaignSubmitting) return;
    const campaignId = String(batchCampaignElement("select")?.value || "").trim();
    const creatorIds = [...selectedCreatorIds()];
    if (!campaignId) {
      setBatchCampaignMessage(t("creatorLibraryCampaignSelectedRequired"), "warning");
      return;
    }
    if (!creatorIds.length) {
      closeBatchCampaignModal();
      updateSelectionControls();
      return;
    }
    state.batchCampaignSubmitting = true;
    setBatchCampaignSubmit(true, t("creatorLibraryJoining"));
    updateSelectionControls();
    try {
      const result = await pageContext.api.post(
        `/api/campaigns/${encodeURIComponent(campaignId)}/creators/batch`,
        { creator_ids: creatorIds },
        { signal: pageContext.resources.signal },
      );
      const successful = new Set(
        (Array.isArray(result.results) ? result.results : [])
          .filter(item => ["added", "restored", "already_present"].includes(item.status))
          .map(item => String(item.creator_id || ""))
          .filter(Boolean),
      );
      successful.forEach(creatorId => selectedCreatorIds().delete(creatorId));
      const summary = batchSummary(result);
      const failures = (Array.isArray(result.results) ? result.results : [])
        .filter(item => item.status === "failed")
        .map(item => `${item.creator_id || t("creatorLibraryUnknownCreator")}：${item.error || t("creatorLibraryAddFailed")}`);
      if (failures.length) {
        setBatchCampaignMessage(`${summary}。${failures.join("；")}`, "warning");
      } else {
        closeBatchCampaignModal();
        pageContext.ui.showSaved(summary);
      }
      render();
    } catch (error) {
      if (error?.name !== "AbortError") {
        setBatchCampaignMessage(error.message || t("creatorLibraryBatchAddFailed"), "error");
      }
    } finally {
      state.batchCampaignSubmitting = false;
      setBatchCampaignSubmit(false);
      updateSelectionControls();
    }
  }

  function toggleCurrentPageSelection(event) {
    const selected = selectedCreatorIds();
    const currentIds = libraryState().records.map(recordId).filter(Boolean);
    currentIds.forEach(creatorId => {
      if (event.target.checked) selected.add(creatorId);
      else selected.delete(creatorId);
    });
    render();
  }

  function toggleCreatorSelection(event) {
    const checkbox = event.target.closest("[data-creator-select-id]");
    if (!checkbox) return;
    const creatorId = String(checkbox.dataset.creatorSelectId || "");
    if (!creatorId) return;
    const selected = selectedCreatorIds();
    if (checkbox.checked) selected.add(creatorId);
    else selected.delete(creatorId);
    updateSelectionControls();
  }

  function renderImportResult(data, failed = false) {
    const panel = element("creator-library-import-result");
    const summary = element("creator-library-import-summary");
    const errors = element("creator-library-import-errors");
    if (!panel || !summary || !errors) return;
    panel.hidden = false;
    panel.dataset.tone = failed ? "error" : "success";
    errors.replaceChildren();
    if (!failed) {
      summary.textContent = t("creatorLibraryImportComplete", { created: Number(data.created) || 0, skipped: Number(data.skipped_existing) || 0 });
      return;
    }
    const report = data.summary || {};
    summary.textContent = t("creatorLibraryImportNotRun", { total: Number(report.total_rows) || 0, invalid: Number(report.invalid_rows) || 0 });
    (Array.isArray(data.rows) ? data.rows : []).forEach(row => {
      const item = document.createElement("li");
      const label = IMPORT_ERROR_KEYS[row.code] ? t(IMPORT_ERROR_KEYS[row.code]) : (row.code || t("creatorLibraryInvalidData"));
      const field = row.field ? `（${row.field}）` : "";
      item.textContent = t("creatorLibraryImportRow", { row: row.row, label, field });
      errors.appendChild(item);
    });
  }

  async function importCreatorWorkbook(event) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file) return;
    try {
      if (!String(file.name || "").toLowerCase().endsWith(".xlsx")) {
        renderImportResult({ summary: { total_rows: 0, invalid_rows: 1 }, rows: [] }, true);
        return;
      }
      const payload = await file.arrayBuffer();
      const response = await pageContext.api.postRaw(
        "/api/creator-library/import",
        payload,
        { headers: { "Content-Type": XLSX_CONTENT_TYPE }, signal: pageContext.resources.signal },
      );
      renderImportResult(response.data || {});
      pageContext.ui.showSaved(t("creatorLibraryExcelImported"));
      await loadRecords();
    } catch (error) {
      if (error?.responseData) renderImportResult(error.responseData, true);
      else showError(error);
    } finally {
      input.value = "";
    }
  }

  async function setViewMode(viewMode) {
    const state = libraryState();
    const nextMode = viewMode === "table" ? "table" : "card";
    if (state.viewMode === nextMode) return;
    state.viewMode = nextMode;
    state.page = 1;
    state.pageSize = DEFAULT_PAGE_SIZE[nextMode];
    global.localStorage.setItem(VIEW_MODE_STORAGE_KEY, nextMode);
    renderPageSizeOptions();
    await loadRecords();
  }

  async function changeSort() {
    const match = valueOf("creator-library-sort", "created_at_desc")
      .match(/^(created_at|updated_at|creator_name|followers|platform)_(asc|desc)$/);
    const state = libraryState();
    state.sort = match?.[1] || "created_at";
    state.order = match?.[2] || "desc";
    state.page = 1;
    await loadRecords();
  }

  async function changePageSize() {
    const state = libraryState();
    const requested = Number(valueOf("creator-library-page-size"));
    state.pageSize = PAGE_SIZES[state.viewMode].includes(requested)
      ? requested
      : DEFAULT_PAGE_SIZE[state.viewMode];
    state.page = 1;
    await loadRecords();
  }

  async function changeFilters() {
    const state = libraryState();
    state.filters = readFilters();
    state.page = 1;
    await loadRecords();
  }

  function scheduleSearchFilter() {
    const requestId = ++filterRequestId;
    pageContext.resources.setTimeout(() => {
      if (requestId === filterRequestId) changeFilters().catch(showError);
    }, 250);
  }

  async function handlePagination(event) {
    const button = event.target.closest("[data-creator-page]");
    if (!button || button.disabled) return;
    const state = libraryState();
    const page = Number(button.dataset.creatorPage);
    if (!Number.isInteger(page) || page < 1 || page > state.pages || page === state.page) return;
    state.page = page;
    await loadRecords();
  }

  async function openCollaborationTask(creatorId) {
    const context = pageContext;
    const data = await context.api.post(
      `/api/creator-library/${encodeURIComponent(creatorId)}/create-task`,
      {},
      { signal: context.resources.signal },
    );
    const task = data.task;
    if (!task?.id) throw new Error(t("creatorLibraryTaskMissing"));
    context.state.currentTaskId = task.id;
    context.state.currentTask = task;
    context.state.review.taskId = task.id;
    global.localStorage.setItem("kolconnect.currentTaskId", task.id);
    await context.navigate("review");
    context.ui.showSaved(data.message || t("creatorLibraryTaskOpened"));
  }

  async function changeArchiveState(creatorId, archived) {
    const message = archived
      ? t("creatorLibraryArchiveConfirm")
      : t("creatorLibraryRestoreConfirm");
    if (!global.confirm(message)) return;
    await pageContext.api.patch(
      `/api/creator-library/${encodeURIComponent(creatorId)}`,
      { archived_at: archived ? new Date().toISOString() : null },
      { signal: pageContext.resources.signal },
    );
    pageContext.ui.showSaved(archived ? t("creatorLibraryArchivedSaved") : t("creatorLibraryRestoredSaved"));
    await loadRecords();
  }

  async function handleAction(event) {
    const button = event.target.closest("[data-creator-action]");
    if (!button) return;
    const creatorId = String(button.dataset.creatorId || "");
    if (!creatorId) return;
    try {
      if (button.dataset.creatorAction === "detail") {
        await pageContext.navigate("creator-library-detail", { creatorId });
      } else if (button.dataset.creatorAction === "campaign") {
        const record = libraryState().records.find(
          item => String(item.creator_id || item.analysis_id || "") === creatorId,
        );
        await campaignModal.open(record);
      } else if (button.dataset.creatorAction === "task") {
        await openCollaborationTask(creatorId);
      } else if (button.dataset.creatorAction === "archive") {
        await changeArchiveState(creatorId, true);
      } else if (button.dataset.creatorAction === "restore") {
        await changeArchiveState(creatorId, false);
      } else if (button.dataset.creatorAction === "delete") {
        const record = libraryState().records.find(
          item => String(item.creator_id || item.analysis_id || "") === creatorId,
        );
        await deleteModal.open(record, {
          onDeleted: async () => {
            pageContext.state.creatorLibraryDetail = {};
            await loadRecords();
          },
        });
      } else if (button.dataset.creatorAction === "merge") {
        const record = libraryState().records.find(
          item => String(item.creator_id || item.analysis_id || "") === creatorId,
        );
        if (!mergeModal) {
          showError(new Error(t("creatorLibraryMergeUnavailable")));
          return;
        }
        await mergeModal.open(record, {
          onMerged: async () => {
            pageContext.state.creatorLibraryDetail = {};
            await loadRecords();
          },
        });
      }
    } catch (error) {
      showError(error);
    }
  }

  async function handleStatusChange(event) {
    const select = event.target.closest("[data-creator-status-id]");
    if (!select) return;
    const creatorId = String(select.dataset.creatorStatusId || "");
    const record = libraryState().records.find(item => String(item.creator_id || item.analysis_id) === creatorId);
    if (!record) return;
    const previousStatus = record.status || "discovered";
    try {
      await pageContext.api.post(
        `/api/creator-library/${encodeURIComponent(creatorId)}/status`,
        { status: select.value },
        { signal: pageContext.resources.signal },
      );
      record.status = select.value;
      pageContext.ui.showSaved(t("creatorLibraryStatusSaved"));
    } catch (error) {
      select.value = previousStatus;
      showError(error);
    }
  }

  function listen(id, type, listener) {
    const target = element(id);
    if (target) pageContext.resources.listen(target, type, listener);
  }

  const creatorLibraryPage = {
    async load(context) {
      if (!context?.state || !context.api || !context.resources || !context.params) {
        throw new Error("Creator Library page context is incomplete.");
      }
      pageContext = context;
      lifecycleId += 1;
      context.state.creatorLibrary ||= {};
      const state = context.state.creatorLibrary;
      state.records ||= [];
      state.selectedCreatorIds = state.selectedCreatorIds instanceof Set
        ? state.selectedCreatorIds
        : new Set();
      state.batchCampaignSubmitting = Boolean(state.batchCampaignSubmitting);
      const storedMode = global.localStorage.getItem(VIEW_MODE_STORAGE_KEY);
      state.viewMode = storedMode === "table" || state.viewMode === "table" ? "table" : "card";
      state.page = Number.isInteger(state.page) && state.page > 0 ? state.page : 1;
      state.pageSize = PAGE_SIZES[state.viewMode].includes(Number(state.pageSize))
        ? Number(state.pageSize)
        : DEFAULT_PAGE_SIZE[state.viewMode];
      state.sort = ["created_at", "updated_at", "creator_name", "followers", "platform"].includes(state.sort)
        ? state.sort
        : "created_at";
      state.order = state.order === "asc" ? "asc" : "desc";
      state.total = Number(state.total) || 0;
      state.pages = Number(state.pages) || 0;
      state.filters = { ...(state.filters || {}), ...readFilters() };
      state.filterOptions = state.filterOptions && typeof state.filterOptions === "object"
        ? state.filterOptions
        : {};
      element("creator-library-sort").value = `${state.sort}_${state.order}`;
      renderPageSizeOptions();
      campaignModal = global.KOLConnectCreatorCampaignModal.create(context);
      deleteModal = global.KOLConnectCreatorDeleteModal.create(context);
      mergeModal = global.KOLConnectCreatorMergeModal?.create(context) || null;
      await loadAgencyOptions().catch(() => {});
      await loadRecords();
    },

    bind() {
      campaignModal.bind();
      deleteModal.bind();
      mergeModal?.bind();
      listen("creator-library-refresh", "click", () => loadRecords().catch(showError));
      listen("creator-library-more-filters", "click", event => {
        const toolbar = element("creator-library-more-filters")?.closest(".creator-library-toolbar");
        if (!toolbar) return;
        const expanded = toolbar.classList.toggle("more-filters-open");
        event.currentTarget.setAttribute("aria-expanded", String(expanded));
        event.currentTarget.textContent = expanded ? t("creatorLibraryMoreFiltersClose") : t("creatorLibraryMoreFiltersOpen");
      });
      listen("creator-library-card-view", "click", () => setViewMode("card").catch(showError));
      listen("creator-library-table-view", "click", () => setViewMode("table").catch(showError));
      [
        "creator-library-country",
        "creator-library-language",
        "creator-library-category",
        "creator-library-agency",
        "creator-library-tag",
        "creator-library-ai-tag",
        "creator-library-level",
        "creator-library-status",
      ].forEach(id => listen(id, "change", () => {
        filterRequestId += 1;
        return changeFilters().catch(showError);
      }));
      ["creator-library-followers-min", "creator-library-followers-max"].forEach(
        id => listen(id, "input", scheduleSearchFilter),
      );
      listen("creator-library-sort", "change", () => changeSort().catch(showError));
      listen("creator-library-page-size", "change", () => changePageSize().catch(showError));
      listen("creator-library-page-buttons", "click", event => handlePagination(event).catch(showError));
      listen("creator-library-search", "input", scheduleSearchFilter);
      listen("creator-library-template-download", "click", downloadImportTemplate);
      listen("creator-library-export", "click", exportSelectedCreators);
      listen("creator-library-batch-campaign", "click", () => openBatchCampaignModal().catch(showError));
      listen("creator-library-batch-campaign-close", "click", closeBatchCampaignModal);
      listen("creator-library-batch-campaign-cancel", "click", closeBatchCampaignModal);
      listen("creator-library-batch-campaign-form", "submit", event => submitBatchCampaign(event).catch(showError));
      listen("creator-library-select-all", "change", toggleCurrentPageSelection);
      listen("creator-library-import-button", "click", () => element("creator-library-import-input")?.click());
      listen("creator-library-import-input", "change", importCreatorWorkbook);
      listen("creator-library-cards", "click", handleAction);
      listen("creator-library-cards", "change", toggleCreatorSelection);
      listen("creator-library-body", "click", handleAction);
      listen("creator-library-body", "change", toggleCreatorSelection);
      listen("creator-library-body", "change", handleStatusChange);
    },

    unbind() {
      lifecycleId += 1;
      filterRequestId += 1;
      campaignModal?.destroy();
      deleteModal?.destroy();
      mergeModal?.destroy();
      pageContext?.resources.cleanup();
      pageContext = null;
      listController = null;
      campaignModal = null;
      deleteModal = null;
      mergeModal = null;
    },
  };

  global.KOLConnectPages.registerPage("creator-library", creatorLibraryPage);
})(window);
