"use strict";

const assert = require("assert").strict;
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");

class FakeElement {
  constructor(id = "") {
    this.id = id;
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.dataset = {};
    this.children = [];
    this.listeners = new Map();
  }

  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = [...children]; }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
  removeEventListener(type) { this.listeners.delete(type); }
  async dispatch(type, extra = {}) {
    const listener = this.listeners.get(type);
    if (listener) return listener({ target: this, preventDefault() {}, ...extra });
    return undefined;
  }
}

function impact(overrides = {}) {
  return {
    ok: true,
    creator: { creator_id: "creator_1", display_name: "Creator One", is_archived: false },
    impact: {
      creators: 1,
      creator_accounts: 2,
      videos: 3,
      insights: 1,
      analysis_data: 1,
      creator_snapshots: 2,
      video_snapshots: { total: 4, direct: 4, indirect: 0 },
      campaign_creators: { total: 0, active: 0, archived: 0 },
      follow_up_logs: 0,
      task_artifacts: 0,
      data_protection: 0,
      legacy_sources: 0,
    },
    blockers: [],
    can_delete: true,
    preview_fingerprint: "f".repeat(64),
    ...overrides,
  };
}

function createEnvironment(api) {
  const ids = [
    "creator-delete-modal", "creator-delete-close", "creator-delete-cancel",
    "creator-delete-refresh", "creator-delete-confirm", "creator-delete-creator-name",
    "creator-delete-state", "creator-delete-impact-list", "creator-delete-blockers",
    "creator-delete-message",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));
  elements.get("creator-delete-modal").hidden = true;
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: () => new FakeElement(),
  };
  const registered = {};
  const sandbox = {
    window: null,
    document,
    console,
    AbortController,
    Option: class Option { constructor(text, value) { this.text = text; this.value = value; } },
    setTimeout,
    clearTimeout,
  };
  sandbox.window = sandbox;
  sandbox.KOLConnectPages = { registerPage(name, page) { registered[name] = page; } };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "webapp/pages/creator-library.js"), "utf8"),
    sandbox,
  );
  const controllers = [];
  const context = {
    api,
    state: { creatorLibrary: { records: [] } },
    resources: {
      signal: new AbortController().signal,
      createAbortController() {
        const controller = new AbortController();
        controllers.push(controller);
        return controller;
      },
      listen(target, type, listener) { target?.addEventListener(type, listener); },
    },
    ui: { saved: [], showSaved(message) { this.saved.push(message); } },
  };
  const modal = sandbox.KOLConnectCreatorDeleteModal.create(context);
  modal.bind();
  return { sandbox, elements, context, modal, registered };
}

async function testPreviewBeforeDeleteAndExactPayload() {
  const calls = [];
  const api = {
    async getCreatorDeleteImpact(creatorId) { calls.push(["GET", creatorId]); return impact(); },
    async deleteCreator(creatorId, payload) { calls.push(["DELETE", creatorId, payload]); return { ok: true }; },
  };
  const env = createEnvironment(api);
  let refreshed = 0;
  await env.modal.open(
    { creator_id: "creator_1", creator_name: "Creator One", archived_at: "" },
    { onDeleted: async () => { refreshed += 1; } },
  );
  assert.deepEqual(calls, [["GET", "creator_1"]]);
  assert.equal(env.elements.get("creator-delete-modal").hidden, false);
  assert.equal(env.elements.get("creator-delete-confirm").disabled, false);
  assert.equal(env.elements.get("creator-delete-impact-list").children.length > 5, true);

  await env.elements.get("creator-delete-confirm").dispatch("click");
  assert.deepEqual(JSON.parse(JSON.stringify(calls[1])), ["DELETE", "creator_1", {
    confirm: true,
    preview_fingerprint: "f".repeat(64),
  }]);
  assert.equal(refreshed, 1);
  assert.equal(env.elements.get("creator-delete-modal").hidden, true);
  assert.equal(env.context.ui.saved[0], "达人已永久删除。");
}

async function testBlockedPreviewDisablesConfirmation() {
  let deletes = 0;
  const env = createEnvironment({
    async getCreatorDeleteImpact() {
      return impact({
        can_delete: false,
        blockers: [{ code: "COOPERATION_RETENTION_ANONYMIZATION_GAP", message: "存在历史合作。" }],
      });
    },
    async deleteCreator() { deletes += 1; },
  });
  await env.modal.open({ creator_id: "creator_1", creator_name: "Creator One" });
  assert.equal(env.elements.get("creator-delete-confirm").disabled, true);
  assert.equal(env.elements.get("creator-delete-blockers").hidden, false);
  assert.match(env.elements.get("creator-delete-state").textContent, /无法永久删除/);
  await env.elements.get("creator-delete-confirm").dispatch("click");
  assert.equal(deletes, 0);
}

async function testDoubleSubmitAndStalePreviewNeverAutoRetryDelete() {
  let resolveDelete;
  let deleteCalls = 0;
  let impactCalls = 0;
  const env = createEnvironment({
    async getCreatorDeleteImpact() { impactCalls += 1; return impact(); },
    deleteCreator() {
      deleteCalls += 1;
      return new Promise(resolve => { resolveDelete = resolve; });
    },
  });
  await env.modal.open({ creator_id: "creator_1" });
  const first = env.elements.get("creator-delete-confirm").dispatch("click");
  const second = env.elements.get("creator-delete-confirm").dispatch("click");
  assert.equal(deleteCalls, 1);
  assert.equal(env.elements.get("creator-delete-confirm").disabled, true);
  resolveDelete({ ok: true });
  await Promise.all([first, second]);

  const stale = createEnvironment({
    async getCreatorDeleteImpact() { impactCalls += 1; return impact(); },
    async deleteCreator() {
      deleteCalls += 1;
      const error = new Error("DELETE_PREVIEW_STALE");
      error.responseData = { error: "DELETE_PREVIEW_STALE" };
      error.status = 409;
      throw error;
    },
  });
  await stale.modal.open({ creator_id: "creator_1" });
  const beforeDelete = deleteCalls;
  const beforeImpact = impactCalls;
  await stale.elements.get("creator-delete-confirm").dispatch("click");
  assert.equal(deleteCalls, beforeDelete + 1);
  assert.equal(impactCalls, beforeImpact + 1);
  assert.match(stale.elements.get("creator-delete-message").textContent, /重新确认/);
}

async function testNewBlockerRefreshesImpactAndLockTimeoutFailsClosed() {
  let impactCalls = 0;
  let deleteCalls = 0;
  const blocked = createEnvironment({
    async getCreatorDeleteImpact() {
      impactCalls += 1;
      return impactCalls === 1
        ? impact()
        : impact({
          can_delete: false,
          blockers: [{ code: "ACTIVE_CAMPAIGN_RELATION", message: "存在进行中的 Campaign。" }],
        });
    },
    async deleteCreator() {
      deleteCalls += 1;
      const error = new Error("DELETE_BLOCKED");
      error.responseData = { error: "DELETE_BLOCKED" };
      throw error;
    },
  });
  await blocked.modal.open({ creator_id: "creator_1" });
  await blocked.elements.get("creator-delete-confirm").dispatch("click");
  assert.equal(deleteCalls, 1);
  assert.equal(impactCalls, 2);
  assert.equal(blocked.elements.get("creator-delete-confirm").disabled, true);
  assert.match(blocked.elements.get("creator-delete-message").textContent, /安全阻止项/);

  const timeout = createEnvironment({
    async getCreatorDeleteImpact() { return impact(); },
    async deleteCreator() {
      const error = new Error("SHARED_STORAGE_LOCK_TIMEOUT");
      error.responseData = { error: "SHARED_STORAGE_LOCK_TIMEOUT" };
      throw error;
    },
  });
  await timeout.modal.open({ creator_id: "creator_1" });
  await timeout.elements.get("creator-delete-confirm").dispatch("click");
  assert.equal(timeout.elements.get("creator-delete-confirm").disabled, true);
  assert.match(timeout.elements.get("creator-delete-message").textContent, /其他操作修改/);
}

async function testApiClientUsesExactRoutesAndJsonDelete() {
  const calls = [];
  const sandbox = {
    window: null,
    fetch: async (url, init) => {
      calls.push({ url, init });
      return { ok: true, status: 200, async json() { return { ok: true }; } };
    },
    console,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "webapp/services/api-client.js"), "utf8"),
    sandbox,
  );
  await sandbox.KOLConnectAPI.getCreatorDeleteImpact("creator / 1");
  await sandbox.KOLConnectAPI.deleteCreator("creator / 1", {
    confirm: true,
    preview_fingerprint: "abc",
  });
  assert.equal(calls[0].url, "/api/creator-library/creator%20%2F%201/delete-impact");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[1].url, "/api/creator-library/creator%20%2F%201");
  assert.equal(calls[1].init.method, "DELETE");
  assert.equal(calls[1].init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    confirm: true,
    preview_fingerprint: "abc",
  });
}

async function testArchiveActionsRemainAndNoForceDeleteExists() {
  const source = fs.readFileSync(path.join(ROOT, "webapp/pages/creator-library.js"), "utf8");
  assert.match(source, /归档达人/);
  assert.match(source, /恢复达人/);
  assert.match(source, /actions\.appendChild\(createAction\("永久删除"/);
  assert.doesNotMatch(source, /force[ _-]?delete/i);
}

(async () => {
  await testPreviewBeforeDeleteAndExactPayload();
  await testBlockedPreviewDisablesConfirmation();
  await testDoubleSubmitAndStalePreviewNeverAutoRetryDelete();
  await testNewBlockerRefreshesImpactAndLockTimeoutFailsClosed();
  await testApiClientUsesExactRoutesAndJsonDelete();
  await testArchiveActionsRemainAndNoForceDeleteExists();
  console.log("M4.6 Creator hard delete UI: 6/6 PASS");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
