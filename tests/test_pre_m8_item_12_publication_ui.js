const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const script = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8");

assert.match(html, /计划发布账号/);
assert.match(html, /id="campaign-account-picker"/);
assert.match(html, /id="campaign-account-summary"/);
assert.match(html, /id="campaign-account-options"/);
assert.doesNotMatch(html, /<option value="">请选择一个或多个执行账号<\/option>/);
assert.match(html, /计划发布日期/);
assert.match(html, /实际发布内容/);
assert.match(html, /id="campaign-publication-list"/);
assert.match(html, /id="campaign-publication-add"/);
assert.match(script, /actual_publish_url/);
assert.match(script, /actual_account_id/);
assert.match(script, /actual_published_at/);
assert.match(script, /observed_at/);
assert.match(script, /publications:\s*publicationPayload\(\)|publications,/);
assert.match(script, /publish_links:\s*publications\.map/);
assert.match(script, /option\.selected = checkbox\.checked/);
assert.match(script, /已选择 \$\{selected\.length\} 个账号/);
assert.match(script, /campaign-account-option\$\{checkbox\.checked \? " is-selected"/);
assert.match(script, /!picker\.contains\(event\.target\).*picker\.open = false/);

console.log("PRE-M8 Item #12 actual publication UI contract: PASS");
