import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

import { mergeInstagramRecentMetrics } from "../chrome_extension/platform/publication_capture.js";

const root = new URL("../", import.meta.url);
const pageSupportSource = readFileSync(new URL("chrome_extension/core/page_support.js", root), "utf8");
const pageContext = { globalThis: {}, URL };
vm.createContext(pageContext);
vm.runInContext(pageSupportSource, pageContext);
const support = pageContext.globalThis.KOLConnectPageSupport;

assert.equal(support.pageMode("https://www.tiktok.com/@creator"), "creator");
assert.equal(support.pageMode("https://www.tiktok.com/@creator/video/123456"), "video");
assert.equal(support.isSupportedCreatorPage("https://www.tiktok.com/@creator/video/123456"), false);
assert.equal(support.pageMode("https://www.instagram.com/reel/ABC_123/"), "video");
assert.equal(support.pageMode("https://www.instagram.com/creator.name/reel/ABC_123/"), "video");
assert.equal(support.pageMode("https://www.youtube.com/shorts/abc-123"), "video");
assert.equal(support.pageMode("https://www.youtube.com/@creator/shorts"), "creator");

const missingCapture = {
  capture_status: "insufficient",
  safe_error_code: "EVIDENCE_NOT_FOUND",
  metrics: Object.fromEntries(["views", "likes", "comments", "shares"].map((name) => [name, {
    value: null, source: "missing", confidence: "low", missing_reason: "not_exposed"
  }])),
  diagnostic: { stage: "evidence_not_found" }
};
const now = Date.parse("2026-11-06T00:00:00Z");
const cache = {
  reel_one: {
    expires_at: now + 60_000,
    metrics: {
      views: { value: 1200, source: "clips_user_api", confidence: "high" },
      likes: { value: 0, source: "clips_user_api", confidence: "high" },
      comments: { value: 7, source: "clips_user_api", confidence: "high" },
      shares: null
    }
  },
  other_reel: {
    expires_at: now + 60_000,
    metrics: { views: { value: 999999, source: "clips_user_api", confidence: "high" } }
  }
};
const merged = mergeInstagramRecentMetrics(missingCapture, { platform: "Instagram", video_id: "reel_one" }, cache, now);
assert.equal(merged.capture_status, "partial");
assert.equal(merged.metrics.views.value, 1200);
assert.equal(merged.metrics.likes.value, 0, "real zero must survive cache reuse");
assert.equal(merged.metrics.comments.value, 7);
assert.equal(merged.metrics.shares.value, null);
assert.equal(merged.metrics.views.source, "clips_user_api");
assert.equal(merged.diagnostic.instagram_recent_cache, "exact_shortcode_match");
assert.equal(missingCapture.metrics.views.value, null, "merge must not mutate the original capture");

const structuredCache = {
  reel_one: { expires_at: now + 60_000, metrics: {
    views: { value: 669863, source: "structured_data", confidence: "high" },
    likes: { value: 23442, source: "structured_data", confidence: "high" }
  } }
};
const structuredMerged = mergeInstagramRecentMetrics(
  missingCapture, { platform: "Instagram", video_id: "reel_one" }, structuredCache, now
);
assert.equal(structuredMerged.metrics.views.value, 669863);
assert.equal(structuredMerged.metrics.views.source, "structured_data");
const lowConfidenceCache = {
  reel_one: { expires_at: now + 60_000, metrics: {
    views: { value: 999999, source: "structured_data", confidence: "medium" }
  } }
};
assert.equal(mergeInstagramRecentMetrics(
  missingCapture, { platform: "Instagram", video_id: "reel_one" }, lowConfidenceCache, now
), missingCapture, "lower-confidence recent evidence must not be reused");

const wrongIdentity = mergeInstagramRecentMetrics(missingCapture, { platform: "Instagram", video_id: "missing" }, cache, now);
assert.equal(wrongIdentity, missingCapture, "another Reel must never inherit cached metrics");
const expired = mergeInstagramRecentMetrics(missingCapture, { platform: "Instagram", video_id: "reel_one" }, cache, now + 120_000);
assert.equal(expired, missingCapture, "expired recent-content evidence must not be reused");

const discovery = readFileSync(new URL("chrome_extension/content/similar_creator_discovery.js", root), "utf8");
for (const contract of [
  "modalCandidates", "modalFromClick", "new Map()", "MutationObserver", "window.addEventListener(\"scroll\"",
  '[class*="ModalContainer"]', '[class*="Dialog"]', "signaledInlineRoots", "inlineCandidates", "seed_urls"
]) assert.ok(discovery.includes(contract), `missing CreatorGraph adaptation contract: ${contract}`);
assert.match(discovery, /'h1', 'h2', 'h3', 'h4', 'p', '\[role="heading"\]'/,
  "inline recommendation discovery must climb from stable heading text rather than a TikTok class name");
assert.ok(!discovery.includes('document.querySelectorAll("a")'), "collector must stay bounded to a recommendation region");

const videoUi = readFileSync(new URL("chrome_extension/content/publication_capture.js", root), "utf8");
const videoCss = readFileSync(new URL("chrome_extension/content/publication_capture.css", root), "utf8");
for (const contract of [
  'host.dataset.mode = "minimized"', "KOLCONNECT_PUBLICATION_PREVIEW", "KOLCONNECT_PUBLICATION_CAPTURE",
  "手动采集码", "data-drag-handle", "data-minimize", "data-close", "publicationCaptureSafeDiagnostics"
]) assert.ok(videoUi.includes(contract), `missing compact video UI contract: ${contract}`);
assert.ok(videoUi.includes('.manual[hidden]{display:none}'));
assert.ok(videoCss.includes('width: min(180px, calc(100vw - 24px))'));
assert.ok(videoCss.includes('#kolconnect-publication-capture[data-mode="expanded"]'));
assert.ok(videoCss.includes('width: min(360px, calc(100vw - 24px))'));
assert.ok(videoUi.includes('.shell{width:100%'));
assert.ok(videoUi.includes("overflow-x:hidden"));
assert.ok(videoUi.includes("@media(max-width:480px)"));
assert.ok(videoUi.includes("if (!host.style.left) return"));
assert.ok(videoUi.includes("host.offsetWidth || 220"));

const assistant = readFileSync(new URL("chrome_extension/content/floating_assistant.js", root), "utf8");
assert.ok(assistant.includes("if (pageSupport.isSupportedCreatorPage(location.href))"));
const assistantCss = readFileSync(new URL("chrome_extension/content/floating_assistant.css", root), "utf8");
assert.ok(assistantCss.includes("max-height: min(560px, calc(100vh - 72px))"));
const background = readFileSync(new URL("chrome_extension/background.js", root), "utf8");
assert.ok(background.includes('message?.type === "KOLCONNECT_PUBLICATION_PREVIEW"'));
assert.ok(background.includes("collectPublicationFromTab(sender.tab.id, pageUrl, 5000)"));
assert.ok(background.includes("claimAndRunPublicationBatch"), "campaign batch path must remain registered");
assert.ok(background.includes("submitPublicationCapture"), "manual capture path must remain registered");

console.log("Extension UI V2.4 compact mode, CreatorGraph adaptation, and metric reuse tests passed");
