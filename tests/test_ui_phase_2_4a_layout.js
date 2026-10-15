"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const styles = read("webapp/styles.css");
const settings = read("webapp/pages/settings.js");
const html = read("webapp/index.html");
const i18n = read("webapp/i18n.js");

assert.match(styles, /\.agency-row-actions,\s*\.campaign-row-actions \{[\s\S]*?flex-wrap: nowrap;[\s\S]*?white-space: nowrap;/);
assert.doesNotMatch(styles, /\.compact-management-table th:last-child,\s*\.compact-management-table td:last-child \{ width: 1%;/);
assert.match(styles, /\.agency-table th:last-child, \.agency-table td:last-child \{ width: 180px; min-width: 180px; padding-right: 14px; \}/);
assert.match(styles, /\.product-table th:last-child, \.product-table td:last-child \{ width: 160px; min-width: 160px; padding-right: 14px; \}/);
assert.match(styles, /\.campaign-table th:last-child, \.campaign-table td:last-child \{ width: 180px; min-width: 180px; padding-right: 14px; \}/);
assert.match(styles, /\.settings-categories \{ display: grid; gap: 18px; \}/);
assert.match(styles, /\.settings-category\[hidden\] \{ display: none !important; \}/);
assert.match(styles, /\.settings-category-cards > \.section-card \{ margin: 0; \}/);
assert.match(styles, /\.settings-category-tabs \{ display: flex; flex-wrap: wrap;/);
assert.match(styles, /\.primary-btn,\s*\.soft-btn,\s*\.secondary-btn,\s*\.danger-btn,\s*\.mini-btn \{[\s\S]*?border-radius: 12px;[\s\S]*?min-height: 42px;/);
assert.match(styles, /\.soft-btn,\s*\.secondary-btn \{[\s\S]*?background: var\(--soft\);[\s\S]*?border-color: var\(--border\);/);
assert.match(styles, /\.text-btn \{[\s\S]*?display: inline-flex;[\s\S]*?border: 1px solid var\(--border\);[\s\S]*?background: var\(--soft\);/);
for (const id of [
  "campaign-date-filter-apply", "mail-followup-show-export", "settings-open-chrome-accounts",
  "settings-open-mail-accounts", "system-health-run", "settings-open-logs", "fx-show-all",
  "creator-library-backup-create", "clean-reset-preview", "feishu-sync-validate", "feishu-sync-dry-run",
]) {
  assert.match(html, new RegExp(`class="[^"]*secondary-btn[^"]*"[^>]*id="${id}"`), `${id} uses the shared secondary button system`);
}
for (const target of ["mail-follow-up", "campaigns", "accounts"]) {
  assert.match(html, new RegExp(`class="text-btn"[^>]*data-dashboard-v2-open="${target}"`), `${target} uses the compact Dashboard action style`);
}
assert.match(html, /id="settings-accounts-card"/);
assert.match(settings, /settingsCategoryGeneral/);
assert.match(settings, /settingsCategoryAccounts/);
assert.match(settings, /settingsCategoryIntegrations/);
assert.match(settings, /settingsCategoryData/);
assert.match(settings, /settingsCategoryAdvanced/);
assert.match(settings, /category\.hidden = category\.dataset\.settingsCategory !== name/);
assert.match(settings, /showSettingsCategory\(categories, 'General'\)/);
assert.match(settings, /showSettingsCategory\(existingCategories, 'General'\)/);
assert.match(settings, /section\.page\[data-page="settings"\]/);
assert.match(settings, /migrationCard\.hidden = true/);
assert.doesNotMatch(html, /id="creator-library-freshness"/);
assert.match(styles, /\.creator-library-detail-grid > \.detail-panel\[data-detail-panel="overview"\]/);
assert.match(i18n, /settingsCategoryGeneral: "常规"/);
assert.match(i18n, /settingsCategoryGeneral: "General"/);

console.log("UI Phase 2.4A layout contracts: OK");
