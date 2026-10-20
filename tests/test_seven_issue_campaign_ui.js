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
for (const platform of ["TikTok", "Instagram", "YouTube"]) {
  assert.match(
    html,
    new RegExp(`<label class="campaign-platform-choice"><input[^>]*value="${platform}"><span>${platform}</span></label>`),
  );
}
assert.match(styles, /\.campaign-platform-choice\s*\{[^}]*display:\s*inline-flex[^}]*white-space:\s*nowrap/s);
assert.match(styles, /\.campaign-platform-choice\s*>\s*input\[type="checkbox"\][^{]*\{[^}]*width:\s*16px[^}]*height:\s*16px/s);

assert.match(styles, /\.campaign-account-picker\s*\{[^}]*width:\s*100%[^}]*min-width:\s*0/s);
assert.match(styles, /\.campaign-account-options\s*\{[^}]*overflow-x:\s*hidden/s);
assert.match(styles, /\.campaign-account-options\[hidden\]\s*\{\s*display:\s*none/s);
assert.match(styles, /\.campaign-account-option\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*16px\s+minmax\(0,\s*1fr\)[^}]*min-height:\s*40px/s);
assert.match(styles, /\.campaign-account-option span\s*\{[^}]*display:\s*block[^}]*text-overflow:\s*ellipsis[^}]*line-height:\s*1\.4/s);
assert.match(html, /id="campaign-account-options" hidden/);
assert.match(script, /optionsContainer\.hidden = eligible\.length === 0/);
assert.match(script, /picker\.open = false;\s*optionsContainer\?\.replaceChildren\(\)/s);
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
