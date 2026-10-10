import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const originalChrome = globalThis.chrome;
const originalFetch = globalThis.fetch;
globalThis.chrome = { storage: { local: { get: async () => ({}) } } };
const api = await import("../chrome_extension/services/local_api.js");
const requests = [];
globalThis.fetch = async (url, options = {}) => {
  requests.push({ url: String(url), options });
  if (!options.method || options.method === "GET") return {
    ok: true, status: 200,
    json: async () => ({ ok: true, page: 1, pages: 2, creators: [
      { creator_id: "creator_a", creator_name: "Same Name", account_count: 2 },
      { creator_id: "creator_b", creator_name: "Same Name", account_count: 1 }
    ] })
  };
  return { ok: true, status: 200, json: async () => ({
    ok: true, action: "LINK_EXISTING_CREATOR", changed: false,
    creator_id: "creator_b", account_uid: "uid_b"
  }) };
};
const page = await api.searchCreators("Same", 1);
assert.equal(page.creators.length, 2);
assert.notEqual(page.creators[0].creator_id, page.creators[1].creator_id);
assert.equal(new URL(requests[0].url).pathname, "/api/creator-library");
assert.equal(new URL(requests[0].url).searchParams.get("search"), "Same");
assert.equal(new URL(requests[0].url).searchParams.get("page_size"), "12");
assert.equal(page.pages, 2);
await api.linkExistingCreator("creator_b", "Instagram", "https://www.instagram.com/gate3c/");
assert.equal(new URL(requests[1].url).pathname, "/api/extension/accounts/link-existing-creator");
const body = JSON.parse(requests[1].options.body);
assert.deepEqual(body, {
  action: "LINK_EXISTING_CREATOR", creator_id: "creator_b",
  platform: "Instagram", profile_url: "https://www.instagram.com/gate3c/"
});
assert.equal(Object.hasOwn(body, "creator_name"), false);

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.hidden = false;
    this.listeners = {};
    this.classList = { toggle() {} };
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setPointerCapture() {}
  getBoundingClientRect() { return { left: 100, top: 100 }; }
  select() {}
  remove() {}
}
class FakeButtonElement extends FakeElement {}
function find(node, className) {
  if (node?.className === className) return node;
  for (const child of node?.children || []) {
    const result = find(child, className);
    if (result) return result;
  }
  return null;
}
function assistantHarness(responder) {
  const documentElement = new FakeElement("html");
  const document = {
    documentElement, body: new FakeElement("body"),
    getElementById: (id) => documentElement.children.find((node) => node.id === id) || null,
    createElement: (tag) => tag === "button" ? new FakeButtonElement(tag) : new FakeElement(tag),
    execCommand: () => true
  };
  const sent = [];
  const location = { href: "https://www.instagram.com/gate3c/" };
  const context = vm.createContext({
    document, location, navigator: { clipboard: { writeText: async () => {} } },
    chrome: { runtime: {
      lastError: null,
      sendMessage(message, callback) { sent.push(message); responder(message, callback); },
      onMessage: { addListener() {} }
    } },
    HTMLButtonElement: FakeButtonElement, URL, Intl, Set,
    innerWidth: 1440, innerHeight: 900,
    setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1,
    addEventListener() {}, console
  });
  context.window = context;
  for (const relative of [
    "config.js", "core/analysis_session.js", "core/page_support.js", "content/floating_assistant.js"
  ]) {
    vm.runInContext(readFileSync(new URL(`../chrome_extension/${relative}`, import.meta.url), "utf8"), context);
  }
  const assistant = context.__KOLCONNECT_NEXT_ASSISTANT__;
  const profile = {
    platform: "Instagram", profile_url: location.href, username: "gate3c",
    fields: { username: { value: "gate3c" }, creator_name: { value: "Browser Name" } }
  };
  assistant.state.profile = profile;
  assistant.state.accountLookup = { state: "ACCOUNT_NOT_FOUND" };
  assistant.initializePreview(profile);
  return { assistant, sent, location, find: (name) => find(assistant.root, name) };
}

let lookupCount = 0;
const harness = assistantHarness((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_SEARCH_CREATORS") return callback({ ok: true, result: {
    page: message.page, pages: 2,
    creators: message.page === 1 ? [
      { creator_id: "creator_a", creator_name: "Same Name", account_count: 2 },
      { creator_id: "creator_b", creator_name: "Same Name", account_count: 1 }
    ] : [{ creator_id: "creator_c", creator_name: "Other Name", account_count: 0 }]
  } });
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    lookupCount++;
    return callback({ ok: true, lookup: { state: lookupCount === 1 ? "ACCOUNT_NOT_FOUND" : "ACCOUNT_EXISTS",
      creator: { display_name: "Same Name" }, linked_accounts: [] } });
  }
  if (message.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR") return callback({
    ok: true, session_id: message.session_id, identity: message.identity,
    result: { changed: false, action: "LINK_EXISTING_CREATOR", creator_id: message.creator_id, account_uid: "uid_b" }
  });
  callback({ ok: true });
});
const state = harness.assistant.state;
assert.equal(harness.find("kol-primary").textContent, "添加到 KOLConnect");
assert.equal(harness.find("kol-creator-selector").hidden, true);
assert.equal(harness.find("kol-actions").children.at(-1).textContent, "关联已有 Creator");
harness.assistant.openCreatorSelector();
assert.equal(harness.find("kol-creator-selector").hidden, false);
assert.equal(state.selectedCreatorId, "");
assert.equal(harness.sent.some((item) => item.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR"), false);
assert.equal(harness.find("kol-link-confirm").disabled, true);
const searchInput = harness.find("kol-creator-selector").children.find((item) => item.tagName === "INPUT");
searchInput.value = "Same";
await harness.assistant.searchCreatorLibrary(1);
assert.equal(harness.sent.at(-1).query, "Same");
assert.equal(harness.find("kol-creator-results").children.length, 2);
assert.equal(harness.find("kol-creator-results").children[0].textContent.includes("Same Name"), true);
assert.equal(harness.find("kol-link-confirm").disabled, true);
await harness.assistant.searchCreatorLibrary(2);
assert.equal(harness.find("kol-creator-results").children.length, 3);
harness.find("kol-creator-results").children[1].listeners.click();
assert.equal(state.selectedCreatorId, "creator_b");
assert.equal(harness.find("kol-link-confirm").disabled, false);
await harness.assistant.linkSelectedCreator();
assert.equal(harness.sent.filter((item) => item.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR").length, 1);
assert.equal(harness.sent.find((item) => item.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR").creator_id, "creator_b");
assert.equal(state.accountLookup.state, "ACCOUNT_EXISTS");
assert.equal(state.selectedCreatorId, "");
assert.equal(harness.find("kol-actions").children.at(-1).hidden, true);
assert.equal(harness.find("kol-primary").textContent, "更新账号");
assert.equal(lookupCount, 2);

const stale = assistantHarness((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_SEARCH_CREATORS") return callback({ ok: true, result: {
    page: 1, pages: 1, creators: [{ creator_id: "creator_a", creator_name: "Same Name" }]
  } });
  callback({ ok: true });
});
stale.assistant.openCreatorSelector();
await stale.assistant.searchCreatorLibrary(1);
stale.find("kol-creator-results").children[0].listeners.click();
stale.location.href = "https://www.instagram.com/other/";
stale.assistant.handleUrlChange(stale.location.href);
await stale.assistant.linkSelectedCreator();
assert.equal(stale.assistant.state.selectedCreatorId, "");
assert.equal(stale.sent.some((item) => item.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR"), false);

const existing = assistantHarness((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  callback({ ok: true });
});
existing.assistant.state.accountLookup = { state: "ACCOUNT_EXISTS" };
existing.assistant.initializePreview(existing.assistant.state.profile);
assert.equal(existing.find("kol-primary").textContent, "更新账号");
assert.equal(existing.find("kol-actions").children.at(-1).hidden, true);
existing.assistant.openCreatorSelector();
assert.equal(existing.assistant.state.creatorSelectorOpen, false);

const searchOffline = assistantHarness((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_SEARCH_CREATORS") return callback({ ok: false, code: "APP_OFFLINE" });
  callback({ ok: true });
});
searchOffline.assistant.openCreatorSelector();
await searchOffline.assistant.searchCreatorLibrary(1);
assert.match(searchOffline.assistant.state.creatorSearchError, /暂不可用/);
assert.equal(searchOffline.find("kol-link-confirm").disabled, true);
assert.equal(searchOffline.find("kol-primary").textContent, "添加到 KOLConnect");
assert.equal(searchOffline.sent.some((item) => item.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR"), false);

let delayedLinkCallback;
let delayedLookupCount = 0;
const race = assistantHarness((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_SEARCH_CREATORS") return callback({ ok: true, result: {
    page: 1, pages: 1, creators: [{ creator_id: "creator_a", creator_name: "Browser Name" }]
  } });
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    delayedLookupCount++;
    return callback({ ok: true, lookup: { state: delayedLookupCount === 1 ? "ACCOUNT_NOT_FOUND" : "ACCOUNT_EXISTS" } });
  }
  if (message.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR") {
    delayedLinkCallback = () => callback({
      ok: true, session_id: message.session_id, identity: message.identity,
      result: { changed: true, action: "LINK_EXISTING_CREATOR", creator_id: message.creator_id, account_uid: "uid_a" }
    });
    return;
  }
  callback({ ok: true });
});
race.assistant.openCreatorSelector();
await race.assistant.searchCreatorLibrary(1);
assert.equal(race.assistant.state.selectedCreatorId, "");
race.find("kol-creator-results").children[0].listeners.click();
const pending = race.assistant.linkSelectedCreator();
await new Promise((resolve) => setImmediate(resolve));
assert.equal(typeof delayedLinkCallback, "function");
assert.equal(race.assistant.state.mutationPending, true);
await race.assistant.linkSelectedCreator();
await race.assistant.mutateCurrent();
assert.equal(race.sent.filter((item) => item.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR").length, 1);
assert.equal(race.sent.some((item) => item.type === "KOLCONNECT_NEXT_ADD_ACCOUNT"), false);
delayedLinkCallback();
await pending;
assert.equal(race.assistant.state.accountLookup.state, "ACCOUNT_EXISTS");
assert.equal(race.assistant.state.mutationPending, false);

let conflictLookupCount = 0;
const conflict = assistantHarness((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_SEARCH_CREATORS") return callback({ ok: true, result: {
    page: 1, pages: 1, creators: [{ creator_id: "creator_a", creator_name: "Browser Name" }]
  } });
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    conflictLookupCount++;
    return callback({ ok: true, lookup: { state: conflictLookupCount === 1 ? "ACCOUNT_NOT_FOUND" : "ACCOUNT_EXISTS" } });
  }
  if (message.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR") {
    return callback({ ok: false, code: "ACCOUNT_OWNED_BY_OTHER_CREATOR" });
  }
  callback({ ok: true });
});
conflict.assistant.openCreatorSelector();
await conflict.assistant.searchCreatorLibrary(1);
conflict.find("kol-creator-results").children[0].listeners.click();
await conflict.assistant.linkSelectedCreator();
assert.equal(conflict.assistant.state.creatorSelectorOpen, false);
assert.equal(conflict.assistant.state.accountLookup.state, "ACCOUNT_EXISTS");
assert.equal(conflict.sent.filter((item) => item.type === "KOLCONNECT_NEXT_LINK_EXISTING_CREATOR").length, 1);
assert.equal(conflict.sent.some((item) => /RELINK/.test(item.type)), false);

const cancelled = assistantHarness((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  callback({ ok: true });
});
cancelled.assistant.openCreatorSelector();
cancelled.assistant.close();
assert.equal(cancelled.assistant.state.creatorSelectorOpen, false);
assert.equal(cancelled.assistant.state.selectedCreatorId, "");

globalThis.chrome = originalChrome;
globalThis.fetch = originalFetch;
console.log("Plugin V1 Gate 3C link selector tests passed");
