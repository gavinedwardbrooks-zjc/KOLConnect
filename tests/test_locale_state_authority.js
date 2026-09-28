"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const i18nSource = fs.readFileSync(path.join(root, "webapp", "i18n.js"), "utf8");
const appSource = fs.readFileSync(path.join(root, "webapp", "app.js"), "utf8");
const settingsSource = fs.readFileSync(path.join(root, "webapp", "pages", "settings.js"), "utf8");

function createRuntime() {
  const listeners = new Map();
  const elements = new Map();
  const element = () => ({
    value: "", textContent: "", hidden: false, checked: false, innerHTML: "", children: [],
    classList: { toggle() {} }, append() {}, appendChild() {}, replaceChildren() {}, add() {},
    setAttribute() {}, removeAttribute() {},
    querySelector() { return null; }, querySelectorAll() { return []; }, addEventListener() {},
  });
  const document = {
    title: "",
    documentElement: { lang: "", dataset: {} },
    body: {},
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    createElement() { return element(); },
    createTreeWalker() { return { nextNode: () => false }; },
  };
  let refreshes = 0;
  const window = {
    document,
    localStorage: { getItem() { return null; }, setItem() {} },
    MutationObserver: undefined,
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init.detail; } },
    addEventListener(type, listener) {
      const current = listeners.get(type) || [];
      current.push(listener);
      listeners.set(type, current);
    },
    dispatchEvent(event) { (listeners.get(event.type) || []).forEach(listener => listener(event)); },
    KOLConnectPages: { refreshCurrent() { refreshes += 1; return Promise.resolve(); } },
  };
  const context = {
    window, document, console, Option: class Option {}, Node: { ELEMENT_NODE: 1 },
    NodeFilter: { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 }, setInterval() { return 0; },
    clearInterval() {}, setTimeout, clearTimeout,
  };
  vm.runInNewContext(i18nSource, context);
  vm.runInNewContext(`${appSource}\nwindow.__localeAuthorityTest = { renderSettingsState, state };`, context);
  return { window, elements, getRefreshes: () => refreshes };
}

function statePayload(language) {
  return {
    ui: { language, debug_mode: false }, profiles: [], selectedProfile: "Default",
    feishu: {}, google_sheets: {}, creator_library: {},
  };
}

const runtime = createRuntime();
const testApi = runtime.window.__localeAuthorityTest;

// Startup applies the persisted choice exactly once.
testApi.renderSettingsState(statePayload("zh-CN"));
assert.equal(runtime.window.KOLConnectI18n.getLocale(), "zh");
assert.equal(runtime.elements.get("ui-language").value, "zh");
for (const [key, value] of Object.entries({
  navDiscoverCreators: "发现达人", navCreatorLibrary: "达人库", navPartnerships: "合作管理",
  navSettings: "设置", navAccounts: "Chrome 账号", navMailAccounts: "邮箱账户",
  navLogs: "日志", settingsTitle: "设置", uiSettingsTitle: "界面设置", uiLanguage: "界面语言",
  defaultProfile: "默认 Profile", saveUi: "保存界面设置", mailFollowupTitle: "邮件跟进",
  dashboardViewAll: "查看全部", mailFollowupWaitingMe: "待我回复",
  mailFollowupWaitingCreator: "待对方回复", mailFollowupWaitingUnknown: "状态未知",
  dashboardCreatorUnitLabel: "位达人", dashboardCreatorAccountUnitLabel: "个平台账号",
})) assert.equal(runtime.window.KOLConnectI18n.t(key), value, `Chinese ${key} must not fall back to English`);

// This is the packaged-app failure sequence: user chooses English, then an
// older async /api/state response arrives while Settings is still mounted.
runtime.window.KOLConnectApp.setLanguage("English");
assert.equal(runtime.window.KOLConnectI18n.getLocale(), "en");
assert.equal(runtime.elements.get("ui-language").value, "en");
for (const [key, value] of Object.entries({
  navDiscoverCreators: "Discover Creators", navCreatorLibrary: "Creator Library", navPartnerships: "Partnerships",
  navSettings: "Settings", navAccounts: "Accounts", navMailAccounts: "Mail Accounts", navLogs: "Logs",
  settingsTitle: "Settings", uiSettingsTitle: "UI settings", uiLanguage: "Language",
  defaultProfile: "Default profile", saveUi: "Save UI settings", mailFollowupTitle: "Mail Follow-up",
  dashboardViewAll: "View all", mailFollowupWaitingMe: "Waiting for Me",
  mailFollowupWaitingCreator: "Waiting for Creator", mailFollowupWaitingUnknown: "Status Unknown",
})) assert.equal(runtime.window.KOLConnectI18n.t(key), value, `English ${key} must not fall back to Chinese`);
testApi.renderSettingsState(statePayload("zh"));
assert.equal(runtime.window.KOLConnectI18n.getLocale(), "en", "a stale settings response must not revert the active locale");
assert.equal(runtime.elements.get("ui-language").value, "en", "reopening Settings preserves the selected locale");
assert.ok(runtime.getRefreshes() >= 1, "locale change refreshes the mounted page through the central event");

runtime.window.KOLConnectApp.setLanguage("zh");
testApi.renderSettingsState(statePayload("en"));
assert.equal(runtime.window.KOLConnectI18n.getLocale(), "zh", "the reverse stale response also cannot override a user choice");

const englishStartup = createRuntime();
englishStartup.window.__localeAuthorityTest.renderSettingsState(statePayload("en-US"));
assert.equal(englishStartup.window.KOLConnectI18n.getLocale(), "en", "a persisted English preference initializes a fresh runtime");
assert.equal(englishStartup.elements.get("ui-language").value, "en");

// Settings changes update the central runtime first without tearing down the
// current Settings page's request signal; persistence then reloads the page.
assert.match(settingsSource, /const language = app\.valueOf\("ui-language"\)/);
assert.match(settingsSource, /app\.setLanguage\(language, \{ refreshCurrent: false \}\)[\s\S]*?api\.post\("\/api\/settings\/ui", \{[\s\S]*?language,/);
assert.match(settingsSource, /await reloadSettings\(\)/);
assert.match(settingsSource, /app\.setLanguage\(app\.valueOf\("ui-language"\), \{ refreshCurrent: false \}\)/);

console.log("Locale state authority and async hydration regression: OK");
