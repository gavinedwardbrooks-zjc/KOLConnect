import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import vm from "node:vm";

import {
  calculateViewSummary,
  engagementRate,
  ensureContentSummaryConsistency,
  finalizeContentAnalysis,
  mapWithConcurrency,
  metric,
  parsePublishedText,
  sleepWithSignal
} from "../core/content_analysis.js";
import { finalizeProfile } from "../core/schema.js";
import { buildImportPayload } from "../services/local_api.js";
import * as Instagram from "../platform/instagram.js";
import * as TikTok from "../platform/tiktok.js";
import * as YouTube from "../platform/youtube.js";

const supportContext = vm.createContext({ URL });
supportContext.globalThis = supportContext;
vm.runInContext(
  readFileSync(new URL("../core/page_support.js", import.meta.url), "utf8"),
  supportContext
);
const supports = supportContext.KOLConnectPageSupport.isSupportedCreatorPage;
assert.equal(supports("https://www.tiktok.com/@creator"), true);
assert.equal(supports("https://www.instagram.com/creator/reels/"), true);
assert.equal(supports("https://www.youtube.com/@creator/shorts"), true);
assert.equal(supports("https://www.tiktok.com/"), false);
assert.equal(supports("https://www.instagram.com/explore/"), false);
assert.equal(supports("https://www.youtube.com/watch?v=abc"), false);

const originalChrome = globalThis.chrome;
const baseYouTubeResult = {
  platform: "YouTube",
  analysis_url: "https://www.youtube.com/@kolconnect_demo_channel/shorts",
  supported: true,
  fields: {
    profile_url: {
      value: "https://www.youtube.com/@kolconnect_demo_channel",
      source: "url",
      confidence: "high",
      missing_reason: ""
    },
    username: {
      value: "@kolconnect_demo_channel",
      source: "url",
      confidence: "high",
      missing_reason: ""
    },
    creator_name: {
      value: "KOLConnect Demo Channel",
      source: "ytInitialData",
      confidence: "high",
      missing_reason: ""
    },
    followers: {
      value: null,
      source: "",
      confidence: "missing",
      missing_reason: "Subscriber count was not exposed."
    }
  },
  bio_candidates: [{ source: "structured_data", value: "Gaming channel" }],
  searched_sources: ["ytInitialData"],
  errors: []
};

globalThis.chrome = {
  scripting: {
    async executeScript({ func }) {
      if (func.name === "collectYouTubePage") return [{ result: structuredClone(baseYouTubeResult) }];
      if (func.name === "fetchYouTubeChannelHomeData") return [{ result: { subscribers: "1,2 mi" } }];
      throw new Error(`Unexpected function ${func.name}`);
    }
  }
};
const youtubeWithSubscribers = finalizeProfile(await YouTube.collectProfile(1));
assert.equal(youtubeWithSubscribers.followers, "1200000");
assert.equal(youtubeWithSubscribers.fields.followers.source, "channel_home_structured_data");

const incompleteYouTubeResult = structuredClone(baseYouTubeResult);
incompleteYouTubeResult.fields.creator_name.value = null;
incompleteYouTubeResult.fields.creator_name.source = "";
incompleteYouTubeResult.fields.creator_name.confidence = "missing";
incompleteYouTubeResult.fields.bio = {
  value: null,
  source: "",
  confidence: "missing",
  missing_reason: "The current YouTube channel page did not expose a public description."
};
incompleteYouTubeResult.bio_candidates = [];
globalThis.chrome.scripting.executeScript = async ({ func }) => {
  if (func.name === "collectYouTubePage") return [{ result: structuredClone(incompleteYouTubeResult) }];
  if (func.name === "fetchYouTubeChannelHomeData") {
    return [{
      result: {
        subscribers: "1,2 mi",
        creator_name: "KOLConnect Demo Creator",
        description: "Public channel description"
      }
    }];
  }
  throw new Error(`Unexpected function ${func.name}`);
};
const youtubeWithHomeProfile = finalizeProfile(await YouTube.collectProfile(1));
assert.equal(youtubeWithHomeProfile.creator_name, "KOLConnect Demo Creator");
assert.equal(youtubeWithHomeProfile.fields.creator_name.value, "KOLConnect Demo Creator");
assert.equal(youtubeWithHomeProfile.fields.creator_name.source, "channel_home_structured_data");
assert.equal(youtubeWithHomeProfile.bio, "Public channel description");

globalThis.chrome.scripting.executeScript = async ({ func }) => {
  if (func.name === "collectYouTubePage") return [{ result: structuredClone(baseYouTubeResult) }];
  if (func.name === "fetchYouTubeChannelHomeData") return [{ result: { subscribers: null } }];
  throw new Error(`Unexpected function ${func.name}`);
};
const youtubeHiddenSubscribers = await YouTube.collectProfile(1);
assert.equal(youtubeHiddenSubscribers.fields.followers.value, null);
assert.equal(youtubeHiddenSubscribers.fields.followers.confidence, "missing");
assert.equal(
  youtubeHiddenSubscribers.fields.followers.missing_reason,
  "The YouTube channel hides or does not expose its subscriber count."
);
globalThis.chrome = originalChrome;

const rawContents = [];
for (let index = 0; index < 5; index += 1) {
  rawContents.push({
    platform: "TikTok",
    content_type: "video",
    video_id: `pinned-${index}`,
    video_url: `https://example.com/pinned-${index}`,
    is_pinned: true,
    views: 5000
  });
}
for (let index = 1; index <= 35; index += 1) {
  rawContents.push({
    platform: "TikTok",
    content_type: "video",
    video_id: `video-${index}`,
    video_url: `https://example.com/video-${index}`,
    is_pinned: false,
    views: index * 100,
    likes: index * 10,
    comments: index,
    published_at: 1_700_000_000 + index
  });
}
rawContents.push({ ...rawContents[7] });
const analysis = finalizeContentAnalysis(rawContents, { limit: 30, excludePinned: true });
assert.equal(analysis.discovered_count, 40);
assert.equal(analysis.excluded_pinned_count, 5);
assert.equal(analysis.returned_count, 30);
assert.equal(new Set(analysis.contents.map((item) => item.video_id)).size, 30);
assert.equal(analysis.valid_views_count, 30);
assert.equal(analysis.valid_engagement_count, 30);
assert.equal(analysis.capture_status, "success");
assert.equal(analysis.average_views, 2050);
assert.equal(analysis.median_views, 2050);
assert.ok(Math.abs(analysis.weighted_engagement_rate - 11) < 0.000001);
assert.deepEqual(analysis.summary_validation, calculateViewSummary(analysis.contents));

const savedTikTokGlobals = {
  chrome: globalThis.chrome,
  fetch: globalThis.fetch,
  DOMParser: globalThis.DOMParser
};
const captchaItems = [100, 200, 300].map((views, index) => ({
  video_id: `987654321012345678${index}`,
  video_url: `https://www.tiktok.com/@fixture_creator/video/987654321012345678${index}`,
  views,
  likes: null,
  comments: null,
  published_at: null,
  is_pinned: false,
  source: "page_dom"
}));
let tiktokDetailRequests = 0;
globalThis.fetch = async () => {
  tiktokDetailRequests += 1;
  return {
    ok: true,
    status: 200,
    redirected: false,
    url: captchaItems[0].video_url,
    headers: { get: () => "text/html; charset=utf-8" },
    async text() { return "<html><body>captcha verify to continue</body></html>"; }
  };
};
globalThis.chrome = {
  scripting: {
    async executeScript({ func, args = [] }) {
      if (func.name === "discoverTikTokContent") return [{ result: structuredClone(captchaItems) }];
      if (func.name === "fetchTikTokContentDetail") return [{ result: await func(...args) }];
      throw new Error(`Unexpected TikTok function ${func.name}`);
    }
  }
};
const blockedTikTokAnalysis = await TikTok.collectRecentContent(1, { limit: 3, excludePinned: false });
assert.equal(tiktokDetailRequests, 1);
assert.equal(blockedTikTokAnalysis.detail_fallback_status, "blocked_by_verification");
assert.equal(blockedTikTokAnalysis.detail_request_count, 1);
assert.equal(blockedTikTokAnalysis.current_page_metadata_status, "current_page_metadata_unavailable");
assert.equal(blockedTikTokAnalysis.returned_count, 3);
assert.equal(blockedTikTokAnalysis.valid_views_count, 3);
for (const [index, item] of blockedTikTokAnalysis.contents.entries()) {
  assert.equal(item.views.value, (index + 1) * 100);
  assert.equal(item.likes.value, null);
  assert.equal(item.comments.value, null);
  assert.equal(item.published_at.value, null);
}
assert.equal("tiktok_live_diagnostic" in blockedTikTokAnalysis, false);
assert.equal("tiktok_detail_diagnostic" in blockedTikTokAnalysis, false);

const normalVideoId = "9876543210123456789";
const normalItem = {
  video_id: normalVideoId,
  video_url: `https://www.tiktok.com/@fixture_creator/video/${normalVideoId}`,
  views: 100,
  likes: null,
  comments: null,
  published_at: null,
  is_pinned: false,
  source: "page_dom"
};
const detailHydration = JSON.stringify({
  item: {
    id: normalVideoId,
    desc: "fixture",
    stats: { playCount: 100, diggCount: 12, commentCount: 3 },
    createTime: 1_720_000_000
  }
});
tiktokDetailRequests = 0;
globalThis.fetch = async () => {
  tiktokDetailRequests += 1;
  return {
    ok: true,
    status: 200,
    redirected: false,
    url: normalItem.video_url,
    headers: { get: () => "text/html; charset=utf-8" },
    async text() { return "<html><body>public video page</body></html>"; }
  };
};
globalThis.DOMParser = class {
  parseFromString() {
    return {
      getElementById(id) {
        return id === "__UNIVERSAL_DATA_FOR_REHYDRATION__"
          ? { textContent: detailHydration }
          : null;
      }
    };
  }
};
globalThis.chrome.scripting.executeScript = async ({ func, args = [] }) => {
  if (func.name === "discoverTikTokContent") return [{ result: [structuredClone(normalItem)] }];
  if (func.name === "fetchTikTokContentDetail") return [{ result: await func(...args) }];
  throw new Error(`Unexpected TikTok function ${func.name}`);
};
const normalTikTokAnalysis = await TikTok.collectRecentContent(1, { limit: 1, excludePinned: false });
assert.equal(tiktokDetailRequests, 1);
assert.equal(normalTikTokAnalysis.detail_fallback_status, "available");
assert.equal(normalTikTokAnalysis.contents[0].views.value, 100);
assert.equal(normalTikTokAnalysis.contents[0].likes.value, 12);
assert.equal(normalTikTokAnalysis.contents[0].comments.value, 3);
assert.ok(normalTikTokAnalysis.contents[0].published_at.value);

const floatingAssistantSource = readFileSync(
  new URL("../content/floating_assistant.js", import.meta.url),
  "utf8"
);
assert.doesNotMatch(floatingAssistantSource, /TikTok 主页 Raw 临时诊断/);
assert.doesNotMatch(floatingAssistantSource, /TikTok Detail 临时诊断/);
assert.match(floatingAssistantSource, /TikTok 限制了视频详情读取，当前仅使用主页可获得的数据。/);
globalThis.chrome = savedTikTokGlobals.chrome;
if (savedTikTokGlobals.fetch === undefined) delete globalThis.fetch;
else globalThis.fetch = savedTikTokGlobals.fetch;
if (savedTikTokGlobals.DOMParser === undefined) delete globalThis.DOMParser;
else globalThis.DOMParser = savedTikTokGlobals.DOMParser;

const summaryOdd = calculateViewSummary([
  { views: { value: 100 } },
  { views: { value: 200 } },
  { views: { value: 300 } }
]);
assert.equal(summaryOdd.average_views, 200);
assert.equal(summaryOdd.median_views, 200);

const summaryEven = calculateViewSummary([
  { views: { value: 100 } },
  { views: { value: 200 } },
  { views: { value: 300 } },
  { views: { value: 1000 } }
]);
assert.equal(summaryEven.average_views, 400);
assert.equal(summaryEven.median_views, 250);

const numericSortSummary = calculateViewSummary([
  { views: { value: 1_200_000 } },
  { views: { value: 350_000 } },
  { views: { value: 98_000 } },
  { views: { value: null }, raw_text: "999M" }
]);
assert.equal(numericSortSummary.average_views, 549_333.3333333334);
assert.equal(numericSortSummary.median_views, 350_000);
assert.equal(numericSortSummary.valid_views_count, 3);

const inconsistentSummary = ensureContentSummaryConsistency({
  ...analysis,
  valid_views_count: 29
});
assert.equal(inconsistentSummary.capture_status, "failed");
assert.equal(inconsistentSummary.error, "CONTENT_VIEW_SUMMARY_MISMATCH");

const noPublicMetrics = finalizeContentAnalysis(
  Array.from({ length: 30 }, (_, index) => ({
    platform: "Instagram",
    content_type: "reel",
    video_id: `empty-${index}`,
    video_url: `https://www.instagram.com/reel/empty-${index}/`
  })),
  { limit: 30, contentType: "reel" }
);
assert.equal(noPublicMetrics.returned_count, 30);
assert.equal(noPublicMetrics.valid_views_count, 0);
assert.equal(noPublicMetrics.valid_publish_time_count, 0);
assert.equal(noPublicMetrics.capture_status, "unavailable");

const cardBound = Instagram.bindInstagramCardViews([
  {
    video_id: "card-a",
    video_url: "https://www.instagram.com/reel/card-a/",
    views: null,
    card_view_candidates: [{ text: "1.2K views", source: "reel_card_aria" }]
  },
  {
    video_id: "card-b",
    video_url: "https://www.instagram.com/reel/card-b/",
    views: null,
    card_view_candidates: [{ text: "1,2 mi visualizações", source: "reel_card_dom" }]
  },
  {
    video_id: "card-c",
    video_url: "https://www.instagram.com/reel/card-c/",
    views: null,
    card_view_candidates: [
      { text: "999 followers", source: "reel_card_dom" },
      { text: "12 posts", source: "reel_card_dom" }
    ]
  }
]);
assert.equal(cardBound[0].views, 1200);
assert.equal(cardBound[0].video_id, "card-a");
assert.equal(cardBound[1].views, 1_200_000);
assert.equal(cardBound[1].video_id, "card-b");
assert.equal(cardBound[2].views, null);

const savedGlobals = {
  chrome: globalThis.chrome,
  fetch: globalThis.fetch,
  DOMParser: globalThis.DOMParser
};
const reelFixture = {
  video_id: "detail-one",
  video_url: "https://www.instagram.com/reel/detail-one/",
  title: null,
  views: null,
  likes: null,
  comments: null,
  published_at: null,
  card_view_candidates: [],
  card_view_missing_reason: "reel_card_view_not_exposed",
  source: "page_dom"
};
globalThis.fetch = async (url) => ({
  status: 200,
  ok: true,
  url,
  async text() { return "<html><body></body></html>"; }
});
globalThis.DOMParser = class {
  parseFromString() {
    return {
      querySelectorAll(selector) {
        if (selector !== "script") return [];
        return [{
          textContent: JSON.stringify({
            payload: {
              shortcode: "detail-one",
              video_view_count: 4567,
              like_count: 89,
              comment_count: 7,
              taken_at: 1_700_000_000
            }
          })
        }];
      },
      querySelector() { return null; }
    };
  }
};
globalThis.chrome = {
  scripting: {
    async executeScript({ func, args = [] }) {
      if (func.name === "discoverInstagramReels") {
        return [{ result: [structuredClone(reelFixture)] }];
      }
      if (func.name === "fetchInstagramReelDetail") {
        return [{ result: await func(...args) }];
      }
      throw new Error(`Unexpected function ${func.name}`);
    }
  }
};
const instagramDetailAnalysis = await Instagram.collectRecentContent(1, { limit: 1 });
assert.equal(instagramDetailAnalysis.contents[0].views.value, 4567);
assert.equal(instagramDetailAnalysis.contents[0].views.source, "reel_detail_structured_data");
assert.equal(instagramDetailAnalysis.contents[0].likes.value, 89);
assert.equal(instagramDetailAnalysis.contents[0].comments.value, 7);
assert.equal(
  instagramDetailAnalysis.contents[0].published_at.value,
  "2023-11-14T22:13:20.000Z"
);
globalThis.chrome = savedGlobals.chrome;
globalThis.fetch = savedGlobals.fetch;
globalThis.DOMParser = savedGlobals.DOMParser;

const noEngagement = engagementRate(
  metric(1000, "test", "high"),
  metric(null, "", "missing", "Likes unavailable."),
  metric(10, "test", "high")
);
assert.equal(noEngagement.value, null);
assert.equal(noEngagement.missing_reason, "Likes or comments were not publicly available.");

const estimatedPublished = parsePublishedText("2 days ago", new Date("2026-07-29T00:00:00.000Z"));
assert.equal(estimatedPublished.value, "2026-07-27T00:00:00.000Z");
assert.equal(estimatedPublished.is_estimated, true);

let activeWorkers = 0;
let maximumWorkers = 0;
await mapWithConcurrency(
  [1, 2, 3, 4, 5],
  async (value) => {
    activeWorkers += 1;
    maximumWorkers = Math.max(maximumWorkers, activeWorkers);
    await new Promise((resolve) => setTimeout(resolve, 5));
    activeWorkers -= 1;
    return value;
  },
  { concurrency: 2, delay: 1 }
);
assert.equal(maximumWorkers, 2);

const cancellation = new AbortController();
const cancelledWait = sleepWithSignal(1000, cancellation.signal);
cancellation.abort();
await assert.rejects(cancelledWait, (error) => error.name === "AbortError");

const payload = buildImportPayload({
  platform: "TikTok",
  profile_url: "https://www.tiktok.com/@creator",
  username: "@creator",
  creator_name: "Creator",
  content_category: "Gaming",
  videos: analysis.contents,
  video_analysis: { average_views: analysis.average_views }
});
assert.equal(payload.videos.length, 30);
assert.equal(payload.videos[0].views, analysis.contents[0].views.value);
assert.equal(typeof payload.videos[0].views, "number");
assert.equal(payload.video_analysis.average_views, 2050);
assert.deepEqual(Object.keys(payload), [
  "task_name",
  "creator",
  "videos",
  "video_analysis",
  "creator_insight",
  "content_category",
  "note",
  "analysis"
]);

const manifest = JSON.parse(readFileSync(new URL("../manifest.json", import.meta.url), "utf8"));
const manifestText = JSON.stringify(manifest).toLowerCase();
assert.equal(manifest.version, "1.0.0");
for (const forbiddenPermission of ["cookies", "webRequest", "webRequestBlocking"]) {
  assert.equal((manifest.permissions || []).includes(forbiddenPermission), false);
}
for (const forbidden of ["interceptor", "bridge", "adapter", "collector"]) {
  assert.equal(manifestText.includes(forbidden), false);
}
const rootDirectories = readdirSync(new URL("..", import.meta.url), { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name.toLowerCase());
for (const forbidden of ["interceptors", "bridge", "adapters", "collectors"]) {
  assert.equal(rootDirectories.includes(forbidden), false);
}

const assistantSource = readFileSync(
  new URL("../content/floating_assistant.js", import.meta.url),
  "utf8"
);
assert.equal(
  assistantSource.includes("profile?.fields?.creator_name?.value"),
  true
);
assert.equal(
  assistantSource.includes("profile_capture_status"),
  true
);
assert.equal(
  assistantSource.includes("content_capture_status"),
  true
);

console.log("Phase 2.1 profile, summary, Instagram Reel detail, and regression tests passed.");
