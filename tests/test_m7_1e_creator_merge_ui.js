"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");

class Element {
  constructor(id = "", tagName = "div") {
    this.id = id;
    this.tagName = tagName.toUpperCase();
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
  append(...children) { children.forEach(child => this.appendChild(child)); }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  focus() {}
  async trigger(type, event = {}) {
    if (this.disabled && type === "click") return;
    const payload = { target: event.target || this, ...event };
    let node = this;
    do {
      for (const listener of node.listeners.get(type) || []) await listener(payload);
      node = node.parentNode;
    } while (node && payload.bubbles !== false);
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
  assert.match(library, /createAction\(t\("creatorLibraryMergeCreator"\), "merge"/);
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
      if (url.startsWith("/api/creator-library?")) {
        if (url.includes("search=other")) return {
          creators: [{ creator_id: "other", creator_name: "Same display name", platform: "Instagram", profile_url: "https://instagram.com/other" }],
        };
        return {
          creators: [{ creator_id: "secondary", creator_name: "Same display name", platform: "TikTok", profile_url: "https://tiktok.com/@secondary" }],
        };
      }
      if (url.endsWith("/primary")) return { record: { creator_id: "primary", creator_name: "Primary" }, accounts: [{ platform: "YouTube", username: "primary" }] };
      if (url.endsWith("/secondary") || url.endsWith("/other")) throw new Error("candidate selection must not depend on a detail fetch");
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
      assert.match(message, /将【Same display name】合并到【Primary】/);
      return confirmations.shift();
    },
  };
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: tagName => new Element("", tagName),
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
  let searchResult = elements.get("creator-merge-search-results").children[0];
  assert.ok(searchResult, "secondary search renders a result");
  assert.equal(searchResult.type, "button");
  assert.equal(searchResult.dataset.creatorMergeCandidateId, "secondary");
  assert.equal(searchResult.children[0].children[0].textContent, "Same display name");
  await searchResult.children[1].trigger("click");
  assert.equal(elements.get("creator-merge-secondary-name").textContent, "Same display name", "visible choose action updates SECONDARY immediately");
  assert.equal(elements.get("creator-merge-secondary-accounts").textContent, "TikTok", "candidate platform summary remains visible");
  assert.equal(elements.get("creator-merge-preview").disabled, false, "selection enables preview without a detail request");

  elements.get("creator-merge-search").value = "other";
  await elements.get("creator-merge-search").trigger("input");
  await flush();
  searchResult = elements.get("creator-merge-search-results").children[0];
  assert.equal(searchResult.dataset.creatorMergeCandidateId, "other");
  await searchResult.children[1].trigger("click");
  assert.equal(elements.get("creator-merge-secondary-accounts").textContent, "Instagram", "selection remains bound to the rerendered candidate ID");

  elements.get("creator-merge-search").value = "secondary";
  await elements.get("creator-merge-search").trigger("input");
  await flush();
  searchResult = elements.get("creator-merge-search-results").children[0];
  await searchResult.children[1].trigger("click");
  await elements.get("creator-merge-preview").trigger("click");
  await flush();
  const previewCall = calls.find(call => call.url.endsWith("/preview"));
  assert.equal(previewCall.payload.secondary_creator_id, "secondary", "preview uses the explicit stable Creator ID, not display text");
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
  assert.equal(execute.payload.secondary_creator_id, "secondary");
  assert.equal(merged, 1, "success refresh callback runs once");
  assert.equal(calls.filter(call => /feishu|full-sync/i.test(call.url)).length, 0, "merge never starts Full Sync");
  console.log("M7.1e manual Creator merge UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
