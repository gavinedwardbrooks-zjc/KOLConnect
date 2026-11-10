import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

import {
  contentItem, finalizeContentAnalysis, normalizeContentRange
} from "../chrome_extension/core/content_analysis.js";
import { matchesInstagramMediaIdentity } from "../chrome_extension/platform/instagram.js";
import { mergeInstagramRecentPublishedTimes } from "../chrome_extension/platform/publication_capture.js";

const root = new URL("../", import.meta.url);
const assistantDataSource = readFileSync(new URL("chrome_extension/core/assistant_data.js", root), "utf8");
const context = { globalThis: {}, Date, Number, Set };
vm.createContext(context);
vm.runInContext(assistantDataSource, context);
const { selectContents } = context.globalThis.KOLConnectAssistantData;

const metric = (value) => ({ value });
const now = Date.parse("2026-11-08T00:00:00Z");
const contents = Array.from({ length: 32 }, (_, index) => ({
  video_id: `video-${index}`,
  is_pinned: index === 0 ? true : index === 1 ? null : false,
  published_at: metric(index === 31 ? null : new Date(now - index * 86_400_000).toISOString()),
  views: metric(index === 2 ? 0 : 100 + index),
  likes: metric(10 + index),
  comments: metric(index % 3),
}));

const sevenItems = selectContents(contents, { range: "items:7", excludePinned: true, now });
const thirtyItems = selectContents(contents, { range: "items:30", excludePinned: true, now });
assert.equal(sevenItems.items.length, 7);
assert.equal(thirtyItems.items.length, 30);
assert.notEqual(sevenItems.metrics.averageViews, thirtyItems.metrics.averageViews);
assert.equal(sevenItems.excludedPinnedCount, 1);
assert.equal(sevenItems.unknownPinnedCount, 1);
assert.equal(sevenItems.items.find((item) => item.video_id === "video-2").views.value, 0,
  "real zero must remain a measured value");

const sevenDays = selectContents(contents, { range: "days:7", excludePinned: true, now });
const thirtyDays = selectContents(contents, { range: "days:30", excludePinned: true, now });
assert.equal(sevenDays.items.length, 7);
assert.equal(thirtyDays.items.length, 30);
assert.notEqual(sevenDays.metrics.averageViews, thirtyDays.metrics.averageViews);
assert.equal(sevenDays.timeCoverageComplete, false);
assert.equal(thirtyDays.timeCoverageComplete, false);
assert.equal(thirtyDays.missingPublishedCount, 1);
assert.ok(!thirtyDays.items.some((item) => item.video_id === "video-31"),
  "unknown publish time must not enter a day window");
assert.ok(sevenDays.metrics.weightedEngagementRate >= 0);

assert.equal(contentItem({ video_id: "unknown", is_pinned: null }).is_pinned, null);
assert.equal(contentItem({ video_id: "missing" }).is_pinned, null);
assert.equal(contentItem({ video_id: "pinned", is_pinned: true }).is_pinned, true);

assert.deepEqual(normalizeContentRange({ type: "last_n_posts", value: 7 }), {
  key: "items:7", type: "last_n_posts", value: 7
});
assert.deepEqual(normalizeContentRange({ type: "last_n_days", value: 30 }), {
  key: "days:30", type: "last_n_days", value: 30
});

const captureFixture = Array.from({ length: 34 }, (_, index) => ({
  video_id: `capture-${index}`,
  video_url: `https://example.test/video/${index}`,
  is_pinned: index < 2,
  published_at: index === 3 ? null : new Date(now - index * 86_400_000).toISOString(),
  views: index === 4 ? 0 : 1000 + index,
  likes: 20 + index,
  comments: index
}));
const capturedSeven = finalizeContentAnalysis(captureFixture.slice(0, 10), {
  range: { type: "last_n_posts", value: 7 }, limit: 10, maximumCount: 30,
  excludePinned: true, sourceOrderNewestFirst: true
});
const capturedThirty = finalizeContentAnalysis(captureFixture.slice(0, 30), {
  range: { type: "last_n_posts", value: 30 }, limit: 30, maximumCount: 30,
  excludePinned: true, sourceOrderNewestFirst: true, sourceLimitReached: true
});
assert.equal(capturedSeven.returned_count, 7, "bounded over-fetch must fill seven non-pinned posts");
assert.equal(capturedSeven.excluded_pinned_count, 2);
assert.equal(capturedSeven.contents.find((item) => item.video_id === "capture-4")?.views.value, 0,
  "confirmed zero remains distinct from missing");
assert.equal(capturedThirty.returned_count, 28);
assert.equal(capturedThirty.range_coverage.complete, false);
assert.ok(capturedThirty.range_coverage.reasons.includes("SOURCE_LIMIT_REACHED"));

const capturedSevenDays = finalizeContentAnalysis(captureFixture, {
  range: { type: "last_n_days", value: 7 }, limit: 30, maximumCount: 30,
  excludePinned: true, sourceOrderNewestFirst: true, now, sourceLimitReached: true
});
const capturedThirtyDays = finalizeContentAnalysis(captureFixture, {
  range: { type: "last_n_days", value: 30 }, limit: 30, maximumCount: 30,
  excludePinned: true, sourceOrderNewestFirst: true, now, sourceLimitReached: true
});
assert.equal(capturedSevenDays.capture_range.key, "days:7");
assert.equal(capturedThirtyDays.capture_range.key, "days:30");
assert.ok(capturedSevenDays.returned_count < capturedThirtyDays.returned_count);
assert.ok(!capturedSevenDays.contents.some((item) => item.video_id === "capture-3"),
  "unknown publish time must not enter a day window");
assert.equal(capturedSevenDays.range_coverage.complete, false,
  "unknown dates prevent a complete time-coverage claim");
assert.ok(capturedSevenDays.range_coverage.reasons.includes("PUBLISHED_TIME_MISSING"));

const boundedDays = finalizeContentAnalysis(captureFixture.filter((item) => item.published_at), {
  range: { type: "last_n_days", value: 7 }, limit: 30, maximumCount: 30,
  excludePinned: true, sourceOrderNewestFirst: true, now, sourceExhausted: true
});
assert.equal(boundedDays.range_coverage.complete, true,
  "an exhausted ordered source with known dates can prove the time boundary");

assert.equal(matchesInstagramMediaIdentity({ shortcode: "DfW3nSUNdKC" }, "DfW3nSUNdKC"), true);
assert.equal(matchesInstagramMediaIdentity({ url: "https://www.instagram.com/reel/DfW3nSUNdKC/" }, "DfW3nSUNdKC"), true);
assert.equal(matchesInstagramMediaIdentity({ "@type": "VideoObject", datePublished: "2026-11-01" }, "DfW3nSUNdKC"), false,
  "an unrelated VideoObject must not supply another Reel's publish time");
assert.equal(matchesInstagramMediaIdentity({ shortcode: "another", datePublished: "2026-11-01" }, "DfW3nSUNdKC"), false);

const publishCache = {
  DfW3nSUNdKC: {
    expires_at: now + 60_000,
    published_at: {
      value: "2026-11-05T10:58:53.000Z",
      source: "reel_detail_dom_exact",
      confidence: "high"
    }
  },
  another: {
    expires_at: now + 60_000,
    published_at: {
      value: "2026-10-01T00:00:00.000Z",
      source: "reel_detail_dom_exact",
      confidence: "high"
    }
  }
};
const publishAnalysis = {
  contents: [{
    video_id: "DfW3nSUNdKC",
    video_url: "https://www.instagram.com/reel/DfW3nSUNdKC/",
    published_at: { value: null, confidence: "missing", missing_reason: "reel_publish_time_not_exposed" }
  }],
  valid_publish_time_count: 0,
  missing_counts: { published_at: 1 }
};
const mergedPublished = mergeInstagramRecentPublishedTimes(publishAnalysis, publishCache, now);
assert.equal(mergedPublished.contents[0].published_at.value, "2026-11-05T10:58:53.000Z");
assert.equal(mergedPublished.contents[0].published_at.source, "reel_detail_dom_exact");
assert.equal(mergedPublished.valid_publish_time_count, 1);
assert.equal(mergedPublished.missing_counts.published_at, 0);
assert.equal(publishAnalysis.contents[0].published_at.value, null, "cache merge must not mutate the original analysis");
assert.equal(mergeInstagramRecentPublishedTimes(publishAnalysis, {
  DfW3nSUNdKC: { ...publishCache.DfW3nSUNdKC, expires_at: now - 1 }
}, now), publishAnalysis, "expired evidence must remain missing");
assert.equal(mergeInstagramRecentPublishedTimes(publishAnalysis, {
  DfW3nSUNdKC: { ...publishCache.DfW3nSUNdKC, published_at: { ...publishCache.DfW3nSUNdKC.published_at, source: "observed_at" } }
}, now), publishAnalysis, "observed_at must never be promoted to published_at");

globalThis.chrome = {
  storage: { local: { get: async () => ({ localApiUrl: "http://127.0.0.1:8765" }) } }
};
const originalFetch = globalThis.fetch;
const {
  assertLocalApiAvailable, loadAgencies, loadExtensionMailOptions
} = await import("../chrome_extension/services/local_api.js");
try {
  globalThis.fetch = async (url) => {
    assert.equal(new URL(url).pathname, "/api/system/health");
    return { ok: true, status: 200, json: async () => ({ ok: true, status: "ok" }) };
  };
  assert.equal(await assertLocalApiAvailable(), true);

  globalThis.fetch = async (url) => {
    assert.equal(new URL(url).pathname, "/api/local/agencies");
    return { ok: true, status: 200, json: async () => ({
      ok: true,
      agencies: [{ agency_id: "agency-1", name: "Example Agency", country_region: "BR" }]
    }) };
  };
  assert.deepEqual(await loadAgencies(), [{ agency_id: "agency-1", name: "Example Agency" }]);

  globalThis.fetch = async () => { throw new TypeError("network unavailable"); };
  await assert.rejects(() => assertLocalApiAvailable(), (error) => error?.code === "APP_OFFLINE");
  await assert.rejects(() => loadAgencies(), (error) => error?.code === "APP_OFFLINE");
  await assert.rejects(() => loadExtensionMailOptions({ language: "zh-CN" }),
    (error) => error?.code === "APP_OFFLINE");

  globalThis.fetch = async (url) => {
    assert.equal(new URL(url).pathname, "/api/extension/workspace/options");
    return { ok: true, status: 200, json: async () => ({
      ok: true,
      templates: [{ template_id: "template-1", name: "问候" }],
      mail_accounts: [{ mail_account_id: "mail-1", email: "sender@example.test" }]
    }) };
  };
  const recoveredMail = await loadExtensionMailOptions({ language: "zh-CN" });
  assert.equal(recoveredMail.templates[0].template_id, "template-1");
  assert.equal(recoveredMail.mail_accounts[0].mail_account_id, "mail-1");
} finally {
  globalThis.fetch = originalFetch;
}

const assistantSource = readFileSync(new URL("chrome_extension/content/floating_assistant.js", root), "utf8");
for (const marker of [
  "采集最近30条", "发布时间未知", "采集详情", "覆盖不完整",
  "KOLConnect 本地服务未运行，未打开无效模板页面", "请先启动 KOLConnect",
  "重试加载邮件配置", "Agency 暂不可用"
]) assert.ok(assistantSource.includes(marker), `missing real-usage UI contract: ${marker}`);
assert.ok(!assistantSource.includes('create("button", "", "分析最近30条")'));
for (const marker of [
  'type: MESSAGE.ANALYZE_CONTENT', "range: requestedRange", "exclude_pinned: state.excludePinned",
  '"items:7": "最近7条"', '"days:30": "最近30天"', "contentAnalysisCache"
]) assert.ok(assistantSource.includes(marker), `capture range is not wired through the UI: ${marker}`);

const backgroundSource = readFileSync(new URL("chrome_extension/background.js", root), "utf8");
for (const marker of [
  "normalizeContentRange(request.range", "range: message.range",
  "exclude_pinned: message.exclude_pinned", "range.value + (excludePinned ? 3 : 0)"
]) assert.ok(backgroundSource.includes(marker), `background range contract missing: ${marker}`);
const mailHandler = backgroundSource.slice(backgroundSource.indexOf('message?.type === MESSAGE.OPEN_MAIL_WORKSPACE'));
assert.ok(mailHandler.indexOf("assertLocalApiAvailable()") < mailHandler.indexOf("chrome.storage.session.set"),
  "local app preflight must happen before creating a handoff or opening a tab");

const discoverySource = readFileSync(new URL("chrome_extension/content/similar_creator_discovery.js", root), "utf8");
for (const marker of [
  "canonicalInstagramProfile", "instagramRecommendationRegions", "instagram_recommendation_region",
  "seed_profile_url", "candidate_profile_url", "suggested_accounts"
]) assert.ok(discoverySource.includes(marker), `Instagram discovery contract missing: ${marker}`);
assert.ok(discoverySource.includes("first_observed_at: firstObservedAt"));
assert.ok(discoverySource.includes("last_observed_at: observedAt"));
for (const marker of ["来源达人", "推荐账号区域", "首次发现"]) {
  assert.ok(assistantSource.includes(marker), `candidate evidence is not visible: ${marker}`);
}
for (const marker of [
  "已采集并去重", "已选择", "复制全部", "复制已选择", "导出全部", "导出已选择", "移交已选择"
]) assert.ok(assistantSource.includes(marker), `discovery action scope is not explicit: ${marker}`);
assert.ok(assistantSource.includes("链接无法规范化"),
  "task handoff must disclose candidates rejected by backend normalization");
assert.ok(discoverySource.includes('region.querySelectorAll("*")'),
  "nested recommendation scroll containers must be observed explicitly");
assert.ok(!discoverySource.includes("if (candidates[0]) return candidates[0].element"),
  "an unrelated visible dialog must not be accepted without a recommendation signal");

const publicationUiSource = readFileSync(new URL("chrome_extension/content/publication_capture.js", root), "utf8");
assert.ok(publicationUiSource.includes("parts.length === mediaIndex + 2"),
  "rendered publish time evidence must be bound to the exact Reel identity");
assert.ok(publicationUiSource.includes("KOLCONNECT_INSTAGRAM_PUBLISHED_AT_OBSERVED"));
assert.ok(backgroundSource.includes('source: "reel_detail_dom_exact"'));

const localApiSource = readFileSync(new URL("chrome_extension/services/local_api.js", root), "utf8");
assert.ok(localApiSource.includes('typeof video.is_pinned === "boolean" ? video.is_pinned : null'),
  "unknown pinned state must not be serialized as false");

console.log("Extension V2.4 real-usage fix behavior tests passed");
