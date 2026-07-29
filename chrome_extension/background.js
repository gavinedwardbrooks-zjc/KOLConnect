import * as TikTok from "./platform/tiktok.js";
import * as Instagram from "./platform/instagram.js";
import * as YouTube from "./platform/youtube.js";
import { buildDiagnosticReport } from "./core/diagnostics.js";
import {
  CONTENT_ANALYSIS_TIMEOUT_MS,
  ensureContentSummaryConsistency,
  failedContentAnalysis
} from "./core/content_analysis.js";
import { MESSAGE } from "./core/messaging.js";
import { failedProfile, finalizeProfile } from "./core/schema.js";
import { importProfile } from "./services/local_api.js";

const PLATFORMS = [TikTok, Instagram, YouTube];
const contentControllers = new Map();

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
  try {
    await sendToTab(tab.id, { type: MESSAGE.OPEN });
  } catch (_) {
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ["content/floating_assistant.css"]
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["core/analysis_session.js", "core/page_support.js", "content/floating_assistant.js"]
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

async function analyzeContentForTab(tab, sessionId) {
  const platform = platformForUrl(tab?.url);
  if (!tab?.id || !platform) {
    return failedContentAnalysis("The current page is not a supported creator profile.", { limit: 30 });
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
      limit: 30,
      excludePinned: true,
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
    return ensureContentSummaryConsistency(analysis);
  } catch (error) {
    if (error?.name === "AbortError") {
      throw error;
    }
    return failedContentAnalysis(error?.message || "Recent content analysis failed.", { limit: 30 });
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
  if (message?.type === MESSAGE.COLLECT) {
    const sessionId = String(message.session_id || "");
    collectForTab(sender.tab, sessionId)
      .then((profile) => sendResponse({ ok: true, profile, session_id: sessionId }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || "Profile collection failed." }));
    return true;
  }
  if (message?.type === MESSAGE.IMPORT) {
    importProfile(message.profile)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || "Import failed." }));
    return true;
  }
  if (message?.type === MESSAGE.ANALYZE_CONTENT) {
    const sessionId = String(message.session_id || "");
    analyzeContentForTab(sender.tab, sessionId)
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
