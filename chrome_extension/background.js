import * as TikTok from "./platform/tiktok.js";
import * as Instagram from "./platform/instagram.js";
import * as YouTube from "./platform/youtube.js";
import { buildDiagnosticReport } from "./core/diagnostics.js";
import {
  CONTENT_ANALYSIS_TIMEOUT_MS,
  ensureContentSummaryConsistency,
  failedContentAnalysis,
  normalizeContentRange
} from "./core/content_analysis.js";
import { MESSAGE } from "./core/messaging.js";
import { failedProfile, finalizeProfile } from "./core/schema.js";
import {
  addAccount, assertLocalApiAvailable, createDiscoveryTask, createExtensionMailDraft, linkExistingCreator, loadAgencies,
  loadExtensionMailOptions, loadLocalApiUrl, lookupAccount, lookupDiscoveryCandidates,
  previewExtensionMailTemplate, searchCreators, submitPublicationCapture, updateAccount
} from "./services/local_api.js";
import { claimAndRunPublicationBatch, resumePublicationBatch } from "./services/publication_batch.js";
import {
  collectPublicationFromTab, INSTAGRAM_RECENT_CACHE_KEY, isTrustedInstagramPublishedAt,
  isTrustedInstagramRecentMetric, mergeInstagramRecentPublishedTimes, publicationIdentity
} from "./platform/publication_capture.js";
import {
  allowedUpdateUrl,
  checkForExtensionUpdate,
  snoozeExtensionUpdate
} from "./services/update_service.js";

const PLATFORMS = [TikTok, Instagram, YouTube];
const contentControllers = new Map();
const MAIL_HANDOFF_TTL_MS = 10 * 60 * 1000;
const mailHandoffKey = (token) => `mail_handoff:${token}`;
const TIKTOK_ISOLATED_CAPTURE_FILES = [
  "capture/passive_capture_protocol_isolated.js",
  "platform/tiktok_network.js",
  "capture/tiktok_capture_session.js",
  "content/passive_capture_bridge.js",
  "content/tiktok_capture_runtime.js"
];

function platformForUrl(url) {
  return PLATFORMS.find((platform) => platform.matches(url || "")) || null;
}

async function collectForTab(tab, sessionId = "") {
  const platform = platformForUrl(tab?.url);
  if (!tab?.id || !platform) {
    const profile = failedProfile("", tab?.url || "", "The current page is not a supported creator profile.");
    profile.capture_status = "unavailable";
    profile.analysis_session_id = sessionId;
    profile.diagnostic_report = buildDiagnosticReport(profile);
    return profile;
  }
  try {
    const raw = await platform.collectProfile(tab.id);
    const platformDiagnostics = platform.getDiagnostics(raw);
    raw.searched_sources = platformDiagnostics.searched_sources;
    raw.errors = platformDiagnostics.errors;
    const profile = finalizeProfile(raw);
    profile.analysis_session_id = sessionId;
    profile.diagnostic_report = buildDiagnosticReport(profile);
    return profile;
  } catch (error) {
    const platformName = platform === TikTok ? "TikTok" : platform === Instagram ? "Instagram" : "YouTube";
    const profile = failedProfile(platformName, tab.url, error?.message || "Profile collection failed.");
    profile.analysis_session_id = sessionId;
    profile.diagnostic_report = buildDiagnosticReport(profile);
    return profile;
  }
}

async function sendToTab(tabId, message) {
  return chrome.tabs.sendMessage(tabId, message);
}

async function openAssistant(tab) {
  if (TikTok.matches(tab.url || "")) {
    // Extension reload invalidates content scripts in an already-open tab while
    // the MAIN-world wrapper may remain. Restore the isolated join idempotently.
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "ISOLATED",
      files: TIKTOK_ISOLATED_CAPTURE_FILES
    });
  }
  try {
    await sendToTab(tab.id, { type: MESSAGE.OPEN });
  } catch (_) {
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ["content/floating_assistant.css"]
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["config.js", "core/analysis_session.js", "core/page_support.js", "content/update_prompt.js", "content/floating_assistant.js"]
    });
    await sendToTab(tab.id, { type: MESSAGE.OPEN });
  }
}

function cancelContentAnalysis(tabId) {
  const active = contentControllers.get(tabId);
  if (!active) return false;
  active.controller.abort();
  active.platform?.cancelRecentContent?.(tabId).catch(() => {});
  clearTimeout(active.timeoutId);
  contentControllers.delete(tabId);
  return true;
}

async function analyzeContentForTab(tab, sessionId, request = {}) {
  const platform = platformForUrl(tab?.url);
  const maximumCount = Number(platform?.RECENT_CONTENT_LIMIT) || 30;
  const range = normalizeContentRange(request.range, maximumCount);
  const excludePinned = request.exclude_pinned !== false;
  const contentLimit = range.type === "last_n_posts"
    ? Math.min(maximumCount, range.value + (excludePinned ? 3 : 0))
    : maximumCount;
  if (!tab?.id || !platform) {
    return failedContentAnalysis("The current page is not a supported creator profile.", {
      limit: contentLimit, maximumCount, range, excludePinned
    });
  }
  cancelContentAnalysis(tab.id);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
    platform.cancelRecentContent?.(tab.id).catch(() => {});
  }, CONTENT_ANALYSIS_TIMEOUT_MS);
  contentControllers.set(tab.id, { controller, timeoutId, sessionId, platform });
  try {
    const analysis = await platform.collectRecentContent(tab.id, {
      limit: contentLimit,
      range,
      excludePinned,
      now: Date.now(),
      analysisUrl: tab.url,
      signal: controller.signal,
      onProgress(progress) {
        sendToTab(tab.id, {
          type: MESSAGE.CONTENT_PROGRESS,
          session_id: sessionId,
          progress
        }).catch(() => {});
      }
    });
    let checked = ensureContentSummaryConsistency(analysis);
    if (platform === Instagram && chrome.storage?.session) {
      const now = Date.now();
      const stored = await chrome.storage.session.get(INSTAGRAM_RECENT_CACHE_KEY).catch(() => ({}));
      const previousCache = stored?.[INSTAGRAM_RECENT_CACHE_KEY] || {};
      checked = mergeInstagramRecentPublishedTimes(checked, previousCache, now);
      const expiresAt = now + 30 * 60 * 1000;
      const cache = Object.fromEntries(Object.entries(previousCache)
        .filter(([, entry]) => Number(entry?.expires_at || 0) > now));
      for (const item of checked.contents || []) {
        const shortcode = String(item.video_id || "").trim()
          || String(item.video_url || "").match(/\/(?:reel|reels|p|tv)\/([A-Za-z0-9_-]+)/i)?.[1];
        if (!shortcode) continue;
        const previous = cache[shortcode] || {};
        cache[shortcode] = {
          ...previous,
          expires_at: expiresAt,
          metrics: Object.fromEntries(["views", "likes", "comments", "shares"].map((name) => {
            const field = item[name];
            return [name, isTrustedInstagramRecentMetric(field)
              ? { value: field.value, source: field.source, confidence: field.confidence }
              : previous.metrics?.[name] || null];
          })),
          published_at: isTrustedInstagramPublishedAt(item.published_at)
            ? { value: item.published_at.value, source: item.published_at.source, confidence: item.published_at.confidence }
            : previous.published_at || null,
        };
      }
      await chrome.storage.session.set({ [INSTAGRAM_RECENT_CACHE_KEY]: cache }).catch(() => {});
    }
    return checked;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw error;
    }
    return failedContentAnalysis(error?.message || "Recent content analysis failed.", {
      limit: contentLimit, maximumCount, range, excludePinned
    });
  } finally {
    const active = contentControllers.get(tab.id);
    if (active?.sessionId === sessionId) {
      clearTimeout(active.timeoutId);
      contentControllers.delete(tab.id);
    }
  }
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id || !platformForUrl(tab.url)) return;
  try {
    await openAssistant(tab);
  } catch (error) {
    try {
      await sendToTab(tab.id, {
        type: MESSAGE.ERROR,
        error: error?.message || "Unable to open KOLConnect."
      });
    } catch (_) {}
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "KOLCONNECT_INSTAGRAM_PUBLISHED_AT_OBSERVED") {
    const senderIdentity = publicationIdentity(sender.tab?.url || "");
    const videoId = String(message.video_id || "").trim();
    const parsed = Date.parse(String(message.published_at || ""));
    if (sender.id !== chrome.runtime.id || sender.frameId !== 0
        || senderIdentity?.platform !== "Instagram" || senderIdentity.video_id !== videoId
        || !Number.isFinite(parsed) || !chrome.storage?.session) {
      sendResponse({ ok: false, code: "INSTAGRAM_PUBLISHED_AT_INVALID" });
      return false;
    }
    chrome.storage.session.get(INSTAGRAM_RECENT_CACHE_KEY).then((stored) => {
      const now = Date.now();
      const cache = stored?.[INSTAGRAM_RECENT_CACHE_KEY] && typeof stored[INSTAGRAM_RECENT_CACHE_KEY] === "object"
        ? { ...stored[INSTAGRAM_RECENT_CACHE_KEY] } : {};
      for (const [cachedId, entry] of Object.entries(cache)) {
        if (Number(entry?.expires_at || 0) <= now) delete cache[cachedId];
      }
      cache[videoId] = {
        ...(cache[videoId] || {}),
        expires_at: now + 30 * 60 * 1000,
        published_at: {
          value: new Date(parsed).toISOString(),
          source: "reel_detail_dom_exact",
          confidence: "high"
        }
      };
      return chrome.storage.session.set({ [INSTAGRAM_RECENT_CACHE_KEY]: cache });
    }).then(() => sendResponse({ ok: true })).catch(() => sendResponse({
      ok: false, code: "INSTAGRAM_PUBLISHED_AT_CACHE_FAILED"
    }));
    return true;
  }
  if (message?.type === "KOLCONNECT_PUBLICATION_BATCH_CLAIM") {
    let senderUrl;
    try { senderUrl = new URL(sender.url || sender.tab?.url || ""); } catch (_) { return false; }
    if (sender.id !== chrome.runtime.id || sender.frameId !== 0
        || !["127.0.0.1", "localhost"].includes(senderUrl.hostname)
        || senderUrl.port !== "8765") {
      sendResponse({ ok: false, error: "BATCH_CLAIM_ORIGIN_INVALID" });
      return false;
    }
    claimAndRunPublicationBatch(String(message.batch_run_id || ""), String(message.claim_token || ""))
      .then(result => sendResponse({ ok: true, ...result }))
      .catch(error => sendResponse({ ok: false, code: error?.code || "BATCH_CLAIM_FAILED", error: error?.message || "批量采集未启动。" }));
    return true;
  }
  if (message?.type === "KOLCONNECT_PUBLICATION_CAPTURE") {
    const pageUrl = String(sender.tab?.url || message.page_url || "");
    if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || !sender.tab?.id || pageUrl !== String(message.page_url || "")) {
      sendResponse({ ok: false, error: "当前页面身份无效。" });
      return false;
    }
    const requestRef = String(message.request_id || "").slice(-12);
    collectPublicationFromTab(sender.tab.id, pageUrl)
      .then(async (capture) => {
        const diagnosticEnabled = Boolean((await chrome.storage.local.get({
          publicationCaptureSafeDiagnostics: false
        })).publicationCaptureSafeDiagnostics);
        if (diagnosticEnabled) console.info("[KOLConnect][PublicationCapture]", {
          stage: capture.diagnostic?.stage || "collector_complete",
          trace_id: crypto.randomUUID?.() || `capture_${Date.now()}`,
          request_ref: requestRef,
          platform: capture.identity?.platform || "unknown",
          capture_status: capture.capture_status,
          safe_error_code: capture.safe_error_code || "",
          fields_present: Object.fromEntries(Object.entries(capture.metrics || {}).map(([name, field]) => [name, field?.value != null])),
          source_types: [...new Set(Object.values(capture.metrics || {}).map((field) => field?.source).filter(Boolean))],
          identity_match_count: capture.diagnostic?.identity_match_count || 0,
          identity_rejected_count: capture.diagnostic?.identity_rejected_count || 0,
          login_required: Boolean(capture.diagnostic?.login_required),
          playback_state: capture.diagnostic?.playback_state || "unknown",
          elapsed_ms: capture.diagnostic?.elapsed_ms || 0,
        });
        return submitPublicationCapture({
          request_id: String(message.request_id || ""), capability_token: String(message.capability_token || ""),
          page_url: pageUrl, platform: capture.identity?.platform || "", video_id: capture.identity?.video_id || "",
          capture_status: capture.capture_status, safe_error_code: capture.safe_error_code || "",
          metrics: capture.metrics || {}, collector_version: chrome.runtime.getManifest().version,
          contract_version: "publication-capture-v1"
        });
      })
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => {
        console.warn("[KOLConnect][PublicationCapture]", {
          stage: "submit_rejected", request_ref: requestRef,
          safe_error_code: error?.code || "CAPTURE_FAILED",
        });
        sendResponse({ ok: false, code: error?.code || "CAPTURE_FAILED", error: error?.message || "采集未完成。" });
      });
    return true;
  }
  if (message?.type === "KOLCONNECT_PUBLICATION_PREVIEW") {
    const pageUrl = String(sender.tab?.url || message.page_url || "");
    if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || !sender.tab?.id
        || pageUrl !== String(message.page_url || "")) {
      sendResponse({ ok: false, code: "PUBLICATION_PAGE_INVALID" });
      return false;
    }
    collectPublicationFromTab(sender.tab.id, pageUrl, 5000)
      .then((capture) => sendResponse({ ok: true, capture }))
      .catch(() => sendResponse({ ok: false, code: "PUBLICATION_PREVIEW_FAILED" }));
    return true;
  }
  if (["KOLCONNECT_PASSIVE_CONNECT", "KOLCONNECT_PASSIVE_REPLAY", "KOLCONNECT_PASSIVE_RESET", "KOLCONNECT_PASSIVE_DIAGNOSTICS"].includes(message?.type)) {
    let url;
    try { url = new URL(sender.url); } catch (_) { return false; }
    if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || !sender.tab?.id
        || url.protocol !== "https:" || !["tiktok.com", "www.tiktok.com", "m.tiktok.com"].includes(url.hostname)) return false;
    const operation = message.type;
    if (operation === "KOLCONNECT_PASSIVE_DIAGNOSTICS") {
      TikTok.readCaptureDiagnostics(sender.tab.id)
        .then(diagnostics => sendResponse({ ok: true, diagnostics }))
        .catch(() => sendResponse({ ok: false, error: "CAPTURE_DIAGNOSTICS_UNAVAILABLE" }));
      return true;
    }
    const work = operation === "KOLCONNECT_PASSIVE_RESET" ? TikTok.resetCapture(sender.tab.id)
      : chrome.scripting.executeScript({ target: { tabId: sender.tab.id }, world: "MAIN",
        func: (op) => {
          const control = globalThis.KOLConnectPassiveCaptureControl;
          if (op === "KOLCONNECT_PASSIVE_CONNECT") return { token: control?.token() || null };
          control?.replay();
          return { ok: true };
        }, args: [operation] });
    work.then((result) => sendResponse(result?.[0]?.result || { ok: true }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (message?.type === MESSAGE.COLLECT) {
    const sessionId = String(message.session_id || "");
    collectForTab(sender.tab, sessionId)
      .then((profile) => sendResponse({ ok: true, profile, session_id: sessionId }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || "Profile collection failed." }));
    return true;
  }
  if ([MESSAGE.ADD_ACCOUNT, MESSAGE.UPDATE_ACCOUNT].includes(message?.type)) {
    const mutate = message.type === MESSAGE.ADD_ACCOUNT ? addAccount : updateAccount;
    Promise.resolve().then(async () => {
      if (String(message.profile?.platform).toLowerCase() === "tiktok") {
        const profile = new URL(message.profile.profile_url).pathname.match(/^\/@([A-Za-z0-9._]+)\/?$/)?.[1];
        const state = await TikTok.captureState(sender.tab?.id, profile);
        if (state.stopped) throw new Error(state.stopped);
      }
      return mutate(message.profile);
    })
      .then((result) => sendResponse({
        ok: true,
        result,
        session_id: String(message.session_id || ""),
        identity: message.identity || null
      }))
      .catch((error) => sendResponse({
        ok: false,
        code: error?.code || "MUTATION_FAILED",
        error: error?.message || "Mutation failed.",
        session_id: String(message.session_id || ""),
        identity: message.identity || null
      }));
    return true;
  }
  if (message?.type === MESSAGE.LOOKUP_ACCOUNT) {
    const platform = typeof message.profile?.platform === "string" ? message.profile.platform : "";
    const profileUrl = typeof message.profile?.profile_url === "string" ? message.profile.profile_url : "";
    lookupAccount(platform, profileUrl)
      .then((lookup) => sendResponse({ ok: true, lookup }))
      .catch((error) => sendResponse({
        ok: false,
        code: error?.code || "LOOKUP_FAILED",
        error: error?.message || "Account lookup failed."
      }));
    return true;
  }
  if (message?.type === MESSAGE.SEARCH_CREATORS) {
    searchCreators(message.query, message.page)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, code: error?.code || "CREATOR_SEARCH_FAILED" }));
    return true;
  }
  if (message?.type === MESSAGE.LINK_EXISTING_CREATOR) {
    linkExistingCreator(message.creator_id, message.identity?.platform, message.identity?.profile_url)
      .then((result) => sendResponse({
        ok: true, result, session_id: String(message.session_id || ""), identity: message.identity || null
      }))
      .catch((error) => sendResponse({
        ok: false, code: error?.code || "LINK_FAILED",
        session_id: String(message.session_id || ""), identity: message.identity || null
      }));
    return true;
  }
  if (message?.type === MESSAGE.LOAD_AGENCIES) {
    loadAgencies()
      .then((agencies) => sendResponse({ ok: true, agencies }))
      .catch((error) => sendResponse({
        ok: false,
        code: error?.code || "AGENCY_LIST_FAILED",
        error: error?.message || "Agency list unavailable."
      }));
    return true;
  }
  if (message?.type === MESSAGE.CREATE_DISCOVERY_TASK) {
    createDiscoveryTask(message.profile_urls, message.seed_url, message.platform)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, code: error?.code || "DISCOVERY_TASK_FAILED" }));
    return true;
  }
  if (message?.type === MESSAGE.LOOKUP_DISCOVERY_CANDIDATES) {
    lookupDiscoveryCandidates(message.profile_urls)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, code: error?.code || "CANDIDATE_LOOKUP_FAILED" }));
    return true;
  }
  if (message?.type === MESSAGE.LOAD_MAIL_OPTIONS) {
    loadExtensionMailOptions(message.query || {})
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, code: error?.code || "MAIL_OPTIONS_FAILED" }));
    return true;
  }
  if (message?.type === MESSAGE.PREVIEW_MAIL_TEMPLATE) {
    previewExtensionMailTemplate(message.payload || {})
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, code: error?.code || "MAIL_TEMPLATE_PREVIEW_FAILED" }));
    return true;
  }
  if (message?.type === MESSAGE.CREATE_MAIL_DRAFT) {
    createExtensionMailDraft(message.payload || {})
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, code: error?.code || "MAIL_DRAFT_CREATE_FAILED" }));
    return true;
  }
  if (message?.type === MESSAGE.OPEN_MAIL_WORKSPACE) {
    const context = message.context && typeof message.context === "object" ? message.context : {};
    const recipientEmail = String(context.recipientEmail || "").trim();
    const creatorName = String(context.creatorName || "").trim();
    const manageOnly = context.mode === "manage_templates";
    const draftId = String(context.draftId || "").trim();
    if (!creatorName || (!manageOnly && (!draftId || !recipientEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipientEmail)))) {
      sendResponse({ ok: false, code: "MAIL_CONTEXT_INVALID" });
      return false;
    }
    const token = crypto.randomUUID();
    const handoff = {
      expires_at: Date.now() + MAIL_HANDOFF_TTL_MS,
      context: {
        creatorId: String(context.creatorId || ""), creatorName, recipientEmail,
        draftType: "initial_outreach", language: String(context.language || "en"),
        creatorTier: ["KOL", "KOC"].includes(context.creatorTier) ? context.creatorTier : "",
        mode: manageOnly ? "manage_templates" : "draft",
        draftId: manageOnly ? "" : draftId,
        templateName: String(context.templateName || "")
      }
    };
    assertLocalApiAvailable()
      .then(() => chrome.storage.session.set({ [mailHandoffKey(token)]: handoff }))
      .then(() => loadLocalApiUrl())
      .then((apiUrl) => chrome.tabs.create({
      url: `${String(apiUrl).replace(/\/$/, "")}/#mail-handoff=${encodeURIComponent(token)}`
    })).then(() => sendResponse({ ok: true })).catch(() => {
      chrome.storage.session.remove(mailHandoffKey(token)).catch(() => {});
      sendResponse({ ok: false, code: "APP_OFFLINE" });
    });
    return true;
  }
  if (message?.type === MESSAGE.CONSUME_MAIL_HANDOFF) {
    const senderUrl = String(sender.url || sender.tab?.url || "");
    const token = String(message.token || "");
    const localSender = /^http:\/\/(127\.0\.0\.1|localhost):8765\//.test(senderUrl);
    if (!localSender || !token) {
      sendResponse({ ok: false, code: "MAIL_HANDOFF_INVALID" });
      return false;
    }
    const key = mailHandoffKey(token);
    chrome.storage.session.get(key).then((stored) => chrome.storage.session.remove(key)
      .then(() => stored[key])).then((handoff) => {
      if (!handoff || handoff.expires_at < Date.now()) {
        sendResponse({ ok: false, code: "MAIL_HANDOFF_INVALID" });
        return;
      }
      sendResponse({ ok: true, context: handoff.context });
    }).catch(() => sendResponse({ ok: false, code: "MAIL_HANDOFF_INVALID" }));
    return true;
  }
  if (message?.type === MESSAGE.CHECK_UPDATE) {
    checkForExtensionUpdate({ currentVersion: chrome.runtime.getManifest().version })
      .then((update) => sendResponse({ ok: true, update }))
      .catch(() => sendResponse({ ok: true, update: null }));
    return true;
  }
  if (message?.type === MESSAGE.SNOOZE_UPDATE) {
    snoozeExtensionUpdate(message.version)
      .then((snoozed) => sendResponse({ ok: snoozed }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (message?.type === MESSAGE.OPEN_UPDATE_DOWNLOAD) {
    const target = allowedUpdateUrl(message.url);
    if (!target) {
      sendResponse({ ok: false });
      return false;
    }
    chrome.tabs.create({ url: target })
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (message?.type === MESSAGE.ANALYZE_CONTENT) {
    const sessionId = String(message.session_id || "");
    analyzeContentForTab(sender.tab, sessionId, {
      range: message.range,
      exclude_pinned: message.exclude_pinned
    })
      .then((analysis) => sendResponse({ ok: true, analysis, session_id: sessionId }))
      .catch((error) => sendResponse({
        ok: false,
        cancelled: error?.name === "AbortError",
        error: error?.name === "AbortError" ? "Content analysis was cancelled." : error?.message
      }));
    return true;
  }
  if (message?.type === MESSAGE.CANCEL_CONTENT) {
    sendResponse({ ok: true, cancelled: cancelContentAnalysis(sender.tab?.id) });
    return false;
  }
  return false;
});

chrome.runtime.onStartup?.addListener(() => { resumePublicationBatch(); });
resumePublicationBatch();

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (!changeInfo.url) return;
  cancelContentAnalysis(tabId);
  if (!platformForUrl(changeInfo.url)) return;
  sendToTab(tabId, {
    type: MESSAGE.PAGE_CHANGED,
    url: changeInfo.url
  }).catch(() => {});
});

function notifyHistoryNavigation(details) {
  if (details.frameId !== 0) return;
  cancelContentAnalysis(details.tabId);
  if (!platformForUrl(details.url)) return;
  sendToTab(details.tabId, {
    type: MESSAGE.PAGE_CHANGED,
    url: details.url
  }).catch(() => {});
}

chrome.webNavigation.onHistoryStateUpdated.addListener(notifyHistoryNavigation);
chrome.webNavigation.onReferenceFragmentUpdated.addListener(notifyHistoryNavigation);
chrome.tabs.onRemoved.addListener((tabId) => cancelContentAnalysis(tabId));
