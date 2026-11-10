(function publicationCaptureCard(root) {
  "use strict";
  const MARKER = "kolconnect-publication-capture";
  const SAFE_FAILURES = Object.freeze({
    AUTH_REQUIRED: "页面要求登录或验证；请完成平台操作后重试。",
    PLATFORM_RESTRICTED: "平台当前限制了数据读取；请完成验证后重试。",
    VIDEO_IDENTITY_MISSING: "未在可信数据源中找到当前视频，请等待页面加载后重试。",
    VIDEO_IDENTITY_MISMATCH: "页面视频身份与采集任务不一致。",
    SOURCE_UNAVAILABLE: "当前页面没有可验证的数据来源。",
    EVIDENCE_NOT_FOUND: "当前页面尚未暴露可验证指标。",
    METRICS_NOT_FOUND: "当前页面尚未暴露可验证指标。",
    CAPTURE_TIMEOUT: "页面读取超时，请等待加载完成后重试。",
    COLLECTOR_NOT_STARTED: "采集器未能启动，请重新加载扩展和页面。",
    PLAYBACK_UNAVAILABLE: "当前 Chrome Profile 无法读取该视频，请核对登录状态或平台限制。",
    CAPTURE_CAPABILITY_INVALID: "采集码无效或不完整，请返回 KOLConnect 生成新采集码。",
    CAPTURE_REQUEST_EXPIRED: "采集码已过期，请返回 KOLConnect 重新发起。",
    CAPTURE_TARGET_MISMATCH: "当前页面不是采集任务指定的视频。",
    CAPTURE_TARGET_STALE: "发布视频身份已变化，请返回 KOLConnect 重新发起。",
    CAPTURE_CONTRACT_UNSUPPORTED: "扩展与 KOLConnect 采集协议不兼容，请更新后重试。",
    CAPTURE_SUBMIT_FAILED: "采集结果未能保存，请确认 KOLConnect 正在运行。",
  });

  const pageSupport = root.KOLConnectPageSupport;
  const identity = pageSupport?.publicationIdentity?.(root.location.href);
  if (!identity || document.getElementById(MARKER)) return;

  const cacheExactInstagramPublishedAt = async () => {
    if (identity.platform !== "Instagram") return false;
    const exactTime = [...document.querySelectorAll("time[datetime]")].find((element) => {
      try {
        const url = new URL(element.closest("a")?.href || "");
        const parts = url.pathname.split("/").filter(Boolean);
        const mediaIndex = parts.findIndex((part) => ["reel", "reels", "p", "tv"].includes(part.toLowerCase()));
        return mediaIndex >= 0 && parts[mediaIndex + 1] === identity.video_id && parts.length === mediaIndex + 2;
      } catch (_) { return false; }
    });
    const rawValue = exactTime?.getAttribute("datetime") || "";
    const parsed = Date.parse(rawValue);
    if (!Number.isFinite(parsed)) return false;
    const response = await chrome.runtime.sendMessage({
      type: "KOLCONNECT_INSTAGRAM_PUBLISHED_AT_OBSERVED",
      video_id: identity.video_id,
      published_at: new Date(parsed).toISOString()
    });
    return response?.ok === true;
  };

  const host = document.createElement("aside");
  host.id = MARKER;
  host.dataset.mode = "minimized";
  const shadow = host.attachShadow({ mode: "closed" });
  shadow.innerHTML = `
    <style>
      :host{all:initial}.shell{width:100%;color:#f6f4ec;font:13px/1.45 "Segoe UI","Microsoft YaHei",sans-serif}
      button,input{font:inherit}.chip{display:flex;align-items:center;gap:8px;min-height:42px;padding:6px 7px 6px 12px;border:1px solid rgba(255,255,255,.16);border-radius:14px;background:#17211f;color:#f6f4ec;box-shadow:0 10px 32px rgba(0,0,0,.28);cursor:move}
      .mark{display:grid;place-items:center;width:25px;height:25px;border-radius:8px;background:#d8f08a;color:#17211f;font-weight:900}.chip strong{flex:1;font-size:13px}.icon{width:29px;height:29px;padding:0;border:0;border-radius:9px;background:#293a35;color:#f6f4ec;cursor:pointer}
      .panel{display:none;overflow:hidden;border:1px solid rgba(255,255,255,.16);border-radius:16px;background:#17211f;box-shadow:0 18px 48px rgba(0,0,0,.35)}
      :host([data-mode="expanded"]) .chip{display:none}:host([data-mode="expanded"]) .panel{display:block}
      .head{display:flex;align-items:center;gap:8px;padding:10px 11px;border-bottom:1px solid rgba(255,255,255,.1);cursor:move}.head strong{flex:1}.body{display:grid;gap:10px;max-height:min(430px,calc(100vh - 100px));overflow-y:auto;overflow-x:hidden;padding:12px}
      .identity{color:#aebeb8;overflow-wrap:anywhere}.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.metric{padding:8px 9px;border-radius:10px;background:#22302d}.metric span{display:block;color:#9fb0aa;font-size:11px}.metric strong{display:block;margin-top:2px;font-size:16px}
      .status{min-height:19px;color:#b9c8c2}.actions{display:flex;flex-wrap:wrap;gap:7px}button.action{min-height:34px;padding:7px 11px;border:0;border-radius:9px;background:#2a3b37;color:#e6eeeb;font-weight:700;cursor:pointer}button.primary{background:#d8f08a;color:#17211f}button:disabled{opacity:.55;cursor:wait}
      .manual[hidden]{display:none}.manual{display:grid;gap:7px;padding-top:2px}.manual input{box-sizing:border-box;width:100%;padding:9px 10px;color:#f7f4ed;background:#0d1513;border:1px solid #41524d;border-radius:9px}
      @media(max-width:480px){.body{max-height:min(360px,calc(100vh - 80px))}}
    </style>
    <div class="shell">
      <div class="chip" data-drag-handle><span class="mark">K</span><strong>视频指标</strong><button class="icon" data-expand aria-label="展开">+</button><button class="icon" data-close aria-label="关闭">×</button></div>
      <section class="panel">
        <header class="head" data-drag-handle><strong>当前视频指标</strong><button class="icon" data-minimize aria-label="最小化">−</button><button class="icon" data-close aria-label="关闭">×</button></header>
        <div class="body">
          <div class="identity"><b data-platform></b> · <span data-video-id></span></div>
          <div class="metrics">${["views", "likes", "comments", "shares"].map((name) => `<div class="metric"><span>${({ views: "播放", likes: "点赞", comments: "评论", shares: "分享" })[name]}</span><strong data-metric="${name}">—</strong></div>`).join("")}</div>
          <div class="status" role="status">展开后读取当前页面的可信公开指标。</div>
          <div class="actions"><button class="action primary" data-refresh>刷新指标</button><button class="action" data-manual>手动采集码</button><button class="action" data-safe-diagnostics>安全诊断：关闭</button></div>
          <div class="manual" hidden><input type="password" autocomplete="off" placeholder="粘贴一次性采集码" aria-label="KOLConnect 一次性采集码"><button class="action primary" data-capture>采集并保存到 Campaign</button></div>
        </div>
      </section>
    </div>`;

  const status = shadow.querySelector('[role="status"]');
  const manual = shadow.querySelector(".manual");
  const input = shadow.querySelector("input");
  const refreshButton = shadow.querySelector("[data-refresh]");
  const captureButton = shadow.querySelector("[data-capture]");
  const diagnosticButton = shadow.querySelector("[data-safe-diagnostics]");
  shadow.querySelector("[data-platform]").textContent = identity.platform;
  shadow.querySelector("[data-video-id]").textContent = identity.video_id;

  const metricText = (value) => Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString() : "—";
  const renderCapture = (capture) => {
    for (const name of ["views", "likes", "comments", "shares"]) {
      shadow.querySelector(`[data-metric="${name}"]`).textContent = metricText(capture?.metrics?.[name]?.value);
    }
    const available = Object.values(capture?.metrics || {}).filter((field) => field?.value != null).length;
    status.textContent = available
      ? `${capture.capture_status === "success" ? "读取完成" : "部分读取"} · ${available}/4 项可信指标`
      : (SAFE_FAILURES[capture?.safe_error_code] || "当前页面尚未提供可验证指标。");
  };
  const preview = async () => {
    refreshButton.disabled = true;
    status.textContent = "正在读取当前视频…";
    try {
      const response = await chrome.runtime.sendMessage({ type: "KOLCONNECT_PUBLICATION_PREVIEW", page_url: root.location.href });
      if (!response?.ok) throw new Error(response?.code || "PREVIEW_FAILED");
      renderCapture(response.capture);
    } catch (_) { status.textContent = "指标读取暂不可用；可稍后刷新或使用采集码。"; }
    finally { refreshButton.disabled = false; }
  };
  const setMode = (mode) => {
    host.dataset.mode = mode;
    if (host.style.left) {
      requestAnimationFrame(() => {
        const box = host.getBoundingClientRect();
        const next = clamp(box.left, box.top);
        host.style.left = `${next.left}px`; host.style.top = `${next.top}px`;
      });
    }
    if (mode === "expanded") preview();
  };
  shadow.querySelector("[data-expand]").addEventListener("click", () => setMode("expanded"));
  shadow.querySelector("[data-minimize]").addEventListener("click", () => setMode("minimized"));
  shadow.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => host.remove()));
  shadow.querySelector("[data-manual]").addEventListener("click", () => {
    manual.hidden = !manual.hidden;
    if (!manual.hidden) input.focus();
  });
  refreshButton.addEventListener("click", preview);

  const renderDiagnosticState = (enabled) => { diagnosticButton.textContent = `安全诊断：${enabled ? "开启" : "关闭"}`; };
  chrome.storage.local.get({ publicationCaptureSafeDiagnostics: false })
    .then((value) => renderDiagnosticState(Boolean(value.publicationCaptureSafeDiagnostics)))
    .catch(() => renderDiagnosticState(false));
  diagnosticButton.addEventListener("click", async () => {
    const current = await chrome.storage.local.get({ publicationCaptureSafeDiagnostics: false });
    const enabled = !Boolean(current.publicationCaptureSafeDiagnostics);
    await chrome.storage.local.set({ publicationCaptureSafeDiagnostics: enabled });
    renderDiagnosticState(enabled);
    status.textContent = enabled ? "安全诊断已开启，只记录阶段、来源类型和字段存在性。" : "安全诊断已关闭。";
  });
  captureButton.addEventListener("click", async () => {
    const parsedCode = root.KOLConnectPublicationCaptureCode?.parse?.(input.value);
    if (!parsedCode) { status.textContent = "采集码格式不完整，请重新复制。"; return; }
    captureButton.disabled = true;
    status.textContent = "正在采集并保存…";
    try {
      const response = await chrome.runtime.sendMessage({
        type: "KOLCONNECT_PUBLICATION_CAPTURE", request_id: parsedCode.request_id,
        capability_token: parsedCode.capability_token, page_url: root.location.href
      });
      const captureStatus = String(response?.result?.attempt?.capture_status || "");
      const safeError = String(response?.result?.attempt?.safe_error_code || "");
      status.textContent = response?.ok && ["success", "partial"].includes(captureStatus)
        ? "采集结果已保存，可返回 KOLConnect 查看。"
        : response?.ok ? (SAFE_FAILURES[safeError] || `本次采集未取得可靠指标（${captureStatus || "failed"}）。`)
          : (SAFE_FAILURES[String(response?.code || "")] || response?.error || "采集未完成。");
      if (response?.ok) input.value = "";
    } catch (_) { status.textContent = "无法连接 KOLConnect，请确认桌面应用已启动。"; }
    finally { captureButton.disabled = false; }
  });

  let drag = null;
  const clamp = (left, top) => ({
    left: Math.max(0, Math.min(root.innerWidth - Math.min(root.innerWidth, host.offsetWidth || 220), left)),
    top: Math.max(0, Math.min(root.innerHeight - 42, top)),
  });
  shadow.querySelectorAll("[data-drag-handle]").forEach((handle) => {
    handle.addEventListener("pointerdown", (event) => {
      if (event.target instanceof HTMLButtonElement) return;
      const box = host.getBoundingClientRect();
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: box.left, top: box.top };
      handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener("pointermove", (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      const next = clamp(drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y);
      host.style.left = `${next.left}px`; host.style.top = `${next.top}px`; host.style.right = "auto"; host.style.bottom = "auto";
    });
    handle.addEventListener("pointerup", () => { drag = null; });
  });
  root.addEventListener("resize", () => {
    if (!host.style.left) return;
    const box = host.getBoundingClientRect();
    const next = clamp(box.left, box.top);
    host.style.left = `${next.left}px`; host.style.top = `${next.top}px`; host.style.right = "auto"; host.style.bottom = "auto";
  });
  document.documentElement.appendChild(host);
  if (identity.platform === "Instagram") {
    for (const delay of [0, 1000, 3000, 8000, 15000, 25000]) {
      setTimeout(() => cacheExactInstagramPublishedAt().catch(() => {}), delay);
    }
  }
})(globalThis);
