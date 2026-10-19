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
  const confirmations = [false, true, true];
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
    {
      status: "blocked", blocked_reason: "FEISHU_FIELD_FETCH_FAILED",
      missing_fields: [], incompatible_fields: [],
      error_codes: ["FEISHU_FIELD_FETCH_FAILED"],
    },
    {
      status: "failed", blocked_reason: "PERMISSION_DENIED",
      error_codes: ["PERMISSION_DENIED"],
      error_context: {
        operation: "creator_record_list", endpoint_category: "bitable_record_list",
        table_role: "creator", feishu_api_code: 1254302, failure_stage: "api", http_status: 200,
      },
    },
    { status: "failed" },
  ];
  let fullSyncCalls = 0;
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
        fullSyncCalls += 1;
        if (fullSyncCalls === 2) {
          return {
            status: "failed", blocked_reason: "PERMISSION_DENIED", error_codes: ["PERMISSION_DENIED"],
            error_context: {
              code: "PERMISSION_DENIED", operation: "creator_create",
              endpoint_category: "bitable_record_batch_create", table_role: "creator",
            },
          };
        }
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
      t: (key, values = {}) => ({
        settingsFeishuValidationPassed: "连接与字段合同验证通过。",
        settingsFeishuDryRunComplete: "Dry Run 已完成，未写入飞书。",
        settingsFeishuSyncComplete: "同步已完成。",
        settingsFeishuSyncPartial: "同步部分完成；后续批次已停止。",
        settingsFeishuSchemaNeedsReview: "飞书表结构需要补充或调整：",
        settingsFeishuMissingFields: `${values.table || ""} 表缺少：`,
        settingsFeishuIncompatibleFields: `${values.table || ""} 表字段类型不兼容:`,
        settingsFeishuCurrentType: `${values.field || ""}（当前类型：${values.type || ""}）`,
        settingsFeishuFieldFetchFailed: "飞书连接成功，但 KOLConnect 无法读取目标表的字段结构。系统已自动重试且未修改任何飞书数据。请稍后重试；如果问题持续存在，请查看诊断日志。",
        settingsFeishuReadPermissionDenied: "飞书拒绝了读取操作。请检查 bitable:app、版本发布和目标 Base/表读取权限。",
        settingsFeishuWritePermissionDenied: "飞书拒绝了写入操作。请检查 bitable:app、版本发布和目标 Base/表读写权限。",
        settingsFeishuOperationFailed: `操作未执行：${values.operation || "--"}`,
        settingsFeishuApiCode: `飞书错误码：${values.code || "--"}`,
        settingsFeishuOperationUnknown: "未识别的飞书操作",
        settingsFeishuOperationCreatorRecordList: "读取 Creator 记录",
        settingsFeishuOperationCreatorCreate: "创建 Creator 记录",
        settingsFeishuReviewDiagnostics: "请查看运行日志中的安全诊断信息。",
        settingsOperationNotRun: `操作未执行：${values.reason || "--"}`,
        settingsAvailable: "可用",
        settingsUnavailable: "不可用",
        settingsNeedsAttention: "需要处理",
        settingsConfigurationError: "配置错误",
        settingsUnknown: "未知",
      }[key] || key),
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
  assert.match(elements.get("feishu-sync-result").textContent, /无法读取目标表的字段结构/);
  assert.doesNotMatch(elements.get("feishu-sync-result").textContent, /表缺少/);
  await elements.get("feishu-sync-validate").click();
  assert.match(elements.get("feishu-sync-result").textContent, /拒绝了读取操作/);
  assert.match(elements.get("feishu-sync-result").textContent, /bitable:app/);
  assert.match(elements.get("feishu-sync-result").textContent, /读取 Creator 记录/);
  assert.match(elements.get("feishu-sync-result").textContent, /1254302/);
  assert.doesNotMatch(elements.get("feishu-sync-result").textContent, /secret|token/i);
  await elements.get("feishu-sync-validate").click();
  assert.match(elements.get("feishu-sync-result").textContent, /未识别的飞书操作/);
  assert.match(elements.get("feishu-sync-result").textContent, /安全诊断信息/);
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
  await elements.get("feishu-sync-full").click();
  assert.match(elements.get("feishu-sync-result").textContent, /拒绝了写入操作/);
  assert.match(elements.get("feishu-sync-result").textContent, /读写权限/);
  console.log("M7.1 Feishu sync settings UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
