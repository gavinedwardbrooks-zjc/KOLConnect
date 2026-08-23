"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const source = fs.readFileSync(path.join(root, "webapp", "pages", "creator-library-detail.js"), "utf8");

class FakeElement {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.children = [];
    this.dataset = {};
    this.listeners = new Map();
    this.classList = { toggle() {} };
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this.children = children;
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  async dispatch(type, event = {}) {
    for (const listener of this.listeners.get(type) || []) {
      await listener({ target: this, preventDefault() {}, ...event });
    }
  }

  closest() {
    return null;
  }
}

function descendantsText(node) {
  return [node.textContent, ...node.children.flatMap(descendantsText)].filter(Boolean).join(" ");
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function run() {
  assert.match(html, /id="creator-ai-summary-card"/); // 22
  assert.match(html, /id="creator-ai-mock-badge"[^>]*>AI Mock</); // 23
  assert.match(html, /当前为本地规则生成，未连接真实 AI/); // 24

  const ids = [
    "creator-library-detail-summary", "creator-library-detail-level", "creator-library-data-meta",
    "creator-library-freshness", "creator-library-basic", "creator-library-video-metrics",
    "creator-library-strengths", "creator-library-risks", "creator-library-snapshots",
    "creator-library-snapshots-empty", "creator-cooperations-body", "creator-cooperations-empty",
    "cooperation-stat-count", "cooperation-stat-spend", "cooperation-stat-views", "cooperation-stat-roi",
    "creator-library-videos", "creator-library-detail-archive", "creator-library-detail-edit",
    "creator-library-detail-add-campaign", "creator-library-detail-task", "creator-library-detail-back",
    "creator-campaigns-body", "creator-campaigns-empty", "creator-campaigns-error",
    "creator-edit-modal", "creator-edit-modal-close", "creator-edit-cancel", "creator-edit-form",
    "creator-ai-summary-card", "creator-ai-mock-badge", "creator-ai-summary-disclosure",
    "creator-ai-summary-generate", "creator-ai-summary-status", "creator-ai-summary-content",
    "creator-ai-summary-profile", "creator-ai-summary-performance", "creator-ai-summary-data-status",
    "creator-ai-summary-freshness", "creator-ai-summary-observations", "creator-ai-summary-limitations",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement("div", id)]));
  elements.get("creator-edit-modal").hidden = true;
  elements.get("creator-ai-summary-content").hidden = true;
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: tag => new FakeElement(tag),
    querySelectorAll: () => [],
  };
  let registeredPage;
  const window = {
    document,
    confirm: () => true,
    localStorage: { setItem() {} },
    KOLConnectPages: { registerPage(_name, page) { registeredPage = page; } },
    KOLConnectCreatorCampaignModal: {
      create() { return { bind() {}, destroy() {}, open() {} }; },
    },
  };
  vm.runInNewContext(source, { window, document, console, setTimeout, clearTimeout, AbortController });

  const calls = [];
  let summaryRequest = deferred();
  const detail = {
    record: {
      creator_id: "creator_one", creator_name: "Creator One", platform: "TikTok",
      profile_url: "https://www.tiktok.com/@one", insight_level: "insufficient",
      data_updated_at: "2026-08-20T00:00:00Z", source: "excel", archived_at: "",
    },
    analysis: {
      creator: { creator_name: "Creator One", platform: "TikTok", profile_url: "https://www.tiktok.com/@one" },
      video_analysis: {}, creator_insight: {}, content_category: "Gaming", videos: [],
    },
    trend: { freshness: { status: "fresh", days: 3 } },
    snapshots: [], cooperations: [], cooperation_statistics: {},
  };
  const resources = {
    signal: {},
    createAbortController() { return { signal: {}, abort() {} }; },
    listen(target, type, listener) { target.addEventListener(type, listener); },
    cleanup() {},
  };
  const context = {
    state: { creatorLibrary: {} },
    params: { creatorId: "creator_one" },
    resources,
    ui: { showError() {}, showSaved() {} },
    navigate: async () => {},
    api: {
      async get(url) {
        calls.push(url);
        if (url.endsWith("/ai-summary")) return summaryRequest.promise;
        if (url.startsWith("/api/campaigns")) return { campaigns: [] };
        return detail;
      },
      async patch() {},
      async post() {},
    },
  };

  await registeredPage.load(context);
  registeredPage.bind();
  assert.equal(calls.some(url => url.endsWith("/ai-summary")), false); // 25

  const partial = {
    mode: "mock",
    data_status: "partial",
    profile: { name: "Creator One", platform: "TikTok", followers: "12000", country: "Brazil", language: "Portuguese", content_category: "Gaming" },
    performance: {
      average_views: { value: 12000, source: "creator_snapshot", measured_at: "2026-08-10T00:00:00Z", freshness: "update_recommended" },
      median_views: null,
      video_count: { value: 30, source: "creator_snapshot", measured_at: "2026-08-10T00:00:00Z", freshness: "update_recommended" },
      creator_score: null,
      stability: null,
    },
    observations: ["平台：TikTok"],
    limitations: [{ message: "缺少有效中位播放测量。" }],
    freshness: { status: "update_recommended" },
  };
  const firstClick = elements.get("creator-ai-summary-generate").dispatch("click");
  await Promise.resolve();
  assert.equal(calls.filter(url => url.endsWith("/ai-summary")).length, 1); // 26
  assert.match(elements.get("creator-ai-summary-status").textContent, /正在生成/); // 27
  summaryRequest.resolve(partial);
  await firstClick;
  assert.equal(elements.get("creator-ai-summary-content").hidden, false);
  assert.match(elements.get("creator-ai-summary-status").textContent, /部分数据/); // 28
  assert.match(descendantsText(elements.get("creator-ai-summary-performance")), /视频数量 30/); // 32

  summaryRequest = deferred();
  const insufficientClick = elements.get("creator-ai-summary-generate").dispatch("click");
  summaryRequest.resolve({
    ...partial,
    data_status: "insufficient",
    performance: { average_views: null, median_views: null, video_count: null, creator_score: null, stability: null },
    freshness: { status: "unknown" },
    limitations: [{ message: "当前缺少可用于表现分析的数据。" }],
  });
  await insufficientClick;
  assert.match(elements.get("creator-ai-summary-status").textContent, /数据不足/); // 29
  const missingVideoText = descendantsText(elements.get("creator-ai-summary-performance"));
  assert.match(missingVideoText, /视频数量 --/);
  assert.doesNotMatch(missingVideoText, /视频数量 0(?:\D|$)/); // 33

  summaryRequest = deferred();
  const staleClick = elements.get("creator-ai-summary-generate").dispatch("click");
  summaryRequest.resolve({ ...partial, freshness: { status: "stale" } });
  await staleClick;
  assert.match(elements.get("creator-ai-summary-status").textContent, /重新采集/); // 30

  const originalDetailSummary = elements.get("creator-library-detail-summary").textContent;
  summaryRequest = deferred();
  const errorClick = elements.get("creator-ai-summary-generate").dispatch("click");
  summaryRequest.reject(new Error("summary failed"));
  await errorClick;
  assert.match(elements.get("creator-ai-summary-status").textContent, /原始达人资料仍可正常查看/);
  assert.equal(elements.get("creator-library-detail-summary").textContent, originalDetailSummary); // 31

  registeredPage.unbind();
  console.log("M6.2 Creator AI Mock UI: 12/12 behaviors PASS");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
