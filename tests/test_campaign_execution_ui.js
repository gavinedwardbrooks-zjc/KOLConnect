const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const page = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-execution.js"), "utf8");
const registry = fs.readFileSync(path.join(root, "webapp", "core", "page-registry.js"), "utf8");

[
  "today", "due-soon", "overdue", "stalled", "waiting-creator", "waiting-internal", "need-my-decision",
].forEach(group => {
  assert.match(html, new RegExp(`campaign-execution-${group}`));
});
assert.match(html, /data-page="campaign-execution"/);
assert.match(html, /pages\/campaign-execution\.js/);
assert.match(page, /\/api\/campaign-execution\/workspace/);
assert.match(page, /KOLConnectAPI\.get/);
assert.match(page, /navigate\("campaign-detail"/);
assert.match(registry, /"campaign-execution": "mail"/);
assert.doesNotMatch(page, /\bfetch\s*\(/);

console.log("Campaign Execution workspace UI contract: OK");
