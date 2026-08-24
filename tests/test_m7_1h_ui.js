const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");

const html = read("webapp/index.html");
const app = read("webapp/app.js");
const campaigns = read("webapp/pages/campaigns.js");
const detail = read("webapp/pages/campaign-detail.js");
const settings = read("webapp/pages/settings.js");

assert.match(html, /id="campaign-platform-any"/);
for (const platform of ["TikTok", "Instagram", "YouTube"]) {
  assert.match(html, new RegExp(`data-campaign-platform value="${platform}"`));
}
assert.match(campaigns, /\bplatforms,\s*\r?\n/);
assert.match(campaigns, /setSelectedPlatforms\(\[\]\)/);
assert.match(campaigns, /event\.target\?\.id === "campaign-platform-any"/);

assert.match(html, /id="campaign-creator-account-id" multiple/);
assert.match(detail, /account_ids:\s*accountIds/);
assert.match(detail, /eligibleAccounts\(accounts\)/);
assert.match(detail, /campaignPlatforms\(\)/);

assert.match(html, /id="campaign-planned-date-list"/);
assert.match(html, /id="campaign-planned-date-add"/);
assert.match(detail, /planned_publish_dates:\s*dates/);
assert.match(detail, /createPlannedDateRow/);

assert.match(html, /扫描达人库缺失邮箱/);
assert.match(app, /扫描本地达人库账号/);
assert.doesNotMatch(html, /扫描飞书表缺失邮箱/);
assert.doesNotMatch(app, /扫描飞书表缺失邮箱/);

for (const id of [
  "feishu-sync-relation-add",
  "feishu-sync-relation-update",
  "feishu-sync-relation-remove",
  "feishu-sync-relation-conflicts",
]) {
  assert.match(html, new RegExp(`id="${id}"`));
  assert.match(settings, new RegExp(id));
}
assert.match(settings, /relation_updated/);
assert.doesNotMatch(detail, /feishu-sync\/full-sync/);

console.log("M7.1h Campaign, local email, and Feishu relation UI: OK");
