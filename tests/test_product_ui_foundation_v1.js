const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const html = read("webapp/index.html");
const detail = read("webapp/pages/creator-library-detail.js");
const dashboard = read("webapp/pages/dashboard.js");
const settings = read("webapp/pages/settings.js");
const campaignDetail = read("webapp/pages/campaign-detail.js");
const styles = read("webapp/styles.css");

// Assert the production modal rather than a detached helper: account data uses
// the dedicated endpoints and no longer presents legacy single-account inputs.
assert.match(html, /id="creator-edit-profile-title">基本资料/);
assert.match(html, /id="creator-edit-accounts-title">平台账号/);
assert.doesNotMatch(html, /id="creator-edit-platform"/);
assert.doesNotMatch(html, /id="creator-edit-profile-url"/);
assert.doesNotMatch(html, /id="creator-edit-followers"/);
assert.match(detail, /\/accounts`/);
assert.match(detail, /ACCOUNT_OWNED_BY_OTHER_CREATOR/);
assert.match(detail, /该账号无法移除/);
assert.doesNotMatch(detail, /profile_url:\s*valueOf\("creator-edit-profile-url"\)/);

for (const [value, title] of [
  ["task", "最近抓取的达人"], ["review_results", "待处理的达人"],
  ["creator_library", "达人库"], ["manual", "临时补邮箱"],
]) {
  assert.match(html, new RegExp(`name="email-source" value="${value}"`));
  assert.match(html, new RegExp(title));
}
assert.match(html, /你想给哪些达人补邮箱？/);
assert.match(html, /仅查找并补充邮箱，不创建新的达人抓取任务/);
assert.match(html, /批量抓取达人/);
assert.match(html, /自动抓取账号资料并进入审核/);
assert.match(html, /一行一个达人主页链接/);

assert.match(html, /id="dashboard-v2-modules"/);
for (const id of ["today", "missing_info", "campaigns", "creator_overview", "data_freshness", "geography", "roi"]) {
  assert.match(html, new RegExp(`data-dashboard-v2-module="${id}"`));
}
assert.match(dashboard, /kolconnect-dashboard-layout-v2/);
assert.match(dashboard, /setVisible/);
assert.match(dashboard, /move\(id, direction\)/);
assert.match(dashboard, /module\.essential \|\| saved\.visible\[module\.id\] !== false/);
assert.match(html, /id="dashboard-customization-dialog"/);
assert.match(html, /id="dashboard-customization-modules"/);
assert.match(html, /id="dashboard-customization-reset"/);
assert.match(dashboard, /function openCustomizationDialog\(\)/);
assert.match(dashboard, /function renderCustomizationDialog\(\)/);
assert.doesNotMatch(dashboard, /navigate\("settings"\)/);
assert.doesNotMatch(settings, /dashboard-settings-modules|dashboard-layout-reset|dashboard-settings-copy/);
assert.match(styles, /dashboard-customization-copy strong \{ white-space: nowrap/);
assert.match(styles, /\.dashboard-v2-module\[hidden\] \{ display: none !important; \}/);

assert.match(html, /id="campaign-creator-quote-currency"/);
assert.match(html, /id="campaign-creator-quote-unit-usd"/);
assert.match(html, /id="campaign-creator-quote-usd"/);
assert.match(html, /id="campaign-creator-cost-usd"/);
assert.match(html, /id="campaign-inline-fx-save"/);
assert.match(campaignDetail, /尚未设置 \$\{code\} 汇率/);
assert.match(campaignDetail, /amount \/ rate/);
assert.match(campaignDetail, /\/api\/settings\/fx/);
assert.match(styles, /\.mail-message-item \{/);
assert.match(styles, /overflow-wrap: anywhere/);

class DashboardModuleContainer {
  constructor(nodes) { this.nodes = nodes; }
  querySelectorAll() { return this.nodes; }
  appendChild(node) { this.nodes.splice(this.nodes.indexOf(node), 1); this.nodes.push(node); }
}
const moduleNodes = ["today", "missing_info", "campaigns", "creator_overview", "data_freshness", "geography", "roi"]
  .map(id => ({ dataset: { dashboardV2Module: id }, hidden: false }));
const local = new Map();
let registeredPage = null;
const dashboardWindow = {
  localStorage: { getItem: key => local.get(key) || null, setItem: (key, value) => local.set(key, value) },
  Event: class Event { constructor(type) { this.type = type; } }, dispatchEvent() {},
  KOLConnectPages: { registerPage(name, page) { assert.equal(name, "dashboard"); registeredPage = page; } },
};
const dashboardDocument = { getElementById: id => id === "dashboard-v2-modules" ? new DashboardModuleContainer(moduleNodes) : null };
vm.runInNewContext(dashboard, { window: dashboardWindow, document: dashboardDocument, console, Map, Set, JSON, Object, Array, Intl, Number, Math, Date });
assert.ok(registeredPage);
const preferences = dashboardWindow.KOLConnectDashboardPreferences;
assert.equal(preferences.get().visible.today, true);
preferences.setVisible("missing_info", false);
assert.equal(moduleNodes.find(node => node.dataset.dashboardV2Module === "missing_info").hidden, true);
preferences.move("data_freshness", -1);
assert.notEqual(preferences.get().order.at(-1), "data_freshness");
preferences.move("today", 1);
assert.equal(preferences.get().order[0], "today", "today must remain first");
local.set("kolconnect-dashboard-layout-v2", "not-json");
assert.equal(preferences.get().visible.today, true, "malformed preferences must fail safe");
preferences.reset();
assert.equal(preferences.get().order.join(","), "today,missing_info,campaigns,creator_overview,data_freshness,geography,roi");

console.log("Product UI Foundation V1: OK");
