"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = relativePath => fs.readFileSync(path.join(root, relativePath), "utf8");
const html = read("webapp/index.html");
const source = read("webapp/app.js");

for (const id of [
  "discover-mode-account", "discover-mode-email", "discover-email-results",
  "discover-email-existing-body", "discover-email-duplicates-output",
  "discover-email-unrecorded-output", "discover-copy-unrecorded-emails",
]) {
  assert.match(html, new RegExp(`id="${id}"`), `missing email cleanup UI: ${id}`);
}

assert.match(source, /apiPost\("\/api\/normalize-links", \{ text \}\)/, "account cleanup must retain its endpoint");
assert.match(source, /apiPost\("\/api\/normalize-emails", \{ text \}\)/, "email mode must use the local check endpoint");
assert.match(source, /setDiscoverMode\("email"\)/);
assert.match(source, /input_duplicate_of_line/);
assert.match(source, /database_matches/);
const emailRenderSource = source.slice(
  source.indexOf("function renderEmailDeduplicationResults"),
  source.indexOf("function updateTaskLinkCounts")
);
assert.match(emailRenderSource, /textContent = String\(value\)/, "existing-match values must use textContent");
assert.doesNotMatch(emailRenderSource, /innerHTML\s*=/, "cleanup rendering must not use innerHTML");

console.log("Pre-M9 email deduplication UI: OK");
