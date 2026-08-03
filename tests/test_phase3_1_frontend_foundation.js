const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function runScript(relativePath, sandbox) {
  vm.runInContext(read(relativePath), sandbox, { filename: relativePath });
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
    this.dataset = {};
    this.classList = new FakeClassList(classes);
    this.listeners = new Map();
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
}

function createPageDocument(elements = new Map()) {
  const buttons = [];
  const sections = [];
  return {
    buttons,
    sections,
    getElementById(id) {
      return elements.get(id) || null;
    },
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
}

function createSandbox(document) {
  const window = {
    setInterval,
    clearInterval,
    setTimeout,
    clearTimeout,
  };
  const sandbox = { AbortController, console, document, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  return sandbox;
}

async function testApiClient() {
  const calls = [];
  const signal = new AbortController().signal;
  const window = {
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ ok: true }) };
    },
  };
  const sandbox = { console, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  runScript("webapp/services/api-client.js", sandbox);

  await window.KOLConnectAPI.get("/api/state", { signal });
  await window.KOLConnectAPI.post("/api/test", { name: "A" });
  await window.KOLConnectAPI.patch("/api/test/1", { name: "B" });

  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.signal, signal);
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.body, JSON.stringify({ name: "A" }));
  assert.equal(calls[2].options.method, "PATCH");
}

async function testPageLifecycleOrder() {
  const document = createPageDocument();
  const sandbox = createSandbox(document);
  runScript("webapp/core/page-registry.js", sandbox);
  const events = [];
  const lifecycle = name => ({
    load: () => events.push(`${name}.load`),
    bind: () => events.push(`${name}.bind`),
    unbind: () => events.push(`${name}.unbind`),
  });
  sandbox.window.KOLConnectPages.registerPage("first", lifecycle("first"));
  sandbox.window.KOLConnectPages.registerPage("second", lifecycle("second"));

  await sandbox.window.KOLConnectPages.navigate("first");
  await sandbox.window.KOLConnectPages.navigate("second");
  assert.deepEqual(events, [
    "first.load",
    "first.bind",
    "first.unbind",
    "second.load",
    "second.bind",
  ]);
}

async function testSettingsRepeatedEntry() {
  const ids = [
    "save-ui-settings",
    "system-health-run",
    "debug-mode",
    "feishu-save",
    "creator-library-save-config",
    "ui-language",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  const document = createPageDocument(elements);
  const sandbox = createSandbox(document);
  let settingsLoads = 0;

  sandbox.window.KOLConnectAPI = { post: async () => ({}) };
  sandbox.window.KOLConnectApp = {
    valueOf: () => "",
    checkedOf: () => false,
    loadSettingsState: async () => { settingsLoads += 1; },
    loadSystemHealth: async () => ({}),
    setDebugModeVisible: () => {},
    setLanguage: () => {},
    renderStaticText: () => {},
    renderCurrentTask: () => {},
    showSaved: () => {},
    showError: error => { throw error; },
  };

  runScript("webapp/core/page-resources.js", sandbox);
  runScript("webapp/core/page-registry.js", sandbox);
  runScript("webapp/pages/settings.js", sandbox);
  sandbox.window.KOLConnectPages.registerPage("dashboard", {
    load: () => {},
    bind: () => {},
    unbind: () => {},
  });

  await sandbox.window.KOLConnectPages.navigate("settings");
  assert.equal(elements.get("save-ui-settings").listenerCount("click"), 1);
  await sandbox.window.KOLConnectPages.navigate("settings");
  assert.equal(elements.get("save-ui-settings").listenerCount("click"), 1);
  await sandbox.window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("save-ui-settings").listenerCount("click"), 0);
  await sandbox.window.KOLConnectPages.navigate("settings");
  assert.equal(elements.get("save-ui-settings").listenerCount("click"), 1);
  assert.equal(settingsLoads, 3);
}

function testPageResourceCleanup() {
  const element = new FakeElement("target");
  const sandbox = createSandbox(createPageDocument());
  runScript("webapp/core/page-resources.js", sandbox);
  const resources = sandbox.window.KOLConnectPageResources.create();
  resources.listen(element, "click", () => {});
  resources.setInterval(() => {}, 10000);
  resources.setTimeout(() => {}, 10000);
  assert.equal(element.listenerCount("click"), 1);
  resources.cleanup();
  assert.equal(element.listenerCount("click"), 0);
  assert.equal(resources.signal.aborted, true);
}

function testScrapeTimersRemainGlobal() {
  const source = read("webapp/app.js");
  assert.match(source, /state\.scrapeStatusTimer = window\.setInterval\(refreshScrapeStatus, 3000\)/);
  assert.match(source, /state\.taskStatusTimer = window\.setInterval\(\(\) => loadTaskList\(\)\.catch\(\(\) => \{\}\), 2000\)/);
  assert.doesNotMatch(read("webapp/pages/settings.js"), /setInterval\(/);
}

function testScriptLoadingOrder() {
  const html = read("webapp/index.html");
  const scripts = [
    "services/api-client.js",
    "core/page-resources.js",
    "core/page-registry.js",
    "app.js",
    "pages/creator-library.js",
    "pages/creator-library-detail.js",
    "pages/products.js",
    "pages/campaigns.js",
    "pages/settings.js",
  ];
  let previousIndex = -1;
  scripts.forEach(script => {
    const scriptIndex = html.indexOf(`src="${script}"`);
    assert.ok(scriptIndex > previousIndex, `${script} must load in dependency order`);
    assert.ok(fs.existsSync(path.join(root, "webapp", script)), `${script} must exist`);
    previousIndex = scriptIndex;
  });
}

async function run() {
  await testApiClient();
  await testPageLifecycleOrder();
  await testSettingsRepeatedEntry();
  testPageResourceCleanup();
  testScrapeTimersRemainGlobal();
  testScriptLoadingOrder();
  console.log("Phase 3.1 frontend foundation: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
