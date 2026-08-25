"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const source = fs.readFileSync(path.join(root, "webapp", "pages", "settings.js"), "utf8");

for (const id of [
  "feishu-chat-card", "feishu-chat-status", "feishu-chat-transport",
  "feishu-chat-bot", "feishu-chat-last-connected", "feishu-chat-last-error",
  "feishu-chat-test", "feishu-chat-enable", "feishu-chat-disable", "feishu-chat-result",
]) {
  assert(html.includes(`id="${id}"`), `missing Feishu chat UI element: ${id}`);
}
assert(!html.includes("tenant_access_token"));

function element() {
  return { textContent: "", hidden: false, disabled: false, dataset: {}, value: "" };
}

const ids = [
  "creator-library-backup-workbook", "creator-library-workbook-path-hint",
  "browser-mode-exit-card", "clean-reset-execute", "feishu-chat-status",
  "feishu-chat-transport", "feishu-chat-bot", "feishu-chat-last-connected",
  "feishu-chat-last-error", "feishu-chat-test", "feishu-chat-enable",
  "feishu-chat-disable", "feishu-chat-result",
];
const elements = Object.fromEntries(ids.map(id => [id, element()]));
const listeners = new Map();
const calls = [];
const scheduled = [];
let nextStatus = null;
let page;

const api = {
  async get(url) {
    calls.push({ method: "GET", url });
    const response = nextStatus || {
      state: "connected", transport: "long_connection", bot_enabled: true,
      last_connected_at: "2026-08-25T00:00:00Z", last_error_code: "",
    };
    nextStatus = null;
    return response;
  },
  async post(url) {
    calls.push({ method: "POST", url });
    if (url.endsWith("/test")) {
      return { ok: false, state: "error", error_code: "SDK_NOT_AVAILABLE", last_error_code: "SDK_NOT_AVAILABLE" };
    }
    if (url.endsWith("/disable")) {
      return { state: "disabled", transport: "long_connection", bot_enabled: false };
    }
    return { state: "connecting", transport: "long_connection", bot_enabled: true };
  },
};

const window = {
  KOLConnectAPI: api,
  KOLConnectApp: {
    async loadSettingsState() { return { feishu: { chat_enabled: false } }; },
    valueOf() { return ""; },
    checkedOf() { return false; },
    showError(error) { throw error; },
  },
  KOLConnectPageResources: {
    create() {
      return {
        signal: {},
        disposed: false,
        listen(target, type, callback) { listeners.set(`${type}:${Object.keys(elements).find(id => elements[id] === target)}`, callback); },
        setTimeout(callback) { scheduled.push(callback); return scheduled.length; },
        cleanup() { this.disposed = true; },
      };
    },
  },
  KOLConnectPages: { registerPage(name, value) { assert.strictEqual(name, "settings"); page = value; } },
  confirm() { return false; },
};
const context = {
  window,
  document: { getElementById(id) { return elements[id] || null; } },
  console,
  setTimeout,
  clearTimeout,
};

vm.runInNewContext(source, context, { filename: "settings.js" });

(async () => {
  await page.load();
  page.bind();
  assert(calls.some(call => call.method === "GET" && call.url === "/api/feishu-chat/status"));
  assert.strictEqual(elements["feishu-chat-status"].textContent, "已连接");
  assert.strictEqual(elements["feishu-chat-bot"].textContent, "已启用");

  await listeners.get("click:feishu-chat-test")();
  assert(calls.some(call => call.method === "POST" && call.url === "/api/feishu-chat/test"));
  assert(elements["feishu-chat-result"].textContent.includes("操作未完成：SDK_NOT_AVAILABLE"));
  assert(elements["feishu-chat-result"].textContent.includes("官方 SDK"));
  assert(!elements["feishu-chat-result"].textContent.includes("secret"));

  await listeners.get("click:feishu-chat-disable")();
  assert(calls.some(call => call.method === "POST" && call.url === "/api/feishu-chat/disable"));
  assert.strictEqual(elements["feishu-chat-status"].textContent, "未启用");

  await listeners.get("click:feishu-chat-enable")();
  assert(calls.some(call => call.method === "POST" && call.url === "/api/feishu-chat/enable"));
  assert.strictEqual(elements["feishu-chat-status"].textContent, "正在连接");
  nextStatus = {
    state: "connected", transport: "long_connection", bot_enabled: true,
    last_connected_at: "2026-08-25T01:00:00Z", last_error_code: "",
  };
  await scheduled.shift()();
  assert.strictEqual(elements["feishu-chat-status"].textContent, "已连接");
  assert.strictEqual(elements["feishu-chat-last-connected"].textContent, "2026-08-25T01:00:00Z");

  await listeners.get("click:feishu-chat-disable")();
  await listeners.get("click:feishu-chat-enable")();
  nextStatus = {
    state: "error", transport: "long_connection", bot_enabled: false,
    last_connected_at: "", last_error_code: "FEISHU_CHAT_CONNECT_TIMEOUT",
    app_secret: "must-not-render",
  };
  await scheduled.shift()();
  assert.strictEqual(elements["feishu-chat-status"].textContent, "连接失败");
  assert.strictEqual(elements["feishu-chat-last-error"].textContent, "FEISHU_CHAT_CONNECT_TIMEOUT");
  assert(elements["feishu-chat-result"].textContent.includes("飞书长连接建立超时"));
  assert(!elements["feishu-chat-result"].textContent.includes("must-not-render"));
  assert.strictEqual(elements["feishu-chat-enable"].disabled, false);

  page.unbind();
  console.log("M7.6 Feishu Chat Settings UI tests passed");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
