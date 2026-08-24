"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");

const html = read("webapp/index.html");
const app = read("webapp/app.js");
const taskHandler = read("app/http_handlers/task_handler.py");
const server = read("app/server.py");
const settings = read("webapp/pages/settings.js");
const feishuHandler = read("app/http_handlers/feishu_sync_handler.py");

assert.doesNotMatch(html, /review-sync-four-tables|review-sync-summary|同步有效结果到飞书表/);
assert.doesNotMatch(app, /manualDirectSync|reviewSyncFourTables|reviewSyncConfirm|sync-four-tables/);
assert.doesNotMatch(taskHandler, /sync-four-tables|sync_task_results_to_four_tables/);
assert.doesNotMatch(server, /"sync_task_results_to_four_tables"\s*:/);

for (const retained of ["review-refresh", "review-scan-missing-email", "review-retry-failed"]) {
  assert.match(html, new RegExp(`id="${retained}"`));
}
assert.match(app, /\/api\/tasks\/\$\{encodeURIComponent\(state\.review\.taskId\)\}\/results\/update/);
assert.match(app, /\/results\/retry-failed/);

for (const retained of ["feishu-sync-validate", "feishu-sync-dry-run", "feishu-sync-full"]) {
  assert.match(html, new RegExp(`id="${retained}"`));
}
assert.match(settings, /\/api\/feishu-sync\/validate/);
assert.match(settings, /\/api\/feishu-sync\/dry-run/);
assert.match(settings, /\/api\/feishu-sync\/full-sync/);
assert.match(settings, /confirm:\s*true/);
assert.match(feishuHandler, /service\.full_sync\([\s\S]*confirm=payload\.get\("confirm"\)[\s\S]*\)/);

console.log("M7.1f legacy capture-page Feishu entry retirement: OK");
