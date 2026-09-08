import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import * as TikTok from "../chrome_extension/platform/tiktok.js";
import { contentItem, finalizeContentAnalysis } from "../chrome_extension/core/content_analysis.js";
import { buildImportPayload } from "../chrome_extension/services/local_api.js";

const require = createRequire(import.meta.url);
const Protocol = require("../chrome_extension/capture/passive_capture_protocol.js");
const Main = require("../chrome_extension/capture/passive_capture_main.js");
const Bridge = require("../chrome_extension/content/passive_capture_bridge.js");
const Network = require("../chrome_extension/platform/tiktok_network.js");
const Session = require("../chrome_extension/capture/tiktok_capture_session.js");
const fixture = JSON.parse(readFileSync(new URL("fixtures/tiktok/item_list_normal.json", import.meta.url), "utf8"));
const runtimeCode = readFileSync(new URL("../chrome_extension/content/tiktok_capture_runtime.js", import.meta.url), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));
const context = (layer, profile = "fixture_creator", time = "2026-09-03T00:00:01Z") => ({ profile, layer, observedAt: time });
const normalized = (id, views, source = "dom") => contentItem({ video_id: id, views, views_source: source,
  views_confidence: source === "hydration" ? "medium" : "low", likes: null });

// Pure merge: same ID only, per-field precedence, zero != missing, defensive snapshot.
const session = Session.createSession("fixture_creator", () => Date.parse("2026-09-03T00:01:00Z"));
const network = Network.parseTikTokItemListResponse(fixture).items;
session.add(network, context("L1"));
session.add(network, context("L1"));
session.add([normalized(network[0].video_id, 999999)], context("L3"));
assert.equal(session.snapshot().items.length, 2);
assert.equal(session.snapshot().items[0].views.value, network[0].views.value);
assert.equal(session.snapshot().items[0].views.source, "tiktok_item_list_api");
session.snapshot().items[0].views.value = -1;
assert.notEqual(session.snapshot().items[0].views.value, -1);
const partial = Session.createSession("fixture_creator");
partial.add([normalized("123", 0, "hydration")], context("L2"));
partial.add([normalized("123", 999)], context("L3"));
partial.add([contentItem({ video_id: "123", likes: 7, likes_source: "dom", likes_confidence: "low" })], context("L3"));
assert.equal(partial.snapshot().items[0].views.value, 0);
assert.equal(partial.snapshot().items[0].likes.value, 7);
assert.equal(partial.snapshot().items[0].comments.value, null);
partial.add([normalized("123", 10, "tiktok_item_list_api")], context("L1"));
partial.add([normalized("123", null)], context("L3"));
assert.equal(partial.snapshot().items[0].views.value, 10);
partial.add([normalized("124", 2)], context("L3", "another_account"));
partial.add([{ ...normalized("124", 2), author_username: "another_account" }], context("L1"));
assert.equal(partial.snapshot().items.length, 1);
assert.equal(Session.createSession("").snapshot().items.length, 0);
const noIdentity = Session.createSession("");
noIdentity.add(network, context("L1", ""));
assert.equal(noIdentity.snapshot().items.length, 0);
const oldId = session.snapshot().session_id;
session.reset("other");
session.add(network, context("L1"));
session.add(network, context("L1", "other")); // response initiated before reset
assert.equal(session.snapshot().items.length, 0);
assert.notEqual(session.snapshot().session_id, oldId);
session.add(network, context("L1", "other", "2026-09-03T00:02:00Z"));
assert.equal(session.snapshot().items.length, 2);
session.stop("LOGIN_REQUIRED");
session.add(network, context("L1", "other", "2026-09-03T00:03:00Z"));
assert.equal(session.snapshot().items.length, 0);
const bounded = Session.createSession("fixture_creator");
for (let i = 0; i < 500; i++) bounded.add([normalized(String(i), i)], context("L3"));
assert.equal(bounded.snapshot().items.length, 200);
const sanitized = Protocol.sanitizeCapturePayload({ itemList: Array(150).fill({ ...fixture.itemList[0],
  token: "secret", author: { uniqueId: "fixture_creator", email: "private" }, headers: { Cookie: "private" } }) }, "tiktok_item_list");
assert.equal(sanitized.itemList.length, 100);
assert.doesNotMatch(JSON.stringify(sanitized), /secret|private|Cookie|headers/);

// Production MAIN wrapper -> real bridge/parser/runtime -> real L2/L3 -> preview/import serializer.
function harness(connect = true) {
  let requests = 0, blocked = "", anchors = [], hydration = null;
  const location = { href: "https://www.tiktok.com/@fixture_creator", origin: "https://www.tiktok.com", pathname: "/@fixture_creator" };
  const document = {
    querySelectorAll(selector) {
      if (selector === 'a[href*="/video/"]') return anchors;
      if ((blocked === "CAPTCHA_DETECTED" && selector.includes("captcha"))
          || (blocked === "LOGIN_REQUIRED" && selector.includes("login-modal"))
          || (blocked === "CAPTURE_BLOCKED" && selector.includes("security-check"))) return [{ getClientRects: () => [1] }];
      return [];
    },
    getElementById(id) { return id === "SIGI_STATE" && hydration ? { textContent: JSON.stringify(hydration) } : null; },
  };
  const listeners = [];
  const target = {
    location, document, URL, crypto: globalThis.crypto,
    KOLConnectPassiveCaptureProtocol: Protocol, KOLConnectTikTokSession: Session,
    getComputedStyle: () => ({ visibility: "visible" }),
    addEventListener: (_type, fn) => listeners.push(fn),
  };
  const dispatch = (data, extra = {}) => listeners.forEach(fn => fn({ data, source: target, origin: location.origin, ...extra }));
  const main = { location, document, URL, crypto: globalThis.crypto, addEventListener() {},
    postMessage: (data) => dispatch(data),
    fetch: async () => { requests += 1; return { ok: true, clone: () => ({ json: async () => fixture }) }; },
  };
  Main.installMainWorldCapture(main, Protocol);
  Bridge.installIsolatedBridge(target, Protocol, Network);
  const messages = [];
  target.chrome = { runtime: { onMessage: { addListener: fn => messages.push(fn) },
    async sendMessage(message) {
      if (message.type === "KOLCONNECT_PASSIVE_CONNECT") return { token: connect ? main.KOLConnectPassiveCaptureControl.token() : null };
      if (message.type === "KOLCONNECT_PASSIVE_REPLAY") main.KOLConnectPassiveCaptureControl.replay();
      else throw new Error("Unexpected external request");
      return { ok: true };
    },
  } };
  target.globalThis = target; target.window = target;
  vm.createContext(target);
  vm.runInContext(runtimeCode, target);
  main.window = main; main.globalThis = main;
  vm.createContext(main);
  return {
    target, main, requests: () => requests,
    block(value) { blocked = value; },
    hydration(value) { hydration = value; },
    dom(id, views) { anchors = [{ href: `https://www.tiktok.com/@fixture_creator/video/${id}`,
      getClientRects: () => [1], closest() { return this; }, getAttribute: () => "DOM title",
      querySelector: selector => selector.includes("video-views") ? { textContent: views } : null }]; },
    chrome: { scripting: { async executeScript({ world, func, args = [] }) {
      const scope = world === "ISOLATED" ? target : main;
      scope.__args = args;
      return [{ result: await vm.runInContext(`(${func.toString()})(...__args)`, scope) }];
    } } },
    dispatch,
  };
}
const savedChrome = globalThis.chrome;
const tab = harness();
await tick();
globalThis.chrome = tab.chrome;
const options = { analysisUrl: tab.main.location.href, excludePinned: false };
await tab.main.fetch("/api/post/item_list/?credentials=DO_NOT_FORWARD");
await tick();
await tab.main.fetch("/api/post/item_list/");
await tick();
const l1 = await TikTok.collectRecentContent(1, options);
assert.equal(tab.requests(), 2, "only the two simulated page calls, no extension detail requests");
assert.equal(l1.passive_capture_status, "CAPTURE_L1_ACTIVE");
assert.equal(l1.returned_count, 2);
assert.equal(l1.contents[0].field_provenance.views.layer, "L1");
assert.equal(l1.contents[0].observed_at, l1.contents[0].views.observed_at);
const beforeDiagnostic = JSON.stringify(tab.target.KOLConnectTikTokCapture.snapshot("fixture_creator"));
const liveDiagnostic = await TikTok.readCaptureDiagnostics(1);
assert.equal(liveDiagnostic.main.installed, true);
assert.equal(liveDiagnostic.main.fetch_interceptions, 2);
assert.equal(liveDiagnostic.main.target_matches, 2);
assert.equal(liveDiagnostic.main.envelopes_emitted, 2);
assert.equal(liveDiagnostic.runtime.bridge.accepted, 2);
assert.equal(liveDiagnostic.runtime.bridge.parser_invocations, 2);
assert.equal(liveDiagnostic.runtime.bridge.normalized_rows, 4);
assert.equal(liveDiagnostic.runtime.session.l1_accepted_rows, 4);
assert.equal(liveDiagnostic.runtime.session.current_l1_rows, 2);
assert.equal(tab.requests(), 2);
assert.equal(JSON.stringify(tab.target.KOLConnectTikTokCapture.snapshot("fixture_creator")), beforeDiagnostic);
assert.doesNotMatch(JSON.stringify(liveDiagnostic), /bridgeToken|DO_NOT_FORWARD|fixture_creator/);
assert.notEqual(l1.contents[0].observed_at, l1.contents[0].published_at.value);
globalThis.chrome = { scripting: { async executeScript(request) {
  if (request.world === "MAIN") throw new Error("malformed hydration fixture");
  return tab.chrome.scripting.executeScript(request);
} } };
const brokenFallback = await TikTok.collectRecentContent(1, options);
assert.equal(brokenFallback.passive_capture_status, "CAPTURE_L1_ACTIVE");
assert.equal(brokenFallback.returned_count, 2);
assert.equal(brokenFallback.capture_diagnostics.fallback_error, "PARSER_ERROR");
const payload = buildImportPayload({ platform: "TikTok", creator_name: "Fixture Creator", username: "fixture_creator",
  profile_url: options.analysisUrl, content_category: "Gaming", videos: l1.contents });
assert.equal(payload.videos.length, 2);
assert.equal(payload.videos[0].field_provenance.views.layer, "L1");
assert.ok(payload.videos[0].observed_at);
assert.doesNotMatch(JSON.stringify(payload), /bridgeToken|Cookie|credentials|Authorization/);
const l2tab = harness(); await tick(); globalThis.chrome = l2tab.chrome;
l2tab.hydration({ itemList: [{ id: "123", desc: "Hydrated", author: { uniqueId: "fixture_creator" }, stats: { playCount: 0, diggCount: 8 } },
  { id: "456", desc: "Other account", author: { uniqueId: "wrong" }, stats: { playCount: 99 } }] });
l2tab.dom("123", "999");
const l2 = await TikTok.collectRecentContent(2, options);
assert.equal(l2.passive_capture_status, "FALLBACK_L2");
assert.equal(l2.returned_count, 1);
assert.equal(l2.contents[0].views.value, 0);
assert.equal(l2.contents[0].views.confidence, "medium");
assert.equal(l2.contents[0].comments.value, null);
assert.equal(l2tab.requests(), 0);
const l3tab = harness(); await tick(); globalThis.chrome = l3tab.chrome;
l3tab.dom("234", "1.2K");
const l3 = await TikTok.collectRecentContent(3, options);
assert.equal(l3.passive_capture_status, "FALLBACK_L3");
assert.equal(l3.contents[0].views.value, 1200);
assert.equal(l3.contents[0].views.confidence, "low");
assert.equal(l3.contents[0].likes.value, null);
assert.equal(l3tab.requests(), 0);
const unavailableBridge = harness(false); await tick(); globalThis.chrome = unavailableBridge.chrome;
unavailableBridge.dom("234", "42");
const degraded = await TikTok.collectRecentContent(3, options);
assert.equal(degraded.capture_diagnostics.bridge_connected, false);
assert.equal(degraded.passive_capture_status, "FALLBACK_L3");
for (const reason of ["CAPTCHA_DETECTED", "LOGIN_REQUIRED", "CAPTURE_BLOCKED"]) {
  const blockedTab = harness(); await tick(); globalThis.chrome = blockedTab.chrome;
  blockedTab.block(reason);
  await assert.rejects(TikTok.collectRecentContent(4, options), new RegExp(reason));
  await blockedTab.main.fetch("/api/post/item_list/"); await tick();
  assert.equal(blockedTab.target.KOLConnectTikTokCapture.snapshot("fixture_creator").items.length, 0);
  assert.equal(blockedTab.requests(), 1);
  blockedTab.block("");
  await assert.rejects(TikTok.collectRecentContent(4, options), new RegExp(reason), "block remains sticky until explicit reset");
  await TikTok.resetCapture(4);
  assert.equal(blockedTab.target.KOLConnectTikTokCapture.snapshot("fixture_creator").stopped, "");
}
const empty = harness(); await tick(); globalThis.chrome = empty.chrome;
assert.equal((await TikTok.collectRecentContent(5, options)).passive_capture_status, "NO_DATA");
const malformed = Protocol.createCaptureEnvelope({ bridgeToken: empty.main.KOLConnectPassiveCaptureControl.token(),
  endpointKind: "tiktok_item_list", method: "GET", payload: {}, profile: "fixture_creator", observedAt: new Date().toISOString() });
empty.dispatch(malformed);
assert.equal((await TikTok.collectRecentContent(5, options)).passive_capture_status, "PARSER_ERROR");
empty.target.location.href = "https://www.tiktok.com/@another";
assert.throws(() => empty.target.KOLConnectTikTokCapture.snapshot("fixture_creator"), /CAPTURE_PROFILE_CHANGED/);
assert.notEqual(tab.target.KOLConnectTikTokCapture.snapshot("fixture_creator").session_id,
  l2tab.target.KOLConnectTikTokCapture.snapshot("fixture_creator").session_id);
globalThis.chrome = savedChrome;
const source = readFileSync(new URL("../chrome_extension/platform/tiktok.js", import.meta.url), "utf8");
assert.doesNotMatch(source, /fetchTikTokContentDetail|\bfetch\(|scrollTo|scrollBy/);
const preview = readFileSync(new URL("../chrome_extension/content/floating_assistant.js", import.meta.url), "utf8");
assert.match(preview, /field_provenance/);
assert.match(preview, /重新开始 TikTok 被动采集/);
assert.match(preview, /KOLCONNECT_PASSIVE_RESET/);
// Exercise the actual background dispatcher: only a top-level extension content
// script on an allowed HTTPS TikTok origin can obtain/replay/reset capture state.
let receive, actionClick, injectionCalls = 0, imports = 0, assistantAvailable = false;
const recoveryInjections = [], assistantMessages = [];
const backgroundTab = harness(); await tick();
const savedFetch = globalThis.fetch;
globalThis.chrome = {
  runtime: { id: "test-extension", onMessage: { addListener: fn => { receive = fn; } } },
  action: { onClicked: { addListener: fn => { actionClick = fn; } } },
  tabs: { onUpdated: { addListener() {} }, onRemoved: { addListener() {} },
    async sendMessage(_tabId, message) {
      if (!assistantAvailable) throw new Error("Receiving end does not exist");
      assistantMessages.push(message); return { ok: true };
    } },
  webNavigation: { onHistoryStateUpdated: { addListener() {} }, onReferenceFragmentUpdated: { addListener() {} } },
  storage: { local: { get: async () => ({}) } },
  scripting: { async insertCSS() {}, async executeScript(request) {
    injectionCalls += 1;
    if (request.files) {
      recoveryInjections.push({ world: request.world || "ISOLATED", files: [...request.files] });
      if (request.files.includes("content/tiktok_capture_runtime.js")) {
        for (const file of request.files) {
          vm.runInContext(readFileSync(new URL(`../chrome_extension/${file}`, import.meta.url), "utf8"), backgroundTab.target);
        }
      } else {
        assistantAvailable = true;
      }
      return [];
    }
    return backgroundTab.chrome.scripting.executeScript(request);
  } },
};
globalThis.fetch = async (url, options) => {
  assert.equal(String(url), "http://127.0.0.1:8765/api/extension/import");
  assert.equal(options.method, "POST"); imports += 1;
  return { ok: true, json: async () => ({ ok: true }) };
};
await import("../chrome_extension/background.js");
const sender = { id: "test-extension", frameId: 0, url: options.analysisUrl, tab: { id: 99, url: options.analysisUrl } };
for (const invalid of [{ id: "wrong" }, { frameId: 1 }, { url: "https://evil.example" }, { url: "http://www.tiktok.com/@fixture_creator" }]) {
  assert.equal(receive({ type: "KOLCONNECT_PASSIVE_CONNECT" }, { ...sender, ...invalid }, () => assert.fail("unexpected reply")), false);
  assert.equal(receive({ type: "KOLCONNECT_PASSIVE_DIAGNOSTICS" }, { ...sender, ...invalid }, () => assert.fail("unexpected diagnostic reply")), false);
}
assert.equal(injectionCalls, 0);
const message = value => new Promise(resolve => assert.equal(receive(value, sender, resolve), true));
const backgroundDiagnostic = await message({ type: "KOLCONNECT_PASSIVE_DIAGNOSTICS" });
assert.equal(backgroundDiagnostic.ok, true);
assert.equal(backgroundDiagnostic.diagnostics.main.fetch_interceptions, 0);
assert.equal(backgroundDiagnostic.diagnostics.runtime.session.current_rows, 0);
assert.equal(backgroundTab.requests(), 0);
assert.match((await message({ type: "KOLCONNECT_PASSIVE_CONNECT" })).token, /^[a-f0-9]{32}$/);
await message({ type: "KOLCONNECT_PASSIVE_REPLAY" });
assert.equal(imports, 0);
const importProfile = { platform: "TikTok", profile_url: options.analysisUrl, username: "fixture_creator", content_category: "Gaming", videos: l1.contents };
backgroundTab.block("LOGIN_REQUIRED");
const blockedAnalysis = await message({ type: "KOLCONNECT_NEXT_ANALYZE_CONTENT", session_id: "blocked-case" });
assert.equal(blockedAnalysis.ok, true);
assert.equal(blockedAnalysis.analysis.capture_status, "failed");
assert.equal(blockedAnalysis.analysis.error, "LOGIN_REQUIRED");
assert.equal((await message({ type: "KOLCONNECT_NEXT_IMPORT", profile: importProfile })).ok, false);
assert.equal(imports, 0, "challenge blocks even an old preview import");
backgroundTab.block("");
await message({ type: "KOLCONNECT_PASSIVE_RESET" });
assert.equal(imports, 0);
assert.equal((await message({ type: "KOLCONNECT_NEXT_IMPORT", profile: importProfile })).ok, true);
assert.equal(imports, 1, "only explicit user import uses the existing local API");

// Extension reload recovery: an already-open page can retain MAIN capture while
// its old isolated receiver is gone. Opening the assistant restores the same
// isolated dependency chain declared by the production manifest.
vm.runInContext("delete globalThis.KOLConnectTikTokCapture", backgroundTab.target);
assert.equal(vm.runInContext("typeof globalThis.KOLConnectTikTokCapture", backgroundTab.target), "undefined");
await actionClick(sender.tab);
await tick();
assert.ok(backgroundTab.target.KOLConnectTikTokCapture, "assistant fallback restores isolated capture runtime");
assert.equal(backgroundTab.target.KOLConnectTikTokCapture.diagnostics().bridge_connected, true);
const productionManifest = JSON.parse(readFileSync(new URL("../chrome_extension/manifest.json", import.meta.url), "utf8"));
const manifestIsolated = productionManifest.content_scripts.find(entry =>
  entry.world === "ISOLATED" && entry.js.includes("content/tiktok_capture_runtime.js"));
assert.deepEqual(recoveryInjections[0], { world: "ISOLATED", files: manifestIsolated.js });
assert.deepEqual(recoveryInjections[1].files,
  ["config.js", "core/analysis_session.js", "core/page_support.js", "content/floating_assistant.js"]);
assert.ok(assistantMessages.some(message => message.type === "KOLCONNECT_NEXT_OPEN"));
const recoveredRuntime = backgroundTab.target.KOLConnectTikTokCapture;
const recoveredDiagnostic = JSON.stringify(recoveredRuntime.diagnostics());
await actionClick(sender.tab);
await tick();
assert.equal(backgroundTab.target.KOLConnectTikTokCapture, recoveredRuntime, "repeated recovery is idempotent");
assert.equal(JSON.stringify(recoveredRuntime.diagnostics()), recoveredDiagnostic);
assert.deepEqual(recoveryInjections[2], { world: "ISOLATED", files: manifestIsolated.js });
assert.equal(backgroundTab.requests(), 0, "runtime recovery adds no TikTok requests");
assert.equal(imports, 1, "runtime recovery does not import local data");

// Production manifest order joins a surviving MAIN wrapper to a fresh isolated
// world and consumes envelopes that arrived while the extension was reloading.
let reloadFetches = 0;
const reloadLocation = { href: options.analysisUrl, origin: "https://www.tiktok.com", pathname: "/@fixture_creator" };
const reloadListeners = [];
let reloadEventSource;
const reloadIsolated = {
  location: reloadLocation, URL, crypto: globalThis.crypto,
  document: { querySelectorAll: () => [] }, getComputedStyle: () => ({ visibility: "visible" }),
  addEventListener: (_type, listener) => reloadListeners.push(listener),
};
const reloadMain = {
  location: reloadLocation, URL, crypto: globalThis.crypto, addEventListener() {},
  postMessage(data) {
    for (const listener of reloadListeners) listener({ data, source: reloadEventSource, origin: reloadLocation.origin });
  },
  async fetch() {
    reloadFetches += 1;
    return { ok: true, clone: () => ({ json: async () => fixture }) };
  },
};
for (const scope of [reloadMain, reloadIsolated]) {
  scope.globalThis = scope; scope.window = scope; vm.createContext(scope);
}
reloadEventSource = vm.runInContext("globalThis", reloadIsolated);
const manifestMain = productionManifest.content_scripts.find(entry =>
  entry.world === "MAIN" && entry.js.includes("capture/passive_capture_main.js"));
for (const file of manifestMain.js) {
  vm.runInContext(readFileSync(new URL(`../chrome_extension/${file}`, import.meta.url), "utf8"), reloadMain);
}
await reloadMain.fetch("/api/post/item_list/?msToken=DO_NOT_EXPOSE");
await tick();
assert.equal(reloadMain.KOLConnectPassiveCaptureControl.diagnostics().pending_envelopes, 1);
const isolatedMessages = [];
reloadIsolated.chrome = { runtime: {
  onMessage: { addListener: listener => isolatedMessages.push(listener) },
  async sendMessage(request) {
    if (request.type === "KOLCONNECT_PASSIVE_CONNECT") {
      return { token: reloadMain.KOLConnectPassiveCaptureControl.token() };
    }
    if (request.type === "KOLCONNECT_PASSIVE_REPLAY") {
      reloadMain.KOLConnectPassiveCaptureControl.replay(); return { ok: true };
    }
    throw new Error("Unexpected extension message");
  },
} };
for (const file of manifestIsolated.js) {
  vm.runInContext(readFileSync(new URL(`../chrome_extension/${file}`, import.meta.url), "utf8"), reloadIsolated);
}
await tick();
const joined = reloadIsolated.KOLConnectTikTokCapture.diagnostics();
assert.equal(joined.bridge_connected, true);
assert.equal(joined.bridge.accepted, 1);
assert.equal(joined.bridge.parser_invocations, 1);
assert.equal(joined.bridge.parser_success, 1);
assert.equal(joined.session.l1_accepted_rows, 2);
assert.equal(joined.session.current_l1_rows, 2);
assert.equal(reloadMain.KOLConnectPassiveCaptureControl.diagnostics().pending_envelopes, 0);
assert.equal(reloadFetches, 1, "isolated join and replay make no TikTok request");
const forged = Protocol.createCaptureEnvelope({ bridgeToken: "f".repeat(32), endpointKind: "tiktok_item_list",
  method: "GET", profile: "fixture_creator", observedAt: new Date().toISOString(), payload: fixture });
reloadMain.postMessage(forged);
assert.equal(reloadIsolated.KOLConnectTikTokCapture.diagnostics().bridge.rejected_reasons.token_mismatch, 1);
assert.equal(reloadIsolated.KOLConnectTikTokCapture.diagnostics().session.current_l1_rows, 2);

// Real assistant button -> real background dispatcher -> serialized MAIN/ISOLATED
// reads -> live capture provider. Delay delivery to exercise the UI's null sentinel.
class DiagnosticElement {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {};
    this.style = {}; this.dataset = {}; this.textContent = ""; this.value = "";
    this.classList = { toggle() {} };
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, listener) { this.listeners[type] = listener; }
}
class DiagnosticButton extends DiagnosticElement {}
const html = new DiagnosticElement("html");
const isolated = backgroundTab.target;
isolated.document.documentElement = html;
isolated.document.body = new DiagnosticElement("body");
isolated.document.createElement = tag => tag === "button" ? new DiagnosticButton(tag) : new DiagnosticElement(tag);
isolated.document.getElementById = id => html.children.find(child => child.id === id);
Object.assign(isolated, {
  HTMLButtonElement: DiagnosticButton, Intl, console, innerWidth: 1400, innerHeight: 900,
  setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1,
  navigator: { clipboard: { writeText: async () => {} } },
});
const deliveries = [], diagnosticRequests = [], diagnosticWorlds = [];
let dropDiagnosticReply = false;
const executeDiagnosticScript = globalThis.chrome.scripting.executeScript;
globalThis.chrome.scripting.executeScript = request => {
  assert.deepEqual(request.target, { tabId: 99 }, "diagnostics target sender tab's top frame, not active tab");
  diagnosticWorlds.push(request.world);
  return executeDiagnosticScript(request);
};
isolated.chrome.runtime.sendMessage = (request, callback) => {
  if (request.type === "KOLCONNECT_NEXT_LOAD_AGENCIES") {
    callback({ ok: true, agencies: [] }); return;
  }
  if (request.type === "KOLCONNECT_PASSIVE_DIAGNOSTICS") {
    diagnosticRequests.push(request);
    assert.equal(receive(request, { ...sender, url: isolated.location.href }, response => {
      // Chrome extension messaging serializes the reply rather than sharing objects.
      deliveries.push(() => callback(dropDiagnosticReply ? undefined : JSON.parse(JSON.stringify(response))));
    }), true);
    return;
  }
  assert.ok(["KOLCONNECT_NEXT_ANALYZE_CONTENT", "KOLCONNECT_NEXT_CANCEL_CONTENT"].includes(request.type));
  receive(request, sender, callback);
};
for (const file of ["config.js", "core/analysis_session.js", "core/page_support.js", "content/floating_assistant.js"]) {
  vm.runInContext(readFileSync(new URL(`../chrome_extension/${file}`, import.meta.url), "utf8"), isolated);
}
const assistant = isolated.__KOLCONNECT_NEXT_ASSISTANT__;
const walk = node => [node, ...node.children.flatMap(walk)];
const diagnosticButton = walk(html).find(node => node.textContent === "刷新 TikTok 诊断（只读）");
const reportText = () => walk(html).filter(node => node.tagName === "PRE").map(node => node.textContent).join("\n");
const importsBeforeDiagnostic = imports;
const requestsBeforeDiagnostic = backgroundTab.requests();
const provider = isolated.KOLConnectTikTokCapture;
const providerBeforeDiagnostic = JSON.stringify(provider.diagnostics());
assistant.state.profile = { platform: "TikTok", username: "fixture_creator", creator_name: "Fixture",
  profile_url: isolated.location.href, content_category: "Gaming", diagnostic_report: {} };
assistant.initializePreview(assistant.state.profile);
await assistant.analyzeContent();
assert.ok(assistant.state.contentAnalysis, "real completed content analysis state is present before diagnostic read");
diagnosticWorlds.length = 0;
assert.equal(assistant.getCaptureDiagnostics().runtime, null, "initial UI null does not mean provider absent");
assert.ok(provider);
let refresh = diagnosticButton.listeners.click();
assert.equal(diagnosticButton.disabled, true);
assert.equal(assistant.getCaptureDiagnostics().runtime, null, "in-flight first read retains initial UI sentinel");
await tick();
assert.equal(deliveries.length, 1);
deliveries.shift()();
await refresh;
assert.equal(diagnosticButton.disabled, false);
assert.ok(assistant.state.contentAnalysis);
assert.equal(assistant.getCaptureDiagnostics().runtime.runtime.available, true);
assert.equal(assistant.getCaptureDiagnostics().runtime.runtime.session.current_rows, 0);
assert.match(reportText(), /"available": true/);
assert.match(reportText(), /"content_analysis_present": true/);
assert.deepEqual(JSON.parse(JSON.stringify(assistant.getCaptureDiagnostics().diagnostic_trace)), {
  request_id: 1,
  status: "STATE_ASSIGNED",
  request_started: true,
  background_response_received: true,
  background_response_ok: true,
  background_response_diagnostics_present: true,
  background_response_runtime_present: true,
  state_assigned: true,
  state_invalidated: false,
  state_rendered: true,
  reason: "",
});
assert.equal(JSON.stringify(provider.diagnostics()), providerBeforeDiagnostic);

// A URL change intentionally invalidates the assistant snapshot and drops the old
// asynchronous response. The provider still exists in the same isolated context.
refresh = diagnosticButton.listeners.click();
await tick();
isolated.location.href = "https://www.tiktok.com/@another_fixture";
assistant.handleUrlChange(isolated.location.href);
assert.equal(assistant.getCaptureDiagnostics().runtime, null);
deliveries.shift()();
await refresh;
assert.equal(assistant.getCaptureDiagnostics().runtime, null, "old-page diagnostics are not applied to a new page");
assert.equal(assistant.getCaptureDiagnostics().diagnostic_trace.status, "STATE_INVALIDATED");
assert.equal(assistant.getCaptureDiagnostics().diagnostic_trace.reason, "URL_CHANGED");
assert.equal(isolated.KOLConnectTikTokCapture, provider);
refresh = diagnosticButton.listeners.click();
await tick(); deliveries.shift()(); await refresh;
assert.equal(assistant.getCaptureDiagnostics().runtime.runtime.available, true);

// Provider absence is represented by available=false, not the outer UI sentinel.
vm.runInContext("delete globalThis.KOLConnectTikTokCapture", isolated);
assert.equal(vm.runInContext("typeof globalThis.KOLConnectTikTokCapture", isolated), "undefined");
refresh = diagnosticButton.listeners.click();
await tick(); deliveries.shift()(); await refresh;
assert.notEqual(assistant.getCaptureDiagnostics().runtime, null);
assert.equal(assistant.getCaptureDiagnostics().runtime.runtime.available, false);
assert.equal(assistant.getCaptureDiagnostics().runtime.runtime.session.current_rows, null);
isolated.KOLConnectTikTokCapture = provider;
dropDiagnosticReply = true;
refresh = diagnosticButton.listeners.click();
await tick(); deliveries.shift()(); await refresh;
assert.equal(assistant.getCaptureDiagnostics().runtime.status, "CAPTURE_DIAGNOSTICS_UNAVAILABLE");
assert.notEqual(assistant.getCaptureDiagnostics().runtime, null, "undefined reply is an explicit error, not provider absence");
assert.equal(diagnosticRequests.length, 5);
assert.deepEqual(diagnosticWorlds, Array.from({ length: 5 }, () => ["MAIN", "ISOLATED"]).flat());
assert.equal(imports, importsBeforeDiagnostic);
assert.equal(backgroundTab.requests(), requestsBeforeDiagnostic);
assert.doesNotMatch(reportText(), /bridgeToken|Cookie|Authorization|another_fixture|fixture_creator/);

globalThis.fetch = savedFetch;
globalThis.chrome = savedChrome;
if (process.argv.includes("--payload")) console.log(JSON.stringify(payload));
else console.log("M8.3-T passive bridge/session/L1-L2-L3/preview/import serializer: PASS");
