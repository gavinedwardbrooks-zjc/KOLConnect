"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const read = relativePath => fs.readFileSync(path.join(root, relativePath), "utf8");
const i18nSource = read("webapp/i18n.js");
const html = read("webapp/index.html");
const appSource = read("webapp/app.js");
const productSource = read("webapp/pages/products.js");
const agencySource = read("webapp/pages/agencies.js");
const campaignSource = read("webapp/pages/campaigns.js");

function createI18n() {
  const document = {
    documentElement: { lang: "", dataset: {} }, body: {}, querySelectorAll: () => [],
    createTreeWalker: () => ({ nextNode: () => false }),
  };
  const window = {
    document, MutationObserver: undefined,
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init.detail; } },
    dispatchEvent() {},
  };
  vm.runInNewContext(i18nSource, {
    window, document, Node: { ELEMENT_NODE: 1 },
    NodeFilter: { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 },
  });
  return window.KOLConnectI18n;
}

function pageMarkup(page) {
  const match = new RegExp(`<section[^>]+data-page="${page}"[^>]*>`).exec(html);
  assert.ok(match, `${page} page must exist`);
  const start = match.index;
  const next = html.indexOf("<section class=\"page", start + 1);
  return html.slice(start, next < 0 ? html.length : next);
}

function assertKeys(i18n, keys, locale, expected) {
  i18n.setLocale(locale);
  for (const [key, value] of Object.entries(expected)) {
    assert.equal(i18n.t(key), value, `${locale} ${key}`);
  }
  for (const key of keys) {
    const value = i18n.t(key);
    assert.ok(!value.startsWith("[missing:"), `${locale} ${key} must resolve`);
    if (locale === "en") assert.doesNotMatch(value, /[\u4e00-\u9fff]/, `${key} must not contain Chinese in English mode`);
  }
}

function assertPageUsesExplicitKeys(page, keys) {
  const markup = pageMarkup(page);
  for (const key of keys) {
    assert.match(markup, new RegExp(`data-i18n(?:-placeholder|-aria-label)?="${key}"`), `${page} must use ${key}`);
  }
}

const i18n = createI18n();
const productKeys = [
  "productEyebrow", "productTitle", "productSubtitle", "productShowArchived", "productListTitle",
  "productNameLabel", "productCompanyNameLabel", "productCampaignCountLabel", "productCreatedAtLabel", "productUpdatedAtLabel",
];
const agencyKeys = [
  "agencyEyebrow", "agencyTitle", "agencySubtitle", "agencyRefreshList", "agencyAssociatedCreators",
  "agencyContactsLabel", "agencyListTitle", "agencyCountryRegion", "agencyUpdatedAt",
];
const campaignKeys = [
  "campaignEyebrow", "campaignTitle", "campaignSubtitle", "campaignProductLabel", "campaignStatusLabel",
  "campaignAllActiveStatuses", "campaignStartDateLabel", "campaignEndDateLabel", "campaignShowArchived",
  "campaignApplyFilters", "campaignListTitle", "campaignNameLabel", "campaignCreatorCountLabel",
  "campaignBusinessStatusLabel", "campaignArchiveStatusLabel", "campaignBudgetLabel",
];
const accountKeys = [
  "accountsTitle", "accountsSubtitle", "accountsConfigurationTitle", "refreshProfiles", "addAccountConfiguration",
  "saveAccounts", "accountsProfileLabel", "alias", "notes", "accountsOpenBrowser", "accountsRemoveConfiguration",
];

assertPageUsesExplicitKeys("products", productKeys);
assertPageUsesExplicitKeys("agencies", agencyKeys);
assertPageUsesExplicitKeys("campaigns", campaignKeys);
assertPageUsesExplicitKeys("accounts", accountKeys.slice(0, 6));

assertKeys(i18n, productKeys, "en", {
  productSubtitle: "Manage product information and view the number of Campaigns associated with each product.",
  productShowArchived: "Show Archived", productListTitle: "Product List", productNameLabel: "Product Name",
  productCompanyNameLabel: "Company Name", productCampaignCountLabel: "Campaign Count",
  productCreatedAtLabel: "Created At", productUpdatedAtLabel: "Updated At",
});
assertKeys(i18n, agencyKeys, "en", {
  agencySubtitle: "View partner agencies, contact coverage, and associated creator resources.",
  agencyRefreshList: "Refresh List", agencyAssociatedCreators: "Associated Creators", agencyContactsLabel: "Contacts",
  agencyListTitle: "Agency List",
});
assertKeys(i18n, campaignKeys, "en", {
  campaignSubtitle: "Manage creator partnership campaigns by product and status, with centralized views of budget, schedule, and ownership.",
  campaignAllActiveStatuses: "All Active Statuses", campaignStartDateLabel: "Start Date", campaignEndDateLabel: "End Date",
  campaignShowArchived: "Show Archived", campaignApplyFilters: "Apply Filters", campaignListTitle: "Campaign List",
  campaignNameLabel: "Campaign Name", campaignCreatorCountLabel: "Creators", campaignBusinessStatusLabel: "Business Status",
  campaignArchiveStatusLabel: "Archive Status", campaignBudgetLabel: "Budget",
});
assertKeys(i18n, accountKeys, "en", {
  accountsSubtitle: "Manage Chrome Profile configurations used for creator discovery. Deleting a configuration does not delete browser data.",
  accountsConfigurationTitle: "Chrome Profile Configuration", refreshProfiles: "Refresh Chrome Accounts",
  addAccountConfiguration: "+ Add Account Configuration", saveAccounts: "Save Account Configuration",
  alias: "Alias", notes: "Notes", accountsOpenBrowser: "Open Browser", accountsRemoveConfiguration: "Remove Configuration",
});

assert.equal(i18n.t("productCount", { count: 1, plural: "" }), "1 product");
assert.equal(i18n.t("productCount", { count: 2, plural: "s" }), "2 products");
assert.equal(i18n.t("agencyCount", { count: 1, pluralY: "y" }), "1 agency");
assert.equal(i18n.t("agencyCount", { count: 2, pluralY: "ies" }), "2 agencies");
assert.equal(i18n.t("agencyContacts", { count: 1, plural: "" }), "1 contact");
assert.equal(i18n.t("agencyCreators", { count: 0, plural: "s" }), "0 creators");
assert.equal(i18n.t("campaignListCount", { count: 1, plural: "" }), "1 Campaign");
assert.equal(i18n.t("campaignListCount", { count: 2, plural: "s" }), "2 Campaigns");

assertKeys(i18n, productKeys, "zh", { productTitle: "产品", productListTitle: "产品列表" });
assertKeys(i18n, agencyKeys, "zh", { agencyAssociatedCreators: "已关联达人", agencyContactsLabel: "联系人" });
assertKeys(i18n, campaignKeys, "zh", { campaignStartDateLabel: "开始日期", campaignApplyFilters: "应用筛选" });
assertKeys(i18n, accountKeys, "zh", { accountsConfigurationTitle: "Chrome Profile 配置", alias: "备注名" });

const renderAccounts = appSource.match(/function renderAccounts\(accounts\) \{[\s\S]*?function getMailProviderOptions/)?.[0] || "";
assert.ok(renderAccounts, "Chrome Account renderer must exist");
assert.doesNotMatch(renderAccounts, /[\u4e00-\u9fff]/, "Chrome Account renderer must use i18n keys for UI chrome");
assert.match(renderAccounts, /t\("accountsOpenBrowser"\)/);
assert.match(renderAccounts, /t\("accountsRemoveConfiguration"\)/);
assert.match(renderAccounts, /t\("alias"\)/);

assert.match(productSource, /productCount", \{ count: products\.length, plural: products\.length === 1 \? "" : "s" \}/);
assert.match(agencySource, /pluralY: agencies\.length === 1 \? "y" : "ies"/);
assert.match(campaignSource, /campaignListCount", \{ count: campaigns\.length, plural: campaigns\.length === 1 \? "" : "s" \}/);
assert.match(productSource, /getLocale\?\.\(\) === "en" \? "en-US" : "zh-CN"/);
assert.match(agencySource, /getLocale\?\.\(\) === "en" \? "en-US" : "zh-CN"/);
assert.match(i18nSource, /document\.documentElement\.lang = locale === "en" \? "en" : "zh-CN"/);

console.log("Four-page English residual localization regression: OK");
