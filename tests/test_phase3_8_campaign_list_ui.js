const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

class FakeClassList {
  constructor(values = []) {
    this.values = new Set(values);
  }

  contains(value) {
    return this.values.has(value);
  }

  toggle(value, enabled) {
    if (enabled) this.values.add(value);
    else this.values.delete(value);
  }
}

class FakeElement {
  constructor(id = "", classes = []) {
    this.id = id;
    this.className = classes.join(" ");
    this.classList = new FakeClassList(classes);
    this.dataset = {};
    this.children = [];
    this.listeners = new Map();
    this.hidden = false;
    this.style = {};
    this.textContent = "";
    this.value = "";
    this.checked = false;
    this.disabled = false;
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

  focus() {}

  closest(selector) {
    if (selector === "[data-campaign-action]" && this.dataset.campaignAction) return this;
    return this.parentElement?.closest(selector) || null;
  }

  async dispatch(type, overrides = {}) {
    const event = {
      target: this,
      preventDefault() {},
      ...overrides,
    };
    for (const listener of [...(this.listeners.get(type) || [])]) {
      await listener(event);
    }
  }
}

function findAction(rootElement, action, campaignId) {
  if (
    rootElement.dataset.campaignAction === action
    && String(rootElement.dataset.campaignId) === String(campaignId)
  ) {
    return rootElement;
  }
  for (const child of rootElement.children) {
    const match = findAction(child, action, campaignId);
    if (match) return match;
  }
  return null;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function run() {
  const ids = [
    "campaign-create-open",
    "campaign-product-filter",
    "campaign-status-filter",
    "campaign-start-date-from",
    "campaign-start-date-to",
    "campaign-date-filter-apply",
    "campaign-include-archived",
    "campaign-products-error",
    "campaign-form-card",
    "campaign-form-title",
    "campaign-form",
    "campaign-name",
    "campaign-product-id",
    "campaign-status",
    "campaign-platform",
    "campaign-country",
    "campaign-country-edit-note",
    "campaign-budget",
    "campaign-start-date",
    "campaign-end-date",
    "campaign-owner",
    "campaign-goal",
    "campaign-form-error",
    "campaign-form-save",
    "campaign-form-cancel",
    "campaign-list-count",
    "campaign-list-loading",
    "campaign-list-error",
    "campaign-list-error-message",
    "campaign-list-retry",
    "campaign-list-empty",
    "campaign-list-table-wrap",
    "campaign-list-body",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  elements.get("campaign-form-card").hidden = true;
  elements.get("campaign-status").value = "draft";
  elements.get("campaign-include-archived").checked = false;

  const navCampaigns = new FakeElement("", ["nav-btn", "nav-sub"]);
  navCampaigns.dataset.page = "campaigns";
  navCampaigns.dataset.primary = "mail";
  const navDashboard = new FakeElement("", ["nav-btn", "nav-primary"]);
  navDashboard.dataset.page = "dashboard";
  navDashboard.dataset.primary = "dashboard";
  const sectionCampaigns = new FakeElement("", ["page"]);
  sectionCampaigns.dataset.page = "campaigns";
  const sectionDashboard = new FakeElement("", ["page", "active"]);
  sectionDashboard.dataset.page = "dashboard";
  const navButtons = [navCampaigns, navDashboard];
  const sections = [sectionCampaigns, sectionDashboard];

  const document = {
    getElementById(id) {
      return elements.get(id) || null;
    },
    createElement() {
      return new FakeElement();
    },
    querySelector(selector) {
      const match = selector.match(/^\.nav-btn\[data-page="(.+)"\]$/);
      return match ? navButtons.find(button => button.dataset.page === match[1]) || null : null;
    },
    querySelectorAll(selector) {
      if (selector === ".nav-btn") return navButtons;
      if (selector === ".page") return sections;
      return [];
    },
  };

  const products = [
    { product_id: "product_one", name: "BlockBlast", company_name: "Hungry Studio" },
    { product_id: "product_two", name: "Color Flow", company_name: "Studio Two" },
  ];
  let campaigns = [{
    campaign_id: "campaign_one",
    product_id: "product_one",
    product_name: "BlockBlast",
    name: "Brazil Launch",
    creators_count: 3,
    status: "running",
    platform: "TikTok",
    country: "Brazil",
    budget: 1000,
    start_date: "2026-08-01",
    end_date: "2026-08-31",
    owner: "Maria",
    goal: "Launch",
    archived_at: null,
  }];
  let campaignApiError = false;
  const calls = [];
  const notices = [];
  const api = {
    async get(url, options = {}) {
      calls.push({ method: "GET", url, signal: options.signal });
      if (url === "/api/products") return { products: clone(products) };
      if (url.startsWith("/api/campaigns")) {
        if (campaignApiError) throw new Error("Campaign API failed");
        const query = url.includes("?") ? url.split("?")[1] : "";
        const params = new URLSearchParams(query);
        const productId = params.get("product_id") || "";
        const status = params.get("status") || "";
        const startDateFrom = params.get("start_date_from") || "";
        const startDateTo = params.get("start_date_to") || "";
        const includeArchived = params.get("include_archived") === "true";
        const filtered = campaigns.filter(campaign => {
          if (productId && campaign.product_id !== productId) return false;
          if (status && campaign.status !== status) return false;
          if (startDateFrom && campaign.start_date < startDateFrom) return false;
          if (startDateTo && campaign.start_date > startDateTo) return false;
          return includeArchived || !campaign.archived_at;
        });
        return { campaigns: clone(filtered) };
      }
      throw new Error(`Unexpected GET ${url}`);
    },
    async post(url, payload, options = {}) {
      calls.push({ method: "POST", url, payload: clone(payload), signal: options.signal });
      const product = products.find(item => item.product_id === payload.product_id);
      const campaign = {
        campaign_id: "campaign_two",
        product_name: product?.name || "",
        creators_count: 0,
        archived_at: null,
        ...clone(payload),
      };
      campaigns.push(campaign);
      return { campaign: clone(campaign) };
    },
    async patch(url, payload, options = {}) {
      calls.push({ method: "PATCH", url, payload: clone(payload), signal: options.signal });
      const campaignId = decodeURIComponent(url.split("/").pop());
      const campaign = campaigns.find(item => item.campaign_id === campaignId);
      Object.assign(campaign, clone(payload));
      const product = products.find(item => item.product_id === campaign.product_id);
      campaign.product_name = product?.name || "";
      return { campaign: clone(campaign) };
    },
  };

  const window = {
    AbortController,
    KOLConnectAPI: api,
    KOLConnectApp: {
      showSaved(message) { notices.push(message); },
      showError(error) { throw error; },
    },
    confirm: () => true,
    setInterval,
    clearInterval,
    setTimeout,
    clearTimeout,
  };
  const sandbox = { AbortController, console, document, Intl, URLSearchParams, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  vm.runInContext(read("webapp/core/page-registry.js"), sandbox);
  vm.runInContext(read("webapp/pages/campaigns.js"), sandbox);
  window.KOLConnectPages.registerPage("dashboard", {
    load: () => {},
    bind: () => {},
    unbind: () => {},
  });

  await window.KOLConnectPages.navigate("campaigns");
  assert.equal(calls.filter(call => call.url === "/api/products").length, 1);
  assert.equal(calls.filter(call => call.url === "/api/campaigns").length, 1);
  assert.equal(elements.get("campaign-list-body").children.length, 1);
  assert.equal(elements.get("campaign-list-count").textContent, "1 个 Campaign");
  assert.equal(elements.get("campaign-create-open").listenerCount("click"), 1);
  assert.equal(elements.get("campaign-date-filter-apply").listenerCount("click"), 1);

  elements.get("campaign-start-date-from").value = "2026-08-01";
  elements.get("campaign-start-date-to").value = "2026-08-31";
  await elements.get("campaign-date-filter-apply").dispatch("click");
  assert.match(calls.at(-1).url, /start_date_from=2026-08-01/);
  assert.match(calls.at(-1).url, /start_date_to=2026-08-31/);
  assert.equal(elements.get("campaign-list-body").children.length, 1, "date bounds must be inclusive");
  elements.get("campaign-start-date-from").value = "";
  elements.get("campaign-start-date-to").value = "";
  await elements.get("campaign-date-filter-apply").dispatch("click");

  elements.get("campaign-product-filter").value = "product_one";
  await elements.get("campaign-product-filter").dispatch("change");
  assert.match(calls.at(-1).url, /product_id=product_one/);
  assert.equal(calls.filter(call => call.url === "/api/products").length, 1);

  elements.get("campaign-status-filter").value = "running";
  await elements.get("campaign-status-filter").dispatch("change");
  assert.match(calls.at(-1).url, /status=running/);
  assert.match(calls.at(-1).url, /product_id=product_one/);

  elements.get("campaign-product-filter").value = "";
  elements.get("campaign-status-filter").value = "";
  await elements.get("campaign-status-filter").dispatch("change");

  await elements.get("campaign-create-open").dispatch("click");
  elements.get("campaign-name").value = "US Launch";
  elements.get("campaign-product-id").value = "product_two";
  elements.get("campaign-platform").value = "YouTube";
  elements.get("campaign-country").value = "USA";
  elements.get("campaign-budget").value = "2500";
  elements.get("campaign-owner").value = "John";
  await elements.get("campaign-form").dispatch("submit");
  assert.equal(calls.filter(call => call.method === "POST").length, 1);
  assert.equal(campaigns.length, 2);
  assert.equal(campaigns[1].product_id, "product_two");
  assert.equal(campaigns[1].country, "USA");

  let action = findAction(elements.get("campaign-list-body"), "edit", "campaign_two");
  assert.ok(action, "active Campaign must provide edit");
  await elements.get("campaign-list-body").dispatch("click", { target: action });
  elements.get("campaign-name").value = "US Launch Updated";
  elements.get("campaign-status").value = "running";
  await elements.get("campaign-form").dispatch("submit");
  assert.equal(campaigns[1].name, "US Launch Updated");
  assert.equal(campaigns[1].status, "running");

  action = findAction(elements.get("campaign-list-body"), "archive", "campaign_two");
  assert.ok(action, "active Campaign must provide archive");
  await elements.get("campaign-list-body").dispatch("click", { target: action });
  const archiveCall = calls.find(
    call => call.method === "PATCH" && typeof call.payload.archived_at === "string",
  );
  assert.ok(archiveCall, "archive must use the existing Campaign PATCH endpoint");
  assert.equal(campaigns[1].status, "running");
  assert.ok(campaigns[1].archived_at);

  elements.get("campaign-include-archived").checked = true;
  await elements.get("campaign-include-archived").dispatch("change");
  assert.match(calls.at(-1).url, /include_archived=true/);
  action = findAction(elements.get("campaign-list-body"), "restore", "campaign_two");
  assert.ok(action, "archived Campaign must provide restore");
  await elements.get("campaign-list-body").dispatch("click", { target: action });
  const restoreCall = calls.find(
    call => call.method === "PATCH" && Object.hasOwn(call.payload, "archived_at") && call.payload.archived_at === null,
  );
  assert.ok(restoreCall, "restore must clear archived_at through PATCH");
  assert.equal(campaigns[1].status, "running");
  assert.equal(campaigns[1].archived_at, null);

  assert.equal(calls.some(call => call.url.startsWith("/api/creator")), false);
  assert.equal(calls.some(call => call.method === "DELETE"), false);

  await window.KOLConnectPages.navigate("campaigns");
  assert.equal(elements.get("campaign-create-open").listenerCount("click"), 1);
  const lastCampaignSignal = calls.filter(call => call.url.startsWith("/api/campaigns")).at(-1).signal;
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("campaign-create-open").listenerCount("click"), 0);
  assert.equal(lastCampaignSignal.aborted, true);
  assert.equal(window.KOLConnectPages.getCurrentPage(), "dashboard");
  assert.ok(notices.length >= 4);

  products.splice(0, products.length);
  campaigns = [];
  await window.KOLConnectPages.navigate("campaigns");
  assert.equal(elements.get("campaign-list-empty").hidden, false, "empty Campaign list must show empty state");
  assert.equal(elements.get("campaign-list-error").hidden, true, "empty Campaign list is not an API error");
  assert.equal(elements.get("campaign-list-count").textContent, "0 个 Campaign");
  assert.equal(elements.get("campaign-create-open").disabled, true, "creation requires a Product");

  campaignApiError = true;
  await elements.get("campaign-list-retry").dispatch("click");
  assert.equal(elements.get("campaign-list-error").hidden, false, "real API failure must show error state");
  assert.equal(elements.get("campaign-list-error").style.display, "");
  assert.equal(elements.get("campaign-list-empty").hidden, true, "error state must not be presented as empty data");

  campaignApiError = false;
  await elements.get("campaign-list-retry").dispatch("click");
  assert.equal(elements.get("campaign-list-error").hidden, true, "successful retry must clear the error state");
  assert.equal(elements.get("campaign-list-error").style.display, "none");
  assert.equal(elements.get("campaign-list-error-message").textContent, "");
  assert.equal(elements.get("campaign-list-empty").hidden, false, "successful empty response must show empty state");

  const source = read("webapp/pages/campaigns.js");
  const html = read("webapp/index.html");
  assert.match(html, /id="campaign-start-date-from"/);
  assert.match(html, /id="campaign-start-date-to"/);
  assert.match(html, /id="campaign-date-filter-apply"/);
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /\/api\/creator/);
  assert.doesNotMatch(source, /\bdelete\s*\(/i);
  assert.doesNotMatch(source, /\{\s*status:\s*["']draft["']\s*\}/);
  console.log("Phase 3.8 Campaign List UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
