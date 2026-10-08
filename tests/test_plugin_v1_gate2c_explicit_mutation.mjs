import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const localApiUrl = new URL("../chrome_extension/services/local_api.js", import.meta.url);
const originalChrome = globalThis.chrome;
const originalFetch = globalThis.fetch;

globalThis.chrome = { storage: { local: { get: async () => ({}) } } };
const api = await import(localApiUrl);

const field = (value, source = "profile_dom", confidence = "high", missingReason = "") => ({
  value,
  source,
  confidence,
  missing_reason: missingReason
});

const mutationProfile = {
  platform: "Instagram",
  profile_url: "https://www.instagram.com/gate2c/",
  username: "@gate2c",
  creator_name: "Gate 2C",
  followers: 0,
  email: null,
  content_category: "Gaming",
  fields: {
    profile_url: field("https://www.instagram.com/gate2c/", "url"),
    username: field("@gate2c", "url"),
    creator_name: field("Gate 2C"),
    followers: field(0, "web_profile_info"),
    bio: field(null, "", "missing", "field_absent"),
    email: field(null, "", "missing", "field_absent"),
    content_category: field("Gaming", "user_input")
  },
  video_analysis: { capture_status: "partial_success", returned_count: 1 },
  videos: [{
    platform: "Instagram",
    video_id: "reel-1",
    video_url: "https://www.instagram.com/reel/reel-1/",
    views: field(0, "reel_card_dom"),
    likes: field(null, "", "missing", "likes_hidden"),
    comments: field(2, "detail_page_structured_data"),
    published_at: field(null, "", "missing", "publish_time_hidden")
  }]
};

const requests = [];
globalThis.fetch = async (_url, options) => {
  requests.push(JSON.parse(options.body));
  return {
    ok: true,
    status: 200,
    json: async () => ({
      ok: true,
      warnings: [{ code: "EMAIL_CONFLICT_PRESERVED" }],
      updated_fields: [],
      preserved_fields: ["creator.email"]
    })
  };
};
const addResult = await api.addAccount(mutationProfile);
const updateResult = await api.updateAccount(mutationProfile);
assert.equal(requests[0].action, "ADD");
assert.equal(requests[1].action, "UPDATE");
assert.equal(requests[0].creator.followers, 0);
assert.equal(requests[0].creator.fields.followers.value, 0);
assert.equal(requests[0].creator.username, "@gate2c");
assert.equal(requests[0].creator.fields.bio.value, null);
assert.equal(requests[0].creator.fields.bio.missing_reason, "field_absent");
assert.equal(requests[0].creator.fields.email.value, null);
assert.equal(requests[0].content_category, "Gaming");
assert.equal(requests[0].creator.fields.content_category.source, "user_input");
assert.equal(requests[0].video_analysis.capture_status, "partial_success");
assert.equal(requests[0].videos[0].views, 0);
assert.equal(requests[0].videos[0].field_provenance.views.source, "reel_card_dom");
assert.equal(addResult.warnings[0].code, "EMAIL_CONFLICT_PRESERVED");
assert.equal(updateResult.preserved_fields[0], "creator.email");
assert.deepEqual(api.validateMutationProfile("UPDATE", { ...mutationProfile, content_category: "" }), []);
assert.deepEqual(
  api.validateMutationProfile("ADD", { ...mutationProfile, content_category: "" }),
  ["Content Category"]
);
assert.throws(
  () => api.buildMutationPayload("", mutationProfile),
  (error) => error instanceof api.LocalApiError && error.code === "EXPLICIT_ACTION_REQUIRED"
);

globalThis.fetch = async () => ({
  ok: false,
  status: 409,
  json: async () => ({
    ok: false,
    error: { code: "ACCOUNT_ALREADY_EXISTS", message: "safe conflict" }
  })
});
await assert.rejects(
  () => api.addAccount(mutationProfile),
  (error) => error instanceof api.LocalApiError
    && error.code === "ACCOUNT_ALREADY_EXISTS"
    && error.status === 409
);

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

function findByClass(node, className) {
  if (node?.className === className) return node;
  for (const child of node?.children || []) {
    const found = findByClass(child, className);
    if (found) return found;
  }
  return null;
}

function createAssistant(responder, href = "https://www.instagram.com/gate2c/") {
  const documentElement = new FakeElement("html");
  const sent = [];
  const document = {
    documentElement,
    body: new FakeElement("body"),
    getElementById(id) {
      return documentElement.children.find((child) => child.id === id) || null;
    },
    createElement(tagName) {
      return tagName === "button" ? new FakeButtonElement(tagName) : new FakeElement(tagName);
    },
    execCommand() { return true; }
  };
  const location = { href };
  const runtime = {
    lastError: null,
    sendMessage(message, callback) {
      sent.push(message);
      responder(message, callback);
    },
    onMessage: { addListener() {} }
  };
  const context = vm.createContext({
    document,
    location,
    navigator: { clipboard: { writeText: async () => {} } },
    chrome: { runtime },
    HTMLButtonElement: FakeButtonElement,
    URL,
    Intl,
    Set,
    innerWidth: 1440,
    innerHeight: 900,
    setTimeout() { return 1; },
    clearTimeout() {},
    setInterval() { return 1; },
    addEventListener() {},
    console
  });
  context.window = context;
  for (const relative of [
    "config.js",
    "core/analysis_session.js",
    "core/page_support.js",
    "content/floating_assistant.js"
  ]) {
    vm.runInContext(
      readFileSync(new URL(`../chrome_extension/${relative}`, import.meta.url), "utf8"),
      context
    );
  }
  const assistant = context.__KOLCONNECT_NEXT_ASSISTANT__;
  return {
    assistant,
    sent,
    location,
    runtime,
    status: () => findByClass(assistant.root, "kol-status"),
    awareness: () => findByClass(assistant.root, "kol-account-awareness-text"),
    button: () => findByClass(assistant.root, "kol-primary")
  };
}

function prepare(harness, lookupState, platform = "Instagram") {
  const profileUrl = platform === "Instagram"
    ? "https://www.instagram.com/gate2c/"
    : platform === "TikTok"
      ? "https://www.tiktok.com/@gate2c"
      : "https://www.youtube.com/@gate2c";
  const profile = {
    ...mutationProfile,
    platform,
    profile_url: profileUrl,
    fields: {
      ...mutationProfile.fields,
      profile_url: field(profileUrl, "url")
    }
  };
  harness.assistant.state.profile = profile;
  harness.assistant.state.accountLookup = lookupState;
  harness.assistant.initializePreview(profile);
  return profile;
}

const successful = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_ADD_ACCOUNT") {
    return callback({
      ok: true,
      session_id: message.session_id,
      identity: message.identity,
      result: { warnings: [{ code: "EMAIL_CONFLICT_PRESERVED" }] }
    });
  }
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    return callback({ ok: true, lookup: { state: "ACCOUNT_EXISTS", creator: { display_name: "Gate 2C" }, linked_accounts: [] } });
  }
  callback({ ok: true });
});
prepare(successful, { state: "ACCOUNT_NOT_FOUND" });
assert.equal(successful.button().textContent, "添加到 KOLConnect");
successful.assistant.previewInputs.email.value = "edited@example.test";
successful.assistant.previewInputs.email.listeners.input();
await successful.assistant.mutateCurrent();
const addMessage = successful.sent.find((message) => message.type === "KOLCONNECT_NEXT_ADD_ACCOUNT");
assert.ok(addMessage);
assert.equal(successful.sent.some((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT"), false);
assert.equal(addMessage.profile.email, "edited@example.test");
assert.equal(addMessage.profile.fields.email.value, "edited@example.test");
assert.equal(addMessage.profile.fields.email.source, "user_input");
assert.match(successful.status().textContent, /添加成功/);
assert.match(successful.status().textContent, /已保留 KOLConnect 中的现有邮箱/);
assert.doesNotMatch(successful.status().textContent, /edited@example/);
assert.equal(successful.assistant.state.accountLookup.state, "ACCOUNT_EXISTS");
assert.equal(successful.assistant.state.mutationPending, false);
assert.equal(successful.button().textContent, "更新账号");

const existing = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT") {
    return callback({ ok: true, session_id: message.session_id, identity: message.identity, result: { warnings: [{ code: "FUTURE_WARNING" }] } });
  }
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    return callback({ ok: true, lookup: { state: "ACCOUNT_EXISTS", creator: { display_name: "Gate 2C" }, linked_accounts: [] } });
  }
  callback({ ok: true });
});
prepare(existing, {
  state: "ACCOUNT_EXISTS",
  creator: { display_name: "Gate 2C" },
  account: { updated_at: "2026-10-08T00:00:00Z" },
  linked_accounts: [{ platform: "Instagram", handle: "gate2c" }]
});
existing.assistant.previewInputs.content_category.value = "";
existing.assistant.previewInputs.content_category.listeners.change();
assert.equal(existing.button().textContent, "更新账号");
assert.equal(existing.button().disabled, false);
await existing.assistant.mutateCurrent();
assert.equal(existing.sent.filter((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT").length, 1);
assert.equal(existing.sent.some((message) => message.type === "KOLCONNECT_NEXT_ADD_ACCOUNT"), false);
assert.match(existing.status().textContent, /更新成功/);
assert.match(existing.status().textContent, /部分资料已按/);
assert.equal(existing.assistant.state.mutationPending, false);
assert.equal(existing.button().textContent, "更新账号");

let pendingCallback;
const doubleClick = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT") {
    pendingCallback = () => callback({ ok: true, session_id: message.session_id, identity: message.identity, result: { warnings: [] } });
    return;
  }
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    return callback({ ok: true, lookup: { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] } });
  }
  callback({ ok: true });
});
prepare(doubleClick, { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] });
const firstMutation = doubleClick.assistant.mutateCurrent();
await doubleClick.assistant.mutateCurrent();
assert.equal(doubleClick.sent.filter((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT").length, 1);
assert.equal(doubleClick.button().textContent, "正在更新…");
pendingCallback();
await firstMutation;
assert.equal(doubleClick.assistant.state.mutationPending, false);

const staleAdd = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_ADD_ACCOUNT") return callback({ ok: false, code: "ACCOUNT_ALREADY_EXISTS" });
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    return callback({ ok: true, lookup: { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] } });
  }
  callback({ ok: true });
});
prepare(staleAdd, { state: "ACCOUNT_NOT_FOUND" });
await staleAdd.assistant.mutateCurrent();
assert.equal(staleAdd.sent.some((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT"), false);
assert.equal(staleAdd.assistant.state.accountLookup.state, "ACCOUNT_EXISTS");
assert.equal(staleAdd.status().textContent, "账号已存在，已刷新收录状态");
assert.equal(staleAdd.assistant.state.mutationPending, false);
assert.equal(staleAdd.button().textContent, "更新账号");
assert.equal(staleAdd.button().disabled, false);

const staleUpdate = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT") return callback({ ok: false, code: "ACCOUNT_NOT_FOUND" });
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") return callback({ ok: true, lookup: { state: "ACCOUNT_NOT_FOUND" } });
  callback({ ok: true });
});
prepare(staleUpdate, { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] });
await staleUpdate.assistant.mutateCurrent();
assert.equal(staleUpdate.sent.some((message) => message.type === "KOLCONNECT_NEXT_ADD_ACCOUNT"), false);
assert.equal(staleUpdate.assistant.state.accountLookup.state, "ACCOUNT_NOT_FOUND");
assert.equal(staleUpdate.status().textContent, "账号记录已不存在，已刷新收录状态");
assert.equal(staleUpdate.assistant.state.mutationPending, false);
assert.equal(staleUpdate.button().textContent, "添加到 KOLConnect");
assert.equal(staleUpdate.button().disabled, false);

const ambiguous = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT") return callback({ ok: false, code: "AMBIGUOUS" });
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") return callback({ ok: true, lookup: { state: "AMBIGUOUS" } });
  callback({ ok: true });
});
prepare(ambiguous, { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] });
await ambiguous.assistant.mutateCurrent();
assert.equal(ambiguous.sent.filter((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT").length, 1);
assert.equal(ambiguous.sent.some((message) => message.type === "KOLCONNECT_NEXT_ADD_ACCOUNT"), false);
assert.equal(ambiguous.assistant.state.accountLookup.state, "AMBIGUOUS");
assert.equal(ambiguous.assistant.state.mutationPending, false);
assert.equal(ambiguous.button().textContent, "账号归属待确认");
assert.equal(ambiguous.button().disabled, true);
await ambiguous.assistant.mutateCurrent();
assert.equal(ambiguous.sent.filter((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT").length, 1);

const ambiguousAwareness = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  callback({ ok: true });
});
prepare(ambiguousAwareness, { state: "AMBIGUOUS" });
assert.equal(ambiguousAwareness.button().textContent, "账号归属待确认");
assert.equal(ambiguousAwareness.button().disabled, true);

const offlineAwareness = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  callback({ ok: true });
});
prepare(offlineAwareness, { state: "APP_OFFLINE" });
assert.equal(offlineAwareness.button().textContent, "KOLConnect 未运行");
assert.equal(offlineAwareness.button().disabled, true);

let transportOffline = true;
let transportAttempts = 0;
let transport;
transport = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT") {
    transportAttempts += 1;
    if (transportOffline) {
      transport.runtime.lastError = { message: "transport offline" };
      callback();
      transport.runtime.lastError = null;
      return;
    }
    return callback({ ok: true, session_id: message.session_id, identity: message.identity, result: { warnings: [] } });
  }
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    return callback({ ok: true, lookup: { state: "ACCOUNT_EXISTS", creator: { display_name: "Retry Creator" }, linked_accounts: [] } });
  }
  callback({ ok: true });
});
prepare(transport, { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] });
await transport.assistant.mutateCurrent();
assert.equal(transportAttempts, 1);
assert.equal(transport.assistant.state.mutationPending, false);
assert.equal(transport.assistant.state.mutationOffline, true);
assert.equal(transport.assistant.state.accountLookup.state, "ACCOUNT_EXISTS");
assert.equal(transport.sent.filter((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT").length, 1);
transportOffline = false;
transport.location.href = "https://www.instagram.com/retry-profile/";
transport.assistant.handleUrlChange(transport.location.href);
prepare(transport, { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] });
assert.equal(transport.button().disabled, false);
await transport.assistant.mutateCurrent();
assert.equal(transportAttempts, 2);
assert.equal(transport.assistant.state.mutationPending, false);
assert.match(transport.status().textContent, /更新成功/);

let lateCallback;
const navigation = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT") {
    lateCallback = () => callback({ ok: true, session_id: message.session_id, identity: message.identity, result: { warnings: [] } });
    return;
  }
  callback({ ok: true });
});
prepare(navigation, { state: "ACCOUNT_EXISTS", creator: {}, linked_accounts: [] });
const oldMutation = navigation.assistant.mutateCurrent();
navigation.location.href = "https://www.instagram.com/profile-b/";
navigation.assistant.handleUrlChange(navigation.location.href);
lateCallback();
await oldMutation;
assert.equal(navigation.sent.filter((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT").length, 1);
assert.equal(navigation.sent.filter((message) => message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT").length, 0);
assert.doesNotMatch(navigation.status().textContent, /更新成功/);

let staleLookupCallback;
const lateRefresh = createAssistant((message, callback) => {
  if (message.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") return callback({ ok: true, agencies: [] });
  if (message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT") {
    return callback({ ok: true, session_id: message.session_id, identity: message.identity, result: { warnings: [] } });
  }
  if (message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT") {
    staleLookupCallback = callback;
    return;
  }
  callback({ ok: true });
});
prepare(lateRefresh, {
  state: "ACCOUNT_EXISTS",
  creator: { display_name: "Profile A" },
  linked_accounts: []
});
const lateRefreshMutation = lateRefresh.assistant.mutateCurrent();
await new Promise((resolve) => setImmediate(resolve));
assert.equal(typeof staleLookupCallback, "function");
assert.equal(lateRefresh.sent.filter((message) => message.type === "KOLCONNECT_NEXT_LOOKUP_ACCOUNT").length, 1);
lateRefresh.location.href = "https://www.instagram.com/profile-b/";
lateRefresh.assistant.handleUrlChange(lateRefresh.location.href);
prepare(lateRefresh, {
  state: "ACCOUNT_NOT_FOUND"
});
const profileBUrl = lateRefresh.assistant.state.profile.profile_url;
const profileBAwareness = lateRefresh.awareness().textContent;
const profileBButton = lateRefresh.button().textContent;
staleLookupCallback({
  ok: true,
  lookup: { state: "ACCOUNT_EXISTS", creator: { display_name: "Profile A stale" }, linked_accounts: [] }
});
await lateRefreshMutation;
assert.equal(lateRefresh.assistant.state.profile.profile_url, profileBUrl);
assert.equal(lateRefresh.assistant.state.accountLookup.state, "ACCOUNT_NOT_FOUND");
assert.equal(lateRefresh.awareness().textContent, profileBAwareness);
assert.equal(lateRefresh.button().textContent, profileBButton);
assert.equal(lateRefresh.sent.filter((message) => message.type === "KOLCONNECT_NEXT_UPDATE_ACCOUNT").length, 1);
assert.equal(lateRefresh.sent.filter((message) => message.type === "KOLCONNECT_NEXT_ADD_ACCOUNT").length, 0);
assert.doesNotMatch(lateRefresh.awareness().textContent, /Profile A stale/);
assert.doesNotMatch(lateRefresh.status().textContent, /更新成功/);

const contentStates = ["success", "partial_success", "failed", "unavailable", "cancelled", "timed_out"];
for (const captureStatus of contentStates) {
  const payload = api.buildMutationPayload("UPDATE", {
    ...mutationProfile,
    videos: [],
    video_analysis: { capture_status: captureStatus }
  });
  assert.equal(payload.video_analysis.capture_status, captureStatus);
}
const notRun = api.buildMutationPayload("UPDATE", { ...mutationProfile, videos: undefined, video_analysis: undefined });
assert.deepEqual(notRun.videos, []);
assert.deepEqual(notRun.video_analysis, {});

for (const platform of ["Instagram", "TikTok", "YouTube"]) {
  const profileUrl = platform === "Instagram"
    ? "https://www.instagram.com/gate2c/"
    : platform === "TikTok" ? "https://www.tiktok.com/@gate2c" : "https://www.youtube.com/@gate2c";
  const payload = api.buildMutationPayload("UPDATE", {
    ...mutationProfile,
    platform,
    profile_url: profileUrl,
    fields: { ...mutationProfile.fields, profile_url: field(profileUrl, "url") }
  });
  assert.equal(payload.action, "UPDATE");
  assert.equal(payload.creator.platform, platform);
  assert.equal(payload.creator.profile_url, profileUrl);
  assert.equal(payload.creator.fields.followers.value, 0);
}

globalThis.chrome = originalChrome;
globalThis.fetch = originalFetch;
console.log("Plugin V1 Gate 2C explicit mutation tests passed");
