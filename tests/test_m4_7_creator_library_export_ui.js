"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");

class FakeClassList {
  toggle() {}
}

class FakeElement {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.dataset = {};
    this.classList = new FakeClassList();
    this.listeners = new Map();
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.indeterminate = false;
    this.textContent = "";
    this.value = "";
  }
  get options() { return this.children; }
  append(...items) { items.forEach(item => this.appendChild(item)); }
  appendChild(item) { this.children.push(item); item.parentNode = this; return item; }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  add(item) { this.appendChild(item); }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  async dispatch(type, event = {}) {
    for (const listener of this.listeners.get(type) || []) {
      await listener({ target: this, preventDefault() {}, ...event });
    }
  }
  click() { this.clicked = true; }
  remove() { this.removed = true; }
  closest(selector) {
    const match = selector.match(/^\[data-([a-z-]+)\]$/);
    if (!match) return null;
    const key = match[1].replace(/-([a-z])/g, (_all, letter) => letter.toUpperCase());
    return Object.hasOwn(this.dataset, key) ? this : null;
  }
}

function option(label, value) {
  const item = new FakeElement("option");
  item.textContent = label;
  item.value = value;
  return item;
}

function find(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children || []) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}

async function run() {
  const ids = [
    "creator-library-search", "creator-library-country", "creator-library-language",
    "creator-library-category", "creator-library-agency", "creator-library-tag",
    "creator-library-level", "creator-library-status", "creator-library-sort",
    "creator-library-page-size", "creator-library-refresh", "creator-library-card-view",
    "creator-library-table-view", "creator-library-select-all", "creator-library-export", "creator-library-batch-campaign",
    "creator-library-template-download", "creator-library-import-button", "creator-library-import-input",
    "creator-library-cards", "creator-library-table-wrap", "creator-library-body",
    "creator-library-empty", "creator-library-pagination", "creator-library-page-summary",
    "creator-library-page-buttons", "creator-library-import-result", "creator-library-import-summary",
    "creator-library-import-errors",
    "creator-library-batch-campaign-modal", "creator-library-batch-campaign-close",
    "creator-library-batch-campaign-count", "creator-library-batch-campaign-select",
    "creator-library-batch-campaign-message", "creator-library-batch-campaign-cancel",
    "creator-library-batch-campaign-submit", "creator-library-batch-campaign-form",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement("div", id)]));
  elements.get("creator-library-sort").value = "created_at_desc";
  elements.get("creator-library-page-size").value = "24";
  const body = new FakeElement("body");
  const downloads = [];
  const requests = [];
  const savedMessages = [];
  const errors = [];
  const bridgeCalls = [];
  let bridgeResult = null;
  let page;
  const api = {
    async get(url) {
      if (url === "/api/local/agencies") return { agencies: [] };
      if (url === "/api/campaigns") return {
        campaigns: [{ campaign_id: "campaign_one", name: "Launch", platform: "TikTok" }],
      };
      if (url.startsWith("/api/creator-library?")) {
        const secondPage = url.includes("page=2");
        return {
          total: 3, pages: 2, page: secondPage ? 2 : 1, page_size: 24, filter_options: {},
          creators: secondPage
            ? [{ creator_id: "creator_three", creator_name: "Three", platform: "YouTube", status: "discovered" }]
            : [
              { creator_id: "creator_one", creator_name: "One", platform: "TikTok", status: "discovered" },
              { creator_id: "creator_two", creator_name: "Two", platform: "Instagram", status: "contacted" },
            ],
        };
      }
      throw new Error(`unexpected GET ${url}`);
    },
    async post(url, payload) {
      requests.push({ url, payload });
      if (url === "/api/campaigns/campaign_one/creators/batch") {
        return {
          added: 1, restored: 0, already_present: 1, failed: 1,
          results: [
            { creator_id: "creator_one", status: "added", error: "" },
            { creator_id: "creator_two", status: "already_present", error: "" },
            { creator_id: "creator_three", status: "failed", error: "缺少账号" },
          ],
        };
      }
      throw new Error(`unexpected POST ${url}`);
    },
  };
  const window = {
    KOLConnectAPI: api,
    KOLConnectPages: { registerPage(_name, candidate) { page = candidate; } },
    KOLConnectCreatorCampaignModal: { create() { return { bind() {}, destroy() {} }; } },
    localStorage: { getItem() { return "card"; }, setItem() {} },
    confirm: () => true,
    URL: {
      createObjectURL(blob) { return `blob:${blob.name}`; },
      revokeObjectURL(url) { downloads.push({ revoked: url }); },
    },
    async fetch(url, options = {}) {
      requests.push({ url, options });
      return {
        ok: true,
        arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
        blob: async () => ({ name: url.includes("export") ? "export" : "template" }),
      };
    },
    btoa: binary => Buffer.from(binary, "binary").toString("base64"),
  };
  const document = {
    body,
    getElementById: id => elements.get(id) || null,
    createElement(tag) {
      const item = new FakeElement(tag);
      if (tag === "a") downloads.push(item);
      return item;
    },
  };
  const sandbox = { AbortController, Option: option, Promise, URLSearchParams, console, document, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "webapp/pages/creator-library.js"), "utf8"), sandbox);
  const resources = {
    signal: new AbortController().signal,
    createAbortController: () => new AbortController(),
    listen: (target, type, listener) => target?.addEventListener(type, listener),
    setTimeout: callback => callback(),
    cleanup() {},
  };
  const context = {
    state: {}, api, resources, params: {}, navigate: async () => {},
    ui: { showSaved(message) { savedMessages.push(message); }, showError(error) { errors.push(error); } },
  };
  await page.load(context);
  page.bind();
  assert.equal(elements.get("creator-library-export").disabled, true, "export starts disabled without a selection");

  const firstCheckbox = find(elements.get("creator-library-cards"), item => item.dataset.creatorSelectId === "creator_one");
  firstCheckbox.checked = true;
  await elements.get("creator-library-cards").dispatch("change", { target: firstCheckbox });
  assert.equal(elements.get("creator-library-export").disabled, false);
  assert.match(elements.get("creator-library-export").textContent, /1/);

  const selectAll = elements.get("creator-library-select-all");
  selectAll.checked = true;
  await selectAll.dispatch("change");
  assert.match(elements.get("creator-library-export").textContent, /2/);

  const nextPage = find(elements.get("creator-library-page-buttons"), item => item.dataset.creatorPage === "2");
  await elements.get("creator-library-page-buttons").dispatch("click", { target: nextPage });
  assert.match(elements.get("creator-library-export").textContent, /2/, "selection survives pagination");
  const thirdCheckbox = find(elements.get("creator-library-cards"), item => item.dataset.creatorSelectId === "creator_three");
  thirdCheckbox.checked = true;
  await elements.get("creator-library-cards").dispatch("change", { target: thirdCheckbox });
  assert.match(elements.get("creator-library-export").textContent, /3/);

  await elements.get("creator-library-batch-campaign").dispatch("click");
  assert.equal(elements.get("creator-library-batch-campaign-modal").hidden, false);
  assert.match(elements.get("creator-library-batch-campaign-count").textContent, /3/);
  elements.get("creator-library-batch-campaign-select").value = "campaign_one";
  await elements.get("creator-library-batch-campaign-form").dispatch("submit");
  const batchRequest = requests.find(request => request.url === "/api/campaigns/campaign_one/creators/batch");
  assert.deepEqual(Array.from(batchRequest.payload.creator_ids), ["creator_one", "creator_two", "creator_three"]);
  assert.match(elements.get("creator-library-batch-campaign-message").textContent, /失败 1/);
  assert.match(elements.get("creator-library-export").textContent, /1/, "only failed creators remain selected");

  window.pywebview = { api: { async save_xlsx(filename, payload) {
    bridgeCalls.push({ filename, payload });
    return bridgeResult || { saved: true, canceled: false, path: "C:\\Exports\\Creators.xlsx" };
  } } };
  await elements.get("creator-library-export").dispatch("click");
  const exportRequest = requests.find(request => request.url === "/api/creator-library/export");
  assert.equal(exportRequest.options.method, "POST");
  assert.deepEqual(JSON.parse(exportRequest.options.body).creator_ids, ["creator_three"]);
  assert.equal(bridgeCalls[0].filename, "KOLConnect_Creator_Export.xlsx");
  assert.equal(bridgeCalls[0].payload, "AQID");
  assert.match(savedMessages.pop(), /C:\\Exports\\Creators.xlsx/);

  await elements.get("creator-library-template-download").dispatch("click");
  assert.ok(requests.some(request => request.url === "/api/creator-library/import-template"));
  assert.equal(bridgeCalls[1].filename, "KOLConnect_Creator_Import_Template.xlsx");
  assert.match(savedMessages.pop(), /模板已保存到/);

  bridgeResult = { saved: false, canceled: true, path: null };
  await elements.get("creator-library-template-download").dispatch("click");
  assert.equal(savedMessages.length, 0, "cancel must not display a success message");

  bridgeResult = { saved: false, canceled: false, error: "保存失败" };
  await elements.get("creator-library-template-download").dispatch("click");
  assert.match(errors.pop().message, /保存失败/);

  delete window.pywebview;
  await elements.get("creator-library-template-download").dispatch("click");
  assert.ok(downloads.some(item => item.href === "blob:template" && item.clicked));

  const source = fs.readFileSync(path.join(ROOT, "webapp/pages/creator-library.js"), "utf8");
  assert.match(source, /URL\.createObjectURL/);
  assert.match(source, /pywebview\?\.api\?\.save_xlsx/);
  assert.match(source, /creator-library-select-all/);
  assert.match(source, /creators\/batch/);
  console.log("M4.7 Creator Library export UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
