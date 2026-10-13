import assert from "node:assert/strict";

import { collectProfile, collectRecentContent } from "../chrome_extension/platform/youtube.js";

const saved = {
  chrome: globalThis.chrome,
  document: globalThis.document,
  fetch: globalThis.fetch,
  location: globalThis.location,
  window: globalThis.window
};

function fieldDocument(metaDescription = "") {
  return {
    querySelector(selector) {
      if (selector === 'meta[name="description"]') return { content: metaDescription };
      return null;
    },
    querySelectorAll() { return []; }
  };
}

function profileChrome(profileResult = null) {
  return {
    scripting: {
      async executeScript({ func }) {
        if (profileResult && func.name === "fetchYouTubeChannelHomeData") {
          return [{ result: structuredClone(profileResult) }];
        }
        return [{ result: await func() }];
      }
    }
  };
}

globalThis.location = { href: "https://www.youtube.com/@valzinhasz/shorts" };
globalThis.window = {
  ytInitialData: {
    metadata: {
      channelMetadataRenderer: {
        title: "Valzinha",
        description: "Humor e Diversão ✨"
      }
    },
    header: {
      pageHeaderRenderer: {
        content: {
          subscriberCountText: { content: "1,2 mi de inscritos" }
        }
      }
    },
    microformat: {
      microformatDataRenderer: {
        channelProfileMicroformatDetails: {
          profilePage: {
            mainEntity: {
              interactionStatistic: [{
                interactionType: { type: "FollowAction" },
                userInteractionCount: "4160000"
              }]
            }
          }
        }
      }
    }
  },
  ytInitialPlayerResponse: null
};
globalThis.document = fieldDocument(
  "在 YouTube 上畅享你喜爱的视频和音乐，上传原创内容并与亲朋好友和全世界分享。"
);
globalThis.chrome = profileChrome();

const publicProfile = await collectProfile(1);
assert.equal(publicProfile.fields.username.value, "@valzinhasz");
assert.equal(publicProfile.fields.creator_name.value, "Valzinha");
assert.equal(publicProfile.fields.followers.value, "1,2 mi de inscritos");
assert.equal(publicProfile.fields.followers.source, "ytInitialData");
assert.equal(publicProfile.fields.bio.value, "Humor e Diversão ✨");
assert.equal(publicProfile.fields.bio.source, "structured_data");
assert.equal(publicProfile.profile_diagnostics.bio_meta_rejected, true);
assert.equal(publicProfile.profile_diagnostics.bio_meta_rejection_reason, "generic_meta_not_channel_owned");

globalThis.window.ytInitialData.header = {};
const modernProfile = await collectProfile(1);
assert.equal(modernProfile.fields.followers.value, "4160000");
assert.equal(
  modernProfile.profile_diagnostics.subscriber_candidate_source,
  "ytInitialData.interactionStatistic"
);

globalThis.location = { href: "https://www.youtube.com/@valzinhasz" };
globalThis.window = {
  ytInitialData: { metadata: { channelMetadataRenderer: { title: "Valzinha" } } },
  ytInitialPlayerResponse: null
};
globalThis.document = fieldDocument(
  "在 YouTube 上畅享你喜爱的视频和音乐，上传原创内容并与亲朋好友和全世界分享。"
);
globalThis.chrome = profileChrome();
const genericMetaProfile = await collectProfile(1);
assert.equal(genericMetaProfile.fields.bio.value, null);
assert.equal(genericMetaProfile.fields.bio.source, "missing");

globalThis.location = { href: "https://www.youtube.com/@valzinhasz/shorts" };
globalThis.window = {
  ytInitialData: { metadata: { channelMetadataRenderer: { title: "Valzinha" } } },
  ytInitialPlayerResponse: null
};
globalThis.document = fieldDocument();
globalThis.chrome = profileChrome({
  subscribers: null,
  subscriber_hidden: false,
  creator_name: "Valzinha",
  description: "Humor e Diversão ✨"
});
const unknownSubscribers = await collectProfile(1);
assert.equal(unknownSubscribers.fields.followers.value, null);
assert.match(unknownSubscribers.fields.followers.missing_reason, /not found/i);
assert.doesNotMatch(unknownSubscribers.fields.followers.missing_reason, /hide|hidden/i);
assert.equal(unknownSubscribers.profile_diagnostics.subscriber_visibility, "not_found");

const structuredShort = (videoId, title, views) => ({
  shortsLockupViewModel: {
    accessibilityText: `${title}, ${views} - 播放 Shorts 短视频`,
    onTap: { innertubeCommand: { reelWatchEndpoint: { videoId } } },
    overlayMetadata: {
      primaryText: { content: title },
      secondaryText: { content: views }
    }
  }
});
const domCard = (text) => ({
  innerText: text,
  textContent: text,
  getAttribute() { return ""; }
});
const domAnchor = (videoId, title, cardText) => ({
  href: `https://www.youtube.com/shorts/${videoId}`,
  textContent: title,
  getAttribute(name) {
    if (name === "href") return `/shorts/${videoId}`;
    if (name === "title") return title;
    return "";
  },
  closest() { return domCard(cardText); }
});
const anchors = [
  domAnchor("KOW-QMg-Ie0", "Duplicate structured Short", "Duplicate structured Short 999次观看"),
  domAnchor("56-74FFeCFI", "DOM fallback Short", "DOM fallback Short 2.6万次观看"),
  domAnchor("", "Navigation", "Shorts")
];
const contentRoot = { querySelectorAll: () => anchors };
globalThis.location = {
  href: "https://www.youtube.com/@valzinhasz/shorts",
  origin: "https://www.youtube.com"
};
globalThis.window = {
  ytInitialData: {
    contents: [
      structuredShort("KOW-QMg-Ie0", "Ela é uma gata", "2.1万次观看"),
      structuredShort("YQr-y9DjEE0", "Eu e minhas amigas", "6.2万次观看"),
      structuredShort("KOW-QMg-Ie0", "Duplicate", "2.1万次观看")
    ]
  },
  ytInitialPlayerResponse: null
};
globalThis.document = {
  querySelector(selector) {
    if (selector.startsWith("ytd-rich-grid-renderer")) return contentRoot;
    return null;
  },
  querySelectorAll() { return []; }
};
globalThis.chrome = {
  scripting: {
    async executeScript({ func, args = [] }) {
      if (func.name === "discoverYouTubeContent") return [{ result: await func(...args) }];
      if (func.name === "fetchYouTubeContentDetail") {
        return [{ result: { video_id: args[0], detail_missing_reason: "detail unavailable" } }];
      }
      if (func.name === "extractYouTubeChannelIdPage") {
        return [{ result: { channel_id: null, source: "missing" } }];
      }
      throw new Error(`Unexpected function ${func.name}`);
    }
  }
};

const shorts = await collectRecentContent(1, {
  analysisUrl: "https://www.youtube.com/@valzinhasz/shorts",
  limit: 30
});
assert.equal(shorts.discovered_count, 3);
assert.equal(shorts.returned_count, 3);
assert.equal(new Set(shorts.contents.map((item) => item.video_id)).size, 3);
assert.equal(shorts.valid_views_count, 3);
assert.equal(shorts.capture_status, "partial_success");
assert.deepEqual(shorts.capture_diagnostics.youtube_discovery, {
  structured_source_present: true,
  structured_candidate_count: 3,
  dom_candidate_count: 2,
  unique_video_count: 3
});
assert.equal(
  shorts.contents.find((item) => item.video_id === "KOW-QMg-Ie0").views.value,
  21000
);
assert.equal(
  shorts.contents.find((item) => item.video_id === "56-74FFeCFI").views.value,
  26000
);

globalThis.chrome = saved.chrome;
globalThis.document = saved.document;
globalThis.fetch = saved.fetch;
globalThis.location = saved.location;
globalThis.window = saved.window;

console.log("YouTube Shorts passive capture repair tests passed.");
