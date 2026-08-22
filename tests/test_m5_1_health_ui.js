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

const ids = [
  "dashboard-total-creators", "dashboard-new-creators", "dashboard-discovered",
  "dashboard-cooperating", "dashboard-spend", "dashboard-average-roi",
  "dashboard-campaigns", "dashboard-total-cost", "dashboard-total-views",
  "dashboard-cooperation-roi", "dashboard-rising-creators", "dashboard-falling-creators",
  "dashboard-expired-creators", "dashboard-action-expired", "dashboard-pending-contact",
  "dashboard-incomplete-cooperations", "dashboard-top-creators", "dashboard-platform-chart",
  "dashboard-status-chart", "dashboard-growth-chart", "dashboard-platform-chart-empty",
  "dashboard-status-chart-empty", "dashboard-growth-chart-empty", "dashboard-health-score",
  "dashboard-health-healthy", "dashboard-health-warning", "dashboard-health-critical",
  "dashboard-health-healthy-bar", "dashboard-health-warning-bar", "dashboard-health-critical-bar",
  "dashboard-health-empty",
  "dashboard-risk-high", "dashboard-risk-medium", "dashboard-risk-low", "dashboard-risk-error",
];

function dashboardResponse(healthSummary) {
  return {
    overview: {}, creator_health: {}, cooperation_performance: {}, action_items: {},
    platform_distribution: [], creator_status_distribution: [], creator_growth_trend: [],
    ...(healthSummary === undefined ? {} : { health_summary: healthSummary }),
  };
}

async function run() {
  const elements = new Map(ids.map(id => [id, new FakeElement()]));
  const responses = [
    dashboardResponse({ score: 60, healthy: 3, warning: 1, critical: 1, total: 5 }),
    dashboardResponse({ score: null, healthy: 0, warning: 0, critical: 0, total: 0 }),
    dashboardResponse(),
  ];
  let registeredPage = null;
  const document = {
    getElementById(id) { return elements.get(id) || null; },
    createElement() { return new FakeElement(); },
    querySelector() { return null; },
  };
  const window = {
    KOLConnectAPI: {
      async get(url) {
        if (url === "/api/risks") return { summary: { high: 0, medium: 0, low: 0 }, cards: [] };
        assert.equal(url, "/api/dashboard");
        return responses.shift();
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

  assert.ok(registeredPage, "Dashboard page should register");
  await registeredPage.load();
  assert.equal(elements.get("dashboard-health-score").textContent, "60");
  assert.equal(elements.get("dashboard-health-healthy").textContent, "3");
  assert.equal(elements.get("dashboard-health-warning").textContent, "1");
  assert.equal(elements.get("dashboard-health-critical").textContent, "1");
  assert.equal(elements.get("dashboard-health-healthy-bar").style.width, "60%");
  assert.equal(elements.get("dashboard-risk-high").textContent, "0");

  await registeredPage.load();
  assert.equal(elements.get("dashboard-health-score").textContent, "--");
  assert.equal(elements.get("dashboard-health-empty").hidden, false);
  assert.equal(elements.get("dashboard-health-healthy").textContent, "0");
  assert.equal(elements.get("dashboard-health-warning").textContent, "0");
  assert.equal(elements.get("dashboard-health-critical").textContent, "0");

  await registeredPage.load();
  assert.equal(elements.get("dashboard-health-score").textContent, "--");
  assert.equal(elements.get("dashboard-health-empty").hidden, false);

  const html = fs.readFileSync(path.join(root, "webapp/index.html"), "utf8");
  for (const id of ["dashboard-health-score", "dashboard-health-empty", "dashboard-health-healthy", "dashboard-health-warning", "dashboard-health-critical"]) {
    assert.match(html, new RegExp(`id=["']${id}["']`));
  }
  assert.match(html, /id="dashboard-risk-high"/);
  console.log("M5.1 health UI tests passed");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
