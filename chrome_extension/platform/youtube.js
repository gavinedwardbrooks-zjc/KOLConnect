import {
  CONTENT_DETAIL_CONCURRENCY,
  CONTENT_DETAIL_DELAY_MS,
  finalizeContentAnalysis,
  mapWithConcurrency,
  parsePublishedText
} from "../core/content_analysis.js";
import {
  abortPageDetailRequests,
  applyPublicProfileFields,
  executePageFunction,
  executeProfileCollector,
  hostMatches,
  selectBio
} from "./common.js";
import { parseHumanCount } from "../core/normalize.js";

export function matches(url) {
  return hostMatches(url, "youtube.com");
}

function collectYouTubePage() {
  const clean = (value, limit = 5000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  const multiline = (value, limit = 5000) => String(value ?? "")
    .replace(/\\r\\n|\\r|\\n/g, "\n")
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n")
    .slice(0, limit)
    .trim();
  const field = (value, source, confidence, reason) => ({
    value: clean(value) || null,
    source: clean(value) ? source : "",
    confidence: clean(value) ? confidence : "missing",
    missing_reason: clean(value) ? "" : reason
  });
  const textFrom = (value) => {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number") return clean(value);
    return clean(value.simpleText || value.content || value.text || value.runs?.map((item) => item.text).join(""));
  };
  const text = (selector) => clean(document.querySelector(selector)?.textContent);
  const meta = (selector) => clean(document.querySelector(selector)?.content);
  const current = new URL(location.href);
  const parts = current.pathname.split("/").filter(Boolean);
  const root = parts[0] || "";
  const supportedRoot = root.startsWith("@") || ["channel", "c", "user"].includes(root);
  const identifier = root.startsWith("@") ? root : parts[1] || "";
  if (!supportedRoot || !identifier) {
    return {
      platform: "YouTube",
      analysis_url: current.href,
      supported: false,
      fields: {},
      searched_sources: ["ytInitialData", "page_dom", "meta", "url"],
      errors: ["The current page is not a YouTube channel page."]
    };
  }

  let metadata = null;
  let headerName = "";
  let subscribers = "";
  let country = "";
  let language = "";
  const queue = [window.ytInitialData, window.ytInitialPlayerResponse].filter(Boolean);
  const seen = new WeakSet();
  let visited = 0;
  while (queue.length && visited < 5000) {
    const node = queue.shift();
    if (!node || typeof node !== "object" || seen.has(node)) continue;
    seen.add(node);
    visited += 1;
    if (!metadata && node.channelMetadataRenderer) metadata = node.channelMetadataRenderer;
    if (!metadata && node.microformatDataRenderer?.title) {
      metadata = {
        title: node.microformatDataRenderer.title,
        description: node.microformatDataRenderer.description
      };
    }
    if (!headerName && node.c4TabbedHeaderRenderer) {
      headerName = textFrom(node.c4TabbedHeaderRenderer.title);
    }
    if (!headerName && node.pageHeaderRenderer) {
      headerName = textFrom(
        node.pageHeaderRenderer.pageTitle
        || node.pageHeaderRenderer.content?.pageHeaderViewModel?.title
      );
    }
    if (!headerName && node.pageHeaderViewModel) {
      headerName = textFrom(node.pageHeaderViewModel.title);
    }
    if (!country && node.channelAboutFullMetadataRenderer) {
      country = textFrom(node.channelAboutFullMetadataRenderer.country);
    }
    if (!country && node.channelMetadataRenderer?.country) {
      country = textFrom(node.channelMetadataRenderer.country);
    }
    if (!language && node.microformatDataRenderer?.language) {
      language = textFrom(node.microformatDataRenderer.language);
    }
    for (const [key, value] of Object.entries(node)) {
      if (!subscribers && /subscriberCountText/i.test(key)) subscribers = textFrom(value);
      if (value && typeof value === "object") queue.push(value);
    }
  }

  const domName = text("yt-page-header-renderer h1")
    || text("ytd-c4-tabbed-header-renderer #channel-name")
    || text("#page-header #channel-name");
  const domSubscribers = text("#subscriber-count") || text("yt-formatted-string#subscriber-count");
  const domDescriptionNode = document.querySelector(
    "ytd-channel-about-metadata-renderer #description, yt-description-preview-view-model #description, #description-container #description"
  );
  const domDescription = multiline(domDescriptionNode?.innerText || domDescriptionNode?.textContent);
  const metaDescription = meta('meta[name="description"]');
  const metadataName = textFrom(metadata?.title);
  const creatorName = metadataName || headerName || domName;
  const creatorNameSource = metadataName
    ? "channelMetadataRenderer"
    : headerName ? "pageHeaderRenderer" : domName ? "page_dom" : "meta";
  const profileUrl = root.startsWith("@")
    ? `https://www.youtube.com/${root}`
    : `https://www.youtube.com/${root}/${identifier}`;
  const contactLinks = [...document.querySelectorAll('a[href^="mailto:"], a[href*="wa.me/"], a[href*="api.whatsapp.com/"]')]
    .map((node) => clean(node.href || node.textContent, 512));

  return {
    platform: "YouTube",
    analysis_url: current.href,
    supported: true,
    fields: {
      profile_url: field(profileUrl, "url", "high", ""),
      username: field(identifier, "url", "high", ""),
      creator_name: field(creatorName, creatorNameSource, metadataName || headerName || domName ? "high" : "medium", "Creator name was not exposed by the current public page."),
      followers: field(subscribers || domSubscribers, subscribers ? "ytInitialData" : "page_dom", "high", "Subscriber count was not exposed by the current public page."),
      bio: field(null, "", "missing", "The current YouTube channel page did not expose a public description.")
    },
    bio_candidates: [
      { source: "structured_data", value: multiline(metadata?.description) },
      { source: "profile_dom", value: domDescription },
      { source: "meta", value: metaDescription }
    ],
    public_profile: {
      email_candidates: [
        ...contactLinks.map((value) => ({ source: "profile_dom", value })),
        { source: "profile_dom", value: domDescription },
        { source: "meta", value: metaDescription }
      ],
      whatsapp_candidates: [
        ...contactLinks.map((value) => ({ source: "profile_dom", value })),
        { source: "profile_dom", value: domDescription }
      ],
      country_candidates: [{ source: "structured_data", value: country }],
      language_candidates: [{ source: "structured_data", value: language }]
    },
    searched_sources: ["ytInitialData", "page_dom", "meta", "url"],
    errors: []
  };
}

export async function collectProfile(tabId) {
  const result = await executeProfileCollector(tabId, collectYouTubePage);
  result.fields ||= {};
  result.fields.bio = selectBio(result.bio_candidates, {
    platform: "youtube",
    username: result.fields.username?.value,
    creatorName: result.fields.creator_name?.value
  });
  delete result.bio_candidates;
  const pathname = new URL(result.analysis_url || result.fields.profile_url?.value || "https://www.youtube.com").pathname;
  const hasText = (value) => typeof value === "string" && value.trim().length > 0;
  const needsHomeLookup = /\/(?:shorts|videos)\/?$/.test(pathname)
    && (
      !hasText(result.fields.followers?.value)
      || !hasText(result.fields.creator_name?.value)
      || !hasText(result.fields.bio?.value)
    );
  if (needsHomeLookup && result.fields.profile_url?.value) {
    const homeResult = await executePageFunction(
      tabId,
      fetchYouTubeChannelHomeData,
      [result.fields.profile_url.value]
    );
    if (!hasText(result.fields.followers?.value)) {
      if (homeResult?.subscribers != null && homeResult.subscribers !== "") {
        result.fields.followers = {
          value: homeResult.subscribers,
          source: "channel_home_structured_data",
          confidence: "high",
          missing_reason: ""
        };
      } else {
        result.fields.followers = {
          value: null,
          source: "missing",
          confidence: "missing",
          missing_reason: "The YouTube channel hides or does not expose its subscriber count."
        };
      }
    }
    if (!hasText(result.fields.creator_name?.value) && hasText(homeResult?.creator_name)) {
      result.fields.creator_name = {
        value: homeResult.creator_name.trim(),
        source: "channel_home_structured_data",
        confidence: "high",
        missing_reason: ""
      };
    }
    if (!hasText(result.fields.bio?.value) && hasText(homeResult?.description)) {
      result.fields.bio = {
        value: homeResult.description.trim(),
        source: "channel_home_structured_data",
        confidence: "high",
        missing_reason: ""
      };
    }
    if (hasText(homeResult?.description)) {
      result.public_profile?.email_candidates?.push({
        source: "channel_home_structured_data",
        value: homeResult.description
      });
      result.public_profile?.whatsapp_candidates?.push({
        source: "channel_home_structured_data",
        value: homeResult.description
      });
    }
  }
  if (!result.fields.followers?.value) {
    result.fields.followers = {
      value: null,
      source: "missing",
      confidence: "missing",
      missing_reason: "The YouTube channel hides or does not expose its subscriber count."
    };
  }
  applyPublicProfileFields(result);
  return result;
}

export function getDiagnostics(result) {
  return {
    searched_sources: result?.searched_sources || [],
    errors: result?.errors || []
  };
}

async function fetchYouTubeChannelHomeData(homeUrl) {
  const textFrom = (value) => {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number") return String(value).trim();
    return String(
      value.simpleText
      || value.content
      || value.text
      || value.runs?.map((item) => item.text).join("")
      || ""
    ).trim();
  };
  const extractAssignedJson = (html, marker) => {
    const markerIndex = html.indexOf(marker);
    if (markerIndex < 0) return null;
    const start = html.indexOf("{", markerIndex + marker.length);
    if (start < 0) return null;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < html.length; index += 1) {
      const char = html[index];
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inString = false;
        continue;
      }
      if (char === '"') inString = true;
      else if (char === "{") depth += 1;
      else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          try { return JSON.parse(html.slice(start, index + 1)); } catch (_) { return null; }
        }
      }
    }
    return null;
  };
  try {
    const response = await fetch(homeUrl, { credentials: "include", redirect: "follow" });
    if (!response.ok) return { subscribers: null };
    const html = await response.text();
    const initialData = extractAssignedJson(html, "var ytInitialData =")
      || extractAssignedJson(html, 'window["ytInitialData"] =')
      || extractAssignedJson(html, "ytInitialData =");
    const queue = [initialData].filter(Boolean);
    const seen = new WeakSet();
    let visited = 0;
    let subscribers = "";
    let creatorName = "";
    let description = "";
    while (queue.length && visited < 12000) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      visited += 1;
      if (node.channelMetadataRenderer) {
        creatorName ||= textFrom(node.channelMetadataRenderer.title);
        description ||= textFrom(node.channelMetadataRenderer.description);
      }
      if (node.microformatDataRenderer) {
        creatorName ||= textFrom(node.microformatDataRenderer.title);
        description ||= textFrom(node.microformatDataRenderer.description);
      }
      if (node.c4TabbedHeaderRenderer) {
        creatorName ||= textFrom(node.c4TabbedHeaderRenderer.title);
      }
      if (node.pageHeaderRenderer) {
        creatorName ||= textFrom(
          node.pageHeaderRenderer.pageTitle
          || node.pageHeaderRenderer.content?.pageHeaderViewModel?.title
        );
      }
      if (node.pageHeaderViewModel) {
        creatorName ||= textFrom(node.pageHeaderViewModel.title);
      }
      for (const [key, value] of Object.entries(node)) {
        if (!subscribers && /^(?:subscriberCountText|subscriberCount)$/i.test(key)) {
          subscribers = textFrom(value);
        }
        if (value && typeof value === "object") queue.push(value);
      }
    }
    return {
      subscribers: subscribers || null,
      creator_name: creatorName || null,
      description: description || null
    };
  } catch (_) {
    return { subscribers: null, creator_name: null, description: null };
  }
}

async function discoverYouTubeContent(targetUrl, contentType) {
  const clean = (value, limit = 2000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  const textFrom = (value) => {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number") return clean(value);
    return clean(value.simpleText || value.content || value.text || value.runs?.map((item) => item.text).join(""));
  };
  const extractAssignedJson = (html, marker) => {
    const markerIndex = html.indexOf(marker);
    if (markerIndex < 0) return null;
    const start = html.indexOf("{", markerIndex + marker.length);
    if (start < 0) return null;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < html.length; index += 1) {
      const char = html[index];
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inString = false;
        continue;
      }
      if (char === '"') inString = true;
      else if (char === "{") depth += 1;
      else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          try { return JSON.parse(html.slice(start, index + 1)); } catch (_) { return null; }
        }
      }
    }
    return null;
  };

  let root = null;
  if (location.href.split(/[?#]/)[0].replace(/\/$/, "") === targetUrl.replace(/\/$/, "")) {
    root = window.ytInitialData;
  }
  if (!root) {
    try {
      const response = await fetch(targetUrl, { credentials: "include", redirect: "follow" });
      if (!response.ok) return [];
      const html = await response.text();
      root = extractAssignedJson(html, "var ytInitialData =")
        || extractAssignedJson(html, 'window["ytInitialData"] =')
        || extractAssignedJson(html, "ytInitialData =");
    } catch (_) {
      return [];
    }
  }
  if (!root) return [];

  const byId = new Map();
  const add = (node, rendererType) => {
    const videoId = clean(
      node.videoId
      || node.onTap?.innertubeCommand?.reelWatchEndpoint?.videoId
      || node.command?.reelWatchEndpoint?.videoId,
      128
    );
    if (!videoId) return;
    const isShort = contentType === "short";
    const metadata = node.overlayMetadata?.primaryText || node.overlayMetadata?.secondaryText;
    const accessibility = textFrom(
      node.accessibilityText
      || node.accessibility?.accessibilityData?.label
      || node.thumbnail?.accessibility?.accessibilityData?.label
    );
    const hasViewsSemantics = (value) => /\bviews?\b|(?:次)?观看|(?:次)?觀看|播放(?:量|次数|次數)?|visualiza(?:ção|ções)|vistas?/i.test(value);
    const selectedRenderer = [
      { value: node.viewCountText, source: "viewCountText" },
      { value: node.shortViewCountText, source: "shortViewCountText" },
      { value: node.overlayMetadata?.secondaryText, source: "overlayMetadata.secondaryText" }
    ].find((candidate) => {
      const text = textFrom(candidate.value);
      return /\d/.test(text) && hasViewsSemantics(text);
    });
    const selectedRendererText = textFrom(selectedRenderer?.value);
    const accessibilityViewsCandidate = /\d/.test(accessibility) && hasViewsSemantics(accessibility)
      ? accessibility
      : "";
    const viewsText = selectedRendererText || accessibilityViewsCandidate;
    const selectedViewsSource = selectedRendererText
      ? selectedRenderer.source
      : accessibilityViewsCandidate ? "accessibility" : "missing";
    const publishedText = textFrom(node.publishedTimeText);
    byId.set(videoId, {
      video_id: videoId,
      video_url: isShort
        ? `https://www.youtube.com/shorts/${videoId}`
        : `https://www.youtube.com/watch?v=${videoId}`,
      title: textFrom(node.title || node.headline || metadata) || null,
      views: viewsText || null,
      likes: null,
      comments: null,
      published_at: null,
      published_raw_text: publishedText,
      is_pinned: false,
      source: `ytInitialData:${rendererType}`,
      views_source_hint: selectedViewsSource
    });
  };

  const queue = [root];
  const seen = new WeakSet();
  let visited = 0;
  while (queue.length && visited < 18000 && byId.size < 60) {
    const node = queue.shift();
    if (!node || typeof node !== "object" || seen.has(node)) continue;
    seen.add(node);
    visited += 1;
    if (contentType === "video") {
      if (node.videoRenderer) add(node.videoRenderer, "videoRenderer");
      if (node.gridVideoRenderer) add(node.gridVideoRenderer, "gridVideoRenderer");
    } else if (node.shortsLockupViewModel) {
      add(node.shortsLockupViewModel, "shortsLockupViewModel");
    } else if (node.reelItemRenderer) {
      add(node.reelItemRenderer, "reelItemRenderer");
    }
    for (const child of Array.isArray(node) ? node : Object.values(node)) {
      if (child && typeof child === "object") queue.push(child);
    }
  }
  return [...byId.values()];
}

async function fetchYouTubeContentDetail(videoId) {
  const clean = (value, limit = 3000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  const textFrom = (value) => {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number") return clean(value);
    return clean(value.simpleText || value.content || value.text || value.runs?.map((item) => item.text).join(""));
  };
  const extractAssignedJson = (html, marker) => {
    const markerIndex = html.indexOf(marker);
    if (markerIndex < 0) return null;
    const start = html.indexOf("{", markerIndex + marker.length);
    if (start < 0) return null;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < html.length; index += 1) {
      const char = html[index];
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inString = false;
        continue;
      }
      if (char === '"') inString = true;
      else if (char === "{") depth += 1;
      else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          try { return JSON.parse(html.slice(start, index + 1)); } catch (_) { return null; }
        }
      }
    }
    return null;
  };
  const missing = "YouTube did not expose this field on the public video page.";
  const numericTextFrom = (root) => {
    if (!root || typeof root !== "object") return "";
    const queue = [root];
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < 300) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      visited += 1;
      for (const [key, value] of Object.entries(node)) {
        if (/^(?:title|text|simpleText|content|label|accessibilityText|countText)$/i.test(key)) {
          const candidate = textFrom(value);
          if (/\d/.test(candidate)) return candidate;
        }
        if (value && typeof value === "object") queue.push(value);
      }
    }
    return "";
  };
  const registry = globalThis.__KOLCONNECT_DETAIL_CONTROLLERS__
    ||= new Set();
  const controller = new AbortController();
  registry.add(controller);
  try {
    const response = await fetch(`https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`, {
      credentials: "include",
      redirect: "follow",
      signal: controller.signal
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const html = await response.text();
    const player = extractAssignedJson(html, "var ytInitialPlayerResponse =")
      || extractAssignedJson(html, 'window["ytInitialPlayerResponse"] =')
      || extractAssignedJson(html, "ytInitialPlayerResponse =");
    const initialData = extractAssignedJson(html, "var ytInitialData =")
      || extractAssignedJson(html, 'window["ytInitialData"] =')
      || extractAssignedJson(html, "ytInitialData =");
    const microformat = player?.microformat?.playerMicroformatRenderer || {};
    let likes = null;
    let comments = null;
    const queue = [initialData].filter(Boolean);
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < 12000 && (likes == null || comments == null)) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      visited += 1;
      if (likes == null && node.likeButtonViewModel) {
        likes = numericTextFrom(node.likeButtonViewModel) || null;
      }
      if (likes == null && node.toggleButtonViewModel) {
        likes = numericTextFrom(node.toggleButtonViewModel) || null;
      }
      if (likes == null && node.toggleButtonRenderer) {
        const label = textFrom(
          node.toggleButtonRenderer.defaultText
          || node.toggleButtonRenderer.accessibilityData?.accessibilityData?.label
        );
        if (/like/i.test(label) && /\d/.test(label)) {
          likes = label;
        }
      }
      if (comments == null && node.commentsHeaderRenderer) {
        comments = numericTextFrom(node.commentsHeaderRenderer) || null;
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object") queue.push(child);
      }
    }
    return {
      video_id: videoId,
      title: clean(player?.videoDetails?.title) || null,
      views: player?.videoDetails?.viewCount ?? null,
      likes,
      comments,
      published_at: microformat.publishDate || microformat.uploadDate || null,
      detail_source: "detail_page_structured_data",
      detail_missing_reason: missing
    };
  } catch (error) {
    return {
      video_id: videoId,
      detail_missing_reason: error?.message || missing
    };
  } finally {
    registry.delete(controller);
  }
}

function mergeYouTubeDetail(item, detail) {
  const missing = detail?.detail_missing_reason || "YouTube did not expose this field on the public video page.";
  const estimated = item.published_at == null
    ? parsePublishedText(item.published_raw_text)
    : { value: item.published_at, is_estimated: false };
  const publishedValue = detail?.published_at || estimated.value || item.published_at;
  const publishedSource = detail?.published_at
    ? detail.detail_source
    : estimated.value ? item.source : item.published_at != null ? item.source : "";
  const detailViews = parseHumanCount(detail?.views);
  const detailLikes = parseHumanCount(detail?.likes);
  const detailComments = parseHumanCount(detail?.comments);
  const viewsValue = detailViews ?? item.views ?? null;
  const likesValue = item.likes ?? detailLikes ?? null;
  const commentsValue = item.comments ?? detailComments ?? null;
  const viewsSource = detailViews != null ? detail.detail_source : item.views != null ? item.source : "";
  const likesSource = item.likes != null ? item.source : detailLikes != null ? detail.detail_source : "";
  const commentsSource = item.comments != null ? item.source : detailComments != null ? detail.detail_source : "";
  const confidence = (source) => /structured_data|ytInitialData/.test(source || "") ? "high" : "medium";
  return {
    ...item,
    title: detail?.title || item.title,
    views: viewsValue,
    likes: likesValue,
    comments: commentsValue,
    published_at: publishedValue ?? null,
    published_estimated: !detail?.published_at && estimated.is_estimated,
    views_source: viewsSource,
    likes_source: likesSource,
    comments_source: commentsSource,
    published_source: publishedSource,
    views_confidence: confidence(viewsSource),
    likes_confidence: confidence(likesSource),
    comments_confidence: confidence(commentsSource),
    published_confidence: estimated.is_estimated ? "low" : confidence(publishedSource),
    views_missing_reason: viewsValue == null ? missing : "",
    likes_missing_reason: likesValue == null ? missing : "",
    comments_missing_reason: commentsValue == null ? missing : "",
    published_missing_reason: publishedValue == null ? missing : ""
  };
}

function youtubeContentTarget(analysisUrl) {
  const url = new URL(analysisUrl);
  const parts = url.pathname.split("/").filter(Boolean);
  const rootCount = parts[0]?.startsWith("@") ? 1 : 2;
  const rootPath = `/${parts.slice(0, rootCount).join("/")}`;
  const section = parts[rootCount]?.toLowerCase();
  const contentType = section === "videos" ? "video" : "short";
  const targetSection = contentType === "video" ? "videos" : "shorts";
  return {
    contentType,
    targetUrl: `${url.origin}${rootPath}/${targetSection}`
  };
}

export function extractYouTubeChannelIdPage() {
  const validChannelId = (value) => {
    const candidate = String(value ?? "").trim();
    return /^UC[A-Za-z0-9_-]{20,}$/.test(candidate) ? candidate : "";
  };
  const channelIdFromUrl = (value) => {
    try {
      const match = new URL(String(value || ""), location.origin).pathname.match(/\/channel\/(UC[A-Za-z0-9_-]{20,})/);
      return validChannelId(match?.[1]);
    } catch (_) {
      return "";
    }
  };

  const metaChannelId = validChannelId(document.querySelector('meta[itemprop="channelId"]')?.content);
  if (metaChannelId) return { channel_id: metaChannelId, source: "meta_channel_id" };

  const queue = [window.ytInitialData, window.ytInitialPlayerResponse].filter(Boolean);
  const seen = new WeakSet();
  let visited = 0;
  while (queue.length && visited < 15000) {
    const node = queue.shift();
    if (!node || typeof node !== "object" || seen.has(node)) continue;
    seen.add(node);
    visited += 1;
    for (const [key, value] of Object.entries(node)) {
      if (/^(?:channelId|channel_id|browseId|externalId)$/.test(key)) {
        const channelId = validChannelId(value);
        if (channelId) return { channel_id: channelId, source: "youtube_structured_data" };
      }
      if (value && typeof value === "object") queue.push(value);
    }
  }

  const explicitChannelUrls = [
    ...document.querySelectorAll('link[itemprop="url"], meta[itemprop="url"], meta[property="og:url"]')
  ];
  for (const node of explicitChannelUrls) {
    const channelId = channelIdFromUrl(node.href || node.content);
    if (channelId) return { channel_id: channelId, source: "page_channel_url" };
  }

  const canonicalChannelId = channelIdFromUrl(document.querySelector('link[rel="canonical"]')?.href);
  if (canonicalChannelId) return { channel_id: canonicalChannelId, source: "canonical_channel_url" };
  return { channel_id: null, source: "missing" };
}

export async function fetchYouTubeRss(channelId, options = {}) {
  const normalizedChannelId = String(channelId ?? "").trim();
  if (!/^UC[A-Za-z0-9_-]{20,}$/.test(normalizedChannelId)) {
    return { ok: false, reason: "channel_id_unavailable", status: null, xml: "" };
  }
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  try {
    const response = await fetchImpl(
      `https://www.youtube.com/feeds/videos.xml?channel_id=${encodeURIComponent(normalizedChannelId)}`,
      { method: "GET", redirect: "follow", signal: options.signal }
    );
    if (!response.ok) {
      return { ok: false, reason: "http_error", status: response.status, xml: "" };
    }
    const xml = await response.text();
    if (!String(xml || "").trim()) {
      return { ok: false, reason: "empty_response", status: response.status, xml: "" };
    }
    return { ok: true, reason: "", status: response.status, xml };
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    return { ok: false, reason: "network_error", status: null, xml: "" };
  }
}

export function parseYouTubeRssXmlPage(xmlText) {
  const empty = (reason) => ({ ok: false, reason, entry_count: 0, entries: [] });
  if (!String(xmlText || "").trim()) return empty("empty_response");
  try {
    const documentNode = new DOMParser().parseFromString(xmlText, "application/xml");
    if (documentNode.getElementsByTagName("parsererror").length) return empty("invalid_xml");
    const nodesByLocalName = (scope, namespace, localName) => {
      const namespaced = [...scope.getElementsByTagNameNS(namespace, localName)];
      if (namespaced.length) return namespaced;
      return [...scope.getElementsByTagNameNS("*", localName)];
    };
    const entryNodes = nodesByLocalName(documentNode, "http://www.w3.org/2005/Atom", "entry");
    const entries = [];
    for (const entryNode of entryNodes) {
      const videoIdNode = nodesByLocalName(
        entryNode,
        "http://www.youtube.com/xml/schemas/2015",
        "videoId"
      )[0];
      const publishedNode = nodesByLocalName(entryNode, "http://www.w3.org/2005/Atom", "published")[0];
      const videoId = String(videoIdNode?.textContent || "").trim();
      const published = String(publishedNode?.textContent || "").trim();
      const parsedDate = new Date(published);
      if (!videoId || Number.isNaN(parsedDate.getTime())) continue;
      entries.push({ video_id: videoId, published_at: parsedDate.toISOString() });
    }
    return { ok: true, reason: "", entry_count: entryNodes.length, entries };
  } catch (_) {
    return empty("invalid_xml");
  }
}

export function applyYouTubeRssPublishedDates(videos = [], rssEntries = []) {
  const rssByVideoId = new Map();
  for (const entry of rssEntries) {
    const videoId = String(entry?.video_id || "").trim();
    const published = String(entry?.published_at || "").trim();
    if (!videoId || !published || Number.isNaN(new Date(published).getTime())) continue;
    rssByVideoId.set(videoId, new Date(published).toISOString());
  }

  let matchedCount = 0;
  let supplementedCount = 0;
  let preservedCount = 0;
  let uncoveredCount = 0;
  const enrichedVideos = videos.map((video) => {
    const rssPublished = rssByVideoId.get(String(video?.video_id || "").trim());
    const hasPublished = video?.published_at != null && video.published_at !== "";
    if (hasPublished) preservedCount += 1;
    if (!rssPublished) {
      uncoveredCount += 1;
      return video;
    }
    matchedCount += 1;
    if (hasPublished) return video;
    supplementedCount += 1;
    return {
      ...video,
      published_at: rssPublished,
      published_estimated: false,
      published_source: "youtube_rss",
      published_confidence: "high",
      published_missing_reason: ""
    };
  });

  return {
    videos: enrichedVideos,
    entry_count: rssByVideoId.size,
    matched_count: matchedCount,
    supplemented_count: supplementedCount,
    preserved_count: preservedCount,
    uncovered_count: uncoveredCount
  };
}

async function enrichYouTubePublishedDates(tabId, videos, options = {}) {
  const existingDateCount = videos.filter(
    (video) => video?.published_at != null && video.published_at !== ""
  ).length;
  const diagnostics = {
    request_context: "background_service_worker",
    channel_id_source: "missing",
    entry_count: 0,
    matched_count: 0,
    supplemented_count: 0,
    preserved_count: existingDateCount,
    uncovered_count: videos.length,
    status: "skipped",
    reason: "channel_id_unavailable"
  };
  if (existingDateCount === videos.length) {
    diagnostics.uncovered_count = 0;
    diagnostics.reason = "no_missing_dates";
    return { videos, diagnostics };
  }
  try {
    const channel = await executePageFunction(tabId, extractYouTubeChannelIdPage);
    diagnostics.channel_id_source = channel?.source || "missing";
    if (!channel?.channel_id) return { videos, diagnostics };

    const response = await fetchYouTubeRss(channel.channel_id, { signal: options.signal });
    if (!response.ok) {
      diagnostics.status = "fallback";
      diagnostics.reason = response.reason;
      return { videos, diagnostics };
    }
    const parsed = await executePageFunction(tabId, parseYouTubeRssXmlPage, [response.xml]);
    if (!parsed?.ok) {
      diagnostics.status = "fallback";
      diagnostics.reason = parsed?.reason || "invalid_xml";
      return { videos, diagnostics };
    }

    const applied = applyYouTubeRssPublishedDates(videos, parsed.entries);
    const { videos: enrichedVideos, ...counts } = applied;
    return {
      videos: enrichedVideos,
      diagnostics: {
        ...diagnostics,
        ...counts,
        entry_count: parsed.entry_count,
        status: "success",
        reason: ""
      }
    };
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    diagnostics.status = "fallback";
    diagnostics.reason = "rss_enrichment_error";
    return { videos, diagnostics };
  }
}

export async function collectRecentContent(tabId, options = {}) {
  const limit = Math.max(1, Math.min(30, Number(options.limit) || 30));
  const target = youtubeContentTarget(options.analysisUrl);
  options.onProgress?.({ phase: "discovering" });
  const discovered = await executePageFunction(
    tabId,
    discoverYouTubeContent,
    [target.targetUrl, target.contentType]
  );
  const eligible = discovered.slice(0, limit);
  options.onProgress?.({
    phase: "discovered",
    discovered: discovered.length,
    excludedPinned: 0
  });
  const completed = await mapWithConcurrency(
    eligible,
    async (item) => {
      if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      if (item.views != null && item.likes != null && item.comments != null && item.published_at != null) {
        return mergeYouTubeDetail(item, null);
      }
      const detail = await executePageFunction(tabId, fetchYouTubeContentDetail, [item.video_id]);
      if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      return mergeYouTubeDetail(item, detail);
    },
    {
      concurrency: CONTENT_DETAIL_CONCURRENCY,
      delay: CONTENT_DETAIL_DELAY_MS,
      signal: options.signal,
      onProgress: options.onProgress
    }
  );
  const completedById = new Map(completed.map((item) => [item.video_id || item.video_url, item]));
  const merged = discovered.map((item) => completedById.get(item.video_id || item.video_url) || item);
  const enriched = await enrichYouTubePublishedDates(tabId, merged, options);
  options.onProgress?.({ phase: "calculating" });
  const analysis = finalizeContentAnalysis(enriched.videos, {
    limit,
    excludePinned: true,
    contentType: target.contentType
  });
  analysis.rss_date_enrichment = enriched.diagnostics;
  return analysis;
}

export async function cancelRecentContent(tabId) {
  return executePageFunction(tabId, abortPageDetailRequests);
}
