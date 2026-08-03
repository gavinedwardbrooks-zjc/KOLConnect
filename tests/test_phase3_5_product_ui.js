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
    if (selector === "[data-product-action]" && this.dataset.productAction) return this;
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

function findAction(rootElement, action, productId) {
  if (
    rootElement.dataset.productAction === action
    && String(rootElement.dataset.productId) === String(productId)
  ) {
    return rootElement;
  }
  for (const child of rootElement.children) {
    const match = findAction(child, action, productId);
    if (match) return match;
  }
  return null;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function run() {
  const ids = [
    "product-include-archived",
    "product-create-open",
    "product-form-card",
    "product-form-title",
    "product-form",
    "product-name",
    "product-company-name",
    "product-note",
    "product-form-error",
    "product-form-save",
    "product-form-cancel",
    "product-list-count",
    "product-list-loading",
    "product-list-error",
    "product-list-error-message",
    "product-list-retry",
    "product-list-empty",
    "product-list-table-wrap",
    "product-list-body",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  elements.get("product-form-card").hidden = true;

  const navProducts = new FakeElement("", ["nav-btn", "nav-sub"]);
  navProducts.dataset.page = "products";
  navProducts.dataset.primary = "mail";
  const navDashboard = new FakeElement("", ["nav-btn", "nav-primary"]);
  navDashboard.dataset.page = "dashboard";
  navDashboard.dataset.primary = "dashboard";
  const sectionProducts = new FakeElement("", ["page"]);
  sectionProducts.dataset.page = "products";
  const sectionDashboard = new FakeElement("", ["page", "active"]);
  sectionDashboard.dataset.page = "dashboard";
  const navButtons = [navProducts, navDashboard];
  const sections = [sectionProducts, sectionDashboard];

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

  let products = [{
    product_id: "product_one",
    name: "BlockBlast",
    company_name: "Hungry Studio",
    note: "Puzzle",
    campaigns_count: 2,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-20T00:00:00Z",
    archived_at: null,
  }];
  const calls = [];
  const notices = [];
  const api = {
    async get(url, options = {}) {
      calls.push({ method: "GET", url, signal: options.signal });
      const includeArchived = url.includes("include_archived=true");
      return { products: clone(products.filter(product => includeArchived || !product.archived_at)) };
    },
    async post(url, payload, options = {}) {
      calls.push({ method: "POST", url, payload: clone(payload), signal: options.signal });
      const product = {
        product_id: "product_two",
        ...clone(payload),
        campaigns_count: 0,
        created_at: "2026-07-31T10:00:00Z",
        updated_at: "2026-07-31T10:00:00Z",
        archived_at: null,
      };
      products.push(product);
      return { product: clone(product) };
    },
    async patch(url, payload, options = {}) {
      calls.push({ method: "PATCH", url, payload: clone(payload), signal: options.signal });
      const productId = decodeURIComponent(url.split("/").pop());
      const product = products.find(item => item.product_id === productId);
      if (Object.prototype.hasOwnProperty.call(payload, "archived_at")) {
        product.archived_at = payload.archived_at ? "2026-07-31T12:00:00Z" : null;
      } else {
        Object.assign(product, clone(payload));
      }
      product.updated_at = "2026-07-31T12:00:00Z";
      return { product: clone(product) };
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
  const sandbox = { AbortController, console, document, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  vm.runInContext(read("webapp/core/page-registry.js"), sandbox);
  vm.runInContext(read("webapp/pages/products.js"), sandbox);
  window.KOLConnectPages.registerPage("dashboard", {
    load: () => {},
    bind: () => {},
    unbind: () => {},
  });

  await window.KOLConnectPages.navigate("products");
  assert.equal(calls.filter(call => call.method === "GET").length, 1);
  assert.equal(elements.get("product-list-body").children.length, 1);
  assert.equal(elements.get("product-list-count").textContent, "1 个产品");
  assert.equal(elements.get("product-create-open").listenerCount("click"), 1);

  await elements.get("product-create-open").dispatch("click");
  elements.get("product-name").value = "New Game";
  elements.get("product-company-name").value = "New Studio";
  elements.get("product-note").value = "Launch";
  await elements.get("product-form").dispatch("submit");
  assert.equal(calls.filter(call => call.method === "POST").length, 1);
  assert.equal(products.length, 2);
  assert.equal(elements.get("product-list-body").children.length, 2);

  let action = findAction(elements.get("product-list-body"), "edit", "product_two");
  assert.ok(action, "active Product must provide edit");
  await elements.get("product-list-body").dispatch("click", { target: action });
  elements.get("product-name").value = "New Game Updated";
  await elements.get("product-form").dispatch("submit");
  assert.equal(products.find(item => item.product_id === "product_two").name, "New Game Updated");

  action = findAction(elements.get("product-list-body"), "archive", "product_two");
  assert.ok(action, "active Product must provide archive");
  await elements.get("product-list-body").dispatch("click", { target: action });
  const archiveCall = calls.find(call => call.method === "PATCH" && call.payload.archived_at);
  assert.ok(archiveCall, "archive must PATCH archived_at with an ISO timestamp");
  assert.equal(elements.get("product-list-body").children.length, 1);

  elements.get("product-include-archived").checked = true;
  await elements.get("product-include-archived").dispatch("change");
  assert.equal(elements.get("product-list-body").children.length, 2);
  action = findAction(elements.get("product-list-body"), "restore", "product_two");
  assert.ok(action, "archived Product must provide restore");
  await elements.get("product-list-body").dispatch("click", { target: action });
  const restoreCall = calls.find(call => call.method === "PATCH" && call.payload.archived_at === null);
  assert.ok(restoreCall, "restore must PATCH archived_at=null");
  assert.equal(products.find(item => item.product_id === "product_two").archived_at, null);

  assert.equal(calls.some(call => call.url.startsWith("/api/campaigns")), false);
  assert.equal(calls.some(call => call.method === "DELETE"), false);

  await window.KOLConnectPages.navigate("products");
  assert.equal(elements.get("product-create-open").listenerCount("click"), 1);
  const lastGetSignal = calls.filter(call => call.method === "GET").at(-1).signal;
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("product-create-open").listenerCount("click"), 0);
  assert.equal(lastGetSignal.aborted, true);
  assert.equal(window.KOLConnectPages.getCurrentPage(), "dashboard");
  assert.ok(notices.length >= 4);

  const source = read("webapp/pages/products.js");
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /\/api\/campaigns/);
  console.log("Phase 3.5 Product Management UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
