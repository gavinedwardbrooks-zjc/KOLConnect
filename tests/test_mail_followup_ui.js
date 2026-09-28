"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const html = read("webapp/index.html");
const pageSource = read("webapp/pages/mail-follow-up.js");
const registry = read("webapp/core/page-registry.js");
const appSource = read("webapp/app.js");
const styles = read("webapp/styles.css");

assert.match(html, /data-page="mail-follow-up"[\s\S]*邮件跟进/);
assert.match(html, /pages\/mail-follow-up\.js/);
assert.equal((html.match(/id="mail-followup-google-sheets"/g) || []).length, 1, "Google sync must have one Mail-page entry point");
assert.doesNotMatch(pageSource, /mail-followup-sync/);
assert.doesNotMatch(pageSource, /\/api\/mail\/(inbox|sent)\/sync/);
assert.match(registry, /"mail-follow-up": "mail"/);
assert.doesNotMatch(pageSource, /innerHTML/);
assert.match(pageSource, /cell\.textContent = value/);
assert.doesNotMatch(pageSource, /user-select|webkit-user-select/);
assert.doesNotMatch(styles, /\.mail-followup-table[^}]*user-select\s*:\s*none/i);
assert.match(styles, /\.mail-followup-actions/);
assert.match(html, /id="mail-sync-crm-replies"[^>]*>同步回复状态到飞书表</);
assert.match(html, /data-page="mail"[\s\S]*id="mail-followup-google-sheets"[^>]*>同步邮件跟进到 Google Sheets</);
assert.match(html, /data-page="mail-follow-up"[\s\S]*id="mail-followup-refresh"[^>]*>刷新</);
assert.doesNotMatch(html, /同步回复状态到达人表/);
assert.match(appSource, /mail-sync-crm-replies[\s\S]*apiPost\("\/api\/mail\/inbox\/sync-crm-replies", \{\}\)/);
assert.match(appSource, /mail-followup-google-sheets[\s\S]*apiPost\("\/api\/mail\/follow-up\/sync-google-sheets", \{\}\)/);
assert.doesNotMatch(pageSource, /sync-google-sheets/);

class Element {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.listeners = new Map();
    this.classList = { toggle() {} };
  }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this.children = children; this.textContent = ""; }
  remove() {}
  click() { return this.listeners.get("click")?.({ target: this }); }
  closest(selector) { return selector === "[data-followup-action]" && this.dataset.followupAction ? this : null; }
  get text() { return `${this.textContent}${this.children.map(child => child.text).join("")}`; }
}

function findAction(element, action) {
  if (element.dataset.followupAction === action) return element;
  for (const child of element.children) {
    const found = findAction(child, action);
    if (found) return found;
  }
  return null;
}

async function clickAction(container, button) {
  container.listeners.get("click")({ target: { closest: () => button } });
  for (let turn = 0; turn < 3; turn += 1) await new Promise(resolve => setImmediate(resolve));
}

function harness({ groups, queue, prompt = () => "", postFailure = null, postGate = null }) {
  const elements = new Map();
  const filters = ["actionable", "all", "me", "creator", "unknown"].map(value => {
    const button = new Element();
    button.dataset.followupFilter = value;
    return button;
  });
  const document = {
    body: new Element(),
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement() { return new Element(); },
    querySelectorAll(selector) { return selector === "[data-followup-filter]" ? filters : []; },
  };
  const calls = { gets: [], posts: [], fetches: [], saved: [], errors: [] };
  const translations = {
    mailFollowupWaitingMe: "待我回复", mailFollowupWaitingCreator: "待对方回复", mailFollowupWaitingUnknown: "状态未知",
    mailFollowupHistoryPartial: "部分历史", mailFollowupHistoryUnknown: "历史范围未知", mailFollowupHistorySynced: "已同步范围内",
    mailFollowupDays: "{days} 天", mailFollowupResume: "恢复跟进", mailFollowupSnooze: "稍后处理 ▼", mailFollowupTomorrow: "明天再处理", mailFollowupThreeDays: "3 天后再处理", mailFollowupChooseDate: "选择日期…", mailFollowupClearSnooze: "取消稍后处理", mailFollowupStop: "停止跟进", mailFollowupExportAdd: "加入导出队列", mailFollowupExportRemove: "移出导出队列", unnamedCreator: "未命名达人", mailFollowupUnknownHelp: "当前邮件时间或联系人归属证据不足，暂时无法可靠判断由谁继续回复。", mailFollowupHistoryHelp: "当前同步的数据无法确认是否包含该联系人全部历史邮件，但不影响系统基于已同步邮件判断当前跟进状态。", mailFollowupUpdated: "邮件跟进状态已更新。",
  };
  let readCount = 0;
  const window = {
    confirm: () => true,
    prompt,
    btoa: value => Buffer.from(value, "binary").toString("base64"),
    URL: { createObjectURL: () => "blob:test", revokeObjectURL() {} },
    KOLConnectPageResources: { create: () => ({ signal: undefined, cleanup() {}, listen(element, event, listener) { element.listeners.set(event, listener); } }) },
    KOLConnectApp: {
      t(key, values) {
        return String(translations[key] || key).replace(/\{(\w+)\}/g, (_, name) => String(values?.[name] ?? ""));
      },
      showSaved: value => calls.saved.push(value), showError: error => calls.errors.push(String(error.message || error)),
    },
    KOLConnectAPI: {
      get: async url => {
        calls.gets.push(url);
        if (url === "/api/mail/follow-up") return { groups: groups[Math.min(readCount++, groups.length - 1)] };
        if (url === "/api/mail/follow-up/export-queue") return { groups: queue };
        throw new Error(`Unexpected GET ${url}`);
      },
      post: async (url, payload) => {
        calls.posts.push({ url, payload });
        if (postGate) await postGate;
        if (postFailure) throw (typeof postFailure === "string" ? new Error(postFailure) : postFailure);
        return { ok: true };
      },
    },
    fetch: async url => {
      calls.fetches.push(url);
      return { ok: true, blob: async () => new Blob(["csv"]), arrayBuffer: async () => new Uint8Array([1, 2]).buffer };
    },
    KOLConnectPages: { registerPage(name, page) { window.registered = { name, page }; } },
  };
  vm.runInNewContext(pageSource, { window, document, Blob, Buffer, Uint8Array, Number, Date, Error, console });
  return { window, calls, filters, get: id => document.getElementById(id) };
}

async function loadPage(harnessResult) {
  assert.equal(harnessResult.window.registered.name, "mail-follow-up");
  await harnessResult.window.registered.page.load();
  harnessResult.window.registered.page.bind();
}

const alpha = {
  creator_id: "creator-a", creator_name: "Creator <script>Alpha</script>", correspondent_email: "a@example.com",
  waiting_for: "me", days_waiting: 2, last_mail_at: "2026-09-20T10:00:00Z", synced_inbound_count: 1,
  synced_outbound_count: 0, partial_history: true, actionability: "normal", export_queue_added_at: null,
};
const beta = {
  ...alpha,
  creator_id: "creator_123",
  creator_name: "",
  correspondent_email: "b@example.com",
  waiting_for: "unknown",
  days_waiting: null,
  partial_history: null,
};

async function run() {
  const h = harness({ groups: [[alpha, beta], [{ ...alpha, creator_name: "Creator Updated" }]], queue: [beta] });
  await loadPage(h);
  assert.match(h.get("mail-followup-list").text, /Creator <script>Alpha<\/script>/);
  assert.match(h.get("mail-followup-list").text, /a@example.com/);
  assert.match(h.get("mail-followup-list").text, /待我回复/);
  assert.match(h.get("mail-followup-list").text, /状态未知/);
  assert.match(h.get("mail-followup-list").text, /2 天/);
  assert.match(h.get("mail-followup-list").text, /未命名达人/);
  assert.doesNotMatch(h.get("mail-followup-list").text, /creator_123/);
  assert.match(h.get("mail-followup-list").text, /历史范围未知/);
  assert.doesNotMatch(h.get("mail-followup-list").text, /历史完整性未知/);
  assert.match(h.get("mail-followup-list").text, /部分历史/);
  const unnamedRow = h.get("mail-followup-list").children[1];
  assert.match(unnamedRow.children[2].title, /无法可靠判断由谁继续回复/);
  assert.match(unnamedRow.children[7].title, /无法确认是否包含该联系人全部历史邮件/);

  await h.get("mail-followup-refresh").click();
  assert.equal(h.calls.gets.filter(url => url === "/api/mail/follow-up").length, 2);
  assert.match(h.get("mail-followup-list").text, /Creator Updated/);

  await h.get("mail-followup-show-export").click();
  assert.equal(h.get("mail-followup-export-panel").hidden, false);
  assert.match(h.get("mail-followup-export-list").text, /b@example.com/);

  const add = findAction(h.get("mail-followup-list"), "export_add");
  await clickAction(h.get("mail-followup-list"), add);
  assert.deepEqual(h.calls.posts.at(-1), { url: "/api/mail/follow-up/actions", payload: { creator_id: "creator-a", correspondent_email: "a@example.com", action: "export_add" } });

  assert.doesNotMatch(pageSource, /明天提醒|3 天后"|自定义提醒/);
  assert.match(pageSource, /mail-followup-defer-menu/);
  assert.match(pageSource, /mailFollowupSnooze|mailFollowupTomorrow|mailFollowupThreeDays|mailFollowupChooseDate|mailFollowupClearSnooze/);
  assert.doesNotMatch(pageSource, /followupSnoozeMenu/);
  await clickAction(h.get("mail-followup-list"), findAction(h.get("mail-followup-list"), "snooze:1"));
  assert.equal(h.calls.posts.at(-1).url, "/api/mail/follow-up/actions");
  assert.equal(h.calls.posts.at(-1).payload.action, "snooze");
  assert.ok(h.calls.posts.at(-1).payload.until, "snooze must retain its existing explicit until payload");

  await h.get("mail-followup-export-csv").click();
  await h.get("mail-followup-export-xlsx").click();
  assert.deepEqual(h.calls.fetches, ["/api/mail/follow-up/export?format=csv", "/api/mail/follow-up/export?format=xlsx"]);

  const failing = harness({ groups: [[alpha]], queue: [], postFailure: "persistence unavailable" });
  await loadPage(failing);
  const stop = findAction(failing.get("mail-followup-list"), "stop");
  await clickAction(failing.get("mail-followup-list"), stop);
  assert.deepEqual(failing.calls.posts[0].payload, { creator_id: "creator-a", correspondent_email: "a@example.com", action: "stop" });
  assert.match(failing.calls.errors.at(-1), /persistence unavailable/);

  const persisted = harness({ groups: [[
    { ...alpha, export_queue_added_at: "2026-09-20T00:00:00Z" },
    { ...beta, actionability: "stopped" },
  ]], queue: [] });
  await loadPage(persisted);
  await persisted.filters.find(button => button.dataset.followupFilter === "all").click();
  await clickAction(persisted.get("mail-followup-list"), findAction(persisted.get("mail-followup-list"), "export_remove"));
  assert.deepEqual(persisted.calls.posts.at(-1).payload, { creator_id: "creator-a", correspondent_email: "a@example.com", action: "export_remove" });
  await clickAction(persisted.get("mail-followup-list"), findAction(persisted.get("mail-followup-list"), "resume"));
  assert.deepEqual(persisted.calls.posts.at(-1).payload, { creator_id: "creator_123", correspondent_email: "b@example.com", action: "resume" });

  console.log("Mail Follow-up UI behavioral integration: OK");
}

run().catch(error => { console.error(error); process.exitCode = 1; });
