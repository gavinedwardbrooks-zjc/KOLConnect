import {
  CONTENT_DETAIL_CONCURRENCY,
  CONTENT_DETAIL_DELAY_MS,
  finalizeContentAnalysis,
  mapWithConcurrency
} from "../core/content_analysis.js";
import { parseHumanCount } from "../core/normalize.js";
import {
  abortPageDetailRequests,
  executePageFunction,
  executeProfileCollector,
  hostMatches,
  selectBio
} from "./common.js";

export function matches(url) {
  return hostMatches(url, "instagram.com");
}

function collectInstagramPage() {
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
  const text = (selector) => clean(document.querySelector(selector)?.textContent);
  const meta = (selector) => clean(document.querySelector(selector)?.content);
  const current = new URL(location.href);
  const handle = current.pathname.split("/").filter(Boolean)[0] || "";
  const reserved = new Set(["accounts", "direct", "explore", "p", "reel", "reels", "stories"]);
  if (!handle || reserved.has(handle.toLowerCase())) {
    return {
      platform: "Instagram",
      analysis_url: current.href,
      supported: false,
      fields: {},
      searched_sources: ["structured_data", "page_dom", "meta", "url"],
      errors: ["The current page is not an Instagram creator profile."]
    };
  }

  const states = [window._sharedData, window.__initialData].filter((value) => value && typeof value === "object");
  for (const script of document.querySelectorAll('script[type="application/ld+json"], script[type="application/json"]')) {
    const content = script.textContent || "";
    if (!content || content.length > 2_000_000) continue;
    try { states.push(JSON.parse(content)); } catch (_) {}
  }

  let profile = null;
  for (const root of states) {
    const queue = [root];
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < 3500 && !profile) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      visited += 1;
      const user = node.user || node.owner || node;
      const username = clean(user.username, 128).replace(/^@/, "");
      if (username && username.toLowerCase() === handle.toLowerCase()) {
        profile = {
          creator_name: clean(user.full_name || user.name, 256),
          followers: user.follower_count ?? user.edge_followed_by?.count ?? "",
          bio: multiline(user.biography || user.description)
        };
        break;
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object") queue.push(child);
      }
    }
    if (profile) break;
  }

  const metaTitle = meta('meta[property="og:title"]');
  const metaDescription = meta('meta[property="og:description"]') || meta('meta[name="description"]');
  const metaName = metaTitle.match(/^(.+?)\s*\(@[^)]+\)/)?.[1] || "";
  const metaFollowers = metaDescription.match(/([\d.,]+\s*[KMB]?)\s+Followers/i)?.[1] || "";
  const domName = text("header h1") || text("header h2");
  const domFollowerNode = document.querySelector('header a[href$="/followers/"] span[title], header a[href*="/followers/"] span');
  const domFollowers = clean(domFollowerNode?.getAttribute("title") || domFollowerNode?.textContent, 64);
  const explicitBioNodes = [
    ...document.querySelectorAll(
      'header [data-testid="user-bio"], header [data-testid*="bio" i], header section span[dir="auto"]'
    )
  ];
  const domBio = explicitBioNodes
    .map((node) => multiline(node.innerText || node.textContent))
    .filter(Boolean)
    .join("\n");
  const creatorName = profile?.creator_name || domName || metaName;
  const followers = (profile?.followers ?? "") || domFollowers || metaFollowers;

  return {
    platform: "Instagram",
    analysis_url: current.href,
    supported: true,
    fields: {
      profile_url: field(`https://www.instagram.com/${handle}/`, "url", "high", ""),
      username: field(`@${handle}`, "url", "high", ""),
      creator_name: field(creatorName, profile?.creator_name ? "structured_data" : domName ? "page_dom" : "meta", profile?.creator_name || domName ? "high" : "medium", "Creator name was not exposed by the current public page."),
      followers: field(followers, profile?.followers !== undefined && profile?.followers !== "" ? "structured_data" : domFollowers ? "page_dom" : "meta", "high", "Follower count was not exposed by the current public page."),
      bio: field(null, "", "missing", "Creator bio was not exposed by the current public page.")
    },
    bio_candidates: [
      { source: "structured_data", value: profile?.bio || "" },
      { source: "profile_dom", value: domBio },
      { source: "meta", value: metaDescription }
    ],
    searched_sources: ["structured_data", "page_dom", "meta", "url"],
    errors: []
  };
}

export async function collectProfile(tabId) {
  const result = await executeProfileCollector(tabId, collectInstagramPage);
  result.fields ||= {};
  result.fields.bio = selectBio(result.bio_candidates, {
    platform: "instagram",
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

function discoverInstagramReels() {
  const clean = (value, limit = 2000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  const byId = new Map();
  const add = (raw) => {
    const videoUrl = clean(raw.video_url);
    const videoId = clean(raw.video_id || videoUrl.match(/\/reel\/([^/?#]+)/)?.[1], 128);
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
      views_source: raw.views != null ? raw.views_source || raw.source : previous.views_source || "",
      likes_source: raw.likes != null ? raw.likes_source || raw.source : previous.likes_source || "",
      comments_source: raw.comments != null ? raw.comments_source || raw.source : previous.comments_source || "",
      published_source: raw.published_at != null
        ? raw.published_source || raw.source
        : previous.published_source || "",
      card_view_candidates: [
        ...(previous.card_view_candidates || []),
        ...(raw.card_view_candidates || [])
      ].slice(0, 20),
      card_view_missing_reason: raw.card_view_missing_reason
        || previous.card_view_missing_reason
        || "",
      is_pinned: Boolean(raw.is_pinned || previous.is_pinned)
    });
  };

  const states = [window._sharedData, window.__initialData].filter((value) => value && typeof value === "object");
  for (const script of document.querySelectorAll('script[type="application/ld+json"], script[type="application/json"]')) {
    const content = script.textContent || "";
    if (!content || content.length > 3_000_000) continue;
    try { states.push(JSON.parse(content)); } catch (_) {}
  }
  for (const root of states) {
    const queue = [root];
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < 14000) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      visited += 1;
      const shortcode = node.shortcode || node.code;
      const isVideo = node.is_video || node.media_type === 2 || node.product_type === "clips";
      if (shortcode && isVideo) {
        add({
          video_id: shortcode,
          video_url: `https://www.instagram.com/reel/${shortcode}/`,
          title: clean(
            node.caption?.text
            || node.edge_media_to_caption?.edges?.[0]?.node?.text
            || node.accessibility_caption
          ) || null,
          views: node.video_view_count ?? node.play_count ?? node.view_count ?? null,
          likes: node.like_count ?? node.edge_media_preview_like?.count ?? node.edge_liked_by?.count ?? null,
          comments: node.comment_count ?? node.edge_media_to_comment?.count ?? node.edge_media_to_parent_comment?.count ?? null,
          published_at: node.taken_at_timestamp ?? node.taken_at ?? null,
          is_pinned: Boolean(node.is_pinned || node.pinned_for_users?.length || node.timeline_pinned_user_ids?.length),
          source: "structured_data"
        });
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object") queue.push(child);
      }
    }
  }

  for (const anchor of document.querySelectorAll('a[href*="/reel/"]')) {
    const match = anchor.href.match(/\/reel\/([^/?#]+)/);
    if (!match) continue;
    let card = anchor;
    let parent = anchor.parentElement;
    for (let depth = 0; parent && depth < 5; depth += 1, parent = parent.parentElement) {
      const reelLinks = parent.querySelectorAll?.('a[href*="/reel/"]') || [];
      if (reelLinks.length !== 1) break;
      card = parent;
    }
    const pinElement = card.querySelector(
      '[aria-label*="pinned" i], [aria-label*="fixado" i], [aria-label*="置顶"], svg[aria-label*="pinned" i]'
    );
    const candidates = [];
    const candidateKeys = new Set();
    const addCandidate = (value, source) => {
      const text = clean(value, 160);
      const key = `${source}:${text}`;
      if (!text || candidateKeys.has(key)) return;
      candidateKeys.add(key);
      candidates.push({ text, source });
    };
    const explicitSelectors = [
      '[aria-label*="views" i]',
      '[aria-label*="plays" i]',
      '[aria-label*="visualiza" i]',
      '[aria-label*="reproducciones" i]',
      '[aria-label*="播放"]',
      '[data-testid*="view-count" i]',
      '[data-testid*="play-count" i]'
    ];
    for (const node of card.querySelectorAll(explicitSelectors.join(","))) {
      addCandidate(node.getAttribute("aria-label"), "reel_card_aria");
      addCandidate(node.textContent, "reel_card_dom");
    }
    for (const icon of card.querySelectorAll(
      'svg[aria-label*="play" i], svg[aria-label*="view" i], svg[aria-label*="visualiza" i], svg[aria-label*="reproducciones" i]'
    )) {
      addCandidate(icon.getAttribute("aria-label"), "reel_card_icon");
      addCandidate(icon.parentElement?.textContent, "reel_card_icon_adjacent");
      addCandidate(icon.parentElement?.parentElement?.textContent, "reel_card_icon_adjacent");
    }
    const hasVisibleNumericOverlay = candidates.length === 0
      && Boolean(card.querySelector("svg"))
      && /\d/.test(clean(card.innerText || card.textContent, 300));
    add({
      video_id: match[1],
      video_url: anchor.href,
      title: clean(anchor.getAttribute("aria-label") || anchor.querySelector("img")?.alt) || null,
      views: null,
      likes: null,
      comments: null,
      published_at: null,
      card_view_candidates: candidates,
      card_view_missing_reason: hasVisibleNumericOverlay
        ? "reel_card_selector_failed"
        : "reel_card_view_not_exposed",
      is_pinned: Boolean(pinElement),
      source: "page_dom"
    });
  }

  return [...byId.values()].slice(0, 60);
}

export function bindInstagramCardViews(items = []) {
  return items.map((item) => {
    if (item.views != null) return item;
    for (const candidate of item.card_view_candidates || []) {
      const text = String(candidate?.text || "").trim();
      const labeled = text.match(
        /([\d.,]+\s*(?:K|M|B|mil|mi|万)?)\s*(?:views?|plays?|visualiza(?:ç|c)[õo]es?|reproducciones?|播放)/i
      );
      const adjacent = /icon_adjacent/.test(candidate?.source || "")
        ? text.match(/^([\d.,]+\s*(?:K|M|B|mil|mi|万)?)$/i)
        : null;
      const rawValue = labeled?.[1] || adjacent?.[1] || "";
      const parsed = parseHumanCount(rawValue);
      if (parsed == null) continue;
      return {
        ...item,
        views: parsed,
        views_source: candidate.source || "reel_card_dom",
        views_confidence: "medium",
        card_view_missing_reason: ""
      };
    }
    return item;
  });
}

async function fetchInstagramReelDetail(videoUrl) {
  const clean = (value, limit = 3000) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  const videoId = String(videoUrl).match(/\/reel\/([^/?#]+)/)?.[1] || "";
  const registry = globalThis.__KOLCONNECT_DETAIL_CONTROLLERS__
    ||= new Set();
  const controller = new AbortController();
  registry.add(controller);
  const emptyResult = (reason) => ({
    video_id: videoId,
    views: null,
    likes: null,
    comments: null,
    published_at: null,
    views_missing_reason: reason,
    likes_missing_reason: reason,
    comments_missing_reason: reason,
    published_missing_reason: reason
  });
  const extractObject = (text, startIndex = 0) => {
    const start = text.indexOf("{", startIndex);
    if (start < 0) return null;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < text.length; index += 1) {
      const char = text[index];
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
          try { return JSON.parse(text.slice(start, index + 1)); } catch (_) { return null; }
        }
      }
    }
    return null;
  };
  const valueFromInteraction = (value, actionName) => {
    for (const item of Array.isArray(value) ? value : [value]) {
      const action = clean(
        item?.interactionType?.["@type"]
        || item?.interactionType
        || item?.["@type"]
      );
      if (action.toLowerCase().includes(actionName.toLowerCase())) {
        return item?.userInteractionCount ?? item?.interactionCount ?? null;
      }
    }
    return null;
  };
  const inspectMetrics = (root, source) => {
    const result = {
      title: null,
      views: null,
      likes: null,
      comments: null,
      published_at: null,
      views_source: "",
      likes_source: "",
      comments_source: "",
      published_source: ""
    };
    const queue = [{ node: root, depth: 0 }];
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < 6000) {
      const { node, depth } = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node) || depth > 18) continue;
      seen.add(node);
      visited += 1;
      result.title ||= clean(
        node.caption?.text
        || node.edge_media_to_caption?.edges?.[0]?.node?.text
        || node.accessibility_caption
        || node.caption
        || node.name
      ) || null;
      if (result.views == null) {
        result.views = node.video_view_count
          ?? node.play_count
          ?? node.view_count
          ?? node.playCount
          ?? node.videoViewCount
          ?? valueFromInteraction(node.interactionStatistic, "WatchAction");
        if (result.views != null) result.views_source = source;
      }
      if (result.likes == null) {
        result.likes = node.like_count
          ?? node.edge_media_preview_like?.count
          ?? node.edge_liked_by?.count
          ?? valueFromInteraction(node.interactionStatistic, "LikeAction");
        if (result.likes != null) result.likes_source = source;
      }
      if (result.comments == null) {
        result.comments = node.comment_count
          ?? node.edge_media_to_comment?.count
          ?? node.edge_media_to_parent_comment?.count
          ?? valueFromInteraction(node.interactionStatistic, "CommentAction");
        if (result.comments != null) result.comments_source = source;
      }
      if (result.published_at == null) {
        result.published_at = node.taken_at
          ?? node.taken_at_timestamp
          ?? node.datePublished
          ?? node.uploadDate
          ?? null;
        if (result.published_at != null) result.published_source = source;
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object") queue.push({ node: child, depth: depth + 1 });
      }
    }
    return result;
  };
  const mergeMetrics = (target, incoming) => {
    for (const field of ["title", "views", "likes", "comments", "published_at"]) {
      if (target[field] == null && incoming[field] != null) target[field] = incoming[field];
    }
    for (const field of ["views_source", "likes_source", "comments_source", "published_source"]) {
      if (!target[field] && incoming[field]) target[field] = incoming[field];
    }
  };
  try {
    const response = await fetch(videoUrl, {
      credentials: "include",
      redirect: "follow",
      signal: controller.signal
    });
    if (response.status === 429) return emptyResult("reel_detail_rate_limited");
    if (!response.ok) return emptyResult("reel_detail_parse_failed");
    const html = await response.text();
    if (/\/accounts\/login|challenge/i.test(response.url) || /login to continue|log in to instagram/i.test(html.slice(0, 30000))) {
      return emptyResult("reel_detail_login_required");
    }
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const states = [];
    for (const script of parsed.querySelectorAll("script")) {
      const content = script.textContent || "";
      if (!content || content.length > 3_000_000) continue;
      try {
        states.push(JSON.parse(content));
        continue;
      } catch (_) {}
      if (content.includes("__additionalDataLoaded")) {
        const commaIndex = content.indexOf(",");
        const value = extractObject(content, commaIndex >= 0 ? commaIndex : 0);
        if (value) states.push(value);
      } else if (content.includes('"__bbox"') || content.trim().startsWith("{")) {
        const value = extractObject(content);
        if (value) states.push(value);
      }
    }
    const metrics = {
      title: null,
      views: null,
      likes: null,
      comments: null,
      published_at: null,
      views_source: "",
      likes_source: "",
      comments_source: "",
      published_source: ""
    };
    for (const root of states) {
      const queue = [{ node: root, depth: 0 }];
      const seen = new WeakSet();
      let visited = 0;
      while (queue.length && visited < 14000) {
        const { node, depth } = queue.shift();
        if (!node || typeof node !== "object" || seen.has(node) || depth > 20) continue;
        seen.add(node);
        visited += 1;
        const shortcode = String(node.shortcode || node.code || "");
        const nodeUrl = clean(node.url || node.contentUrl || node.mainEntityOfPage);
        const isVideoObject = /VideoObject/i.test(clean(node["@type"]));
        if (shortcode === videoId || nodeUrl.includes(`/reel/${videoId}`) || isVideoObject) {
          mergeMetrics(metrics, inspectMetrics(node, "reel_detail_structured_data"));
        }
        for (const child of Array.isArray(node) ? node : Object.values(node)) {
          if (child && typeof child === "object") queue.push({ node: child, depth: depth + 1 });
        }
      }
    }

    const description = clean(
      parsed.querySelector('meta[property="og:description"]')?.content
      || parsed.querySelector('meta[name="description"]')?.content
    );
    const labeledCount = (labels) => {
      const expression = new RegExp(
        `([\\d.,]+\\s*(?:K|M|B|mil|mi|万)?)\\s*(?:${labels})`,
        "i"
      );
      return description.match(expression)?.[1] || null;
    };
    if (metrics.views == null) {
      metrics.views = labeledCount("views?|plays?|visualiza(?:ç|c)[õo]es?|reproducciones?|播放");
      if (metrics.views != null) metrics.views_source = "reel_detail_meta";
    }
    if (metrics.likes == null) {
      metrics.likes = labeledCount("likes?|curtidas?|me gusta");
      if (metrics.likes != null) metrics.likes_source = "reel_detail_meta";
    }
    if (metrics.comments == null) {
      metrics.comments = labeledCount("comments?|comentários?|comentarios?");
      if (metrics.comments != null) metrics.comments_source = "reel_detail_meta";
    }
    if (metrics.published_at == null) {
      const timeValue = parsed.querySelector("time[datetime]")?.getAttribute("datetime")
        || parsed.querySelector('meta[property="article:published_time"]')?.content
        || parsed.querySelector('meta[itemprop="datePublished"]')?.content
        || parsed.querySelector('meta[itemprop="uploadDate"]')?.content;
      if (timeValue) {
        metrics.published_at = timeValue;
        metrics.published_source = "reel_detail_dom_meta";
      }
    }
    const parsedAnything = states.length > 0
      || metrics.views != null
      || metrics.likes != null
      || metrics.comments != null
      || metrics.published_at != null;
    return {
      video_id: videoId,
      ...metrics,
      views_missing_reason: metrics.views == null
        ? parsedAnything ? "reel_detail_view_not_exposed" : "reel_detail_parse_failed"
        : "",
      likes_missing_reason: metrics.likes == null
        ? parsedAnything ? "reel_likes_not_public" : "reel_detail_parse_failed"
        : "",
      comments_missing_reason: metrics.comments == null
        ? parsedAnything ? "reel_comments_not_public" : "reel_detail_parse_failed"
        : "",
      published_missing_reason: metrics.published_at == null
        ? parsedAnything ? "reel_publish_time_not_exposed" : "reel_detail_parse_failed"
        : ""
    };
  } catch (error) {
    if (error?.name === "AbortError") return emptyResult("reel_detail_parse_failed");
    return emptyResult("reel_detail_parse_failed");
  } finally {
    registry.delete(controller);
  }
}

function mergeInstagramDetail(item, detail) {
  const confidence = (source) => {
    if (!source) return "missing";
    return /structured_data/.test(source) ? "high" : "medium";
  };
  const views = item.views ?? detail?.views ?? null;
  const likes = item.likes ?? detail?.likes ?? null;
  const comments = item.comments ?? detail?.comments ?? null;
  const publishedAt = item.published_at ?? detail?.published_at ?? null;
  const viewsSource = item.views != null
    ? item.views_source || item.source || ""
    : detail?.views != null ? detail.views_source || "" : "";
  const likesSource = item.likes != null
    ? item.likes_source || item.source || ""
    : detail?.likes != null ? detail.likes_source || "" : "";
  const commentsSource = item.comments != null
    ? item.comments_source || item.source || ""
    : detail?.comments != null ? detail.comments_source || "" : "";
  const publishedSource = item.published_at != null
    ? item.published_source || item.source || ""
    : detail?.published_at != null ? detail.published_source || "" : "";
  const viewsMissingReason = views == null
    ? item.card_view_missing_reason === "reel_card_selector_failed"
      ? item.card_view_missing_reason
      : detail?.views_missing_reason
        || item.card_view_missing_reason
        || "reel_detail_view_not_exposed"
    : "";
  return {
    ...item,
    title: detail?.title || item.title,
    views,
    likes,
    comments,
    published_at: publishedAt,
    views_source: viewsSource,
    likes_source: likesSource,
    comments_source: commentsSource,
    published_source: publishedSource,
    views_confidence: confidence(viewsSource),
    likes_confidence: confidence(likesSource),
    comments_confidence: confidence(commentsSource),
    published_confidence: confidence(publishedSource),
    views_missing_reason: viewsMissingReason,
    likes_missing_reason: likes == null
      ? detail?.likes_missing_reason || "reel_likes_not_public"
      : "",
    comments_missing_reason: comments == null
      ? detail?.comments_missing_reason || "reel_comments_not_public"
      : "",
    published_missing_reason: publishedAt == null
      ? detail?.published_missing_reason || "reel_publish_time_not_exposed"
      : ""
  };
}

export async function collectRecentContent(tabId, options = {}) {
  const limit = Math.max(1, Math.min(30, Number(options.limit) || 30));
  options.onProgress?.({ phase: "discovering" });
  const rawDiscovered = await executePageFunction(tabId, discoverInstagramReels);
  const discovered = bindInstagramCardViews(rawDiscovered);
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
        return mergeInstagramDetail(item, null);
      }
      const detail = await executePageFunction(tabId, fetchInstagramReelDetail, [item.video_url]);
      if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      return mergeInstagramDetail(item, detail);
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
    contentType: "reel"
  });
}

export async function cancelRecentContent(tabId) {
  return executePageFunction(tabId, abortPageDetailRequests);
}
