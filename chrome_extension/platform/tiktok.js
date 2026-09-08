import {
  contentItem,
  finalizeContentAnalysis,
} from "../core/content_analysis.js";
import {
  applyPublicProfileFields,
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
          bio: multiline(user.signature || user.bio),
          email: clean(user.businessEmail || user.publicEmail, 320),
          whatsapp: clean(user.whatsapp || user.whatsApp, 128),
          country: clean(user.country || user.region, 128),
          language: clean(user.language || user.lang, 128)
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
  const contactLinks = [...document.querySelectorAll('a[href^="mailto:"], a[href*="wa.me/"], a[href*="api.whatsapp.com/"]')]
    .map((node) => clean(node.href || node.textContent, 512));
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
  applyPublicProfileFields(result);
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
  const candidates = [];
  const visibleLinks = [...document.querySelectorAll('a[href*="/video/"]')].filter((anchor) => {
    try {
      const url = new URL(anchor.href);
      return url.protocol === "https:" && ["www.tiktok.com", "tiktok.com", "m.tiktok.com"].includes(url.hostname)
        && url.pathname.startsWith(`/@${handle}/video/`) && anchor.getClientRects().length > 0;
    } catch (_) { return false; }
  });
  const visibleIds = new Set(visibleLinks.map((anchor) => anchor.href.match(/\/video\/(\d+)/)?.[1]));
  const add = (raw) => {
    if (typeof (raw.video_id || raw.id) !== "string") return;
    const videoId = clean(raw.video_id || raw.id, 128);
    const videoUrl = clean(raw.video_url || (videoId && handle
      ? `https://www.tiktok.com/@${handle}/video/${videoId}`
      : ""));
    if (!/^\d{1,32}$/.test(videoId) || candidates.length >= 200) return;
    candidates.push({ ...raw, video_id: videoId, video_url: videoUrl });
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
      const author = node.author?.uniqueId || node.author?.unique_id || "";
      const belongs = author ? typeof author === "string" && author.toLowerCase() === handle.toLowerCase()
        : visibleIds.has(String(videoId));
      if (belongs && videoId && (
        node.video
        || node.desc !== undefined
        || stats.playCount !== undefined
        || stats.play_count !== undefined
      )) {
        const mapped = {
          video_id: videoId,
          video_url: node.shareInfo?.shareUrl || node.share_url || "",
          title: clean(node.desc || node.title) || null,
          views: stats.playCount ?? stats.play_count ?? null,
          likes: stats.diggCount ?? stats.digg_count ?? null,
          comments: stats.commentCount ?? stats.comment_count ?? null,
          shares: stats.shareCount ?? stats.share_count ?? null,
          published_at: node.createTime ?? node.create_time ?? null,
          is_pinned: typeof node.isPinnedItem === "boolean" ? node.isPinnedItem : null,
          source: "hydration"
        };
        add(mapped);
      }
      for (const child of Array.isArray(node) ? node : Object.values(node)) {
        if (child && typeof child === "object" && queue.length < 12000) queue.push(child);
      }
    }
  }

  for (const anchor of visibleLinks) {
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
      source: "dom"
    });
  }

  return candidates;
}

export async function captureState(tabId, profile, fallback = []) {
  const result = await chrome.scripting.executeScript({
    target: { tabId }, world: "ISOLATED",
    func: (expected, items) => {
      if (!globalThis.KOLConnectTikTokCapture) throw new Error("CAPTURE_L1_UNAVAILABLE: reload the TikTok tab after updating the extension.");
      return globalThis.KOLConnectTikTokCapture.snapshot(expected, items);
    },
    args: [profile, fallback],
  });
  return result[0].result;
}

export async function readCaptureDiagnostics(tabId) {
  const read = async (world, func) => {
    try { return (await chrome.scripting.executeScript({ target: { tabId }, world, func }))[0]?.result || null; }
    catch (_) { return null; }
  };
  const main = await read("MAIN", () => ({
    installed: Boolean(globalThis.__kolconnectPassiveCaptureMainV1__),
    protocol_available: Boolean(globalThis.KOLConnectPassiveCaptureProtocol),
    control_available: Boolean(globalThis.KOLConnectPassiveCaptureControl),
    counters: globalThis.KOLConnectPassiveCaptureControl?.diagnostics?.() || null,
  }));
  const runtime = await read("ISOLATED", () => globalThis.KOLConnectTikTokCapture?.diagnostics?.() || null);
  // MAIN is page-controlled. Export only fixed keys with numeric/boolean values.
  const counts = (source, keys) => Object.fromEntries(keys.split(" ").map(key =>
    [key, Number.isSafeInteger(source?.[key]) && source[key] >= 0 ? source[key] : null]));
  const flags = (source, keys) => Object.fromEntries(keys.split(" ").map(key =>
    [key, typeof source?.[key] === "boolean" ? source[key] : null]));
  const sessionReasons = "stopped profile_missing profile_mismatch timestamp layer invalid_id author_mismatch capacity batch_limit";
  return {
    scope: "document_lifetime_counters_current_session_rows",
    main: { available: Boolean(main), ...flags(main, "installed protocol_available control_available"),
      ...flags(main?.counters, "fetch_wrapper_current xhr_open_wrapper_current xhr_send_wrapper_current"),
      ...counts(main?.counters, "fetch_interceptions xhr_interceptions target_matches envelopes_emitted envelopes_replayed pending_envelopes generation"),
      matched_families: counts(main?.counters?.matched_families, "tiktok_item_list tiktok_user_detail tiktok_comment_list"),
      misses: counts(main?.counters?.misses, "profile_missing old_generation response_unavailable response_rejected redirect_mismatch clone_failed body_too_large decode_failed emit_failed observation_failed xhr_response_type") },
    runtime: { available: Boolean(runtime), ...flags(runtime, "bridge_connected parser_error"),
      bridge: { ...flags(runtime?.bridge, "token_configured"),
        ...counts(runtime?.bridge, "accepted rejected parser_invocations parser_success parser_errors normalized_rows consumer_errors"),
        rejected_reasons: counts(runtime?.bridge?.rejected_reasons, "source origin token_unavailable token_mismatch invalid_envelope receiver_exception"),
        parser_reasons: counts(runtime?.bridge?.parser_reasons, "invalid_payload exception") },
      session: { ...flags(runtime?.session, "stopped"),
        ...counts(runtime?.session, "accepted_rows rejected_rows l1_accepted_rows l1_rejected_rows current_rows current_l1_rows generation"),
        rejected_reasons: counts(runtime?.session?.rejected_reasons, sessionReasons),
        l1_rejected_reasons: counts(runtime?.session?.l1_rejected_reasons, sessionReasons) } },
  };
}

export async function resetCapture(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, world: "MAIN",
    func: () => globalThis.KOLConnectPassiveCaptureControl?.reset() });
  await chrome.scripting.executeScript({ target: { tabId }, world: "ISOLATED",
    func: () => globalThis.KOLConnectTikTokCapture?.reset() });
}

export async function collectRecentContent(tabId, options = {}) {
  const profile = new URL(options.analysisUrl).pathname.match(/^\/@([A-Za-z0-9._]+)\/?$/)?.[1];
  if (!profile) throw new Error("CAPTURE_PROFILE_REQUIRED");
  const initial = await captureState(tabId, profile);
  if (initial.stopped) throw new Error(initial.stopped);
  if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
  options.onProgress?.({ phase: "discovering" });
  const observedAt = new Date().toISOString();
  let discovered = [], fallbackError = false;
  try {
    discovered = await executePageFunction(tabId, discoverTikTokContent);
    if (!Array.isArray(discovered)) throw new Error("PARSER_ERROR");
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    discovered = []; fallbackError = true;
  }
  const fallback = discovered.map((raw) => {
    const layer = raw.source === "hydration" ? "L2" : "L3";
    const confidence = layer === "L2" ? "medium" : "low";
    const item = { ...raw, platform: "TikTok", content_type: "video",
      capture_layer: layer, observed_at: observedAt };
    for (const field of ["views", "likes", "comments", "shares"]) {
      item[field + "_source"] = raw.source;
      item[field + "_confidence"] = confidence;
      item[field + "_missing_reason"] = "Not exposed by the current page.";
    }
    item.published_source = raw.source;
    item.published_confidence = confidence;
    return { ...contentItem(item), is_pinned: raw.is_pinned ?? null };
  });
  if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
  const state = await captureState(tabId, profile, fallback);
  if (state.stopped) throw new Error(state.stopped);
  const analysis = finalizeContentAnalysis(state.items, {
    limit: Math.min(20, Number(options.limit) || 20),
    excludePinned: options.excludePinned !== false, contentType: "video",
  });
  const layers = state.items.map((item) => item.capture_layer);
  analysis.passive_capture_status = layers.includes("L1") ? "CAPTURE_L1_ACTIVE"
    : layers.includes("L2") ? "FALLBACK_L2" : layers.includes("L3") ? "FALLBACK_L3"
      : state.parser_error || fallbackError ? "PARSER_ERROR" : "NO_DATA";
  analysis.capture_diagnostics = {
    l1: layers.includes("L1") ? "CAPTURE_L1_ACTIVE" : "CAPTURE_L1_UNAVAILABLE",
    l2: fallback.some((row) => row.capture_layer === "L2") ? "AVAILABLE" : "UNAVAILABLE",
    l3: fallback.some((row) => row.capture_layer === "L3") ? "AVAILABLE" : "UNAVAILABLE",
    bridge_connected: state.l1_available, parser_error: state.parser_error,
    fallback_error: fallbackError ? "PARSER_ERROR" : "",
  };
  analysis.capture_session_id = state.session_id;
  analysis.detail_request_count = 0;
  return analysis;
}

export async function cancelRecentContent(tabId) {
  return chrome.scripting.executeScript({ target: { tabId }, world: "ISOLATED",
    func: () => globalThis.KOLConnectTikTokCapture?.stop() });
}
