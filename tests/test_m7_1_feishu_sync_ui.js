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
    for (const listener of this.listeners.get("click") || []) {
      await listener({ target: this, preventDefault() {} });
    }
  }
}

async function run() {
  const html = read("webapp/index.html");
  for (const id of (
    "feishu-sync-card feishu-sync-validate feishu-sync-dry-run feishu-sync-full "
    + "feishu-sync-local-creators feishu-sync-remote-creators feishu-sync-create "
    + "feishu-sync-update feishu-sync-conflicts feishu-sync-unmanaged feishu-sync-result"
  ).split(" ")) {
    assert.match(html, new RegExp(`id="${id}"`), `${id} must render`);
  }
  assert.match(html, /不会删除飞书记录/);
  assert.doesNotMatch(html, /自动同步到飞书/);

  const ids = [
    "feishu-sync-validate", "feishu-sync-dry-run", "feishu-sync-full",
    "feishu-sync-connection", "feishu-sync-local-creators", "feishu-sync-remote-creators",
    "feishu-sync-create", "feishu-sync-update", "feishu-sync-conflicts",
    "feishu-sync-unmanaged", "feishu-sync-result",
  ];
  const elements = new Map(ids.map(id => [id, new Element(id)]));
  const document = { getElementById: id => elements.get(id) || null };
  const calls = [];
  const confirmations = [false, true];
  const validationResults = [
    { status: "success", connection_ok: true },
    {
      status: "blocked", blocked_reason: "FEISHU_SCHEMA_INVALID",
      missing_fields: [
        { table: "creator", field: "KOLConnect Creator ID" },
        { table: "creator", field: "内容类型" },
        { table: "account", field: "最近同步时间" },
      ],
      incompatible_fields: [],
    },
    {
      status: "blocked", blocked_reason: "FEISHU_SCHEMA_INVALID",
      missing_fields: [],
      incompatible_fields: [
        { table: "account", field: "粉丝数", actual_type: 15 },
      ],
    },
    { status: "failed" },
  ];
  const window = {
    confirm: () => confirmations.shift(),
    KOLConnectAPI: {
      post: async (url, payload) => {
        calls.push({ url, payload });
        if (url.endsWith("validate")) return validationResults.shift();
        if (url.endsWith("dry-run")) return {
          status: "success", local_creator_count: 10, remote_creator_count: 8,
          creator_create_count: 2, creator_update_count: 1,
          creator_conflict_count: 0, remote_unmanaged_count: 3,
        };
        return {
          status: "partial", creator_created: 2, creator_updated: 1,
          account_created: 2, account_updated: 0, creator_failed: 0, account_failed: 1,
        };
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
  sandbox.window.KOLConnectPages = { registerPage: (_name, page) => { sandbox.page = page; } };
  vm.runInContext(read("webapp/pages/settings.js"), sandbox);
  await sandbox.page.load();
  sandbox.page.bind();

  await elements.get("feishu-sync-validate").click();
  assert.match(elements.get("feishu-sync-result").textContent, /连接与字段合同验证通过/);
  await elements.get("feishu-sync-validate").click();
  const missingMessage = elements.get("feishu-sync-result").textContent;
  assert.match(missingMessage, /飞书表结构需要补充/);
  assert.match(missingMessage, /Creator 表缺少：[\s\S]*KOLConnect Creator ID[\s\S]*内容类型/);
  assert.match(missingMessage, /Creator Account 表缺少：[\s\S]*最近同步时间/);
  assert.doesNotMatch(missingMessage, /secret|token/i);
  await elements.get("feishu-sync-validate").click();
  assert.match(elements.get("feishu-sync-result").textContent, /Creator Account 表字段类型不兼容:[\s\S]*粉丝数/);
  await elements.get("feishu-sync-validate").click();
  assert.equal(elements.get("feishu-sync-result").textContent, "操作未执行：FEISHU_SYNC_FAILED");
  await elements.get("feishu-sync-dry-run").click();
  assert.equal(elements.get("feishu-sync-local-creators").textContent, 10);
  assert.equal(elements.get("feishu-sync-create").textContent, 2);
  assert.match(elements.get("feishu-sync-result").textContent, /未写入飞书/);

  await elements.get("feishu-sync-full").click();
  assert.equal(calls.filter(call => call.url.endsWith("full-sync")).length, 0, "cancel must not sync");
  await elements.get("feishu-sync-full").click();
  const full = calls.find(call => call.url.endsWith("full-sync"));
  assert.equal(full.payload.confirm, true);
  assert.deepEqual(Object.keys(full.payload), ["confirm"]);
  assert.match(elements.get("feishu-sync-result").textContent, /同步部分完成/);
  assert.match(elements.get("feishu-sync-result").textContent, /后续批次已停止/);
  assert.doesNotMatch(elements.get("feishu-sync-result").textContent, /secret|token/i);
  console.log("M7.1 Feishu sync settings UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
