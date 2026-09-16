"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(ROOT, "webapp", "app.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "webapp", "index.html"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "webapp", "styles.css"), "utf8");

assert.match(app, /function openContinueScrapeDialog\(task\)/);
assert.match(app, /const unfinished = entries\.filter\(item => item\.unfinished > 0\)/);
assert.match(app, /taskId: task\.id[\s\S]*platforms/);
assert.match(app, /task\.task_type === "manual" && hasRunnableLinks/);
assert.match(app, /viewOriginal\.textContent = "查看原始链接"/);
assert.match(app, /scope=\$\{scope\}/);
assert.match(app, /copyTaskLinks\("all"\)/);
assert.match(app, /copyTaskLinks\("unfinished"\)/);
assert.doesNotMatch(app, /const canContinue = task\.status !== "completed"/);

assert.match(html, />账号主页<\/th>/);
assert.match(app, /function readableAccountHomepage/);
assert.match(app, /link\.textContent = readableAccountHomepage\(profileUrl\)/);
assert.match(app, /link\.href = profileUrl/);
assert.doesNotMatch(html, /reviewAccountUid/);
assert.match(css, /\.account-homepage-link[\s\S]*text-overflow:\s*ellipsis/);

for (const value of ["task", "review_results", "creator_library", "manual"]) {
  assert.match(html, new RegExp(`name="email-source" value="${value}"`));
}
assert.match(html, /name="email-scope" value="missing" checked/);
assert.match(app, /\/api\/tasks\/email-recheck\/candidates/);
assert.match(app, /\/api\/tasks\/email-recheck\/scan/);
assert.match(app, /\/api\/creator-library\/email-capture/);
assert.match(app, /email_not_found:\s*"未找到"/);
assert.match(app, /capture_failed:\s*"页面无法访问"/);
assert.match(app, /email_conflict:\s*"邮箱冲突，未覆盖"/);
assert.match(app, /item\.email_source \|\| "—"/);
assert.match(app, /cell\.textContent = value/);
assert.doesNotMatch(html, /account_uid/);

assert.match(html, /查看待补充范围/);
assert.match(app, /function openReviewEmailEnrichment/);
assert.match(app, /value="review_results"/);
assert.match(app, /默认仅处理缺少邮箱的账号/);
assert.match(html, /<option value="attention" selected>待补充<\/option>/);
assert.match(html, /<th>待补充<\/th>/);
assert.doesNotMatch(html, /id="capture-mode"|id="capture-manual-panel"|id="manual-task-create"/);
assert.doesNotMatch(html, /id="creator-analysis-panel"|id="review-view-analysis"/);

console.log("Discovery workflow polish tests passed");
