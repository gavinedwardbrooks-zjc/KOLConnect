"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const read = relativePath => fs.readFileSync(path.join(ROOT, relativePath), "utf8");

function count(source, fragment) {
  return source.split(fragment).length - 1;
}

function testInformationArchitectureAndSingleMailAccountForm() {
  const html = read("webapp/index.html");
  const primaryLabels = [...html.matchAll(/class="nav-btn nav-primary[^>]*>([^<]+)<\/button>/g)]
    .map(match => match[1].trim());
  assert.deepEqual(primaryLabels, ["工作台", "发现达人", "达人库", "合作管理", "设置"]);
  const secondaryByPrimary = primary => [...html.matchAll(new RegExp(`class="nav-btn nav-sub"[^>]*data-primary="${primary}"[^>]*>([^<]+)<\\/button>`, "g"))]
    .map(match => match[1].trim());
  assert.deepEqual(secondaryByPrimary("scrape"), ["邮箱抓取", "审核结果", "链接清洗"]);
  assert.deepEqual(secondaryByPrimary("mail"), ["产品", "Agency", "Campaign", "邮件"]);
  assert.deepEqual(secondaryByPrimary("settings"), ["Chrome 账号", "邮箱账户", "日志"]);
  assert.match(html, /data-page="scrape" data-primary="scrape"[^>]*>邮箱抓取</);
  assert.match(html, /data-page="mail-accounts" data-primary="settings">邮箱账户</);
  assert.equal(count(html, 'id="mail-accounts-list"'), 1, "mail account form must have one owner");
  assert.equal(count(html, 'id="mail-add-account"'), 1);
  assert.match(html, /data-page="mail"[\s\S]*id="mail-inbox-sync"/);
  assert.match(html, /data-page="mail-accounts"[\s\S]*id="mail-accounts-list"/);
}

function testWorkflowMarkup() {
  const html = read("webapp/index.html");
  const source = read("webapp/app.js");
  assert.match(html, /id="task-link-counts"/);
  assert.match(html, /class="platform-multiselect"/);
  assert.match(source, /\.task-platform-option:checked/);
  assert.match(source, /platforms: selectedTaskPlatforms\(\)/);
  assert.match(html, /id="discover-count-input"/);
  assert.match(html, /id="discover-detail-body"/);
  assert.match(html, /id="discover-status-filter"/);
  assert.match(source, /renderDiscoverResults\(data\)/);
  assert.match(source, /标准化后重复|duplicate_of_line/);
  const reviewToolbar = html.match(/<div class="review-toolbar">([\s\S]*?)<p class="hint" id="review-summary">/)[1];
  assert.match(reviewToolbar, /id="review-task-select"/);
  assert.match(reviewToolbar, /id="review-search"/);
  assert.match(reviewToolbar, /id="review-page-size"/);
  assert.match(reviewToolbar, /id="review-refresh"/);
  assert.match(reviewToolbar, /id="review-scan-missing-email"/);
  assert.match(reviewToolbar, /id="review-retry-failed"/);
  assert.equal(count(reviewToolbar, 'class="primary-btn"'), 1);
  assert.match(reviewToolbar, /id="review-sync-four-tables"/);
}

class ClassList {
  constructor(...values) { this.values = new Set(values); }
  contains(value) { return this.values.has(value); }
  toggle(value, enabled) { enabled ? this.values.add(value) : this.values.delete(value); }
}

async function testSecondaryNavigationFollowsActivePrimary() {
  const buttons = [];
  const sections = [];
  const subNav = { hidden: false };
  const addButton = (page, primary, kind) => {
    const button = { dataset: { page, primary }, classList: new ClassList(`nav-${kind}`), hidden: false };
    buttons.push(button);
    return button;
  };
  addButton("dashboard", "dashboard", "primary");
  addButton("scrape", "scrape", "primary");
  addButton("mail", "mail", "primary");
  addButton("settings", "settings", "primary");
  const scrape = addButton("scrape", "scrape", "sub");
  const products = addButton("products", "mail", "sub");
  const accounts = addButton("accounts", "settings", "sub");
  const document = {
    querySelector(selector) {
      if (selector === ".sub-nav") return subNav;
      const match = selector.match(/data-page="([^"]+)"/);
      return match ? buttons.find(button => button.dataset.page === match[1]) || null : null;
    },
    querySelectorAll(selector) {
      if (selector === ".nav-btn") return buttons;
      if (selector === ".page") return sections;
      return [];
    },
  };
  const sandbox = { window: {}, document, console };
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-registry.js"), sandbox);
  const page = { load() {}, bind() {}, unbind() {} };
  ["dashboard", "scrape", "products", "accounts"].forEach(name => sandbox.window.KOLConnectPages.registerPage(name, page));

  await sandbox.window.KOLConnectPages.navigate("dashboard");
  assert.equal(subNav.hidden, true);
  assert.equal(scrape.hidden, true);
  await sandbox.window.KOLConnectPages.navigate("products");
  assert.equal(products.hidden, false);
  assert.equal(scrape.hidden, true);
  assert.equal(accounts.hidden, true);
  assert.equal(products.classList.contains("active"), true);
}

async function run() {
  testInformationArchitectureAndSingleMailAccountForm();
  testWorkflowMarkup();
  await testSecondaryNavigationFollowsActivePrimary();
  console.log("M4.8 UX consolidation tests passed");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
