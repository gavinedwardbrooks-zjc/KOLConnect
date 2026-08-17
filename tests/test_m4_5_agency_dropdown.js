"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const EXTENSION = path.join(ROOT, "chrome_extension");
const LOAD_AGENCIES = "KOLCONNECT_NEXT_LOAD_AGENCIES";

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

function createAssistant(agencyResponse) {
  const documentElement = new FakeElement("html");
  const document = {
    documentElement,
    body: new FakeElement("body"),
    getElementById(id) {
      return documentElement.children.find(child => child.id === id) || null;
    },
    createElement(tagName) {
      return tagName === "button" ? new FakeButtonElement(tagName) : new FakeElement(tagName);
    },
    execCommand() { return true; },
  };
  const messages = [];
  const context = vm.createContext({
    document,
    location: { href: "https://www.instagram.com/demo/" },
    navigator: { clipboard: { writeText: async () => {} } },
    chrome: {
      runtime: {
        lastError: null,
        sendMessage(message, callback) {
          messages.push(message);
          callback(message.type === LOAD_AGENCIES ? agencyResponse : { ok: true });
        },
        onMessage: { addListener() {} },
      },
    },
    HTMLButtonElement: FakeButtonElement,
    URL,
    Intl,
    innerWidth: 1440,
    innerHeight: 900,
    setTimeout() { return 1; },
    clearTimeout() {},
    setInterval() { return 1; },
    addEventListener() {},
    console,
  });
  context.window = context;
  for (const relative of [
    "config.js",
    "core/analysis_session.js",
    "core/page_support.js",
    "content/floating_assistant.js",
  ]) {
    vm.runInContext(fs.readFileSync(path.join(EXTENSION, relative), "utf8"), context);
  }
  return { assistant: context.__KOLCONNECT_NEXT_ASSISTANT__, messages };
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
}

async function run() {
  const requests = [];
  global.chrome = { storage: { local: { async get() { return {}; } } } };
  global.fetch = async (url, options = {}) => {
    requests.push({ url: String(url), options });
    return {
      ok: true,
      async json() {
        return { ok: true, agencies: [{ agency_id: "agency_one", name: "North Studio", public_email: "private@example.com" }] };
      },
    };
  };
  const api = await import(pathToFileURL(path.join(EXTENSION, "services", "local_api.js")));
  assert.deepEqual(await api.loadAgencies(), [{ agency_id: "agency_one", name: "North Studio" }]);
  assert.match(requests[0].url, /\/api\/local\/agencies$/);
  assert.equal(requests[0].options.method, "GET");
  const payload = api.buildImportPayload({
    platform: "Instagram",
    profile_url: "https://www.instagram.com/demo/",
    agency_id: "agency_one",
  });
  assert.equal(payload.creator.agency_id, "agency_one");
  assert.equal(Object.hasOwn(payload.creator, "agency_name"), false);

  const success = createAssistant({
    ok: true,
    agencies: [
      { agency_id: "agency_one", name: "North Studio" },
      { agency_id: "agency_two", name: "South Studio" },
    ],
  });
  await flushPromises();
  const select = success.assistant.previewInputs.agency_id;
  assert.equal(success.messages.filter(message => message.type === LOAD_AGENCIES).length, 1);
  assert.deepEqual(select.children.map(item => item.textContent), ["未选择 Agency", "North Studio", "South Studio"]);
  assert.deepEqual(select.children.map(item => item.value), ["", "agency_one", "agency_two"]);

  success.assistant.state.profile = {
    platform: "Instagram",
    profile_url: "https://www.instagram.com/demo/",
    username: "demo",
  };
  success.assistant.initializePreview(success.assistant.state.profile);
  success.assistant.previewInputs.content_category.value = "Lifestyle";
  select.value = "agency_two";
  select.listeners.change();
  await success.assistant.importCurrent();
  const importMessage = success.messages.find(message => message.type === "KOLCONNECT_NEXT_IMPORT");
  assert.equal(importMessage.profile.agency_id, "agency_two");
  assert.equal(Object.hasOwn(importMessage.profile, "agency_name"), false);
  select.value = "";
  select.listeners.change();
  assert.equal(success.assistant.profileForImport().agency_id, "");

  const failed = createAssistant({ ok: false, error: "Agency unavailable" });
  await flushPromises();
  assert.equal(failed.assistant.previewInputs.agency_id.disabled, true);
  assert.match(failed.assistant.agencyStatus.textContent, /暂不可用/);
  failed.assistant.state.profile = {
    platform: "TikTok",
    profile_url: "https://www.tiktok.com/@demo",
    username: "demo",
  };
  failed.assistant.initializePreview(failed.assistant.state.profile);
  failed.assistant.previewInputs.content_category.value = "Gaming";
  await failed.assistant.importCurrent();
  const fallbackImport = failed.messages.find(message => message.type === "KOLCONNECT_NEXT_IMPORT");
  assert.equal(fallbackImport.profile.agency_id, "");

  const sources = [
    "chrome_extension/background.js",
    "chrome_extension/content/floating_assistant.js",
    "chrome_extension/services/local_api.js",
  ].map(relative => fs.readFileSync(path.join(ROOT, relative), "utf8")).join("\n");
  assert.doesNotMatch(sources, /\/api\/agencies/);
  assert.doesNotMatch(sources, /agency_name\s*:/);
  console.log("M4.5 Extension Agency dropdown: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
