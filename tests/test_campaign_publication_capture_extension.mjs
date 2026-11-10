import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const moduleUrl = pathToFileURL(path.join(root, "chrome_extension/platform/publication_capture.js")).href;
const { collectPublicationFromTab, collectPublicationPage, publicationIdentity } = await import(moduleUrl);
const { submitPublicationCapture } = await import(pathToFileURL(path.join(root, "chrome_extension/services/local_api.js")).href);
const {
  claimAndRunPublicationBatch, resumePublicationBatch
} = await import(pathToFileURL(path.join(root, "chrome_extension/services/publication_batch.js")).href);

function captureCodeParser() {
  const context = {};
  context.globalThis = context;
  vm.runInNewContext(fs.readFileSync(path.join(root, "chrome_extension/core/publication_capture_code.js"), "utf8"), context);
  return context.KOLConnectPublicationCaptureCode;
}

test("capture code parser accepts complete copied codes and rejects truncated input", () => {
  const parser = captureCodeParser();
  const request = `capture_${"a".repeat(32)}`;
  const token = "Abc_def-12345678901234567890";
  assert.deepEqual({ ...parser.parse(`${request}.${token}`) }, { request_id: request, capability_token: token });
  assert.deepEqual({ ...parser.parse(`\u200B${request}．${token}\n`) }, { request_id: request, capability_token: token });
  assert.equal(parser.parse(request), null);
  assert.equal(parser.parse(`wrong.${token}`), null);
});

test("YouTube card click sends the complete parsed code through the real message handler", async () => {
  const listeners = {};
  const input = { value: `\u200Bcapture_${"b".repeat(32)}．Token_12345678901234567890\n` };
  const button = { disabled: false, addEventListener: (name, handler) => { listeners[`capture-${name}`] = handler; } };
  const passiveButton = { disabled: false, textContent: "", addEventListener() {} };
  const diagnosticButton = {
    textContent: "", addEventListener: (name, handler) => { listeners[`diagnostic-${name}`] = handler; }
  };
  const status = { textContent: "" };
  const shadow = {
    set innerHTML(_value) {},
    querySelector(selector) {
      if (selector === "input") return input;
      if (selector === "[data-capture]") return button;
      if (selector === "[data-safe-diagnostics]") return diagnosticButton;
      if (selector === "[data-refresh]" || selector === "[data-manual]"
          || selector === "[data-expand]" || selector === "[data-minimize]") return passiveButton;
      if (selector === ".manual") return { hidden: true };
      if (selector === "[data-platform]" || selector === "[data-video-id]"
          || selector.startsWith("[data-metric=")) return { textContent: "" };
      return status;
    },
    querySelectorAll() { return []; },
  };
  const host = {
    id: "", dataset: {}, style: {}, offsetWidth: 220,
    attachShadow: () => shadow, remove() {},
    getBoundingClientRect: () => ({ left: 10, top: 10 })
  };
  const document = {
    getElementById: () => null,
    createElement: () => host,
    documentElement: { appendChild() {} },
  };
  let sent = null;
  const context = {
    URL,
    document,
    location: { href: "https://www.youtube.com/watch?v=video_1" }, innerWidth: 1280, innerHeight: 720,
    addEventListener() {},
    KOLConnectPageSupport: { publicationIdentity: () => ({ platform: "YouTube", video_id: "video_1" }) },
    KOLConnectPublicationCaptureCode: captureCodeParser(),
    chrome: {
      runtime: { sendMessage: async (message) => {
        sent = message;
        return { ok: true, result: { attempt: { capture_status: "partial" } } };
      } },
      storage: { local: {
        get: async (defaults) => ({ ...defaults }),
        set: async (value) => { context.diagnosticState = value; },
      } },
    },
  };
  context.globalThis = context;
  vm.runInNewContext(fs.readFileSync(path.join(root, "chrome_extension/content/publication_capture.js"), "utf8"), context);
  await listeners["capture-click"]();
  assert.equal(sent.request_id, `capture_${"b".repeat(32)}`);
  assert.equal(sent.capability_token, "Token_12345678901234567890");
  assert.equal(sent.page_url, "https://www.youtube.com/watch?v=video_1");
  assert.match(status.textContent, /已保存/);
  await listeners["diagnostic-click"]();
  assert.equal(context.diagnosticState.publicationCaptureSafeDiagnostics, true);
  assert.match(diagnosticButton.textContent, /开启/);
  assert.match(status.textContent, /只记录阶段、来源类型和字段存在性/);
});

test("single-video identities are strict for TikTok Instagram and YouTube", () => {
  assert.deepEqual(publicationIdentity("https://www.tiktok.com/@creator/video/123"), { platform: "TikTok", video_id: "123" });
  assert.deepEqual(publicationIdentity("https://www.instagram.com/reel/ABC_1/"), { platform: "Instagram", video_id: "ABC_1" });
  assert.deepEqual(publicationIdentity("https://www.instagram.com/creator.name/reel/ABC_1/"), { platform: "Instagram", video_id: "ABC_1" });
  assert.deepEqual(publicationIdentity("https://www.instagram.com/p/POST_1/"), { platform: "Instagram", video_id: "POST_1" });
  assert.deepEqual(publicationIdentity("https://www.youtube.com/shorts/yt_1"), { platform: "YouTube", video_id: "yt_1" });
  assert.deepEqual(publicationIdentity("https://www.youtube.com/watch?v=watch_1"), { platform: "YouTube", video_id: "watch_1" });
  assert.equal(publicationIdentity("https://www.youtube.com/@creator/shorts"), null);
  assert.equal(publicationIdentity("https://example.com/video/123"), null);
});

test("YouTube structured state preserves zero and missing fields", () => {
  const result = collectPublicationPage(
    { platform: "YouTube", video_id: "yt_1" },
    { ytInitialPlayerResponse: { videoDetails: { videoId: "yt_1", viewCount: "0" } } },
    { querySelectorAll: () => [] },
  );
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, 0);
  assert.equal(result.metrics.views.source, "ytInitialPlayerResponse.videoDetails");
  assert.equal(result.metrics.likes.value, null);
  assert.equal(result.metrics.likes.missing_reason, "not_exposed");
});

test("YouTube current-page structured data keeps exact-video views likes and comments", () => {
  const result = collectPublicationPage(
    { platform: "YouTube", video_id: "yt_exact" },
    {
      ytInitialPlayerResponse: { videoDetails: { videoId: "yt_exact", viewCount: "12,345" } },
      ytInitialData: { contents: {
        likeButtonViewModel: { likeCountEntity: { accessibilityText: "1.2K likes" } },
        commentsHeaderRenderer: { countText: { simpleText: "35 Comments" } },
      } },
    },
    { querySelectorAll: () => [] },
  );
  assert.equal(result.metrics.views.value, 12345);
  assert.equal(result.metrics.likes.value, 1200);
  assert.equal(result.metrics.comments.value, 35);
  assert.equal(result.metrics.likes.source, "ytInitialData.likeButtonViewModel");
});

test("YouTube Shorts description header supplies identity-bound localized views", () => {
  const result = collectPublicationPage(
    { platform: "YouTube", video_id: "short_exact" },
    {
      ytInitialPlayerResponse: { videoDetails: { videoId: "short_exact", viewCount: null } },
      ytInitialData: { engagementPanels: [{ engagementPanelSectionListRenderer: { content: {
        structuredDescriptionContentRenderer: { items: [{ videoDescriptionHeaderRenderer: {
          views: { simpleText: "46,066次观看" },
        } }] },
      } } }] },
    },
    { querySelectorAll: () => [] },
  );
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, 46066);
  assert.equal(result.metrics.views.source, "ytInitialData.videoDescriptionHeaderRenderer.views");
  assert.equal(result.metrics.views.confidence, "high");
});

test("TikTok and Instagram parsers bind metrics to the requested video only", () => {
  const document = { querySelectorAll: () => [] };
  const tiktok = collectPublicationPage(
    { platform: "TikTok", video_id: "100" },
    { SIGI_STATE: { ItemModule: { 100: { id: "100", stats: { playCount: 12, diggCount: 2, commentCount: 0, shareCount: 1 } }, 101: { id: "101", stats: { playCount: 999 } } } } },
    document,
  );
  assert.equal(tiktok.capture_status, "success");
  assert.equal(tiktok.metrics.views.value, 12);
  assert.equal(tiktok.metrics.views.source, "SIGI_STATE");
  assert.equal(tiktok.metrics.comments.value, 0);

  const instagram = collectPublicationPage(
    { platform: "Instagram", video_id: "ABC" },
    { __additionalDataLoaded: { media: { shortcode: "ABC", video_view_count: 20, edge_media_preview_like: { count: 4 }, edge_media_to_comment: { count: 1 } } } },
    document,
  );
  assert.equal(instagram.metrics.views.value, 20);
  assert.equal(instagram.metrics.likes.value, 4);
  assert.equal(instagram.metrics.comments.value, 1);
  assert.equal(instagram.metrics.shares.value, null);
});

test("TikTok compact structured counts preserve 12.2K 1.6K zero and null semantics", () => {
  const result = collectPublicationPage(
    { platform: "TikTok", video_id: "100" },
    { SIGI_STATE: { ItemModule: { 100: { id: "100", stats: {
      playCount: "12.2K", diggCount: "1.6K", commentCount: 0, shareCount: null,
    } } } } },
    { querySelectorAll: () => [] },
  );
  assert.equal(result.metrics.views.value, 12200);
  assert.equal(result.metrics.likes.value, 1600);
  assert.equal(result.metrics.comments.value, 0);
  assert.equal(result.metrics.shares.value, null);
});

test("TikTok video-page hydration scripts are identity-bound medium-confidence evidence", () => {
  const hydration = { ItemModule: {
    100: { id: "100", stats: { playCount: 12200, diggCount: 1600, commentCount: 19 } },
    101: { id: "101", stats: { playCount: 999999 } },
  } };
  const document = {
    querySelectorAll: () => [],
    getElementById: (id) => id === "SIGI_STATE" ? { textContent: JSON.stringify(hydration) } : null,
  };
  const result = collectPublicationPage({ platform: "TikTok", video_id: "100" }, {}, document);
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, 12200);
  assert.equal(result.metrics.views.source, "SIGI_STATE_SCRIPT");
  assert.equal(result.metrics.views.confidence, "medium");
  assert.equal(result.metrics.comments.value, 19);
});

test("TikTok video pages initialize passive capture for the exact profile", () => {
  const context = { URL, crypto: globalThis.crypto };
  context.globalThis = context;
  vm.runInNewContext(fs.readFileSync(path.join(root, "chrome_extension/capture/passive_capture_protocol.js"), "utf8"), context);
  assert.equal(context.KOLConnectPassiveCaptureProtocol.profileUsername("https://www.tiktok.com/@creator/video/123"), "creator");
  assert.equal(context.KOLConnectPassiveCaptureProtocol.profileUsername("https://www.tiktok.com/@other/video/123"), "other");
});

test("TikTok collector reuses only exact-video high-confidence passive L1 metrics", async () => {
  globalThis.chrome = { scripting: { executeScript: async ({ world }) => world === "MAIN"
    ? [{ result: { capture_status: "insufficient", safe_error_code: "METRICS_NOT_FOUND", metrics: {
      views: { value: null, source: "missing", confidence: "low" },
      likes: { value: null, source: "missing", confidence: "low" },
      comments: { value: null, source: "missing", confidence: "low" },
      shares: { value: null, source: "missing", confidence: "low" },
    } } }]
    : [{ result: { state: "matched", row: {
      views: { value: 12200, source: "tiktok_item_list_api", confidence: "high" },
      likes: { value: 1600, source: "tiktok_item_list_api", confidence: "high" },
      comments: { value: 19, source: "tiktok_item_list_api", confidence: "high" },
      shares: { value: null, source: "", confidence: "missing" },
    } } }], } };
  const result = await collectPublicationFromTab(1, "https://www.tiktok.com/@creator/video/123");
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, 12200);
  assert.equal(result.metrics.likes.source, "tiktok_item_list_api");
  assert.equal(result.metrics.shares.value, null);
  delete globalThis.chrome;
});

test("TikTok rendered overlays are not evidence and identity misses remain insufficient", async () => {
  const visibleOverlay = { querySelectorAll: () => [], querySelector: () => null, body: { innerText: "12.2K views 1.6K likes 19 comments" } };
  const page = collectPublicationPage({ platform: "TikTok", video_id: "123" }, {}, visibleOverlay);
  assert.equal(page.capture_status, "insufficient");
  assert.equal(page.metrics.views.value, null);
  globalThis.chrome = { scripting: { executeScript: async ({ world }) => world === "MAIN"
    ? [{ result: page }] : [{ result: { state: "video_identity_missing" } }], } };
  const result = await collectPublicationFromTab(1, "https://www.tiktok.com/@creator/video/123");
  assert.equal(result.capture_status, "insufficient");
  assert.equal(result.safe_error_code, "VIDEO_IDENTITY_MISSING");
  delete globalThis.chrome;
});

test("Instagram Post and YouTube Watch fixtures retain identity-scoped sources", () => {
  const document = { querySelectorAll: () => [] };
  const instagram = collectPublicationPage(
    { platform: "Instagram", video_id: "POST_1" },
    { __additionalDataLoaded: { media: { shortcode: "POST_1", play_count: 0, like_count: 3, comment_count: 0 } } },
    document,
  );
  assert.equal(instagram.metrics.views.value, 0);
  assert.equal(instagram.metrics.views.source, "instagram_page_state");
  assert.equal(instagram.metrics.comments.value, 0);

  const youtube = collectPublicationPage(
    { platform: "YouTube", video_id: "watch_1" },
    { ytInitialPlayerResponse: { videoDetails: { videoId: "watch_1", viewCount: "42" } } },
    document,
  );
  assert.equal(youtube.metrics.views.value, 42);
  assert.equal(youtube.metrics.views.source, "ytInitialPlayerResponse.videoDetails");
  assert.equal(youtube.metrics.likes.value, null);
});

test("Instagram current-page meta keeps verified likes and comments when views are missing", () => {
  const meta = { content: "1,538 likes, 35 comments" };
  const document = {
    querySelectorAll: () => [],
    querySelector: (selector) => selector.includes("og:description") ? meta : null,
  };
  const result = collectPublicationPage({ platform: "Instagram", video_id: "ABC" }, {}, document);
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, null);
  assert.equal(result.metrics.likes.value, 1538);
  assert.equal(result.metrics.comments.value, 35);
  assert.equal(result.metrics.likes.source, "instagram_meta_description");
});

test("Instagram localized and code-based structured evidence remains exact-video partial", () => {
  const meta = { content: "1.538 curtidas, 35 comentários" };
  const document = {
    querySelectorAll: () => [],
    querySelector: (selector) => selector.includes("og:description") ? meta : null,
  };
  const result = collectPublicationPage(
    { platform: "Instagram", video_id: "CODE_1" },
    { __additionalDataLoaded: { media: {
      code: "CODE_1", edge_liked_by: { count: 1538 }, edge_media_to_parent_comment: { count: 35 },
    } } },
    document,
  );
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, null);
  assert.equal(result.metrics.likes.value, 1538);
  assert.equal(result.metrics.comments.value, 35);
  assert.equal(result.metrics.likes.source, "instagram_page_state");
});

test("Instagram matching page scripts are parsed but other shortcodes are rejected", () => {
  const script = { textContent: `window.__additionalDataLoaded('/p/ABC/', {"media":{"shortcode":"ABC","like_count":1538,"comment_count":35}});` };
  const document = { querySelectorAll: (selector) => selector === "script" ? [script] : [], querySelector: () => null };
  const matched = collectPublicationPage({ platform: "Instagram", video_id: "ABC" }, {}, document);
  const mismatched = collectPublicationPage({ platform: "Instagram", video_id: "OTHER" }, {}, document);
  assert.equal(matched.metrics.likes.value, 1538);
  assert.equal(matched.metrics.comments.value, 35);
  assert.equal(mismatched.capture_status, "insufficient");
});

test("Instagram exact shortcode wins over a different numeric media id and reads nested metrics", () => {
  const result = collectPublicationPage(
    { platform: "Instagram", video_id: "REEL_EXACT" },
    { __additionalDataLoaded: {
      id: "9876543210", code: "REEL_EXACT",
      media: { like_count: 1538, comment_count: 35, play_count: 0 }
    } },
    { querySelectorAll: () => [], querySelector: () => null },
  );
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, 0);
  assert.equal(result.metrics.likes.value, 1538);
  assert.equal(result.metrics.comments.value, 35);
  assert.ok(result.diagnostic.identity_match_count >= 1);
});

test("Instagram matched containers do not borrow metrics from another nested reel", () => {
  const result = collectPublicationPage(
    { platform: "Instagram", video_id: "REEL_EXACT" },
    { __additionalDataLoaded: {
      code: "REEL_EXACT", media: { code: "OTHER_REEL", like_count: 9999 }
    } },
    { querySelectorAll: () => [], querySelector: () => null },
  );
  assert.equal(result.capture_status, "insufficient");
  assert.equal(result.metrics.likes.value, null);
  assert.ok(result.diagnostic.identity_rejected_count >= 1);
});

test("Instagram JSON-LD accepts an exact reel URL when its numeric identifier differs", () => {
  const script = { textContent: JSON.stringify({
    "@type": "VideoObject", identifier: "9876543210",
    contentUrl: "https://www.instagram.com/reel/REEL_EXACT/",
    interactionStatistic: [
      { interactionType: { "@type": "LikeAction" }, userInteractionCount: 1538 },
      { interactionType: { "@type": "CommentAction" }, userInteractionCount: 35 },
    ]
  }) };
  const result = collectPublicationPage(
    { platform: "Instagram", video_id: "REEL_EXACT" }, {},
    { querySelectorAll: (selector) => selector.includes("ld+json") ? [script] : [], querySelector: () => null },
  );
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.likes.value, 1538);
  assert.equal(result.metrics.comments.value, 35);
});

test("login or challenge pages return an actionable restricted status", () => {
  const login = { querySelectorAll: () => [], querySelector: (selector) => selector.includes("login-modal") ? {} : null };
  const challenge = { querySelectorAll: () => [], querySelector: (selector) => selector.includes("captcha") ? {} : null };
  const loginResult = collectPublicationPage({ platform: "Instagram", video_id: "ABC" }, {}, login);
  const challengeResult = collectPublicationPage({ platform: "Instagram", video_id: "ABC" }, {}, challenge);
  assert.equal(loginResult.safe_error_code, "AUTH_REQUIRED");
  assert.equal(loginResult.diagnostic.stage, "auth_required");
  assert.equal(challengeResult.safe_error_code, "PLATFORM_RESTRICTED");
  assert.equal(challengeResult.diagnostic.stage, "platform_restricted");
});

test("JSON-LD metrics require matching identity and absent evidence stays insufficient", () => {
  const script = (value) => ({ textContent: JSON.stringify(value) });
  const mismatched = collectPublicationPage(
    { platform: "YouTube", video_id: "wanted" }, {},
    { querySelectorAll: () => [script({ "@type": "VideoObject", identifier: "other", interactionStatistic: [{ interactionType: { "@type": "WatchAction" }, userInteractionCount: 99 }] })] },
  );
  assert.equal(mismatched.capture_status, "insufficient");
  assert.equal(mismatched.metrics.views.value, null);
  assert.equal(mismatched.safe_error_code, "METRICS_NOT_FOUND");
});

test("manifest and UI expose an explicit publication-scoped capture flow", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "chrome_extension/manifest.json"), "utf8"));
  const scripts = manifest.content_scripts.flatMap((entry) => entry.js || []);
  assert.ok(scripts.includes("content/publication_capture.js"));
  assert.ok(scripts.includes("core/publication_capture_code.js"));
  assert.ok(scripts.includes("content/publication_batch_claim.js"));
  assert.ok(manifest.permissions.includes("tabs"));
  const content = fs.readFileSync(path.join(root, "chrome_extension/content/publication_capture.js"), "utf8");
  const background = fs.readFileSync(path.join(root, "chrome_extension/background.js"), "utf8");
  const campaign = fs.readFileSync(path.join(root, "webapp/pages/campaign-detail.js"), "utf8");
  assert.match(content, /一次性采集码/);
  assert.match(content, /KOLCONNECT_PUBLICATION_CAPTURE/);
  assert.match(content, /attachShadow\(\{\s*mode:\s*"closed"\s*\}\)/);
  assert.match(content, /本次采集未取得可靠指标/);
  assert.match(content, /采集码格式不完整/);
  assert.match(background, /submitPublicationCapture/);
  assert.match(background, /stage:\s*"submit_rejected"/);
  assert.match(background, /KOLCONNECT_PUBLICATION_BATCH_CLAIM/);
  assert.match(background, /claimAndRunPublicationBatch/);
  assert.doesNotMatch(background, /capability_token[^\n]*console\./);
  assert.match(campaign, /X-KOLConnect-Publication-Capture-CSRF/);
  assert.match(campaign, /data-capture-check/);
});

test("collector result contract reaches localhost without dropping identity or provenance", async () => {
  let submitted = null;
  globalThis.chrome = { storage: { local: { get: async () => ({}) } } };
  globalThis.fetch = async (_url, init) => {
    submitted = JSON.parse(init.body);
    return { ok: true, status: 200, json: async () => ({ ok: true, attempt: { capture_status: "partial" } }) };
  };
  const payload = {
    request_id: "capture_fixture", capability_token: "fixture-token", page_url: "https://www.instagram.com/reel/ABC/",
    platform: "Instagram", video_id: "ABC", capture_status: "partial", safe_error_code: "",
    metrics: { likes: { value: 1538, source: "instagram_meta_description", confidence: "medium", missing_reason: "" } },
    collector_version: "2.0.1", contract_version: "publication-capture-v1",
  };
  const response = await submitPublicationCapture(payload);
  assert.equal(response.attempt.capture_status, "partial");
  assert.deepEqual(submitted, payload);
  delete globalThis.fetch;
  delete globalThis.chrome;
});

test("a stalled page collector fails with a bounded timeout and no retry", async () => {
  let calls = 0;
  globalThis.chrome = { scripting: { executeScript: () => { calls += 1; return new Promise(() => {}); } } };
  const result = await collectPublicationFromTab(1, "https://www.youtube.com/watch?v=yt_1", 2);
  assert.equal(result.capture_status, "failed");
  assert.equal(result.safe_error_code, "CAPTURE_TIMEOUT");
  assert.equal(calls, 1);
  delete globalThis.chrome;
});

test("YouTube batch capture waits for asynchronous structured evidence within the bound", async () => {
  let calls = 0;
  globalThis.chrome = {
    tabs: { get: async () => ({ url: "https://www.youtube.com/watch?v=yt_ready" }) },
    scripting: { executeScript: async () => {
      calls += 1;
      if (calls < 3) return [{ result: {
        capture_status: "insufficient", safe_error_code: "METRICS_NOT_FOUND", metrics: {},
        diagnostic: { stage: "metrics_not_found" },
      } }];
      return [{ result: {
        capture_status: "partial", safe_error_code: "",
        metrics: { views: { value: 42, source: "ytInitialPlayerResponse.videoDetails", confidence: "high" } },
        diagnostic: { stage: "metrics_collected" },
      } }];
    } },
  };
  const result = await collectPublicationFromTab(9, "https://www.youtube.com/watch?v=yt_ready", 1500);
  assert.equal(calls, 3);
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.views.value, 42);
  delete globalThis.chrome;
});

test("YouTube batch keeps an early like while waiting for later exact-video views", async () => {
  let calls = 0;
  globalThis.chrome = {
    tabs: { get: async () => ({ url: "https://www.youtube.com/watch?v=yt_late_views" }) },
    scripting: { executeScript: async () => {
      calls += 1;
      const metrics = {
        likes: { value: 1628, source: "ytInitialData.likeButtonViewModel", confidence: "high" },
        views: { value: calls === 1 ? null : 98765, source: calls === 1 ? "missing" : "ytInitialPlayerResponse.videoDetails", confidence: calls === 1 ? "low" : "high" },
      };
      return [{ result: { capture_status: "partial", safe_error_code: "", metrics,
        diagnostic: { stage: "metrics_collected", playback_state: calls === 1 ? "ERROR" : "OK" } } }];
    } },
  };
  const result = await collectPublicationFromTab(11, "https://www.youtube.com/watch?v=yt_late_views", 1000);
  assert.equal(calls, 2);
  assert.equal(result.metrics.likes.value, 1628);
  assert.equal(result.metrics.views.value, 98765);
  delete globalThis.chrome;
});

test("Instagram login overlay does not preempt later public exact-reel evidence", async () => {
  let calls = 0;
  globalThis.chrome = {
    tabs: { get: async () => ({ url: "https://www.instagram.com/reel/REEL_LOGIN/" }) },
    scripting: { executeScript: async () => {
      calls += 1;
      if (calls === 1) return [{ result: {
        capture_status: "insufficient", safe_error_code: "AUTH_REQUIRED", metrics: {},
        diagnostic: { stage: "auth_required" },
      } }];
      return [{ result: {
        capture_status: "partial", safe_error_code: "",
        metrics: {
          likes: { value: 1538, source: "instagram_meta_description", confidence: "medium" },
          comments: { value: 35, source: "instagram_meta_description", confidence: "medium" },
          views: { value: null, source: "missing", confidence: "low" },
        },
        diagnostic: { stage: "metrics_collected" },
      } }];
    } },
  };
  const result = await collectPublicationFromTab(12, "https://www.instagram.com/reel/REEL_LOGIN/", 1000);
  assert.equal(calls, 2);
  assert.equal(result.capture_status, "partial");
  assert.equal(result.metrics.likes.value, 1538);
  assert.equal(result.metrics.views.value, null);
  delete globalThis.chrome;
});

test("YouTube playability failure is classified without fabricating metrics", () => {
  const result = collectPublicationPage(
    { platform: "YouTube", video_id: "yt_unplayable" },
    { ytInitialPlayerResponse: { videoDetails: { videoId: "yt_unplayable" }, playabilityStatus: { status: "ERROR" } } },
    { querySelectorAll: () => [], querySelector: () => null },
  );
  assert.equal(result.capture_status, "insufficient");
  assert.equal(result.safe_error_code, "PLAYBACK_UNAVAILABLE");
  assert.equal(result.diagnostic.playback_state, "ERROR");
  assert.equal(result.metrics.views.value, null);
});

test("redirected tab identity mismatch fails closed before collecting metrics", async () => {
  let collected = false;
  globalThis.chrome = {
    tabs: { get: async () => ({ url: "https://www.youtube.com/watch?v=other_video" }) },
    scripting: { executeScript: async () => { collected = true; return []; } },
  };
  const result = await collectPublicationFromTab(10, "https://www.youtube.com/watch?v=expected_video", 50);
  assert.equal(result.capture_status, "insufficient");
  assert.equal(result.safe_error_code, "VIDEO_IDENTITY_MISMATCH");
  assert.equal(collected, false);
  delete globalThis.chrome;
});

test("one batch claim automatically opens collects submits and closes three videos", async () => {
  const session = {};
  const opened = [];
  const removed = [];
  const submitted = [];
  let nextIndex = 0;
  const items = [1, 2, 3].map(index => ({
    item_id: `item_${index}`,
    canonical_url: `https://www.youtube.com/watch?v=video_${index}`,
    platform: "YouTube",
    video_id: `video_${index}`,
    capture_code: `capture_${String(index).repeat(32)}.Token_${String(index).repeat(24)}`,
  }));
  globalThis.chrome = {
    runtime: { getManifest: () => ({ version: "2.0.1" }) },
    storage: {
      local: { get: async () => ({}) },
      session: {
        get: async key => ({ [key]: session[key] }),
        set: async values => Object.assign(session, values),
        remove: async key => { delete session[key]; },
      },
    },
    tabs: {
      create: async ({ url }) => { const tab = { id: opened.length + 1, url, status: "complete" }; opened.push(tab); return tab; },
      get: async id => opened.find(tab => tab.id === id),
      remove: async id => { removed.push(id); },
      onUpdated: { addListener() {}, removeListener() {} },
    },
    scripting: {
      executeScript: async ({ args }) => [{ result: {
        capture_status: "partial", safe_error_code: "",
        metrics: {
          views: { value: Number(args[0].video_id.slice(-1)), source: "fixture", confidence: "high", missing_reason: "" },
          likes: { value: 0, source: "fixture", confidence: "high", missing_reason: "" },
          comments: { value: null, source: "missing", confidence: "low", missing_reason: "not_exposed" },
          shares: { value: null, source: "missing", confidence: "low", missing_reason: "not_exposed" },
        },
      } }],
    },
  };
  globalThis.fetch = async (url, init) => {
    const pathName = new URL(url).pathname;
    const body = JSON.parse(init.body);
    if (pathName.endsWith("/claim")) {
      assert.equal(body.claim_token, "claim-token");
      return { ok: true, status: 200, json: async () => ({ ok: true, executor_token: "executor-token", batch: {} }) };
    }
    if (pathName.endsWith("/next")) {
      assert.equal(body.executor_token, "executor-token");
      const item = items[nextIndex++] || null;
      return { ok: true, status: 200, json: async () => ({ ok: true, state: item ? "opening" : "completed", item }) };
    }
    if (pathName.endsWith("/result")) {
      submitted.push(body);
      return { ok: true, status: 200, json: async () => ({ ok: true, attempt: { capture_status: "partial" } }) };
    }
    throw new Error(`unexpected URL ${url}`);
  };
  const started = await claimAndRunPublicationBatch("batch_1", "claim-token");
  assert.equal(started.started, true);
  const finished = await resumePublicationBatch();
  assert.equal(finished.state, "completed");
  assert.equal(opened.length, 3);
  assert.deepEqual(removed, [1, 2, 3]);
  assert.equal(submitted.length, 3);
  assert.deepEqual(submitted.map(row => row.video_id), ["video_1", "video_2", "video_3"]);
  assert.deepEqual(submitted.map(row => row.metrics.likes.value), [0, 0, 0]);
  assert.equal(session.publicationBatchExecution, undefined);
  delete globalThis.fetch;
  delete globalThis.chrome;
});

test("YouTube Shorts batch recovers once when SPA navigation changes the target during capture", async () => {
  const session = {};
  const targetUrl = "https://www.youtube.com/shorts/BHFVmDzkRuo";
  const wrongUrl = "https://www.youtube.com/shorts/Xn3hlZXuJrE";
  const item = {
    item_id: "item_short", canonical_url: targetUrl, platform: "YouTube", video_id: "BHFVmDzkRuo",
    capture_code: `capture_${"9".repeat(32)}.Shorts_${"s".repeat(24)}`,
  };
  const tab = { id: 91, url: targetUrl, status: "complete" };
  const updates = [];
  const submitted = [];
  let nextCalls = 0;
  let collectionCalls = 0;
  globalThis.chrome = {
    runtime: { getManifest: () => ({ version: "2.0.1" }) },
    storage: {
      local: { get: async () => ({}) },
      session: {
        get: async key => ({ [key]: session[key] }),
        set: async values => Object.assign(session, values),
        remove: async key => { delete session[key]; },
      },
    },
    tabs: {
      create: async () => tab,
      get: async () => ({ ...tab }),
      update: async (_id, { url }) => {
        updates.push(url);
        tab.url = url;
        tab.status = "complete";
        return { ...tab };
      },
      remove: async () => {},
      onUpdated: { addListener() {}, removeListener() {} },
    },
    scripting: {
      executeScript: async () => {
        collectionCalls += 1;
        if (collectionCalls === 1) tab.url = wrongUrl;
        return [{ result: {
          capture_status: "partial", safe_error_code: "",
          metrics: { views: { value: 42, source: "fixture", confidence: "high", missing_reason: "" } },
        } }];
      },
    },
  };
  globalThis.fetch = async (url, init) => {
    const pathname = new URL(url).pathname;
    if (pathname.endsWith("/claim")) {
      return { ok: true, status: 200, json: async () => ({ ok: true, executor_token: "executor-short", batch: {} }) };
    }
    if (pathname.endsWith("/next")) {
      nextCalls += 1;
      return { ok: true, status: 200, json: async () => ({
        ok: true, state: nextCalls === 1 ? "opening" : "completed", item: nextCalls === 1 ? item : null
      }) };
    }
    if (pathname.endsWith("/result")) {
      submitted.push(JSON.parse(init.body));
      return { ok: true, status: 200, json: async () => ({ ok: true, attempt: { capture_status: "partial" } }) };
    }
    throw new Error(`unexpected URL ${url}`);
  };

  await claimAndRunPublicationBatch("batch_short", "claim-short");
  const finished = await resumePublicationBatch();
  assert.equal(finished.state, "completed");
  assert.deepEqual(updates, [targetUrl], "the owned tab should be restored exactly once to the target Short");
  assert.equal(collectionCalls, 2, "metrics must be recollected after restoring the target identity");
  assert.equal(submitted.length, 1);
  assert.equal(submitted[0].video_id, "BHFVmDzkRuo");
  assert.equal(submitted[0].page_url, targetUrl);
  delete globalThis.fetch;
  delete globalThis.chrome;
});

test("YouTube Shorts batch fails closed and advances after the one recovery also drifts", async () => {
  const session = {};
  const targetUrl = "https://www.youtube.com/shorts/target_once";
  const tab = { id: 92, url: targetUrl, status: "complete" };
  const item = {
    item_id: "item_drift", canonical_url: targetUrl, platform: "YouTube", video_id: "target_once",
    capture_code: `capture_${"8".repeat(32)}.Drift_${"d".repeat(24)}`,
  };
  let nextCalls = 0;
  let updateCalls = 0;
  const submitted = [];
  globalThis.chrome = {
    runtime: { getManifest: () => ({ version: "2.0.1" }) },
    storage: {
      local: { get: async () => ({}) },
      session: {
        get: async key => ({ [key]: session[key] }), set: async values => Object.assign(session, values),
        remove: async key => { delete session[key]; },
      },
    },
    tabs: {
      create: async () => tab, get: async () => ({ ...tab }),
      update: async (_id, { url }) => { updateCalls += 1; tab.url = url; return { ...tab }; },
      remove: async () => {}, onUpdated: { addListener() {}, removeListener() {} },
    },
    scripting: { executeScript: async () => {
      tab.url = `https://www.youtube.com/shorts/wrong_${updateCalls}`;
      return [{ result: {
        capture_status: "partial", safe_error_code: "",
        metrics: { views: { value: 999, source: "wrong-page", confidence: "high", missing_reason: "" } },
      } }];
    } },
  };
  globalThis.fetch = async (url, init) => {
    const pathname = new URL(url).pathname;
    if (pathname.endsWith("/claim")) return { ok: true, status: 200, json: async () => ({ ok: true, executor_token: "executor-drift", batch: {} }) };
    if (pathname.endsWith("/next")) {
      nextCalls += 1;
      return { ok: true, status: 200, json: async () => ({
        ok: true, state: nextCalls === 1 ? "opening" : "completed", item: nextCalls === 1 ? item : null
      }) };
    }
    if (pathname.endsWith("/result")) {
      submitted.push(JSON.parse(init.body));
      return { ok: true, status: 200, json: async () => ({ ok: true, attempt: { capture_status: "failed" } }) };
    }
    throw new Error(`unexpected URL ${url}`);
  };

  await claimAndRunPublicationBatch("batch_drift", "claim-drift");
  const finished = await resumePublicationBatch();
  assert.equal(finished.state, "completed", "a failed item must not leave the batch permanently opening");
  assert.equal(updateCalls, 1, "Shorts recovery must be bounded to one navigation");
  assert.equal(submitted.length, 1);
  assert.equal(submitted[0].capture_status, "failed");
  assert.equal(submitted[0].safe_error_code, "VIDEO_IDENTITY_MISMATCH");
  assert.deepEqual(submitted[0].metrics, {}, "metrics from the wrong Short must never be submitted");
  delete globalThis.fetch;
  delete globalThis.chrome;
});

test("MV3 worker resume uses session authorization and never asks for a per-video code", async () => {
  const session = { publicationBatchExecution: { batch_run_id: "batch_resume", executor_token: "executor_resume" } };
  let nextCalls = 0;
  globalThis.chrome = {
    storage: {
      local: { get: async () => ({}) },
      session: {
        get: async key => ({ [key]: session[key] }),
        set: async values => Object.assign(session, values),
        remove: async key => { delete session[key]; },
      },
    },
  };
  globalThis.fetch = async (url, init) => {
    assert.match(new URL(url).pathname, /\/next$/);
    assert.equal(JSON.parse(init.body).executor_token, "executor_resume");
    nextCalls += 1;
    return { ok: true, status: 200, json: async () => ({ ok: true, state: "completed", item: null }) };
  };
  const result = await resumePublicationBatch();
  assert.equal(result.state, "completed");
  assert.equal(nextCalls, 1);
  assert.equal(session.publicationBatchExecution, undefined);
  delete globalThis.fetch;
  delete globalThis.chrome;
});

test("MV3 worker resumes an in-flight item from session storage with the owned tab", async () => {
  const item = {
    item_id: "item_inflight", canonical_url: "https://www.youtube.com/watch?v=resume_1",
    platform: "YouTube", video_id: "resume_1",
    capture_code: `capture_${"a".repeat(32)}.Resume_${"b".repeat(24)}`,
  };
  const session = { publicationBatchExecution: {
    batch_run_id: "batch_resume", executor_token: "executor_resume", current_item: item, current_tab_id: 44,
  } };
  let submitted = 0;
  let nextCalls = 0;
  const removed = [];
  globalThis.chrome = {
    runtime: { getManifest: () => ({ version: "2.0.1" }) },
    storage: {
      local: { get: async () => ({}) },
      session: {
        get: async key => ({ [key]: session[key] }),
        set: async values => Object.assign(session, values),
        remove: async key => { delete session[key]; },
      },
    },
    tabs: {
      get: async id => ({ id, url: item.canonical_url, status: "complete" }),
      create: async () => { throw new Error("existing owned tab should be reused"); },
      remove: async id => removed.push(id),
      onUpdated: { addListener() {}, removeListener() {} },
    },
    scripting: { executeScript: async () => [{ result: {
      capture_status: "partial", safe_error_code: "",
      metrics: { views: { value: 7, source: "fixture", confidence: "high", missing_reason: "" } },
    } }] },
  };
  globalThis.fetch = async (url) => {
    const pathname = new URL(url).pathname;
    if (pathname.endsWith("/state")) {
      return { ok: true, status: 200, json: async () => ({ ok: true, state: "running", continue_current: true }) };
    }
    if (pathname.endsWith("/result")) {
      submitted += 1;
      return { ok: true, status: 200, json: async () => ({ ok: true, attempt: { capture_status: "partial" } }) };
    }
    nextCalls += 1;
    return { ok: true, status: 200, json: async () => ({ ok: true, state: "completed", item: null }) };
  };
  const result = await resumePublicationBatch();
  assert.equal(result.state, "completed");
  assert.equal(submitted, 1);
  assert.equal(nextCalls, 1);
  assert.deepEqual(removed, [44]);
  delete globalThis.fetch;
  delete globalThis.chrome;
});

test("cancelled backend state clears a stale worker snapshot without reopening the video", async () => {
  const item = {
    canonical_url: "https://www.youtube.com/watch?v=cancelled_1", platform: "YouTube", video_id: "cancelled_1",
    capture_code: `capture_${"c".repeat(32)}.Cancelled_${"d".repeat(24)}`,
  };
  const session = { publicationBatchExecution: {
    batch_run_id: "batch_cancelled", executor_token: "executor_old", current_item: item,
  } };
  let opened = 0;
  globalThis.chrome = {
    storage: {
      local: { get: async () => ({}) },
      session: {
        get: async key => ({ [key]: session[key] }), set: async values => Object.assign(session, values),
        remove: async key => { delete session[key]; },
      },
    },
    tabs: { create: async () => { opened += 1; } },
  };
  globalThis.fetch = async url => {
    assert.match(new URL(url).pathname, /\/state$/);
    return { ok: true, status: 200, json: async () => ({ ok: true, state: "cancelled", continue_current: false }) };
  };
  const result = await resumePublicationBatch();
  assert.equal(result.state, "cancelled");
  assert.equal(opened, 0);
  assert.equal(session.publicationBatchExecution, undefined);
  delete globalThis.fetch;
  delete globalThis.chrome;
});

test("lost submit response resumes after the committed item without orphaning pending work", async () => {
  const item = {
    canonical_url: "https://www.youtube.com/watch?v=committed_1", platform: "YouTube", video_id: "committed_1",
    capture_code: `capture_${"e".repeat(32)}.Committed_${"f".repeat(24)}`,
  };
  const session = { publicationBatchExecution: {
    batch_run_id: "batch_response_lost", executor_token: "executor_valid", current_item: item,
  } };
  let opened = 0;
  let nextCalls = 0;
  globalThis.chrome = {
    storage: {
      local: { get: async () => ({}) },
      session: {
        get: async key => ({ [key]: session[key] }), set: async values => Object.assign(session, values),
        remove: async key => { delete session[key]; },
      },
    },
    tabs: { create: async () => { opened += 1; } },
  };
  globalThis.fetch = async url => {
    const pathname = new URL(url).pathname;
    if (pathname.endsWith("/state")) {
      return { ok: true, status: 200, json: async () => ({ ok: true, state: "running", continue_current: false }) };
    }
    assert.match(pathname, /\/next$/);
    nextCalls += 1;
    return { ok: true, status: 200, json: async () => ({ ok: true, state: "completed", item: null }) };
  };
  const result = await resumePublicationBatch();
  assert.equal(result.state, "completed");
  assert.equal(nextCalls, 1);
  assert.equal(opened, 0);
  assert.equal(session.publicationBatchExecution, undefined);
  delete globalThis.fetch;
  delete globalThis.chrome;
});
