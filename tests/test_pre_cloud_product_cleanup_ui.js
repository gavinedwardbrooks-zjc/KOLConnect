"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const read = relativePath => fs.readFileSync(path.join(ROOT, relativePath), "utf8");
const index = read("webapp/index.html");
const app = read("webapp/app.js");
const detail = read("webapp/pages/creator-library-detail.js");

// The retired queue card must not remain reachable from the normal review page;
// row editing and retry controls remain in the results table.
assert.doesNotMatch(index, /id="review-queue"/);
assert.match(index, /id="review-status-filter"/);
assert.match(index, /账号名/);
assert.match(app, /review-status-filter/);
assert.match(app, /retryFailedReviewRecord/);

// Task runs expose one persistent task selection surface, per-platform choices,
// and clear source-link copy/export actions.
assert.match(app, /task-selector/);
assert.match(app, /task-run-platforms/);
assert.match(app, /抓取所选平台/);
assert.match(app, /copyTaskLinks\("all"\)/);
assert.match(app, /copyTaskLinks\("unfinished"\)/);

// Chrome profiles are reusable configuration, not a consumable quota UI.
assert.match(index, /Chrome Profile 配置/);
assert.match(index, /id="accounts-add"/);
assert.match(app, /打开浏览器/);
assert.match(app, /移除配置/);
assert.doesNotMatch(app, /使用次数/);

// Direct Creator maintenance owns WhatsApp and sends it through the existing
// Creator PATCH payload.
assert.match(index, /id="creator-edit-whatsapp"/);
assert.match(detail, /whatsapp:\s*valueOf\("creator-edit-whatsapp"\)/);

console.log("Pre-Cloud product cleanup UI: OK");
