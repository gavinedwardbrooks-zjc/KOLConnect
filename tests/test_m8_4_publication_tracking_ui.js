"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const page = fs.readFileSync(path.join(root, "webapp", "pages", "campaign-detail.js"), "utf8");

assert.match(html, /id="campaign-publication-performance-list"/);
assert.match(html, /id="campaign-publications-refresh-all"/);
assert.match(html, /发布内容表现/);
assert.match(page, /hydrateLatestPublicationObservations/);
assert.match(page, /campaignPerformance\?\.publications/);
assert.match(page, /publications\/\$\{encodeURIComponent\(publicationId\)\}\/refresh/);
assert.match(page, /campaigns\/\$\{encodeURIComponent\(campaignId\)\}\/publication-capture-batches/);
assert.match(page, /X-KOLConnect-Publication-Capture-CSRF/);
assert.match(page, /schedulePublicationBatchPoll/);
assert.match(page, /value === null \|\| value === undefined \|\| value === "" \? "—"/);
assert.match(page, /result\.status === "SUCCESS"/);
assert.match(html, /一键更新全部视频/);
assert.doesNotMatch(html, /publication-performance-chart/);
assert.doesNotMatch(page, /setInterval\s*\(/);

console.log("M8.4 publication tracking UI tests passed");
