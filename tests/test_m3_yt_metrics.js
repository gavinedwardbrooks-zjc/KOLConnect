import assert from "node:assert/strict";
import { parseHumanCount } from "../chrome_extension/core/normalize.js";
import { engagementRate } from "../chrome_extension/core/content_analysis.js";
import { collectRecentContent } from "../chrome_extension/platform/youtube.js";

const countCases = new Map([
  ["8864次观看", 8864],
  ["2.3万次观看", 23000],
  ["15万次观看", 150000],
  ["1.2萬次觀看", 12000],
  ["23K views", 23000],
  ["1.5M views", 1500000],
  ["1,234 条评论", 1234],
  ["2.3万条评论", 23000]
]);
for (const [input, expected] of countCases) {
  assert.equal(parseHumanCount(input), expected, input);
}
assert.equal(parseHumanCount("评论"), null);

const originalChrome = globalThis.chrome;
const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
const originalLocation = globalThis.location;

function assignedHtml(player, initialData) {
  return `<script>var ytInitialPlayerResponse = ${JSON.stringify(player)};</script>`
    + `<script>var ytInitialData = ${JSON.stringify(initialData)};</script>`;
}

async function collectFixture({ cardViews, cardSource = "overlayMetadata.secondaryText", player, initialData }) {
  const discovered = [{
    video_id: "videoA",
    video_url: "https://www.youtube.com/shorts/videoA",
    title: "Fixture Short",
    views: cardViews,
    likes: null,
    comments: null,
    published_at: "2026-08-01T00:00:00.000Z",
    is_pinned: false,
    source: "ytInitialData:shortsLockupViewModel",
    views_source_hint: cardSource
  }];
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    url: "https://www.youtube.com/watch?v=videoA",
    headers: { get: () => "text/html" },
    text: async () => assignedHtml(player, initialData)
  });
  globalThis.chrome = {
    scripting: {
      async executeScript({ func, args = [] }) {
        if (func.name === "discoverYouTubeContent") return [{ result: structuredClone(discovered) }];
        if (func.name === "fetchYouTubeContentDetail") return [{ result: await func(...args) }];
        if (func.name === "extractYouTubeChannelIdPage") {
          return [{ result: { channel_id: "", source: "missing" } }];
        }
        throw new Error(`Unexpected function ${func.name}`);
      }
    }
  };
  return collectRecentContent(1, {
    analysisUrl: "https://www.youtube.com/@fixture/shorts",
    limit: 1
  });
}

const modernInitialData = {
  contents: [{
    likeButtonViewModel: {
      likeButtonViewModel: {
        toggleButtonViewModel: {
          toggleButtonViewModel: {
            defaultButtonViewModel: { buttonViewModel: { title: "500" } },
            likeStatus: "INDIFFERENT"
          }
        }
      }
    },
    commentsHeaderRenderer: {
      countText: { simpleText: "100 条评论" }
    }
  }]
};
const exact = await collectFixture({
  cardViews: "2.3万次观看",
  player: {
    videoDetails: { title: "Fixture Short", viewCount: "23377" },
    microformat: { playerMicroformatRenderer: {} }
  },
  initialData: modernInitialData
});
assert.equal(exact.contents[0].views.value, 23377);
assert.equal(exact.contents[0].likes.value, 500);
assert.equal(exact.contents[0].comments.value, 100);
assert.equal(exact.contents[0].engagement_rate.value, (600 / 23377) * 100);

const correctedAbbreviation = await collectFixture({
  cardViews: "23000",
  player: { videoDetails: { viewCount: "23377" }, microformat: { playerMicroformatRenderer: {} } },
  initialData: modernInitialData
});
assert.equal(correctedAbbreviation.contents[0].views.value, 23377);

const detailMissing = await collectFixture({
  cardViews: "8864次观看",
  player: { videoDetails: {}, microformat: { playerMicroformatRenderer: {} } },
  initialData: { contents: [] }
});
assert.equal(detailMissing.contents[0].views.value, 8864);
assert.equal(detailMissing.contents[0].likes.value, null);
assert.equal(detailMissing.contents[0].comments.value, null);
assert.equal(detailMissing.contents[0].engagement_rate.value, null);

const legacy = await collectFixture({
  cardViews: "1000 views",
  player: { videoDetails: { viewCount: "1000" }, microformat: { playerMicroformatRenderer: {} } },
  initialData: {
    contents: [{
      toggleButtonRenderer: { defaultText: { simpleText: "42 likes" } },
      commentsHeaderRenderer: { countText: { simpleText: "评论" } }
    }],
    microformat: { comments: [{ text: "one" }, { text: "two" }] }
  }
});
assert.equal(legacy.contents[0].likes.value, 42);
assert.equal(legacy.contents[0].comments.value, null);

globalThis.chrome = {
  scripting: {
    async executeScript({ func, args = [] }) {
      if (func.name === "discoverYouTubeContent") {
        globalThis.location = { href: args[0] };
        globalThis.window = {
          ytInitialData: {
            contents: [{
              shortsLockupViewModel: {
                videoId: "videoB",
                headline: { simpleText: "Fixture Short B" },
                overlayMetadata: { secondaryText: { content: "7 days ago" } }
              }
            }]
          }
        };
        return [{ result: await func(...args) }];
      }
      if (func.name === "fetchYouTubeContentDetail") {
        return [{ result: { video_id: args[0], detail_missing_reason: "detail unavailable" } }];
      }
      if (func.name === "extractYouTubeChannelIdPage") {
        return [{ result: { channel_id: "", source: "missing" } }];
      }
      throw new Error(`Unexpected function ${func.name}`);
    }
  }
};
const semanticGuard = await collectRecentContent(1, {
  analysisUrl: "https://www.youtube.com/@fixture/shorts",
  limit: 1
});
assert.equal(semanticGuard.contents[0].views.value, null);

assert.equal(
  engagementRate({ value: 10000 }, { value: 500 }, { value: 100 }).value,
  6
);
assert.equal(engagementRate({ value: 10000 }, { value: null }, { value: 100 }).value, null);

globalThis.chrome = originalChrome;
globalThis.fetch = originalFetch;
globalThis.window = originalWindow;
globalThis.location = originalLocation;

console.log("M3-B.3 YouTube Shorts metrics tests passed.");
