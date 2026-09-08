(() => {
  const GLOBAL_KEY = "__KOLCONNECT_NEXT_ASSISTANT__";
  const ROOT_ID = "kolconnect-next-root";
  if (globalThis[GLOBAL_KEY]) return;

  const MESSAGE = {
    OPEN: "KOLCONNECT_NEXT_OPEN",
    ERROR: "KOLCONNECT_NEXT_ERROR",
    COLLECT: "KOLCONNECT_NEXT_COLLECT",
    IMPORT: "KOLCONNECT_NEXT_IMPORT",
    LOAD_AGENCIES: "KOLCONNECT_NEXT_LOAD_AGENCIES",
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
    preview: null
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
  const brand = create("span", "kol-brand", "KOLConnect v1.0.0");
  const minimizeButton = create("button", "kol-icon-button", "−");
  const closeButton = create("button", "kol-icon-button", "×");
  minimizeButton.type = "button";
  minimizeButton.title = "最小化";
  closeButton.type = "button";
  closeButton.title = "关闭";
  head.append(brand, minimizeButton, closeButton);

  const body = create("main", "kol-body");
  const status = create("div", "kol-status", "等待分析当前达人主页。");
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

  const contentSection = create("section", "kol-content-section");
  contentSection.append(create("h3", "kol-section-title", "最近内容分析"));
  const contentStatus = create("div", "kol-content-status", "尚未分析。");
  const contentSummary = create("div", "kol-content-summary");
  const contentSummaryFields = {};
  const summaryLabels = {
    content_type: "内容类型",
    returned_count: "最近内容数量",
    excluded_pinned_count: "排除置顶数量",
    valid_views_count: "有效播放数据",
    valid_publish_time_count: "有效发布时间",
    valid_engagement_count: "有效互动率",
    average_views: "平均播放",
    median_views: "中位播放",
    weighted_engagement_rate: "综合互动率",
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
  const contentDetails = create("details", "kol-content-details");
  contentDetails.append(create("summary", "", "查看内容明细"));
  const contentList = create("div", "kol-content-list");
  contentDetails.append(contentList);
  contentSection.append(
    contentStatus,
    contentSummary,
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
  const analyzeContentButton = create("button", "", "分析最近30条");
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
  for (const button of [
    refreshButton,
    analyzeContentButton,
    cancelContentButton,
    copyButton,
    importButton
  ]) {
    button.type = "button";
  }
  cancelContentButton.hidden = true;
  importButton.disabled = true;
  actions.append(refreshButton, analyzeContentButton, cancelContentButton, copyButton, importButton);
  body.append(status, card, previewSection, contentSection, diagnostics, actions);
  panel.append(head, body);
  root.append(panel);
  document.documentElement.append(root);

  const setStatus = (text, tone = "") => {
    status.textContent = text;
    status.dataset.tone = tone;
  };

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
      if (!response?.ok) throw new Error(response?.error || "Agency list unavailable.");
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
    } catch (_) {
      agencySelect.replaceChildren(emptyAgency);
      agencySelect.value = "";
      agencySelect.disabled = true;
      agencyStatus.textContent = "Agency 暂不可用，不影响导入";
    }
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

  const syncPreviewState = () => {
    if (!state.preview) return;
    for (const [name, input] of Object.entries(previewInputs)) {
      state.preview[name] = String(input.value || "").trim();
    }
    importButton.disabled = !state.profile || !state.preview.content_category;
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
    importButton.disabled = !state.profile || !state.preview?.content_category;
  };

  const profileForImport = () => ({
    ...state.profile,
    email: state.preview?.email || "",
    whatsapp: state.preview?.whatsapp || "",
    country: state.preview?.country || "",
    language: state.preview?.language || "",
    content_category: state.preview?.content_category || "",
    agency_id: state.preview?.agency_id || ""
  });

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
  };

  const missingReasons = (item) => [
    item.views?.missing_reason,
    item.likes?.missing_reason,
    item.comments?.missing_reason,
    item.published_at?.missing_reason,
    item.engagement_rate?.missing_reason
  ].filter(Boolean);

  const renderContent = () => {
    const analysis = state.contentAnalysis;
    contentList.replaceChildren();
    if (!analysis) {
      for (const element of Object.values(contentSummaryFields)) element.textContent = "—";
      contentStatus.textContent = state.contentLoading ? "正在分析…" : "尚未分析。";
      contentDetails.hidden = true;
      updateContentDiagnostic();
      renderProfile();
      return;
    }

    const total = analysis.returned_count || 0;
    contentSummaryFields.content_type.textContent = contentTypeLabel(analysis.content_type);
    contentSummaryFields.returned_count.textContent = String(total);
    contentSummaryFields.excluded_pinned_count.textContent = String(analysis.excluded_pinned_count || 0);
    contentSummaryFields.valid_views_count.textContent = `${analysis.valid_views_count || 0}/${total}`;
    contentSummaryFields.valid_publish_time_count.textContent = `${analysis.valid_publish_time_count || 0}/${total}`;
    contentSummaryFields.valid_engagement_count.textContent = `${analysis.valid_engagement_count || 0}/${total}`;
    contentSummaryFields.average_views.textContent = formatNumber(analysis.average_views);
    contentSummaryFields.median_views.textContent = formatNumber(analysis.median_views);
    contentSummaryFields.weighted_engagement_rate.textContent = formatPercent(analysis.weighted_engagement_rate);
    contentSummaryFields.capture_status.textContent = analysis.capture_status || "—";
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
    contentStatus.textContent = passiveLabels[passiveState] || (analysis.error === "CONTENT_VIEW_SUMMARY_MISMATCH"
      ? "播放统计数据不一致，请重新分析。"
      : analysis.capture_status === "success"
      ? "最近内容分析完成。"
      : analysis.capture_status === "partial_success"
        ? "已取得部分公开内容数据。"
        : analysis.capture_status === "unavailable"
          ? "当前页面没有公开足够的内容数据。"
          : "内容分析失败。");
    contentDetails.hidden = !analysis.contents?.length;
    for (const [index, item] of (analysis.contents || []).entries()) {
      const itemCard = create("article", "kol-content-item");
      const title = create(
        "strong",
        "kol-content-item-title",
        `${index + 1}. ${item.title || item.video_id || "未命名内容"}`
      );
      const metrics = create(
        "div",
        "kol-content-item-metrics",
        `播放 ${formatNumber(item.views?.value)} · 发布时间 ${
          item.published_at?.value
            ? new Date(item.published_at.value).toLocaleDateString()
            : "—"
        } · 互动率 ${formatPercent(item.engagement_rate?.value)}`
      );
      const reasons = missingReasons(item);
      if (item.capture_layer) {
        const sources = [["views", "播放"], ["likes", "点赞"], ["comments", "评论"], ["published_at", "发布时间"]]
          .map(([key, label]) => `${label} ${item.field_provenance?.[key]?.layer || "—"}/${item.field_provenance?.[key]?.confidence || "missing"}`);
        itemCard.append(create("div", "kol-content-missing",
          `来源 ${item.capture_layer} · ${sources.join(" · ")} · 观察时间 ${item.observed_at || "—"}`));
      }
      if (reasons.length) {
        itemCard.append(title, metrics, create("div", "kol-content-missing", [...new Set(reasons)].join("；")));
      } else {
        itemCard.append(title, metrics);
      }
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
    state.profile = null;
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
      renderProfile();
      showProfileStatus(response.profile);
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
        sendMessage({ type: MESSAGE.ANALYZE_CONTENT, session_id: sessionId }),
        sessionId
      );
      if (!contentSessions.isCurrent(sessionId) || response?.session_id !== sessionId) return;
      if (!response?.ok) {
        if (response?.cancelled) {
          state.contentLoading = false;
          analyzeContentButton.disabled = false;
          cancelContentButton.hidden = true;
          contentStatus.textContent = "内容分析已停止或超时，请重试。";
          return;
        }
        throw new Error(response?.error || "Recent content analysis failed.");
      }
      state.contentAnalysis = response.analysis;
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

  const importCurrent = async () => {
    syncPreviewState();
    if (!state.profile || !state.preview?.content_category) {
      setStatus(
        state.profile ? "请选择 Content Category 后再导入。" : "请先分析当前达人主页。",
        "warning"
      );
      return;
    }
    if (!state.profile) {
      setStatus("请先分析当前达人主页。", "warning");
      return;
    }
    setStatus("正在连接 KOLConnect…");
    try {
      const response = await sendMessage({ type: MESSAGE.IMPORT, profile: profileForImport() });
      if (!response?.ok) throw new Error(response?.error || "Import failed.");
      setStatus("导入成功，已进入 KOLConnect 审核流程。");
    } catch (error) {
      setStatus(error?.message || "达人导入失败。", "error");
    }
  };

  const open = (manual = false) => {
    if (!pageSupport.isSupportedCreatorPage(location.href)) return;
    if (!manual && state.dismissedUrl === location.href) return;
    if (manual) state.dismissedUrl = "";
    state.visible = true;
    root.style.display = "block";
    if (!state.profile || state.analyzedUrl !== location.href) {
      scheduleProfileAnalysis(location.href, 0);
    }
  };

  const close = () => {
    state.dismissedUrl = location.href;
    state.visible = false;
    root.style.display = "none";
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
  importButton.addEventListener("click", importCurrent);
  for (const input of Object.values(previewInputs)) {
    input.addEventListener("input", syncPreviewState);
    input.addEventListener("change", syncPreviewState);
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
    importCurrent,
    initializePreview,
    profileForImport,
    agencyStatus,
    getCaptureDiagnostics,
    refreshCaptureDiagnostics
  };

  loadAgencyOptions();

  if (pageSupport.isSupportedCreatorPage(location.href)) {
    open();
  }
})();
