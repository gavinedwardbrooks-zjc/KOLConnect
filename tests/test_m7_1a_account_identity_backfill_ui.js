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
    this.dataset = {};
    this.children = [];
    this.hidden = false;
    this.disabled = false;
    this._textContent = "";
  }
  set textContent(value) {
    this._textContent = String(value ?? "");
    if (this._textContent === "") this.children = [];
  }
  get textContent() {
    return this.children.length
      ? this.children.map(child => child.textContent).join(" ")
      : this._textContent;
  }
  appendChild(child) { this.children.push(child); return child; }
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

function preview(overrides = {}) {
  return {
    status: "success",
    summary: {
      remote_accounts: 1, eligible: 1, unchanged: 0, unmatched: 0, conflicts: 0,
    },
    candidates: [{
      remote_record_id: "rec-1", account_uid: "uid-1", creator_id: "creator-1",
      platform: "TikTok", profile_url: "https://www.tiktok.com/@one", status: "UPDATE",
    }],
    blocked: [],
    ...overrides,
  };
}

async function run() {
  const html = read("webapp/index.html");
  const requiredIds = (
    "feishu-account-backfill-card feishu-account-backfill-preview "
    + "feishu-account-backfill-execute feishu-account-backfill-remote "
    + "feishu-account-backfill-eligible feishu-account-backfill-unchanged "
    + "feishu-account-backfill-unmatched feishu-account-backfill-conflicts "
    + "feishu-account-backfill-result feishu-account-backfill-details "
    + "feishu-account-backfill-rows"
  ).split(" ");
  for (const id of requiredIds) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /不会修改达人表/);

  const elements = new Map(requiredIds.map(id => [id, new Element(id)]));
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: tag => new Element(tag),
  };
  const calls = [];
  const confirmations = [false, true, true];
  const previewResults = [
    preview({ app_secret: "must-not-render", token: "must-not-render" }),
    preview(),
    preview({
      status: "blocked",
      summary: { remote_accounts: 1, eligible: 0, unchanged: 0, unmatched: 0, conflicts: 1 },
      candidates: [],
      blocked: [{
        remote_record_id: "rec-1", account_uid: "uid-1", creator_id: "creator-1",
        local_creator_id: "creator-1", remote_creator_id: "creator-other",
        platform: "TikTok", profile_url: "https://www.tiktok.com/@one",
        reason: "CREATOR_ID_CONFLICT",
      }],
    }),
    preview({
      summary: { remote_accounts: 1, eligible: 0, unchanged: 1, unmatched: 0, conflicts: 0 },
      candidates: [],
    }),
  ];
  const executeResults = [
    {
      ...preview(), status: "partial", attempted: 1, succeeded: 0, failed: 1,
      remaining: 1, error_codes: ["TRANSIENT_REMOTE_ERROR"],
    },
    {
      ...preview(), status: "success", attempted: 1, succeeded: 1, failed: 0,
      remaining: 0,
    },
  ];
  const window = {
    confirm: () => confirmations.shift(),
    KOLConnectAPI: {
      post: async (url, payload) => {
        calls.push({ url, payload });
        if (url.endsWith("dry-run")) return previewResults.shift();
        if (url.endsWith("execute")) return executeResults.shift();
        throw new Error(`Unexpected API call: ${url}`);
      },
    },
    KOLConnectApp: {
      loadSettingsState: async () => ({}),
      valueOf: () => "",
      checkedOf: () => false,
      showError: error => { throw error; },
    },
  };
  const sandbox = { AbortController, console, document, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  sandbox.window.KOLConnectPages = {
    registerPage: (_name, page) => { sandbox.page = page; },
  };
  vm.runInContext(read("webapp/pages/settings.js"), sandbox);
  await sandbox.page.load();
  sandbox.page.bind();

  assert.equal(calls.length, 0, "initial state must not request a backfill preview");
  assert.equal(elements.get("feishu-account-backfill-execute").disabled, true);
  await elements.get("feishu-account-backfill-preview").click();
  assert.equal(calls[0].url, "/api/feishu-sync/account-backfill/dry-run");
  assert.equal(elements.get("feishu-account-backfill-execute").disabled, false);
  assert.match(elements.get("feishu-account-backfill-result").textContent, /可安全认领 1/);
  assert.match(elements.get("feishu-account-backfill-rows").textContent, /TikTok/);
  assert.doesNotMatch(elements.get("feishu-account-backfill-result").textContent, /secret|token/i);

  await elements.get("feishu-account-backfill-execute").click();
  assert.equal(calls.filter(call => call.url.endsWith("execute")).length, 0, "cancel must not execute");
  await elements.get("feishu-account-backfill-execute").click();
  const firstExecute = calls.find(call => call.url.endsWith("execute"));
  assert.equal(firstExecute.payload.confirm, true);
  assert.deepEqual(Object.keys(firstExecute.payload), ["confirm"]);
  assert.match(elements.get("feishu-account-backfill-result").textContent, /部分成功/);

  await elements.get("feishu-account-backfill-preview").click();
  await elements.get("feishu-account-backfill-execute").click();
  assert.match(elements.get("feishu-account-backfill-result").textContent, /认领完成/);

  await elements.get("feishu-account-backfill-preview").click();
  assert.equal(elements.get("feishu-account-backfill-execute").disabled, true);
  assert.match(elements.get("feishu-account-backfill-result").textContent, /认领已阻塞/);
  assert.match(elements.get("feishu-account-backfill-rows").textContent, /身份冲突/);
  assert.match(elements.get("feishu-account-backfill-rows").textContent, /creator-other/);

  await elements.get("feishu-account-backfill-preview").click();
  assert.equal(elements.get("feishu-account-backfill-unchanged").textContent, "1");
  assert.equal(elements.get("feishu-account-backfill-execute").disabled, true);
  console.log("M7.1a Account identity backfill UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
