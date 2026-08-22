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

async function run() {
  const ids = [
    "dashboard-country-list", "dashboard-language-list", "dashboard-geography-error",
    "dashboard-roi-trend-chart", "dashboard-roi-trend-empty", "dashboard-roi-trend-error",
    "dashboard-roi-latest", "dashboard-risk-high", "dashboard-risk-medium",
    "dashboard-risk-low", "dashboard-risk-error", "dashboard-health-score",
    "dashboard-health-empty", "dashboard-health-healthy", "dashboard-health-warning",
    "dashboard-health-critical", "dashboard-health-healthy-bar", "dashboard-health-warning-bar",
    "dashboard-health-critical-bar",
  ];
  const elements = new Map(ids.map(id => [id, new FakeElement()]));
  let registeredPage = null;
  const calls = [];
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
        calls.push(url);
        if (url === "/api/analytics/geography") return {
          countries: [
            { name: "Brazil", creator_count: 4, active_creator_count: 3 },
            { name: "Unknown", creator_count: 1, active_creator_count: 1 },
          ],
          languages: [{ name: "Portuguese", creator_count: 4 }],
        };
        if (url === "/api/analytics/roi-trend") return {
          trend: [
            { month: "2026-01", average_recorded_roi: 1.5 },
            { month: "2026-03", average_recorded_roi: null },
          ],
        };
        if (url === "/api/analytics/platforms") return { platforms: [], summary: {} };
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
  assert.ok(calls.includes("/api/analytics/geography"));
  assert.ok(calls.includes("/api/analytics/roi-trend"));
  assert.equal(elements.get("dashboard-country-list").children[0].children[0].textContent, "Brazil");
  assert.equal(elements.get("dashboard-country-list").children[0].children[1].textContent, "4");
  assert.equal(elements.get("dashboard-country-list").children[0].children[2].textContent, "活跃 3");
  assert.equal(elements.get("dashboard-language-list").children[0].children[0].textContent, "Portuguese");
  assert.equal(elements.get("dashboard-roi-latest").textContent, "--");
  assert.equal(elements.get("dashboard-risk-high").textContent, "1");
  assert.equal(elements.get("dashboard-health-score").textContent, "80");

  const roiChart = chartCalls.find(chart => chart.config.data.datasets[0].label === "Average recorded ROI");
  assert.ok(roiChart);
  assert.deepEqual(Array.from(roiChart.config.data.labels), ["2026-01", "2026-03"]);
  assert.deepEqual(Array.from(roiChart.config.data.datasets[0].data), [1.5, null]);

  const html = fs.readFileSync(path.join(root, "webapp/index.html"), "utf8");
  assert.match(html, /id="dashboard-country-list"/);
  assert.match(html, /id="dashboard-language-list"/);
  assert.match(html, /id="dashboard-roi-trend-chart"/);
  assert.match(html, /Based on recorded ROI values, not automatically calculated financial ROI\./);
  console.log("M5.3 geography and recorded ROI analytics UI: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
