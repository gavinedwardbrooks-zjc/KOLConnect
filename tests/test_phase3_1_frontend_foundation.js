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
    this.textContent = "";
    this.disabled = false;
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

  async dispatch(type) {
    for (const listener of this.listeners.get(type) || []) {
      await listener({ target: this, preventDefault() {} });
    }
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
    "creator-library-workbook-path",
    "creator-library-backup-workbook",
    "creator-library-backup-latest",
    "creator-library-backup-create",
    "ui-language",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  const document = createPageDocument(elements);
  const sandbox = createSandbox(document);
  let settingsLoads = 0;
  const posts = [];
  const notices = [];

  sandbox.window.KOLConnectAPI = {
    post: async (url, payload) => {
      posts.push({ url, payload });
      if (url === "/api/settings/creator-library/backup") {
        return {
          ok: true,
          backup: {
            filename: "Creator_Library_20260822.xlsx",
            created_at: "2026-08-22T08:30:00Z",
            size: 1024,
          },
        };
      }
      return {};
    },
  };
  sandbox.window.KOLConnectApp = {
    valueOf: id => (id === "creator-library-workbook-path" ? "C:/Data/Creator_Library.xlsx" : ""),
    checkedOf: () => false,
    loadSettingsState: async () => { settingsLoads += 1; },
    loadSystemHealth: async () => ({}),
    setDebugModeVisible: () => {},
    setLanguage: () => {},
    renderStaticText: () => {},
    renderCurrentTask: () => {},
    showSaved: message => { notices.push(message); },
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
  assert.equal(elements.get("creator-library-backup-create").listenerCount("click"), 1);
  assert.equal(elements.get("creator-library-backup-workbook").textContent, "C:/Data/Creator_Library.xlsx");
  await elements.get("creator-library-backup-create").dispatch("click");
  const backupCall = posts.find(call => call.url === "/api/settings/creator-library/backup");
  assert.ok(backupCall, "settings backup card must call the manual workbook backup endpoint");
  assert.equal(Object.keys(backupCall.payload).length, 0);
  assert.match(elements.get("creator-library-backup-latest").textContent, /Creator_Library_20260822\.xlsx/);
  assert.equal(elements.get("creator-library-backup-create").disabled, false);
  assert.ok(notices.includes("达人库 Excel 备份已创建。"));
  await sandbox.window.KOLConnectPages.navigate("settings");
  assert.equal(elements.get("save-ui-settings").listenerCount("click"), 1);
  await sandbox.window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("save-ui-settings").listenerCount("click"), 0);
  await sandbox.window.KOLConnectPages.navigate("settings");
  assert.equal(elements.get("save-ui-settings").listenerCount("click"), 1);
  assert.equal(settingsLoads, 3);
  const html = read("webapp/index.html");
  assert.match(html, /id="creator-library-backup-workbook"/);
  assert.match(html, /id="creator-library-backup-latest"/);
  assert.match(html, /id="creator-library-backup-create"/);
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
