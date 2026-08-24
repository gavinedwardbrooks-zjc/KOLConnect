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

function safePreview(overrides = {}) {
  const targets = [{
    remote_record_id: "rec1234567890abcdef",
    display_name: "<img src=x onerror=secretToken()>",
    legacy_id: "legacy-1",
    relation_status: "NO_RELATION",
    delete_eligible: true,
    email: "must-not-render@example.com",
    notes: "must-not-render",
  }];
  return {
    status: "success",
    summary: {
      remote_creators: 1967,
      managed_remote_creators: 1951,
      unmanaged_remote_creators: 1,
      identity_conflicts: 0,
    },
    targets,
    gates: { G1: true, G2: true, G3: true, G4: true },
    app_secret: "must-not-render",
    token: "must-not-render",
    ...overrides,
  };
}

async function run() {
  const html = read("webapp/index.html");
  const requiredIds = (
    "feishu-legacy-creator-cleanup-card feishu-legacy-creator-cleanup-preview "
    + "feishu-legacy-creator-cleanup-execute feishu-legacy-creator-cleanup-remote "
    + "feishu-legacy-creator-cleanup-managed feishu-legacy-creator-cleanup-unmanaged "
    + "feishu-legacy-creator-cleanup-eligible feishu-legacy-creator-cleanup-relation-risk "
    + "feishu-legacy-creator-cleanup-ambiguous feishu-legacy-creator-cleanup-blocked "
    + "feishu-legacy-creator-cleanup-conflicts feishu-legacy-creator-cleanup-result "
    + "feishu-legacy-creator-cleanup-details feishu-legacy-creator-cleanup-rows"
  ).split(" ");
  for (const id of requiredIds) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /正常新用户无需使用/);
  assert.match(html, /feishu-legacy-creator-cleanup-execute[^>]*disabled/);

  const elements = new Map(requiredIds.map(id => [id, new Element(id)]));
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: tag => new Element(tag),
  };
  const calls = [];
  const confirmations = [false, true, true, true, true];
  const responses = [
    safePreview(),
    safePreview({
      status: "success",
      blocked_reason: "CLEANUP_BLOCKED_RELATION_RISK",
      targets: [{
        remote_record_id: "unsafe",
        relation_status: "AMBIGUOUS_RELATION",
        delete_eligible: false,
      }],
      gates: { G1: true, G9: false },
    }),
    safePreview(),
    { status: "partial", attempted: 1, succeeded: 0, failed: 1, remaining: 1 },
    safePreview(),
    { status: "blocked", blocked_reason: "CLEANUP_TARGET_SET_CHANGED" },
    safePreview(),
    { status: "failed", error_codes: ["TRANSIENT_NETWORK_ERROR"] },
    safePreview(),
    { status: "success", attempted: 1, succeeded: 1, failed: 0, remaining: 0 },
  ];
  const window = {
    confirm: () => confirmations.shift(),
    KOLConnectAPI: {
      post: async (url, payload) => {
        calls.push({ url, payload });
        if (url.includes("full-sync")) throw new Error("Full Sync must never run");
        return responses.shift();
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

  const preview = elements.get("feishu-legacy-creator-cleanup-preview");
  const execute = elements.get("feishu-legacy-creator-cleanup-execute");
  assert.equal(execute.disabled, true, "execute starts disabled");
  await execute.click();
  assert.equal(calls.length, 0, "execute before preview makes no request");

  await preview.click();
  assert.equal(calls[0].url, "/api/feishu-sync/legacy-creator-cleanup/preview");
  assert.equal(JSON.stringify(calls[0].payload), "{}");
  assert.equal(calls.filter(call => call.url.endsWith("execute")).length, 0, "preview does not delete");
  assert.equal(execute.disabled, false, "safe gates enable execute");
  assert.equal(elements.get("feishu-legacy-creator-cleanup-remote").textContent, "1967");
  assert.equal(elements.get("feishu-legacy-creator-cleanup-managed").textContent, "1951");
  assert.match(elements.get("feishu-legacy-creator-cleanup-rows").textContent, /<img src=x/);
  assert.doesNotMatch(elements.get("feishu-legacy-creator-cleanup-rows").textContent, /email|must-not-render/i);
  assert.doesNotMatch(elements.get("feishu-legacy-creator-cleanup-result").textContent, /secret|token/i);

  await execute.click();
  assert.equal(calls.filter(call => call.url.endsWith("execute")).length, 0, "cancel makes no request");

  await preview.click();
  assert.equal(execute.disabled, true, "unsafe preview keeps execute disabled");
  assert.match(elements.get("feishu-legacy-creator-cleanup-result").textContent, /未通过全部安全门槛/);

  await preview.click();
  await execute.click();
  const partialCall = calls.find(call => call.url.endsWith("execute"));
  assert.equal(JSON.stringify(partialCall.payload), '{"confirm":true}');
  assert.deepEqual(Object.keys(partialCall.payload), ["confirm"]);
  assert.match(elements.get("feishu-legacy-creator-cleanup-result").textContent, /清理部分完成/);
  assert.equal(execute.disabled, true, "execute requires a fresh preview after any attempt");

  await preview.click();
  await execute.click();
  assert.match(elements.get("feishu-legacy-creator-cleanup-result").textContent, /清理已阻塞/);

  await preview.click();
  await execute.click();
  assert.match(elements.get("feishu-legacy-creator-cleanup-result").textContent, /清理失败/);

  await preview.click();
  await execute.click();
  assert.match(elements.get("feishu-legacy-creator-cleanup-result").textContent, /清理完成/);
  assert.match(elements.get("feishu-legacy-creator-cleanup-result").textContent, /验证连接/);
  assert.match(elements.get("feishu-legacy-creator-cleanup-result").textContent, /M7\.1 Dry Run/);
  assert.equal(calls.filter(call => call.url.includes("full-sync")).length, 0);
  console.log("M7.1d Legacy Creator cleanup Settings UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
