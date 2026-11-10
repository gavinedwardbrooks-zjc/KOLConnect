const PLATFORM_HOSTS = Object.freeze({
  tiktok: new Set(["tiktok.com", "www.tiktok.com", "m.tiktok.com"]),
  instagram: new Set(["instagram.com", "www.instagram.com", "m.instagram.com"]),
  youtube: new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"])
});
export const INSTAGRAM_RECENT_CACHE_KEY = "instagram_publication_metric_cache_v1";
export const INSTAGRAM_RECENT_TRUSTED_SOURCES = Object.freeze(new Set([
  "clips_user_api", "structured_data", "reel_detail_structured_data"
]));
export const INSTAGRAM_PUBLISHED_TRUSTED_SOURCES = Object.freeze(new Set([
  "clips_user_api", "structured_data", "reel_detail_structured_data", "reel_detail_dom_exact"
]));

export function isTrustedInstagramRecentMetric(field) {
  return INSTAGRAM_RECENT_TRUSTED_SOURCES.has(String(field?.source || ""))
    && field?.confidence === "high"
    && Number.isSafeInteger(field.value)
    && field.value >= 0;
}

export function isTrustedInstagramPublishedAt(field) {
  const parsed = Date.parse(String(field?.value || ""));
  return INSTAGRAM_PUBLISHED_TRUSTED_SOURCES.has(String(field?.source || ""))
    && field?.confidence === "high"
    && Number.isFinite(parsed);
}

export function mergeInstagramRecentPublishedTimes(analysis, cache, now = Date.now()) {
  if (!analysis || !cache || typeof cache !== "object" || !Array.isArray(analysis.contents)) return analysis;
  let reused = 0;
  const contents = analysis.contents.map((item) => {
    if (item?.published_at?.value) return item;
    const videoId = String(item?.video_id || "").trim()
      || String(item?.video_url || "").match(/\/(?:reel|reels|p|tv)\/([A-Za-z0-9_-]+)/i)?.[1]
      || "";
    const cached = cache[videoId];
    if (!videoId || Number(cached?.expires_at || 0) <= now || !isTrustedInstagramPublishedAt(cached?.published_at)) {
      return item;
    }
    reused += 1;
    const value = new Date(cached.published_at.value).toISOString();
    return {
      ...item,
      published_at: {
        value,
        raw_text: value,
        is_estimated: false,
        source: cached.published_at.source,
        confidence: "high",
        missing_reason: ""
      }
    };
  });
  if (!reused) return analysis;
  const validPublished = contents.filter((item) => item?.published_at?.value).length;
  return {
    ...analysis,
    contents,
    valid_publish_time_count: validPublished,
    missing_counts: { ...(analysis.missing_counts || {}), published_at: contents.length - validPublished },
    instagram_published_time_cache: "exact_shortcode_match"
  };
}

export function mergeInstagramRecentMetrics(capture, identity, cache, now = Date.now()) {
  if (identity?.platform !== "Instagram" || !cache || typeof cache !== "object") return capture;
  const cached = cache[String(identity.video_id || "")];
  if (!cached || Number(cached.expires_at || 0) <= now) return capture;
  const merged = { ...capture, metrics: { ...(capture?.metrics || {}) } };
  let reused = 0;
  for (const name of ["views", "likes", "comments", "shares"]) {
    if (merged.metrics[name]?.value != null) continue;
    const field = cached.metrics?.[name];
    if (!isTrustedInstagramRecentMetric(field)) continue;
    merged.metrics[name] = { value: field.value, source: field.source, confidence: "high", missing_reason: "" };
    reused += 1;
  }
  if (!reused) return capture;
  const available = Object.values(merged.metrics).filter((field) => field?.value != null).length;
  merged.capture_status = available === 4 ? "success" : "partial";
  merged.safe_error_code = "";
  merged.diagnostic = {
    ...(merged.diagnostic || {}),
    stage: "metrics_collected",
    instagram_recent_cache: "exact_shortcode_match",
    fields_present: Object.fromEntries(Object.entries(merged.metrics).map(([name, field]) => [name, field?.value != null])),
  };
  return merged;
}

export function publicationIdentity(rawUrl) {
  let url;
  try { url = new URL(String(rawUrl || "")); } catch (_) { return null; }
  const host = url.hostname.toLowerCase();
  const parts = url.pathname.split("/").filter(Boolean);
  if (PLATFORM_HOSTS.tiktok.has(host)) {
    const match = url.pathname.match(/^\/@[A-Za-z0-9._-]+\/video\/(\d+)/);
    return match ? { platform: "TikTok", video_id: match[1] } : null;
  }
  if (PLATFORM_HOSTS.instagram.has(host)) {
    const match = url.pathname.match(/^\/(?:[A-Za-z0-9._]+\/)?(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/i);
    return match ? { platform: "Instagram", video_id: match[1] } : null;
  }
  if (PLATFORM_HOSTS.youtube.has(host)) {
    const videoId = host === "youtu.be" ? parts[0] : (parts[0] === "shorts" ? parts[1] : url.searchParams.get("v"));
    return /^[A-Za-z0-9_-]+$/.test(videoId || "") ? { platform: "YouTube", video_id: videoId } : null;
  }
  return null;
}

export function collectPublicationPage(target, root = globalThis, doc = globalThis.document) {
  const result = { views: null, likes: null, comments: null, shares: null };
  const evidence = {};
  const parseCount = (value) => {
    if (typeof value === "number") return Number.isSafeInteger(value) && value >= 0 ? value : null;
    const text = String(value ?? "").trim().replace(/\s+/g, "");
    const match = text.match(/^([0-9]+(?:[.,][0-9]+)*)(K|M|B|mil|mi|万|萬)?$/i);
    if (!match) return null;
    const suffix = (match[2] || "").toUpperCase();
    let numeric = match[1];
    if (suffix) {
      numeric = numeric.replace(",", ".");
      if (!/^\d+(?:\.\d+)?$/.test(numeric)) return null;
    } else if (/^\d{1,3}(?:[.,]\d{3})+$/.test(numeric)) {
      numeric = numeric.replace(/[.,]/g, "");
    } else if (!/^\d+$/.test(numeric)) return null;
    const multiplier = {
      K: 1_000, MIL: 1_000, M: 1_000_000, MI: 1_000_000,
      B: 1_000_000_000, "万": 10_000, "萬": 10_000
    }[suffix] || 1;
    const parsed = Number(numeric) * multiplier;
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
  };
  const set = (name, value, source, confidence = "high") => {
    if (result[name] !== null || value === null || value === undefined || value === "") return;
    const number = parseCount(value);
    if (number === null) return;
    result[name] = number;
    evidence[name] = { source, confidence, missing_reason: "" };
  };
  const inspect = (node, source, confidence = "high") => {
    if (!node || typeof node !== "object") return;
    const stats = node.stats || node.statistics || node.videoDetails || node.engagement || node;
    set("views", stats.playCount ?? stats.viewCount ?? stats.view_count ?? stats.videoViewCount
      ?? stats.video_view_count ?? stats.play_count, source, confidence);
    set("likes", stats.diggCount ?? stats.likeCount ?? stats.edge_media_preview_like?.count
      ?? stats.edge_liked_by?.count ?? stats.like_count, source, confidence);
    set("comments", stats.commentCount ?? stats.edge_media_to_comment?.count
      ?? stats.edge_media_to_parent_comment?.count ?? stats.comment_count, source, confidence);
    set("shares", stats.shareCount ?? stats.share_count, source, confidence);
  };
  const identityCandidates = (node) => {
    if (!node || typeof node !== "object") return [];
    return [...new Set([
      node.id, node.aweme_id, node.shortcode, node.code, node.videoId, node.video_id
    ].map((value) => String(value ?? "").trim()).filter(Boolean))];
  };
  const urlMatchesIdentity = (node) => {
    const nodeUrl = String(node?.url ?? node?.contentUrl ?? node?.mainEntityOfPage ?? "");
    if (target.platform !== "Instagram") return nodeUrl.includes(String(target.video_id));
    return new RegExp(
      `/(?:reel|reels|p|tv)/${String(target.video_id).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:/|$)`,
      "i"
    ).test(nodeUrl);
  };
  const inspectIdentityBoundSubtree = (rootNode, source, confidence = "high") => {
    const queue = [rootNode];
    const seen = new Set();
    let visited = 0;
    while (queue.length && visited < 6000) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node); visited += 1;
      const candidates = identityCandidates(node);
      if (node !== rootNode && candidates.length
          && !candidates.includes(String(target.video_id)) && !urlMatchesIdentity(node)) continue;
      inspect(node, source, confidence);
      for (const child of Object.values(node)) if (child && typeof child === "object") queue.push(child);
    }
  };
  let identityMatchCount = 0;
  let identityRejectedCount = 0;
  const findMatching = (value, source, confidence = "high") => {
    const queue = [value];
    const seen = new Set();
    let visited = 0;
    while (queue.length && visited < 20000) {
      const node = queue.shift();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node); visited += 1;
      const candidates = identityCandidates(node);
      const matched = candidates.includes(String(target.video_id)) || urlMatchesIdentity(node);
      if (matched) {
        identityMatchCount += 1;
        inspectIdentityBoundSubtree(node, source, confidence);
      } else if (candidates.length) {
        identityRejectedCount += 1;
      }
      for (const child of Object.values(node)) if (child && typeof child === "object") queue.push(child);
    }
  };
  let pageIdentityMismatch = false;
  let playbackState = "";
  if (target.platform === "YouTube") {
    playbackState = String(root.ytInitialPlayerResponse?.playabilityStatus?.status || "").toUpperCase();
    const details = root.ytInitialPlayerResponse?.videoDetails;
    const playerVideoId = String(details?.videoId || "");
    if (playerVideoId && playerVideoId !== String(target.video_id)) pageIdentityMismatch = true;
    if (playerVideoId === String(target.video_id)) {
      inspect(details, "ytInitialPlayerResponse.videoDetails");
      const textFrom = (value) => {
        if (value == null) return "";
        if (typeof value === "string" || typeof value === "number") return String(value).trim();
        return String(value.simpleText || value.content || value.text
          || value.runs?.map((item) => item.text).join("") || "").trim();
      };
      const countFrom = (value) => {
        const extract = (text) => String(text || "")
          .match(/(?:^|[^\d])([\d.,]+\s*(?:K|M|B|mil|mi|万|萬)?)(?=$|[^\d])/i)?.[1] || null;
        const direct = extract(textFrom(value));
        if (direct || !value || typeof value !== "object") return direct;
        const queue = [value];
        const seen = new Set();
        let visited = 0;
        while (queue.length && visited < 300) {
          const node = queue.shift();
          if (!node || typeof node !== "object" || seen.has(node)) continue;
          seen.add(node); visited += 1;
          for (const [key, child] of Object.entries(node)) {
            if (/^(?:title|text|simpleText|content|label|accessibilityText|countText)$/i.test(key)) {
              const found = extract(textFrom(child));
              if (found) return found;
            }
            if (child && typeof child === "object") queue.push(child);
          }
        }
        return null;
      };
      const queue = [root.ytInitialData].filter(Boolean);
      const seen = new Set();
      let visited = 0;
      while (queue.length && visited < 12000
          && (result.views === null || result.likes === null || result.comments === null)) {
        const node = queue.shift();
        if (!node || typeof node !== "object" || seen.has(node)) continue;
        seen.add(node); visited += 1;
        if (result.views === null && node.videoDescriptionHeaderRenderer) {
          set("views", countFrom(node.videoDescriptionHeaderRenderer.views),
            "ytInitialData.videoDescriptionHeaderRenderer.views");
        }
        if (result.likes === null && node.likeButtonViewModel) {
          set("likes", countFrom(node.likeButtonViewModel), "ytInitialData.likeButtonViewModel");
        }
        if (result.likes === null && node.toggleButtonRenderer) {
          const label = textFrom(node.toggleButtonRenderer.defaultText)
            || textFrom(node.toggleButtonRenderer.accessibilityData?.accessibilityData?.label);
          if (!/dislike/i.test(label) && /(?:\blikes?\b|赞|讚)/i.test(label)) {
            set("likes", countFrom(label), "ytInitialData.toggleButtonRenderer");
          }
        }
        if (result.comments === null && node.commentsHeaderRenderer) {
          set("comments", countFrom(node.commentsHeaderRenderer.countText)
            || countFrom(node.commentsHeaderRenderer), "ytInitialData.commentsHeaderRenderer");
        }
        for (const child of Object.values(node)) if (child && typeof child === "object") queue.push(child);
      }
    }
  } else if (target.platform === "TikTok") {
    findMatching(root.SIGI_STATE, "SIGI_STATE", "medium");
    findMatching(root.__UNIVERSAL_DATA_FOR_REHYDRATION__, "UNIVERSAL_DATA", "medium");
    for (const id of ["SIGI_STATE", "__UNIVERSAL_DATA_FOR_REHYDRATION__"]) {
      const text = String(doc?.getElementById?.(id)?.textContent || "");
      if (!text || text.length > 3_000_000 || !text.includes(String(target.video_id))) continue;
      try { findMatching(JSON.parse(text), id === "SIGI_STATE" ? "SIGI_STATE_SCRIPT" : "UNIVERSAL_DATA_SCRIPT", "medium"); }
      catch (_) {}
    }
  } else if (target.platform === "Instagram") {
    findMatching(root.__additionalDataLoaded, "instagram_page_state", "medium");
    const extractObject = (text, startIndex = 0) => {
      const start = text.indexOf("{", startIndex);
      if (start < 0) return null;
      let depth = 0, inString = false, escaped = false;
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
        else if (char === "}" && --depth === 0) {
          try { return JSON.parse(text.slice(start, index + 1)); } catch (_) { return null; }
        }
      }
      return null;
    };
    for (const script of Array.from(doc?.querySelectorAll?.("script") || []).slice(0, 250)) {
      const text = String(script.textContent || "");
      if (!text.includes(String(target.video_id)) || text.length > 3_000_000) continue;
      let state = null;
      try { state = JSON.parse(text); } catch (_) {
        const hint = text.includes("__additionalDataLoaded") ? text.indexOf(",") : 0;
        state = extractObject(text, Math.max(0, hint));
      }
      if (state) findMatching(state, "instagram_page_script", "medium");
    }
    const description = String(
      doc?.querySelector?.('meta[property="og:description"]')?.content
      || doc?.querySelector?.('meta[name="description"]')?.content
      || ""
    ).slice(0, 4000);
    const labeled = (labels) => description.match(new RegExp(
      `([\\d.,]+\\s*(?:K|M|B|万|萬)?)\\s*(?:${labels})`, "i"
    ))?.[1];
    set("views", labeled("views?|plays?|visualiza(?:ç|c)[õo]es?|reproducciones?|播放"), "instagram_meta_description", "medium");
    set("likes", labeled("likes?|curtidas?|me gusta|赞|讚"), "instagram_meta_description", "medium");
    set("comments", labeled("comments?|comentários?|comentarios?|评论|評論"), "instagram_meta_description", "medium");
  }
  for (const script of pageIdentityMismatch ? []
    : Array.from(doc?.querySelectorAll?.('script[type="application/ld+json"]') || [])) {
    try {
      const data = JSON.parse(script.textContent || "null");
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
      const identifiers = [...new Set([
        item?.identifier, item?.videoId, item?.shortcode, item?.code
      ].map((value) => String(value ?? "").trim()).filter(Boolean))];
        const url = String(item?.url ?? item?.contentUrl ?? "");
      if (!identifiers.includes(String(target.video_id)) && !url.includes(String(target.video_id))) continue;
      identityMatchCount += 1;
        for (const stat of Array.isArray(item?.interactionStatistic) ? item.interactionStatistic : []) {
          const type = String(stat?.interactionType?.["@type"] || "").toLowerCase();
          if (type.includes("watch")) set("views", stat.userInteractionCount, "json_ld");
          if (type.includes("like")) set("likes", stat.userInteractionCount, "json_ld");
          if (type.includes("comment")) set("comments", stat.userInteractionCount, "json_ld");
        }
      }
    } catch (_) {}
  }
  const fields = Object.fromEntries(Object.keys(result).map((name) => [name, evidence[name] || {
    source: "missing", confidence: "low", missing_reason: "not_exposed"
  }]));
  for (const name of Object.keys(result)) fields[name].value = result[name];
  const available = Object.values(result).filter((value) => value !== null).length;
  const authRequired = Boolean(doc?.querySelector?.('[data-e2e="login-modal"], form[action*="login"]'));
  const platformRestricted = Boolean(doc?.querySelector?.('iframe[src*="captcha"], [class*="challenge"], [data-e2e*="verify"]'));
  const playbackAuthRequired = playbackState === "LOGIN_REQUIRED";
  const playbackUnavailable = ["ERROR", "UNPLAYABLE", "CONTENT_CHECK_REQUIRED", "AGE_CHECK_REQUIRED"]
    .includes(playbackState);
  if (pageIdentityMismatch) {
    for (const name of Object.keys(result)) {
      result[name] = null;
      delete evidence[name];
      fields[name] = { value: null, source: "missing", confidence: "low", missing_reason: "video_identity_mismatch" };
    }
  }
  const verifiedAvailable = pageIdentityMismatch ? 0 : available;
  const safeError = verifiedAvailable ? "" : pageIdentityMismatch ? "VIDEO_IDENTITY_MISMATCH"
    : platformRestricted ? "PLATFORM_RESTRICTED" : (authRequired || playbackAuthRequired) ? "AUTH_REQUIRED"
      : playbackUnavailable ? "PLAYBACK_UNAVAILABLE" : "METRICS_NOT_FOUND";
  return {
    capture_status: verifiedAvailable === 4 ? "success" : (verifiedAvailable ? "partial" : "insufficient"),
    safe_error_code: safeError,
    metrics: fields,
    diagnostic: {
      stage: verifiedAvailable ? "metrics_collected" : pageIdentityMismatch ? "video_identity_mismatch"
        : platformRestricted ? "platform_restricted" : (authRequired || playbackAuthRequired) ? "auth_required"
          : playbackUnavailable ? "playback_unavailable" : "metrics_not_found",
      playback_state: playbackState || "unknown",
      identity_match_count: identityMatchCount,
      identity_rejected_count: identityRejectedCount,
      login_required: authRequired || playbackAuthRequired,
      fields_present: Object.fromEntries(Object.entries(result).map(([name, value]) => [name, value !== null])),
      sources: Object.fromEntries(Object.entries(evidence).map(([name, value]) => [name, value.source])),
    },
  };
}

export async function collectPublicationFromTab(tabId, pageUrl, timeoutMs = 15000) {
  const identity = publicationIdentity(pageUrl);
  if (!identity) return { capture_status: "failed", safe_error_code: "UNSUPPORTED_PAGE", metrics: {}, diagnostic: { stage: "unsupported_page" } };
  try {
    const tab = await chrome.tabs?.get?.(tabId);
    const actualIdentity = publicationIdentity(tab?.url || pageUrl);
    if (actualIdentity && (actualIdentity.platform !== identity.platform || actualIdentity.video_id !== identity.video_id)) {
      return { identity, capture_status: "insufficient", safe_error_code: "VIDEO_IDENTITY_MISMATCH", metrics: {},
        diagnostic: { stage: "video_identity_mismatch" } };
    }
  } catch (_) {}
  const startedAt = Date.now();
  let capture = null;
  let bestCapture = null;
  let bestAvailable = 0;
  let attempts = 0;
  while (Date.now() - startedAt < timeoutMs) {
    const remaining = Math.max(1, timeoutMs - (Date.now() - startedAt));
    let timeoutId;
    let execution;
    try {
      execution = await Promise.race([
        chrome.scripting.executeScript({ target: { tabId }, world: "MAIN", func: collectPublicationPage, args: [identity] }),
        new Promise((resolve) => { timeoutId = setTimeout(() => resolve(null), remaining); }),
      ]);
    } catch (_) {
      clearTimeout(timeoutId);
      return { identity, capture_status: "failed", safe_error_code: "COLLECTOR_NOT_STARTED", metrics: {}, diagnostic: { stage: "collector_not_started" } };
    }
    clearTimeout(timeoutId);
    if (!execution) return { identity, capture_status: "failed", safe_error_code: "CAPTURE_TIMEOUT", metrics: {}, diagnostic: { stage: "timeout" } };
    attempts += 1;
    capture = execution?.[0]?.result || {
      capture_status: "failed", safe_error_code: "COLLECTOR_UNAVAILABLE", metrics: {},
      diagnostic: { stage: "collector_unavailable" }
    };
    const available = Object.values(capture.metrics || {})
      .filter((field) => field?.value !== null && field?.value !== undefined).length;
    if (available > bestAvailable) {
      bestAvailable = available;
      bestCapture = capture;
    }
    if (capture.capture_status === "success"
        || ["PLATFORM_RESTRICTED", "VIDEO_IDENTITY_MISMATCH", "PLAYBACK_UNAVAILABLE"].includes(capture.safe_error_code)) break;
    if (capture.capture_status === "partial") {
      if (identity.platform === "Instagram" || capture.metrics?.views?.value != null) break;
    }
    if (identity.platform === "TikTok") break;
    const waitMs = Math.min(500, timeoutMs - (Date.now() - startedAt));
    if (waitMs <= 0) break;
    await new Promise((resolve) => setTimeout(resolve, waitMs));
  }
  if (bestCapture && bestAvailable > Object.values(capture?.metrics || {})
    .filter((field) => field?.value !== null && field?.value !== undefined).length) capture = bestCapture;
  capture ||= { capture_status: "insufficient", safe_error_code: "EVIDENCE_NOT_FOUND", metrics: {}, diagnostic: {} };
  if (capture.capture_status === "insufficient" && capture.safe_error_code === "METRICS_NOT_FOUND") {
    capture.safe_error_code = "EVIDENCE_NOT_FOUND";
    capture.diagnostic = { ...(capture.diagnostic || {}), stage: "evidence_not_found", attempts };
  }
  capture.diagnostic = {
    ...(capture.diagnostic || {}), attempts,
    elapsed_ms: Math.max(0, Date.now() - startedAt),
  };
  if (identity.platform === "Instagram") {
    try {
      const stored = await chrome.storage.session.get(INSTAGRAM_RECENT_CACHE_KEY);
      capture = mergeInstagramRecentMetrics(capture, identity, stored?.[INSTAGRAM_RECENT_CACHE_KEY]);
    } catch (_) {}
    return { identity, ...capture };
  }
  if (identity.platform !== "TikTok") return { identity, ...capture };

  const profile = new URL(pageUrl).pathname.match(/^\/@([A-Za-z0-9._-]+)\/video\/\d+/)?.[1] || "";
  let passive = null;
  try {
    const isolated = await chrome.scripting.executeScript({
      target: { tabId }, world: "ISOLATED",
      func: (expectedProfile, videoId) => {
        const runtime = globalThis.KOLConnectTikTokCapture;
        if (!runtime) return { state: "runtime_unavailable" };
        try {
          const snapshot = runtime.snapshot(expectedProfile);
          if (snapshot.stopped) return { state: "platform_restricted", reason: snapshot.stopped };
          const row = snapshot.items.find((item) => String(item.video_id) === String(videoId));
          return row ? { state: "matched", row } : { state: "video_identity_missing" };
        } catch (_) { return { state: "video_identity_mismatch" }; }
      },
      args: [profile, identity.video_id],
    });
    passive = isolated?.[0]?.result || null;
  } catch (_) { passive = { state: "runtime_unavailable" }; }
  if (passive?.state === "matched") {
    for (const name of ["views", "likes", "comments", "shares"]) {
      const field = passive.row?.[name];
      if (field?.source !== "tiktok_item_list_api" || field?.confidence !== "high"
          || !Number.isSafeInteger(field.value) || field.value < 0) continue;
      capture.metrics[name] = { value: field.value, source: field.source, confidence: field.confidence, missing_reason: "" };
    }
    const available = Object.values(capture.metrics).filter((field) => field?.value !== null && field?.value !== undefined).length;
    capture.capture_status = available === 4 ? "success" : available ? "partial" : "insufficient";
    capture.safe_error_code = available ? "" : "METRICS_NOT_FOUND";
    capture.diagnostic = { stage: available ? "metrics_collected" : "metrics_not_found", passive_state: passive.state,
      fields_present: Object.fromEntries(Object.entries(capture.metrics).map(([name, field]) => [name, field?.value != null])) };
  } else if (!Object.values(capture.metrics || {}).some((field) => field?.value != null)) {
    capture.safe_error_code = passive?.state === "platform_restricted" ? "PLATFORM_RESTRICTED"
      : passive?.state === "video_identity_mismatch" ? "VIDEO_IDENTITY_MISMATCH"
        : passive?.state === "video_identity_missing" ? "VIDEO_IDENTITY_MISSING" : "SOURCE_UNAVAILABLE";
    capture.diagnostic = { stage: passive?.state || "source_unavailable" };
  }
  return { identity, ...capture };
}
