const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const EXTENSION = path.join(ROOT, "chrome_extension");

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
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

(async () => {
  const requests = [];
  global.chrome = {
    storage: { local: { async get() { return {}; } } }
  };
  global.fetch = async (_url, options) => {
    requests.push(JSON.parse(options.body));
    return { ok: true, async json() { return { ok: true }; } };
  };

  const api = await import(pathToFileURL(path.join(EXTENSION, "services", "local_api.js")));
  const common = await import(pathToFileURL(path.join(EXTENSION, "platform", "common.js")));
  assert.deepEqual([...api.CONTENT_CATEGORY_OPTIONS], [
    "Gaming", "Lifestyle", "Beauty", "Tech", "Comedy", "Education",
    "Music", "Sports", "Travel", "Food", "News", "Other"
  ]);

  const profile = {
    platform: "Instagram",
    profile_url: "https://www.instagram.com/demo/",
    username: "@demo",
    creator_name: "Demo Creator",
    followers: "12000",
    bio: "Public bio",
    email: "creator@example.com",
    whatsapp: "+5511999999999",
    country: "Brazil",
    language: "Portuguese",
    language_source: "structured_data",
    content_category: "Lifestyle",
    note: "Keep existing fields",
    capture_status: "success",
    analysis_url: "https://www.instagram.com/demo/"
  };
  const fixedNow = new Date("2026-08-07T00:00:00.000Z");
  const payload = api.buildImportPayload(profile, fixedNow);
  assert.equal(payload.creator.email, "creator@example.com");
  assert.equal(payload.creator.whatsapp, "+5511999999999");
  assert.equal(payload.creator.country, "Brazil");
  assert.equal(payload.creator.language, "Portuguese");
  assert.equal(payload.content_category, "Lifestyle");
  assert.equal(payload.creator.creator_name, "Demo Creator");
  assert.equal(payload.creator.followers, "12000");
  assert.equal(payload.creator.profile_url, profile.profile_url);
  assert.equal(payload.note, "Keep existing fields");
  assert.equal(payload.analysis.capture_status, "success");

  const emptyOptional = api.buildImportPayload({
    platform: "TikTok",
    profile_url: "https://www.tiktok.com/@empty",
    username: "@empty",
    content_category: "Other"
  }, fixedNow);
  assert.equal(emptyOptional.creator.email, "");
  assert.equal(emptyOptional.creator.whatsapp, "");
  assert.equal(emptyOptional.creator.country, "");
  assert.equal(emptyOptional.creator.language, "");
  assert.deepEqual(
    api.validateImportProfile({ ...profile, content_category: "" }),
    ["Content Category"]
  );
  assert.deepEqual(api.validateImportProfile(profile), []);

  const publicResult = {
    fields: {},
    public_profile: {
      email_candidates: [{ source: "profile_dom", value: "Contact creator@example.com" }],
      whatsapp_candidates: [{ source: "profile_dom", value: "https://wa.me/5511999999999" }],
      country_candidates: [{ source: "structured_data", value: "Brazil" }],
      language_candidates: [{ source: "structured_data", value: "Portuguese" }]
    }
  };
  common.applyPublicProfileFields(publicResult);
  assert.equal(publicResult.fields.email.value, "creator@example.com");
  assert.equal(publicResult.fields.whatsapp.value, "+5511999999999");
  assert.equal(publicResult.fields.country.value, "Brazil");
  assert.equal(publicResult.fields.language.value, "Portuguese");
  const noGuess = {
    fields: {},
    public_profile: {
      email_candidates: [{ source: "profile_dom", value: "Brazilian creator" }],
      whatsapp_candidates: [{ source: "profile_dom", value: "+55 11 99999-9999" }],
      country_candidates: [],
      language_candidates: []
    }
  };
  common.applyPublicProfileFields(noGuess);
  assert.equal(noGuess.fields.email.value, null);
  assert.equal(noGuess.fields.whatsapp.value, null);
  assert.equal(noGuess.fields.country.value, null);
  assert.equal(noGuess.fields.language.value, null);

  const documentElement = new FakeElement("html");
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
  const sentMessages = [];
  const context = vm.createContext({
    document,
    location: { href: "https://www.instagram.com/demo/" },
    navigator: { clipboard: { writeText: async () => {} } },
    chrome: {
      runtime: {
        lastError: null,
        sendMessage(message, callback) {
          sentMessages.push(message);
          callback({ ok: true });
        },
        onMessage: { addListener() {} }
      }
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
    console
  });
  context.window = context;
  for (const relative of [
    "config.js",
    "core/analysis_session.js",
    "core/page_support.js",
    "content/floating_assistant.js"
  ]) {
    vm.runInContext(readFileSync(path.join(EXTENSION, relative), "utf8"), context);
  }
  const assistant = context.__KOLCONNECT_NEXT_ASSISTANT__;
  assistant.state.profile = { ...profile, content_category: "" };
  assistant.initializePreview(assistant.state.profile);
  assert.equal(assistant.previewInputs.email.value, "creator@example.com");
  assert.equal(assistant.previewInputs.content_category.value, "");
  await assistant.importCurrent();
  assert.equal(sentMessages.length, 0, "category validation must block import");

  assistant.previewInputs.email.value = "edited@example.com";
  assistant.previewInputs.whatsapp.value = "+5511888888888";
  assistant.previewInputs.country.value = "BR";
  assistant.previewInputs.language.value = "pt-BR";
  assistant.previewInputs.content_category.value = "Gaming";
  assistant.previewInputs.content_category.listeners.change();
  await assistant.importCurrent();
  assert.equal(sentMessages.length, 1);
  assert.equal(sentMessages[0].profile.email, "edited@example.com");
  assert.equal(sentMessages[0].profile.whatsapp, "+5511888888888");
  assert.equal(sentMessages[0].profile.country, "BR");
  assert.equal(sentMessages[0].profile.language, "pt-BR");
  assert.equal(sentMessages[0].profile.content_category, "Gaming");

  await api.importProfile(profile);
  await api.importProfile(profile);
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[0].creator, requests[1].creator);
  assert.equal(requests[0].content_category, requests[1].content_category);

  console.log("M1-B1b extension payload, preview, validation, and import tests passed.");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
