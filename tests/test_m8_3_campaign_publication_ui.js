"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const page = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8");

assert.match(html, /id="campaign-publication-list"/);
assert.match(html, /实际发布内容/);
assert.match(html, /计划发布账号/);
assert.match(html, /计划发布日期/);
assert.match(page, /publication-row/);
assert.match(page, /actual_publish_url/);
assert.match(page, /actual_account_id/);
assert.match(page, /actual_published_at/);
assert.match(page, /campaign-publication-add/);
assert.doesNotMatch(page, /planned_publish_dates:\s*publication/);

console.log("M8.3 Campaign publication UI tests passed");
