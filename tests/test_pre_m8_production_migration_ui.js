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
    for (const listener of this.listeners.get("click") || []) await listener({ preventDefault() {} });
  }
}

async function run() {
  const html = read("webapp/index.html");
  const source = read("webapp/pages/settings.js");
  for (const id of [
    "storage-migration-card", "storage-migration-check", "storage-migration-prepare",
    "storage-migration-confirm", "storage-migration-cancel", "storage-migration-authority",
    "storage-migration-status", "storage-migration-backup", "storage-migration-result",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /storage-migration-confirm[^>]*disabled/);
  assert.doesNotMatch(source, /api\/assistant\/.*storage-migration|api\/feishu-chat\/.*storage-migration/);

  const ids = [
    "storage-migration-check", "storage-migration-prepare", "storage-migration-confirm",
    "storage-migration-cancel", "storage-migration-recover", "storage-migration-authority",
    "storage-migration-status", "storage-migration-backup", "storage-migration-id",
    "storage-migration-result", "clean-reset-execute", "browser-mode-exit-card",
    "creator-library-backup-workbook", "creator-library-workbook-path-hint",
  ];
  const elements = new Map(ids.map(id => [id, new Element(id)]));
  elements.get("storage-migration-confirm").disabled = true;
  elements.get("storage-migration-cancel").disabled = true;
  const calls = [];
  const confirmations = [false, true];
  const ready = {
    status: "ready_for_activation",
    authority: "legacy_excel",
    migration_id: "migration-safe",
    confirmation_token: "token-secret",
    backup: { filename: "Creator_Library.migration-safe.xlsx" },
    counts: { creators: 4, creator_accounts: 6, campaigns: 1 },
  };
  const window = {
    crypto: { randomUUID: () => "ui-session" },
    confirm: text => {
      assert.match(text, /原 Excel 会保留/);
      assert.match(text, /唯一运行数据源/);
      return confirmations.shift();
    },
    KOLConnectAPI: {
      get: async url => {
        calls.push({ method: "GET", url });
        if (url === "/api/feishu-chat/status") return { state: "disabled" };
        if (url.endsWith("/status")) return { status: "success", authority: "legacy_excel", migration_required: true, migration_status: "available" };
        throw new Error(`unexpected GET ${url}`);
      },
      post: async (url, payload) => {
        calls.push({ method: "POST", url, payload });
        if (url.endsWith("/prepare")) return ready;
        if (url.endsWith("/confirm")) return { status: "success", authority: "sqlite_active", migration_id: "migration-safe" };
        if (url.endsWith("/cancel")) return { status: "cancelled", authority: "legacy_excel" };
        throw new Error(`unexpected POST ${url}`);
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
  const sandbox = { AbortController, console, document, Math, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  window.KOLConnectPages = { registerPage: (_name, page) => { sandbox.page = page; } };
  vm.runInContext(source, sandbox);
  await sandbox.page.load();
  sandbox.page.bind();

  await elements.get("storage-migration-confirm").click();
  assert.equal(calls.filter(call => call.url.endsWith("/confirm")).length, 0, "confirm disabled before preparation");
  await elements.get("storage-migration-prepare").click();
  assert.equal(elements.get("storage-migration-confirm").disabled, false);
  assert.match(elements.get("storage-migration-result").textContent, /Creators 4/);

  await elements.get("storage-migration-confirm").click();
  assert.equal(calls.filter(call => call.url.endsWith("/confirm")).length, 0, "cancelled browser confirmation performs no activation");
  await elements.get("storage-migration-confirm").click();
  const confirmCall = calls.find(call => call.url.endsWith("/confirm"));
  assert.equal(confirmCall.payload.confirm, true);
  assert.equal(confirmCall.payload.migration_id, "migration-safe");
  assert.equal(confirmCall.payload.confirmation_token, "token-secret");
  assert.match(confirmCall.payload.session_id, /settings-ui-session/);
  assert.match(elements.get("storage-migration-result").textContent, /SQLite 已启用/);
  assert.equal(calls.filter(call => call.url.includes("feishu-sync/full-sync")).length, 0);
  assert.doesNotMatch(elements.get("storage-migration-result").textContent, /token-secret/);
  console.log("PRE-M8 production migration Settings UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
