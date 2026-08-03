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
    if (selector === "[data-dashboard-creator-id]" && this.dataset.dashboardCreatorId) return this;
    return this.parentElement?.closest(selector) || null;
  }

  async dispatch(type, overrides = {}) {
    const event = { target: this, preventDefault() {}, ...overrides };
    for (const listener of [...(this.listeners.get(type) || [])]) await listener(event);
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
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement("div", id)]));
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
  const api = {
    async get(url, options = {}) {
      calls.push({ url, signal: options.signal });
      const response = responses.length ? responses.shift() : dashboardResponse();
      return response instanceof Promise ? response : clone(response);
    },
  };
  const window = {
    AbortController,
    KOLConnectAPI: api,
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

  responses.push(dashboardResponse(30));
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/dashboard");
  assert.ok(calls[0].signal instanceof AbortSignal);
  assert.equal(elements.get("dashboard-total-creators").textContent, "30");
  assert.equal(elements.get("dashboard-campaigns").textContent, "3");
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 1);
  assert.equal(sections[0].listenerCount("click"), 1);

  const creatorButton = elements.get("dashboard-rising-creators").children[0];
  await sections[0].dispatch("click", { target: creatorButton });
  assert.equal(navigations.length, 1);
  assert.equal(navigations[0].pageName, "creator-library-detail");
  assert.equal(navigations[0].params.creatorId, "creator_one");

  await window.KOLConnectPages.navigate("products");
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 0);
  assert.equal(sections[0].listenerCount("click"), 0);
  responses.push(dashboardResponse(31));
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 1);
  assert.equal(sections[0].listenerCount("click"), 1);
  assert.equal(elements.get("dashboard-total-creators").textContent, "31");

  const stale = deferred();
  responses.push(stale.promise);
  const refreshPromise = elements.get("dashboard-refresh").dispatch("click");
  await Promise.resolve();
  const staleCall = calls.at(-1);
  await window.KOLConnectPages.navigate("products");
  assert.equal(staleCall.signal.aborted, true, "leaving Dashboard must abort its active request");
  stale.resolve(dashboardResponse(999));
  await refreshPromise;
  assert.equal(elements.get("dashboard-total-creators").textContent, "31", "stale responses must not update Dashboard DOM");
  assert.equal(errors.length, 0);

  const appSource = read("webapp/app.js");
  assert.doesNotMatch(appSource, /function\s+loadDashboard\s*\(/);
  assert.doesNotMatch(appSource, /function\s+renderDashboard\s*\(/);
  assert.doesNotMatch(appSource, /dashboard-refresh[^\n]*addEventListener/);
  assert.doesNotMatch(appSource, /dashboard:\s*\(\)\s*=>\s*loadDashboard/);

  const html = read("webapp/index.html");
  assert.match(html, /src="pages\/dashboard\.js"/);
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
