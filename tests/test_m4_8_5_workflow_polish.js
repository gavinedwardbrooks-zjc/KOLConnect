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

function testCaptureModeAndResultActions() {
  const html = read("webapp/index.html");
  const source = read("webapp/app.js");
  assert.match(html, /id="capture-mode"[\s\S]*value="automatic">自动抓取[\s\S]*value="manual">人工抓取/);
  assert.match(html, /id="capture-automatic-panel"/);
  assert.match(html, /id="capture-manual-panel" hidden/);
  assert.match(source, /automaticPanel\.hidden = mode !== "automatic"/);
  assert.match(source, /manualPanel\.hidden = mode !== "manual"/);
  assert.match(source, /platforms: selectedTaskPlatforms\(\)/, "platform payload remains unchanged");
  assert.match(html, /id="scrape-open-results"[^>]*>打开结果文件/);
  assert.match(html, /id="scrape-open-result-folder"[^>]*disabled>打开结果文件夹/);
  assert.match(source, /\/api\/tasks\/\$\{encodeURIComponent\(state\.currentTaskId\)\}\/results\/open-folder/);
  assert.doesNotMatch(source, /open-folder[^\n]*(path|directory)\s*:/i, "frontend must not submit a path");
}

function testCompactReviewAndCreatorLibraryToolbars() {
  const html = read("webapp/index.html");
  const css = read("webapp/styles.css");
  assert.match(html, /扫描达人库缺失邮箱/);
  assert.doesNotMatch(html, /同步有效结果到飞书表|review-sync-four-tables/);
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

function testChromeAccountLabels() {
  const html = read("webapp/index.html");
  assert.match(html, /data-page="accounts" data-primary="settings"[^>]*>Chrome 账号/);
  assert.match(html, /data-i18n="accountsTitle">Chrome 账号/);
  assert.match(html, /管理用于达人抓取的 Chrome Profile 和用途/);
  assert.match(html, /data-i18n="profilesTitle">Chrome Profile/);
}

testDashboardReadingOrder();
testCaptureModeAndResultActions();
testCompactReviewAndCreatorLibraryToolbars();
testRecentMailPaginationContract();
testChromeAccountLabels();
console.log("M4.8.5 workflow polish tests passed");
