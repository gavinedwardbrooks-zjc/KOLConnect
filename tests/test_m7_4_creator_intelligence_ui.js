"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const detail = fs.readFileSync(path.join(root, "webapp", "pages", "creator-library-detail.js"), "utf8");
const app = fs.readFileSync(path.join(root, "webapp", "app.js"), "utf8");

for (const id of [
  "creator-intelligence-ai-tags",
  "creator-intelligence-categories",
  "creator-intelligence-audience",
  "creator-intelligence-content-signals",
  "creator-intelligence-follower-band",
  "creator-intelligence-engagement-band",
  "creator-intelligence-price-band",
  "creator-intelligence-confidence",
]) {
  assert.match(html, new RegExp(`id=["']${id}["']`), `${id} must render`);
}

assert.match(detail, /selectedAccount\(detail\)/, "intelligence must follow selected account");
assert.match(detail, /accountSignal\?\.follower_band/, "account follower band must not be combined");
assert.match(detail, /render\(detail\);\s*renderIntelligence\(intelligence\);/, "account switch must refresh intelligence signals");
assert.match(detail, /data\?\.intelligence/, "legacy summary must tolerate additive intelligence");
assert.match(app, /mailSaveSuccess[^\n]*配置保存成功/, "save success must be explicit");
assert.match(app, /Outlook \/ Microsoft 365/);
assert.match(app, /outlook\.office365\.com/);
assert.doesNotMatch(app, /Basic authentication is disabled/, "raw server bytes must not enter UI copy");

console.log("M7.4 Creator Intelligence UI: 8/8 foundations PASS");
