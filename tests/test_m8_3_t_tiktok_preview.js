"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const Network = require("../chrome_extension/platform/tiktok_network.js");
const Session = require("../chrome_extension/capture/tiktok_capture_session.js");
const ROOT = path.resolve(__dirname, "../chrome_extension");
class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {};
    this.style = {}; this.dataset = {}; this.textContent = ""; this.value = "";
    this.classList = { toggle() {} };
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  getBoundingClientRect() { return { left: 0, top: 0 }; }
  setPointerCapture() {}
}
class Button extends Element {}
async function run() {
  const html = new Element("html");
  const sent = [];
  const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/tiktok/item_list_normal.json"), "utf8"));
  const session = Session.createSession("creator");
  session.add(Network.parseTikTokItemListResponse(fixture).items, {
    profile: "creator", layer: "L1", observedAt: "2026-09-03T00:00:00Z",
  });
  let fail = false;
  let diagnosticsFail = false;
  const runtimeDiagnostics = { main: { installed: true, fetch_interceptions: 4 },
    runtime: { bridge: { accepted: 0 }, session: { current_l1_rows: 0 } } };
  const context = vm.createContext({
    document: { documentElement: html, body: new Element("body"),
      getElementById: id => html.children.find(child => child.id === id),
      createElement: tag => tag === "button" ? new Button(tag) : new Element(tag) },
    location: { href: "https://www.tiktok.com/@creator" },
    navigator: { clipboard: { writeText: async () => {} } },
    chrome: { runtime: { lastError: null, onMessage: { addListener() {} }, sendMessage(message, callback) {
      sent.push(message);
      if (message.type === "KOLCONNECT_PASSIVE_DIAGNOSTICS") callback(diagnosticsFail
        ? { ok: false, error: "secret-error-not-for-display" } : { ok: true, diagnostics: runtimeDiagnostics });
      else if (message.type === "KOLCONNECT_NEXT_ANALYZE_CONTENT") callback(fail ? { ok: true, session_id: message.session_id,
        analysis: { contents: [], returned_count: 0, capture_status: "failed", error: "CAPTCHA_DETECTED" } }
        : { ok: true, session_id: message.session_id, analysis: { contents: session.snapshot().items, returned_count: 2,
          passive_capture_status: "CAPTURE_L1_ACTIVE", capture_status: "partial_success",
          capture_diagnostics: { bridge_connected: true, parser_error: false } } });
      else callback({ ok: true, agencies: [] });
    } } },
    HTMLButtonElement: Button, URL, Intl, console, innerWidth: 1400, innerHeight: 900,
    setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, addEventListener() {},
  });
  context.window = context;
  for (const file of ["config.js", "core/analysis_session.js", "core/page_support.js", "content/floating_assistant.js"]) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, file), "utf8"), context);
  }
  const ui = context.__KOLCONNECT_NEXT_ASSISTANT__;
  assert.equal(ui.state.contentAnalysis, null);
  const beforeRefresh = sent.length;
  await ui.refreshCaptureDiagnostics();
  assert.equal(sent.length, beforeRefresh + 1);
  assert.equal(sent.at(-1).type, "KOLCONNECT_PASSIVE_DIAGNOSTICS");
  assert.equal(ui.state.contentAnalysis, null, "diagnostics must not fabricate analysis");
  assert.equal(ui.getCaptureDiagnostics().runtime.main.fetch_interceptions, 4);
  ui.getCaptureDiagnostics().runtime.main.fetch_interceptions = 999;
  assert.equal(ui.getCaptureDiagnostics().runtime.main.fetch_interceptions, 4, "defensive read snapshot");
  ui.state.profile = { platform: "TikTok", username: "creator", creator_name: "Fixture", profile_url: context.location.href, content_category: "Gaming", diagnostic_report: {} };
  ui.initializePreview(ui.state.profile);
  await ui.analyzeContent();
  assert.ok(ui.state.contentAnalysis, "exposed state is live after completed analysis");
  assert.equal(ui.state.profile.diagnostic_report.content_analysis.capture_diagnostics.bridge_connected, true);
  const walk = node => [node, ...node.children.flatMap(walk)];
  const text = () => walk(html).map(node => node.textContent).join("\n");
  const imports = () => sent.filter(message => message.type === "KOLCONNECT_NEXT_IMPORT");
  assert.equal(imports().length, 0, "preview must never auto-import");
  assert.match(text(), /L1 被动网络采集/);
  assert.match(text(), /来源 L1/);
  assert.match(text(), /high/);
  assert.match(text(), /2026-09-03T00:00:00Z/);
  assert.match(text(), /刷新 TikTok 诊断（只读）/);
  const analysisBefore = JSON.stringify(ui.state.contentAnalysis);
  await ui.refreshCaptureDiagnostics();
  assert.equal(JSON.stringify(ui.state.contentAnalysis), analysisBefore);
  diagnosticsFail = true;
  await ui.refreshCaptureDiagnostics();
  assert.match(text(), /CAPTURE_DIAGNOSTICS_UNAVAILABLE/);
  assert.doesNotMatch(text(), /secret-error-not-for-display/);
  await ui.importCurrent();
  assert.equal(imports().length, 1);
  assert.equal(imports()[0].profile.videos.length, 2);
  assert.equal(imports()[0].profile.videos[0].field_provenance.views.layer, "L1");
  fail = true;
  await ui.analyzeContent();
  assert.equal(ui.state.profile.videos.length, 0, "failed capture clears stale video preview");
  assert.match(text(), /CAPTCHA_DETECTED/);
  const reset = walk(html).find(node => node.textContent === "重新开始 TikTok 被动采集");
  assert.equal(reset.hidden, false);
  await reset.listeners.click();
  assert.ok(sent.some(message => message.type === "KOLCONNECT_PASSIVE_RESET"));
  assert.equal(imports().length, 1, "reset must not import");
  assert.equal(ui.state.profile.videos.length, 0);
  console.log("M8.3-T TikTok preview/provenance/explicit import/reset/error UI: PASS");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
