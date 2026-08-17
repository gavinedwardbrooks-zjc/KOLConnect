"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");

class FakeClassList {
  constructor() { this.values = new Set(); }
  toggle(value, enabled) {
    if (enabled) this.values.add(value);
    else this.values.delete(value);
  }
}

class FakeElement {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.listeners = new Map();
    this.dataset = {};
    this.classList = new FakeClassList();
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.value = "";
    this.files = [];
  }
  get options() { return this.children; }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  add(child) { this.appendChild(child); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
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
  closest(selector) {
    const match = selector.match(/^\[data-([a-z-]+)\]$/);
    if (!match) return null;
    const key = match[1].replace(/-([a-z])/g, (_full, letter) => letter.toUpperCase());
    return Object.hasOwn(this.dataset, key) ? this : null;
  }
}

function option(label, value, _defaultSelected = false, selected = false) {
  const item = new FakeElement("option");
  item.textContent = label;
  item.value = value;
  item.selected = selected;
  return item;
}

function createEnvironment() {
  const ids = [
    "creator-library-search", "creator-library-country", "creator-library-language",
    "creator-library-category", "creator-library-agency", "creator-library-tag",
    "creator-library-level", "creator-library-status", "creator-library-sort",
    "creator-library-page-size", "creator-library-refresh", "creator-library-card-view",
    "creator-library-table-view", "creator-library-cards", "creator-library-table-wrap",
    "creator-library-body", "creator-library-empty", "creator-library-pagination",
    "creator-library-page-summary", "creator-library-page-buttons",
    "creator-library-template-download", "creator-library-import-button",
    "creator-library-import-input", "creator-library-import-result",
    "creator-library-import-summary", "creator-library-import-errors",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement("div", id)]));
  elements.get("creator-library-sort").value = "created_at_desc";
  elements.get("creator-library-page-size").value = "50";
  const body = new FakeElement("body");
  const created = [];
  const document = {
    body,
    getElementById: id => elements.get(id) || null,
    createElement(tagName) {
      const item = new FakeElement(tagName);
      created.push(item);
      return item;
    },
  };
  const calls = [];
  let validationFailure = false;
  const api = {
    async get(url) {
      calls.push({ method: "GET", url });
      if (url === "/api/local/agencies") {
        return { agencies: [{ agency_id: "agency_one", name: "North Studio" }] };
      }
      if (url.startsWith("/api/creator-library?")) {
        return {
          total: 1, pages: 1, page: 1, page_size: 50, filter_options: {},
          creators: [{
            creator_id: "creator_one", creator_name: "Creator One", platform: "TikTok",
            profile_url: "https://www.tiktok.com/@one", content_category: "Tech",
            agency_id: "agency_one", agency_name: "North Studio", status: "discovered",
          }],
        };
      }
      throw new Error(`Unexpected GET ${url}`);
    },
    async postRaw(url, payload, options) {
      calls.push({ method: "POST_RAW", url, payload, options });
      if (validationFailure) {
        const error = new Error("BATCH_IMPORT_VALIDATION_FAILED");
        error.responseData = {
          ok: false,
          error: "BATCH_IMPORT_VALIDATION_FAILED",
          summary: { total_rows: 2, valid_new_rows: 1, skipped_existing: 0, invalid_rows: 1 },
          rows: [{ row: 3, status: "INVALID", code: "UNKNOWN_AGENCY", field: "agency_id" }],
        };
        throw error;
      }
      return { ok: true, data: { total_rows: 2, created: 1, skipped_existing: 1 } };
    },
  };
  let page;
  const storage = new Map([["creator_library_view_mode", "table"]]);
  const window = {
    KOLConnectAPI: api,
    KOLConnectPages: { registerPage(_name, candidate) { page = candidate; } },
    KOLConnectCreatorCampaignModal: { create() { return { bind() {}, destroy() {} }; } },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    confirm: () => true,
  };
  const sandbox = {
    AbortController, console, Date, document, Intl, Option: option, Promise, URLSearchParams, window,
  };
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
  return {
    calls, created, elements, page,
    setValidationFailure(value) { validationFailure = value; },
    context: {
      state: {}, api, resources, params: {}, navigate: async () => {},
      ui: { showSaved() {}, showError(error) { throw error; } },
    },
  };
}

async function run() {
  const env = createEnvironment();
  await env.page.load(env.context);
  env.page.bind();

  const agency = env.elements.get("creator-library-agency");
  assert.equal(agency.options[1].value, "agency_one");
  assert.equal(agency.options[1].textContent, "North Studio");
  const row = env.elements.get("creator-library-body").children[0];
  assert.equal(row.children[5].textContent, "North Studio", "Agency column must render agency_name");

  agency.value = "agency_one";
  await agency.dispatch("change");
  assert.ok(env.calls.some(call => call.url?.includes("agency_id=agency_one")));

  await env.elements.get("creator-library-template-download").dispatch("click");
  const download = env.created.find(item => item.tagName === "A" && item.clicked);
  assert.equal(download.href, "/api/creator-library/import-template");
  assert.equal(download.download, "KOLConnect_Creator_Import_Template.xlsx");

  const input = env.elements.get("creator-library-import-input");
  input.files = [{ name: "creators.xlsx", arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer }];
  await input.dispatch("change");
  const upload = env.calls.find(call => call.method === "POST_RAW");
  assert.equal(upload.url, "/api/creator-library/import");
  assert.equal(upload.options.headers["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  assert.match(env.elements.get("creator-library-import-summary").textContent, /新增 1/);
  assert.match(env.elements.get("creator-library-import-summary").textContent, /跳过已有 1/);

  env.setValidationFailure(true);
  input.files = [{ name: "invalid.xlsx", arrayBuffer: async () => new Uint8Array([4]).buffer }];
  await input.dispatch("change");
  assert.match(env.elements.get("creator-library-import-summary").textContent, /无效 1/);
  const errorText = env.elements.get("creator-library-import-errors").children
    .map(item => item.textContent).join(" ");
  assert.match(errorText, /第 3 行/);
  assert.match(errorText, /Agency 不存在/);

  const source = fs.readFileSync(path.join(ROOT, "webapp/pages/creator-library.js"), "utf8");
  assert.doesNotMatch(source, /\/api\/agencies/);
  assert.doesNotMatch(source, /FileReader/);
  console.log("M4.4 Creator Library Agency and XLSX import UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
