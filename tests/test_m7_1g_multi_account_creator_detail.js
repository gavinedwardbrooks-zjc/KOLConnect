"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");

class FakeElement {
  constructor(id = "") {
    this.id = id;
    this.dataset = {};
    this.children = [];
    this.listeners = new Map();
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.value = "";
    this.attributes = {};
    this.parentElement = null;
    this.classList = {
      values: new Set(),
      add: value => this.classList.values.add(value),
      toggle: (value, force) => force
        ? this.classList.values.add(value)
        : this.classList.values.delete(value),
    };
  }
  addEventListener(type, listener) {
    const values = this.listeners.get(type) || new Set();
    values.add(listener);
    this.listeners.set(type, values);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  closest(selector) {
    if (selector === "[data-creator-account-key]" && this.dataset.creatorAccountKey) return this;
    return this.parentElement?.closest(selector) || null;
  }
  async dispatch(type, target = this) {
    const event = { target, preventDefault() {} };
    for (const listener of [...(this.listeners.get(type) || [])]) await listener(event);
  }
}

function definitionValues(element) {
  const result = {};
  for (let index = 0; index < element.children.length; index += 2) {
    const term = element.children[index];
    const value = element.children[index + 1];
    result[term.textContent] = value.children[0]?.textContent || value.textContent;
  }
  return result;
}

function clone(value) { return JSON.parse(JSON.stringify(value)); }

async function run() {
  const ids = [
    "creator-account-count", "creator-account-options", "creator-account-empty",
    "creator-library-detail-summary", "creator-library-detail-level", "creator-library-data-meta",
    "creator-library-freshness", "creator-library-basic", "creator-library-video-metrics",
    "creator-library-recommendation", "creator-library-strengths", "creator-library-risks",
    "creator-library-detail-archive", "creator-library-detail-edit",
    "creator-library-detail-add-campaign", "creator-library-detail-task",
    "creator-ai-summary-status", "creator-ai-summary-content", "creator-ai-summary-generate",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  const document = {
    getElementById(id) { return elements.get(id) || null; },
    querySelectorAll() { return []; },
    createElement() { return new FakeElement(); },
  };
  const youtube = {
    account_id: "account_youtube", creator_id: "creator_insa",
    account_uid: "youtube|https://www.youtube.com/@insa011", platform: "YouTube",
    username: "insa011", profile_url: "https://www.youtube.com/@insa011",
    followers: "1.14M", last_scrape_time: "2026-08-24T08:05:38Z",
    data_source: "系统抓取", updated_at: "2026-08-24T08:20:22Z",
  };
  const tiktok = {
    account_id: "account_tiktok", creator_id: "creator_insa",
    account_uid: "tiktok|https://www.tiktok.com/@insa011_", platform: "TikTok",
    username: "insa011_", profile_url: "https://www.tiktok.com/@insa011_",
    followers: "627.6K", last_scrape_time: "2026-08-24T08:05:01Z",
    data_source: "系统抓取", updated_at: "2026-08-24T08:19:29Z",
  };
  const instagram = {
    account_id: "account_instagram", creator_id: "creator_insa",
    account_uid: "instagram|https://www.instagram.com/insa", platform: "Instagram",
    username: "insa", profile_url: "https://www.instagram.com/insa", followers: "300K",
  };
  const originalAccountUids = [tiktok, youtube, instagram].map(account => account.account_uid);
  let response = {
    record: {
      creator_id: "creator_insa", creator_name: "INSA", account_uid: youtube.account_uid,
      country: "brazil", language: "葡萄牙语", content_category: "pov",
      insight_level: "insufficient", source: "excel", archived_at: null,
    },
    analysis: {
      creator: { creator_name: "INSA", platform: "YouTube", profile_url: youtube.profile_url, followers: "1.14M" },
      video_analysis: { sample_size: 2, average_views: 999999, median_views: 888888 },
      creator_insight: {}, content_category: "pov", videos: [],
    },
    accounts: [tiktok, youtube],
    snapshots: [
      { account_uid: youtube.account_uid, followers: "1.14M", average_views: 120000, median_views: 90000, captured_at: "2026-08-24T08:05:38Z" },
      { account_uid: tiktok.account_uid, followers: "627.6K", average_views: 64000, median_views: 50000, captured_at: "2026-08-24T08:05:01Z" },
    ],
    trend: { freshness: { status: "fresh", days: 0 } },
    cooperations: [], cooperation_statistics: {},
  };
  const calls = [];
  const api = {
    async get(url) {
      calls.push({ method: "GET", url });
      if (url.startsWith("/api/creator-library/")) return clone(response);
      if (url.startsWith("/api/campaigns?")) return { campaigns: [] };
      throw new Error(`Unexpected GET ${url}`);
    },
    async post(url) { calls.push({ method: "POST", url }); throw new Error("write not expected"); },
    async patch(url) { calls.push({ method: "PATCH", url }); throw new Error("write not expected"); },
  };
  let registeredPage = null;
  function resources() {
    const listeners = [];
    return {
      signal: new AbortController().signal,
      createAbortController() { return new AbortController(); },
      listen(target, type, listener) { target.addEventListener(type, listener); listeners.push([target, type, listener]); },
      cleanup() { listeners.forEach(([target, type, listener]) => target.removeEventListener(type, listener)); },
    };
  }
  const window = {
    URL, localStorage: { setItem() {} },
    KOLConnectCreatorCampaignModal: { create() { return { bind() {}, destroy() {}, open() {} }; } },
    KOLConnectPages: { registerPage(name, page) { assert.equal(name, "creator-library-detail"); registeredPage = page; } },
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(root, "webapp/pages/creator-library-detail.js"), "utf8"),
    { window, document, console, AbortController, URL, Date, Intl, JSON, Math, Set },
  );
  const context = {
    params: { creatorId: "creator_insa", accountId: "account_youtube" },
    api, resources: resources(), state: { creatorLibrary: {} },
    navigate() {}, ui: { showError(error) { throw error; }, showSaved() {} },
  };
  await registeredPage.load(context);
  registeredPage.bind();
  assert.equal(elements.get("creator-account-count").textContent, "2 个");
  assert.equal(elements.get("creator-account-options").children.length, 2);
  let values = definitionValues(elements.get("creator-library-basic"));
  assert.equal(values["达人名称"], "INSA");
  assert.equal(values["平台"], "YouTube");
  assert.equal(values["账号"], "@insa011");
  assert.equal(values["主页链接"], youtube.profile_url);
  assert.equal(values["粉丝数"], "1.14M");
  assert.equal(definitionValues(elements.get("creator-library-video-metrics"))["平均播放"], "120,000");
  const aiStatus = elements.get("creator-ai-summary-status").textContent;

  const tiktokButton = elements.get("creator-account-options").children.find(
    button => button.dataset.creatorAccountKey === "account_tiktok",
  );
  await elements.get("creator-account-options").dispatch("click", tiktokButton.children[1]);
  values = definitionValues(elements.get("creator-library-basic"));
  assert.equal(values["达人名称"], "INSA");
  assert.equal(values["平台"], "TikTok");
  assert.equal(values["账号"], "@insa011_");
  assert.equal(values["主页链接"], tiktok.profile_url);
  assert.equal(values["粉丝数"], "627.6K");
  assert.deepEqual(
    [tiktok, youtube, instagram].map(account => account.account_uid),
    originalAccountUids,
  );
  assert.equal(definitionValues(elements.get("creator-library-video-metrics"))["平均播放"], "64,000");
  assert.equal(elements.get("creator-ai-summary-status").textContent, aiStatus);
  assert.equal(calls.some(call => call.method !== "GET"), false);

  response.accounts[0].followers = "";
  response.snapshots = response.snapshots.filter(snapshot => snapshot.account_uid !== tiktok.account_uid);
  context.params.accountId = "account_tiktok";
  await registeredPage.load(context);
  values = definitionValues(elements.get("creator-library-basic"));
  assert.equal(values["粉丝数"], "--");
  assert.equal(definitionValues(elements.get("creator-library-video-metrics"))["平均播放"], "--");

  response.accounts = [youtube];
  context.params.accountId = "";
  await registeredPage.load(context);
  assert.equal(elements.get("creator-account-options").children.length, 1);
  response.accounts = [tiktok, youtube, instagram];
  await registeredPage.load(context);
  assert.equal(elements.get("creator-account-options").children.length, 3);
  assert.equal(definitionValues(elements.get("creator-library-basic"))["平台"], "YouTube");
  assert.equal(response.accounts.map(account => account.account_uid).join("|"), [tiktok, youtube, instagram].map(account => account.account_uid).join("|"));
  console.log("M7.1g multi-account Creator Detail UI: OK");
}

run().catch(error => { console.error(error); process.exitCode = 1; });
