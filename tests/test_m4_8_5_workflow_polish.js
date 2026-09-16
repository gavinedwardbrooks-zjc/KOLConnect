"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const read = relativePath => fs.readFileSync(path.join(ROOT, relativePath), "utf8");

function testDashboardReadingOrder() {
  const html = read("webapp/index.html");
  const kpis = html.indexOf("dashboard-overview-grid");
  const actions = html.indexOf("dashboard-action-center");
  const charts = html.indexOf("dashboard-visualization-grid");
  assert.ok(kpis >= 0 && kpis < actions && actions < charts, "KPI < today actions < charts");
}

function testCaptureAndResultActions() {
  const html = read("webapp/index.html");
  const source = read("webapp/app.js");
  const css = read("webapp/styles.css");
  assert.match(html, /id="capture-automatic-panel"/);
  assert.doesNotMatch(html, /id="capture-mode"|id="capture-manual-panel"|id="manual-task-create"/);
  assert.doesNotMatch(source, /\$\("manual-task-create"\)\.addEventListener/);
  assert.match(source, /platforms: selectedTaskPlatforms\(\)/, "platform payload remains unchanged");
  assert.match(source, /review\.textContent = "查看结果"/);
  assert.match(source, /run\.textContent = "继续抓取"/);
  assert.match(source, /moreSummary\.textContent = "更多"/);
  assert.match(source, /moreActions\.append\(viewOriginal, copyAll, copyUnfinished, exportLinks, rename, remove\)/);
  assert.match(source, /more\.addEventListener\("click", event => event\.stopPropagation\(\)\)/, "More must not re-render its parent task card when opened");
  assert.match(source, /closeMoreOnOutsideClick/, "More menu must close when focus moves outside it");
  assert.match(source, /event\.key !== "Escape"/, "More menu supports keyboard close");
  assert.match(css, /\.task-card-more-actions[\s\S]*z-index:\s*20/, "More menu stays above task cards");
  assert.match(html, /id="scrape-open-results"[^>]*>打开结果文件/);
  assert.match(html, /id="scrape-open-result-folder"[^>]*disabled>打开结果文件夹/);
  assert.match(source, /\/api\/tasks\/\$\{encodeURIComponent\(state\.currentTaskId\)\}\/results\/open-folder/);
  assert.doesNotMatch(source, /open-folder[^\n]*(path|directory)\s*:/i, "frontend must not submit a path");
}

function testCompactReviewAndCreatorLibraryToolbars() {
  const html = read("webapp/index.html");
  const source = read("webapp/app.js");
  const css = read("webapp/styles.css");
  assert.match(html, /扫描达人库缺失邮箱/);
  assert.doesNotMatch(html, /同步有效结果到飞书表|review-sync-four-tables/);
  assert.doesNotMatch(html, /<th data-i18n="reviewAccountUid">账号唯一ID<\/th>/);
  assert.match(source, /function reviewPrimaryResultLabel/);
  assert.match(css, /\.review-toolbar-actions[\s\S]*grid-column:\s*1 \/ -1/);
  assert.match(html, /class="creator-library-actions-left"/);
  assert.match(html, /class="creator-library-actions-right"/);
  assert.match(html, /id="creator-library-selected-count">已选 0 人/);
  [
    "creator-library-card-view", "creator-library-table-view", "creator-library-select-all",
    "creator-library-export", "creator-library-batch-campaign", "creator-library-template-download",
    "creator-library-import-button", "creator-library-refresh",
  ].forEach(id => assert.match(html, new RegExp(`id="${id}"`)));
  assert.match(css, /\.creator-library-actions[\s\S]*grid-column:\s*1 \/ -1/);
}

function testRecentMailPaginationContract() {
  const html = read("webapp/index.html");
  const source = read("webapp/app.js");
  assert.match(html, /id="mail-page-size"[\s\S]*value="10"[\s\S]*value="20" selected[\s\S]*value="50"/);
  assert.match(html, /id="mail-page-previous"/);
  assert.match(html, /id="mail-page-next"/);
  assert.match(html, /id="mail-page-total"/);
  assert.match(html, /id="mail-page-summary"/);
  assert.match(source, /filtered\.slice\(start, start \+ pageSize\)/);
  assert.match(source, /state\.mailInbox\.page = Math\.min\(Math\.max\(1, state\.mailInbox\.page\), totalPages\)/);
  assert.match(source, /\$\("mail-matched-only"\)[\s\S]*state\.mailInbox\.page = 1/);
  assert.match(source, /\$\("mail-page-size"\)[\s\S]*state\.mailInbox\.page = 1/);
}

function testMailLongTokenContainment() {
  const css = read("webapp/styles.css");
  assert.match(css, /\.mail-message-snippet[\s\S]*max-width:\s*100%[\s\S]*overflow-wrap:\s*anywhere[\s\S]*word-break:\s*break-word/, "long unbroken URLs must wrap within a mail card");
  assert.match(css, /\.page\[data-page="mail"\] \.section-card[\s\S]*min-width:\s*0/, "mail card containers remain shrinkable");
}

function testChromeAccountLabels() {
  const html = read("webapp/index.html");
  const source = read("webapp/app.js");
  const css = read("webapp/styles.css");
  assert.match(html, /data-page="accounts" data-primary="settings"[^>]*>Chrome 账号/);
  assert.match(html, /data-i18n="accountsTitle">Chrome 账号/);
  assert.match(html, /管理用于达人抓取的 Chrome Profile 配置；删除配置不会删除浏览器数据/);
  assert.match(html, /Chrome Profile 配置/);
  assert.match(source, /row\.className = "chrome-profile-card"/);
  assert.match(source, /#accounts-list \.chrome-profile-card/);
  assert.match(css, /\.chrome-profile-card/);
  assert.match(css, /\.chrome-profile-actions \.mini-btn \{ white-space: nowrap; \}/);
}

testDashboardReadingOrder();
testCaptureAndResultActions();
testCompactReviewAndCreatorLibraryToolbars();
testRecentMailPaginationContract();
testMailLongTokenContainment();
testChromeAccountLabels();
console.log("M4.8.5 workflow polish tests passed");
