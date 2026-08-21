"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor() { this.value = ""; this.hidden = false; this.textContent = ""; this.children = []; this.dataset = {}; }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.children.push(item); return item; }
  replaceChildren(...items) { this.children = items; }
  addEventListener() {}
  querySelectorAll() { return []; }
}

const elements = new Map([
  "review-queue-actions", "review-results-body", "review-empty", "review-summary",
  "review-pagination", "review-view-analysis", "review-queue", "review-queue-progress",
  "review-queue-state", "review-queue-current", "creator-analysis-panel",
].map(id => [id, new Element()]));
const fields = [
  { dataset: { queueField: "达人名称" }, value: "Edited" },
  { dataset: { queueField: "rejection_reason" }, value: "not suitable" },
];
const calls = [];
let shouldFail = false;
const sandbox = {
  console,
  document: {
    createElement: () => new Element(),
    getElementById: id => elements.get(id) || null,
    querySelectorAll: selector => selector === "[data-queue-field]" ? fields : [],
  },
  window: {
    addEventListener: () => {},
    localStorage: { getItem: () => "", setItem: () => {} },
    alert: () => {},
    KOLConnectAPI: {
      get: async () => ({ records: [], platforms: [], platform_results: {}, review_total: 1, reviewed_count: 1, pending_count: 0 }),
      post: async (url, payload) => {
        calls.push({ url, payload });
        if (shouldFail) throw new Error("request failed");
        return { ok: true };
      },
    },
  },
};
sandbox.globalThis = sandbox;
const source = fs.readFileSync(path.join(__dirname, "..", "webapp", "app.js"), "utf8")
  + "\nglobalThis.__reviewTest = { state, pendingReviewRecords, submitReviewQueueAction };";
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: "app.js" });

(async () => {
  const api = sandbox.__reviewTest;
  api.state.review.taskId = "task_20260101T000000Z_deadbeef";
  api.state.review.records = [
    { account_uid: "pending", review_eligible: true, review_state: "pending" },
    { account_uid: "approved", review_eligible: true, review_state: "approved" },
    { account_uid: "failed", review_eligible: false, review_state: "pending" },
  ];
  assert.deepEqual(Array.from(api.pendingReviewRecords(), row => row.account_uid), ["pending"]);

  const pending = api.state.review.records[0];
  await api.submitReviewQueueAction("approve", pending);
  await api.submitReviewQueueAction("reject", pending);
  await api.submitReviewQueueAction("edit_approve", pending);
  assert.deepEqual(calls.map(call => call.url), [
    "/api/tasks/task_20260101T000000Z_deadbeef/results/review",
    "/api/tasks/task_20260101T000000Z_deadbeef/results/review",
    "/api/tasks/task_20260101T000000Z_deadbeef/results/review",
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.map(call => call.payload))), [
    { account_uid: "pending", action: "approve" },
    { account_uid: "pending", action: "reject", rejection_reason: "not suitable" },
    { account_uid: "pending", action: "edit_approve", fields: { "达人名称": "Edited" } },
  ]);

  api.state.review.records = [{ account_uid: "pending", review_eligible: true, review_state: "pending" }];
  shouldFail = true;
  await api.submitReviewQueueAction("approve", pending);
  assert.deepEqual(Array.from(api.pendingReviewRecords(), row => row.account_uid), ["pending"]);
  console.log("M4 D4 final review queue: OK");
})().catch(error => { console.error(error); process.exitCode = 1; });
