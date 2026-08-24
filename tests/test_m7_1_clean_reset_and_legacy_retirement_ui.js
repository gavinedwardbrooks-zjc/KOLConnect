"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");

class Element {
  constructor(id) {
    this.id = id;
    this.listeners = new Map();
    this.dataset = {};
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
  }
  addEventListener(type, listener) {
    const values = this.listeners.get(type) || new Set();
    values.add(listener);
    this.listeners.set(type, values);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  async click() {
    if (this.disabled) return;
    for (const listener of this.listeners.get("click") || []) {
      await listener({ target: this, preventDefault() {} });
    }
  }
}

async function run() {
  const html = read("webapp/index.html");
  const settingsSource = read("webapp/pages/settings.js");
  const serverSource = read("app/server.py");
  for (const retired of [
    "feishu-account-backfill-card",
    "feishu-creator-backfill-card",
    "feishu-legacy-creator-cleanup-card",
  ]) {
    assert.doesNotMatch(html, new RegExp(retired), `${retired} must be retired`);
  }
  assert.doesNotMatch(settingsSource, /account-backfill|creator-backfill|legacy-creator-cleanup/);
  assert.doesNotMatch(serverSource, /account_identity_backfill_handler|creator_identity_backfill_handler|legacy_creator_cleanup_handler/);
  assert.match(serverSource, /clean_reset_handler/);
  for (const retained of ["feishu-sync-validate", "feishu-sync-dry-run", "feishu-sync-full"]) {
    assert.match(html, new RegExp(`id="${retained}"`), `${retained} remains available`);
  }
  for (const id of [
    "clean-reset-card", "clean-reset-preview", "clean-reset-execute",
    "clean-reset-creators", "clean-reset-accounts", "clean-reset-videos",
    "clean-reset-snapshots", "clean-reset-campaigns", "clean-reset-result",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`), `${id} must render`);
  }
  assert.match(html, /clean-reset-execute[^>]*disabled/);
  assert.match(html, /Chrome 配置：保留/);

  const ids = [
    "clean-reset-preview", "clean-reset-execute", "clean-reset-creators",
    "clean-reset-accounts", "clean-reset-videos", "clean-reset-snapshots",
    "clean-reset-campaigns", "clean-reset-result",
  ];
  const elements = new Map(ids.map(id => [id, new Element(id)]));
  const calls = [];
  const confirmations = [false, true];
  const preview = {
    status: "success",
    review_items: [],
    summary: { creators: 2453, accounts: 2453, videos: 60, snapshots: 4909, campaigns: 0 },
  };
  const previews = [
    { status: "blocked", review_items: ["UNKNOWN_SHEET:UnexpectedBusinessData"], summary: {} },
    preview,
  ];
  const window = {
    confirm: message => {
      assert.match(message, /Creators: 2453/);
      assert.match(message, /Chrome 配置：保留/);
      assert.match(message, /飞书配置：保留/);
      return confirmations.shift();
    },
    KOLConnectAPI: {
      post: async (url, payload) => {
        calls.push({ url, payload });
        if (url.endsWith("preview")) return previews.shift();
        if (url.endsWith("execute")) return {
          status: "success",
          backup: { filename: "Creator_Library_before_clean_reset_20260824.xlsx" },
        };
        throw new Error(`unexpected request ${url}`);
      },
    },
    KOLConnectApp: {
      loadSettingsState: async () => ({}),
      valueOf: () => "",
      checkedOf: () => false,
      showError: error => { throw error; },
    },
  };
  const document = { getElementById: id => elements.get(id) || null };
  const sandbox = { AbortController, console, document, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  sandbox.window.KOLConnectPages = { registerPage: (_name, page) => { sandbox.page = page; } };
  vm.runInContext(settingsSource, sandbox);
  await sandbox.page.load();
  sandbox.page.bind();

  const execute = elements.get("clean-reset-execute");
  await execute.click();
  assert.equal(calls.length, 0, "execute before preview makes no request");
  await elements.get("clean-reset-preview").click();
  assert.equal(calls.length, 1, "preview performs exactly one read-only request");
  assert.equal(calls[0].url, "/api/settings/clean-reset/preview");
  assert.equal(calls.filter(call => call.url.endsWith("execute")).length, 0);
  assert.equal(execute.disabled, true, "unsafe preview keeps execution disabled");
  assert.match(elements.get("clean-reset-result").textContent, /UNKNOWN_SHEET/);

  await elements.get("clean-reset-preview").click();
  assert.equal(execute.disabled, false);
  assert.equal(elements.get("clean-reset-creators").textContent, 2453);

  await execute.click();
  assert.equal(calls.filter(call => call.url.endsWith("execute")).length, 0, "cancel does not reset");
  await execute.click();
  const executeCall = calls.find(call => call.url.endsWith("execute"));
  assert.equal(JSON.stringify(executeCall.payload), '{"confirm":true}');
  assert.match(elements.get("clean-reset-result").textContent, /本地业务数据已清空/);
  assert.equal(execute.disabled, true, "a fresh preview is required after execution");
  assert.equal(calls.filter(call => call.url.includes("feishu-sync")).length, 0);
  console.log("M7.1 clean reset and legacy migration retirement UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
