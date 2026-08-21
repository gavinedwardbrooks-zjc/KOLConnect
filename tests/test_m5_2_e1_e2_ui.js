"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const dashboard = fs.readFileSync(path.join(root, "webapp", "pages", "dashboard.js"), "utf8");
const campaign = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8");

for (const id of ["dashboard-risk-high", "dashboard-risk-medium", "dashboard-risk-low"]) {
  assert.match(html, new RegExp(`id=["']${id}["']`));
}
for (const heading of ["Campaign", "Creator", "Stage", "Publish Date", "Publish Link", "Risk"]) {
  assert.match(html, new RegExp(`<th>${heading}</th>`));
}
assert.match(dashboard, /KOLConnectAPI\.get\("\/api\/risks"/);
assert.match(dashboard, /renderRiskSummary/);
assert.match(campaign, /missing-publish-links/);
assert.match(campaign, /renderMissingPublishLinks/);
assert.doesNotMatch(dashboard, /cdn|https:\/\//i);

console.log("M5.2 E1/E2 minimal UI tests passed");
