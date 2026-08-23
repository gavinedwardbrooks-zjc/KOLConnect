"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

async function loadSettings(pywebview) {
  const listeners = new Map();
  const apiCalls = [];
  const elements = new Map([
    ["creator-library-workbook-path-hint", { dataset: {}, textContent: "" }],
    ["creator-library-backup-workbook", { dataset: {}, textContent: "" }],
    ["browser-mode-exit-card", { hidden: true }],
    ["browser-mode-exit", { disabled: false, textContent: "退出浏览器模式" }],
  ]);
  let registeredPage = null;
  const window = {
    pywebview,
    KOLConnectPages: {
      registerPage(name, page) {
        if (name === "settings") registeredPage = page;
      },
    },
    KOLConnectPageResources: {
      create() {
        return {
          signal: new AbortController().signal,
          cleanup() {},
          listen(element, type, listener) { listeners.set(`${type}:${[...elements].find(([, value]) => value === element)?.[0]}`, listener); },
        };
      },
    },
    KOLConnectApp: {
      async loadSettingsState() {},
      valueOf() { return "C:/Data/Creator_Library.xlsx"; },
      showError(error) { throw error; },
    },
    KOLConnectAPI: {
      async post(url, payload) {
        apiCalls.push({ url, payload });
        return { ok: true, shutting_down: true };
      },
    },
  };
  const sandbox = {
    AbortController,
    console,
    document: { getElementById: id => elements.get(id) || null },
    window,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/pages/settings.js"), sandbox, {
    filename: "webapp/pages/settings.js",
  });
  assert.ok(registeredPage, "Settings page must register without pywebview");
  await registeredPage.load();
  registeredPage.bind();
  return { elements, listeners, apiCalls };
}

async function run() {
  const browser = await loadSettings(undefined);
  const browserHint = browser.elements.get("creator-library-workbook-path-hint");
  assert.equal(browserHint.dataset.runtimeMode, "browser");
  assert.match(browserHint.textContent, /高级本地文件设置/);
  assert.match(browserHint.textContent, /浏览器不会提供原生文件选择器/);
  assert.match(browserHint.textContent, /不会上传工作簿/);
  assert.equal(browser.elements.get("browser-mode-exit-card").hidden, false);
  await browser.listeners.get("click:browser-mode-exit")();
  assert.equal(browser.apiCalls.length, 1);
  assert.equal(browser.apiCalls[0].url, "/api/runtime/shutdown");
  assert.equal(Object.keys(browser.apiCalls[0].payload).length, 0);
  assert.equal(browser.elements.get("browser-mode-exit").disabled, true);
  assert.match(browser.elements.get("browser-mode-exit").textContent, /已退出/);

  const desktop = await loadSettings({ api: { save_xlsx() {} } });
  const desktopHint = desktop.elements.get("creator-library-workbook-path-hint");
  assert.equal(desktopHint.dataset.runtimeMode, "desktop");
  assert.match(desktopHint.textContent, /WPS 云盘/);
  assert.equal(desktop.elements.get("browser-mode-exit-card").hidden, true);

  const creatorSource = read("webapp/pages/creator-library.js");
  assert.match(creatorSource, /pywebview\?\.api\?\.save_xlsx/);
  assert.match(creatorSource, /URL\.createObjectURL/);
  assert.match(creatorSource, /anchor\.download = filename/);
  assert.doesNotMatch(creatorSource, /result\.desktop\s*\?[^:]+path[^:]+:\s*[^;]+path/);

  const html = read("webapp/index.html");
  assert.match(html, /id="creator-library-workbook-path-hint"/);
  assert.match(html, /id="browser-mode-exit"/);
  console.log("M6.1 Local Browser Mode UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
