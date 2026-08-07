import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  applyYouTubeRssPublishedDates,
  extractYouTubeChannelIdPage,
  fetchYouTubeRss,
  parseYouTubeRssXmlPage
} from "../chrome_extension/platform/youtube.js";
import { finalizeContentAnalysis } from "../chrome_extension/core/content_analysis.js";

const videos = [
  { video_id: "A", title: "A", published_at: null, views: 100 },
  { video_id: "B", title: "B", published_at: "2026-07-01T00:00:00.000Z", views: 200 },
  { video_id: "C", title: "C", published_at: null, views: 300 }
];
const applied = applyYouTubeRssPublishedDates(videos, [
  { video_id: "A", published_at: "2026-08-03T14:30:00+00:00" },
  { video_id: "B", published_at: "2026-08-04T14:30:00+00:00" },
  { video_id: "X", published_at: "2026-08-05T14:30:00+00:00" }
]);
assert.equal(applied.videos.length, 3);
assert.equal(applied.videos[0].published_at, "2026-08-03T14:30:00.000Z");
assert.equal(applied.videos[0].published_source, "youtube_rss");
assert.equal(applied.videos[1].published_at, "2026-07-01T00:00:00.000Z");
assert.equal(applied.videos[2].published_at, null);
assert.equal(applied.matched_count, 2);
assert.equal(applied.supplemented_count, 1);
assert.equal(applied.preserved_count, 1);
assert.equal(applied.uncovered_count, 1);

const manyVideos = Array.from({ length: 30 }, (_, index) => ({
  video_id: `video-${index}`,
  published_at: null
}));
const partialRss = Array.from({ length: 7 }, (_, index) => ({
  video_id: `video-${index}`,
  published_at: `2026-08-${String(index + 1).padStart(2, "0")}T00:00:00Z`
}));
const partialApplied = applyYouTubeRssPublishedDates(manyVideos, partialRss);
assert.equal(partialApplied.videos.length, 30);
assert.equal(partialApplied.supplemented_count, 7);
assert.equal(partialApplied.uncovered_count, 23);

const analysis = finalizeContentAnalysis(applied.videos, { limit: 3, excludePinned: false, contentType: "short" });
assert.equal(analysis.valid_publish_time_count, 2);
assert.equal(analysis.contents.find((item) => item.video_id === "A").published_at.value, "2026-08-03T14:30:00.000Z");

const okResponse = await fetchYouTubeRss("UC1234567890123456789012", {
  fetchImpl: async () => ({ ok: true, status: 200, text: async () => "<feed />" })
});
assert.equal(okResponse.ok, true);
assert.equal(okResponse.xml, "<feed />");
const notFound = await fetchYouTubeRss("UC1234567890123456789012", {
  fetchImpl: async () => ({ ok: false, status: 404, text: async () => "" })
});
assert.deepEqual(notFound, { ok: false, reason: "http_error", status: 404, xml: "" });
const emptyResponse = await fetchYouTubeRss("UC1234567890123456789012", {
  fetchImpl: async () => ({ ok: true, status: 200, text: async () => "  " })
});
assert.equal(emptyResponse.reason, "empty_response");
const networkError = await fetchYouTubeRss("UC1234567890123456789012", {
  fetchImpl: async () => { throw new Error("offline"); }
});
assert.equal(networkError.reason, "network_error");
assert.equal((await fetchYouTubeRss("not-a-channel", { fetchImpl: async () => assert.fail() })).reason, "channel_id_unavailable");

class FakeNode {
  constructor(localName, textContent = "", children = []) {
    this.localName = localName;
    this.textContent = textContent;
    this.children = children;
  }

  getElementsByTagNameNS(_namespace, localName) {
    return this.children.filter((node) => node.localName === localName);
  }

  getElementsByTagName(localName) {
    return localName === "parsererror" ? [] : this.getElementsByTagNameNS("*", localName);
  }
}

const originalDomParser = globalThis.DOMParser;
globalThis.DOMParser = class {
  parseFromString(xml) {
    if (xml.includes("invalid")) {
      return { getElementsByTagName: () => [{}] };
    }
    const entryA = new FakeNode("entry", "", [
      new FakeNode("videoId", "A"),
      new FakeNode("published", "2026-08-03T14:30:00+00:00")
    ]);
    const entryB = new FakeNode("entry", "", [
      new FakeNode("videoId", "B"),
      new FakeNode("published", "not-a-date")
    ]);
    return new FakeNode("document", "", [entryA, entryB]);
  }
};
const parsed = parseYouTubeRssXmlPage("<feed><entry /></feed>");
assert.equal(parsed.ok, true);
assert.equal(parsed.entry_count, 2);
assert.deepEqual(parsed.entries, [{ video_id: "A", published_at: "2026-08-03T14:30:00.000Z" }]);
assert.equal(parseYouTubeRssXmlPage("invalid").reason, "invalid_xml");
globalThis.DOMParser = originalDomParser;

const originalDocument = globalThis.document;
const originalWindow = globalThis.window;
const originalLocation = globalThis.location;
globalThis.document = {
  querySelector(selector) {
    if (selector === 'meta[itemprop="channelId"]') return null;
    if (selector === 'link[rel="canonical"]') return { href: "https://www.youtube.com/@demo" };
    return null;
  },
  querySelectorAll() { return []; }
};
globalThis.window = {
  ytInitialData: { metadata: { channelId: "UCabcdefghijklmnopqrstuv" } },
  ytInitialPlayerResponse: null
};
globalThis.location = { origin: "https://www.youtube.com" };
assert.deepEqual(extractYouTubeChannelIdPage(), {
  channel_id: "UCabcdefghijklmnopqrstuv",
  source: "youtube_structured_data"
});
globalThis.document = originalDocument;
globalThis.window = originalWindow;
globalThis.location = originalLocation;

const originalChrome = globalThis.chrome;
const originalFetch = globalThis.fetch;
const discoveredVideo = {
  video_id: "A",
  video_url: "https://www.youtube.com/shorts/A",
  title: "A",
  views: 100,
  likes: 10,
  comments: 1,
  published_at: null,
  is_pinned: false,
  source: "ytInitialData:shortsLockupViewModel"
};
const installCollectorFixture = (channelResult, parsedResult) => {
  globalThis.chrome = {
    scripting: {
      async executeScript({ func, args }) {
        if (func.name === "discoverYouTubeContent") return [{ result: [structuredClone(discoveredVideo)] }];
        if (func.name === "fetchYouTubeContentDetail") {
          return [{
            result: {
              video_id: args[0],
              detail_missing_reason: "detail unavailable"
            }
          }];
        }
        if (func.name === "extractYouTubeChannelIdPage") return [{ result: channelResult }];
        if (func.name === "parseYouTubeRssXmlPage") return [{ result: parsedResult }];
        throw new Error(`Unexpected function ${func.name}`);
      }
    }
  };
};

installCollectorFixture(
  { channel_id: "UC1234567890123456789012", source: "youtube_structured_data" },
  { ok: true, reason: "", entry_count: 1, entries: [{ video_id: "A", published_at: "2026-08-03T14:30:00Z" }] }
);
globalThis.fetch = async () => ({ ok: true, status: 200, text: async () => "<feed />" });
const collectedWithRss = await (await import("../chrome_extension/platform/youtube.js")).collectRecentContent(1, {
  analysisUrl: "https://www.youtube.com/@demo/shorts",
  limit: 1
});
assert.equal(collectedWithRss.returned_count, 1);
assert.equal(collectedWithRss.contents[0].published_at.value, "2026-08-03T14:30:00.000Z");
assert.equal(collectedWithRss.rss_date_enrichment.supplemented_count, 1);

installCollectorFixture(
  { channel_id: "UC1234567890123456789012", source: "youtube_structured_data" },
  { ok: false, reason: "invalid_xml", entry_count: 0, entries: [] }
);
globalThis.fetch = async () => ({ ok: false, status: 404, text: async () => "" });
const collectedAfter404 = await (await import("../chrome_extension/platform/youtube.js")).collectRecentContent(1, {
  analysisUrl: "https://www.youtube.com/@demo/shorts",
  limit: 1
});
assert.equal(collectedAfter404.returned_count, 1);
assert.equal(collectedAfter404.contents[0].views.value, 100);
assert.equal(collectedAfter404.contents[0].published_at.value, null);
assert.equal(collectedAfter404.rss_date_enrichment.reason, "http_error");

globalThis.fetch = async () => ({ ok: true, status: 200, text: async () => "invalid" });
const collectedAfterInvalidXml = await (await import("../chrome_extension/platform/youtube.js")).collectRecentContent(1, {
  analysisUrl: "https://www.youtube.com/@demo/shorts",
  limit: 1
});
assert.equal(collectedAfterInvalidXml.returned_count, 1);
assert.equal(collectedAfterInvalidXml.rss_date_enrichment.reason, "invalid_xml");

globalThis.fetch = async () => { throw new Error("offline"); };
const collectedAfterNetworkError = await (await import("../chrome_extension/platform/youtube.js")).collectRecentContent(1, {
  analysisUrl: "https://www.youtube.com/@demo/shorts",
  limit: 1
});
assert.equal(collectedAfterNetworkError.returned_count, 1);
assert.equal(collectedAfterNetworkError.rss_date_enrichment.reason, "network_error");

installCollectorFixture({ channel_id: null, source: "missing" }, null);
let rssRequested = false;
globalThis.fetch = async () => {
  rssRequested = true;
  throw new Error("RSS should be skipped");
};
const collectedWithoutChannelId = await (await import("../chrome_extension/platform/youtube.js")).collectRecentContent(1, {
  analysisUrl: "https://www.youtube.com/@demo/shorts",
  limit: 1
});
assert.equal(rssRequested, false);
assert.equal(collectedWithoutChannelId.returned_count, 1);
assert.equal(collectedWithoutChannelId.rss_date_enrichment.reason, "channel_id_unavailable");
globalThis.chrome = originalChrome;
globalThis.fetch = originalFetch;

const assistantSource = readFileSync(
  new URL("../chrome_extension/content/floating_assistant.js", import.meta.url),
  "utf8"
);
assert.doesNotMatch(assistantSource, /YouTube 临时诊断/);
assert.doesNotMatch(assistantSource, /youtube_shorts_diagnostic/);

console.log("M3-B YouTube RSS date tests passed.");
