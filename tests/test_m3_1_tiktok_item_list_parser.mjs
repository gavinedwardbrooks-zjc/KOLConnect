import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

import { contentItem } from "../chrome_extension/core/content_analysis.js";

const require = createRequire(import.meta.url);
const Network = require("../chrome_extension/platform/tiktok_network.js");
const Protocol = require("../chrome_extension/capture/passive_capture_protocol.js");
const Bridge = require("../chrome_extension/content/passive_capture_bridge.js");
const fixtureUrl = new URL("./fixtures/tiktok/item_list_normal.json", import.meta.url);
const fixtureText = readFileSync(fixtureUrl, "utf8");
const fixture = JSON.parse(fixtureText);

function clone(value) {
  return structuredClone(value);
}

function createWindow() {
  const listeners = new Map();
  const target = {
    location: {
      href: "https://www.tiktok.com/@fixture",
      origin: "https://www.tiktok.com",
    },
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(listener);
    },
    dispatchMessage(data, options = {}) {
      const event = {
        data,
        origin: options.origin ?? target.location.origin,
        source: options.source ?? target,
      };
      for (const listener of listeners.get("message") || []) listener(event);
    },
    postMessage(data) {
      target.dispatchMessage(data);
    },
  };
  return target;
}

function assertField(field, value, sourcePath) {
  assert.equal(field.value, value);
  assert.equal(field.source, Network.SOURCE);
  assert.equal(field.confidence, "high");
  assert.equal(field.missing_reason, "");
  assert.equal(field.source_path, sourcePath);
}

// Sanitized structure-preserving copy of a manually captured page-generated
// TikTok /api/post/item_list/ response. Negative variants below are synthetic.
assert.ok(Array.isArray(fixture.itemList));
assert.ok(fixture.itemList.length >= 2);
for (const item of fixture.itemList) {
  assert.equal(typeof item.id, "string");
  assert.match(item.id, /^738123456789012345[67]$/);
  assert.equal(typeof item.createTime, "number");
  assert.equal(typeof item.desc, "string");
  assert.equal(typeof item.textLanguage, "string");
  for (const key of ["collectCount", "commentCount", "diggCount", "playCount", "shareCount"]) {
    assert.equal(typeof item.stats[key], "number");
    assert.equal(typeof item.statsV2[key], "string");
  }
}
const fixtureLower = fixtureText.toLowerCase();
for (const forbidden of [
  "http://", "https://", "secuid", "author", "userid", "signature", "x-bogus",
  "mstoken", "logid", "cookie", "authorization", "headers", "?",
]) {
  assert.equal(fixtureLower.includes(forbidden), false, `fixture contains ${forbidden}`);
}

const parsed = Network.parseTikTokItemListResponse(fixture);
assert.equal(parsed.diagnostic.status, "success");
assert.equal(parsed.diagnostic.input_count, 2);
assert.equal(parsed.diagnostic.parsed_count, 2);
assert.equal(parsed.metadata.cursor, "30");
assert.equal(parsed.metadata.has_more, true);

const first = parsed.items[0];
assert.equal(first.video_id, "7381234567890123456");
assert.equal(first.video_id.length, 19);
assert.equal(first.video_id_provenance.source, Network.SOURCE);
assert.equal(first.video_id_provenance.confidence, "high");
assert.equal(first.video_id_provenance.source_path, "id");
assert.equal(first.title, "Fixture video one");
assert.equal(first.title_provenance.source, Network.SOURCE);
assert.equal(first.title_provenance.confidence, "high");
assert.equal(first.title_provenance.missing_reason, "");
assert.equal(first.title_provenance.source_path, "desc");
assert.equal("description" in first, false, "parser must not invent a non-canonical alias");
assertField(first.views, 9000, "stats.playCount");
assertField(first.likes, 678, "stats.diggCount");
assertField(first.comments, 45, "stats.commentCount");
assertField(first.shares, 12, "stats.shareCount");
assertField(first.published_at, "2023-11-14T22:13:20.000Z", "createTime");
assert.equal(first.published_at.raw_text, "1700000000");
assert.equal(first.published_at.is_estimated, false);
assert.equal(first.is_pinned, null);

const zero = parsed.items[1];
for (const field of [zero.views, zero.likes, zero.comments, zero.shares]) {
  assert.equal(field.value, 0, "a real zero must remain zero");
  assert.equal(field.confidence, "high");
}
assert.equal(zero.is_pinned, null, "list position must not imply pinned status");

const fallbackPayload = clone(fixture);
const fallbackItem = fallbackPayload.itemList[0];
delete fallbackItem.stats.playCount;
fallbackItem.stats.diggCount = null;
fallbackItem.stats.commentCount = -1;
fallbackItem.stats.shareCount = "invalid";
fallbackItem.statsV2.playCount = "432900";
fallbackItem.statsV2.diggCount = "154";
fallbackItem.statsV2.commentCount = "45";
fallbackItem.statsV2.shareCount = "12";
const fallback = Network.parseTikTokItemListResponse(fallbackPayload).items[0];
assertField(fallback.views, 432900, "statsV2.playCount");
assertField(fallback.likes, 154, "statsV2.diggCount");
assertField(fallback.comments, 45, "statsV2.commentCount");
assertField(fallback.shares, 12, "statsV2.shareCount");

const preferredPayload = clone(fixture);
preferredPayload.itemList[0].stats.playCount = 111;
preferredPayload.itemList[0].statsV2.playCount = "999";
assertField(
  Network.parseTikTokItemListResponse(preferredPayload).items[0].views,
  111,
  "stats.playCount",
);

for (const invalid of ["12.5", "1e9", "12K", "-1", "abc", "", {}, null]) {
  const invalidPayload = clone(fixture);
  invalidPayload.itemList[0].stats.playCount = invalid;
  invalidPayload.itemList[0].statsV2.playCount = invalid;
  const field = Network.parseTikTokItemListResponse(invalidPayload).items[0].views;
  assert.equal(field.value, null);
  assert.equal(field.confidence, "missing");
  assert.equal(field.missing_reason, "invalid_value");
}

const missingPayload = clone(fixture);
delete missingPayload.itemList[0].stats.playCount;
delete missingPayload.itemList[0].statsV2.playCount;
const missingViews = Network.parseTikTokItemListResponse(missingPayload).items[0].views;
assert.equal(missingViews.value, null);
assert.equal(missingViews.missing_reason, "field_absent");

for (const invalidId of [undefined, null, "", 7381234567890123456]) {
  const payload = clone(fixture);
  payload.itemList = [{ ...payload.itemList[0], id: invalidId }];
  assert.equal(Network.parseTikTokItemListResponse(payload).items.length, 0);
}

for (const [desc, reason] of [["", "empty_value"], [undefined, "field_absent"], [{}, "invalid_value"]]) {
  const payload = clone(fixture);
  if (desc === undefined) delete payload.itemList[0].desc;
  else payload.itemList[0].desc = desc;
  const item = Network.parseTikTokItemListResponse(payload).items[0];
  assert.equal(item.title, null);
  assert.equal(item.title_provenance.missing_reason, reason);
}

const stringTime = clone(fixture);
stringTime.itemList[0].createTime = "1700000000";
assertField(
  Network.parseTikTokItemListResponse(stringTime).items[0].published_at,
  "2023-11-14T22:13:20.000Z",
  "createTime",
);
for (const invalidTime of [undefined, -1, "12.5", "abc", {}]) {
  const payload = clone(fixture);
  if (invalidTime === undefined) delete payload.itemList[0].createTime;
  else payload.itemList[0].createTime = invalidTime;
  assert.equal(Network.parseTikTokItemListResponse(payload).items[0].published_at.value, null);
}

const dedupePayload = clone(fixture);
const duplicateFirst = clone(dedupePayload.itemList[0]);
delete duplicateFirst.stats.diggCount;
delete duplicateFirst.statsV2.diggCount;
const duplicateLater = clone(dedupePayload.itemList[0]);
delete duplicateLater.stats.playCount;
delete duplicateLater.statsV2.playCount;
duplicateLater.stats.diggCount = 777;
dedupePayload.itemList = [duplicateFirst, duplicateLater];
const deduped = Network.parseTikTokItemListResponse(dedupePayload);
assert.equal(deduped.items.length, 1);
assert.equal(deduped.diagnostic.duplicate_count, 1);
assert.equal(deduped.items[0].views.value, 9000, "missing duplicate must not erase valid data");
assert.equal(deduped.items[0].likes.value, 777, "later valid data fills a missing field");

for (const malformed of [null, [], {}, { itemList: {} }, { error: "blocked" }]) {
  const result = Network.parseTikTokItemListResponse(malformed);
  assert.deepEqual(result.items, []);
  assert.equal(result.diagnostic.status, "invalid_payload");
}
assert.equal(Network.parseTikTokItemListResponse({ itemList: [] }).diagnostic.status, "success");

const withUnknownFields = clone(fixture);
withUnknownFields.itemList[0].signedMediaUrl = "https://cdn.example/signed?token=secret";
const unknownIgnored = Network.parseTikTokItemListResponse(withUnknownFields).items[0];
assert.equal("signedMediaUrl" in unknownIgnored, false);

const canonical = contentItem(first);
assert.equal(canonical.shares.value, 12);
assert.equal(canonical.shares.source, Network.SOURCE);
assert.equal(canonical.engagement_rate.value, ((678 + 45) / 9000) * 100);

const target = createWindow();
let parserInvocations = 0;
const parserSpy = {
  parseTikTokItemListResponse(payload) {
    parserInvocations += 1;
    return Network.parseTikTokItemListResponse(payload);
  },
};
const bridge = Bridge.installIsolatedBridge(target, Protocol, parserSpy);
const received = [];
bridge.subscribeItemList((result) => received.push(result));
const token = "0123456789abcdef0123456789abcdef";
target.dispatchMessage(Protocol.createBootstrapEnvelope(token));
const validEnvelope = Protocol.createCaptureEnvelope({
  bridgeToken: token,
  endpointKind: "tiktok_item_list",
  method: "GET",
  payload: fixture,
});
target.dispatchMessage(validEnvelope);
assert.equal(parserInvocations, 1);
assert.equal(received.length, 1);
assert.equal(received[0].items.length, 2);

target.dispatchMessage({ ...validEnvelope, bridgeToken: "ffffffffffffffffffffffffffffffff" });
target.dispatchMessage(validEnvelope, { source: {} });
target.dispatchMessage(validEnvelope, { origin: "https://evil.example" });
target.dispatchMessage({ ...validEnvelope, namespace: "wrong" });
target.dispatchMessage({ ...validEnvelope, type: "wrong" });
target.dispatchMessage({ ...validEnvelope, endpointKind: "unsupported" });
target.dispatchMessage({ ...validEnvelope, payload: null });
target.dispatchMessage(null);
const userDetailEnvelope = Protocol.createCaptureEnvelope({
  bridgeToken: token,
  endpointKind: "tiktok_user_detail",
  method: "GET",
  payload: fixture,
});
target.dispatchMessage(userDetailEnvelope);
assert.equal(parserInvocations, 1, "forged and non-item-list messages must not invoke the parser");

const parserFailureTarget = createWindow();
const parserFailureBridge = Bridge.installIsolatedBridge(parserFailureTarget, Protocol, {
  parseTikTokItemListResponse() {
    throw new Error("parser failure");
  },
});
let rawCaptureCount = 0;
parserFailureBridge.subscribe(() => { rawCaptureCount += 1; });
parserFailureTarget.dispatchMessage(Protocol.createBootstrapEnvelope(token));
assert.doesNotThrow(() => parserFailureTarget.dispatchMessage(validEnvelope));
assert.equal(rawCaptureCount, 1, "parser failure must not block validated transport consumers");

const parserSource = readFileSync(
  new URL("../chrome_extension/platform/tiktok_network.js", import.meta.url),
  "utf8",
);
for (const forbidden of ["fetch(", "XMLHttpRequest", "fetchTikTokContentDetail", "chrome.", "window.", "document."]) {
  assert.equal(parserSource.includes(forbidden), false, `parser contains active dependency ${forbidden}`);
}

const manifest = JSON.parse(readFileSync(
  new URL("../chrome_extension/manifest.json", import.meta.url),
  "utf8",
));
const isolatedScripts = manifest.content_scripts.find((entry) => (
  entry.run_at === "document_start" && !entry.world && entry.js.includes("content/passive_capture_bridge.js")
)).js;
assert.ok(
  isolatedScripts.indexOf("platform/tiktok_network.js")
    < isolatedScripts.indexOf("content/passive_capture_bridge.js"),
  "the isolated parser must load before bridge wiring",
);
assert.equal(manifest.version, "0.2.3");

console.log("M3.1 TikTok item_list sanitized fixture, parser, and bridge integration: OK");
