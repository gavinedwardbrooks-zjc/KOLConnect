"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

class FakeClassList {
  constructor(values = []) {
    this.values = new Set(values);
  }
  contains(value) { return this.values.has(value); }
  toggle(value, enabled) {
    if (enabled) this.values.add(value);
    else this.values.delete(value);
  }
}

class FakeElement {
  constructor(id = "", classes = []) {
    this.id = id;
    this.children = [];
    this.dataset = {};
    this.classList = new FakeClassList(classes);
    this.listeners = new Map();
    this.style = {};
    this.hidden = false;
    this.textContent = "";
    this.parentNode = null;
    this.type = "";
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  replaceChildren(...children) {
    this.children = [];
    children.forEach(child => this.appendChild(child));
  }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }
  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }
  listenerCount(type) { return this.listeners.get(type)?.size || 0; }
  async dispatch(type, event = {}) {
    for (const listener of this.listeners.get(type) || []) {
      await listener({ target: this, preventDefault() {}, ...event });
    }
  }
  closest(selector) {
    const match = selector.match(/^\[data-([a-z-]+)\]$/);
    if (!match) return null;
    const key = match[1].replace(/-([a-z])/g, (_full, letter) => letter.toUpperCase());
    let current = this;
    while (current) {
      if (Object.hasOwn(current.dataset, key)) return current;
      current = current.parentNode;
    }
    return null;
  }
}

function walk(root) {
  return [root, ...root.children.flatMap(walk)];
}

function findByDataset(root, key, value) {
  return walk(root).find(element => String(element.dataset[key] || "") === String(value));
}

function createEnvironment() {
  const ids = [
    "agency-list-refresh", "agency-list-count", "agency-list-loading", "agency-list-error",
    "agency-list-error-message", "agency-list-retry", "agency-list-empty", "agency-list-table-wrap",
    "agency-list-body", "agency-overview-total", "agency-overview-creators", "agency-overview-contacts",
    "agency-detail-title", "agency-detail-subtitle", "agency-detail-back", "agency-detail-loading",
    "agency-detail-error", "agency-detail-error-message", "agency-detail-retry", "agency-detail-content",
    "agency-detail-name", "agency-detail-country", "agency-detail-website", "agency-detail-email",
    "agency-detail-stage", "agency-detail-owner", "agency-detail-note", "agency-contact-count",
    "agency-contacts-empty", "agency-contacts-table-wrap", "agency-contacts-body", "agency-creator-count",
    "agency-creators-empty", "agency-creators-table-wrap", "agency-creators-body", "agency-campaign-count",
    "agency-campaigns-unavailable", "agency-campaigns-empty", "agency-campaigns-table-wrap",
    "agency-campaigns-body",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  const buttons = ["agencies", "agency-detail"].map(page => {
    const button = new FakeElement("", ["nav-btn"]);
    button.dataset.page = page;
    button.dataset.primary = "mail";
    return button;
  });
  const sections = ["agencies", "agency-detail"].map(page => {
    const section = new FakeElement("", ["page"]);
    section.dataset.page = page;
    return section;
  });
  const document = {
    createElement: () => new FakeElement(),
    getElementById: id => elements.get(id) || null,
    querySelector(selector) {
      const match = selector.match(/^\.nav-btn\[data-page="(.+)"\]$/);
      return match ? buttons.find(button => button.dataset.page === match[1]) || null : null;
    },
    querySelectorAll(selector) {
      if (selector === ".nav-btn") return buttons;
      if (selector === ".page") return sections;
      return [];
    },
  };

  const calls = [];
  const navigation = [];
  const state = {
    agencies: [{
      agency_id: "agency_one", name: "North Studio", country: "US",
      contact_count: 1, creator_count: 2, updated_at: "2026-08-17T00:00:00Z",
    }],
    detail: {
      agency: {
        agency_id: "agency_one", name: "North Studio", country: "US",
        website: "https://agency.example", public_email: "hello@agency.example",
        cooperation_stage: "active", owner: "Alex", note: "Priority partner",
      },
      contacts: [],
      creators: [
        { creator_id: "creator_one", name: "Creator One", platform: "TikTok", country: "US", status: "active" },
        { creator_id: "creator_two", name: "Creator Two", platform: "YouTube", country: "CA", status: "active" },
      ],
    },
    contacts: [
      {
        contact_id: "contact_one", agency_id: "agency_one", name: "Sam",
        position: "Manager", email: "sam@example.com", whatsapp: "+1", status: "active",
      },
      {
        contact_id: "contact_other", agency_id: "agency_other", name: "Other",
        position: "Manager", email: "other@example.com", whatsapp: "+2", status: "active",
      },
    ],
    campaigns: {
      creator_one: [{ campaign_id: "campaign_one", name: "Launch", product_name: "App", status: "running", creators_count: 2 }],
      creator_two: [{ campaign_id: "campaign_one", name: "Launch", product_name: "App", status: "running", creators_count: 2 }],
    },
    detailError: false,
  };
  const api = {
    async get(url, options = {}) {
      calls.push({ method: "GET", url, signal: options.signal });
      if (url === "/api/local/agencies") return { agencies: structuredClone(state.agencies) };
      if (url === "/api/local/agencies/agency_one") {
        if (state.detailError) throw new Error("未找到 Agency。");
        return structuredClone(state.detail);
      }
      if (url === "/api/local/agency-contacts") {
        return { contacts: structuredClone(state.contacts) };
      }
      if (url.startsWith("/api/campaigns?creator_id=")) {
        const creatorId = decodeURIComponent(url.split("=")[1]);
        return { campaigns: structuredClone(state.campaigns[creatorId] || []) };
      }
      throw new Error(`Unexpected GET ${url}`);
    },
  };
  const window = {
    AbortController,
    KOLConnectAPI: api,
    KOLConnectApp: {
      navigate(page, params) { navigation.push({ page, params }); },
    },
    setInterval,
    clearInterval,
    setTimeout,
    clearTimeout,
  };
  const sandbox = { AbortController, console, document, Intl, Promise, URLSearchParams, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  vm.runInContext(read("webapp/core/page-registry.js"), sandbox);
  vm.runInContext(read("webapp/pages/agencies.js"), sandbox);
  return { calls, elements, navigation, state, window };
}

async function run() {
  const { calls, elements, navigation, state, window } = createEnvironment();

  await window.KOLConnectPages.navigate("agencies");
  assert.equal(elements.get("agency-list-body").children.length, 1);
  assert.equal(elements.get("agency-list-count").textContent, "1 个 Agency");
  assert.equal(elements.get("agency-overview-creators").textContent, "2");
  assert.equal(elements.get("agency-overview-contacts").textContent, "1");
  assert.equal(calls.filter(call => call.url === "/api/local/agencies").length, 1);

  const detailButton = findByDataset(elements.get("agency-list-body"), "agencyDetailId", "agency_one");
  assert.ok(detailButton, "Agency list must provide a detail action");
  await elements.get("agency-list-body").dispatch("click", { target: detailButton });
  assert.equal(navigation.at(-1).page, "agency-detail");
  assert.equal(navigation.at(-1).params.agencyId, "agency_one");

  await window.KOLConnectPages.navigate("agency-detail", { agencyId: "agency_one" });
  assert.equal(elements.get("agency-detail-title").textContent, "North Studio");
  assert.equal(elements.get("agency-contacts-body").children.length, 1, "contacts must use exact agency_id filtering");
  assert.equal(elements.get("agency-creators-body").children.length, 2);
  assert.equal(elements.get("agency-campaigns-body").children.length, 1, "duplicate Campaigns must be deduplicated");
  assert.equal(elements.get("agency-campaign-count").textContent, "1 个");
  assert.ok(calls.some(call => call.url === "/api/local/agencies/agency_one"));
  assert.ok(calls.some(call => call.url === "/api/local/agency-contacts"));
  assert.ok(calls.some(call => call.url === "/api/campaigns?creator_id=creator_one"));
  assert.ok(calls.some(call => call.url === "/api/campaigns?creator_id=creator_two"));

  state.detail.creators = [];
  state.contacts = [];
  await window.KOLConnectPages.navigate("agency-detail", { agencyId: "agency_one" });
  assert.equal(elements.get("agency-contacts-empty").hidden, false);
  assert.equal(elements.get("agency-creators-empty").hidden, false);
  assert.equal(elements.get("agency-campaigns-empty").hidden, false);

  state.detailError = true;
  await window.KOLConnectPages.navigate("agency-detail", { agencyId: "agency_one" });
  assert.equal(elements.get("agency-detail-error").hidden, false);
  assert.equal(elements.get("agency-detail-content").hidden, true);
  assert.match(elements.get("agency-detail-error-message").textContent, /未找到 Agency/);

  const source = read("webapp/pages/agencies.js");
  const html = read("webapp/index.html");
  assert.doesNotMatch(source, /\/api\/agencies/);
  assert.doesNotMatch(source, /AgencyRepository/);
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /KOLConnectAPI\.(post|patch|delete)/);
  assert.match(source, /\/api\/local\/agencies/);
  assert.match(source, /KOLConnectAPI\.get\("\/api\/local\/agency-contacts"/);
  assert.match(source, /contact\.agency_id/);
  assert.match(source, /\/api\/campaigns\?creator_id=/);
  assert.match(html, /data-page="agencies"/);
  assert.match(html, /data-page="agency-detail"/);
  assert.match(html, /src="pages\/agencies\.js"/);

  console.log("M4.3 Agency list and detail UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
