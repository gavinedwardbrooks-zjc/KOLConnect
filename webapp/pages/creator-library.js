(function registerCreatorLibraryPage(global) {
  "use strict";

  const STATUS_LABELS = Object.freeze({
    discovered: "已发现",
    contacted: "已联系",
    negotiating: "洽谈中",
    cooperating: "合作中",
    completed: "已完成",
    rejected: "已拒绝",
  });

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

    function setSubmitState(disabled, label = "确认加入") {
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
      const platform = String(account.platform || "未标注平台");
      const identity = account.username || account.profile_url || account.account_uid || account.account_id;
      const preferred = preferredPlatform && platform.toLowerCase() === preferredPlatform.toLowerCase();
      return `${platform} · ${identity || "未命名账号"}${preferred ? "（匹配 Campaign 平台）" : ""}`;
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
      setSelectOptions(select, options, accounts.length ? "请选择执行账号" : "暂无可用账号");
      if (accounts.length === 1) select.value = String(accounts[0].account_id || "");
      select.disabled = accounts.length === 0;
      if (hint) {
        hint.textContent = accounts.length === 0
          ? "该达人暂无可用社交账号，请先完善达人账号信息。"
          : accounts.length === 1
            ? "已自动选择该达人的唯一社交账号。"
            : platform
              ? `已优先排列与 ${platform} 匹配的账号，请人工确认执行账号。`
              : "该达人有多个账号，请人工选择本次合作的执行账号。";
      }
      setSubmitState(accounts.length === 0 || campaigns.length === 0);
    }

    function renderCampaigns() {
      const select = modalElement("creator-campaign-select");
      const options = campaigns.map(campaign => new Option(
        [campaign.name, campaign.product_name, campaign.platform].filter(Boolean).join(" · "),
        String(campaign.campaign_id || ""),
      ));
      setSelectOptions(select, options, campaigns.length ? "请选择 Campaign" : "暂无可用 Campaign");
      select.disabled = campaigns.length === 0;
      renderAccounts();
      if (!campaigns.length) setMessage("当前没有可加入的 Campaign。", "warning");
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
      setSelectOptions(modalElement("creator-campaign-select"), [], "请选择 Campaign");
      setSelectOptions(modalElement("creator-campaign-account-select"), [], "请选择执行账号");
      setSubmitState(true);
    }

    async function open(record, options = {}) {
      const creatorId = String(record?.creator_id || record?.analysis_id || "").trim();
      if (!creatorId) throw new Error("缺少 Creator ID，无法加入 Campaign。");
      close();
      const currentRequest = ++requestId;
      creator = { ...record, creator_id: creatorId };
      onCreated = typeof options.onCreated === "function" ? options.onCreated : null;
      const modal = modalElement("creator-campaign-modal");
      if (!modal) throw new Error("加入 Campaign 窗口未加载。");
      modal.hidden = false;
      modalElement("creator-campaign-creator-name").textContent = record.creator_name || "未命名达人";
      modalElement("creator-campaign-agency-name").textContent = record.agency_name || "暂无 Agency";
      setMessage("正在加载 Campaign 和达人账号...", "loading");
      setSubmitState(true, "正在加载...");
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
          || "未命名达人";
        modalElement("creator-campaign-agency-name").textContent = detailRecord.agency_name
          || creator.agency_name
          || "暂无 Agency";
        setMessage("");
        setSubmitState(false);
        renderCampaigns();
      } catch (error) {
        if (error?.name === "AbortError" || currentRequest !== requestId) return;
        setMessage(error.message || "无法加载 Campaign 或达人账号。", "error");
        setSubmitState(true);
      }
    }

    async function submit(event) {
      event.preventDefault();
      if (!creator) return;
      const campaignId = String(modalElement("creator-campaign-select")?.value || "").trim();
      const accountId = String(modalElement("creator-campaign-account-select")?.value || "").trim();
      if (!campaignId) {
        setMessage("请选择 Campaign。", "warning");
        return;
      }
      if (!accounts.length) {
        setMessage("该达人暂无可用社交账号，请先完善达人账号信息。", "warning");
        return;
      }
      if (!accountId) {
        setMessage("请选择本次合作的执行账号。", "warning");
        return;
      }
      submitController?.abort();
      submitController = context.resources.createAbortController();
      setMessage("");
      setSubmitState(true, "正在加入...");
      try {
        const result = await context.api.post(
          `/api/campaigns/${encodeURIComponent(campaignId)}/creators`,
          { creator_id: creator.creator_id, account_id: accountId },
          { signal: submitController.signal },
        );
        const callback = onCreated;
        const creatorName = creator.creator_name || "该达人";
        close();
        if (callback) await callback(result.campaign_creator);
        context.ui.showSaved(`${creatorName} 已加入 Campaign。`);
      } catch (error) {
        if (error?.name === "AbortError") return;
        setMessage(
          error?.status === 409 ? "该达人已经加入此 Campaign。" : (error.message || "加入 Campaign 失败。"),
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
    const IMPACT_LABELS = Object.freeze({
      creators: "达人主记录",
      creator_accounts: "账号",
      videos: "视频",
      insights: "Insight",
      analysis_data: "Analysis",
      creator_snapshots: "Creator Snapshots",
      video_snapshots: "Video Snapshots",
      campaign_creators: "Campaign 关系",
      follow_up_logs: "跟进记录",
      task_artifacts: "任务文件",
      data_protection: "数据保护记录",
      legacy_sources: "Legacy 记录",
      cooperations: "历史合作",
      embedded_analysis_references: "嵌入式 Analysis 引用",
      unmapped_task_artifacts: "未解析任务文件",
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
        confirm.textContent = submitting ? "正在永久删除..." : "确认永久删除";
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
        Object.entries(IMPACT_LABELS).forEach(([key, label]) => {
          if (!Object.prototype.hasOwnProperty.call(values, key)) return;
          const item = document.createElement("li");
          const name = document.createElement("span");
          const count = document.createElement("strong");
          name.textContent = label;
          count.textContent = String(impactCount(values[key]));
          item.append(name, count);
          list.appendChild(item);
        });
      }
      if (blockers) {
        blockers.replaceChildren();
        (impact?.blockers || []).forEach(blocker => {
          const item = document.createElement("li");
          item.textContent = blocker.message || blocker.code || "存在无法安全处理的关联数据。";
          blockers.appendChild(item);
        });
        blockers.hidden = !impact?.blockers?.length;
      }
      const state = modalElement("creator-delete-state");
      if (state) {
        state.textContent = impact?.can_delete
          ? "影响检查已通过，可以继续确认。"
          : "当前无法永久删除。请先处理下列阻止项。";
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
      setMessage(message || "正在检查永久删除影响...", message ? "warning" : "loading");
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
        setMessage(error.message || "无法读取永久删除影响。", "error");
        setButtons();
      }
    }

    async function open(record, options = {}) {
      const creatorId = String(record?.creator_id || record?.analysis_id || "").trim();
      if (!creatorId) throw new Error("缺少 Creator ID，无法检查永久删除影响。");
      close();
      creator = { ...record, creator_id: creatorId };
      onDeleted = typeof options.onDeleted === "function" ? options.onDeleted : null;
      const modal = modalElement("creator-delete-modal");
      if (!modal) throw new Error("永久删除确认窗口未加载。");
      modal.hidden = false;
      modalElement("creator-delete-creator-name").textContent = record.creator_name || "未命名达人";
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
        context.ui.showSaved("达人已永久删除。");
      } catch (error) {
        if (error?.name === "AbortError") return;
        submitting = false;
        const code = error?.responseData?.error || error?.message;
        if (code === "DELETE_PREVIEW_STALE") {
          await loadImpact("相关数据已发生变化，请重新确认删除影响。");
        } else if (code === "DELETE_BLOCKED") {
          await loadImpact("当前出现新的安全阻止项，已刷新删除影响。");
        } else if (code === "SHARED_STORAGE_LOCK_TIMEOUT") {
          impact = null;
          setMessage("当前数据正在被其他操作修改，请稍后重新检查影响。", "warning");
          setButtons();
        } else if (code === "CREATOR_NOT_FOUND") {
          const callback = onDeleted;
          close();
          if (callback) await callback();
          context.ui.showSaved("达人已不存在，列表已刷新。");
        } else {
          impact = null;
          setMessage("永久删除失败，数据已保持或恢复到安全状态。请稍后重试。", "error");
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
  let lifecycleId = 0;
  let filterRequestId = 0;
  const VIEW_MODE_STORAGE_KEY = "creator_library_view_mode";
  const PAGE_SIZES = Object.freeze({ card: [12, 24, 48], table: [25, 50, 100] });
  const DEFAULT_PAGE_SIZE = Object.freeze({ card: 24, table: 50 });
  const XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  const IMPORT_ERROR_LABELS = Object.freeze({
    MISSING_REQUIRED_FIELD: "必填字段缺失",
    INVALID_PLATFORM: "平台无效",
    INVALID_PROFILE_URL: "主页链接无效",
    DUPLICATE_IN_FILE: "文件内存在重复达人",
    UNKNOWN_AGENCY: "Agency 不存在",
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
    if (!change || change.status === "no_history") return "暂无历史数据";
    if (change.status !== "available" || change.delta === null || change.delta === undefined) return "--";
    const amount = formatMetric(Math.abs(Number(change.delta)));
    if (change.direction === "growth") return `↑ 增长 ${amount}`;
    if (change.direction === "decline") return `↓ 下降 ${amount}`;
    return "— 无变化";
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
    summary.textContent = `第 ${start}-${end} 条，共 ${state.total} 位达人`;
    buttons.appendChild(createPageButton("上一页", state.page - 1, state.page <= 1));
    const pageNumbers = visiblePageNumbers(state.page, state.pages);
    pageNumbers.forEach((page, index) => {
      if (index > 0 && page - pageNumbers[index - 1] > 1) {
        const gap = document.createElement("span");
        gap.textContent = "…";
        buttons.appendChild(gap);
      }
      buttons.appendChild(createPageButton(String(page), page, false, page === state.page));
    });
    buttons.appendChild(createPageButton("下一页", state.page + 1, state.page >= state.pages));
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
    const exportButton = element("creator-library-export");
    if (selectAll) {
      selectAll.checked = currentIds.length > 0 && currentIds.every(id => selected.has(id));
      selectAll.indeterminate = currentIds.some(id => selected.has(id)) && !selectAll.checked;
      selectAll.disabled = currentIds.length === 0;
    }
    if (exportButton) {
      exportButton.disabled = selected.size === 0;
      exportButton.textContent = selected.size ? `导出选中达人（${selected.size}）` : "导出选中达人";
    }
  }

  function createSelectionControl(creatorId) {
    const label = document.createElement("label");
    label.className = "creator-card-select";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.creatorSelectId = creatorId;
    input.checked = selectedCreatorIds().has(creatorId);
    const text = document.createElement("span");
    text.textContent = "选择";
    label.append(input, text);
    return label;
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
      avatar.textContent = String(record.creator_name || record.platform || "K").trim().slice(0, 1).toUpperCase();
      const identityText = document.createElement("div");
      const title = document.createElement("h2");
      title.textContent = record.creator_name || "未命名达人";
      const subtitle = document.createElement("p");
      subtitle.textContent = [record.platform, record.country || "未知地区"].filter(Boolean).join(" · ");
      identityText.append(title, subtitle);
      identity.append(avatar, identityText);

      const tags = document.createElement("div");
      tags.className = "creator-card-tags";
      [
        record.content_category,
        record.insight_level || "insufficient",
        STATUS_LABELS[record.status] || "已发现",
      ].filter(Boolean).forEach((label, index) => {
        const tag = document.createElement("span");
        tag.className = index === 1 ? "creator-card-level" : "creator-card-tag";
        tag.textContent = label;
        tags.appendChild(tag);
      });

      const metrics = document.createElement("div");
      metrics.className = "creator-card-metrics";
      [
        ["粉丝", record.followers || "--"],
        ["平均播放", formatMetric(record.average_views)],
        ["最近分析", formatTime(record.last_analysis_time || record.analysis_time)],
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
      actions.appendChild(createSelectionControl(creatorId));
      actions.appendChild(createAction("查看达人", "detail", creatorId, "soft-btn creator-card-action"));
      if (archived) {
        actions.appendChild(createAction("恢复达人", "restore", creatorId, "soft-btn creator-card-action"));
      } else {
        actions.append(
          createAction("加入 Campaign", "campaign", creatorId, "primary-btn creator-card-action"),
          createAction("归档达人", "archive", creatorId, "soft-btn creator-card-action"),
        );
      }
      actions.appendChild(createAction("永久删除", "delete", creatorId, "soft-btn danger creator-card-action"));
      card.append(identity, tags, metrics, actions);
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
        record.creator_name || "未命名达人",
        record.platform || "--",
        "link",
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
        archivedLabel.textContent = "已归档";
        statusCell.appendChild(archivedLabel);
      } else {
        const statusSelect = document.createElement("select");
        statusSelect.dataset.creatorStatusId = creatorId;
        Object.entries(STATUS_LABELS).forEach(([value, label]) => {
          statusSelect.add(new Option(label, value, false, value === record.status));
        });
        statusCell.appendChild(statusSelect);
      }
      row.appendChild(statusCell);

      const actions = document.createElement("td");
      actions.appendChild(createAction("查看分析", "detail", creatorId, "soft-btn compact-btn"));
      if (archived) {
        actions.appendChild(createAction("恢复", "restore", creatorId, "soft-btn compact-btn"));
      } else {
        actions.append(
          createAction("加入 Campaign", "campaign", creatorId, "soft-btn compact-btn"),
          createAction("创建合作任务", "task", creatorId, "primary-btn compact-btn"),
          createAction("归档", "archive", creatorId, "soft-btn compact-btn"),
        );
      }
      actions.appendChild(createAction("永久删除", "delete", creatorId, "soft-btn danger compact-btn"));
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
    renderOptions("creator-library-category", options.content_category || [], "全部内容类型");
    renderOptions("creator-library-country", options.country || [], "全部国家/地区");
    renderOptions("creator-library-language", options.language || [], "全部语言");
    renderOptions("creator-library-tag", options.tag || [], "全部标签");
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
    select.replaceChildren(new Option("全部 Agency", ""), ...options);
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
      throw new Error(result?.error || "文件保存失败，请稍后重试。");
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
    if (!response.ok) throw new Error("下载失败，请稍后重试。");
    return saveXlsxResponse(response, filename);
  }

  async function downloadImportTemplate() {
    try {
      const result = await downloadBinary("/api/creator-library/import-template", "KOLConnect_Creator_Import_Template.xlsx");
      if (result.desktop && result.saved) pageContext.ui.showSaved(`模板已保存到：${result.path}`);
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
      if (!response.ok) throw new Error("导出失败，请刷新达人库后重试。");
      const result = await saveXlsxResponse(response, "KOLConnect_Creator_Export.xlsx");
      if (result.canceled) return;
      pageContext.ui.showSaved(
        result.desktop ? `已保存到：${result.path}` : `已导出 ${creatorIds.length} 位达人。`,
      );
    } catch (error) {
      showError(error);
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
      summary.textContent = `导入完成：新增 ${Number(data.created) || 0}，跳过已有 ${Number(data.skipped_existing) || 0}。`;
      return;
    }
    const report = data.summary || {};
    summary.textContent = `导入未执行：共 ${Number(report.total_rows) || 0} 行，无效 ${Number(report.invalid_rows) || 0} 行。`;
    (Array.isArray(data.rows) ? data.rows : []).forEach(row => {
      const item = document.createElement("li");
      const label = IMPORT_ERROR_LABELS[row.code] || row.code || "数据无效";
      const field = row.field ? `（${row.field}）` : "";
      item.textContent = `第 ${row.row} 行：${label}${field}`;
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
      pageContext.ui.showSaved("Creator Excel 导入完成。");
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
    if (!task?.id) throw new Error("未找到关联的审核任务。");
    context.state.currentTaskId = task.id;
    context.state.currentTask = task;
    context.state.review.taskId = task.id;
    global.localStorage.setItem("kolconnect.currentTaskId", task.id);
    await context.navigate("review");
    context.ui.showSaved(data.message || "已打开关联的审核任务。");
  }

  async function changeArchiveState(creatorId, archived) {
    const message = archived
      ? "归档后，达人将从默认列表隐藏，历史分析和 Campaign 关联会保留。"
      : "恢复该达人到默认达人库？";
    if (!global.confirm(message)) return;
    await pageContext.api.patch(
      `/api/creator-library/${encodeURIComponent(creatorId)}`,
      { archived_at: archived ? new Date().toISOString() : null },
      { signal: pageContext.resources.signal },
    );
    pageContext.ui.showSaved(archived ? "达人已归档。" : "达人已恢复。");
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
      pageContext.ui.showSaved("达人状态已保存。");
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
      await loadAgencyOptions().catch(() => {});
      await loadRecords();
    },

    bind() {
      campaignModal.bind();
      deleteModal.bind();
      listen("creator-library-refresh", "click", () => loadRecords().catch(showError));
      listen("creator-library-card-view", "click", () => setViewMode("card").catch(showError));
      listen("creator-library-table-view", "click", () => setViewMode("table").catch(showError));
      [
        "creator-library-country",
        "creator-library-language",
        "creator-library-category",
        "creator-library-agency",
        "creator-library-tag",
        "creator-library-level",
        "creator-library-status",
      ].forEach(id => listen(id, "change", () => {
        filterRequestId += 1;
        return changeFilters().catch(showError);
      }));
      listen("creator-library-sort", "change", () => changeSort().catch(showError));
      listen("creator-library-page-size", "change", () => changePageSize().catch(showError));
      listen("creator-library-page-buttons", "click", event => handlePagination(event).catch(showError));
      listen("creator-library-search", "input", scheduleSearchFilter);
      listen("creator-library-template-download", "click", downloadImportTemplate);
      listen("creator-library-export", "click", exportSelectedCreators);
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
      pageContext?.resources.cleanup();
      pageContext = null;
      listController = null;
      campaignModal = null;
      deleteModal = null;
    },
  };

  global.KOLConnectPages.registerPage("creator-library", creatorLibraryPage);
})(window);
