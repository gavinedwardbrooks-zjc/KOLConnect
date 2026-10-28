"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");

class Element {
  constructor(id = "") {
    this.id = id;
    this.listeners = new Map();
    this.children = [];
    this.dataset = {};
    this.textContent = "";
    this.value = "";
    this.checked = false;
    this.hidden = false;
    this.disabled = false;
    this.readOnly = false;
    this.placeholder = "";
  }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  async dispatch(type) {
    for (const listener of this.listeners.get(type) || []) await listener({ preventDefault() {} });
  }
  click() {
    if (this.disabled) return Promise.resolve();
    return this.dispatch("click");
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function run() {
  const ids = [
    "ai-provider", "ai-endpoint", "ai-model", "ai-enabled", "ai-api-key",
    "ai-clear-key", "ai-model-suggestions", "ai-endpoint-hint", "ai-provider-status",
    "ai-provider-result", "ai-provider-save", "ai-provider-test", "clean-reset-execute",
  ];
  const elements = new Map(ids.map(id => [id, new Element(id)]));
  const catalog = [
    { id: "custom", label: "Custom", base_url: "", custom_endpoint: true, model_suggestions: [] },
    { id: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com", custom_endpoint: false, model_suggestions: [] },
  ];
  const configuration = provider => ({
    provider,
    provider_catalog: catalog,
    profiles: {
      custom: { base_url: "https://ai.example.com/v1", model: "model-a", enabled: true, key_configured: true },
      deepseek: { base_url: "https://api.deepseek.com", model: "deep-model", enabled: true, key_configured: true },
    },
  });
  const pendingSave = deferred();
  const calls = [];
  const window = {
    crypto: { randomUUID: () => "ui-session" },
    confirm: () => false,
    KOLConnectAPI: {
      get: async url => {
        if (url === "/api/settings/ai-provider") return { configuration: configuration("custom") };
        if (url === "/api/feishu-chat/status") return { state: "disabled" };
        if (url.endsWith("/storage-migration/status")) return { status: "success", authority: "sqlite_active" };
        throw new Error(`unexpected GET ${url}`);
      },
      post: async (url, payload) => {
        calls.push({ url, payload });
        if (url === "/api/settings/ai-provider") return pendingSave.promise;
        throw new Error(`unexpected POST ${url}`);
      },
    },
    KOLConnectApp: {
      loadSettingsState: async () => ({}),
      valueOf: id => elements.get(id)?.value || "",
      checkedOf: id => Boolean(elements.get(id)?.checked),
      showError: error => { throw error; },
      t: key => ({
        settingsAiSaving: "正在安全保存 AI 配置…",
        settingsAiSaved: "AI 配置已保存，尚未调用模型。",
        settingsAiKeyConfigured: "已保存",
        settingsAiKeyMissing: "请输入",
        settingsAiKeyReady: "已配置",
        settingsNotConfigured: "未配置",
        settingsAiCustomEndpointHint: "custom",
        settingsAiPresetEndpointHint: "preset",
      }[key] || key),
    },
  };
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: () => new Element(),
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  const sandbox = { AbortController, console, document, Math, Promise, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  window.KOLConnectPages = { registerPage: (_name, page) => { sandbox.page = page; } };
  vm.runInContext(read("webapp/pages/settings.js"), sandbox);
  await sandbox.page.load();
  sandbox.page.bind();

  elements.get("ai-provider").value = "custom";
  elements.get("ai-endpoint").value = "https://ai.example.com/v1";
  elements.get("ai-model").value = "model-a";
  elements.get("ai-enabled").checked = true;
  elements.get("ai-api-key").value = "replacement-key";

  const firstSave = elements.get("ai-provider-save").click();
  assert.equal(elements.get("ai-provider-save").disabled, true);
  assert.equal(elements.get("ai-provider-result").textContent, "正在安全保存 AI 配置…");
  await elements.get("ai-provider-save").click();
  assert.equal(calls.filter(call => call.url === "/api/settings/ai-provider").length, 1, "duplicate save is blocked");

  elements.get("ai-provider").value = "deepseek";
  await elements.get("ai-provider").dispatch("change");
  pendingSave.resolve({ configuration: configuration("custom") });
  await firstSave;

  assert.equal(elements.get("ai-provider").value, "deepseek", "stale save response must not reset provider selection");
  assert.equal(elements.get("ai-provider-save").disabled, false);
  assert.equal(elements.get("ai-provider-result").textContent, "AI 配置已保存，尚未调用模型。");
  assert.equal(calls[0].payload.provider, "custom");
  assert.equal(calls[0].payload.api_key, "replacement-key");
  console.log("M9.1-D AI provider save concurrency UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
