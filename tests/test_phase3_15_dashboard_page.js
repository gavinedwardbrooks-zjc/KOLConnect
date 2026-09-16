const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
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
  constructor(tagName = "div", id = "", classes = []) {
    this.tagName = tagName;
    this.id = id;
    this.className = classes.join(" ");
    this.classList = new FakeClassList(classes);
    this.dataset = {};
    this.children = [];
    this.listeners = new Map();
    this.parentElement = null;
    this.textContent = "";
    this.type = "";
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
    const existingIndex = this.children.indexOf(child);
    if (existingIndex >= 0) this.children.splice(existingIndex, 1);
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

  querySelectorAll(selector) {
    if (selector === "[data-dashboard-v2-module]") {
      return this.children.filter(child => child.dataset.dashboardV2Module);
    }
    return [];
  }

  closest(selector) {
    if (selector === "[data-dashboard-campaign-id]" && this.dataset.dashboardCampaignId) return this;
    if (selector === "[data-dashboard-creator-id]" && this.dataset.dashboardCreatorId) return this;
    if (selector === "[data-dashboard-v2-open]" && this.dataset.dashboardV2Open) return this;
    if (selector === "[data-dashboard-v2-drawer-close]" && this.dataset.dashboardV2DrawerClose !== undefined) return this;
    if (selector === "[data-dashboard-v2-drawer-primary]" && this.dataset.dashboardV2DrawerPrimary) return this;
    if (selector === "#dashboard-v2-customize" && this.id === "dashboard-v2-customize") return this;
    return this.parentElement?.closest(selector) || null;
  }

  focus() {}

  async dispatch(type, overrides = {}) {
    const event = { target: this, preventDefault() {}, ...overrides };
    for (const listener of [...(this.listeners.get(type) || [])]) await listener(event);
  }

  getContext() {
    return { canvas: this };
  }
}

function dashboardResponse(totalCreators = 12) {
  return {
    overview: {
      total_creators: totalCreators,
      new_creators_7d: 2,
      discovered_count: 4,
      cooperating_count: 3,
      cooperation_spend: 1500,
      average_roi: 1.8,
    },
    creator_health: {
      rising_creators: [{ creator_id: "creator_one", creator_name: "Maria", platform: "TikTok", change: { metric: "followers", direction: "growth", delta: 200 } }],
      falling_creators: [],
      expired_creators: [],
    },
    cooperation_performance: {
      total_campaigns: 3,
      total_cost: 1500,
      total_views: 80000,
      average_roi: 1.8,
      top_creators: [],
    },
    action_items: {
      expired_creators: [],
      pending_contact: [],
      incomplete_cooperations: [],
    },
    platform_distribution: [
      { platform: "TikTok", count: 8 },
      { platform: "YouTube", count: 4 },
    ],
    creator_status_distribution: [
      { status: "discovered", count: 9 },
      { status: "contacted", count: 3 },
    ],
    creator_growth_trend: [
      { date: "2026-08-20", count: 1 },
      { date: "2026-08-21", count: 2 },
    ],
    dashboard_v2: {
      creator_count: totalCreators,
      account_count: totalCreators + 3,
      platform_accounts: [{ platform: "TikTok", count: 8 }],
      missing: {
        email_accounts: [{ creator_id: "creator_one", creator_name: "Maria", platform: "TikTok", username: "maria", profile_url: "https://www.tiktok.com/@maria" }],
        country_creators: [],
        language_creators: [],
        content_type_creators: [],
      },
      campaigns: [{ campaign_id: "campaign_one", name: "Campaign One", status: "running", creator_count: 2, published_count: 1 }],
    },
  };
}

function risksResponse() {
  return {
    summary: { high: 0, medium: 0, low: 0 },
    cards: [],
  };
}

function platformAnalyticsResponse() {
  return {
    platforms: [
      { platform: "tiktok", creator_count: 8, campaign_creator_count: 4, published_count: 3 },
      { platform: "instagram", creator_count: 2, campaign_creator_count: 1, published_count: 1 },
      { platform: "youtube", creator_count: 4, campaign_creator_count: 2, published_count: 1 },
    ],
    summary: { platform_count: 3, creator_count: 14, campaign_creator_count: 7, ignored_campaign_creator_count: 0 },
  };
}

function geographyResponse() {
  return {
    countries: [{ name: "Brazil", creator_count: 5, active_creator_count: 4 }],
    languages: [{ name: "Portuguese", creator_count: 5 }],
  };
}

function roiTrendResponse() {
  return {
    trend: [
      { month: "2026-01", average_recorded_roi: 1.2 },
      { month: "2026-03", average_recorded_roi: 2.4 },
    ],
  };
}

function deferred() {
  let resolve;
  const promise = new Promise(next => { resolve = next; });
  return { promise, resolve };
}

async function run() {
  const ids = [
    "dashboard-refresh", "dashboard-total-creators", "dashboard-new-creators",
    "dashboard-discovered", "dashboard-cooperating", "dashboard-spend",
    "dashboard-average-roi", "dashboard-campaigns", "dashboard-total-cost",
    "dashboard-total-views", "dashboard-cooperation-roi", "dashboard-rising-creators",
    "dashboard-falling-creators", "dashboard-expired-creators", "dashboard-action-expired",
    "dashboard-pending-contact", "dashboard-incomplete-cooperations", "dashboard-top-creators",
    "dashboard-platform-chart", "dashboard-status-chart", "dashboard-growth-chart",
    "dashboard-platform-chart-empty", "dashboard-status-chart-empty", "dashboard-growth-chart-empty",
    "dashboard-risk-high", "dashboard-risk-medium", "dashboard-risk-low", "dashboard-risk-error",
    "dashboard-platform-analytics-chart", "dashboard-platform-analytics-empty",
    "dashboard-platform-analytics-error", "dashboard-country-list", "dashboard-language-list",
    "dashboard-geography-error", "dashboard-roi-trend-chart", "dashboard-roi-trend-empty",
    "dashboard-roi-trend-error", "dashboard-roi-latest",
    "dashboard-v2-creator-count", "dashboard-v2-account-count", "dashboard-v2-campaign-count",
    "dashboard-v2-spend", "dashboard-v2-roi", "dashboard-v2-missing-email",
    "dashboard-v2-missing-country", "dashboard-v2-missing-language", "dashboard-v2-missing-content-type",
    "dashboard-v2-today-list", "dashboard-v2-campaign-list", "dashboard-v2-platform-list",
    "dashboard-v2-health-score", "dashboard-v2-health-healthy", "dashboard-v2-health-warning",
    "dashboard-v2-health-critical", "dashboard-v2-country-list", "dashboard-v2-language-list",
    "dashboard-v2-roi-latest",
    "dashboard-v2-drawer", "dashboard-v2-drawer-title", "dashboard-v2-drawer-count",
    "dashboard-v2-drawer-search", "dashboard-v2-drawer-list", "dashboard-v2-drawer-primary",
  ];
  for (const platform of ["tiktok", "instagram", "youtube"]) {
    for (const metric of ["creators", "followers-median", "followers-average", "relations", "publish-rate", "views", "likes", "comments", "engagement", "cost", "roi"]) {
      ids.push(`platform-${platform}-${metric}`);
    }
  }
  const elements = new Map(ids.map(id => [id, new FakeElement("div", id)]));
  const v2Modules = ["today", "missing_info", "campaigns", "creator_overview", "data_freshness", "geography", "roi"];
  const v2ModuleContainer = new FakeElement("div", "dashboard-v2-modules");
  v2Modules.forEach(id => {
    const module = new FakeElement("section");
    module.dataset.dashboardV2Module = id;
    v2ModuleContainer.appendChild(module);
  });
  elements.set("dashboard-v2-modules", v2ModuleContainer);
  const navButtons = ["dashboard", "products"].map(name => {
    const button = new FakeElement("button", "", ["nav-btn"]);
    button.dataset.page = name;
    button.dataset.primary = name;
    return button;
  });
  const sections = ["dashboard", "products"].map(name => {
    const section = new FakeElement("section", "", ["page"]);
    section.dataset.page = name;
    return section;
  });

  const document = {
    getElementById(id) {
      return elements.get(id) || null;
    },
    createElement(tagName) {
      return new FakeElement(tagName);
    },
    querySelector(selector) {
      const navMatch = selector.match(/^\.nav-btn\[data-page="(.+)"\]$/);
      if (navMatch) return navButtons.find(button => button.dataset.page === navMatch[1]) || null;
      const pageMatch = selector.match(/^\.page\[data-page="(.+)"\]$/);
      if (pageMatch) return sections.find(section => section.dataset.page === pageMatch[1]) || null;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".nav-btn") return navButtons;
      if (selector === ".page") return sections;
      return [];
    },
  };

  const calls = [];
  const navigations = [];
  const errors = [];
  const responses = [];
  const chartCalls = [];
  class FakeChart {
    constructor(context, config) {
      this.context = context;
      this.config = config;
      this.destroyed = false;
      chartCalls.push(this);
    }

    destroy() {
      this.destroyed = true;
    }
  }
  const api = {
    async get(url, options = {}) {
      calls.push({ url, signal: options.signal });
      if (url === "/api/risks") return clone(risksResponse());
      if (url === "/api/analytics/platforms") return clone(platformAnalyticsResponse());
      if (url === "/api/analytics/geography") return clone(geographyResponse());
      if (url === "/api/analytics/roi-trend") return clone(roiTrendResponse());
      if (url !== "/api/dashboard") throw new Error(`Unexpected GET ${url}`);
      const response = responses.length ? responses.shift() : dashboardResponse();
      return response instanceof Promise ? response : clone(response);
    },
  };
  const window = {
    AbortController,
    KOLConnectAPI: api,
    Chart: FakeChart,
    KOLConnectApp: {
      showError(error) { errors.push(error); },
      navigate(pageName, params) {
        navigations.push({ pageName, params });
        return Promise.resolve();
      },
    },
    setInterval,
    clearInterval,
    setTimeout,
    clearTimeout,
    Event: class Event { constructor(type, options = {}) { this.type = type; this.bubbles = options.bubbles; } },
    localStorage: {
      values: new Map([
        ["kolconnect-dashboard-layout-v1", JSON.stringify({ order: ["cooperation_overview"], visible: { cooperation_overview: false } })],
        ["kolconnect-dashboard-layout-v2", JSON.stringify({ version: 2, order: v2Modules, visible: {} })],
      ]),
      getItem(key) { return this.values.get(key) || null; },
      setItem(key, value) { this.values.set(key, String(value)); },
    },
    dispatchEvent() {},
  };
  const sandbox = { AbortController, console, document, Intl, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  vm.runInContext(read("webapp/core/page-registry.js"), sandbox);
  vm.runInContext(read("webapp/pages/dashboard.js"), sandbox);
  window.KOLConnectPages.registerPage("products", {
    load: () => {},
    bind: () => {},
    unbind: () => {},
  });

  const initialDashboard = dashboardResponse(30);
  initialDashboard.action_items.incomplete_cooperations = [{
    cooperation_id: "relation_one",
    creator_id: "creator_one",
    creator_name: "Maria",
    platform: "TikTok",
    campaign: "Campaign One",
    campaign_id: "campaign_one",
  }];
  responses.push(initialDashboard);
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(calls.length, 5);
  const dashboardCall = calls.find(call => call.url === "/api/dashboard");
  const riskCall = calls.find(call => call.url === "/api/risks");
  const analyticsCall = calls.find(call => call.url === "/api/analytics/platforms");
  const geographyCall = calls.find(call => call.url === "/api/analytics/geography");
  const roiTrendCall = calls.find(call => call.url === "/api/analytics/roi-trend");
  assert.ok(dashboardCall, "Dashboard should request its existing aggregate payload");
  assert.ok(riskCall, "Dashboard should request the independent risk summary");
  assert.ok(analyticsCall, "Dashboard should request independent platform analytics");
  assert.ok(geographyCall, "Dashboard should request independent geography analytics");
  assert.ok(roiTrendCall, "Dashboard should request independent recorded ROI trend");
  assert.ok(dashboardCall.signal instanceof AbortSignal);
  assert.ok(riskCall.signal instanceof AbortSignal);
  assert.ok(analyticsCall.signal instanceof AbortSignal);
  assert.ok(geographyCall.signal instanceof AbortSignal);
  assert.ok(roiTrendCall.signal instanceof AbortSignal);
  assert.equal(elements.get("dashboard-total-creators").textContent, "30");
  assert.equal(elements.get("dashboard-campaigns").textContent, "3");
  assert.equal(elements.get("dashboard-risk-high").textContent, "0");
  assert.equal(elements.get("dashboard-risk-medium").textContent, "0");
  assert.equal(elements.get("dashboard-risk-low").textContent, "0");
  assert.equal(elements.get("dashboard-v2-creator-count").textContent, "30");
  assert.equal(elements.get("dashboard-v2-account-count").textContent, "33");
  assert.equal(elements.get("dashboard-v2-missing-email").textContent, "1");
  assert.equal(elements.get("dashboard-v2-campaign-list").children[0].dataset.dashboardCampaignId, "campaign_one");
  const missingEmailButton = new FakeElement("button");
  missingEmailButton.dataset.dashboardV2Open = "missing-email";
  await sections[0].dispatch("click", { target: missingEmailButton });
  assert.equal(elements.get("dashboard-v2-drawer").hidden, false);
  assert.equal(elements.get("dashboard-v2-drawer-count").textContent, "共 1 个账号");
  assert.equal(elements.get("dashboard-v2-drawer-list").children.length, 1, "drawer must use the same collection as the missing-email metric");
  assert.equal(elements.get("dashboard-v2-drawer-primary").textContent, "批量补全邮箱");
  const drawerViewCreator = elements.get("dashboard-v2-drawer-list").children[0].children[3].children.at(-1);
  await elements.get("dashboard-v2-drawer").dispatch("click", { target: drawerViewCreator });
  assert.equal(navigations.length, 1);
  assert.equal(navigations[0].pageName, "creator-library-detail", "drawer must open the existing Creator detail workflow");
  assert.equal(navigations[0].params.creatorId, "creator_one");
  const campaignOverview = new FakeElement("button");
  campaignOverview.dataset.dashboardV2Open = "campaigns";
  await sections[0].dispatch("click", { target: campaignOverview });
  assert.equal(navigations[1].pageName, "campaigns", "Campaign overview opens the existing Campaign workflow");
  const accountOverview = new FakeElement("button");
  accountOverview.dataset.dashboardV2Open = "accounts";
  await sections[0].dispatch("click", { target: accountOverview });
  assert.equal(navigations[2].pageName, "creator-library", "Account overview opens the existing Creator Library workflow");
  assert.equal(chartCalls.length, 5);
  assert.deepEqual(chartCalls[0].config.data.labels, ["TikTok", "YouTube"]);
  assert.deepEqual(chartCalls[1].config.data.datasets[0].data, [9, 3]);
  assert.deepEqual(chartCalls[2].config.data.datasets[0].data, [1, 2]);
  assert.deepEqual(Array.from(chartCalls[3].config.data.labels), ["TikTok", "Instagram", "YouTube"]);
  assert.deepEqual(Array.from(chartCalls[4].config.data.labels), ["2026-01", "2026-03"]);
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 1);
  assert.equal(sections[0].listenerCount("click"), 1);

  const preferences = window.KOLConnectDashboardPreferences;
  assert.deepEqual(Array.from(preferences.get().order), v2Modules, "V2 must ignore retired V1 layouts");
  assert.equal(preferences.get().visible.today, true, "today remains fixed and visible");

  // This mirrors Settings -> Dashboard without a browser reload: Settings only
  // mutates the shared preferences, then the page registry reactivates Dashboard.
  preferences.setVisible("missing_info", false);
  assert.equal(v2ModuleContainer.children.find(node => node.dataset.dashboardV2Module === "missing_info").hidden, true);
  assert.equal(v2ModuleContainer.children[0].dataset.dashboardV2Module, "today", "today remains first");
  preferences.move("campaigns", -1);
  assert.deepEqual(Array.from(preferences.get().order).slice(0, 3), ["today", "campaigns", "missing_info"]);
  await window.KOLConnectPages.navigate("products");
  responses.push(dashboardResponse(30));
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(v2ModuleContainer.children.find(node => node.dataset.dashboardV2Module === "missing_info").hidden, true, "hidden optional section stays absent after Settings -> Dashboard navigation");
  assert.deepEqual(
    Array.from(v2ModuleContainer.children).map(node => node.dataset.dashboardV2Module).slice(0, 3),
    ["today", "campaigns", "missing_info"],
    "Dashboard reapplies the persisted V2 order when it becomes active",
  );
  preferences.setVisible("missing_info", true);
  await window.KOLConnectPages.navigate("products");
  const reenabledDashboard = dashboardResponse(30);
  reenabledDashboard.action_items.incomplete_cooperations = [{
    cooperation_id: "relation_one",
    creator_id: "creator_one",
    creator_name: "Maria",
    platform: "TikTok",
    campaign: "Campaign One",
    campaign_id: "campaign_one",
  }];
  responses.push(reenabledDashboard);
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(v2ModuleContainer.children.find(node => node.dataset.dashboardV2Module === "missing_info").hidden, false, "re-enabled optional section returns without an application reload");
  preferences.reset();
  assert.deepEqual(Array.from(preferences.get().order), v2Modules);
  window.localStorage.setItem("kolconnect-dashboard-layout-v2", "{not-json");
  assert.deepEqual(Array.from(preferences.get().order), v2Modules, "malformed V2 settings must safely fall back");

  const creatorButton = elements.get("dashboard-rising-creators").children[0];
  await sections[0].dispatch("click", { target: creatorButton });
  assert.equal(navigations.length, 4);
  assert.equal(navigations[3].pageName, "creator-library-detail");
  assert.equal(navigations[3].params.creatorId, "creator_one");

  const reviewButton = elements.get("dashboard-incomplete-cooperations").children[0];
  await sections[0].dispatch("click", { target: reviewButton });
  assert.equal(navigations.length, 5);
  assert.equal(navigations[4].pageName, "campaign-detail");
  assert.equal(navigations[4].params.campaignId, "campaign_one");

  await window.KOLConnectPages.navigate("products");
  assert.equal(chartCalls.filter(chart => chart.destroyed).length, 15, "each Dashboard exit must clean up its own chart set");
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 0);
  assert.equal(sections[0].listenerCount("click"), 0);
  responses.push(dashboardResponse(31));
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 1);
  assert.equal(sections[0].listenerCount("click"), 1);
  assert.equal(elements.get("dashboard-total-creators").textContent, "31");

  const emptyCharts = dashboardResponse(32);
  emptyCharts.platform_distribution = [];
  emptyCharts.creator_status_distribution = [];
  emptyCharts.creator_growth_trend = [];
  responses.push(emptyCharts);
  await elements.get("dashboard-refresh").dispatch("click");
  assert.equal(elements.get("dashboard-platform-chart-empty").hidden, false);
  assert.equal(elements.get("dashboard-status-chart-empty").hidden, false);
  assert.equal(elements.get("dashboard-growth-chart-empty").hidden, false);
  assert.equal(elements.get("dashboard-total-creators").textContent, "32");

  const stale = deferred();
  responses.push(stale.promise);
  const callsBeforeStaleRefresh = calls.length;
  const refreshPromise = elements.get("dashboard-refresh").dispatch("click");
  await Promise.resolve();
  const staleCall = calls.slice(callsBeforeStaleRefresh).find(call => call.url === "/api/dashboard");
  assert.ok(staleCall, "refresh should make a Dashboard request");
  await window.KOLConnectPages.navigate("products");
  assert.equal(staleCall.signal.aborted, true, "leaving Dashboard must abort its active request");
  stale.resolve(dashboardResponse(999));
  await refreshPromise;
  assert.equal(elements.get("dashboard-total-creators").textContent, "32", "stale responses must not update Dashboard DOM");
  assert.equal(errors.length, 0);

  const appSource = read("webapp/app.js");
  assert.doesNotMatch(appSource, /function\s+loadDashboard\s*\(/);
  assert.doesNotMatch(appSource, /function\s+renderDashboard\s*\(/);
  assert.doesNotMatch(appSource, /dashboard-refresh[^\n]*addEventListener/);
  assert.doesNotMatch(appSource, /dashboard:\s*\(\)\s*=>\s*loadDashboard/);

  const html = read("webapp/index.html");
  assert.match(html, /src="vendor\/chart\.umd\.min\.js"/);
  assert.doesNotMatch(html, /https?:\/\/.*chart/i);
  assert.match(html, /id="dashboard-platform-chart"/);
  assert.match(html, /id="dashboard-status-chart"/);
  assert.match(html, /id="dashboard-growth-chart"/);
  assert.match(html, /src="pages\/dashboard\.js"/);
  assert.match(html, /id="dashboard-v2-modules"/);
  assert.match(html, /id="dashboard-v2-drawer"/);
  assert.match(html, /data-dashboard-v2-open="missing-email"/);
  assert.doesNotMatch(read("webapp/pages/dashboard.js"), /account_uid/);
  const styles = read("webapp/styles.css");
  assert.match(styles, /\.dashboard-v2-grid \{ display: grid; grid-template-columns: minmax\(0, 1\.2fr\) minmax\(320px, \.8fr\)/);
  assert.match(styles, /\.dashboard-v2-module\.dashboard-v2-wide \{ grid-column: 1 \/ -1; \}/);
  assert.match(styles, /\.dashboard-v2-grid \{ grid-template-columns: 1fr; \}/);
  assert.match(html, />活跃 Campaign</);
  assert.match(html, />待复盘</);
  assert.doesNotMatch(html, />合作数量</);
  assert.doesNotMatch(html, />合作记录缺失</);
  console.log("Phase 3.15 Dashboard page migration: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
