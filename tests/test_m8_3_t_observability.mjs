import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { readCaptureDiagnostics } from "../chrome_extension/platform/tiktok.js";

const require = createRequire(import.meta.url);
const Main = require("../chrome_extension/capture/passive_capture_main.js");
const Protocol = require("../chrome_extension/capture/passive_capture_protocol.js");
const Bridge = require("../chrome_extension/content/passive_capture_bridge.js");
const Network = require("../chrome_extension/platform/tiktok_network.js");
const Session = require("../chrome_extension/capture/tiktok_capture_session.js");
const fixture = JSON.parse(readFileSync(new URL("fixtures/tiktok/item_list_normal.json", import.meta.url)));
const tick = () => new Promise(resolve => setImmediate(resolve));
const location = { href: "https://www.tiktok.com/@fixture_creator", origin: "https://www.tiktok.com" };
let receive, fetchCalls = 0, xhrCalls = 0, emitted = 0;
const target = { location, addEventListener: (_type, fn) => { receive = fn; } };
const bridge = Bridge.installIsolatedBridge(target, Protocol, Network);
class Xhr {
  open() { return "opened"; }
  send() { xhrCalls += 1; return "sent"; }
  addEventListener(_event, listener) { this.complete = listener; }
}
const main = { location, crypto: globalThis.crypto, XMLHttpRequest: Xhr,
  postMessage(data) { emitted += 1; receive({ source: target, origin: location.origin, data }); },
  async fetch() { fetchCalls += 1; return { ok: true, clone: () => ({ json: async () => fixture }) }; } };
Main.installMainWorldCapture(main, Protocol);
const control = main.KOLConnectPassiveCaptureControl;
const token = control.token();
bridge.setExpectedToken(token);
await main.fetch("/api/post/item_list/?msToken=DO_NOT_EXPOSE");
await main.fetch("/api/unrelated/");
await tick();
const xhr = new Xhr();
assert.equal(xhr.open("GET", "/api/post/item_list/?cookie=DO_NOT_EXPOSE"), "opened");
assert.equal(xhr.send(), "sent");
xhr.status = 200; xhr.responseType = "json"; xhr.response = fixture; xhr.complete();
assert.equal(control.diagnostics().fetch_interceptions, 2);
assert.equal(control.diagnostics().xhr_interceptions, 1);
assert.equal(control.diagnostics().target_matches, 2);
assert.equal(control.diagnostics().matched_families.tiktok_item_list, 2);
assert.equal(control.diagnostics().matched_families.tiktok_comment_list, 0);
assert.equal(control.diagnostics().envelopes_emitted, 2);
assert.equal(control.diagnostics().fetch_wrapper_current, true);
assert.equal(control.diagnostics().xhr_send_wrapper_current, true);
assert.equal(bridge.diagnostics().parser_success, 2);
assert.equal(bridge.diagnostics().normalized_rows, 4);

const envelope = Protocol.createCaptureEnvelope({ bridgeToken: token, endpointKind: "tiktok_item_list",
  profile: "fixture_creator", observedAt: "2026-09-03T00:00:01Z", payload: fixture });
const dispatch = (data, extra = {}) => receive({ source: target, origin: location.origin, data, ...extra });
dispatch(envelope, { source: {} });
dispatch(envelope, { origin: "https://other.example" });
dispatch({ ...envelope, bridgeToken: "a".repeat(32) });
dispatch({ ...envelope, profile: "invalid/profile?secret" });
bridge.setExpectedToken(null);
dispatch(envelope);
bridge.setExpectedToken(token);
assert.deepEqual(bridge.diagnostics().rejected_reasons, {
  source: 1, origin: 1, token_mismatch: 1, token_unavailable: 1, invalid_envelope: 1, receiver_exception: 0,
});
assert.equal(bridge.diagnostics().parser_invocations, 2, "rejected messages never invoke parser");
dispatch({ ...envelope, payload: {} });
assert.equal(bridge.diagnostics().parser_errors, 1);
assert.equal(bridge.diagnostics().parser_reasons.invalid_payload, 1);
const oldBridgeCounts = bridge.diagnostics();
oldBridgeCounts.rejected_reasons.source = 900;
assert.equal(bridge.diagnostics().rejected_reasons.source, 1);

const throwingTarget = { location, addEventListener: (_event, fn) => { receive = fn; } };
const throwingBridge = Bridge.installIsolatedBridge(throwingTarget, Protocol,
  { parseTikTokItemListResponse() { throw new Error("DO_NOT_EXPOSE"); } }, token);
receive({ source: throwingTarget, origin: location.origin, data: envelope });
assert.equal(throwingBridge.diagnostics().parser_reasons.exception, 1);
assert.doesNotMatch(JSON.stringify(throwingBridge.diagnostics()), /DO_NOT_EXPOSE/);

const session = Session.createSession("fixture_creator", () => Date.parse("2026-09-03T00:02:00Z"));
const rows = Network.parseTikTokItemListResponse(fixture).items;
const ctx = { profile: "fixture_creator", layer: "L1", observedAt: "2026-09-03T00:00:01Z" };
session.add(rows, ctx);
session.add(rows, ctx);
session.add(rows, { ...ctx, profile: "other" });
session.add([rows[0]], { ...ctx, observedAt: "not-a-date" });
session.add([rows[0]], { ...ctx, layer: "invalid" });
session.add([{ ...rows[0], video_id: "bad" }], ctx);
session.add([{ ...rows[0], author_username: "other" }], ctx);
assert.equal(session.diagnostics().accepted_rows, 4);
assert.equal(session.diagnostics().current_l1_rows, 2);
assert.equal(session.diagnostics().l1_rejected_rows, 5);
assert.equal(session.diagnostics().rejected_reasons.layer, 1);
assert.equal(session.diagnostics().l1_rejected_reasons.author_mismatch, 1);
const snapshot = JSON.stringify(session.snapshot());
session.diagnostics().l1_rejected_reasons.author_mismatch = 99;
assert.equal(JSON.stringify(session.snapshot()), snapshot);
session.reset();
session.add(rows, ctx);
assert.equal(session.diagnostics().current_rows, 0);
assert.equal(session.diagnostics().l1_accepted_rows, 4, "cumulative counts survive session resets");
assert.equal(session.diagnostics().l1_rejected_reasons.timestamp, 3);
session.stop("LOGIN_REQUIRED");
session.add(rows, ctx);
assert.equal(session.diagnostics().l1_rejected_reasons.stopped, 2);
const noProfile = Session.createSession(""); noProfile.add(rows, ctx);
assert.equal(noProfile.diagnostics().rejected_reasons.profile_missing, 2);
const full = Session.createSession("fixture_creator");
full.add(Array.from({ length: 202 }, (_, n) => ({ ...rows[0], video_id: String(n) })), ctx);
full.add([{ ...rows[0], video_id: "9999" }], ctx);
assert.equal(full.diagnostics().current_rows, 200);
assert.equal(full.diagnostics().rejected_reasons.batch_limit, 2);
assert.equal(full.diagnostics().rejected_reasons.capacity, 1);

// Hostile/old page diagnostics cannot leak arbitrary strings or turn absent counts into zero.
const savedChrome = globalThis.chrome;
let scriptCalls = 0;
globalThis.chrome = { scripting: { async executeScript({ world }) {
  scriptCalls += 1;
  if (world === "MAIN") return [{ result: { installed: true, token: "DO_NOT_EXPOSE",
    counters: { fetch_interceptions: 2, xhr_interceptions: "DO_NOT_EXPOSE", misses: { secret: token } } } }];
  return [{ result: null }];
} } };
const redacted = await readCaptureDiagnostics(1);
assert.equal(redacted.main.fetch_interceptions, 2);
assert.equal(redacted.main.xhr_interceptions, null);
assert.equal(redacted.runtime.available, false);
assert.doesNotMatch(JSON.stringify(redacted), /DO_NOT_EXPOSE|secret|bridgeToken/);
assert.ok(!JSON.stringify(redacted).includes(token));
assert.equal(scriptCalls, 2);
globalThis.chrome.scripting.executeScript = async () => { throw Error("DO_NOT_EXPOSE"); };
const unavailable = await readCaptureDiagnostics(1);
assert.equal(unavailable.main.available, false);
assert.equal(unavailable.runtime.available, false);
globalThis.chrome = savedChrome;
assert.equal(fetchCalls, 2);
assert.equal(xhrCalls, 1);
assert.equal(emitted, 2, "diagnostic reads never emit/replay bridge messages");
assert.doesNotMatch(JSON.stringify(control.diagnostics()), /DO_NOT_EXPOSE|bridgeToken|itemList/);
assert.ok(!JSON.stringify(control.diagnostics()).includes(token));
control.diagnostics().misses.clone_failed = 999;
assert.equal(control.diagnostics().misses.clone_failed, 0);
const replayTarget = { location, addEventListener: (_event, fn) => { receive = fn; } };
Bridge.installIsolatedBridge(replayTarget, Protocol, Network, token);
// Replay is tested only as an existing explicit operation, never by a diagnostic read.
main.postMessage = data => { emitted += 1; receive({ source: replayTarget, origin: location.origin, data }); };
control.replay();
assert.equal(control.diagnostics().envelopes_replayed, 2);
assert.equal(control.diagnostics().pending_envelopes, 0);
assert.equal(control.diagnostics().envelopes_emitted, 2, "replays are distinct from first emission");
await main.fetch("/api/comment/list/"); await tick();
assert.equal(control.diagnostics().matched_families.tiktok_comment_list, 1);
assert.equal(control.diagnostics().target_matches, 3);
assert.equal(fetchCalls, 3);
main.fetch = () => {};
assert.equal(control.diagnostics().fetch_wrapper_current, false, "observe replacement without repairing it");
console.log("M8.3-T read-only observability counters/redaction/no-side-effects: PASS");
