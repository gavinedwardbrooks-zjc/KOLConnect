const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

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
    this.parentElement = null;
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  listenerCount(type) {
    return this.listeners.get(type)?.size || 0;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  append(...children) {
    children.forEach(child => this.appendChild(child));
  }

  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }

  closest(selector) {
    if (selector === "[data-campaign-creator-action]" && this.dataset.campaignCreatorAction) return this;
    return this.parentElement?.closest(selector) || null;
  }

  async dispatch(type, overrides = {}) {
    const event = { target: this, preventDefault() {}, ...overrides };
    for (const listener of [...(this.listeners.get(type) || [])]) await listener(event);
  }
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function findAction(node, action, recordId) {
  if (
    node.dataset.campaignCreatorAction === action
    && String(node.dataset.campaignCreatorId) === String(recordId)
  ) return node;
  for (const child of node.children) {
    const match = findAction(child, action, recordId);
    if (match) return match;
  }
  return null;
}

async function run() {
  const ids = [
    "campaign-detail-title", "campaign-detail-subtitle", "campaign-detail-back",
    "campaign-detail-loading", "campaign-detail-error", "campaign-detail-error-message",
    "campaign-detail-retry", "campaign-detail-content", "campaign-detail-badges",
    "campaign-detail-overview", "campaign-detail-goal", "campaign-detail-readonly",
    "campaign-creator-count", "campaign-creator-add-open", "campaign-creator-form-card",
    "campaign-creator-form-title", "campaign-creator-form", "campaign-creator-id",
    "campaign-creator-account-id", "campaign-creator-stage", "campaign-creator-quote",
    "campaign-creator-cost", "campaign-creator-publish-links", "campaign-creator-publish-date",
    "campaign-creator-views", "campaign-creator-likes", "campaign-creator-comments",
    "campaign-creator-roi", "campaign-creator-performance-note", "campaign-creator-form-error",
    "campaign-creator-form-save", "campaign-creator-form-cancel", "campaign-creator-empty",
    "campaign-creator-table-wrap", "campaign-creator-list-body",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  elements.get("campaign-creator-form-card").hidden = true;
  elements.get("campaign-creator-stage").value = "pending_contact";

  const document = {
    getElementById(id) {
      return elements.get(id) || null;
    },
    createElement() {
      return new FakeElement();
    },
  };

  let campaign = {
    campaign_id: "campaign_one",
    product_id: "product_one",
    product_name: "BlockBlast",
    name: "Brazil Launch",
    country: "Brazil",
    platform: "TikTok",
    start_date: "2026-08-01",
    end_date: "2026-08-31",
    status: "completed",
    budget: 1000,
    goal: "Launch",
    owner: "Maria",
    created_at: "2026-08-01T00:00:00Z",
    archived_at: null,
  };
  let relations = [{
    id: "relation_one",
    campaign_id: "campaign_one",
    creator_id: "creator_one",
    creator_name: "Ana",
    agency_id: null,
    agency_name: null,
    account_id: "account_one",
    account_platform: "TikTok",
    account_url: "https://www.tiktok.com/@ana",
    stage: "executing",
    creator_quote: 500,
    cost: 400,
    publish_links: JSON.stringify(["https://www.tiktok.com/@ana/video/1"]),
    publish_date: "2026-08-10",
    views: 10000,
    likes: 500,
    comments: 20,
    roi: 2.5,
    performance_note: "Good",
  }];
  const creators = [
    { creator_id: "creator_one", creator_name: "Ana", platform: "TikTok" },
    { creator_id: "creator_two", creator_name: "Bella", platform: "Instagram" },
  ];
  const accounts = {
    creator_one: [{ account_id: "account_one", platform: "TikTok", profile_url: "https://www.tiktok.com/@ana" }],
    creator_two: [{ account_id: "account_two", platform: "Instagram", profile_url: "https://www.instagram.com/bella" }],
  };
  const calls = [];

  const api = {
    async get(url, options = {}) {
      calls.push({ method: "GET", url, signal: options.signal });
      if (url === "/api/campaigns/campaign_one") return { campaign: clone(campaign) };
      if (url === "/api/campaigns/campaign_one/creators") return { campaign_creators: clone(relations) };
      if (url === "/api/creator-library") return { records: clone(creators) };
      const creatorMatch = url.match(/^\/api\/creator-library\/(.+)$/);
      if (creatorMatch) return { accounts: clone(accounts[creatorMatch[1]] || []) };
      throw new Error(`Unexpected GET ${url}`);
    },
    async post(url, payload, options = {}) {
      calls.push({ method: "POST", url, payload: clone(payload), signal: options.signal });
      relations.push({
        id: "relation_two",
        campaign_id: "campaign_one",
        creator_id: payload.creator_id,
        creator_name: "Bella",
        agency_name: "Studio B",
        account_platform: "Instagram",
        account_url: "https://www.instagram.com/bella",
        ...clone(payload),
      });
      return { campaign_creator: clone(relations.at(-1)) };
    },
    async patch(url, payload, options = {}) {
      calls.push({ method: "PATCH", url, payload: clone(payload), signal: options.signal });
      const recordId = url.split("/").at(-1);
      relations = relations.map(item => item.id === recordId ? { ...item, ...clone(payload) } : item);
      return { campaign_creator: clone(relations.find(item => item.id === recordId)) };
    },
  };

  let registeredPage = null;
  const resources = [];
  function createResources() {
    const listeners = [];
    const controllers = [];
    const manager = {
      signal: new AbortController().signal,
      listen(target, type, listener) {
        target.addEventListener(type, listener);
        listeners.push({ target, type, listener });
      },
      createAbortController() {
        const controller = new AbortController();
        controllers.push(controller);
        return controller;
      },
      cleanup() {
        listeners.forEach(({ target, type, listener }) => target.removeEventListener(type, listener));
        controllers.forEach(controller => controller.abort());
      },
    };
    resources.push(manager);
    return manager;
  }

  const notices = [];
  const window = {
    KOLConnectAPI: api,
    KOLConnectApp: {
      showSaved(message) { notices.push(message); },
      showError(error) { throw error; },
    },
    KOLConnectPageResources: { create: createResources },
    KOLConnectPages: {
      registerPage(name, page) {
        assert.equal(name, "campaign-detail");
        registeredPage = page;
      },
      async navigate() {},
    },
  };

  const context = { window, document, console, AbortController, Intl, URL, JSON, Date, Map, Set };
  vm.runInNewContext(
    fs.readFileSync(path.join(root, "webapp/pages/campaign-detail.js"), "utf8"),
    context,
  );
  assert.ok(registeredPage, "campaign-detail page should register");

  await registeredPage.load({ campaignId: "campaign_one" });
  const initialCalls = calls.splice(0);
  assert.deepEqual(initialCalls.map(call => `${call.method} ${call.url}`), [
    "GET /api/campaigns/campaign_one",
    "GET /api/campaigns/campaign_one/creators",
  ], "initial load must use two parallel aggregate requests only");
  assert.equal(elements.get("campaign-detail-title").textContent, "Brazil Launch");
  assert.equal(elements.get("campaign-creator-count").textContent, "1 位达人");
  assert.equal(elements.get("campaign-detail-content").hidden, false);
  assert.equal(elements.get("campaign-creator-add-open").disabled, false);

  registeredPage.bind();
  assert.equal(elements.get("campaign-creator-add-open").listenerCount("click"), 1);
  await elements.get("campaign-creator-add-open").dispatch("click");
  assert.equal(calls.splice(0)[0].url, "/api/creator-library");
  elements.get("campaign-creator-id").value = "creator_two";
  await elements.get("campaign-creator-id").dispatch("change");
  assert.equal(calls.splice(0)[0].url, "/api/creator-library/creator_two");
  elements.get("campaign-creator-account-id").value = "account_two";
  elements.get("campaign-creator-stage").value = "quoted";
  elements.get("campaign-creator-quote").value = "650";
  await elements.get("campaign-creator-form").dispatch("submit");
  const addCalls = calls.splice(0);
  const postCall = addCalls.find(call => call.method === "POST");
  assert.equal(postCall.url, "/api/campaigns/campaign_one/creators");
  assert.equal(postCall.payload.creator_id, "creator_two");
  assert.equal(postCall.payload.account_id, "account_two");
  assert.equal(relations.length, 2);

  const editButton = findAction(elements.get("campaign-creator-list-body"), "edit", "relation_one");
  assert.ok(editButton, "active Campaign should expose relation edit action");
  await elements.get("campaign-creator-list-body").dispatch("click", { target: editButton });
  elements.get("campaign-creator-account-id").value = "account_one";
  elements.get("campaign-creator-stage").value = "completed";
  elements.get("campaign-creator-quote").value = "700";
  elements.get("campaign-creator-cost").value = "450";
  elements.get("campaign-creator-publish-links").value = "https://www.tiktok.com/@ana/video/2";
  elements.get("campaign-creator-publish-date").value = "2026-08-20";
  elements.get("campaign-creator-views").value = "12000";
  elements.get("campaign-creator-likes").value = "800";
  elements.get("campaign-creator-comments").value = "35";
  elements.get("campaign-creator-roi").value = "3.2";
  elements.get("campaign-creator-performance-note").value = "Strong result";
  await elements.get("campaign-creator-form").dispatch("submit");
  const editCalls = calls.splice(0);
  const patchCall = editCalls.find(call => call.method === "PATCH");
  assert.equal(patchCall.url, "/api/campaign-creators/relation_one");
  assert.equal(patchCall.payload.stage, "completed");
  assert.equal(patchCall.payload.account_id, "account_one");
  assert.equal(patchCall.payload.creator_quote, "700");
  assert.equal(patchCall.payload.cost, "450");
  assert.deepEqual(patchCall.payload.publish_links, ["https://www.tiktok.com/@ana/video/2"]);
  assert.equal(patchCall.payload.publish_date, "2026-08-20");
  assert.equal(patchCall.payload.views, "12000");
  assert.equal(patchCall.payload.likes, "800");
  assert.equal(patchCall.payload.comments, "35");
  assert.equal(patchCall.payload.roi, "3.2");
  assert.equal(patchCall.payload.performance_note, "Strong result");

  await registeredPage.unbind();
  assert.equal(elements.get("campaign-creator-add-open").listenerCount("click"), 0);
  campaign.archived_at = "2026-08-30T00:00:00Z";
  await registeredPage.load({ campaignId: "campaign_one" });
  registeredPage.bind();
  assert.equal(elements.get("campaign-creator-add-open").disabled, true);
  assert.equal(elements.get("campaign-detail-readonly").hidden, false);
  assert.equal(findAction(elements.get("campaign-creator-list-body"), "edit", "relation_one"), null);
  assert.equal(elements.get("campaign-creator-add-open").listenerCount("click"), 1);
  await registeredPage.unbind();
  assert.equal(elements.get("campaign-creator-add-open").listenerCount("click"), 0);

  const source = fs.readFileSync(path.join(root, "webapp/pages/campaign-detail.js"), "utf8");
  const campaignsSource = fs.readFileSync(path.join(root, "webapp/pages/campaigns.js"), "utf8");
  assert.doesNotMatch(source, /\bfetch\s*\(/, "page must use api-client rather than direct fetch");
  assert.match(source, /Promise\.all\s*\(/, "initial detail requests should run in parallel");
  assert.match(campaignsSource, /createAction\("detail"/, "Campaign list must provide a detail action");
  assert.match(campaignsSource, /navigate\("campaign-detail",\s*\{\s*campaignId\s*\}\)/, "detail action must navigate with campaign id");
  assert.ok(notices.length >= 2, "add and edit should show saved feedback");
  console.log("Phase 3.10 Campaign Detail UI tests passed");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
