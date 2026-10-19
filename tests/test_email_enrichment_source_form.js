"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(value = "") {
    this.value = value;
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.textContent = "";
    this.children = [];
    this.options = [];
    this.dataset = {};
  }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.children.push(item); return item; }
  replaceChildren(...items) { this.children = items; this.options = [...items]; }
  add(item) { this.options.push(item); this.children.push(item); }
  addEventListener() {}
}

const ROOT = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(ROOT, "webapp", "index.html"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "webapp", "styles.css"), "utf8");
const elements = new Map([
  ["email-source-task-field", new Element()],
  ["email-platform-field", new Element()],
  ["email-scope-selector", new Element()],
  ["email-manual-source-field", new Element()],
  ["email-source-help", new Element()],
  ["email-source-task", new Element("")],
  ["email-manual-links", new Element()],
  ["email-enrichment-start", new Element()],
  ["email-enrichment-summary", new Element()],
  ["email-enrichment-results", new Element()],
  ["email-enrichment-results-wrap", new Element()],
  ["profile-select", new Element("default")],
]);
const sources = ["creator_library", "url_add"].map(value => ({ value, checked: value === "creator_library" }));
const platforms = ["tiktok", "instagram", "youtube"].map(value => ({ value, checked: value !== "instagram" }));
const scopes = [{ value: "missing", checked: false }, { value: "all", checked: true }];
const gets = [];
const posts = [];

function checked(items) { return items.find(item => item.checked) || null; }
function selectSource(value) {
  const domValue = value === "library" ? "creator_library" : value;
  sources.forEach(item => { item.checked = item.value === domValue; });
}

const sandbox = {
  console,
  URL,
  URLSearchParams,
  Option: class { constructor(text, value) { this.text = text; this.value = value; } },
  document: {
    getElementById: id => elements.get(id) || null,
    createElement: () => new Element(),
    querySelector: selector => {
      if (selector === 'input[name="email-source"]:checked') return checked(sources);
      if (selector === 'input[name="email-scope"]:checked') return checked(scopes);
      return null;
    },
    querySelectorAll: selector => {
      if (selector === ".email-platform-option:checked") return platforms.filter(item => item.checked);
      return [];
    },
  },
  window: {
    addEventListener: () => {},
    localStorage: { getItem: () => "", setItem: () => {} },
    KOLConnectI18n: { register: () => {}, t: key => key },
    KOLConnectAPI: {
      get: async url => {
        gets.push(url);
        return { candidates: [{ platform: "TikTok", profile_url: "https://www.tiktok.com/@demo" }], scanned_accounts: 1, candidate_count: 1, missing_email_count: 1 };
      },
      post: async (url, payload) => {
        posts.push({ url, payload });
        return {};
      },
    },
  },
};
sandbox.globalThis = sandbox;

const source = fs.readFileSync(path.join(ROOT, "webapp", "app.js"), "utf8") + `
globalThis.__emailForm = {
  state,
  renderEmailSourceControls,
  buildEmailEnrichmentRequest,
  emailEnrichmentScanPayload,
  emailEnrichmentBackendSource,
  renderEmailTaskOptions,
  previewEmailEnrichment,
  startEmailEnrichment,
};`;
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: "app.js" });
const api = sandbox.__emailForm;

function assertVisibility(sourceValue, expected) {
  selectSource(sourceValue);
  api.renderEmailSourceControls();
  assert.equal(elements.get("email-source-task-field").hidden, !expected.task);
  assert.equal(elements.get("email-platform-field").hidden, !expected.platform);
  assert.equal(elements.get("email-scope-selector").hidden, !expected.scope);
  assert.equal(elements.get("email-manual-source-field").hidden, !expected.manual);
}

(async () => {
  assert.match(html, /id="email-source-help"/);
  assert.equal((html.match(/name="email-source"/g) || []).length, 2);
  assert.match(html, />从达人库选择</);
  assert.match(html, />通过链接添加达人并补邮箱</);
  assert.match(html, /新识别的达人会自动加入达人库/);
  assert.doesNotMatch(html, /临时补邮箱/);
  assert.doesNotMatch(html, /value="task"|value="review_results"|value="manual"|value="temporary"/);
  assert.match(source, /emailStatusLabel\(item\.status, item\.reason_code\)/);
  assert.match(source, /reason_code:\s*data\.reason_code/);
  assert.match(source, /BROWSER_START_FAILED:[\s\S]*PROFILE_AUTH_REQUIRED:[\s\S]*SCRAPE_TIMEOUT:/);
  assert.match(css, /#email-source-task-field\[hidden\][\s\S]*#email-manual-source-field\[hidden\][^{]*\{\s*display:\s*none;/);
  assertVisibility("library", { task: true, platform: true, scope: true, manual: false });
  assertVisibility("url_add", { task: false, platform: true, scope: false, manual: true });

  api.state.tasks = [{ id: "task-old", name: "Previous capture", task_type: "scrape", total_links: 2 }];
  elements.get("email-source-task").value = "";
  api.renderEmailTaskOptions();
  assert.equal(elements.get("email-source-task").options[0].value, "", "All tasks must be the default task filter");
  assert.equal(elements.get("email-source-task").options[0].text, "emailAllTasks");

  elements.get("email-manual-links").value = [
    "https://www.tiktok.com/@demo",
    "https://www.instagram.com/ignored/",
    "not-a-url",
  ].join("\n");
  let request = api.buildEmailEnrichmentRequest();
  assert.deepEqual(JSON.parse(JSON.stringify(request)), {
    source: "url_add",
    platforms: ["tiktok", "youtube"],
    links: [{ profile_url: "https://www.tiktok.com/@demo", platform: "tiktok" }],
  });
  assert.equal("taskId" in request, false, "hidden stale task must not enter manual request");
  assert.equal("missingOnly" in request, false, "hidden scope must not enter manual request");

  await api.previewEmailEnrichment();
  elements.get("email-manual-links").value = "https://www.youtube.com/@changed-after-preview";
  platforms[0].checked = false;
  platforms[1].checked = true;
  await api.startEmailEnrichment();
  assert.deepEqual(JSON.parse(JSON.stringify(posts[0])), {
    url: "/api/creator-library/email-capture",
    payload: { url: "https://www.tiktok.com/@demo" },
  }, "URL-add Start must use the preview snapshot and existing persistence-capable endpoint");
  posts.length = 0;

  selectSource("library");
  platforms[0].checked = true;
  platforms[1].checked = false;
  elements.get("email-source-task").value = "";
  request = api.buildEmailEnrichmentRequest();
  assert.equal(request.taskId, "", "All tasks uses an empty optional filter");
  assert.equal(request.missingOnly, false);
  assert.equal(api.emailEnrichmentBackendSource(request), "creator_library");

  scopes[0].checked = true;
  scopes[1].checked = false;
  request = api.buildEmailEnrichmentRequest();
  assert.equal(request.missingOnly, true, "missing-email capability remains a library scope filter");
  scopes[0].checked = false;
  scopes[1].checked = true;

  elements.get("email-source-task").value = "task-old";
  request = api.buildEmailEnrichmentRequest();
  assert.equal(request.taskId, "task-old");
  assert.equal(api.emailEnrichmentBackendSource(request), "task", "recent-capture capability is an optional library filter");

  await api.previewEmailEnrichment();
  assert.match(gets.at(-1), /source=task/);
  assert.match(gets.at(-1), /task_id=task-old/);
  assert.match(gets.at(-1), /missing_only=false/);

  elements.get("email-source-task").value = "stale-after-preview";
  platforms[0].checked = false;
  platforms[1].checked = true;
  await assert.rejects(api.startEmailEnrichment(), /emailNoCandidates/);
  assert.deepEqual(JSON.parse(JSON.stringify(posts[0])), {
    url: "/api/tasks/email-recheck/scan",
    payload: { source: "task", platforms: ["tiktok", "youtube"], missing_only: false, task_id: "task-old" },
  }, "Start must use the exact preview snapshot rather than changed controls");

  selectSource("url_add");
  platforms.forEach(item => { item.checked = false; });
  assert.throws(() => api.buildEmailEnrichmentRequest(), /scrapeSelectPlatform/);

  console.log("Email enrichment source-driven form tests passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
