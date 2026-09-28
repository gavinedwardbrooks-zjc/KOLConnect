"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "webapp", "i18n.js"), "utf8");
const appSource = fs.readFileSync(path.join(root, "webapp", "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");

const listeners = [];
const document = {
  documentElement: { lang: "", dataset: {} },
  body: {},
  querySelectorAll: () => [],
  createTreeWalker: () => ({ nextNode: () => false }),
};
const window = {
  document,
  MutationObserver: undefined,
  CustomEvent: class CustomEvent { constructor(name, init) { this.name = name; this.detail = init.detail; } },
  dispatchEvent(event) { listeners.push(event); },
};
vm.runInNewContext(source, { window, document, Node: { ELEMENT_NODE: 1 }, NodeFilter: { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 } });

const i18n = window.KOLConnectI18n;
i18n.register({
  zh: { testKey: "中文界面", parameterized: "共 {count} 条" },
  en: { testKey: "English UI", parameterized: "{count} items" },
});

assert.equal(i18n.setLocale("en"), "en");
assert.equal(i18n.t("testKey"), "English UI");
assert.equal(i18n.t("parameterized", { count: 3 }), "3 items");
assert.match(i18n.t("missing.key"), /^\[missing:missing\.key\]$/);
assert.equal(document.documentElement.lang, "en");

assert.equal(i18n.setLocale("zh"), "zh");
assert.equal(i18n.t("testKey"), "中文界面");
assert.equal(i18n.t("parameterized", { count: 3 }), "共 3 条");
assert.equal(listeners.length, 2, "each explicit language switch must notify mounted pages");

// The literal fallback serves unkeyed legacy UI chrome.  Its source map is
// Chinese-to-English, so it must be selected by the target locale, not by its
// source locale.  This catches the packaged mixed-language regression.
assert.equal(i18n.setLocale("en-US"), "en");
assert.equal(i18n.text("查看全部"), "View All");
assert.equal(i18n.setLocale("中文"), "zh");
assert.equal(i18n.text("View All"), "查看全部");

const hydrationListeners = [];
const hydrationWindow = {
  document: { documentElement: { lang: "", dataset: {} }, body: {}, querySelectorAll: () => [], createTreeWalker: () => ({ nextNode: () => false }) },
  MutationObserver: undefined,
  CustomEvent: class CustomEvent { constructor(name, init) { this.name = name; this.detail = init.detail; } },
  dispatchEvent(event) { hydrationListeners.push(event); },
};
vm.runInNewContext(source, {
  window: hydrationWindow,
  document: hydrationWindow.document,
  Node: { ELEMENT_NODE: 1 },
  NodeFilter: { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 },
});
const hydratedI18n = hydrationWindow.KOLConnectI18n;
assert.equal(hydratedI18n.hydrateLocale("zh-CN"), "zh", "startup initializes from persisted settings once");
assert.equal(hydratedI18n.setLocale("English"), "en", "a user choice becomes the runtime authority");
assert.equal(hydratedI18n.hydrateLocale("zh"), "en", "a delayed stale settings response cannot revert English");
assert.equal(hydratedI18n.getLocale(), "en");

// Compatibility literal conversion must be opt-in. Dynamic business data can
// collide with a localized UI phrase and must remain byte-for-byte unchanged.
class FakeElement {
  constructor({ textContent = "", i18nKey = "", literal = false } = {}) {
    this.nodeType = 1;
    this.textContent = textContent;
    this.dataset = i18nKey ? { i18n: i18nKey } : {};
    this.literal = literal;
  }
  matches(selector) {
    return selector === "[data-i18n-literal]" && this.literal;
  }
  querySelectorAll(selector) {
    return selector === "[data-i18n]" && this.dataset.i18n ? [this] : [];
  }
  getAttribute() { return null; }
  setAttribute() {}
}
const runtimeDocument = {
  documentElement: { lang: "", dataset: {} },
  body: {},
  querySelectorAll: () => [],
  createTreeWalker: () => ({ nextNode: () => false }),
};
const runtimeWindow = {
  document: runtimeDocument,
  MutationObserver: undefined,
  CustomEvent: class CustomEvent { constructor(name, init) { this.name = name; this.detail = init.detail; } },
  dispatchEvent() {},
};
vm.runInNewContext(source, {
  window: runtimeWindow,
  document: runtimeDocument,
  Node: { ELEMENT_NODE: 1 },
  NodeFilter: { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 },
});
const runtimeI18n = runtimeWindow.KOLConnectI18n;
runtimeI18n.setLocale("en");
for (const name of ["产品列表", "联系人", "设置", "产品名称", "刷新列表"]) {
  const dynamicTitle = new FakeElement({ textContent: name });
  runtimeI18n.apply(dynamicTitle);
  assert.equal(dynamicTitle.textContent, name, `dynamic user data must not be localized: ${name}`);
}
const staticChrome = new FakeElement({ textContent: "产品列表", i18nKey: "productListTitle" });
runtimeI18n.apply(staticChrome);
assert.equal(staticChrome.textContent, "Product List", "explicit static chrome remains localized");
assert.match(fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8"), /campaign-detail-title"\)\.textContent = campaign\?\.name/);
assert.match(fs.readFileSync(path.join(root, "webapp", "pages", "agencies.js"), "utf8"), /agency-detail-title"\)\.textContent = text\(agency\.name/);
assert.match(fs.readFileSync(path.join(root, "webapp", "pages", "creator-library-detail.js"), "utf8"), /creator_name/);
assert.match(source, /node\.matches\?\.\("\[data-i18n-literal\]"\)/);
assert.doesNotMatch(source, /\.nav-btn, th, label, h1, h2, h3/);

const staticKeys = [...html.matchAll(/data-i18n(?:-placeholder|-aria-label)?="([^"]+)"/g)].map(match => match[1]);
const dictionaries = i18n.getDictionaries();
for (const key of Object.keys(dictionaries.zh)) {
  assert.ok(dictionaries.en[key], `central English dictionary is missing ${key}`);
  assert.notEqual(dictionaries.en[key], "", `central English dictionary has a blank ${key}`);
}
for (const key of Object.keys(dictionaries.en)) {
  assert.ok(dictionaries.zh[key], `central Chinese dictionary is missing ${key}`);
  assert.notEqual(dictionaries.zh[key], "", `central Chinese dictionary has a blank ${key}`);
}
for (const key of staticKeys) {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  assert.ok(
    dictionaries.zh[key] || new RegExp(`\\b${escaped}\\s*:`).test(appSource),
    `missing dictionary source for ${key}`,
  );
}
assert.match(html, /data-i18n="navDiscoverCreators"/);
assert.match(html, /data-i18n="navMailFollowUp"/);
assert.match(fs.readFileSync(path.join(root, "webapp", "core", "page-registry.js"), "utf8"), /refreshCurrent\(\)/);
assert.match(fs.readFileSync(path.join(root, "webapp", "pages", "mail-follow-up.js"), "utf8"), /mailFollowupWaitingMe/);
assert.doesNotMatch(fs.readFileSync(path.join(root, "webapp", "pages", "mail-follow-up.js"), "utf8"), /textContent = "待我回复"/);

const settingsSource = fs.readFileSync(path.join(root, "webapp", "pages", "settings.js"), "utf8");
const mailFollowupSource = fs.readFileSync(path.join(root, "webapp", "pages", "mail-follow-up.js"), "utf8");
for (const source of [settingsSource, mailFollowupSource]) {
  const keys = [...source.matchAll(/\bt\("([A-Za-z][A-Za-z0-9]+)"/g)].map(match => match[1]);
  for (const key of new Set(keys)) {
    assert.ok(dictionaries.zh[key], `Chinese dictionary is missing ${key}`);
    assert.ok(dictionaries.en[key], `English dictionary is missing ${key}`);
  }
}
assert.doesNotMatch(settingsSource, /[\u4e00-\u9fff]/, "Settings runtime UI must use explicit i18n keys");
assert.doesNotMatch(mailFollowupSource, /[\u4e00-\u9fff]/, "Mail Follow-up runtime UI must use explicit i18n keys");
assert.match(html, /data-page="mail-follow-up"[\s\S]*data-i18n="mailFollowupTitle"/);
assert.match(html, /data-page="settings"[\s\S]*data-i18n="settingsSystemTools"/);
assert.match(appSource, /mailGoogleFollowupSynced/);
assert.match(appSource, /mailPageSummary/);
assert.match(appSource, /CONNECTED: "settingsConnected"/);
assert.doesNotMatch(appSource, /CONNECTED: "已连接"/);

const creatorLibrarySource = fs.readFileSync(path.join(root, "webapp", "pages", "creator-library.js"), "utf8");
const creatorKeys = [...creatorLibrarySource.matchAll(/\bt\("(creator(?:Library|Delete|Import|Status|Trend)[A-Za-z0-9]+)"/g)]
  .map(match => match[1]);
for (const key of new Set(creatorKeys)) {
  assert.ok(dictionaries.zh[key], `Creator Library key ${key} must have a Chinese value`);
  assert.ok(dictionaries.en[key], `Creator Library key ${key} must have an English value`);
}
assert.doesNotMatch(creatorLibrarySource, /[\u4e00-\u9fff]/, "Creator Library runtime UI must use explicit i18n keys");

const campaignDetailSource = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8");
const campaignDetailKeys = [...campaignDetailSource.matchAll(/\bt\("(campaignDetail[A-Za-z0-9]+)"/g)]
  .map(match => match[1]);
for (const key of new Set(campaignDetailKeys)) {
  assert.ok(dictionaries.zh[key], `Campaign Detail key ${key} must have a Chinese value`);
  assert.ok(dictionaries.en[key], `Campaign Detail key ${key} must have an English value`);
}
const campaignDetailMarkup = html.match(/<section class="page" data-page="campaign-detail">[\s\S]*?<\/section>\s*<section class="page workspace-narrow" data-page="mail">/)?.[0] || "";
const campaignDetailStaticKeys = [...campaignDetailMarkup.matchAll(/data-i18n="(campaignDetail[A-Za-z0-9]+)"/g)].map(match => match[1]);
for (const key of new Set(campaignDetailStaticKeys)) {
  assert.ok(dictionaries.zh[key], `Campaign Detail static key ${key} must have a Chinese value`);
  assert.ok(dictionaries.en[key], `Campaign Detail static key ${key} must have an English value`);
}
assert.doesNotMatch(campaignDetailSource, /[\u4e00-\u9fff]/, "Campaign Detail runtime UI must use explicit i18n keys");
assert.match(html, /data-page="campaign-detail"[\s\S]*data-i18n="campaignDetailTitle"/);

const discoveryKeys = [
  "discoveryContinue", "discoveryViewOriginal", "reviewUnnamedCreator", "reviewStatusSummary",
  "emailStatusNotFound", "emailStatusUnavailable", "emailStatusConflict", "emailReviewSelected",
  "taskDetailSummary", "taskDetailDeleteConfirm", "linkStatusNormalized", "linkEmailDuplicate",
  "emailEnrichmentTitle", "linkTitle",
];
for (const key of discoveryKeys) {
  const occurrences = appSource.match(new RegExp(`\\b${key}\\s*:`, "g")) || [];
  assert.equal(occurrences.length, 2, `Discovery key ${key} must be present in both locale dictionaries`);
}
assert.match(html, /data-page="scrape"[\s\S]*data-i18n="emailEnrichmentTitle"/);
assert.match(html, /data-page="review"[\s\S]*data-i18n="reviewFilter"/);
assert.match(html, /data-page="task-details"[\s\S]*option value="已完成" data-i18n="taskDetailCompleted"/);
assert.match(html, /data-page="discover"[\s\S]*data-i18n="linkTitle"/);
assert.match(appSource, /email_not_found:\s*t\("emailStatusNotFound"\)/);
assert.match(appSource, /reviewField\(record, "creator_name"\)[\s\S]*t\("reviewUnnamedCreator"\)/);
assert.match(appSource, /function taskDetailStatusLabel\(status\)/);
assert.match(appSource, /taskDetailStatusLabel\(item\.status\)/);
assert.match(appSource, /function refreshDiscoveryLocale\(\)/);
assert.match(appSource, /refreshDiscoveryLocale\(\);/);
assert.match(appSource, /i18n\?\.hydrateLocale\(data\.ui\?\.language\)/, "settings hydration must delegate to the central locale authority");
assert.doesNotMatch(appSource, /state\.language\s*=\s*data\.ui\?\.language/, "late settings responses must not directly replace runtime locale");
assert.match(appSource, /addEventListener\("kolconnect:localechange"/, "mounted pages must refresh from the central locale event");
assert.match(source, /locale === "en" \? literals\.zh : literals\.en/, "literal fallback direction must match the target locale");
assert.equal(dictionaries.zh.dashboardCreatorUnitLabel, "位达人");
assert.equal(dictionaries.zh.dashboardCreatorAccountUnitLabel, "个平台账号");

console.log("Central i18n runtime contract: OK");
