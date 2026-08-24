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
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
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
      remote_creators: 1967,
      tier_a_eligible: 1,
      already_correct: 0,
      tier_b_manual_review: 7,
      ambiguous: 2,
      unmatched: 6,
      conflicts: 0,
      blocked: 15,
    },
    candidates: [{
      remote_record_id: "remote-creator-1",
      creator_name: "<img src=x onerror=secretToken()>",
      creator_id: "creator-1",
      accounts: [{ platform: "TikTok", account_uid: "uid-1" }],
    }],
    blocked: [],
    ...overrides,
  };
}

async function run() {
  const html = read("webapp/index.html");
  const requiredIds = (
    "feishu-creator-backfill-card feishu-creator-backfill-preview "
    + "feishu-creator-backfill-execute feishu-creator-backfill-remote "
    + "feishu-creator-backfill-eligible feishu-creator-backfill-unchanged "
    + "feishu-creator-backfill-tier-b feishu-creator-backfill-residual "
    + "feishu-creator-backfill-conflicts feishu-creator-backfill-blocked "
    + "feishu-creator-backfill-result "
    + "feishu-creator-backfill-details feishu-creator-backfill-rows"
  ).split(" ");
  for (const id of requiredIds) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /历史飞书数据迁移/);
  assert.match(html, /不会创建或删除 Creator/);
  assert.match(html, /feishu-account-backfill-preview/);
  assert.match(html, /feishu-sync-dry-run/);

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
      status: "success",
      summary: {
        remote_creators: 1, tier_a_eligible: 0, already_correct: 0,
        tier_b_manual_review: 0, ambiguous: 1, unmatched: 0, conflicts: 1, blocked: 1,
      },
      candidates: [],
      blocked: [{
        remote_record_id: "remote-creator-1",
        remote_creator_id: "creator-other",
        reason: "CREATOR_ID_CONFLICT",
      }],
    }),
  ];
  const executeResults = [
    { ...preview(), status: "partial", succeeded: 1, failed: 1, remaining: 1 },
    { ...preview(), status: "success", succeeded: 1, failed: 0, remaining: 0 },
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

  assert.equal(calls.length, 0);
  assert.equal(elements.get("feishu-creator-backfill-execute").disabled, true);
  await elements.get("feishu-creator-backfill-preview").click();
  assert.equal(calls[0].url, "/api/feishu-sync/creator-backfill/dry-run");
  assert.equal(elements.get("feishu-creator-backfill-execute").disabled, false);
  assert.equal(elements.get("feishu-creator-backfill-eligible").textContent, "1");
  assert.equal(elements.get("feishu-creator-backfill-tier-b").textContent, "7");
  assert.equal(elements.get("feishu-creator-backfill-residual").textContent, "8");
  assert.match(elements.get("feishu-creator-backfill-rows").textContent, /TikTok/);
  assert.match(elements.get("feishu-creator-backfill-rows").textContent, /<img src=x/);
  assert.doesNotMatch(elements.get("feishu-creator-backfill-result").textContent, /secret|token/i);

  await elements.get("feishu-creator-backfill-execute").click();
  assert.equal(calls.filter(call => call.url.endsWith("execute")).length, 0);
  await elements.get("feishu-creator-backfill-execute").click();
  const executeCall = calls.find(call => call.url.endsWith("execute"));
  assert.equal(executeCall.payload.confirm, true);
  assert.deepEqual(Object.keys(executeCall.payload), ["confirm"]);
  assert.match(elements.get("feishu-creator-backfill-result").textContent, /部分成功/);

  await elements.get("feishu-creator-backfill-preview").click();
  await elements.get("feishu-creator-backfill-execute").click();
  assert.match(elements.get("feishu-creator-backfill-result").textContent, /重新运行预览/);

  await elements.get("feishu-creator-backfill-preview").click();
  assert.equal(elements.get("feishu-creator-backfill-execute").disabled, true);
  assert.match(elements.get("feishu-creator-backfill-rows").textContent, /Creator 身份冲突/);
  console.log("M7.1c Creator identity backfill UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
