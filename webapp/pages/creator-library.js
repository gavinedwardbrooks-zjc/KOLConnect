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

  let pageContext = null;
  let listController = null;
  let campaignModal = null;
  let lifecycleId = 0;

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

  function numericValue(value) {
    if (value === null || value === undefined || value === "") return 0;
    if (typeof value === "number") return Number.isFinite(value) ? value : 0;
    const raw = String(value).trim().replace(/,/g, "");
    const match = raw.match(/^([0-9]+(?:\.[0-9]+)?)\s*([kmb])?$/i);
    if (!match) return Number(raw) || 0;
    const multiplier = { k: 1e3, m: 1e6, b: 1e9 }[(match[2] || "").toLowerCase()] || 1;
    return Number(match[1]) * multiplier;
  }

  function tagsFor(record) {
    return String(record.tags || "")
      .replace(/，/g, ",")
      .split(",")
      .map(tag => tag.trim())
      .filter(Boolean);
  }

  function valueOf(id, fallback = "") {
    const target = element(id);
    return target ? (target.value ?? fallback) : fallback;
  }

  function filteredRecords() {
    const keyword = valueOf("creator-library-search").trim().toLowerCase();
    const platform = valueOf("creator-library-platform");
    const country = valueOf("creator-library-country");
    const language = valueOf("creator-library-language");
    const category = valueOf("creator-library-category");
    const tag = valueOf("creator-library-tag");
    const level = valueOf("creator-library-level");
    const status = valueOf("creator-library-status");
    const sort = valueOf("creator-library-sort", "analysis_time_desc");
    const records = libraryState().records.filter(record => {
      const archived = Boolean(record.archived_at);
      const searchable = [
        record.creator_name,
        record.platform,
        record.profile_url,
        record.country,
        record.language,
        record.content_category,
        record.tags,
      ].join(" ").toLowerCase();
      return (!keyword || searchable.includes(keyword))
        && (!platform || record.platform === platform)
        && (!country || record.country === country)
        && (!language || record.language === language)
        && (!category || record.content_category === category)
        && (!tag || tagsFor(record).includes(tag))
        && (!level || record.insight_level === level)
        && (status === "archived" ? archived : !archived && (!status || record.status === status));
    });
    const sortValues = {
      followers_desc: record => numericValue(record.followers),
      median_views_desc: record => numericValue(record.median_views),
      average_views_desc: record => numericValue(record.average_views),
      analysis_time_desc: record => Date.parse(record.last_analysis_time || record.analysis_time || "") || 0,
    };
    const valueForSort = sortValues[sort] || sortValues.analysis_time_desc;
    return records.sort((left, right) => valueForSort(right) - valueForSort(left));
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

  function renderCards(records) {
    const cards = element("creator-library-cards");
    cards.replaceChildren();
    records.forEach(record => {
      const creatorId = String(record.creator_id || record.analysis_id || "");
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
      actions.appendChild(createAction("查看达人", "detail", creatorId, "soft-btn creator-card-action"));
      if (archived) {
        actions.appendChild(createAction("恢复达人", "restore", creatorId, "soft-btn creator-card-action"));
      } else {
        actions.append(
          createAction("加入 Campaign", "campaign", creatorId, "primary-btn creator-card-action"),
          createAction("归档达人", "archive", creatorId, "soft-btn creator-card-action"),
        );
      }
      card.append(identity, tags, metrics, actions);
      cards.appendChild(card);
    });
  }

  function renderTable(records) {
    const body = element("creator-library-body");
    body.replaceChildren();
    records.forEach(record => {
      const creatorId = String(record.creator_id || record.analysis_id || "");
      const archived = Boolean(record.archived_at);
      const row = document.createElement("tr");
      const values = [
        record.creator_name || "未命名达人",
        record.platform || "--",
        "link",
        record.followers || "--",
        record.content_category || "--",
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

    renderOptions("creator-library-platform", state.records.map(item => item.platform), "全部平台");
    renderOptions("creator-library-category", state.records.map(item => item.content_category), "全部内容类型");
    renderOptions("creator-library-country", state.records.map(item => item.country), "全部国家/地区");
    renderOptions("creator-library-language", state.records.map(item => item.language), "全部语言");
    renderOptions("creator-library-tag", state.records.flatMap(tagsFor), "全部标签");
    const records = filteredRecords();
    empty.hidden = records.length > 0;
    cards.hidden = state.view !== "cards";
    tableWrap.hidden = state.view !== "table" && records.length > 0;
    element("creator-library-card-view").classList.toggle("active", state.view === "cards");
    element("creator-library-table-view").classList.toggle("active", state.view === "table");
    renderCards(records);
    renderTable(records);
  }

  async function loadRecords() {
    const currentLifecycle = lifecycleId;
    listController?.abort();
    listController = pageContext.resources.createAbortController();
    const includeArchived = valueOf("creator-library-status") === "archived";
    const url = includeArchived ? "/api/creator-library?include_archived=true" : "/api/creator-library";
    const data = await pageContext.api.get(url, { signal: listController.signal });
    if (!pageContext || currentLifecycle !== lifecycleId) return;
    libraryState().records = Array.isArray(data.records) ? data.records : [];
    render();
  }

  function setView(view) {
    libraryState().view = view === "table" ? "table" : "cards";
    global.localStorage.setItem("kolconnect.creatorLibraryView", libraryState().view);
    render();
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
      context.state.creatorLibrary.records ||= [];
      context.state.creatorLibrary.view = context.state.creatorLibrary.view === "table" ? "table" : "cards";
      campaignModal = global.KOLConnectCreatorCampaignModal.create(context);
      await loadRecords();
    },

    bind() {
      campaignModal.bind();
      listen("creator-library-refresh", "click", () => loadRecords().catch(showError));
      listen("creator-library-card-view", "click", () => setView("cards"));
      listen("creator-library-table-view", "click", () => setView("table"));
      [
        "creator-library-platform",
        "creator-library-country",
        "creator-library-language",
        "creator-library-category",
        "creator-library-tag",
        "creator-library-level",
        "creator-library-sort",
      ].forEach(id => listen(id, "change", render));
      listen("creator-library-status", "change", () => loadRecords().catch(showError));
      listen("creator-library-search", "input", render);
      listen("creator-library-cards", "click", handleAction);
      listen("creator-library-body", "click", handleAction);
      listen("creator-library-body", "change", handleStatusChange);
    },

    unbind() {
      lifecycleId += 1;
      campaignModal?.destroy();
      pageContext?.resources.cleanup();
      pageContext = null;
      listController = null;
      campaignModal = null;
    },
  };

  global.KOLConnectPages.registerPage("creator-library", creatorLibraryPage);
})(window);
