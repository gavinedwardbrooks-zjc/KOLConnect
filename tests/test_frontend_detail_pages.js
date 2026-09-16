"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const app = fs.readFileSync(path.join(root, "webapp", "app.js"), "utf8");

// Task-result intelligence remains a backend capability, but an empty aggregate
// card must not occupy the normal review workflow.
assert.doesNotMatch(html, /id="creator-analysis-panel"|id="review-view-analysis"/);
assert.doesNotMatch(app, /function viewCreatorAnalysis/);
assert.match(html, /id="review-results-body"/);
assert.match(app, /function renderReviewResults/);

console.log("Review detail surface: OK");
