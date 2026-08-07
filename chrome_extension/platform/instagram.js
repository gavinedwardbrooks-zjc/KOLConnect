import {
  CONTENT_DETAIL_CONCURRENCY,
  CONTENT_DETAIL_DELAY_MS,
  finalizeContentAnalysis,
  mapWithConcurrency
} from "../core/content_analysis.js";
import { parseHumanCount } from "../core/normalize.js";
import {
  IG_APP_ID,
  INSTAGRAM_CLIPS_PAGE_SIZE,
  INSTAGRAM_MAX_REELS,
  INSTAGRAM_PAGE_DELAY_MAX_MS,
  INSTAGRAM_PAGE_DELAY_MIN_MS
} from "../constants.js";
import {
  abortPageDetailRequests,
  applyPublicProfileFields,
  executePageFunction,
  executeProfileCollector,
  hostMatches,
  selectBio
} from "./common.js";

export function matches(url) {
  return hostMatches(url, "instagram.com");
}

function instagramApiField(value, source, missingReason) {
  const normalized = String(value ?? "").trim();
  return {
    value: normalized || null,
    source: normalized ? source : "",
    confidence: normalized ? "high" : "missing",
    missing_reason: normalized ? "" : missingReason
  };
}

export function fetchInstagramWebProfilePage(appId) {
  const clean = (value, limit = 5000) => String(value ?? "").trim().slice(0, limit);
  const current = new URL(location.href);
  const username = current.pathname.split("/").filter(Boolean)[0] || "";
  const reserved = new Set(["accounts", "direct", "explore", "p", "reel", "reels", "stories"]);
  if (!username || reserved.has(username.toLowerCase())) {
    return Promise.resolve({
      ok: false,
      status: 0,
      reason: "instagram_profile_url_required"
    });
  }
  return fetch(`/api/v1/users/web_profile_info/?username=${encodeURIComponent(username)}`, {
    method: "GET",
    credentials: "include",
    headers: { "X-IG-App-ID": appId }
  }).then(async (response) => {
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        reason: `web_profile_info_http_${response.status}`
      };
    }
    let payload;
    try {
      payload = await response.json();
    } catch (_) {
      return {
        ok: false,
        status: response.status,
        reason: "web_profile_info_invalid_json"
      };
    }
    const user = payload?.data?.user || payload?.user;
    if (!user || typeof user !== "object") {
      return {
        ok: false,
        status: response.status,
        reason: "web_profile_info_user_missing"
      };
    }
    return {
      ok: true,
      status: response.status,
      requested_username: username,
      user: {
        id: clean(user.id, 128),
        username: clean(user.username, 128),
        full_name: clean(user.full_name, 256),
        biography: clean(user.biography),
        followers: user.edge_followed_by?.count ?? user.follower_count ?? null,
        followers_source: user.edge_followed_by?.count != null
          ? "web_profile_info.edge_followed_by.count"
          : user.follower_count != null ? "web_profile_info.follower_count" : "",
        is_private: Boolean(user.is_private),
        business_email: clean(user.business_email || user.public_email, 320),
        whatsapp: clean(user.whatsapp_number || user.whatsapp, 128),
        country: clean(user.country || user.country_code, 128),
        language: clean(user.language, 128)
      }
    };
  }).catch((error) => ({
    ok: false,
    status: 0,
    reason: "web_profile_info_network_error",
    error: clean(error?.message, 300)
  }));
}

export function fetchInstagramClipsPage(targetUserId, maxId, appId, pageSize) {
  const clean = (value, limit = 3000) => String(value ?? "").trim().slice(0, limit);
  const body = new URLSearchParams({
    target_user_id: String(targetUserId),
    page_size: String(pageSize)
  });
  if (maxId) body.set("max_id", String(maxId));
  let csrfToken = "";
  try {
    const csrfCookie = String(document.cookie || "")
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrftoken="));
    const encodedToken = csrfCookie ? csrfCookie.slice("csrftoken=".length) : "";
    try {
      csrfToken = decodeURIComponent(encodedToken);
    } catch (_) {
      csrfToken = encodedToken;
    }
  } catch (_) {}
  if (!csrfToken) {
    console.warn("[KOLConnect][Instagram] csrf_token_unavailable");
    return Promise.resolve({
      ok: false,
      status: 0,
      reason: "csrf_token_unavailable"
    });
  }
  return fetch("/api/v1/clips/user/", {
    method: "POST",
    credentials: "include",
    headers: {
      "X-IG-App-ID": appId,
      "X-CSRFToken": csrfToken,
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: body.toString()
  }).then(async (response) => {
    if (!response.ok) {
      let reason = `clips_user_http_${response.status}`;
      if (response.status === 403 && typeof response.clone === "function") {
        try {
          const errorText = await response.clone().text();
          let errorMessage = errorText.slice(0, 500);
          try {
            const errorPayload = JSON.parse(errorText);
            errorMessage = String(
              errorPayload?.message
              || errorPayload?.error?.message
              || errorPayload?.error
              || ""
            ).slice(0, 500);
          } catch (_) {}
          if (/csrf.*(?:missing|incorrect|invalid|failed)/i.test(errorMessage)) {
            reason = "csrf_rejected";
          }
        } catch (_) {}
      }
      return {
        ok: false,
        status: response.status,
        reason
      };
    }
    let payload;
    try {
      payload = await response.json();
    } catch (_) {
      return {
        ok: false,
        status: response.status,
        reason: "clips_user_invalid_json"
      };
    }
    const listCandidates = [
      payload?.items,
      payload?.clips,
      payload?.data?.items,
      payload?.data?.clips
    ];
    const items = listCandidates.find(Array.isArray);
    if (!items) {
      return {
        ok: false,
        status: response.status,
        reason: "clips_user_items_missing"
      };
    }
    const paging = payload?.paging_info || payload?.pagingInfo || payload?.data?.paging_info || {};
    const rawMoreAvailable = payload?.more_available ?? paging?.more_available;
    const moreAvailable = typeof rawMoreAvailable === "boolean"
      ? rawMoreAvailable
      : rawMoreAvailable === 1 ? true : rawMoreAvailable === 0 ? false : null;
    return {
      ok: true,
      status: response.status,
      items: items.map((item) => {
        const media = item?.media || item;
        return {
          id: clean(media?.id, 128),
          code: clean(media?.code || media?.shortcode, 128),
          play_count: media?.play_count ?? media?.video_view_count ?? null,
          like_count: media?.like_count ?? null,
          comment_count: media?.comment_count ?? null,
          caption: { text: clean(media?.caption?.text || media?.caption) },
          taken_at: media?.taken_at ?? media?.taken_at_timestamp ?? null,
          is_pinned: Boolean(media?.is_pinned),
          product_type: clean(media?.product_type, 64),
          user: { username: clean(media?.user?.username, 128) }
        };
      }),
      more_available: moreAvailable,
      max_id: clean(paging?.max_id ?? payload?.next_max_id ?? payload?.max_id, 512)
    };
  }).catch((error) => ({
    ok: false,
    status: 0,
    reason: "clips_user_network_error",
    error: clean(error?.message, 300)
  }));
}

export function mapInstagramProfileResponse(response = {}) {
  const user = response.user || {};
  const username = String(user.username || response.requested_username || "").trim().replace(/^@/, "");
  const biography = String(user.biography || "").trim();
  const result = {
    platform: "Instagram",
    analysis_url: username ? `https://www.instagram.com/${username}/` : "",
    supported: Boolean(username),
    instagram_user_id: String(user.id || "").trim(),
    is_private: Boolean(user.is_private),
    fields: {
      profile_url: instagramApiField(
        username ? `https://www.instagram.com/${username}/` : "",
        "web_profile_info",
        "Creator profile URL was not available."
      ),
      username: instagramApiField(username ? `@${username}` : "", "web_profile_info", "Creator username was not available."),
      creator_name: instagramApiField(
        username,
        "web_profile_info",
        "Creator name was not exposed by Instagram web_profile_info."
      ),
      followers: instagramApiField(
        user.followers,
        user.followers_source || "web_profile_info",
        "Follower count was not exposed by Instagram web_profile_info."
      ),
      bio: instagramApiField(null, "", "Creator bio was not exposed by Instagram web_profile_info.")
    },
    bio_candidates: [{ source: "structured_data", value: biography }],
    public_profile: {
      email_candidates: [
        { source: "structured_data", value: user.business_email || "" },
        { source: "structured_data", value: biography }
      ],
      whatsapp_candidates: [
        { source: "structured_data", value: user.whatsapp || "" },
        { source: "structured_data", value: biography }
      ],
      country_candidates: [{ source: "structured_data", value: user.country || "" }],
      language_candidates: [{ source: "structured_data", value: user.language || "" }]
    },
    searched_sources: ["web_profile_info"],
    errors: []
  };
  result.fields.bio = selectBio(result.bio_candidates, {
    platform: "instagram",
    username: result.fields.username.value,
    creatorName: result.fields.creator_name.value
  });
  applyPublicProfileFields(result);
  delete result.bio_candidates;
  return result;
}

function hasUsableFollowers(value) {
  if (value === null || value === undefined || String(value).trim() === "") return false;
  return parseHumanCount(value) != null;
}

export function mapInstagramMedia(raw = {}) {
  const media = raw?.media || raw;
  const videoId = String(media?.id ?? media?.code ?? "").trim();
  const code = String(media?.code || "").trim();
  const source = "clips_user_api";
  return {
    platform: "Instagram",
    content_type: "reel",
    video_id: videoId,
    video_url: code ? `https://www.instagram.com/reel/${code}/` : "",
    title: String(media?.caption?.text || media?.caption || "").trim() || null,
    views: media?.play_count ?? null,
    likes: media?.like_count ?? null,
    comments: media?.comment_count ?? null,
    published_at: media?.taken_at ?? null,
    is_pinned: Boolean(media?.is_pinned),
    product_type: String(media?.product_type || "").trim(),
    creator_username: String(media?.user?.username || "").trim(),
    views_source: media?.play_count == null ? "" : source,
    likes_source: media?.like_count == null ? "" : source,
    comments_source: media?.comment_count == null ? "" : source,
    published_source: media?.taken_at == null ? "" : source,
    views_confidence: media?.play_count == null ? "missing" : "high",
    likes_confidence: media?.like_count == null ? "missing" : "high",
    comments_confidence: media?.comment_count == null ? "missing" : "high",
    published_confidence: media?.taken_at == null ? "missing" : "high",
    views_missing_reason: media?.play_count == null ? "clips_api_play_count_not_exposed" : "",
    likes_missing_reason: media?.like_count == null ? "clips_api_like_count_not_exposed" : "",
    comments_missing_reason: media?.comment_count == null ? "clips_api_comment_count_not_exposed" : "",
    published_missing_reason: media?.taken_at == null ? "clips_api_taken_at_not_exposed" : ""
  };
}

export async function paginateInstagramClips({
  targetUserId,
  fetchPage,
  maxReels = INSTAGRAM_MAX_REELS,
  pageSize = INSTAGRAM_CLIPS_PAGE_SIZE,
  sleep = (delay) => new Promise((resolve) => setTimeout(resolve, delay)),
  random = Math.random,
  warn = console.warn
} = {}) {
  if (!targetUserId) throw new Error("instagram_user_id_missing");
  if (typeof fetchPage !== "function") throw new Error("instagram_clips_fetcher_missing");
  const unique = new Map();
  const cursors = new Set();
  let maxId = "";
  let pages = 0;
  let stopReason = "more_available_false";

  while (unique.size < maxReels) {
    const response = await fetchPage({ targetUserId, maxId, pageSize });
    pages += 1;
    if (!response?.ok) {
      const error = new Error(response?.reason || "clips_user_request_failed");
      error.status = Number(response?.status) || 0;
      throw error;
    }
    if (!Array.isArray(response.items)) throw new Error("clips_user_items_missing");
    for (const media of response.items) {
      const key = String(media?.id ?? media?.code ?? "").trim();
      if (!key || unique.has(key)) continue;
      unique.set(key, media);
      if (unique.size >= maxReels) break;
    }
    if (unique.size >= maxReels) {
      stopReason = "max_reels_reached";
      break;
    }
    if (response.more_available === false) {
      stopReason = "more_available_false";
      break;
    }
    const nextMaxId = String(response.max_id || "").trim();
    if (!nextMaxId) throw new Error("clips_user_cursor_missing");
    if (nextMaxId === maxId || cursors.has(nextMaxId)) {
      warn("[KOLConnect][Instagram] Repeated clips cursor; pagination stopped.");
      stopReason = "repeated_cursor";
      break;
    }
    cursors.add(nextMaxId);
    maxId = nextMaxId;
    const spread = INSTAGRAM_PAGE_DELAY_MAX_MS - INSTAGRAM_PAGE_DELAY_MIN_MS;
    await sleep(INSTAGRAM_PAGE_DELAY_MIN_MS + Math.floor(random() * (spread + 1)));
  }
  return {
    items: [...unique.values()].slice(0, maxReels),
    pages,
    stop_reason: stopReason
  };
}

export function collectInstagramPage() {
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
        const edgeFollowers = user.edge_followed_by?.count;
        const directFollowers = user.follower_count;
        profile = {
          creator_name: clean(user.full_name || user.name, 256),
          followers: edgeFollowers ?? directFollowers ?? "",
          followers_source: edgeFollowers != null
            ? "hydration.edge_followed_by.count"
            : directFollowers != null ? "hydration.follower_count" : "",
          bio: multiline(user.biography || user.description),
          email: clean(user.business_email || user.public_email, 320),
          whatsapp: clean(user.whatsapp_number || user.whatsapp, 128),
          country: clean(user.country || user.country_code, 128),
          language: clean(user.language || user.locale, 128)
        };
        break;
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object") queue.push(child);
      }
    }
    if (profile) break;
  }

  if (profile && (profile.followers === "" || profile.followers == null)) {
    for (const root of states) {
      const queue = [root];
      const seen = new WeakSet();
      let visited = 0;
      let foundFollowers = false;
      while (queue.length && visited < 3500 && !foundFollowers) {
        const node = queue.shift();
        if (!node || typeof node !== "object" || seen.has(node)) continue;
        seen.add(node);
        visited += 1;
        const user = node.user || node.owner || node;
        const username = clean(user.username, 128).replace(/^@/, "");
        if (username && username.toLowerCase() === handle.toLowerCase()) {
          const edgeFollowers = user.edge_followed_by?.count;
          const directFollowers = user.follower_count;
          if (edgeFollowers != null || directFollowers != null) {
            profile.followers = edgeFollowers ?? directFollowers;
            profile.followers_source = edgeFollowers != null
              ? "hydration.edge_followed_by.count"
              : "hydration.follower_count";
            foundFollowers = true;
            break;
          }
        }
        for (const child of Array.isArray(node) ? node : Object.values(node)) {
          if (child && typeof child === "object") queue.push(child);
        }
      }
      if (foundFollowers) break;
    }
  }

  const metaTitle = meta('meta[property="og:title"]');
  const metaDescription = meta('meta[property="og:description"]') || meta('meta[name="description"]');
  const metaName = metaTitle.match(/^(.+?)\s*\(@[^)]+\)/)?.[1] || "";
  const extractFollowerCount = (value, requireLabel = false) => {
    const raw = clean(value, 256);
    if (!raw) return "";
    const labeled = raw.match(
      /([\d.,]+\s*(?:K|M|B|mio|mil|mi|万|萬)?)\s*(?:位|名)?\s*(?:followers?|seguidores?|粉丝|粉絲)/i
    );
    if (labeled) return clean(labeled[1], 64);
    if (requireLabel) return "";
    return clean(raw.match(/[\d.,]+\s*(?:K|M|B|mio|mil|mi|万|萬)?/i)?.[0], 64);
  };
  const metaFollowers = extractFollowerCount(metaDescription, true);
  const domName = text("header h1") || text("header h2");
  const semanticFollowerNodes = [
    ...document.querySelectorAll([
      'header a[href*="/followers"]',
      'header [data-testid*="follower" i]',
      'header [aria-label*="followers" i]',
      'header [aria-label*="seguidores" i]',
      'header [aria-label*="粉丝"]',
      'header [aria-label*="粉絲"]'
    ].join(","))
  ];
  const structuralFollowerNodes = [
    ...document.querySelectorAll("header ul li, header section li")
  ];
  let domFollowers = "";
  for (const node of semanticFollowerNodes) {
    for (const value of [
      node.getAttribute?.("title"),
      node.getAttribute?.("aria-label"),
      node.textContent
    ]) {
      domFollowers = extractFollowerCount(value, false);
      if (domFollowers) break;
    }
    if (domFollowers) break;
  }
  if (!domFollowers) {
    for (const node of structuralFollowerNodes) {
      domFollowers = extractFollowerCount(
        node.getAttribute?.("aria-label") || node.textContent,
        true
      );
      if (domFollowers) break;
    }
  }
  const explicitBioSelector = [
    'header [data-testid="user-bio"]',
    'header [data-testid*="bio" i]',
    'header [itemprop="description"]',
    'header [aria-label*="biography" i]'
  ].join(",");
  const blockedBioAncestorSelector = [
    "a",
    "button",
    '[role="button"]',
    '[role="link"]',
    '[role="tab"]',
    '[role="tablist"]',
    '[role="navigation"]',
    "nav",
    "ul",
    "ol",
    "li",
    '[data-testid*="highlight" i]',
    '[data-testid*="story" i]',
    '[aria-label*="highlight" i]',
    '[aria-label*="story" i]'
  ].join(",");
  const bioTextNodes = [
    ...document.querySelectorAll(`${explicitBioSelector}, header section span[dir="auto"]`)
  ];
  const seenBioText = new Set();
  const domBio = bioTextNodes
    .filter((node) => {
      if (node.matches?.(explicitBioSelector) || node.closest?.(explicitBioSelector)) return true;
      if (!node.closest?.("header section")) return false;
      return !node.closest?.(blockedBioAncestorSelector);
    })
    .map((node) => multiline(node.innerText || node.textContent))
    .filter((value) => {
      if (!value || seenBioText.has(value)) return false;
      seenBioText.add(value);
      return true;
    })
    .join("\n");
  const creatorName = profile?.creator_name || domName || metaName;
  const hasFollowerValue = (value) => value !== null
    && value !== undefined
    && String(value).trim() !== "";
  const followers = hasFollowerValue(profile?.followers)
    ? profile.followers
    : hasFollowerValue(domFollowers) ? domFollowers : metaFollowers;
  const followersSource = hasFollowerValue(profile?.followers)
    ? profile.followers_source || "structured_data"
    : hasFollowerValue(domFollowers) ? "profile_dom" : metaFollowers ? "meta" : "";
  const contactLinks = [...document.querySelectorAll('header a[href^="mailto:"], header a[href*="wa.me/"], header a[href*="api.whatsapp.com/"]')]
    .map((node) => clean(node.href || node.textContent, 512));

  return {
    platform: "Instagram",
    analysis_url: current.href,
    supported: true,
    fields: {
      profile_url: field(`https://www.instagram.com/${handle}/`, "url", "high", ""),
      username: field(`@${handle}`, "url", "high", ""),
      creator_name: field(creatorName, profile?.creator_name ? "structured_data" : domName ? "page_dom" : "meta", profile?.creator_name || domName ? "high" : "medium", "Creator name was not exposed by the current public page."),
      followers: field(followers, followersSource, "high", "Follower count was not exposed by the current public page."),
      bio: field(null, "", "missing", "Creator bio was not exposed by the current public page.")
    },
    bio_candidates: [
      { source: "structured_data", value: profile?.bio || "" },
      { source: "profile_dom", value: domBio },
      { source: "meta", value: metaDescription }
    ],
    public_profile: {
      email_candidates: [
        { source: "structured_data", value: profile?.email || "" },
        ...contactLinks.map((value) => ({ source: "profile_dom", value })),
        { source: "profile_dom", value: domBio }
      ],
      whatsapp_candidates: [
        { source: "structured_data", value: profile?.whatsapp || "" },
        ...contactLinks.map((value) => ({ source: "profile_dom", value })),
        { source: "profile_dom", value: domBio }
      ],
      country_candidates: [{ source: "structured_data", value: profile?.country || "" }],
      language_candidates: [{ source: "structured_data", value: profile?.language || "" }]
    },
    searched_sources: ["structured_data", "page_dom", "meta", "url"],
    errors: []
  };
}

export async function collectProfile(tabId) {
  let apiResponse = null;
  try {
    apiResponse = await executePageFunction(tabId, fetchInstagramWebProfilePage, [IG_APP_ID]);
    if (apiResponse?.ok) {
      const apiResult = mapInstagramProfileResponse(apiResponse);
      if (!hasUsableFollowers(apiResult.fields.followers?.value)) {
        try {
          const fallbackResult = await executeProfileCollector(tabId, collectInstagramPage);
          const fallbackFollowers = fallbackResult?.fields?.followers;
          if (hasUsableFollowers(fallbackFollowers?.value)) {
            apiResult.fields.followers = fallbackFollowers;
            apiResult.searched_sources = [
              ...new Set([
                ...(apiResult.searched_sources || []),
                ...(fallbackResult.searched_sources || [])
              ])
            ];
            apiResult.followers_fallback_used = true;
          }
        } catch (error) {
          console.warn(
            "[KOLConnect][Instagram] Followers fallback failed; preserving API profile fields.",
            error?.message || error
          );
        }
      }
      return apiResult;
    }
    console.warn(
      "[KOLConnect][Instagram] web_profile_info unavailable; using hydration/DOM fallback.",
      apiResponse?.reason || "unknown_error"
    );
  } catch (error) {
    console.warn(
      "[KOLConnect][Instagram] web_profile_info failed; using hydration/DOM fallback.",
      error?.message || error
    );
  }
  const result = await executeProfileCollector(tabId, collectInstagramPage);
  result.fields ||= {};
  result.fields.bio = selectBio(result.bio_candidates, {
    platform: "instagram",
    username: result.fields.username?.value,
    creatorName: result.fields.creator_name?.value
  });
  applyPublicProfileFields(result);
  result.api_fallback_reason = apiResponse?.reason || "web_profile_info_unavailable";
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

async function collectInstagramLegacyContent(tabId, options = {}) {
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

function logUnavailableFallbacks(diagnostics) {
  console.warn("[KOLConnect][Instagram] feed fallback unavailable / not verified.");
  diagnostics.push({ source: "feed_api", status: "skipped", reason: "feed_fallback_not_verified" });
  console.warn("[KOLConnect][Instagram] GraphQL fallback unavailable: reliable doc_id was not exposed.");
  diagnostics.push({ source: "graphql", status: "skipped", reason: "graphql_doc_id_not_available" });
}

export const RECENT_CONTENT_LIMIT = INSTAGRAM_MAX_REELS;

export async function collectRecentContent(tabId, options = {}) {
  const limit = Math.max(1, Math.min(INSTAGRAM_MAX_REELS, Number(options.limit) || INSTAGRAM_MAX_REELS));
  const apiDiagnostics = [];
  options.onProgress?.({ phase: "discovering", source: "clips_user_api" });
  try {
    if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const profileResponse = await executePageFunction(tabId, fetchInstagramWebProfilePage, [IG_APP_ID]);
    if (!profileResponse?.ok) {
      const error = new Error(profileResponse?.reason || "web_profile_info_failed");
      error.status = Number(profileResponse?.status) || 0;
      throw error;
    }
    const targetUserId = String(profileResponse.user?.id || "").trim();
    const expectedUsername = String(
      profileResponse.user?.username || profileResponse.requested_username || ""
    ).trim().toLowerCase();
    const paginated = await paginateInstagramClips({
      targetUserId,
      maxReels: INSTAGRAM_MAX_REELS,
      pageSize: INSTAGRAM_CLIPS_PAGE_SIZE,
      sleep: typeof options.paginationSleep === "function" ? options.paginationSleep : undefined,
      fetchPage: async ({ targetUserId: userId, maxId, pageSize }) => {
        if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
        const response = await executePageFunction(tabId, fetchInstagramClipsPage, [
          userId,
          maxId,
          IG_APP_ID,
          pageSize
        ]);
        if (response?.status === 429) {
          console.warn("[KOLConnect][Instagram] clips/user rate limited; stopping API pagination.");
        }
        return response;
      }
    });
    if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const mapped = paginated.items
      .filter((media) => {
        const productType = String(media?.product_type || "").trim().toLowerCase();
        return !productType || productType === "clips" || productType === "reels";
      })
      .map(mapInstagramMedia);
    const usernameMismatches = mapped.filter((item) => (
      expectedUsername
      && item.creator_username
      && item.creator_username.toLowerCase() !== expectedUsername
    )).length;
    apiDiagnostics.push({
      source: "web_profile_info",
      status: "success",
      user_id_available: Boolean(targetUserId)
    });
    apiDiagnostics.push({
      source: "clips_user_api",
      status: "success",
      pages: paginated.pages,
      unique_reels: mapped.length,
      stop_reason: paginated.stop_reason,
      username_mismatches: usernameMismatches
    });
    options.onProgress?.({
      phase: "discovered",
      source: "clips_user_api",
      discovered: mapped.length,
      pages: paginated.pages,
      excludedPinned: 0
    });
    options.onProgress?.({ phase: "calculating" });
    const analysis = finalizeContentAnalysis(mapped, {
      limit,
      maximumCount: INSTAGRAM_MAX_REELS,
      excludePinned: false,
      contentType: "reel"
    });
    analysis.collector_mode = "instagram_internal_api";
    analysis.data_source = "clips_user_api";
    analysis.api_diagnostics = apiDiagnostics;
    return analysis;
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    const reason = error?.message || "instagram_internal_api_failed";
    console.warn("[KOLConnect][Instagram] clips/user API failed; entering fallback chain.", reason);
    apiDiagnostics.push({
      source: "clips_user_api",
      status: "failed",
      http_status: Number(error?.status) || 0,
      reason
    });
  }

  logUnavailableFallbacks(apiDiagnostics);
  const legacy = await collectInstagramLegacyContent(tabId, {
    ...options,
    limit: Math.min(limit, 30)
  });
  legacy.collector_mode = "legacy_fallback";
  legacy.data_source = "hydration_dom";
  legacy.api_diagnostics = [
    ...apiDiagnostics,
    { source: "hydration_dom", status: "success", returned: legacy.returned_count }
  ];
  return legacy;
}

export async function cancelRecentContent(tabId) {
  return executePageFunction(tabId, abortPageDetailRequests);
}
