(() => {
  const GLOBAL_KEY = "__KOLCONNECT_NEXT_ASSISTANT__";
  const ROOT_ID = "kolconnect-next-root";
  if (globalThis[GLOBAL_KEY]) return;

  const MESSAGE = {
    OPEN: "KOLCONNECT_NEXT_OPEN",
    ERROR: "KOLCONNECT_NEXT_ERROR",
    COLLECT: "KOLCONNECT_NEXT_COLLECT",
    IMPORT: "KOLCONNECT_NEXT_IMPORT",
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
  if (!SessionController || !pageSupport) return;

  for (const staleId of [ROOT_ID, "kolconnect-next-assistant"]) {
    document.getElementById(staleId)?.remove();
  }

  const profileSessions = new SessionController(ANALYSIS_TIMEOUT_MS);
  const contentSessions = new SessionController(CONTENT_TIMEOUT_MS);
  const state = {
    profile: null,
    contentAnalysis: null,
    contentLoading: false,
    visible: false,
    minimized: false,
    dismissedUrl: "",
    lastUrl: location.href,
    analyzedUrl: "",
    analysisTimer: null,
    currentSessionId: "",
    currentContentSessionId: ""
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
  const brand = create("span", "kol-brand", "KOLConnect v0.1.2");
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
  contentSection.append(contentStatus, contentSummary, contentDetails);

  const diagnostics = create("details", "kol-diagnostics");
  diagnostics.append(create("summary", "", "高级诊断"));
  const diagnosticsText = create("pre", "", "—");
  diagnostics.append(diagnosticsText);

  const actions = create("div", "kol-actions");
  const refreshButton = create("button", "", "重新分析资料");
  const analyzeContentButton = create("button", "", "分析最近30条");
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
  actions.append(refreshButton, analyzeContentButton, cancelContentButton, copyButton, importButton);
  body.append(status, card, contentSection, diagnostics, actions);
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

  const formatNumber = (value) => value == null
    ? "—"
    : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
  const formatPercent = (value) => value == null ? "—" : `${Number(value).toFixed(2)}%`;
  const contentTypeLabel = (value) => ({
    video: "视频",
    reel: "Reels",
    short: "Shorts"
  }[value] || "—");

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
      missing_field_summary: analysis.missing_field_summary || {},
      summary_validation: analysis.summary_validation || {}
    } : {};
  };

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
    fieldElements.username.textContent = username || "—";
    fieldElements.creator_name.textContent = displayName;
    fieldElements.followers.textContent = profile?.followers
      ? formatNumber(Number(profile.followers))
      : "—";
    fieldElements.bio.textContent = profile?.bio || "暂无公开简介";
    fieldElements.capture_status.textContent = profile?.capture_status || "idle";
    diagnosticsText.textContent = JSON.stringify(profile?.diagnostic_report || {}, null, 2);
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
    contentStatus.textContent = analysis.error === "CONTENT_VIEW_SUMMARY_MISMATCH"
      ? "播放统计数据不一致，请重新分析。"
      : analysis.capture_status === "success"
      ? "最近内容分析完成。"
      : analysis.capture_status === "partial_success"
        ? "已取得部分公开内容数据。"
        : analysis.capture_status === "unavailable"
          ? "当前页面没有公开足够的内容数据。"
          : "内容分析失败。";
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
    const report = JSON.stringify(state.profile?.diagnostic_report || {}, null, 2);
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
    if (!state.profile) {
      setStatus("请先分析当前达人主页。", "warning");
      return;
    }
    setStatus("正在连接 KOLConnect…");
    try {
      const response = await sendMessage({ type: MESSAGE.IMPORT, profile: state.profile });
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
    state
  };

  if (pageSupport.isSupportedCreatorPage(location.href)) {
    open();
  }
})();
