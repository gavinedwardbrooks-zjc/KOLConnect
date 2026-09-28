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
assert.match(app, /viewOriginal\.textContent = t\("discoveryViewOriginal"\)/);
assert.match(app, /scope=\$\{scope\}/);
assert.match(app, /copyTaskLinks\("all"\)/);
assert.match(app, /copyTaskLinks\("unfinished"\)/);
assert.doesNotMatch(app, /const canContinue = task\.status !== "completed"/);

assert.match(html, />账号主页<\/th>/);
assert.match(html, /<th>达人<\/th>/);
assert.match(app, /function readableAccountHomepage/);
assert.match(app, /link\.textContent = readableAccountHomepage\(profileUrl\)/);
assert.match(app, /link\.href = profileUrl/);
assert.doesNotMatch(html, /reviewAccountUid/);
assert.match(app, /const linkedCreatorId = reviewField\(record, "creator_id"\)\.trim\(\)/);
assert.match(app, /reviewField\(record, "creator_name"\)\.trim\(\)[\s\S]*reviewField\(record, "账号名"\)\.trim\(\)[\s\S]*t\("reviewUnnamedCreator"\)/);
assert.match(app, /setPage\("creator-library-detail", \{ creatorId: linkedCreatorId \}\)/);
assert.doesNotMatch(app, /creatorName = [^\n]*email/);
assert.match(css, /\.account-homepage-link[\s\S]*text-overflow:\s*ellipsis/);

for (const value of ["task", "review_results", "creator_library", "manual"]) {
  assert.match(html, new RegExp(`name="email-source" value="${value}"`));
}
assert.match(html, /name="email-scope" value="missing" checked/);
assert.match(app, /\/api\/tasks\/email-recheck\/candidates/);
assert.match(app, /\/api\/tasks\/email-recheck\/scan/);
assert.match(app, /\/api\/creator-library\/email-capture/);
assert.match(app, /email_not_found:\s*t\("emailStatusNotFound"\)/);
assert.match(app, /capture_failed:\s*t\("emailStatusUnavailable"\)/);
assert.match(app, /email_conflict:\s*t\("emailStatusConflict"\)/);
assert.match(app, /item\.email_source \|\| "—"/);
assert.match(app, /cell\.textContent = value/);
assert.doesNotMatch(html, /account_uid/);

assert.match(html, /查看待补充范围/);
assert.match(app, /function openReviewEmailEnrichment/);
assert.match(app, /value="review_results"/);
assert.match(app, /t\("emailReviewSelected"\)/);
assert.match(html, /<option value="attention" selected data-i18n="reviewAttention">待补充<\/option>/);
assert.match(html, /<th data-i18n="reviewCompletion">待补充<\/th>/);
assert.doesNotMatch(html, /id="capture-mode"|id="capture-manual-panel"|id="manual-task-create"/);
assert.doesNotMatch(html, /id="creator-analysis-panel"|id="review-view-analysis"/);

console.log("Discovery workflow polish tests passed");
