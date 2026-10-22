import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  contentItem,
  failedContentAnalysis,
  finalizeContentAnalysis,
} from "../chrome_extension/core/content_analysis.js";

const item = (overrides = {}) => ({
  platform: "Instagram",
  content_type: "reel",
  video_id: "reel-1",
  video_url: "https://www.instagram.com/reel/reel-1/",
  ...overrides,
});

const empty = finalizeContentAnalysis([]);
assert.equal(empty.capture_status, "unavailable");
assert.equal(empty.status_reason, "NO_CONTENT_FOUND");
assert.equal(empty.usable_content_count, 0);

const identityOnly = finalizeContentAnalysis([item()]);
assert.equal(identityOnly.returned_count, 1);
assert.equal(identityOnly.usable_content_count, 0);
assert.equal(identityOnly.capture_status, "unavailable");
assert.equal(identityOnly.status_reason, "NO_USABLE_RECENT_CONTENT");

// Invalid pre-wrapped values used to bypass metric normalization and could
// incorrectly produce partial_success while valid metric counts stayed zero.
const malformed = finalizeContentAnalysis([item({
  views: { value: "", source: "fixture" },
  likes: { value: Number.POSITIVE_INFINITY, source: "fixture" },
  published_at: { value: "not-a-date", source: "fixture" },
})]);
assert.equal(malformed.capture_status, "unavailable");
assert.equal(malformed.usable_content_count, 0);
assert.equal(malformed.valid_views_count, 0);
assert.equal(malformed.contents[0].views.value, null);
assert.equal(malformed.contents[0].likes.value, null);
assert.equal(malformed.contents[0].published_at.value, null);

const partial = finalizeContentAnalysis([item({ views: 1250 })]);
assert.equal(partial.capture_status, "partial_success");
assert.equal(partial.status_reason, "PARTIAL_PUBLIC_DATA");
assert.equal(partial.usable_content_count, 1);

const missingStaysMissing = contentItem(item({ views: null, likes: null, comments: null }));
assert.equal(missingStaysMissing.views.value, null);
assert.equal(missingStaysMissing.likes.value, null);
assert.equal(missingStaysMissing.comments.value, null);

assert.equal(failedContentAnalysis("LOGIN_REQUIRED").status_reason, "LOGIN_REQUIRED");
assert.equal(failedContentAnalysis("challenge page").status_reason, "ACCESS_RESTRICTED");
assert.equal(failedContentAnalysis("unsupported page").status_reason, "UNSUPPORTED_STATE");

const assistant = readFileSync(
  new URL("../chrome_extension/content/floating_assistant.js", import.meta.url), "utf8"
);
assert.match(assistant, /NO_CONTENT_FOUND: "未读取到符合条件的近期内容。"/);
assert.match(assistant, /NO_USABLE_RECENT_CONTENT: "读取到内容条目，但没有可用的公开指标。"/);
assert.match(assistant, /handleUrlChange[\s\S]*cancelContentAnalysis\(false\)[\s\S]*clearContent\(\)/);

for (const platform of ["instagram", "youtube", "tiktok"]) {
  const source = readFileSync(
    new URL(`../chrome_extension/platform/${platform}.js`, import.meta.url), "utf8"
  );
  assert.match(source, /network_records/);
  assert.match(source, /hydration_records/);
  assert.match(source, /dom_records/);
  assert.match(source, /normalized_records/);
  assert.match(source, /final_status_reason/);
}

console.log("Recent-content outcome semantics: OK");
