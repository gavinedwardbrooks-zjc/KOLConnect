import {
  CONTENT_DETAIL_CONCURRENCY,
  CONTENT_DETAIL_DELAY_MS,
  finalizeContentAnalysis,
  mapWithConcurrency
} from "../core/content_analysis.js";
import {
  abortPageDetailRequests,
  executePageFunction,
  executeProfileCollector,
  hostMatches,
  selectBio
} from "./common.js";

export function matches(url) {
  return hostMatches(url, "tiktok.com");
}

function collectTikTokPage() {
  const clean = (value, limit = 3000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
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
  const current = new URL(location.href);
  const handle = current.pathname.match(/^\/@([^/?#]+)/)?.[1] || "";
  const missing = "Creator profile data was not exposed by the current public page.";
  if (!handle) {
    return {
      platform: "TikTok",
      analysis_url: current.href,
      supported: false,
      fields: {},
      searched_sources: ["page_state", "page_dom", "url"],
      errors: ["The current page is not a TikTok creator profile."]
    };
  }

  const states = [];
  for (const state of [window.__UNIVERSAL_DATA_FOR_REHYDRATION__, window.SIGI_STATE]) {
    if (state && typeof state === "object") states.push(state);
  }
  for (const id of ["__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"]) {
    const text = document.getElementById(id)?.textContent;
    if (!text || text.length > 3_000_000) continue;
    try { states.push(JSON.parse(text)); } catch (_) {}
  }

  let profile = null;
  const inspect = (root) => {
    const queue = [root];
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < 4000 && !profile) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      visited += 1;
      const user = node.user || node.userInfo?.user || node;
      const username = clean(user.uniqueId || user.unique_id || user.username, 128).replace(/^@/, "");
      if (username && username.toLowerCase() === handle.toLowerCase()) {
        const stats = node.stats || node.userInfo?.stats || user.stats || {};
        profile = {
          username,
          creator_name: clean(user.nickname || user.fullName, 256),
          followers: stats.followerCount ?? stats.follower_count ?? user.followerCount ?? "",
          bio: multiline(user.signature || user.bio)
        };
        break;
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object") queue.push(child);
      }
    }
  };
  states.forEach(inspect);

  const domName = clean(document.querySelector('[data-e2e="user-title"], [data-e2e="user-subtitle"]')?.textContent, 256);
  const domFollowers = clean(document.querySelector('[data-e2e="followers-count"]')?.textContent, 64);
  const domBioNode = document.querySelector(
    '[data-e2e="user-bio"], [data-e2e="user-bio"] span, h2[data-e2e="user-bio"]'
  );
  const domBio = multiline(domBioNode?.innerText || domBioNode?.textContent);
  const metaBio = multiline(
    document.querySelector('meta[property="og:description"]')?.content
      || document.querySelector('meta[name="description"]')?.content
  );
  const creatorName = profile?.creator_name || domName;
  const followers = (profile?.followers ?? "") || domFollowers;
  return {
    platform: "TikTok",
    analysis_url: current.href,
    supported: true,
    fields: {
      profile_url: field(`https://www.tiktok.com/@${handle}`, "url", "high", missing),
      username: field(`@${handle}`, "url", "high", missing),
      creator_name: field(creatorName, profile?.creator_name ? "page_state" : "page_dom", "high", "Creator name was not exposed by the current public page."),
      followers: field(followers, profile?.followers !== undefined && profile?.followers !== "" ? "page_state" : "page_dom", "high", "Follower count was not exposed by the current public page."),
      bio: field(null, "", "missing", "Creator bio was not exposed by the current public page.")
    },
    bio_candidates: [
      { source: "structured_data", value: profile?.bio || "" },
      { source: "profile_dom", value: domBio },
      { source: "meta", value: metaBio }
    ],
    searched_sources: ["page_state", "page_dom", "url"],
    errors: []
  };
}

export async function collectProfile(tabId) {
  const result = await executeProfileCollector(tabId, collectTikTokPage);
  result.fields ||= {};
  result.fields.bio = selectBio(result.bio_candidates, {
    platform: "tiktok",
    username: result.fields.username?.value,
    creatorName: result.fields.creator_name?.value
  });
  delete result.bio_candidates;
  return result;
}

export function getDiagnostics(result) {
  return {
    searched_sources: result?.searched_sources || [],
    errors: result?.errors || []
  };
}

function discoverTikTokContent() {
  const clean = (value, limit = 1000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  const current = new URL(location.href);
  const handle = current.pathname.match(/^\/@([^/?#]+)/)?.[1] || "";
  const byId = new Map();
  const add = (raw) => {
    const videoId = clean(raw.video_id || raw.id, 128);
    const videoUrl = clean(raw.video_url || (videoId && handle
      ? `https://www.tiktok.com/@${handle}/video/${videoId}`
      : ""));
    const key = videoId || videoUrl;
    if (!key) return;
    const previous = byId.get(key) || {};
    byId.set(key, {
      ...previous,
      ...raw,
      video_id: videoId || previous.video_id || "",
      video_url: videoUrl || previous.video_url || "",
      title: raw.title || previous.title || null,
      views: raw.views ?? previous.views ?? null,
      likes: raw.likes ?? previous.likes ?? null,
      comments: raw.comments ?? previous.comments ?? null,
      published_at: raw.published_at ?? previous.published_at ?? null,
      is_pinned: Boolean(raw.is_pinned || previous.is_pinned)
    });
  };

  const states = [];
  for (const state of [window.__UNIVERSAL_DATA_FOR_REHYDRATION__, window.SIGI_STATE]) {
    if (state && typeof state === "object") states.push(state);
  }
  for (const id of ["__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"]) {
    const text = document.getElementById(id)?.textContent;
    if (!text || text.length > 3_000_000) continue;
    try { states.push(JSON.parse(text)); } catch (_) {}
  }

  for (const root of states) {
    const queue = [root];
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < 12000) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      visited += 1;
      const videoId = node.id || node.aweme_id || node.itemId;
      const stats = node.stats || node.statistics || {};
      if (videoId && (
        node.video
        || node.desc !== undefined
        || stats.playCount !== undefined
        || stats.play_count !== undefined
      )) {
        add({
          video_id: videoId,
          video_url: node.shareInfo?.shareUrl || node.share_url || "",
          title: clean(node.desc || node.title) || null,
          views: stats.playCount ?? stats.play_count ?? null,
          likes: stats.diggCount ?? stats.digg_count ?? null,
          comments: stats.commentCount ?? stats.comment_count ?? null,
          published_at: node.createTime ?? node.create_time ?? null,
          is_pinned: Boolean(node.isPinned || node.is_pinned || node.pinned),
          source: "structured_data"
        });
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object") queue.push(child);
      }
    }
  }

  for (const anchor of document.querySelectorAll('a[href*="/video/"]')) {
    const match = anchor.href.match(/\/video\/(\d+)/);
    if (!match) continue;
    const card = anchor.closest('[data-e2e*="user-post"], article, div') || anchor;
    const pinText = clean(
      card.querySelector('[data-e2e*="pin" i], [aria-label*="pinned" i]')?.textContent
      || card.querySelector('[aria-label*="置顶"]')?.getAttribute("aria-label")
    );
    add({
      video_id: match[1],
      video_url: anchor.href,
      title: clean(anchor.getAttribute("aria-label") || anchor.title) || null,
      views: clean(card.querySelector('[data-e2e="video-views"], strong')?.textContent) || null,
      likes: null,
      comments: null,
      published_at: null,
      is_pinned: /pinned|置顶|fixado/i.test(pinText),
      source: "page_dom"
    });
  }

  return [...byId.values()].slice(0, 60);
}

async function fetchTikTokContentDetail(videoUrl) {
  const clean = (value, limit = 2000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  const videoId = String(videoUrl).match(/\/video\/(\d+)/)?.[1] || "";
  const missing = "TikTok did not expose this field on the public video page.";
  const registry = globalThis.__KOLCONNECT_DETAIL_CONTROLLERS__
    ||= new Set();
  const controller = new AbortController();
  registry.add(controller);
  try {
    const response = await fetch(videoUrl, {
      credentials: "include",
      redirect: "follow",
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const html = await response.text();
    if (/\/login|verify|captcha/i.test(response.url) || /captcha|verify to continue/i.test(html.slice(0, 20000))) {
      return { video_id: videoId, detail_missing_reason: "TikTok required login or verification." };
    }
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const states = [];
    for (const id of ["__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"]) {
      const text = parsed.getElementById(id)?.textContent;
      if (!text || text.length > 3_000_000) continue;
      try { states.push(JSON.parse(text)); } catch (_) {}
    }
    let found = null;
    for (const root of states) {
      const queue = [root];
      const seen = new WeakSet();
      let visited = 0;
      while (queue.length && visited < 10000 && !found) {
        const node = queue.shift();
        if (!node || typeof node !== "object" || seen.has(node)) continue;
        seen.add(node);
        visited += 1;
        const id = String(node.id || node.aweme_id || node.itemId || "");
        if (id === videoId) {
          const stats = node.stats || node.statistics || {};
          found = {
            video_id: videoId,
            title: clean(node.desc || node.title) || null,
            views: stats.playCount ?? stats.play_count ?? null,
            likes: stats.diggCount ?? stats.digg_count ?? null,
            comments: stats.commentCount ?? stats.comment_count ?? null,
            published_at: node.createTime ?? node.create_time ?? null,
            detail_source: "detail_page_structured_data"
          };
          break;
        }
        for (const child of Array.isArray(node) ? node : Object.values(node)) {
          if (child && typeof child === "object") queue.push(child);
        }
      }
      if (found) break;
    }
    return found || { video_id: videoId, detail_missing_reason: missing };
  } catch (error) {
    return {
      video_id: videoId,
      detail_missing_reason: error?.message || missing
    };
  } finally {
    registry.delete(controller);
  }
}

function mergeTikTokDetail(item, detail) {
  const missing = detail?.detail_missing_reason || "TikTok did not expose this field on the public video page.";
  const confidence = (source) => /structured_data/.test(source || "") ? "high" : "medium";
  const viewsSource = item.views != null ? item.source : detail?.views != null ? detail.detail_source : "";
  const likesSource = item.likes != null ? item.source : detail?.likes != null ? detail.detail_source : "";
  const commentsSource = item.comments != null ? item.source : detail?.comments != null ? detail.detail_source : "";
  const publishedSource = item.published_at != null ? item.source : detail?.published_at != null ? detail.detail_source : "";
  return {
    ...item,
    title: detail?.title || item.title,
    views: item.views ?? detail?.views ?? null,
    likes: item.likes ?? detail?.likes ?? null,
    comments: item.comments ?? detail?.comments ?? null,
    published_at: item.published_at ?? detail?.published_at ?? null,
    views_source: viewsSource,
    likes_source: likesSource,
    comments_source: commentsSource,
    published_source: publishedSource,
    views_confidence: confidence(viewsSource),
    likes_confidence: confidence(likesSource),
    comments_confidence: confidence(commentsSource),
    published_confidence: confidence(publishedSource),
    views_missing_reason: item.views == null && detail?.views == null ? missing : "",
    likes_missing_reason: item.likes == null && detail?.likes == null ? missing : "",
    comments_missing_reason: item.comments == null && detail?.comments == null ? missing : "",
    published_missing_reason: item.published_at == null && detail?.published_at == null ? missing : ""
  };
}

export async function collectRecentContent(tabId, options = {}) {
  const limit = Math.max(1, Math.min(30, Number(options.limit) || 30));
  options.onProgress?.({ phase: "discovering" });
  const discovered = await executePageFunction(tabId, discoverTikTokContent);
  const eligible = discovered.filter((item) => !options.excludePinned || !item.is_pinned).slice(0, limit);
  options.onProgress?.({
    phase: "discovered",
    discovered: discovered.length,
    excludedPinned: discovered.filter((item) => item.is_pinned).length
  });
  const completed = await mapWithConcurrency(
    eligible,
    async (item) => {
      if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      if (item.views != null && item.likes != null && item.comments != null && item.published_at != null) {
        return mergeTikTokDetail(item, null);
      }
      const detail = await executePageFunction(tabId, fetchTikTokContentDetail, [item.video_url]);
      if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      return mergeTikTokDetail(item, detail);
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
  options.onProgress?.({ phase: "calculating" });
  return finalizeContentAnalysis(merged, {
    limit,
    excludePinned: options.excludePinned !== false,
    contentType: "video"
  });
}

export async function cancelRecentContent(tabId) {
  return executePageFunction(tabId, abortPageDetailRequests);
}
