const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const read = relativePath => fs.readFileSync(path.join(root, relativePath), "utf8");

const html = read("webapp/index.html");
const script = read("webapp/pages/campaign-detail.js");
const styles = read("webapp/styles.css");
const i18n = read("webapp/i18n.js");

assert.match(styles, /\.campaign-platform-field\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/s);
assert.match(styles, /\.campaign-choice-list label\s*\{[^}]*min-width:\s*max-content[^}]*white-space:\s*nowrap/s);

assert.match(styles, /\.campaign-account-picker\s*\{[^}]*width:\s*100%[^}]*min-width:\s*0/s);
assert.match(styles, /\.campaign-account-options\s*\{[^}]*overflow-x:\s*hidden/s);
assert.match(styles, /\.campaign-account-option span\s*\{[^}]*text-overflow:\s*ellipsis/s);
assert.match(html, /id="campaign-creator-account-id"[^>]*multiple[^>]*hidden/);

const supportedCurrencies = [
  "USD", "CNY", "BRL", "EUR", "GBP", "JPY", "KRW", "HKD", "TWD",
  "SGD", "AUD", "CAD", "MXN", "SAR", "AED", "INR", "IDR", "THB",
  "VND", "PHP", "MYR", "TRY", "ZAR",
];
for (const currency of supportedCurrencies) {
  assert.match(script, new RegExp(`${currency}:\\s*"campaignDetailCurrency`));
}
assert.equal((script.match(/:\s*"campaignDetailCurrency[A-Za-z]+"/g) || []).length, 23);
for (const key of [
  "Hkd", "Twd", "Sgd", "Aud", "Cad", "Mxn", "Sar", "Aed", "Inr", "Idr",
  "Thb", "Vnd", "Php", "Myr", "Try", "Zar",
]) {
  assert.match(i18n, new RegExp(`campaignDetailCurrency${key}:\\s*"[^"\\r\\n]+"`));
}

assert.match(html, /<label class="campaign-decision-control">\s*<input id="campaign-creator-need-my-decision"[^>]*>\s*<span/s);
assert.match(styles, /\.campaign-decision-control\s*\{[^}]*display:\s*inline-flex[^}]*white-space:\s*nowrap/s);

assert.match(script, /actionRow\.className\s*=\s*"campaign-creator-action-row"/);
assert.match(script, /actionRow\.appendChild\(editButton\)/);
assert.match(script, /actionRow\.appendChild\(removeButton\)/);
assert.match(styles, /\.campaign-creator-action-row\s*\{[^}]*display:\s*inline-flex[^}]*white-space:\s*nowrap/s);

console.log("Seven-issue Campaign UI regression tests passed.");
