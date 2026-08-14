"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const Protocol = require("../chrome_extension/capture/passive_capture_protocol.js");
const MainCapture = require("../chrome_extension/capture/passive_capture_main.js");
const Bridge = require("../chrome_extension/content/passive_capture_bridge.js");

function createCrypto(seed = 1) {
  let next = seed;
  return {
    getRandomValues(bytes) {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = next % 256;
        next += 1;
      }
      return bytes;
    },
  };
}

function createWindow(overrides = {}) {
  const listeners = new Map();
  const target = {
    crypto: createCrypto(),
    location: {
      href: "https://www.tiktok.com/@creator",
      origin: "https://www.tiktok.com",
    },
    messages: [],
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
    postMessage(data, targetOrigin) {
      target.messages.push({ data, targetOrigin });
      target.dispatchMessage(data);
    },
    ...overrides,
  };
  return target;
}

function flushObservers() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function captureMessages(target) {
  return target.messages
    .map((entry) => entry.data)
    .filter((message) => message?.type === Protocol.CAPTURE_TYPE);
}

async function testMatcher() {
  const base = "https://www.tiktok.com/@creator";
  assert.equal(
    Protocol.matchTikTokEndpoint("https://www.tiktok.com/api/post/item_list/?b=2&a=1", base),
    "tiktok_item_list",
  );
  assert.equal(
    Protocol.matchTikTokEndpoint("https://m.tiktok.com/api/user/detail/?a=1&b=2", base),
    "tiktok_user_detail",
  );
  assert.equal(
    Protocol.matchTikTokEndpoint("/api/comment/list/?cursor=1", base),
    "tiktok_comment_list",
  );
  assert.equal(Protocol.matchTikTokEndpoint("https://www.tiktok.com/api/music/list/", base), null);
  assert.equal(
    Protocol.matchTikTokEndpoint("https://www.tiktok.com/other?next=/api/post/item_list/", base),
    null,
  );
  assert.equal(
    Protocol.matchTikTokEndpoint("https://www.tiktok.com/prefix/api/post/item_list/", base),
    null,
  );
  assert.equal(
    Protocol.matchTikTokEndpoint("https://www.not-tiktok.com/api/post/item_list/", base),
    null,
  );
  assert.equal(
    Protocol.matchTikTokEndpoint("https://lookalike-tiktok.com/api/post/item_list/", base),
    null,
  );
  assert.equal(Protocol.matchTikTokEndpoint("not a valid url", "not a valid base"), null);
}

async function testFetchCapture() {
  let originalFetchCalls = 0;
  let cloneCalls = 0;
  let pageReads = 0;
  const rawPayload = {
    transport: "only",
    Authorization: "Bearer secret",
    Cookie: "session=secret",
    headers: { "X-Bogus": "signature" },
    nested: {
      msToken: "secret",
      device_id: "fingerprint",
      safeUrl: "https://www.tiktok.com/@creator/video/123?X-Bogus=secret",
    },
    rawRequest: { credentials: "include" },
    rawResponse: { body: "secret" },
  };
  const originalResponse = {
    bodyUsed: false,
    clone() {
      cloneCalls += 1;
      return { json: async () => structuredClone(rawPayload) };
    },
    async json() {
      pageReads += 1;
      this.bodyUsed = true;
      return { page: "still-readable" };
    },
  };
  const target = createWindow({
    fetch: async () => {
      originalFetchCalls += 1;
      return originalResponse;
    },
  });
  const bridge = Bridge.installIsolatedBridge(target, Protocol);
  const received = [];
  bridge.subscribe((message) => received.push(message));
  assert.equal(MainCapture.installMainWorldCapture(target, Protocol), true);
  assert.equal(MainCapture.installMainWorldCapture(target, Protocol), false);

  const pageResponse = await target.fetch(
    "https://www.tiktok.com/api/post/item_list/?msToken=secret&X-Bogus=signature",
    { method: "POST", headers: { Authorization: "secret" } },
  );
  await flushObservers();

  assert.equal(originalFetchCalls, 1, "the hook must not create an extra fetch");
  assert.equal(cloneCalls, 1);
  assert.strictEqual(pageResponse, originalResponse);
  assert.equal(originalResponse.bodyUsed, false);
  assert.deepEqual(await pageResponse.json(), { page: "still-readable" });
  assert.equal(pageReads, 1);
  assert.equal(received.length, 1);
  assert.equal(captureMessages(target).length, 1);
  assert.equal(received[0].endpointKind, "tiktok_item_list");
  assert.equal(received[0].method, "POST");
  assert.equal(received[0].pathname, "/api/post/item_list/");
  assert.equal(received[0].payload.nested.safeUrl, "/@creator/video/123");

  const serialized = JSON.stringify(received[0]);
  for (const forbidden of [
    "Bearer secret", "session=secret", "Authorization", "Cookie", "headers",
    "credentials", "X-Bogus", "msToken", "device_id", "rawRequest", "rawResponse",
    "https://", "?",
  ]) {
    assert.equal(serialized.includes(forbidden), false, `bridge leaked ${forbidden}`);
  }
  assert.deepEqual(Object.keys(received[0]).sort(), [
    "bridgeToken", "endpointKind", "method", "namespace", "pathname", "payload", "platform", "type",
  ]);

  await target.fetch("https://www.tiktok.com/api/music/list/");
  await flushObservers();
  assert.equal(originalFetchCalls, 2);
  assert.equal(cloneCalls, 1);
  assert.equal(received.length, 1);
}

async function testFetchFailuresPreservePageBehavior() {
  const parseFailureResponse = {
    clone() {
      return { json: async () => { throw new Error("invalid json"); } };
    },
  };
  const target = createWindow({ fetch: async () => parseFailureResponse });
  Bridge.installIsolatedBridge(target, Protocol);
  MainCapture.installMainWorldCapture(target, Protocol);
  assert.strictEqual(
    await target.fetch("https://www.tiktok.com/api/user/detail/"),
    parseFailureResponse,
  );
  await flushObservers();
  assert.equal(captureMessages(target).length, 0);

  const rejected = createWindow({
    fetch: async () => { throw new Error("page network failure"); },
  });
  MainCapture.installMainWorldCapture(rejected, Protocol);
  await assert.rejects(
    rejected.fetch("https://www.tiktok.com/api/user/detail/"),
    /page network failure/,
  );

  const observerFailureResponse = {
    clone() { return { json: async () => ({ safe: true }) }; },
  };
  const observerFailure = createWindow({ fetch: async () => observerFailureResponse });
  MainCapture.installMainWorldCapture(observerFailure, Protocol);
  observerFailure.postMessage = () => { throw new Error("observer failed"); };
  assert.strictEqual(
    await observerFailure.fetch("https://www.tiktok.com/api/comment/list/"),
    observerFailureResponse,
  );
  await flushObservers();
}

class FakeXhr {
  constructor() {
    this.listeners = new Map();
    this.status = 200;
    this.responseType = "";
    this.responseText = "{}";
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }

  open(...args) {
    this.openArgs = args;
    return "open-result";
  }

  send(...args) {
    this.sendArgs = args;
    for (const listener of this.listeners.get("loadend") || []) listener.call(this);
    return "send-result";
  }
}

async function testXhrCapture() {
  const target = createWindow({ XMLHttpRequest: FakeXhr });
  const bridge = Bridge.installIsolatedBridge(target, Protocol);
  const received = [];
  bridge.subscribe((message) => received.push(message));
  assert.equal(MainCapture.installMainWorldCapture(target, Protocol), true);
  assert.equal(MainCapture.installMainWorldCapture(target, Protocol), false);

  const xhr = new target.XMLHttpRequest();
  xhr.responseText = JSON.stringify({ transport: "only" });
  assert.equal(xhr.open("POST", "/api/comment/list/?cursor=1", true), "open-result");
  const body = "cursor=1";
  assert.equal(xhr.send(body), "send-result");
  assert.deepEqual(xhr.openArgs, ["POST", "/api/comment/list/?cursor=1", true]);
  assert.deepEqual(xhr.sendArgs, [body]);
  assert.equal(received.length, 1);
  assert.equal(received[0].endpointKind, "tiktok_comment_list");

  const nonTarget = new target.XMLHttpRequest();
  nonTarget.open("GET", "/api/music/list/");
  nonTarget.send(null);
  assert.equal(received.length, 1);

  const malformed = new target.XMLHttpRequest();
  malformed.responseText = "not-json";
  malformed.open("GET", "/api/user/detail/");
  assert.doesNotThrow(() => malformed.send(null));
  assert.equal(received.length, 1);

  const failed = new target.XMLHttpRequest();
  failed.status = 500;
  failed.responseText = JSON.stringify({ should: "not-capture" });
  failed.open("GET", "/api/user/detail/");
  failed.send(null);
  assert.equal(received.length, 1);

  const aborted = new target.XMLHttpRequest();
  aborted.status = 0;
  aborted.open("GET", "/api/user/detail/");
  aborted.send(null);
  assert.equal(received.length, 1);
}

async function testBridgeValidationAndTokens() {
  const firstToken = Protocol.createBridgeToken(createCrypto(1));
  const secondToken = Protocol.createBridgeToken(createCrypto(2));
  assert.match(firstToken, /^[a-f0-9]{32}$/);
  assert.match(secondToken, /^[a-f0-9]{32}$/);
  assert.notEqual(firstToken, secondToken);

  const target = createWindow();
  const bridge = Bridge.installIsolatedBridge(target, Protocol);
  assert.strictEqual(Bridge.installIsolatedBridge(target, Protocol), bridge);
  const received = [];
  bridge.subscribe((message) => received.push(message));
  target.dispatchMessage(Protocol.createBootstrapEnvelope(firstToken));
  const valid = Protocol.createCaptureEnvelope({
    bridgeToken: firstToken,
    endpointKind: "tiktok_user_detail",
    method: "GET",
    payload: { transport: "only" },
  });
  target.dispatchMessage(valid);
  target.dispatchMessage(valid);
  assert.equal(received.length, 2, "valid events must be independently delivered");

  const forged = [
    { ...valid, bridgeToken: secondToken },
    { ...valid, bridgeToken: undefined },
    { ...valid, namespace: "wrong" },
    { ...valid, namespace: undefined },
    { ...valid, type: "wrong" },
    { ...valid, platform: "instagram" },
    { ...valid, endpointKind: "unsupported" },
    { ...valid, pathname: "/api/post/item_list/" },
    { ...valid, payload: null },
    null,
  ];
  for (const message of forged) target.dispatchMessage(message);
  target.dispatchMessage(valid, { source: {} });
  target.dispatchMessage(valid, { origin: "https://evil.example" });
  assert.equal(received.length, 2);
}

async function testManifestWiring() {
  const manifestPath = path.join(__dirname, "..", "chrome_extension", "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  assert.equal(manifest.version, "0.2.3");
  const isolated = manifest.content_scripts.find((entry) => (
    entry.run_at === "document_start"
    && !entry.world
    && entry.js.includes("content/passive_capture_bridge.js")
  ));
  const main = manifest.content_scripts.find((entry) => (
    entry.run_at === "document_start"
    && entry.world === "MAIN"
    && entry.js.includes("capture/passive_capture_main.js")
  ));
  assert.ok(isolated);
  assert.ok(main);
  const expectedMatches = [
    "https://tiktok.com/*",
    "https://www.tiktok.com/*",
    "https://m.tiktok.com/*",
  ];
  assert.deepEqual(isolated.matches, expectedMatches);
  assert.deepEqual(main.matches, expectedMatches);
  assert.equal(manifest.permissions.includes("webRequest"), false);
}

async function testMainWorldBootIgnoresPageModuleGlobal() {
  const target = createWindow({ module: { exports: {} } });
  target.window = target;
  target.globalThis = target;
  vm.createContext(target);

  const protocolSource = fs.readFileSync(
    path.join(__dirname, "..", "chrome_extension", "capture", "passive_capture_protocol.js"),
    "utf8",
  );
  const mainSource = fs.readFileSync(
    path.join(__dirname, "..", "chrome_extension", "capture", "passive_capture_main.js"),
    "utf8",
  );
  vm.runInContext(protocolSource, target);
  assert.equal(target.__kolconnectPassiveCaptureProtocolScriptV1__, "exposed");
  assert.equal(target.__kolconnectPassiveCaptureProtocolErrorV1__, "");
  vm.runInContext(mainSource, target);

  assert.equal(typeof target.KOLConnectPassiveCaptureProtocol, "object");
  assert.equal(target.__kolconnectPassiveCaptureMainV1__, true);
  assert.equal(target.__kolconnectPassiveCaptureMainScriptV1__, "installed");
  assert.equal(target.__kolconnectPassiveCaptureMainErrorV1__, "");

  const failedTarget = createWindow({ crypto: null, module: { exports: {} } });
  failedTarget.window = failedTarget;
  failedTarget.globalThis = failedTarget;
  vm.createContext(failedTarget);
  vm.runInContext(protocolSource, failedTarget);
  assert.doesNotThrow(() => vm.runInContext(mainSource, failedTarget));
  assert.equal(failedTarget.__kolconnectPassiveCaptureMainV1__, undefined);
  assert.equal(failedTarget.__kolconnectPassiveCaptureMainScriptV1__, "failed");
  assert.equal(failedTarget.__kolconnectPassiveCaptureMainErrorV1__, "Error");

  const protocolFailureTarget = createWindow({ module: { exports: {} } });
  protocolFailureTarget.window = protocolFailureTarget;
  protocolFailureTarget.globalThis = protocolFailureTarget;
  Object.defineProperty(protocolFailureTarget, "KOLConnectPassiveCaptureProtocol", {
    configurable: true,
    set() {
      throw new TypeError("sensitive runtime details must not be exposed");
    },
  });
  vm.createContext(protocolFailureTarget);
  assert.doesNotThrow(() => vm.runInContext(protocolSource, protocolFailureTarget));
  assert.equal(protocolFailureTarget.__kolconnectPassiveCaptureProtocolScriptV1__, "failed");
  assert.equal(protocolFailureTarget.__kolconnectPassiveCaptureProtocolErrorV1__, "TypeError");
  assert.equal(
    protocolFailureTarget.__kolconnectPassiveCaptureProtocolErrorV1__.includes("sensitive"),
    false,
  );

  const missingProtocolTarget = createWindow({ module: { exports: {} } });
  missingProtocolTarget.window = missingProtocolTarget;
  missingProtocolTarget.globalThis = missingProtocolTarget;
  vm.createContext(missingProtocolTarget);
  vm.runInContext(mainSource, missingProtocolTarget);
  assert.equal(
    missingProtocolTarget.__kolconnectPassiveCaptureMainScriptV1__,
    "skipped_protocol_unavailable",
  );
  assert.equal(missingProtocolTarget.__kolconnectPassiveCaptureMainV1__, undefined);

  vm.runInContext(mainSource, target);
  assert.equal(target.__kolconnectPassiveCaptureMainScriptV1__, "skipped_already_installed");
  assert.equal(target.__kolconnectPassiveCaptureMainV1__, true);

  assert.equal(MainCapture.installMainWorldCapture(null, Protocol), false);
}

async function run() {
  await testMatcher();
  await testFetchCapture();
  await testFetchFailuresPreservePageBehavior();
  await testXhrCapture();
  await testBridgeValidationAndTokens();
  await testManifestWiring();
  await testMainWorldBootIgnoresPageModuleGlobal();
  console.log("M3.1 MAIN-world passive capture and bridge foundation: OK");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
