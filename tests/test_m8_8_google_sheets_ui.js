const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const settings = fs.readFileSync(path.join(root, "webapp", "pages", "settings.js"), "utf8");
const campaign = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8");

assert(html.includes('id="google-sheets-client-id"'));
assert(html.includes('id="google-sheets-client-secret"'));
assert(html.includes('id="google-sheets-spreadsheet-id"'));
assert(html.includes('id="google-sheets-connect"'));
assert(html.includes('id="google-sheets-disconnect"'));
assert(html.includes('id="google-sheets-sync"'));
assert(html.includes('id="campaign-google-sheets-sync"'));
assert(settings.includes('/api/settings/google-sheets'));
assert(settings.includes('/api/google-sheets/connect'));
assert(settings.includes('/api/google-sheets/disconnect'));
assert(settings.includes('/api/google-sheets/sync'));
assert(settings.includes('AUTH_REQUIRED: "需要授权"'));
assert(settings.includes("Google 授权已失效或尚未完成，请重新连接 Google 后再同步。"));
assert(campaign.includes('/google-sheets-sync'));
assert(campaign.includes('googleSheetsSyncPending'));
assert(campaign.includes('result.status !== "SUCCESS"'));
assert(campaign.includes('requestedLifecycle !== lifecycleId'));
assert(campaign.includes('Google Sheets 报告仅部分写入'));
assert(!html.includes("Google Sheets 定时"));
assert(!settings.includes("Import from Google Sheets"));

console.log("M8.8 Google Sheets UI tests passed");
