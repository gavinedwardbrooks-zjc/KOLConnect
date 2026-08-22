"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

class FakeElement {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.hidden = false;
    this.textContent = "";
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  getContext() { return {}; }
}

function analyticsResponse() {
  return {
    platforms: [
      {
        platform: "tiktok", creator_count: 2, followers_average: 1500,
        followers_median: 1400, campaign_creator_count: 2, published_count: 1,
        publish_rate: 50, views_total: 10000, likes_total: 800,
        comments_total: 200, visible_engagement_rate: 10, cost_total: 500,
        recorded_roi_average: 1.75,
      },
      {
        platform: "instagram", creator_count: 1, followers_average: null,
        followers_median: null, campaign_creator_count: 0, published_count: 0,
        publish_rate: null, views_total: 0, likes_total: 0, comments_total: 0,
        visible_engagement_rate: null, cost_total: 0, recorded_roi_average: null,
      },
      {
        platform: "youtube", creator_count: 3, followers_average: 5000,
        followers_median: 4500, campaign_creator_count: 1, published_count: 1,
        publish_rate: 100, views_total: 20000, likes_total: 1200,
        comments_total: 300, visible_engagement_rate: 7.5, cost_total: 900,
        recorded_roi_average: 2.2,
      },
    ],
    summary: { platform_count: 3, creator_count: 6, campaign_creator_count: 3, ignored_campaign_creator_count: 1 },
  };
}

async function run() {
  const ids = [
    "dashboard-platform-analytics-chart", "dashboard-platform-analytics-empty",
    "dashboard-platform-analytics-error", "dashboard-risk-high", "dashboard-risk-medium",
    "dashboard-risk-low", "dashboard-risk-error", "dashboard-health-score",
    "dashboard-health-empty", "dashboard-health-healthy", "dashboard-health-warning",
    "dashboard-health-critical", "dashboard-health-healthy-bar", "dashboard-health-warning-bar",
    "dashboard-health-critical-bar",
  ];
  for (const platform of ["tiktok", "instagram", "youtube"]) {
    for (const metric of ["creators", "followers-median", "followers-average", "relations", "publish-rate", "views", "likes", "comments", "engagement", "cost", "roi"]) {
      ids.push(`platform-${platform}-${metric}`);
    }
  }
  const elements = new Map(ids.map(id => [id, new FakeElement()]));
  let registeredPage = null;
  const chartCalls = [];
  class FakeChart {
    constructor(_context, config) { this.config = config; chartCalls.push(this); }
    destroy() {}
  }
  const document = {
    getElementById(id) { return elements.get(id) || null; },
    createElement() { return new FakeElement(); },
    querySelector() { return null; },
  };
  const window = {
    Chart: FakeChart,
    KOLConnectAPI: {
      async get(url) {
        if (url === "/api/analytics/platforms") return analyticsResponse();
        if (url === "/api/risks") return { summary: { high: 1, medium: 2, low: 3 }, cards: [] };
        if (url === "/api/dashboard") return {
          overview: {}, creator_health: {}, cooperation_performance: {}, action_items: {},
          platform_distribution: [], creator_status_distribution: [], creator_growth_trend: [],
          health_summary: { score: 80, healthy: 8, warning: 1, critical: 1, total: 10 },
        };
        throw new Error(`Unexpected URL ${url}`);
      },
    },
    KOLConnectApp: { showError(error) { throw error; } },
    KOLConnectPageResources: {
      create() {
        return {
          disposed: false,
          createAbortController: () => new AbortController(),
          cleanup() { this.disposed = true; },
          listen() {},
        };
      },
    },
    KOLConnectPages: { registerPage(_name, page) { registeredPage = page; } },
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(root, "webapp/pages/dashboard.js"), "utf8"),
    { window, document, AbortController, Intl, Map, Set, console },
  );

  await registeredPage.load();
  assert.equal(elements.get("platform-tiktok-creators").textContent, "2");
  assert.equal(elements.get("platform-tiktok-followers-median").textContent, "1,400");
  assert.equal(elements.get("platform-tiktok-followers-average").textContent, "1,500");
  assert.equal(elements.get("platform-tiktok-relations").textContent, "2");
  assert.equal(elements.get("platform-tiktok-publish-rate").textContent, "50%");
  assert.equal(elements.get("platform-tiktok-views").textContent, "10,000");
  assert.equal(elements.get("platform-tiktok-likes").textContent, "800");
  assert.equal(elements.get("platform-tiktok-comments").textContent, "200");
  assert.equal(elements.get("platform-tiktok-engagement").textContent, "10%");
  assert.equal(elements.get("platform-tiktok-cost").textContent, "500");
  assert.equal(elements.get("platform-tiktok-roi").textContent, "1.75");
  assert.equal(elements.get("platform-instagram-followers-average").textContent, "--");
  assert.equal(elements.get("platform-instagram-publish-rate").textContent, "--");
  assert.equal(elements.get("platform-instagram-engagement").textContent, "--");
  assert.equal(elements.get("platform-instagram-roi").textContent, "--");
  assert.equal(elements.get("dashboard-health-score").textContent, "80");
  assert.equal(elements.get("dashboard-risk-high").textContent, "1");
  assert.deepEqual(Array.from(chartCalls[0].config.data.labels), ["TikTok", "Instagram", "YouTube"]);

  const html = fs.readFileSync(path.join(root, "webapp/index.html"), "utf8");
  assert.match(html, /aria-label="平台分析"/);
  assert.match(html, />TikTok</);
  assert.match(html, />Instagram</);
  assert.match(html, />YouTube</);
  assert.match(html, />可见互动率</);
  assert.match(html, /基于已录入值，不代表系统根据收入自动计算的财务 ROI/);
  assert.match(html, /id="dashboard-risk-high"/);
  assert.match(html, /id="dashboard-health-score"/);
  console.log("M5.3.1 platform analytics UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
