(() => {
  const GLOBAL_KEY = "__KOLCONNECT_NEXT_ASSISTANT__";
  const ROOT_ID = "kolconnect-next-root";
  if (globalThis[GLOBAL_KEY]) return;

  const MESSAGE = {
    OPEN: "KOLCONNECT_NEXT_OPEN",
    ERROR: "KOLCONNECT_NEXT_ERROR",
    COLLECT: "KOLCONNECT_NEXT_COLLECT",
    ADD_ACCOUNT: "KOLCONNECT_NEXT_ADD_ACCOUNT",
    UPDATE_ACCOUNT: "KOLCONNECT_NEXT_UPDATE_ACCOUNT",
    LOOKUP_ACCOUNT: "KOLCONNECT_NEXT_LOOKUP_ACCOUNT",
    SEARCH_CREATORS: "KOLCONNECT_NEXT_SEARCH_CREATORS",
    LINK_EXISTING_CREATOR: "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR",
    LOAD_AGENCIES: "KOLCONNECT_NEXT_LOAD_AGENCIES",
    CREATE_DISCOVERY_TASK: "KOLCONNECT_NEXT_CREATE_DISCOVERY_TASK",
    LOOKUP_DISCOVERY_CANDIDATES: "KOLCONNECT_NEXT_LOOKUP_DISCOVERY_CANDIDATES",
    LOAD_MAIL_OPTIONS: "KOLCONNECT_NEXT_LOAD_MAIL_OPTIONS",
    PREVIEW_MAIL_TEMPLATE: "KOLCONNECT_NEXT_PREVIEW_MAIL_TEMPLATE",
    CREATE_MAIL_DRAFT: "KOLCONNECT_NEXT_CREATE_MAIL_DRAFT",
    OPEN_MAIL_WORKSPACE: "KOLCONNECT_NEXT_OPEN_MAIL_WORKSPACE",
    CHECK_UPDATE: "KOLCONNECT_NEXT_CHECK_UPDATE",
    SNOOZE_UPDATE: "KOLCONNECT_NEXT_SNOOZE_UPDATE",
    OPEN_UPDATE_DOWNLOAD: "KOLCONNECT_NEXT_OPEN_UPDATE_DOWNLOAD",
    PAGE_CHANGED: "KOLCONNECT_NEXT_PAGE_CHANGED",
    ANALYZE_CONTENT: "KOLCONNECT_NEXT_ANALYZE_CONTENT",
    CANCEL_CONTENT: "KOLCONNECT_NEXT_CANCEL_CONTENT",
    CONTENT_PROGRESS: "KOLCONNECT_NEXT_CONTENT_PROGRESS"
  };
  const ANALYSIS_TIMEOUT_MS = 10000;
  const CONTENT_TIMEOUT_MS = 95000;
  const NAVIGATION_DEBOUNCE_MS = 1000;
  const URL_CHECK_INTERVAL_MS = 1500;
  const SessionController = globalThis.KOLConnectAnalysisSessionController;
  const pageSupport = globalThis.KOLConnectPageSupport;
  const UpdatePrompt = globalThis.KOLConnectUpdatePrompt;
  const AssistantData = globalThis.KOLConnectAssistantData || Object.freeze({
    publishedTime: (item) => {
      const value = Date.parse(item?.published_at?.value || "");
      return Number.isFinite(value) ? value : null;
    },
    selectContents: (contents) => ({
      items: Array.isArray(contents) ? contents : [], excludedPinnedCount: 0,
      unknownPinnedCount: 0, missingPublishedCount: 0,
      metrics: { averageViews: null, medianViews: null, averageLikes: null,
        validViews: 0, validLikes: 0, validComments: 0,
        sampleCount: Array.isArray(contents) ? contents.length : 0 }
    })
  });
  const SimilarDiscovery = globalThis.KOLConnectSimilarCreatorDiscovery;
  const contentCategoryOptions = globalThis.KOLConnectConfig?.CONTENT_CATEGORY_OPTIONS || [];
  if (!SessionController || !pageSupport || !contentCategoryOptions.length) return;

  for (const staleId of [ROOT_ID, "kolconnect-next-assistant"]) {
    document.getElementById(staleId)?.remove();
  }

  const profileSessions = new SessionController(ANALYSIS_TIMEOUT_MS);
  const contentSessions = new SessionController(CONTENT_TIMEOUT_MS);
  const state = {
    profile: null,
    contentAnalysis: null,
    captureDiagnostics: null,
    captureDiagnosticTrace: {
      request_id: 0,
      status: "NOT_REQUESTED",
      request_started: false,
      background_response_received: false,
      background_response_ok: false,
      background_response_diagnostics_present: false,
      background_response_runtime_present: false,
      state_assigned: false,
      state_invalidated: false,
      state_rendered: false,
      reason: ""
    },
    contentLoading: false,
    visible: false,
    minimized: false,
    dismissedUrl: "",
    lastUrl: location.href,
    analyzedUrl: "",
    analysisTimer: null,
    currentSessionId: "",
    currentContentSessionId: "",
    preview: null,
    accountLookup: null,
    mutationPending: false,
    mutationSequence: 0,
    pendingAction: "",
    mutationOffline: false,
    previewDirty: new Set(),
    creatorSelectorOpen: false,
    creatorSelectorGeneration: 0,
    creatorSearchQuery: "",
    creatorPlatformFilter: "",
    creatorSearchPage: 0,
    creatorSearchPages: 0,
    creatorSearchResults: [],
    creatorSearchLoading: false,
    creatorSearchError: "",
    selectedCreatorId: "",
    creatorSelectorContext: null,
    updateCheckStarted: false,
    activeTab: "overview",
    dataRange: "items:30",
    excludePinned: true,
    contentAnalysisCache: new Map(),
    creatorTier: "",
    discovery: SimilarDiscovery?.getState?.() || { status: "idle", candidates: [] },
    selectedDiscoveryUrls: new Set(),
    discoveryBusy: false,
    discoveryLookup: new Map(),
    discoveryFilter: "all",
    mailOptionsGeneration: 0,
    mailOptions: null,
    mailOptionsState: "idle",
    mailTemplatePreview: null,
    mailDraftPending: false
  };

  const create = (tag, className = "", text = "") => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  };

  const root = create("aside");
  root.id = ROOT_ID;
  root.style.display = "none";
  const panel = create("section", "kol-panel");
  const head = create("header", "kol-head");
  const brand = create("span", "kol-brand", "KOLConnect v2.0.1");
  const minimizeButton = create("button", "kol-icon-button", "−");
  const closeButton = create("button", "kol-icon-button", "×");
  minimizeButton.type = "button";
  minimizeButton.title = "最小化";
  closeButton.type = "button";
  closeButton.title = "关闭";
  head.append(brand, minimizeButton, closeButton);

  const body = create("main", "kol-body");
  const tabList = create("nav", "kol-tabs");
  tabList.role = "tablist";
  const tabPanels = {};
  const tabButtons = {};
  for (const [name, label] of [["overview", "概览"], ["data", "数据"], ["contact", "联系"], ["tools", "工具"]]) {
    const button = create("button", "kol-tab", label);
    button.type = "button";
    button.role = "tab";
    button.dataset.tab = name;
    const panelElement = create("section", "kol-tab-panel");
    panelElement.dataset.panel = name;
    panelElement.role = "tabpanel";
    tabButtons[name] = button;
    tabPanels[name] = panelElement;
    tabList.append(button);
  }
  const status = create("div", "kol-status", "等待分析当前达人主页。");
  const updatePromptHost = create("div", "kol-update-host");
  const card = create("section", "kol-card");
  const fieldElements = {};
  const labels = {
    platform: "平台",
    username: "用户名",
    creator_name: "达人名称",
    followers: "粉丝 / 订阅数",
    bio: "简介",
    capture_status: "基础资料状态"
  };
  for (const [name, label] of Object.entries(labels)) {
    const row = create("div", "kol-row");
    row.append(create("span", "kol-label", label));
    const value = create("span", "kol-value", "—");
    fieldElements[name] = value;
    row.append(value);
    card.append(row);
  }

  const previewSection = create("section", "kol-preview-section");
  previewSection.append(create("h3", "kol-section-title", "导入预览"));
  const previewInputs = {};
  const previewLabels = {
    email: "Email",
    whatsapp: "WhatsApp",
    country: "Country",
    language: "Language"
  };
  for (const [name, label] of Object.entries(previewLabels)) {
    const field = create("label", "kol-preview-field");
    field.append(create("span", "kol-label", label));
    const input = create("input", "kol-preview-input");
    input.type = "text";
    input.autocomplete = "off";
    previewInputs[name] = input;
    field.append(input);
    previewSection.append(field);
  }
  const categoryField = create("label", "kol-preview-field");
  categoryField.append(create("span", "kol-label", "Content Category *"));
  const categorySelect = create("select", "kol-preview-input");
  const emptyCategory = create("option", "", "请选择");
  emptyCategory.value = "";
  categorySelect.append(emptyCategory);
  for (const category of contentCategoryOptions) {
    const option = create("option", "", category);
    option.value = category;
    categorySelect.append(option);
  }
  previewInputs.content_category = categorySelect;
  categoryField.append(categorySelect);
  previewSection.append(categoryField);

  const agencyField = create("label", "kol-preview-field");
  agencyField.append(create("span", "kol-label", "Agency"));
  const agencySelect = create("select", "kol-preview-input");
  const emptyAgency = create("option", "", "未选择 Agency");
  emptyAgency.value = "";
  agencySelect.append(emptyAgency);
  agencySelect.disabled = true;
  previewInputs.agency_id = agencySelect;
  agencyField.append(agencySelect);
  const agencyStatus = create("span", "kol-field-status", "正在加载 Agency…");
  agencyField.append(agencyStatus);
  previewSection.append(agencyField);

  const accountAwareness = create("section", "kol-account-awareness");
  accountAwareness.append(create("h3", "kol-section-title", "KOLConnect 收录状态"));
  const accountAwarenessText = create("div", "kol-account-awareness-text", "等待资料读取完成。");
  accountAwareness.append(accountAwarenessText);

  const creatorSelector = create("section", "kol-creator-selector");
  creatorSelector.hidden = true;
  creatorSelector.append(create("h3", "kol-section-title", "关联已有 Creator"));
  const creatorSearchInput = create("input", "kol-preview-input");
  creatorSearchInput.type = "search";
  creatorSearchInput.placeholder = "搜索达人名称或主页";
  creatorSearchInput.autocomplete = "off";
  const creatorSearchButton = create("button", "", "搜索");
  const creatorPlatformFilter = create("select", "kol-preview-input");
  for (const [value, label] of [["", "全部平台"], ["tiktok.com", "TikTok"], ["instagram.com", "Instagram"], ["youtube.com", "YouTube"]]) {
    const option = create("option", "", label); option.value = value; creatorPlatformFilter.append(option);
  }
  const creatorSearchStatus = create("div", "kol-field-status");
  const creatorSearchResults = create("div", "kol-creator-results");
  const creatorLoadMoreButton = create("button", "", "加载更多");
  const creatorSelectionStatus = create("div", "kol-field-status");
  const creatorConfirmButton = create("button", "kol-link-confirm", "确认关联");
  const creatorCancelButton = create("button", "", "取消");
  for (const button of [creatorSearchButton, creatorLoadMoreButton, creatorConfirmButton, creatorCancelButton]) {
    button.type = "button";
  }
  creatorSelector.append(
    creatorSearchInput, creatorPlatformFilter, creatorSearchButton, creatorSearchStatus, creatorSearchResults,
    creatorLoadMoreButton, creatorSelectionStatus, creatorConfirmButton, creatorCancelButton
  );

  const contentSection = create("section", "kol-content-section");
  contentSection.append(create("h3", "kol-section-title", "最近内容分析"));
  const dataControls = create("div", "kol-data-controls");
  const dataRangeSelect = create("select", "kol-preview-input");
  for (const [value, label] of [["items:7", "最近7条"], ["items:30", "最近30条"], ["days:7", "最近7天"], ["days:30", "最近30天"]]) {
    const option = create("option", "", label);
    option.value = value;
    dataRangeSelect.append(option);
  }
  dataRangeSelect.value = state.dataRange;
  const pinnedToggle = create("label", "kol-toggle");
  const pinnedInput = create("input");
  pinnedInput.type = "checkbox";
  pinnedInput.checked = true;
  pinnedToggle.append(pinnedInput, create("span", "", "排除明确置顶"));
  dataControls.append(dataRangeSelect, pinnedToggle);
  contentSection.append(
    dataControls,
    create("p", "kol-range-hint", "按所选范围执行有界采集；若平台上限或发布时间不足，按天结果会明确标记覆盖不完整。")
  );
  const contentStatus = create("div", "kol-content-status", "尚未分析。");
  const coreMetrics = create("div", "kol-metric-grid");
  const coreMetricFields = {};
  for (const [name, label] of [["followers", "粉丝数"], ["average_views", "平均播放"], ["average_likes", "平均点赞"], ["sample_count", "有效样本"]]) {
    const metric = create("div", "kol-metric-card");
    metric.append(create("span", "kol-label", label));
    const value = create("strong", "", "—");
    coreMetricFields[name] = value;
    metric.append(value);
    coreMetrics.append(metric);
  }
  const contentSummary = create("div", "kol-content-summary");
  const contentSummaryFields = {};
  const summaryLabels = {
    content_type: "内容类型",
    returned_count: "筛选后内容数量",
    excluded_pinned_count: "排除置顶数量",
    valid_views_count: "有效播放数据",
    valid_publish_time_count: "有效发布时间",
    valid_engagement_count: "有效互动率",
    average_views: "平均播放",
    median_views: "中位播放",
    average_likes: "平均点赞",
    coverage: "样本覆盖",
    weighted_engagement_rate: "综合互动率",
    time_coverage: "时间范围覆盖",
    capture_status: "数据状态"
  };
  for (const [name, label] of Object.entries(summaryLabels)) {
    const row = create("div", "kol-row");
    row.append(create("span", "kol-label", label));
    const value = create("span", "kol-value", "—");
    contentSummaryFields[name] = value;
    row.append(value);
    contentSummary.append(row);
  }
  const performanceDetails = create("details", "kol-content-details");
  performanceDetails.append(create("summary", "", "近期内容表现"), contentSummary);
  const contentDetails = create("details", "kol-content-details");
  contentDetails.append(create("summary", "", "最近视频"));
  const contentList = create("div", "kol-content-list");
  contentDetails.append(contentList);
  contentSection.append(
    contentStatus,
    coreMetrics,
    performanceDetails,
    contentDetails
  );

  const diagnostics = create("details", "kol-diagnostics");
  diagnostics.append(create("summary", "", "高级诊断"));
  const diagnosticsText = create("pre", "", "—");
  const diagnosticsRefresh = create("button", "", "刷新 TikTok 诊断（只读）");
  diagnosticsRefresh.type = "button";
  const diagnosticsHint = create("p", "", "只读内存计数，不采集、不重放、不请求 TikTok。累计计数随页面重载清零；当前行数按会话去重。fetch 匹配计数在响应完成后记录，XHR 在 send 时记录；bridge 拒绝计数包含无关页面消息。");
  diagnostics.append(diagnosticsRefresh, diagnosticsHint, diagnosticsText);

  const actions = create("div", "kol-actions");
  const refreshButton = create("button", "", "重新分析资料");
  const analyzeContentButton = create("button", "", "采集最近30条");
  const resetCaptureButton = create("button", "", "重新开始 TikTok 被动采集");
  resetCaptureButton.type = "button";
  resetCaptureButton.hidden = true;
  contentSection.append(resetCaptureButton);
  resetCaptureButton.addEventListener("click", async () => {
    await cancelContentAnalysis(false);
    try {
      const result = await sendMessage({ type: "KOLCONNECT_PASSIVE_RESET" });
      if (!result?.ok) throw new Error("被动采集重置失败，请刷新 TikTok 页面。");
      clearContent();
      if (state.profile) { state.profile.videos = []; state.profile.video_analysis = {}; }
      contentStatus.textContent = "已清空采集会话。请正常浏览主页后再次分析；不会主动请求视频。";
    } catch (error) { contentStatus.textContent = error.message; }
  });
  const cancelContentButton = create("button", "kol-danger", "取消内容分析");
  const copyButton = create("button", "", "复制诊断报告");
  const importButton = create("button", "kol-primary", "导入 KOLConnect");
  const linkButton = create("button", "", "关联已有 Creator");
  for (const button of [
    refreshButton,
    analyzeContentButton,
    cancelContentButton,
    copyButton,
    importButton,
    linkButton
  ]) {
    button.type = "button";
  }
  cancelContentButton.hidden = true;
  importButton.disabled = true;
  linkButton.hidden = true;
  const overviewQuick = create("div", "kol-button-grid kol-overview-quick");
  const toDataButton = create("button", "", "数据分析");
  const toContactButton = create("button", "", "联系达人");
  toDataButton.type = toContactButton.type = "button";
  overviewQuick.append(toDataButton, toContactButton);
  const dataActions = create("div", "kol-button-grid");
  dataActions.append(analyzeContentButton, cancelContentButton);
  const contactBusiness = create("section", "kol-contact-business");
  contactBusiness.append(create("h3", "kol-section-title", "邮件建联"));
  const tierField = create("label", "kol-preview-field");
  tierField.append(create("span", "kol-label", "达人分级"));
  const tierSelect = create("select", "kol-preview-input");
  for (const [value, label] of [["", "待确认"], ["KOL", "KOL"], ["KOC", "KOC"]]) {
    const option = create("option", "", label); option.value = value; tierSelect.append(option);
  }
  tierField.append(tierSelect);
  const templateField = create("label", "kol-preview-field");
  templateField.append(create("span", "kol-label", "邮件模板"));
  const templateAuthoritySelect = create("select", "kol-preview-input");
  templateAuthoritySelect.append(create("option", "", "请先选择分级和语言"));
  templateField.append(templateAuthoritySelect);
  const mailAccountField = create("label", "kol-preview-field");
  mailAccountField.append(create("span", "kol-label", "发送邮箱"));
  const mailAccountSelect = create("select", "kol-preview-input");
  mailAccountSelect.append(create("option", "", "请选择已启用邮箱"));
  mailAccountField.append(mailAccountSelect);
  const mailTemplatePreview = create("div", "kol-mail-template-preview");
  mailTemplatePreview.hidden = true;
  const mailTemplatePreviewTitle = create("strong", "", "");
  const mailTemplatePreviewGreeting = create("p", "", "");
  mailTemplatePreview.append(mailTemplatePreviewTitle, mailTemplatePreviewGreeting);
  const mailHint = create("p", "kol-field-status", "模板由 KOLConnect Mail Template Service 提供。创建后只保存草稿，不会自动发送。");
  const retryMailOptionsButton = create("button", "", "重试加载邮件配置");
  retryMailOptionsButton.type = "button";
  retryMailOptionsButton.hidden = true;
  const openMailButton = create("button", "kol-mail-action", "使用此模板创建邮件草稿");
  const manageTemplatesButton = create("button", "", "管理邮件模板");
  openMailButton.type = manageTemplatesButton.type = "button";
  contactBusiness.append(tierField, templateField, mailAccountField, mailTemplatePreview, mailHint, retryMailOptionsButton, openMailButton, manageTemplatesButton);
  const contactActions = create("div", "kol-button-grid");
  contactActions.append(refreshButton, importButton);
  const discoverySection = create("section", "kol-discovery");
  discoverySection.append(create("h3", "kol-section-title", "相似达人发现"));
  const discoveryStatus = create("p", "kol-field-status", "仅在 TikTok 达人主页的推荐弹窗中手动采集。");
  const discoveryControls = create("div", "kol-inline-actions");
  const discoveryStart = create("button", "kol-primary", "开始发现");
  const discoveryPause = create("button", "", "暂停");
  const discoveryFinish = create("button", "", "结束");
  for (const button of [discoveryStart, discoveryPause, discoveryFinish]) button.type = "button";
  discoveryControls.append(discoveryStart, discoveryPause, discoveryFinish);
  const discoveryList = create("div", "kol-discovery-list");
  const discoveryFilters = create("div", "kol-inline-actions");
  const discoveryLookupButton = create("button", "", "查询本地状态");
  const discoveryFilterSelect = create("select", "kol-preview-input");
  for (const [value, label] of [["all", "全部候选"], ["not_recorded", "仅未收录"], ["missing_email", "仅无邮箱"]]) {
    const option = create("option", "", label); option.value = value; discoveryFilterSelect.append(option);
  }
  discoveryLookupButton.type = "button";
  discoveryFilters.append(discoveryFilterSelect, discoveryLookupButton);
  const discoveryActions = create("div", "kol-inline-actions");
  const discoverySelectAll = create("button", "", "全选");
  const discoveryCopyAll = create("button", "", "复制全部");
  const discoveryCopy = create("button", "", "复制已选择");
  const discoveryCsvAll = create("button", "", "导出全部");
  const discoveryCsv = create("button", "", "导出已选择");
  const discoveryHandoff = create("button", "kol-primary", "移交发现达人任务");
  for (const button of [discoverySelectAll, discoveryCopyAll, discoveryCopy, discoveryCsvAll, discoveryCsv, discoveryHandoff]) button.type = "button";
  discoveryActions.append(discoverySelectAll, discoveryCopyAll, discoveryCopy, discoveryCsvAll, discoveryCsv, discoveryHandoff);
  discoverySection.append(discoveryStatus, discoveryControls, discoveryFilters, discoveryList, discoveryActions);
  const toolActions = create("div", "kol-actions");
  toolActions.append(copyButton, linkButton);

  tabPanels.overview.append(status, updatePromptHost, card, accountAwareness, overviewQuick);
  tabPanels.data.append(contentSection, dataActions);
  tabPanels.contact.append(previewSection, contactBusiness, contactActions);
  tabPanels.tools.append(discoverySection, creatorSelector, diagnostics, toolActions);
  body.append(tabList, ...Object.values(tabPanels));
  panel.append(head, body);
  root.append(panel);
  document.documentElement.append(root);

  const setStatus = (text, tone = "") => {
    status.textContent = text;
    status.dataset.tone = tone;
  };

  const renderTabs = () => {
    for (const [name, button] of Object.entries(tabButtons)) {
      const active = state.activeTab === name;
      button.dataset.active = String(active);
      button.ariaSelected = String(active);
      button.tabIndex = active ? 0 : -1;
      tabPanels[name].hidden = !active;
    }
  };
  const activateTab = (name) => {
    if (!tabPanels[name]) return;
    state.activeTab = name;
    renderTabs();
    if (name === "contact") loadMailOptions().catch(() => {});
  };
  Object.values(tabButtons).forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.tab)));
  tabList.addEventListener("keydown", (event) => {
    if (!new Set(["ArrowLeft", "ArrowRight", "Home", "End"]).has(event.key)) return;
    event.preventDefault();
    const names = Object.keys(tabButtons);
    let index = names.indexOf(state.activeTab);
    if (event.key === "Home") index = 0;
    else if (event.key === "End") index = names.length - 1;
    else index = (index + (event.key === "ArrowRight" ? 1 : -1) + names.length) % names.length;
    activateTab(names[index]);
    tabButtons[names[index]].focus();
  });

  const sendMessage = (message) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });

  const loadAgencyOptions = async () => {
    agencySelect.disabled = true;
    agencyStatus.textContent = "正在加载 Agency…";
    try {
      const response = await sendMessage({ type: MESSAGE.LOAD_AGENCIES });
      if (!response?.ok) {
        const error = new Error(response?.error || "Agency list unavailable.");
        error.code = response?.code || "AGENCY_LIST_FAILED";
        throw error;
      }
      const selectedAgencyId = state.preview?.agency_id || "";
      const options = [emptyAgency];
      for (const agency of Array.isArray(response.agencies) ? response.agencies : []) {
        if (!agency?.agency_id) continue;
        const option = create("option", "", agency.name || agency.agency_id);
        option.value = agency.agency_id;
        options.push(option);
      }
      agencySelect.replaceChildren(...options);
      agencySelect.value = options.some((option) => option.value === selectedAgencyId)
        ? selectedAgencyId
        : "";
      agencySelect.disabled = false;
      agencyStatus.textContent = options.length > 1 ? "" : "暂无可选 Agency";
    } catch (error) {
      agencySelect.replaceChildren(emptyAgency);
      agencySelect.value = "";
      agencySelect.disabled = true;
      agencyStatus.textContent = error?.code === "APP_OFFLINE"
        ? "KOLConnect 未运行，Agency 保持未选择"
        : "Agency 暂不可用，保持未选择且不影响基本导入";
    }
  };

  const checkForUpdate = async () => {
    if (state.updateCheckStarted || !UpdatePrompt) return;
    state.updateCheckStarted = true;
    try {
      const response = await sendMessage({ type: MESSAGE.CHECK_UPDATE });
      if (!response?.ok || !response.update) return;
      const prompt = UpdatePrompt.render({
        update: response.update,
        onDownload: async (update) => {
          const result = await sendMessage({
            type: MESSAGE.OPEN_UPDATE_DOWNLOAD,
            url: update.download_url
          });
          return Boolean(result?.ok);
        },
        onSnooze: async (update) => {
          const result = await sendMessage({ type: MESSAGE.SNOOZE_UPDATE, version: update.latest_version });
          return Boolean(result?.ok);
        }
      });
      if (prompt) updatePromptHost.replaceChildren(prompt);
    } catch (_) {}
  };

  const formatNumber = (value) => value == null
    ? "—"
    : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
  const formatPercent = (value) => value == null ? "—" : `${Number(value).toFixed(2)}%`;
  const contentTypeLabel = (value) => ({
    video: "视频",
    reel: "Reels",
    short: "Shorts"
  }[value] || "—");

  const hasValidProfileIdentity = (profile = state.profile) => Boolean(
    profile?.platform && profile?.profile_url && profile?.username
  );

  const mutationAction = () => state.accountLookup?.state === "ACCOUNT_NOT_FOUND"
    ? "ADD"
    : state.accountLookup?.state === "ACCOUNT_EXISTS" ? "UPDATE" : "";

  const resetCreatorSelector = () => {
    state.creatorSelectorGeneration += 1;
    state.creatorSelectorOpen = false;
    state.creatorSearchQuery = "";
    state.creatorPlatformFilter = "";
    state.creatorSearchPage = 0;
    state.creatorSearchPages = 0;
    state.creatorSearchResults = [];
    state.creatorSearchLoading = false;
    state.creatorSearchError = "";
    state.selectedCreatorId = "";
    state.creatorSelectorContext = null;
    creatorSearchInput.value = "";
    creatorPlatformFilter.value = "";
    renderCreatorSelector();
  };

  const selectorContextCurrent = () => {
    const context = state.creatorSelectorContext;
    return Boolean(context && state.creatorSelectorOpen
      && state.accountLookup?.state === "ACCOUNT_NOT_FOUND"
      && lookupContextCurrent(context.sessionId, context.identity, context.pageUrl));
  };

  const renderCreatorSelector = () => {
    creatorSelector.hidden = !state.creatorSelectorOpen || state.accountLookup?.state !== "ACCOUNT_NOT_FOUND";
    creatorSearchButton.disabled = state.creatorSearchLoading || state.mutationPending;
    creatorSearchStatus.textContent = state.creatorSearchError
      || (state.creatorSearchLoading ? "正在搜索…" : state.creatorSearchPage
        ? `第 ${state.creatorSearchPage}/${state.creatorSearchPages} 页`
        : "输入关键词并搜索，明确选择一位 Creator。");
    const entries = state.creatorSearchResults.filter((creator) => !state.creatorPlatformFilter
      || String(creator.profile_url || "").toLowerCase().includes(state.creatorPlatformFilter)).map((creator) => {
      const row = create("button", "kol-creator-result");
      row.type = "button";
      row.dataset.creatorId = creator.creator_id;
      row.textContent = `${creator.creator_name || "未命名 Creator"} · ${creator.account_count ?? "—"} 个账号${creator.profile_url ? ` · ${creator.profile_url}` : ` · ${creator.creator_id.slice(0, 8)}`}`;
      row.disabled = state.mutationPending;
      row.dataset.selected = String(state.selectedCreatorId === creator.creator_id);
      row.addEventListener("click", () => {
        if (state.mutationPending || !selectorContextCurrent()) return;
        state.selectedCreatorId = creator.creator_id;
        renderCreatorSelector();
      });
      return row;
    });
    creatorSearchResults.replaceChildren(...entries);
    creatorLoadMoreButton.hidden = !state.creatorSearchPage || state.creatorSearchPage >= state.creatorSearchPages;
    creatorLoadMoreButton.disabled = state.creatorSearchLoading || state.mutationPending;
    const selected = state.creatorSearchResults.find((row) => row.creator_id === state.selectedCreatorId);
    creatorSelectionStatus.textContent = selected
      ? `当前：${state.profile?.platform || "—"} @${state.profile?.username || "—"}；目标：${selected.creator_name || "未命名 Creator"}。确认后仅关联当前 CreatorAccount。`
      : "尚未选择 Creator。";
    creatorConfirmButton.disabled = !selected || !selectorContextCurrent()
      || state.creatorSearchLoading || Boolean(state.creatorSearchError) || state.mutationPending;
  };

  const searchCreatorLibrary = async (page = 1) => {
    if (!selectorContextCurrent() || state.mutationPending || state.creatorSearchLoading) return;
    const context = state.creatorSelectorContext;
    const generation = ++state.creatorSelectorGeneration;
    const query = creatorSearchInput.value.trim();
    if (page === 1) {
      state.creatorSearchQuery = query;
      state.creatorSearchResults = [];
      state.selectedCreatorId = "";
      state.creatorSearchPage = 0;
    } else if (query !== state.creatorSearchQuery) {
      return;
    }
    state.creatorSearchLoading = true;
    state.creatorSearchError = "";
    renderCreatorSelector();
    try {
      const response = await sendMessage({ type: MESSAGE.SEARCH_CREATORS, query, page });
      if (generation !== state.creatorSelectorGeneration || !selectorContextCurrent()
          || context !== state.creatorSelectorContext) return;
      if (!response?.ok || !Array.isArray(response.result?.creators)) throw new Error("搜索暂不可用，请确认 KOLConnect 已启动。");
      state.creatorSearchResults = page === 1
        ? response.result.creators
        : [...state.creatorSearchResults, ...response.result.creators];
      state.creatorSearchPage = response.result.page;
      state.creatorSearchPages = response.result.pages;
    } catch (_) {
      if (generation !== state.creatorSelectorGeneration || !selectorContextCurrent()) return;
      state.creatorSearchError = "搜索暂不可用，请确认 KOLConnect 已启动。";
      state.selectedCreatorId = "";
    } finally {
      if (generation === state.creatorSelectorGeneration) {
        state.creatorSearchLoading = false;
        renderCreatorSelector();
      }
    }
  };

  const openCreatorSelector = () => {
    if (state.mutationPending || state.accountLookup?.state !== "ACCOUNT_NOT_FOUND"
        || !hasValidProfileIdentity()) return;
    resetCreatorSelector();
    state.creatorSelectorOpen = true;
    state.creatorSelectorContext = {
      sessionId: state.currentSessionId, pageUrl: location.href, identity: profileIdentity()
    };
    renderCreatorSelector();
  };

  const syncPreviewState = (changedField = "") => {
    if (!state.preview) return;
    if (changedField) state.previewDirty.add(changedField);
    for (const [name, input] of Object.entries(previewInputs)) {
      state.preview[name] = String(input.value || "").trim();
    }
    renderProfile();
  };

  const initializePreview = (profile) => {
    state.preview = profile ? {
      email: profile.email || "",
      whatsapp: profile.whatsapp || "",
      country: profile.country || "",
      language: profile.language || "",
      content_category: profile.content_category || "",
      agency_id: ""
    } : null;
    for (const [name, input] of Object.entries(previewInputs)) {
      input.value = state.preview?.[name] || "";
    }
    state.previewDirty = new Set();
    renderProfile();
  };

  const previewFieldState = (name, value, original) => {
    if (!state.previewDirty.has(name) && original && typeof original === "object") {
      return { ...original };
    }
    if (value !== "") {
      return { value, source: "user_input", confidence: "high", missing_reason: "" };
    }
    return {
      value: null,
      source: "user_input",
      confidence: "missing",
      missing_reason: "No value was supplied in the import preview."
    };
  };

  const profileForMutation = () => {
    const fields = { ...(state.profile?.fields || {}) };
    for (const name of ["email", "whatsapp", "country", "language", "content_category"]) {
      const value = state.preview?.[name] ?? "";
      fields[name] = previewFieldState(name, value, fields[name]);
    }
    return {
      ...state.profile,
      fields,
      email: fields.email.value,
      whatsapp: fields.whatsapp.value,
      country: fields.country.value,
      language: fields.language.value,
      content_category: fields.content_category.value,
      agency_id: state.preview?.agency_id ?? ""
    };
  };

  const updateContentDiagnostic = () => {
    if (!state.profile?.diagnostic_report) return;
    const analysis = state.contentAnalysis;
    state.profile.diagnostic_report.profile_capture_status = state.profile.capture_status || "failed";
    state.profile.diagnostic_report.content_capture_status = analysis?.capture_status || "not_analyzed";
    state.profile.diagnostic_report.content_analysis = analysis ? {
      requested_count: analysis.requested_count,
      discovered_count: analysis.discovered_count,
      excluded_pinned_count: analysis.excluded_pinned_count,
      returned_count: analysis.returned_count,
      valid_views_count: analysis.valid_views_count,
      valid_publish_time_count: analysis.valid_publish_time_count,
      valid_engagement_count: analysis.valid_engagement_count,
      capture_status: analysis.capture_status,
      capture_diagnostics: analysis.capture_diagnostics || {},
      missing_field_summary: analysis.missing_field_summary || {},
      summary_validation: analysis.summary_validation || {}
    } : {};
  };

  const getCaptureDiagnostics = () => JSON.parse(JSON.stringify({
    content_analysis_present: Boolean(state.contentAnalysis),
    content_loading: state.contentLoading,
    runtime: state.captureDiagnostics,
    diagnostic_trace: state.captureDiagnosticTrace,
  }));
  const diagnosticReport = () => ({ ...state.profile?.diagnostic_report,
    ...(pageSupport.isSupportedCreatorPage(location.href) && /tiktok\.com\//i.test(location.href)
      ? { tiktok_capture: getCaptureDiagnostics() } : {}) });
  const refreshCaptureDiagnostics = async () => {
    const url = location.href;
    const requestId = state.captureDiagnosticTrace.request_id + 1;
    state.captureDiagnosticTrace = {
      request_id: requestId,
      status: "REQUEST_STARTED",
      request_started: true,
      background_response_received: false,
      background_response_ok: false,
      background_response_diagnostics_present: false,
      background_response_runtime_present: false,
      state_assigned: false,
      state_invalidated: false,
      state_rendered: false,
      reason: ""
    };
    diagnosticsRefresh.disabled = true;
    try {
      const result = await sendMessage({ type: "KOLCONNECT_PASSIVE_DIAGNOSTICS" });
      state.captureDiagnosticTrace.background_response_received = true;
      state.captureDiagnosticTrace.background_response_ok = result?.ok === true;
      state.captureDiagnosticTrace.background_response_diagnostics_present = Boolean(result?.diagnostics);
      state.captureDiagnosticTrace.background_response_runtime_present = Boolean(result?.diagnostics?.runtime);
      if (location.href !== url) {
        state.captureDiagnosticTrace.status = "STATE_INVALIDATED";
        state.captureDiagnosticTrace.state_invalidated = true;
        state.captureDiagnosticTrace.reason = "URL_CHANGED";
        return;
      }
      state.captureDiagnostics = result?.ok && result.diagnostics
        ? result.diagnostics : { status: "CAPTURE_DIAGNOSTICS_UNAVAILABLE" };
      state.captureDiagnosticTrace.status = result?.ok && result.diagnostics
        ? "STATE_ASSIGNED" : "BACKGROUND_RESPONSE_UNAVAILABLE";
      state.captureDiagnosticTrace.state_assigned = true;
      state.captureDiagnosticTrace.reason = result?.ok && result.diagnostics ? "" : "NO_DIAGNOSTICS";
    } catch (_) {
      if (location.href === url) {
        state.captureDiagnostics = { status: "CAPTURE_DIAGNOSTICS_UNAVAILABLE" };
        state.captureDiagnosticTrace.status = "BACKGROUND_ERROR";
        state.captureDiagnosticTrace.state_assigned = true;
        state.captureDiagnosticTrace.reason = "MESSAGE_ERROR";
      } else {
        state.captureDiagnosticTrace.status = "STATE_INVALIDATED";
        state.captureDiagnosticTrace.state_invalidated = true;
        state.captureDiagnosticTrace.reason = "URL_CHANGED";
      }
    } finally {
      diagnosticsRefresh.disabled = false;
      state.captureDiagnosticTrace.state_rendered = true;
      diagnosticsText.textContent = JSON.stringify(diagnosticReport(), null, 2);
    }
    return getCaptureDiagnostics();
  };
  diagnosticsRefresh.addEventListener("click", refreshCaptureDiagnostics);

  const renderProfile = () => {
    const profile = state.profile;
    const creatorName = typeof profile?.fields?.creator_name?.value === "string"
      ? profile.fields.creator_name.value.trim()
      : "";
    const username = typeof profile?.fields?.username?.value === "string"
      ? profile.fields.username.value.trim()
      : "";
    const displayName = creatorName || username || "—";
    fieldElements.platform.textContent = profile?.platform || "—";
    resetCaptureButton.hidden = profile?.platform !== "TikTok";
    fieldElements.username.textContent = username || "—";
    fieldElements.creator_name.textContent = displayName;
    fieldElements.followers.textContent = profile?.followers
      ? formatNumber(Number(profile.followers))
      : "—";
    fieldElements.bio.textContent = profile?.bio || "暂无公开简介";
    fieldElements.capture_status.textContent = profile?.capture_status || "idle";
    diagnosticsRefresh.hidden = diagnosticsHint.hidden = !/tiktok\.com\//i.test(location.href);
    diagnosticsText.textContent = JSON.stringify(diagnosticReport(), null, 2);

    const lookup = state.accountLookup;
    const validIdentity = hasValidProfileIdentity(profile);
    linkButton.hidden = lookup?.state !== "ACCOUNT_NOT_FOUND";
    linkButton.disabled = state.mutationPending || state.mutationOffline || !validIdentity;
    if (!lookup || lookup.state === "LOADING_PROFILE") {
      accountAwarenessText.textContent = "正在核对 KOLConnect 收录状态…";
      importButton.textContent = "正在核对…";
      importButton.disabled = true;
    } else if (lookup.state === "ACCOUNT_NOT_FOUND") {
      accountAwarenessText.textContent = "未收录。可按当前资料添加到 KOLConnect。";
      importButton.textContent = state.mutationPending && state.pendingAction === "ADD"
        ? "正在添加…"
        : state.mutationOffline ? "KOLConnect 未运行" : "添加到 KOLConnect";
      importButton.disabled = state.mutationPending
        || state.mutationOffline
        || !validIdentity
        || !state.preview?.content_category;
    } else if (lookup.state === "ACCOUNT_EXISTS") {
      const creatorName = String(lookup.creator?.display_name || "已收录达人");
      const linked = (lookup.linked_accounts || []).map((account) => (
        `${account.platform || ""} ${account.handle || account.profile_url || ""}`.trim()
      )).filter(Boolean);
      const updated = lookup.account?.updated_at ? `最近更新：${lookup.account.updated_at}` : "最近更新时间未知";
      accountAwarenessText.textContent = `已收录：${creatorName}。${linked.length ? `关联账号：${linked.join("、")}。` : ""}${updated}`;
      importButton.textContent = state.mutationPending && state.pendingAction === "UPDATE"
        ? "正在更新…"
        : state.mutationOffline ? "KOLConnect 未运行" : "更新账号";
      importButton.disabled = state.mutationPending || state.mutationOffline || !validIdentity;
    } else if (lookup.state === "AMBIGUOUS") {
      accountAwarenessText.textContent = "账号归属存在歧义，未执行自动判断。";
      importButton.textContent = "账号归属待确认";
      importButton.disabled = true;
    } else if (lookup.state === "APP_OFFLINE") {
      accountAwarenessText.textContent = "KOLConnect 未运行。请启动应用后重新分析资料。";
      importButton.textContent = "KOLConnect 未运行";
      importButton.disabled = true;
    } else {
      accountAwarenessText.textContent = "无法确认 KOLConnect 收录状态，请重新分析资料。";
      importButton.textContent = "无法确认收录状态";
      importButton.disabled = true;
    }
    renderCreatorSelector();
  };

  const missingReasons = (item) => [
    item.views?.missing_reason,
    item.likes?.missing_reason,
    item.comments?.missing_reason,
    item.published_at?.missing_reason,
    item.engagement_rate?.missing_reason
  ].filter(Boolean);

  const contentRangeLabel = (range = state.dataRange) => ({
    "items:7": "最近7条",
    "items:30": "最近30条",
    "days:7": "最近7天",
    "days:30": "最近30天"
  })[range] || "最近30条";

  const contentRangeRequest = (range = state.dataRange) => {
    const [kind, rawValue] = String(range).split(":");
    return {
      type: kind === "days" ? "last_n_days" : "last_n_posts",
      value: Number(rawValue) === 7 ? 7 : 30
    };
  };

  const contentCacheKey = () => `${state.dataRange}|pinned:${state.excludePinned}`;

  const updateAnalyzeContentButton = () => {
    const cached = state.contentAnalysisCache.has(contentCacheKey());
    analyzeContentButton.textContent = `${cached ? "重新采集" : "采集"}${contentRangeLabel()}`;
  };

  const renderContent = () => {
    updateAnalyzeContentButton();
    const analysis = state.contentAnalysis;
    contentList.replaceChildren();
    if (!analysis) {
      for (const element of Object.values(contentSummaryFields)) element.textContent = "—";
      for (const element of Object.values(coreMetricFields)) element.textContent = "—";
      coreMetricFields.followers.textContent = formatNumber(state.profile?.followers ?? null);
      contentStatus.textContent = state.contentLoading ? "正在分析…" : "尚未分析。";
      contentDetails.hidden = true;
      updateContentDiagnostic();
      renderProfile();
      return;
    }

    const view = AssistantData.selectContents(analysis.contents, {
      range: state.dataRange,
      excludePinned: state.excludePinned
    });
    const total = view.metrics.sampleCount;
    contentSummaryFields.content_type.textContent = contentTypeLabel(analysis.content_type);
    contentSummaryFields.returned_count.textContent = String(total);
    contentSummaryFields.excluded_pinned_count.textContent = String(analysis.excluded_pinned_count ?? view.excludedPinnedCount);
    contentSummaryFields.valid_views_count.textContent = `${view.metrics.validViews}/${total}`;
    contentSummaryFields.valid_publish_time_count.textContent = `${view.items.filter((item) => AssistantData.publishedTime(item) !== null).length}/${total}`;
    contentSummaryFields.valid_engagement_count.textContent = `${view.items.filter((item) => item.engagement_rate?.value != null).length}/${total}`;
    contentSummaryFields.average_views.textContent = formatNumber(view.metrics.averageViews);
    contentSummaryFields.median_views.textContent = formatNumber(view.metrics.medianViews);
    contentSummaryFields.average_likes.textContent = formatNumber(view.metrics.averageLikes);
    contentSummaryFields.coverage.textContent = `播放 ${view.metrics.validViews}/${total} · 点赞 ${view.metrics.validLikes}/${total}`;
    contentSummaryFields.weighted_engagement_rate.textContent = formatPercent(view.metrics.weightedEngagementRate);
    const coverage = analysis.range_coverage || {};
    contentSummaryFields.time_coverage.textContent = state.dataRange.startsWith("days:")
      ? `有效时间 ${analysis.known_publish_time_count ?? view.knownPublishedCount} 条 · 缺失 ${analysis.unknown_publish_time_count ?? view.missingPublishedCount} 条 · ${coverage.complete ? "时间边界已覆盖" : "覆盖不完整"}`
      : `按条数采集 · 发现 ${analysis.discovered_count || 0} 条 · 返回 ${analysis.returned_count || analysis.contents?.length || 0} 条`;
    contentSummaryFields.capture_status.textContent = analysis.capture_status || "—";
    coreMetricFields.followers.textContent = formatNumber(state.profile?.followers ?? null);
    coreMetricFields.average_views.textContent = formatNumber(view.metrics.averageViews);
    coreMetricFields.average_likes.textContent = formatNumber(view.metrics.averageLikes);
    coreMetricFields.sample_count.textContent = String(total);
    const passiveLabels = {
      CAPTURE_L1_ACTIVE: "L1 被动网络采集（高置信度）。",
      FALLBACK_L2: "L1 无可用数据，使用 L2 页面内嵌数据（中置信度）。",
      FALLBACK_L3: "L1 / L2 无可用数据，使用 L3 可见页面（低置信度）。",
      NO_DATA: "当前未观察到数据，请正常浏览后重试。",
      PARSER_ERROR: "观察到的响应无法解析，未生成有效内容。",
      CAPTCHA_DETECTED: "CAPTCHA_DETECTED：检测到验证页，采集已停止。请手动处理后重新开始采集。",
      LOGIN_REQUIRED: "LOGIN_REQUIRED：需要登录，采集已停止。请手动登录后重新开始采集。",
      CAPTURE_BLOCKED: "CAPTURE_BLOCKED：检测到安全检查，采集已停止。",
      CAPTURE_STOPPED: "CAPTURE_STOPPED：采集已停止，请重新开始采集。",
      CAPTURE_PROFILE_CHANGED: "CAPTURE_PROFILE_CHANGED：账号页面已变化，请重新分析资料。",
      CAPTURE_L1_UNAVAILABLE: "CAPTURE_L1_UNAVAILABLE：被动桥接未就绪，请更新扩展后刷新 TikTok 页面。",
    };
    const passiveState = analysis.passive_capture_status || (state.profile?.platform === "TikTok" ? String(analysis.error || "").split(":")[0] : "");
    const reasonLabels = {
      NO_CONTENT_FOUND: "未读取到符合条件的近期内容。",
      NO_USABLE_RECENT_CONTENT: "读取到内容条目，但没有可用的公开指标。",
      LOGIN_REQUIRED: "当前页面需要登录，无法读取近期内容。",
      ACCESS_RESTRICTED: "当前页面受到平台访问限制，无法读取近期内容。",
      UNSUPPORTED_STATE: "当前页面状态不支持近期内容分析。",
      CAPTURE_FAILED: "达人主页读取成功，但近期内容暂未获取到。",
    };
    contentStatus.textContent = passiveLabels[passiveState] || reasonLabels[analysis.status_reason] || (analysis.error === "CONTENT_VIEW_SUMMARY_MISMATCH"
      ? "播放统计数据不一致，请重新分析。"
      : analysis.capture_status === "success"
      ? "最近内容分析完成。"
      : analysis.capture_status === "partial_success"
        ? "已取得部分公开内容数据。"
        : analysis.capture_status === "unavailable"
          ? "当前页面没有公开足够的内容数据。"
          : "内容分析失败。");
    if (view.unknownPinnedCount || state.dataRange.startsWith("days:")) {
      const notes = [];
      if (view.unknownPinnedCount) notes.push(`${view.unknownPinnedCount} 条置顶状态未知，未按置顶排除`);
      if (state.dataRange.startsWith("days:") && (analysis.unknown_publish_time_count ?? view.missingPublishedCount)) notes.push(`${analysis.unknown_publish_time_count ?? view.missingPublishedCount} 条缺少可靠发布时间，未进入时间窗口`);
      if (state.dataRange.startsWith("days:")) {
        const days = state.dataRange.split(":")[1];
        if (!coverage.complete) notes.push(`平台边界或发布时间覆盖不足，仅展示已验证的${days}天部分结果`);
      }
      contentStatus.textContent += ` ${notes.join("；")}。`;
    }
    contentDetails.hidden = !view.items.length;
    for (const [index, item] of view.items.entries()) {
      const itemCard = create("article", "kol-content-item");
      const title = create(
        "strong",
        "kol-content-item-title",
        `${index + 1}. ${item.title || item.video_id || "未命名内容"}`
      );
      const metrics = create(
        "div",
        "kol-content-item-metrics",
        `播放 ${formatNumber(item.views?.value)} · 点赞 ${formatNumber(item.likes?.value)} · 评论 ${formatNumber(item.comments?.value)} · ${
          item.published_at?.value
            ? `发布时间 ${new Date(item.published_at.value).toLocaleDateString()}`
            : "发布时间未知"
        } · 互动率 ${formatPercent(item.engagement_rate?.value)}`
      );
      const reasons = missingReasons(item);
      const hasAuditDetails = Boolean(item.capture_layer || reasons.length);
      const auditDetails = create("details", "kol-content-provenance");
      auditDetails.append(create("summary", "", "采集详情"));
      if (hasAuditDetails) {
        const sources = [["views", "播放"], ["likes", "点赞"], ["comments", "评论"], ["published_at", "发布时间"]]
          .map(([key, label]) => `${label} ${item.field_provenance?.[key]?.layer || "—"}/${item.field_provenance?.[key]?.confidence || "missing"}`);
        const lines = [];
        if (item.capture_layer) lines.push(`来源 ${item.capture_layer} · ${sources.join(" · ")} · 观察时间 ${item.observed_at || "—"}`);
        if (reasons.length) lines.push(`缺失原因：${[...new Set(reasons)].join("；")}`);
        auditDetails.append(create("div", "kol-content-missing", lines.join("\n")));
      }
      itemCard.append(title, metrics);
      if (hasAuditDetails) itemCard.append(auditDetails);
      if (item.video_url) {
        const link = create("a", "kol-content-link", "打开内容");
        link.href = item.video_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        itemCard.append(link);
      }
      contentList.append(itemCard);
    }
    updateContentDiagnostic();
    renderProfile();
  };

  const clearProfile = () => {
    state.mutationSequence += 1;
    state.mutationPending = false;
    state.pendingAction = "";
    state.mutationOffline = false;
    state.profile = null;
    state.accountLookup = null;
    state.contentAnalysisCache.clear();
    resetCreatorSelector();
    initializePreview(null);
    renderProfile();
  };

  const clearContent = () => {
    state.contentAnalysis = null;
    state.contentLoading = false;
    analyzeContentButton.disabled = false;
    cancelContentButton.hidden = true;
    renderContent();
  };

  const showProfileStatus = (profile) => {
    const messages = {
      success: ["资料读取完成。", ""],
      partial_success: ["仅读取到部分公开资料，请检查后再导入。", "warning"],
      unavailable: ["当前页面没有可用的达人公开资料。", "warning"],
      failed: ["资料读取失败，请复制诊断报告后检查。", "error"]
    };
    const [message, tone] = messages[profile?.capture_status] || ["等待分析当前达人主页。", ""];
    setStatus(message, tone);
  };

  const profileIdentity = (profile = state.profile) => ({
    platform: String(profile?.platform || ""),
    profile_url: String(profile?.profile_url || "")
  });

  const identityMatches = (left, right) => left?.platform === right?.platform
    && left?.profile_url === right?.profile_url;

  const lookupContextCurrent = (sessionId, identity, pageUrl) => (
    profileSessions.isCurrent(sessionId)
    && state.currentSessionId === sessionId
    && location.href === pageUrl
    && identityMatches(profileIdentity(), identity)
  );

  const refreshAccountLookup = async (profile, sessionId, options = {}) => {
    const identity = profileIdentity(profile);
    const pageUrl = String(options.pageUrl || location.href);
    if (!identity.platform || !identity.profile_url) {
      if (lookupContextCurrent(sessionId, identity, pageUrl)) {
        state.accountLookup = { state: "INVALID_REQUEST" };
        renderProfile();
      }
      return false;
    }
    if (options.showLoading && lookupContextCurrent(sessionId, identity, pageUrl)) {
      state.accountLookup = { state: "LOADING_PROFILE" };
      renderProfile();
    }
    let response;
    try {
      response = await profileSessions.waitFor(
        sendMessage({ type: MESSAGE.LOOKUP_ACCOUNT, profile: identity }),
        sessionId
      );
    } catch (_) {
      response = { ok: false, code: "APP_OFFLINE" };
    }
    if (!lookupContextCurrent(sessionId, identity, pageUrl)) return false;
    state.accountLookup = response?.ok
      ? response.lookup
      : { state: response?.code === "APP_OFFLINE" ? "APP_OFFLINE" : "ERROR" };
    if (state.accountLookup?.state !== "ACCOUNT_NOT_FOUND") resetCreatorSelector();
    state.mutationOffline = response?.code === "APP_OFFLINE";
    renderProfile();
    if (state.activeTab === "contact") loadMailOptions().catch(() => {});
    return Boolean(response?.ok);
  };

  const collectProfile = async (sessionId = "") => {
    const activeSessionId = sessionId || profileSessions.begin();
    state.currentSessionId = activeSessionId;
    setStatus("正在读取当前达人公开资料…");
    fieldElements.capture_status.textContent = "collecting";
    try {
      const response = await profileSessions.waitFor(
        sendMessage({ type: MESSAGE.COLLECT, session_id: activeSessionId }),
        activeSessionId
      );
      if (!profileSessions.isCurrent(activeSessionId)) return;
      if (response?.session_id !== activeSessionId || response?.profile?.analysis_session_id !== activeSessionId) {
        return;
      }
      if (!response?.ok) throw new Error(response?.error || "Profile collection failed.");
      state.profile = response.profile;
      initializePreview(response.profile);
      state.analyzedUrl = state.lastUrl;
      state.accountLookup = { state: "LOADING_PROFILE" };
      renderProfile();
      showProfileStatus(response.profile);
      await refreshAccountLookup(response.profile, activeSessionId, {
        pageUrl: state.lastUrl,
        showLoading: false
      });
    } catch (error) {
      if (!profileSessions.isCurrent(activeSessionId)) return;
      profileSessions.invalidate();
      state.currentSessionId = profileSessions.currentSessionId;
      fieldElements.capture_status.textContent = "failed";
      if (error?.name === "AnalysisTimeoutError" || error?.message === "ANALYSIS_TIMEOUT") {
        setStatus("资料读取超时，请点击重新分析。", "error");
      } else {
        setStatus(error?.message || "资料读取失败。", "error");
      }
    }
  };

  const scheduleProfileAnalysis = (url = location.href, delay = NAVIGATION_DEBOUNCE_MS) => {
    state.lastUrl = String(url || location.href);
    const sessionId = profileSessions.begin();
    state.currentSessionId = sessionId;
    window.clearTimeout(state.analysisTimer);
    clearProfile();
    fieldElements.capture_status.textContent = "collecting";
    setStatus("页面已切换，正在重新分析…");
    state.analysisTimer = window.setTimeout(() => collectProfile(sessionId), delay);
  };

  const cancelContentAnalysis = async (showMessage = true) => {
    const wasLoading = state.contentLoading;
    contentSessions.invalidate();
    state.currentContentSessionId = contentSessions.currentSessionId;
    state.contentLoading = false;
    if (wasLoading && state.profile) {
      state.profile.videos = [];
      state.profile.video_analysis = { capture_status: "cancelled" };
    }
    analyzeContentButton.disabled = false;
    cancelContentButton.hidden = true;
    try {
      await sendMessage({ type: MESSAGE.CANCEL_CONTENT });
    } catch (_) {}
    if (wasLoading && showMessage) contentStatus.textContent = "内容分析已取消。";
  };

  const analyzeContent = async () => {
    if (!state.profile) {
      setStatus("请先等待达人基础资料读取完成。", "warning");
      return;
    }
    await cancelContentAnalysis(false);
    const sessionId = contentSessions.begin();
    const requestedRange = contentRangeRequest();
    const requestedKey = contentCacheKey();
    state.currentContentSessionId = sessionId;
    state.contentLoading = true;
    state.contentAnalysis = null;
    analyzeContentButton.disabled = true;
    if (state.profile.platform === "TikTok") { state.profile.videos = []; state.profile.video_analysis = {}; }
    cancelContentButton.hidden = false;
    contentStatus.textContent = "正在发现内容……";
    renderContent();
    try {
      const response = await contentSessions.waitFor(
        sendMessage({
          type: MESSAGE.ANALYZE_CONTENT,
          session_id: sessionId,
          range: requestedRange,
          exclude_pinned: state.excludePinned
        }),
        sessionId
      );
      if (!contentSessions.isCurrent(sessionId) || response?.session_id !== sessionId) return;
      if (!response?.ok) {
        if (response?.cancelled) {
          state.contentLoading = false;
          state.profile.videos = [];
          state.profile.video_analysis = { capture_status: "timed_out" };
          analyzeContentButton.disabled = false;
          cancelContentButton.hidden = true;
          contentStatus.textContent = "内容分析已停止或超时，请重试。";
          return;
        }
        throw new Error(response?.error || "Recent content analysis failed.");
      }
      const responseRangeKey = response.analysis?.capture_range?.key;
      if ((responseRangeKey && responseRangeKey !== state.dataRange) || requestedKey !== contentCacheKey()) return;
      state.contentAnalysis = response.analysis;
      state.contentAnalysisCache.set(requestedKey, response.analysis);
      state.contentLoading = false;
      analyzeContentButton.disabled = false;
      cancelContentButton.hidden = true;
      state.profile.videos = response.analysis?.contents || [];
      const { contents: _contents, ...summary } = response.analysis || {};
      state.profile.video_analysis = summary;
      renderContent();
    } catch (error) {
      if (!contentSessions.isCurrent(sessionId)) return;
      await cancelContentAnalysis(false);
      if (state.profile) {
        state.profile.video_analysis = {
          capture_status: error?.name === "AnalysisTimeoutError" ? "timed_out" : "failed"
        };
      }
      contentStatus.textContent = error?.name === "AnalysisTimeoutError"
        ? "内容分析超时，请稍后重试。"
        : error?.message || "内容分析失败。";
    }
  };

  const handleUrlChange = (url = location.href) => {
    const nextUrl = String(url || location.href);
    if (nextUrl === state.lastUrl) return;
    state.captureDiagnostics = null;
    state.captureDiagnosticTrace.status = "STATE_INVALIDATED";
    state.captureDiagnosticTrace.state_invalidated = true;
    state.captureDiagnosticTrace.reason = "URL_CHANGED";
    state.lastUrl = nextUrl;
    profileSessions.invalidate();
    state.currentSessionId = profileSessions.currentSessionId;
    window.clearTimeout(state.analysisTimer);
    cancelContentAnalysis(false);
    clearProfile();
    clearContent();

    if (!pageSupport.isSupportedCreatorPage(nextUrl)) {
      state.visible = false;
      root.style.display = "none";
      return;
    }

    state.dismissedUrl = "";
    state.visible = true;
    root.style.display = "block";
    checkForUpdate();
    scheduleProfileAnalysis(nextUrl);
  };

  const copyDiagnostics = async () => {
    const report = JSON.stringify(diagnosticReport(), null, 2);
    try {
      await navigator.clipboard.writeText(report);
    } catch (_) {
      const textarea = create("textarea");
      textarea.value = report;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.append(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    setStatus("诊断报告已复制。");
  };

  const copyText = async (value) => {
    try { await navigator.clipboard.writeText(value); }
    catch (_) {
      const textarea = create("textarea");
      textarea.value = value;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.append(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
  };

  const renderDiscovery = () => {
    const snapshot = state.discovery || { status: "idle", candidates: [] };
    const allCandidates = Array.isArray(snapshot.candidates) ? snapshot.candidates : [];
    const candidates = allCandidates.filter((candidate) => {
      const lookup = state.discoveryLookup.get(candidate.profile_url);
      if (state.discoveryFilter === "not_recorded") return lookup?.record_state === "not_recorded";
      if (state.discoveryFilter === "missing_email") return lookup?.email_state === "missing";
      return true;
    });
    const currentHost = new URL(location.href).hostname.toLowerCase();
    const currentPlatform = currentHost.endsWith("tiktok.com") ? "TikTok"
      : currentHost.endsWith("instagram.com") ? "Instagram" : "";
    const discoveryPlatform = snapshot.platform || currentPlatform;
    const selectedCount = allCandidates.filter((item) => state.selectedDiscoveryUrls.has(item.profile_url)).length;
    discoveryStatus.textContent = currentPlatform
      ? `${({ idle: "尚未开始", running: "采集中", paused: "已暂停", finished: "已结束" })[snapshot.status] || snapshot.status} · 已采集并去重 ${allCandidates.length} 个 · 已选择 ${selectedCount} 个${candidates.length !== allCandidates.length ? ` · 当前显示 ${candidates.length}` : ""} · 来源：${discoveryPlatform} 推荐账号区域`
      : "相似达人发现支持 TikTok 与 Instagram 达人主页。";
    discoveryStart.textContent = snapshot.status === "paused" ? "继续" : "开始发现";
    discoveryStart.disabled = state.discoveryBusy || !currentPlatform || snapshot.status === "running";
    discoveryPause.disabled = state.discoveryBusy || snapshot.status !== "running";
    discoveryFinish.disabled = state.discoveryBusy || !new Set(["running", "paused"]).has(snapshot.status);
    const rows = candidates.map((candidate) => {
      const row = create("label", "kol-discovery-row");
      const checkbox = create("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.selectedDiscoveryUrls.has(candidate.profile_url);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selectedDiscoveryUrls.add(candidate.profile_url);
        else state.selectedDiscoveryUrls.delete(candidate.profile_url);
        renderDiscovery();
      });
      const text = create("span", "", `@${candidate.username}`);
      text.title = candidate.profile_url;
      const lookup = state.discoveryLookup.get(candidate.profile_url);
      const stateText = lookup
        ? `${({ recorded: "已收录", not_recorded: "未收录", ambiguous: "待确认", invalid: "链接无效" })[lookup.record_state] || "待确认"} · ${({ present: "有邮箱", missing: "无邮箱", unknown: "邮箱未知" })[lookup.email_state] || "邮箱未知"}`
        : "收录与邮箱状态待查询";
      const badge = create("small", "kol-discovery-state", stateText);
      const seedNames = (candidate.seed_urls || []).map((url) => {
        try { return new URL(url).pathname.split("/").filter(Boolean).at(-1)?.replace(/^@/, ""); }
        catch (_) { return ""; }
      }).filter(Boolean);
      const firstObserved = candidate.first_observed_at || candidate.observed_at;
      const evidence = create("small", "kol-discovery-evidence",
        `来源达人 ${seedNames.length ? seedNames.map((name) => `@${name}`).join("、") : "未知"} · ${candidate.platform || discoveryPlatform} 推荐账号区域 · 首次发现 ${firstObserved ? new Date(firstObserved).toLocaleString() : "未知"}`);
      const details = create("span", "kol-discovery-candidate");
      details.append(text, badge, evidence);
      row.append(checkbox, details);
      return row;
    });
    discoveryList.replaceChildren(...rows);
    discoverySelectAll.textContent = selectedCount === allCandidates.length && allCandidates.length ? "取消全选" : `全选全部 (${allCandidates.length})`;
    discoveryCopyAll.textContent = `复制全部 (${allCandidates.length})`;
    discoveryCopy.textContent = `复制已选择 (${selectedCount})`;
    discoveryCsvAll.textContent = `导出全部 (${allCandidates.length})`;
    discoveryCsv.textContent = `导出已选择 (${selectedCount})`;
    discoveryHandoff.textContent = `移交已选择 (${selectedCount})`;
    for (const button of [discoveryCopyAll, discoveryCsvAll]) button.disabled = state.discoveryBusy || !allCandidates.length;
    for (const button of [discoveryCopy, discoveryCsv, discoveryHandoff]) button.disabled = state.discoveryBusy || !selectedCount;
  };

  const selectedDiscoveryCandidates = () => (state.discovery?.candidates || [])
    .filter((candidate) => state.selectedDiscoveryUrls.has(candidate.profile_url));

  const exportDiscoveryCsv = (candidates, scope) => {
    const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const lines = ["platform,profile_url,username,seed_url,recommendation_source,first_observed_at,last_observed_at", ...candidates.map((item) => [
      item.platform || state.discovery?.platform || "", item.profile_url, item.username, (item.seed_urls || []).join(" | "), item.recommendation_source,
      item.first_observed_at || item.observed_at, item.last_observed_at || item.observed_at
    ].map(escape).join(","))];
    const blob = new Blob(["\uFEFF", lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = create("a");
    link.href = url;
    link.download = `KOLConnect_similar_creators_${scope}_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    setStatus(`已导出 ${candidates.length} 个${scope === "all" ? "全部" : "已选择"}候选。`);
  };

  const lookupDiscoveryCandidates = async () => {
    const candidates = state.discovery?.candidates || [];
    if (!candidates.length || state.discoveryBusy) return;
    state.discoveryBusy = true;
    renderDiscovery();
    try {
      const response = await sendMessage({
        type: MESSAGE.LOOKUP_DISCOVERY_CANDIDATES,
        profile_urls: candidates.map((item) => item.profile_url)
      });
      if (!response?.ok || !Array.isArray(response.result?.candidates)) throw new Error("LOOKUP_FAILED");
      state.discoveryLookup = new Map(response.result.candidates.map((item) => [item.input_url, item]));
      setStatus("已按 KOLConnect CreatorAccount authority 更新候选状态。");
    } catch (_) {
      state.discoveryLookup = new Map();
      setStatus("暂无法查询收录状态；不会把未知候选标记为未收录。", "warning");
    } finally {
      state.discoveryBusy = false;
      renderDiscovery();
    }
  };

  const runDiscoveryAction = async (action) => {
    if (!SimilarDiscovery || state.discoveryBusy) return;
    state.discoveryBusy = true;
    renderDiscovery();
    try {
      const result = await action();
      if (result?.ok === false) {
        const messages = {
          SUPPORTED_PROFILE_REQUIRED: "请先打开 TikTok 或 Instagram 达人主页。",
          RECOMMENDATION_REGION_NOT_FOUND: "未识别到平台推荐账号区域，请先由用户打开或滚动到推荐列表。",
          TIKTOK_PROFILE_REQUIRED: "请先打开 TikTok 达人主页。",
          RECOMMENDATION_MODAL_NOT_FOUND: "未识别到平台推荐账号区域，请先由用户打开平台推荐列表。"
        };
        setStatus(messages[result.code] || "相似达人发现暂不可用。", "warning");
      }
    } finally {
      state.discoveryBusy = false;
      renderDiscovery();
    }
  };

  const selectedMailTemplate = () => (state.mailOptions?.templates || [])
    .find((item) => item.template_id === templateAuthoritySelect.value);

  const mailRequestPayload = () => {
    syncPreviewState();
    const template = selectedMailTemplate();
    return {
      platform: state.profile?.platform || "",
      profile_url: state.profile?.profile_url || "",
      recipient_email: String(state.preview?.email || "").trim(),
      creator_name: String(state.profile?.fields?.creator_name?.value || state.profile?.username || "").trim(),
      audience_type: tierSelect.value.toLowerCase(),
      language: String(state.preview?.language || "").trim(),
      template_id: template?.template_id || "",
      template_version: template?.template_version,
      mail_account_id: mailAccountSelect.value
    };
  };

  const renderMailOptions = () => {
    const priorTemplate = templateAuthoritySelect.value;
    const priorAccount = mailAccountSelect.value;
    const unavailable = state.mailOptionsState === "offline";
    const loading = state.mailOptionsState === "loading";
    const templatePlaceholder = unavailable ? "请先启动 KOLConnect" : loading ? "正在加载邮件模板…" : "请选择邮件模板";
    const accountPlaceholder = unavailable ? "请先启动 KOLConnect" : loading ? "正在加载发送邮箱…" : "请选择已启用邮箱";
    templateAuthoritySelect.replaceChildren(new Option(templatePlaceholder, ""));
    for (const item of state.mailOptions?.templates || []) {
      templateAuthoritySelect.add(new Option(item.name, item.template_id));
    }
    if ((state.mailOptions?.templates || []).some((item) => item.template_id === priorTemplate)) templateAuthoritySelect.value = priorTemplate;
    mailAccountSelect.replaceChildren(new Option(accountPlaceholder, ""));
    for (const item of state.mailOptions?.mail_accounts || []) {
      mailAccountSelect.add(new Option(`${item.name || item.email} · ${item.email}`, item.mail_account_id));
    }
    if ((state.mailOptions?.mail_accounts || []).some((item) => item.mail_account_id === priorAccount)) mailAccountSelect.value = priorAccount;
    templateAuthoritySelect.disabled = loading || !(state.mailOptions?.templates || []).length;
    mailAccountSelect.disabled = loading || !(state.mailOptions?.mail_accounts || []).length;
    retryMailOptionsButton.hidden = !new Set(["offline", "error"]).has(state.mailOptionsState);
    openMailButton.disabled = state.mailDraftPending || !templateAuthoritySelect.value || !mailAccountSelect.value;
    if (!(state.mailOptions?.templates || []).length) mailHint.textContent = "没有适用模板。请进入模板管理创建对应分级与语言的模板。";
  };

  const loadMailOptions = async () => {
    const generation = ++state.mailOptionsGeneration;
    state.mailTemplatePreview = null;
    mailTemplatePreview.hidden = true;
    const audience = tierSelect.value.toLowerCase();
    const language = String(state.preview?.language || "").trim();
    if (!state.profile || !audience || !language || state.accountLookup?.state !== "ACCOUNT_EXISTS") {
      state.mailOptions = null;
      state.mailOptionsState = "idle";
      renderMailOptions();
      return;
    }
    state.mailOptionsState = "loading";
    renderMailOptions();
    mailHint.textContent = "正在读取 KOLConnect 邮件模板…";
    const response = await sendMessage({
      type: MESSAGE.LOAD_MAIL_OPTIONS,
      query: { platform: state.profile.platform, profile_url: state.profile.profile_url, audience_type: audience, language }
    });
    if (generation !== state.mailOptionsGeneration) return;
    if (!response?.ok) {
      state.mailOptions = null;
      state.mailOptionsState = response?.code === "APP_OFFLINE" ? "offline" : "error";
      renderMailOptions();
      mailHint.textContent = state.mailOptionsState === "offline"
        ? "请先启动 KOLConnect。邮件模板和发送邮箱当前不可用，已编辑的联系人信息会保留。"
        : "邮件配置暂不可用，请重试或检查账号配置。";
      return;
    }
    state.mailOptions = response.result;
    state.mailOptionsState = "ready";
    const authoritativeEmail = String(state.mailOptions?.identity?.account_email || "").trim();
    if (authoritativeEmail && !state.previewDirty.has("email")) {
      state.preview.email = authoritativeEmail;
      previewInputs.email.value = authoritativeEmail;
      renderProfile();
    }
    renderMailOptions();
    mailHint.textContent = (state.mailOptions.templates || []).length
      ? "请选择模板和发送邮箱。创建后只保存草稿，不会自动发送。"
      : "没有适用模板。请进入模板管理创建对应分级与语言的模板。";
  };

  const previewSelectedMailTemplate = async () => {
    const payload = mailRequestPayload();
    if (!payload.template_id) {
      state.mailTemplatePreview = null;
      mailTemplatePreview.hidden = true;
      renderMailOptions();
      return;
    }
    const response = await sendMessage({ type: MESSAGE.PREVIEW_MAIL_TEMPLATE, payload });
    if (!response?.ok) {
      state.mailTemplatePreview = null;
      mailTemplatePreview.hidden = true;
      setStatus("模板无法预览，请检查达人称呼、语言和模板变量。", "warning");
      return;
    }
    state.mailTemplatePreview = response.result.rendered;
    mailTemplatePreviewTitle.textContent = `主题：${response.result.rendered.subject}`;
    mailTemplatePreviewGreeting.textContent = String(response.result.rendered.body || "").split(/\r?\n/)[0] || "正文已生成";
    mailTemplatePreview.hidden = false;
    renderMailOptions();
  };

  const handoffMailWorkspace = async (context) => {
    const response = await sendMessage({ type: MESSAGE.OPEN_MAIL_WORKSPACE, context });
    if (!response?.ok) throw new Error(response?.code || "MAIL_HANDOFF_FAILED");
  };

  const openMailWorkspace = async (manageOnly = false) => {
    syncPreviewState();
    const email = String(state.preview?.email || "").trim();
    const creatorName = String(state.profile?.fields?.creator_name?.value || state.profile?.username || "").trim();
    if (!manageOnly && (!email || !creatorName)) {
      setStatus("请先确认达人称呼和有效 Email。", "warning");
      activateTab("contact");
      return;
    }
    openMailButton.disabled = true;
    try {
      if (manageOnly) {
        await handoffMailWorkspace({
          creatorId: state.accountLookup?.creator?.creator_id || "",
          creatorName: creatorName || "模板管理",
          recipientEmail: email,
          language: String(state.preview?.language || "en"),
          creatorTier: tierSelect.value,
          mode: "manage_templates"
        });
        setStatus("已打开 Mail Workspace 模板管理。模板 authority 仍由桌面应用维护。");
        return;
      }
      const payload = { ...mailRequestPayload(), idempotency_key: crypto.randomUUID() };
      if (!payload.template_id || !payload.mail_account_id) throw new Error("MAIL_SELECTION_REQUIRED");
      state.mailDraftPending = true;
      const response = await sendMessage({ type: MESSAGE.CREATE_MAIL_DRAFT, payload });
      if (!response?.ok || !response.result?.draft?.draft_id) throw new Error(response?.code || "MAIL_DRAFT_CREATE_FAILED");
      await handoffMailWorkspace({
        creatorId: response.result.identity?.creator_id || "", creatorName,
        recipientEmail: email, language: payload.language, creatorTier: tierSelect.value,
        mode: "draft", draftId: response.result.draft.draft_id,
        templateName: selectedMailTemplate()?.name || ""
      });
      setStatus("邮件草稿已持久化并在 Mail Workspace 打开；不会自动发送。");
    } catch (error) {
      const message = error?.message === "MAIL_SELECTION_REQUIRED"
        ? "请先选择邮件模板和发送邮箱。"
        : error?.message === "APP_OFFLINE"
          ? "KOLConnect 本地服务未运行，未打开无效模板页面。请启动应用后重试。"
          : manageOnly
            ? "模板管理暂不可用，未打开无效页面。请检查 KOLConnect 本地服务。"
            : "草稿创建失败，当前 Contact 输入已保留，请检查账号、模板版本和本地服务。";
      setStatus(message, "error");
    } finally {
      state.mailDraftPending = false;
      renderMailOptions();
    }
  };

  const mutationContextCurrent = (context) => (
    context.sequence === state.mutationSequence
    && lookupContextCurrent(context.sessionId, context.identity, context.pageUrl)
  );

  const mutationWarnings = (result) => {
    const warnings = Array.isArray(result?.warnings) ? result.warnings : [];
    const hasEmailConflict = warnings.some((warning) => warning?.code === "EMAIL_CONFLICT_PRESERVED");
    const hasUnknown = warnings.some((warning) => warning?.code !== "EMAIL_CONFLICT_PRESERVED");
    if (hasEmailConflict) return "检测到不同的邮箱，已保留 KOLConnect 中的现有邮箱。";
    return hasUnknown ? "部分资料已按 KOLConnect 现有数据保护规则保留。" : "";
  };

  const mutateCurrent = async () => {
    syncPreviewState();
    const action = mutationAction();
    if (state.mutationPending) return;
    if (!state.profile || !hasValidProfileIdentity()) {
      setStatus("请先分析当前达人主页。", "warning");
      return;
    }
    if (!action) {
      setStatus("请先等待 KOLConnect 收录状态核对完成。", "warning");
      return;
    }
    if (action === "ADD" && !state.preview?.content_category) {
      setStatus("请选择 Content Category 后再添加。", "warning");
      return;
    }
    if (action === "ADD") resetCreatorSelector();
    const context = {
      sequence: state.mutationSequence + 1,
      sessionId: state.currentSessionId,
      pageUrl: location.href,
      identity: profileIdentity()
    };
    state.mutationSequence = context.sequence;
    state.mutationPending = true;
    state.pendingAction = action;
    state.mutationOffline = false;
    renderProfile();
    setStatus(action === "ADD" ? "正在添加…" : "正在更新…");
    try {
      const response = await sendMessage({
        type: action === "ADD" ? MESSAGE.ADD_ACCOUNT : MESSAGE.UPDATE_ACCOUNT,
        profile: profileForMutation(),
        session_id: context.sessionId,
        identity: context.identity
      });
      if (!mutationContextCurrent(context)) return;
      if (!response?.ok) {
        const code = String(response?.code || "MUTATION_FAILED");
        if (code === "ACCOUNT_ALREADY_EXISTS" && action === "ADD") {
          setStatus("账号已存在，已刷新收录状态", "warning");
          await refreshAccountLookup(state.profile, context.sessionId, { pageUrl: context.pageUrl });
          return;
        }
        if (code === "ACCOUNT_NOT_FOUND" && action === "UPDATE") {
          setStatus("账号记录已不存在，已刷新收录状态", "warning");
          await refreshAccountLookup(state.profile, context.sessionId, { pageUrl: context.pageUrl });
          return;
        }
        if (code === "AMBIGUOUS") {
          setStatus("账号归属存在歧义，未执行操作。", "warning");
          await refreshAccountLookup(state.profile, context.sessionId, { pageUrl: context.pageUrl });
          return;
        }
        if (code === "APP_OFFLINE") {
          state.mutationOffline = true;
          setStatus("KOLConnect 未运行。请启动应用后重新分析资料。", "error");
          return;
        }
        const safeErrors = {
          EXPLICIT_ACTION_REQUIRED: "操作请求无效，请重新分析后再试。",
          VALIDATION_ERROR: "当前资料未通过校验，请检查后再试。"
        };
        setStatus(safeErrors[code] || "KOLConnect 操作失败，请稍后重试。", "error");
        return;
      }
      if (response.session_id !== context.sessionId || !identityMatches(response.identity, context.identity)) return;
      const warning = mutationWarnings(response.result);
      setStatus(`${action === "ADD" ? "添加成功" : "更新成功"}${warning ? `。${warning}` : ""}`, warning ? "warning" : "");
      await refreshAccountLookup(state.profile, context.sessionId, { pageUrl: context.pageUrl });
    } catch (_) {
      if (!mutationContextCurrent(context)) return;
      state.mutationOffline = true;
      setStatus("KOLConnect 未运行。请启动应用后重新分析资料。", "error");
    } finally {
      if (context.sequence === state.mutationSequence) {
        state.mutationPending = false;
        state.pendingAction = "";
        renderProfile();
      }
    }
  };

  const linkSelectedCreator = async () => {
    if (state.mutationPending || !selectorContextCurrent() || !hasValidProfileIdentity()) return;
    const selectedId = state.selectedCreatorId;
    if (!selectedId || !state.creatorSearchResults.some((row) => row.creator_id === selectedId)) return;
    const context = {
      sequence: state.mutationSequence + 1,
      sessionId: state.currentSessionId,
      pageUrl: location.href,
      identity: profileIdentity()
    };
    state.mutationSequence = context.sequence;
    state.mutationPending = true;
    state.pendingAction = "LINK_EXISTING_CREATOR";
    renderProfile();
    try {
      // Recheck the authoritative account state before sending the explicit link.
      const checked = await refreshAccountLookup(state.profile, context.sessionId, { pageUrl: context.pageUrl });
      if (!mutationContextCurrent(context)) return;
      if (!checked || !selectorContextCurrent()) {
        resetCreatorSelector();
        setStatus("账号状态已变化，请重新分析后再关联。", "warning");
        return;
      }
      const response = await sendMessage({
        type: MESSAGE.LINK_EXISTING_CREATOR,
        creator_id: selectedId,
        session_id: context.sessionId,
        identity: context.identity
      });
      if (!mutationContextCurrent(context)) return;
      if (!response?.ok) {
        const code = String(response?.code || "LINK_FAILED");
        const messages = {
          CREATOR_NOT_FOUND: "所选 Creator 已不存在，请重新搜索。",
          CREATOR_ARCHIVED: "所选 Creator 已归档，请重新选择。",
          ACCOUNT_IDENTITY_INVALID: "当前账号身份无效，请重新分析。",
          ACCOUNT_IDENTITY_AMBIGUOUS: "账号身份存在歧义，未执行关联。",
          ACCOUNT_IDENTITY_STALE: "页面账号身份已变化，请重新分析。",
          ACCOUNT_IDENTITY_CONFLICT: "账号身份与现有记录冲突，未执行关联。",
          ACCOUNT_OWNED_BY_OTHER_CREATOR: "账号已属于其他 Creator；本阶段不支持重新关联。",
          APP_OFFLINE: "KOLConnect 未运行，请启动后重试。"
        };
        setStatus(messages[code] || "关联未完成，请稍后重试。", "warning");
        resetCreatorSelector();
        if (code !== "APP_OFFLINE") await refreshAccountLookup(state.profile, context.sessionId, { pageUrl: context.pageUrl });
        return;
      }
      if (response.session_id !== context.sessionId || !identityMatches(response.identity, context.identity)
          || response.result?.creator_id !== selectedId) return;
      resetCreatorSelector();
      setStatus("关联完成，正在刷新收录状态…");
      await refreshAccountLookup(state.profile, context.sessionId, { pageUrl: context.pageUrl });
      if (mutationContextCurrent(context) && state.accountLookup?.state === "ACCOUNT_EXISTS") {
        setStatus("已关联到所选 Creator。");
      }
    } catch (_) {
      if (!mutationContextCurrent(context)) return;
      resetCreatorSelector();
      setStatus("KOLConnect 暂不可用，未确认关联结果。", "error");
    } finally {
      if (context.sequence === state.mutationSequence) {
        state.mutationPending = false;
        state.pendingAction = "";
        renderProfile();
      }
    }
  };

  const open = (manual = false) => {
    if (!pageSupport.isSupportedCreatorPage(location.href)) return;
    if (!manual && state.dismissedUrl === location.href) return;
    if (manual) state.dismissedUrl = "";
    state.visible = true;
    root.style.display = "block";
    checkForUpdate();
    if (!state.profile || state.analyzedUrl !== location.href) {
      scheduleProfileAnalysis(location.href, 0);
    }
  };

  const close = () => {
    state.dismissedUrl = location.href;
    state.visible = false;
    root.style.display = "none";
    resetCreatorSelector();
    cancelContentAnalysis(false);
  };

  const toggle = () => {
    if (state.visible) close();
    else open(true);
  };

  refreshButton.addEventListener("click", () => scheduleProfileAnalysis(location.href, 0));
  analyzeContentButton.addEventListener("click", analyzeContent);
  cancelContentButton.addEventListener("click", () => cancelContentAnalysis(true));
  copyButton.addEventListener("click", copyDiagnostics);
  importButton.addEventListener("click", mutateCurrent);
  linkButton.addEventListener("click", openCreatorSelector);
  creatorSearchButton.addEventListener("click", () => searchCreatorLibrary(1));
  creatorSearchInput.addEventListener("input", () => {
    state.selectedCreatorId = "";
    state.creatorSearchResults = [];
    state.creatorSearchPage = 0;
    state.creatorSearchPages = 0;
    state.creatorSelectorGeneration += 1;
    state.creatorSearchLoading = false;
    state.creatorSearchError = "";
    renderCreatorSelector();
  });
  creatorPlatformFilter.addEventListener("change", () => {
    state.creatorPlatformFilter = creatorPlatformFilter.value;
    state.selectedCreatorId = "";
    renderCreatorSelector();
  });
  creatorSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchCreatorLibrary(1);
  });
  creatorLoadMoreButton.addEventListener("click", () => searchCreatorLibrary(state.creatorSearchPage + 1));
  creatorConfirmButton.addEventListener("click", linkSelectedCreator);
  creatorCancelButton.addEventListener("click", resetCreatorSelector);
  toDataButton.addEventListener("click", () => activateTab("data"));
  toContactButton.addEventListener("click", () => activateTab("contact"));
  dataRangeSelect.addEventListener("change", () => {
    state.dataRange = dataRangeSelect.value;
    cancelContentAnalysis(false).catch(() => {});
    state.contentAnalysis = state.contentAnalysisCache.get(contentCacheKey()) || null;
    renderContent();
  });
  pinnedInput.addEventListener("change", () => {
    state.excludePinned = pinnedInput.checked;
    cancelContentAnalysis(false).catch(() => {});
    state.contentAnalysis = state.contentAnalysisCache.get(contentCacheKey()) || null;
    renderContent();
  });
  tierSelect.addEventListener("change", () => {
    state.creatorTier = tierSelect.value;
    loadMailOptions().catch(() => {});
  });
  templateAuthoritySelect.addEventListener("change", () => previewSelectedMailTemplate().catch(() => {}));
  mailAccountSelect.addEventListener("change", () => previewSelectedMailTemplate().catch(() => {}));
  openMailButton.addEventListener("click", () => openMailWorkspace(false));
  manageTemplatesButton.addEventListener("click", () => openMailWorkspace(true));
  retryMailOptionsButton.addEventListener("click", () => loadMailOptions().catch(() => {}));
  discoveryStart.addEventListener("click", () => runDiscoveryAction(
    state.discovery?.status === "paused" ? () => SimilarDiscovery.resume() : () => SimilarDiscovery.start()
  ));
  discoveryPause.addEventListener("click", () => runDiscoveryAction(() => SimilarDiscovery.pause()));
  discoveryFinish.addEventListener("click", () => runDiscoveryAction(() => SimilarDiscovery.finish()));
  discoveryLookupButton.addEventListener("click", () => lookupDiscoveryCandidates());
  discoveryFilterSelect.addEventListener("change", () => {
    state.discoveryFilter = discoveryFilterSelect.value;
    renderDiscovery();
  });
  discoverySelectAll.addEventListener("click", () => {
    const candidates = state.discovery?.candidates || [];
    const allSelected = candidates.length && candidates.every((item) => state.selectedDiscoveryUrls.has(item.profile_url));
    state.selectedDiscoveryUrls = new Set(allSelected ? [] : candidates.map((item) => item.profile_url));
    renderDiscovery();
  });
  discoveryCopyAll.addEventListener("click", async () => {
    const candidates = state.discovery?.candidates || [];
    await copyText(candidates.map((item) => item.profile_url).join("\n"));
    setStatus(`已复制全部 ${candidates.length} 个达人主页链接。`);
  });
  discoveryCopy.addEventListener("click", async () => {
    const candidates = selectedDiscoveryCandidates();
    await copyText(candidates.map((item) => item.profile_url).join("\n"));
    setStatus(`已复制已选择的 ${candidates.length} 个达人主页链接。`);
  });
  discoveryCsvAll.addEventListener("click", () => exportDiscoveryCsv(state.discovery?.candidates || [], "all"));
  discoveryCsv.addEventListener("click", () => exportDiscoveryCsv(selectedDiscoveryCandidates(), "selected"));
  discoveryHandoff.addEventListener("click", async () => {
    const candidates = selectedDiscoveryCandidates();
    if (!candidates.length || !confirm(`确认将 ${candidates.length} 个链接移交到现有发现达人任务？任务只会创建，不会自动启动抓取。`)) return;
    state.discoveryBusy = true;
    renderDiscovery();
    try {
      const response = await sendMessage({
        type: MESSAGE.CREATE_DISCOVERY_TASK,
        profile_urls: candidates.map((item) => item.profile_url),
        seed_url: state.discovery?.seed_url || "",
        platform: state.discovery?.platform || candidates[0]?.platform || ""
      });
      if (!response?.ok) throw new Error(response?.code || "DISCOVERY_TASK_FAILED");
      const task = response.result?.task || {};
      const acceptedCount = Number(task.valid_count);
      const invalidCount = Number(task.invalid_count);
      if (Number.isFinite(acceptedCount) && acceptedCount !== candidates.length) {
        setStatus(`任务已创建，但仅接受 ${acceptedCount}/${candidates.length} 个候选${Number.isFinite(invalidCount) && invalidCount > 0 ? `；${invalidCount} 个链接无法规范化` : ""}。请检查任务后再手动启动。`, "error");
      } else {
        setStatus(`发现达人任务已创建，共移交 ${candidates.length} 个已选择候选。请在 KOLConnect 中确认并手动启动抓取。`);
      }
    } catch (_) { setStatus("任务移交失败，请确认 KOLConnect 已启动。", "error"); }
    finally { state.discoveryBusy = false; renderDiscovery(); }
  });
  for (const [name, input] of Object.entries(previewInputs)) {
    input.addEventListener("input", () => {
      syncPreviewState(name);
      if (name === "language") loadMailOptions().catch(() => {});
    });
    input.addEventListener("change", () => {
      syncPreviewState(name);
      if (name === "language") loadMailOptions().catch(() => {});
    });
  }
  closeButton.addEventListener("click", close);
  minimizeButton.addEventListener("click", () => {
    state.minimized = !state.minimized;
    root.classList.toggle("kol-minimized", state.minimized);
  });

  let drag = null;
  head.addEventListener("pointerdown", (event) => {
    if (event.target instanceof HTMLButtonElement) return;
    const box = root.getBoundingClientRect();
    drag = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      left: box.left,
      top: box.top
    };
    head.setPointerCapture(event.pointerId);
  });
  head.addEventListener("pointermove", (event) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const left = Math.max(0, Math.min(innerWidth - 220, drag.left + event.clientX - drag.x));
    const top = Math.max(0, Math.min(innerHeight - 48, drag.top + event.clientY - drag.y));
    root.style.left = `${left}px`;
    root.style.top = `${top}px`;
    root.style.right = "auto";
  });
  head.addEventListener("pointerup", () => {
    drag = null;
  });
  for (const eventName of ["click", "dblclick", "mousedown", "mouseup", "pointerdown", "pointerup", "wheel", "keydown"]) {
    root.addEventListener(eventName, (event) => event.stopPropagation());
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === MESSAGE.OPEN) {
      toggle();
    } else if (message?.type === MESSAGE.PAGE_CHANGED) {
      handleUrlChange(message.url);
    } else if (message?.type === MESSAGE.CONTENT_PROGRESS) {
      if (!contentSessions.isCurrent(message.session_id)) return;
      const progress = message.progress || {};
      if (progress.phase === "discovering") {
        contentStatus.textContent = "正在发现内容……";
      } else if (progress.phase === "discovered") {
        contentStatus.textContent = `已找到 ${progress.discovered || 0} 条，排除置顶 ${progress.excludedPinned || 0} 条`;
      } else if (progress.phase === "details") {
        contentStatus.textContent = `正在读取 ${progress.current || 0}/${progress.total || 0}`;
      } else if (progress.phase === "calculating") {
        contentStatus.textContent = "正在计算结果……";
      }
    } else if (message?.type === MESSAGE.ERROR) {
      profileSessions.invalidate();
      fieldElements.capture_status.textContent = "failed";
      setStatus(message.error || "资料读取失败。", "error");
    }
  });

  window.addEventListener("popstate", () => handleUrlChange(location.href));
  window.addEventListener("hashchange", () => handleUrlChange(location.href));
  window.setInterval(() => handleUrlChange(location.href), URL_CHECK_INTERVAL_MS);

  globalThis[GLOBAL_KEY] = {
    open,
    close,
    toggle,
    collect: () => scheduleProfileAnalysis(location.href, 0),
    analyzeContent,
    cancelContentAnalysis,
    handleUrlChange,
    root,
    state,
    previewInputs,
    mutateCurrent,
    openCreatorSelector,
    searchCreatorLibrary,
    linkSelectedCreator,
    initializePreview,
    profileForMutation,
    agencyStatus,
    getCaptureDiagnostics,
    refreshCaptureDiagnostics
  };

  loadAgencyOptions();
  renderTabs();
  renderDiscovery();
  SimilarDiscovery?.subscribe?.((snapshot) => {
    state.discovery = snapshot;
    const available = new Set(snapshot.candidates.map((item) => item.profile_url));
    state.selectedDiscoveryUrls = new Set([...state.selectedDiscoveryUrls].filter((url) => available.has(url)));
    renderDiscovery();
  });

  if (pageSupport.isSupportedCreatorPage(location.href)) {
    open();
  }
})();
