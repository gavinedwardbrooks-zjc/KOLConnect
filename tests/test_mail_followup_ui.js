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

assert.match(html, /data-page="mail-follow-up"[\s\S]*邮件跟进/);
assert.match(html, /pages\/mail-follow-up\.js/);
assert.match(registry, /"mail-follow-up": "mail"/);
assert.doesNotMatch(pageSource, /innerHTML/);

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

function harness({ groups, queue, prompt = () => "", postFailure = null }) {
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
  let readCount = 0;
  const window = {
    confirm: () => true,
    prompt,
    btoa: value => Buffer.from(value, "binary").toString("base64"),
    URL: { createObjectURL: () => "blob:test", revokeObjectURL() {} },
    KOLConnectPageResources: { create: () => ({ signal: undefined, cleanup() {}, listen(element, event, listener) { element.listeners.set(event, listener); } }) },
    KOLConnectApp: { showSaved: value => calls.saved.push(value), showError: error => calls.errors.push(String(error.message || error)) },
    KOLConnectAPI: {
      get: async url => {
        calls.gets.push(url);
        if (url === "/api/mail/follow-up") return { groups: groups[Math.min(readCount++, groups.length - 1)] };
        if (url === "/api/mail/follow-up/export-queue") return { groups: queue };
        throw new Error(`Unexpected GET ${url}`);
      },
      post: async (url, payload) => {
        calls.posts.push({ url, payload });
        if (postFailure) throw new Error(postFailure);
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
  synced_outbound_count: 0, partial_history: null, actionability: "normal", export_queue_added_at: null,
};
const beta = { ...alpha, correspondent_email: "b@example.com", waiting_for: "unknown", days_waiting: null, partial_history: true };

async function run() {
  const h = harness({ groups: [[alpha, beta], [{ ...alpha, creator_name: "Creator Updated" }]], queue: [beta] });
  await loadPage(h);
  assert.match(h.get("mail-followup-list").text, /Creator <script>Alpha<\/script>/);
  assert.match(h.get("mail-followup-list").text, /a@example.com/);
  assert.match(h.get("mail-followup-list").text, /待我回复/);
  assert.match(h.get("mail-followup-list").text, /状态未知/);
  assert.match(h.get("mail-followup-list").text, /2 天/);
  assert.match(h.get("mail-followup-list").text, /历史完整性未知/);
  assert.match(h.get("mail-followup-list").text, /部分历史/);

  await h.get("mail-followup-refresh").click();
  assert.equal(h.calls.gets.filter(url => url === "/api/mail/follow-up").length, 2);
  assert.match(h.get("mail-followup-list").text, /Creator Updated/);

  await h.get("mail-followup-show-export").click();
  assert.equal(h.get("mail-followup-export-panel").hidden, false);
  assert.match(h.get("mail-followup-export-list").text, /b@example.com/);

  const add = findAction(h.get("mail-followup-list"), "export_add");
  await clickAction(h.get("mail-followup-list"), add);
  assert.deepEqual(h.calls.posts.at(-1), { url: "/api/mail/follow-up/actions", payload: { creator_id: "creator-a", correspondent_email: "a@example.com", action: "export_add" } });

  const custom = findAction(h.get("mail-followup-list"), "snooze:custom");
  h.window.prompt = () => "not-a-date";
  const beforeInvalid = h.calls.posts.length;
  await clickAction(h.get("mail-followup-list"), custom);
  assert.equal(h.calls.posts.length, beforeInvalid, "invalid snooze must not persist");
  assert.match(h.calls.errors.at(-1), /提醒时间格式无效/);

  h.window.prompt = () => "2026-12-01T09:00:00Z";
  await clickAction(h.get("mail-followup-list"), custom);
  assert.deepEqual(h.calls.posts.at(-1), { url: "/api/mail/follow-up/actions", payload: {
    creator_id: "creator-a", correspondent_email: "a@example.com", action: "snooze", until: "2026-12-01T09:00:00.000Z",
  } });

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
  assert.deepEqual(persisted.calls.posts.at(-1).payload, { creator_id: "creator-a", correspondent_email: "b@example.com", action: "resume" });

  console.log("Mail Follow-up UI behavioral integration: OK");
}

run().catch(error => { console.error(error); process.exitCode = 1; });
