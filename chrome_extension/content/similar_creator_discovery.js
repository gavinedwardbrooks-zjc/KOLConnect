(() => {
  const GLOBAL_KEY = "KOLConnectSimilarCreatorDiscovery";
  if (globalThis[GLOBAL_KEY]) return;
  const STORAGE_KEY = "kolconnect_similar_creator_session_v2";
  const LEGACY_STORAGE_KEY = "kolconnect_similar_creator_session_v1";

  const clean = (value) => String(value ?? "").trim();
  const canonicalTikTokProfile = (value) => {
    try {
      const url = new URL(value, location.href);
      if (!/(^|\.)tiktok\.com$/i.test(url.hostname)) return "";
      const match = url.pathname.match(/^\/@([A-Za-z0-9._]{2,30})\/?$/);
      return match ? `https://www.tiktok.com/@${match[1]}` : "";
    } catch (_) { return ""; }
  };
  const INSTAGRAM_RESERVED_PATHS = new Set([
    "accounts", "about", "api", "challenge", "developer", "direct", "directory", "emails",
    "explore", "legal", "p", "privacy", "reel", "reels", "stories", "terms", "web"
  ]);
  const canonicalInstagramProfile = (value) => {
    try {
      const url = new URL(value, location.href);
      if (!/(^|\.)instagram\.com$/i.test(url.hostname)) return "";
      const match = url.pathname.match(/^\/([A-Za-z0-9._]{1,30})\/?$/);
      if (!match || INSTAGRAM_RESERVED_PATHS.has(match[1].toLowerCase())) return "";
      return `https://www.instagram.com/${match[1]}/`;
    } catch (_) { return ""; }
  };
  const platformContext = (value = location.href) => {
    const tiktok = canonicalTikTokProfile(value);
    if (tiktok) return { platform: "TikTok", seed_url: tiktok };
    const instagram = canonicalInstagramProfile(value);
    if (instagram) return { platform: "Instagram", seed_url: instagram };
    return { platform: "", seed_url: "" };
  };
  const emptyState = () => ({ status: "idle", ...platformContext(), candidates: new Map(), updated_at: "" });
  let state = emptyState();
  let observer = null;
  let rootObserver = null;
  let observedRegion = null;
  const scrollRoots = new Set();
  const listeners = new Set();

  const publicState = () => ({
    status: state.status, platform: state.platform, seed_url: state.seed_url,
    seed_profile_url: state.seed_url, updated_at: state.updated_at,
    candidates: [...state.candidates.values()].sort((a, b) => a.username.localeCompare(b.username))
  });
  const emit = () => listeners.forEach((listener) => listener(publicState()));
  const persist = async () => {
    state.updated_at = new Date().toISOString();
    const stored = { ...state, candidates: Object.fromEntries(state.candidates) };
    try { await chrome.storage.local.set({ [STORAGE_KEY]: stored }); } catch (_) {}
    emit();
  };
  const restore = async () => {
    try {
      const result = await chrome.storage.local.get([STORAGE_KEY, LEGACY_STORAGE_KEY]);
      const stored = result[STORAGE_KEY] || result[LEGACY_STORAGE_KEY];
      const context = platformContext();
      const storedPlatform = clean(stored?.platform) || (canonicalTikTokProfile(stored?.seed_url) ? "TikTok" : "");
      if (stored && stored.seed_url === context.seed_url && storedPlatform === context.platform
          && stored.candidates && typeof stored.candidates === "object") {
        state = {
          ...emptyState(), ...stored, platform: storedPlatform,
          candidates: new Map(Object.entries(stored.candidates)),
          status: stored.status === "running" ? "paused" : stored.status
        };
      }
    } catch (_) {}
    emit();
  };

  const isVisible = (element) => {
    const box = element?.getBoundingClientRect?.();
    return Boolean(box && box.width > 180 && box.height > 80);
  };
  const recommendationSignal = (element) => /推荐|建议|你可能|相似|similar|suggested|accounts you may|discover/i
    .test(clean(element?.textContent).toLowerCase());
  const instagramRecommendationHeading = (element) => /^(你可能喜欢的账户|为你推荐|推荐用户|推荐帐户|suggested for you|suggested accounts|accounts you may like)$/i
    .test(clean(element?.textContent));
  const canonicalForPlatform = (platform, value) => platform === "Instagram"
    ? canonicalInstagramProfile(value) : canonicalTikTokProfile(value);
  const profileLinks = (element, platform = platformContext().platform) => [...(element?.querySelectorAll?.("a[href]") || [])]
    .map((anchor) => canonicalForPlatform(platform, anchor.href)).filter(Boolean);

  // Adapted from CreatorGraph v1.1: TikTok keeps the proven modal scoring,
  // while Instagram is bounded to its explicit recommendation heading and list.
  const modalCandidates = () => [...document.querySelectorAll([
    '[role="dialog"]', '[aria-modal="true"]', '[data-e2e*="modal"]',
    '[class*="ModalContainer"]', '[class*="Dialog"]'
  ].join(", "))]
    .filter((element, index, items) => items.indexOf(element) === index && isVisible(element))
    .map((element) => ({ element, profiles: profileLinks(element, "TikTok"), width: element.getBoundingClientRect().width }))
    .filter((candidate) => candidate.profiles.length >= 2 && !candidate.element.querySelector('input[type="password"]'))
    .sort((left, right) => right.profiles.length - left.profiles.length || right.width - left.width);

  const signaledInlineRoots = () => [...document.querySelectorAll([
    '[data-e2e*="recommend"]', '[data-e2e*="suggest"]', 'section', 'aside',
    'h1', 'h2', 'h3', 'h4', 'p', '[role="heading"]'
  ].join(", "))]
    .filter((element) => recommendationSignal(element))
    .map((element) => {
      let node = element;
      while (node && node !== document.body) {
        if (isVisible(node) && profileLinks(node, "TikTok").length >= 2) return node;
        node = node.parentElement;
      }
      return null;
    }).filter(Boolean);

  const inlineCandidates = () => [...new Set(signaledInlineRoots())]
    .filter((element) => recommendationSignal(element) && profileLinks(element, "TikTok").length >= 2)
    .map((element) => ({ element, profiles: profileLinks(element, "TikTok"), width: element.getBoundingClientRect().width }))
    .sort((left, right) => right.profiles.length - left.profiles.length || right.width - left.width);

  const modalFromClick = (target) => {
    let node = target instanceof Element ? target : null;
    while (node && node !== document.body) {
      if (isVisible(node) && profileLinks(node, "TikTok").length >= 2 && recommendationSignal(node)) return node;
      node = node.parentElement;
    }
    return null;
  };

  const instagramRecommendationRegions = () => [...document.querySelectorAll('h1,h2,h3,h4,[role="heading"],span,div')]
    .filter((element) => instagramRecommendationHeading(element))
    .map((heading) => {
      let node = heading;
      for (let depth = 0; node && node !== document.body && depth < 8; depth += 1, node = node.parentElement) {
        const box = node.getBoundingClientRect?.();
        const list = node.querySelector?.("ul");
        if (list && box && box.width > 180 && box.height > 80 && box.height < 900
            && profileLinks(list, "Instagram").length >= 2) return node;
      }
      return null;
    }).filter(Boolean);

  const recommendationRegion = () => {
    const context = platformContext();
    if (context.platform === "Instagram") return instagramRecommendationRegions()[0] || null;
    if (context.platform !== "TikTok") return null;
    const candidates = modalCandidates();
    const signaled = candidates.find((candidate) => recommendationSignal(candidate.element));
    return signaled?.element || inlineCandidates()[0]?.element || null;
  };
  const recommendationModal = recommendationRegion;

  const bindScrollRoots = (region) => {
    const next = new Set([region, ...region.querySelectorAll("*")].filter((element) =>
      Number(element?.scrollWidth || 0) > Number(element?.clientWidth || 0) + 2
      || Number(element?.scrollHeight || 0) > Number(element?.clientHeight || 0) + 2));
    for (const element of scrollRoots) {
      if (!next.has(element)) {
        element.removeEventListener?.("scroll", collect);
        scrollRoots.delete(element);
      }
    }
    for (const element of next) {
      if (!scrollRoots.has(element)) {
        element.addEventListener?.("scroll", collect, { passive: true });
        scrollRoots.add(element);
      }
    }
  };

  const stopObservers = () => {
    for (const element of scrollRoots) element.removeEventListener?.("scroll", collect);
    scrollRoots.clear();
    window.removeEventListener("scroll", collect);
    observer?.disconnect(); rootObserver?.disconnect(); observer = rootObserver = null;
    observedRegion = null;
  };
  const collect = async () => {
    if (state.status !== "running") return;
    const context = platformContext();
    if (!context.seed_url || context.seed_url !== state.seed_url || context.platform !== state.platform) {
      state.status = "paused"; stopObservers(); await persist(); return;
    }
    const region = recommendationRegion();
    if (!region) return;
    let changed = false;
    for (const anchor of region.querySelectorAll("a[href]")) {
      const profileUrl = canonicalForPlatform(state.platform, anchor.href);
      if (!profileUrl || profileUrl === state.seed_url) continue;
      const username = state.platform === "TikTok"
        ? profileUrl.split("/@")[1]
        : new URL(profileUrl).pathname.split("/").filter(Boolean)[0];
      const existing = state.candidates.get(profileUrl);
      const sources = new Set([...(existing?.seed_urls || []), state.seed_url]);
      const observedAt = new Date().toISOString();
      const firstObservedAt = existing?.first_observed_at || existing?.observed_at || observedAt;
      const recommendationSource = state.platform === "Instagram"
        ? "instagram_recommendation_region" : "tiktok_recommendation_region";
      state.candidates.set(profileUrl, {
        platform: state.platform, seed_platform: state.platform,
        profile_url: profileUrl, canonical_profile_url: profileUrl, candidate_profile_url: profileUrl,
        username, candidate_username: username,
        seed_url: state.seed_url, seed_profile_url: state.seed_url, seed_urls: [...sources],
        recommendation_source: recommendationSource,
        recommendation_region: state.platform === "Instagram" ? "suggested_accounts" : "recommended_accounts",
        observed_at: firstObservedAt, first_observed_at: firstObservedAt, last_observed_at: observedAt
      });
      changed ||= !existing || sources.size !== (existing.seed_urls || []).length;
    }
    if (changed) await persist();
    if (observedRegion !== region) {
      observer?.disconnect();
      observer = new MutationObserver(() => collect());
      observedRegion = region;
      observer.observe(region, { childList: true, subtree: true, attributes: true, attributeFilter: ["href"] });
    }
    bindScrollRoots(region);
  };

  const startRootObserver = () => {
    if (rootObserver) return;
    rootObserver = new MutationObserver(() => collect());
    rootObserver.observe(document.documentElement, { childList: true, subtree: true });
    window.addEventListener("scroll", collect, { passive: true });
  };
  const start = async () => {
    const context = platformContext();
    if (!context.seed_url) return { ok: false, code: "SUPPORTED_PROFILE_REQUIRED" };
    if (!recommendationRegion()) return { ok: false, code: "RECOMMENDATION_REGION_NOT_FOUND" };
    if (state.seed_url !== context.seed_url || state.platform !== context.platform) state = emptyState();
    state.seed_url = context.seed_url; state.platform = context.platform; state.status = "running";
    startRootObserver(); await collect(); await persist();
    return { ok: true, state: publicState() };
  };
  const pause = async () => { if (state.status === "running") state.status = "paused"; await persist(); return publicState(); };
  const resume = async () => {
    const context = platformContext();
    if (state.status === "paused" && context.seed_url === state.seed_url && context.platform === state.platform) {
      state.status = "running"; startRootObserver(); await collect();
    }
    await persist(); return publicState();
  };
  const finish = async () => { state.status = "finished"; stopObservers(); await persist(); return publicState(); };
  const clear = async () => {
    state = emptyState(); stopObservers();
    try { await chrome.storage.local.remove([STORAGE_KEY, LEGACY_STORAGE_KEY]); } catch (_) {}
    emit();
  };
  const subscribe = (listener) => { listeners.add(listener); listener(publicState()); return () => listeners.delete(listener); };

  globalThis[GLOBAL_KEY] = Object.freeze({
    start, pause, resume, finish, clear, subscribe, getState: publicState,
    canonicalTikTokProfile, canonicalInstagramProfile, platformContext,
    modalCandidates, modalFromClick, instagramRecommendationRegions, recommendationRegion,
    recommendationModal, restore
  });
  restore();
})();
