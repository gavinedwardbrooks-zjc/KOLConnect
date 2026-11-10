import { collectPublicationFromTab, publicationIdentity } from "../platform/publication_capture.js";
import {
  claimPublicationBatch, nextPublicationBatchItem, publicationBatchExecutionState, submitPublicationCapture
} from "./local_api.js";

const STORAGE_KEY = "publicationBatchExecution";
let running = null;

function parseCaptureCode(value) {
  const match = String(value || "").match(/^(capture_[a-f0-9]{32})\.([A-Za-z0-9_-]{20,})$/);
  return match ? { request_id: match[1], capability_token: match[2] } : null;
}

async function waitForTab(tabId, timeoutMs = 30000) {
  const current = await chrome.tabs.get(tabId);
  if (current?.status === "complete") return;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error("TAB_LOAD_TIMEOUT")), timeoutMs);
    const listener = (id, change) => {
      if (id === tabId && change.status === "complete") finish();
    };
    function finish(error) {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      error ? reject(error) : resolve();
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

function itemIdentityMatches(item, rawUrl) {
  const identity = publicationIdentity(rawUrl);
  return identity?.platform === item.platform && identity?.video_id === item.video_id;
}

function isYouTubeShort(item) {
  try {
    return item.platform === "YouTube" && new URL(item.canonical_url).pathname.startsWith("/shorts/");
  } catch (_) {
    return false;
  }
}

async function waitForStableTarget(tabId, item, quietMs = 300) {
  const current = await chrome.tabs.get(tabId);
  if (!itemIdentityMatches(item, current?.url)) return false;
  return new Promise((resolve) => {
    let timer = setTimeout(() => finish(true), quietMs);
    const listener = (id, change, tab) => {
      if (id !== tabId || (!change.url && !tab?.url)) return;
      const url = change.url || tab.url;
      if (!itemIdentityMatches(item, url)) return finish(false);
      clearTimeout(timer);
      timer = setTimeout(() => finish(true), quietMs);
    };
    function finish(stable) {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve(stable);
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

function watchTargetIdentity(tabId, item) {
  let drifted = false;
  const listener = (id, change, tab) => {
    if (id !== tabId || (!change.url && !tab?.url)) return;
    if (!itemIdentityMatches(item, change.url || tab.url)) drifted = true;
  };
  chrome.tabs.onUpdated.addListener(listener);
  return async () => {
    chrome.tabs.onUpdated.removeListener(listener);
    const current = await chrome.tabs.get(tabId);
    return drifted || !itemIdentityMatches(item, current?.url);
  };
}

function identityFailure(item) {
  return {
    identity: { platform: item.platform, video_id: item.video_id },
    capture_status: "failed", safe_error_code: "VIDEO_IDENTITY_MISMATCH", metrics: {},
    diagnostic: { stage: "video_identity_mismatch" }
  };
}

async function collectStablePublication(tab, item) {
  let recovered = false;
  while (true) {
    const stable = await waitForStableTarget(tab.id, item);
    if (!stable) {
      if (!isYouTubeShort(item) || recovered) return identityFailure(item);
      await chrome.tabs.update(tab.id, { url: item.canonical_url });
      recovered = true;
      await waitForTab(tab.id);
      continue;
    }
    const stopWatching = watchTargetIdentity(tab.id, item);
    const capture = await collectPublicationFromTab(tab.id, item.canonical_url);
    const drifted = await stopWatching();
    const collectorMismatch = capture?.safe_error_code === "VIDEO_IDENTITY_MISMATCH"
      || capture?.diagnostic?.stage === "video_identity_mismatch";
    if (!drifted && !collectorMismatch) return capture;
    if (!isYouTubeShort(item) || recovered) return identityFailure(item);
    await chrome.tabs.update(tab.id, { url: item.canonical_url });
    recovered = true;
    await waitForTab(tab.id);
  }
}

async function storeExecution(value) {
  const area = chrome.storage.session;
  if (!area) throw new Error("SESSION_STORAGE_UNAVAILABLE");
  if (value) await area.set({ [STORAGE_KEY]: value });
  else await area.remove(STORAGE_KEY);
}

async function loadExecution() {
  const area = chrome.storage.session;
  if (!area) return null;
  return (await area.get(STORAGE_KEY))[STORAGE_KEY] || null;
}

async function processItem(execution, item) {
  const parsed = parseCaptureCode(item.capture_code);
  if (!parsed) throw new Error("ITEM_CAPABILITY_INVALID");
  let tab = null;
  let capture;
  try {
    if (execution.current_tab_id) {
      try { tab = await chrome.tabs.get(execution.current_tab_id); } catch (_) { tab = null; }
    }
    if (!tab || tab.url !== item.canonical_url) {
      tab = await chrome.tabs.create({ url: item.canonical_url, active: true });
      execution.current_tab_id = tab.id;
      await storeExecution(execution);
    }
    await waitForTab(tab.id);
    capture = await collectStablePublication(tab, item);
  } catch (error) {
    capture = {
      identity: { platform: item.platform, video_id: item.video_id }, capture_status: "failed",
      safe_error_code: error?.message === "TAB_LOAD_TIMEOUT" ? "CAPTURE_TIMEOUT" : "COLLECTOR_NOT_STARTED",
      metrics: {}
    };
  }
  try {
    const diagnosticEnabled = Boolean((await chrome.storage.local.get({
      publicationCaptureSafeDiagnostics: false
    })).publicationCaptureSafeDiagnostics);
    if (diagnosticEnabled) console.info("[KOLConnect][PublicationBatch]", {
      stage: capture.diagnostic?.stage || "collector_complete",
      trace_id: crypto.randomUUID?.() || `capture_${Date.now()}`,
      item_ref: String(item.item_id || "").slice(-12),
      platform: item.platform,
      capture_status: capture.capture_status,
      safe_error_code: capture.safe_error_code || "",
      fields_present: Object.fromEntries(Object.entries(capture.metrics || {})
        .map(([name, field]) => [name, field?.value != null])),
      source_types: [...new Set(Object.values(capture.metrics || {})
        .map((field) => field?.source).filter(Boolean))],
      playback_state: capture.diagnostic?.playback_state || "unknown",
      identity_match_count: capture.diagnostic?.identity_match_count || 0,
      identity_rejected_count: capture.diagnostic?.identity_rejected_count || 0,
      login_required: Boolean(capture.diagnostic?.login_required),
      elapsed_ms: capture.diagnostic?.elapsed_ms || 0,
    });
    return await submitPublicationCapture({
      ...parsed, page_url: item.canonical_url, platform: item.platform, video_id: item.video_id,
      capture_status: capture.capture_status, safe_error_code: capture.safe_error_code || "",
      metrics: capture.metrics || {}, collector_version: chrome.runtime.getManifest().version,
      contract_version: "publication-capture-v1"
    });
  } finally {
    if (tab?.id) try { await chrome.tabs.remove(tab.id); } catch (_) {}
    delete execution.current_tab_id;
  }
}

export async function runPublicationBatch(execution = null) {
  if (running) return running;
  running = (async () => {
    const active = execution || await loadExecution();
    if (!active?.batch_run_id || !active?.executor_token) return { state: "idle" };
    if (active.current_item) {
      const parsed = parseCaptureCode(active.current_item.capture_code);
      const state = await publicationBatchExecutionState(
        active.batch_run_id, active.executor_token, parsed?.request_id || ""
      );
      if (!state.continue_current) {
        delete active.current_item;
        delete active.current_tab_id;
        if (state.state === "running") {
          // The backend may have committed the item while its HTTP response was lost.
          await storeExecution(active);
        } else {
          await storeExecution(null);
          return { state: state.state || "interrupted" };
        }
      }
    }
    for (let count = 0; count < 300; count += 1) {
      let item = active.current_item || null;
      if (!item) {
        const next = await nextPublicationBatchItem(active.batch_run_id, active.executor_token);
        if (!next.item) {
          if (["completed", "cancelled", "paused", "interrupted"].includes(next.state)) await storeExecution(null);
          return { state: next.state || "completed" };
        }
        item = next.item;
        active.current_item = item;
        await storeExecution(active);
      }
      try {
        await processItem(active, item);
      } catch (error) {
        if (["BATCH_NOT_RUNNING", "BATCH_CANCELLED"].includes(error?.code)) {
          await storeExecution(null);
          return { state: "interrupted", code: error.code };
        }
        throw error;
      }
      delete active.current_item;
      delete active.current_tab_id;
      await storeExecution(active);
    }
    await storeExecution(null);
    return { state: "failed", code: "BATCH_ITEM_LIMIT" };
  })().finally(() => { running = null; });
  return running;
}

export async function claimAndRunPublicationBatch(batchRunId, claimToken) {
  const result = await claimPublicationBatch(batchRunId, claimToken);
  const execution = { batch_run_id: batchRunId, executor_token: result.executor_token };
  await storeExecution(execution);
  runPublicationBatch(execution).catch(() => {});
  return { batch: result.batch, started: true };
}

export function resumePublicationBatch() {
  return runPublicationBatch().catch(() => ({ state: "interrupted" }));
}
