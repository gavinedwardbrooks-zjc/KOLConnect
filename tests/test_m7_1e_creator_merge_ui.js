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
    this.children = [];
    this.dataset = {};
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
  }
  addEventListener(type, listener) {
    this.listeners.set(type, [...(this.listeners.get(type) || []), listener]);
  }
  removeEventListener() {}
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  focus() {}
  async trigger(type) {
    if (this.disabled && type === "click") return;
    for (const listener of this.listeners.get(type) || []) await listener({ target: this });
  }
}

async function flush() {
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
}

async function run() {
  const html = read("webapp/index.html");
  const library = read("webapp/pages/creator-library.js");
  const source = read("webapp/pages/creator-merge.js");
  assert.match(library, /createAction\("合并达人", "merge"/);
  for (const id of [
    "creator-merge-modal", "creator-merge-primary-name", "creator-merge-secondary-name",
    "creator-merge-search", "creator-merge-search-results", "creator-merge-preview",
    "creator-merge-confirm", "creator-merge-conflicts",
    "creator-merge-result-creators", "creator-merge-result-accounts", "creator-merge-result-platforms",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /主达人 · 保留/);
  assert.match(html, /待合并达人 · 合并后删除/);
  assert.doesNotMatch(source, /innerHTML/);

  const ids = [
    "creator-merge-modal", "creator-merge-primary-name", "creator-merge-primary-accounts",
    "creator-merge-secondary-name", "creator-merge-secondary-accounts", "creator-merge-search",
    "creator-merge-search-results", "creator-merge-count-accounts", "creator-merge-count-videos",
    "creator-merge-result-creators", "creator-merge-result-accounts", "creator-merge-result-platforms",
    "creator-merge-count-snapshots", "creator-merge-count-campaigns", "creator-merge-conflicts",
    "creator-merge-message", "creator-merge-preview", "creator-merge-confirm", "creator-merge-close",
    "creator-merge-cancel",
  ];
  const elements = new Map(ids.map(id => [id, new Element(id)]));
  const calls = [];
  const confirmations = [false, true];
  let merged = 0;
  const api = {
    get: async url => {
      calls.push({ method: "GET", url });
      if (url.startsWith("/api/creator-library?")) return {
        creators: [{ creator_id: "secondary", creator_name: "Remote <unsafe>", platform: "TikTok", profile_url: "https://tiktok.com/@secondary" }],
      };
      if (url.endsWith("/primary")) return { record: { creator_id: "primary", creator_name: "Primary" }, accounts: [{ platform: "YouTube", username: "primary" }] };
      if (url.endsWith("/secondary")) return { record: { creator_id: "secondary", creator_name: "Remote <unsafe>" }, accounts: [{ platform: "TikTok", username: "secondary" }] };
      throw new Error(`unexpected GET ${url}`);
    },
    post: async (url, payload) => {
      calls.push({ method: "POST", url, payload });
      if (url.endsWith("/preview")) return {
        safe_to_merge: true,
        preview_fingerprint: "fingerprint",
        primary: { creator_id: "primary", account_count: 1, accounts: [{ platform: "YouTube" }] },
        secondary: { creator_id: "secondary", account_count: 1, accounts: [{ platform: "TikTok" }] },
        migration_summary: { accounts: 1, videos: 2, creator_snapshots: 3, video_snapshots: 4, campaign_creators: 5 },
        conflicts: [],
      };
      if (url.endsWith("/execute")) return { merged: true, migrated: { CreatorAccounts: 1 } };
      throw new Error(`unexpected POST ${url}`);
    },
  };
  const resources = {
    signal: {},
    listen: (element, type, listener) => element?.addEventListener(type, listener),
    setTimeout: callback => { callback(); return 1; },
  };
  const window = {
    confirm: message => {
      assert.match(message, /将【Remote <unsafe>】合并到【Primary】/);
      return confirmations.shift();
    },
  };
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: () => new Element(),
  };
  const sandbox = { console, document, window, setTimeout };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);

  const modal = window.KOLConnectCreatorMergeModal.create({
    api, resources, state: {},
    ui: { showError: error => { throw error; }, showSaved: () => {} },
  });
  modal.bind();
  await modal.open({ creator_id: "primary", creator_name: "Primary" }, { onMerged: async () => { merged += 1; } });
  assert.equal(elements.get("creator-merge-confirm").disabled, true, "preview is mandatory");

  elements.get("creator-merge-search").value = "secondary";
  await elements.get("creator-merge-search").trigger("input");
  await flush();
  const searchResult = elements.get("creator-merge-search-results").children[0];
  assert.ok(searchResult, "secondary search renders a result");
  assert.equal(searchResult.children[0].children[0].textContent, "Remote <unsafe>");
  await searchResult.trigger("click");
  await elements.get("creator-merge-preview").trigger("click");
  await flush();
  assert.equal(elements.get("creator-merge-confirm").disabled, false, "safe preview enables merge");
  assert.equal(elements.get("creator-merge-result-creators").textContent, "2 → 1");
  assert.equal(elements.get("creator-merge-result-accounts").textContent, "2 → 2");
  assert.match(elements.get("creator-merge-result-platforms").textContent, /YouTube/);
  assert.match(elements.get("creator-merge-result-platforms").textContent, /TikTok/);
  assert.equal(elements.get("creator-merge-conflicts").hidden, true, "safe preview has no conflicts");
  assert.equal(calls.filter(call => call.url.endsWith("/execute")).length, 0, "preview never executes");

  await elements.get("creator-merge-confirm").trigger("click");
  assert.equal(calls.filter(call => call.url.endsWith("/execute")).length, 0, "cancel causes zero execute requests");
  await elements.get("creator-merge-confirm").trigger("click");
  await flush();
  const execute = calls.find(call => call.url.endsWith("/execute"));
  assert.equal(execute.payload.confirm, true);
  assert.equal(execute.payload.preview_fingerprint, "fingerprint");
  assert.equal(merged, 1, "success refresh callback runs once");
  assert.equal(calls.filter(call => /feishu|full-sync/i.test(call.url)).length, 0, "merge never starts Full Sync");
  console.log("M7.1e manual Creator merge UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
