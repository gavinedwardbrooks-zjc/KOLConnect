"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor() { this.children = []; this.dataset = {}; this.textContent = ""; this.listeners = {}; this.classList = { toggle() {}, add() {} }; }
  replaceChildren(...children) { this.children = children; }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); }
  setAttribute() {}
  closest() { return this; }
  get text() { return this.textContent + this.children.map(child => child.text).join(" "); }
}

async function run() {
  const ids = ["creator-library-detail-similar", "creator-library-similar-results", "creator-library-similar-card", "creator-library-similar-status"];
  const elements = new Map(ids.map(id => [id, new Element()]));
  let page;
  let response = { total: 1, candidates: [{ creator_id: "candidate", creator_name: "<script>remote</script>",
    base_similarity_score: 87.25, available_nominal_weight: 75,
    why_recommended: [{ id: "tag", text: "人工标签：gaming" }],
    unavailable_dimensions: ["price", "engagement"],
    dimensions: { country_language: { evidence: { unavailable: ["language"] } } },
  }] };
  const calls = [], navigations = [];
  const document = { getElementById: id => elements.get(id) || null, querySelectorAll: () => [], createElement: () => new Element() };
  const window = {
    KOLConnectPages: { registerPage(name, value) { page = value; } },
    KOLConnectCreatorCampaignModal: { create: () => ({ bind() {}, destroy() {} }) },
  };
  const context = {
    params: { creatorId: "source" }, state: { creatorLibrary: {} },
    resources: { signal: new AbortController().signal, createAbortController: () => new AbortController(),
      listen(el, type, fn) { el.listeners[type] = fn; }, cleanup() {} },
    api: { async get(url) {
      calls.push(url);
      if (url.endsWith("/similar")) return typeof response === "function" ? response() : response;
      if (url === "/api/creator-library/source") return { record: { creator_id: "source", creator_name: "source" } };
      if (url.startsWith("/api/campaigns?")) return { campaigns: [] };
      throw new Error("Unexpected URL " + url);
    } },
    async navigate(...args) { navigations.push(args); }, ui: { showError(error) { throw error; } },
  };
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, "../webapp/pages/creator-library-detail.js"), "utf8"),
    { window, document, AbortController, URL, console });
  await page.load(context);
  page.bind();
  const click = () => elements.get("creator-library-detail-similar").listeners.click();
  assert.equal(calls.some(url => url.endsWith("/similar")), false);
  await click();
  const results = elements.get("creator-library-similar-results");
  assert.match(results.text, /87\.25%/);
  assert.match(results.text, /人工标签：gaming/);
  assert.match(results.text, /未纳入评分：报价、互动率/);
  assert.match(results.text, /国家\/语言缺项：语言/);
  assert.equal(results.children[0].children[0].children[0].textContent, "<script>remote</script>");
  const button = results.children[0].children[1];
  elements.get("creator-library-similar-results").listeners.click({ target: button });
  assert.equal(navigations[0][0], "creator-library-detail");
  assert.equal(navigations[0][1].creatorId, "candidate");
  response.candidates[0].base_similarity_score = null;
  await click();
  assert.match(results.text, /相似度 --/);
  response = { total: 0, candidates: [] };
  await click();
  assert.match(results.text, /暂无/);
  response = () => { throw new Error("retryable failure"); };
  await click();
  assert.match(elements.get("creator-library-similar-status").text, /retryable failure/);
  let finish;
  response = () => new Promise(resolve => { finish = resolve; });
  const pending = click();
  page.unbind();
  finish({ total: 1, candidates: [{ creator_name: "stale" }] });
  await pending;
  assert.doesNotMatch(results.text, /stale/);
  console.log("M8.2 similarity UI: score, evidence, missing data, safe rendering, navigation, retry and stale response PASS");
}

run().catch(error => { console.error(error); process.exitCode = 1; });
