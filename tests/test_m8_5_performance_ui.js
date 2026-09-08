"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const campaign = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8");
const creator = fs.readFileSync(path.join(root, "webapp", "pages", "creator-library-detail.js"), "utf8");

[
  "campaign-performance-total-views",
  "campaign-performance-total-likes",
  "campaign-performance-total-comments",
  "campaign-performance-average-er",
  "campaign-performance-highlights",
  "campaign-performance-money",
  "campaign-performance-trends",
  "creator-history-performance-summary",
  "creator-history-performance-money",
  "creator-history-campaigns",
].forEach(id => assert.match(html, new RegExp(`id="${id}"`)));

assert.match(campaign, /\/api\/campaigns\/\$\{encodeURIComponent\(campaignId\)\}\/performance/);
assert.match(campaign, /coverageText/);
assert.match(campaign, /最快增长（播放\/天）/);
assert.match(campaign, /start_observed_at/);
assert.match(campaign, /end_observed_at/);
assert.match(campaign, /total_cost_by_currency/);
assert.match(campaign, /total_quote_by_currency/);
assert.match(campaign, /ROI：—（缺少权威回报数据）/);
assert.match(campaign, /value === null \|\| value === undefined \|\| value === "" \? "—"/);
assert.match(campaign, /textContent = value/);
assert.doesNotMatch(campaign, /performance.*innerHTML/i);

assert.match(creator, /\/historical-performance/);
assert.match(creator, /total_cost_by_currency/);
assert.match(creator, /total_quote_by_currency/);
assert.match(creator, /efficiency_by_currency/);
assert.match(creator, /ROI：--（缺少权威回报数据）/);
assert.match(creator, /textContent = `\$\{currency\} · CPV/);
assert.doesNotMatch(creator, /历史.*innerHTML/i);

// Existing M8.4 refresh and M5.2 risk/navigation surfaces remain present.
assert.match(html, /id="campaign-publications-refresh-all"/);
assert.match(html, /id="dashboard-risk-high"/);
assert.match(campaign, /publications\/refresh/);

class Element {
  constructor() { this.children = []; this.textContent = ""; this.hidden = false; }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; this.textContent = ""; }
  get text() { return this.textContent + this.children.map(child => child.text).join(" "); }
}

function harness(source, hook) {
  const elements = new Map();
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement() { return new Element(); },
  };
  const window = { KOLConnectPages: { registerPage() {} } };
  const context = { window, document, Intl, URL, console };
  vm.runInNewContext(source.replace(/\}\)\(window\);\s*$/, `${hook}\n})(window);`), context);
  return { window, elements, get: document.getElementById };
}

async function run() {
  const c = harness(campaign, `global.testRender = data => { campaignPerformance = data; renderCampaignPerformanceAnalytics(); };
    global.testReload = () => { resources = {signal: undefined}; campaignId = 'c1'; return reloadCampaignPerformanceAnalytics(); };
    global.testInvalidate = () => { lifecycleId += 1; };`);
  c.window.testRender(null);
  assert.equal(c.get("campaign-performance-total-views").textContent, "—");
  c.window.testRender({
    totals: {views: {total: 0, valid_count: 1, total_publications: 2}},
    average_er: 0, valid_er_count: 1, total_publications: 2,
    total_cost_by_currency: {USD: 10, BRL: 20},
    publications: [{creator_name: "Creator", platform: "TikTok", series: [
      {observed_at: "2026-01-01T00:00:00Z", views: 0, likes: null, comments: 1, engagement_rate: null},
    ]}],
  });
  assert.equal(c.get("campaign-performance-total-views").textContent, "0");
  assert.equal(c.get("campaign-performance-views-coverage").textContent, "1 / 2 条有数据");
  assert.equal(c.get("campaign-performance-average-er").textContent, "0%");
  assert.match(c.get("campaign-performance-money").text, /USD 10 · BRL 20/);
  assert.match(c.get("campaign-performance-trends").text, /2026-01-01T00:00:00Z/);
  assert.match(c.get("campaign-performance-trends").text, /—/);
  let resolve;
  c.window.KOLConnectAPI = {get: () => new Promise(done => {resolve = done;})};
  const pending = c.window.testReload();
  c.window.testInvalidate();
  resolve({totals: {views: {total: 999}}});
  await pending;
  assert.equal(c.get("campaign-performance-total-views").textContent, "0", "stale response must not overwrite the next lifecycle");

  const d = harness(creator, "global.testHistory = data => { historicalPerformance = data; renderHistoricalPerformance(); };");
  d.window.testHistory(null);
  assert.equal(d.get("creator-history-performance-empty").hidden, false);
  d.window.testHistory({cooperation_count: 2, publication_count: 3, historical_campaign_count: 1,
    average_latest_views: 0, total_historical_publications: 3, valid_publication_views_count: 1,
    total_cost_by_currency: {USD: 10, BRL: 20}, efficiency_by_currency: {USD: {cpv: null, cpe: 0}},
    historical_campaigns: [{campaign_id: "c1", campaign_name: "<script>not executed</script>"}],
  });
  assert.match(d.get("creator-history-performance-summary").text, /平均播放 0/);
  assert.match(d.get("creator-history-performance-money").text, /USD 10 · BRL 20/);
  assert.match(d.get("creator-history-performance-money").text, /CPV -- · CPE 0/);
  assert.match(d.get("creator-history-performance-money").text, /ROI：--/);
  assert.match(d.get("creator-history-campaigns").text, /<script>not executed<\/script>/);
  console.log("M8.5 performance analytics UI tests passed");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
