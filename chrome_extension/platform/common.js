export async function executePageFunction(tabId, collector, args = []) {
  const [execution] = await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    func: collector,
    args
  });
  if (!execution?.result) throw new Error("The page did not return a collection result.");
  return execution.result;
}

export async function executeProfileCollector(tabId, collector) {
  return executePageFunction(tabId, collector);
}

export function abortPageDetailRequests() {
  const registry = globalThis.__KOLCONNECT_DETAIL_CONTROLLERS__;
  if (!registry || typeof registry[Symbol.iterator] !== "function") return { aborted: 0 };
  let aborted = 0;
  for (const controller of registry) {
    try {
      controller.abort();
      aborted += 1;
    } catch (_) {}
  }
  registry.clear?.();
  return { aborted };
}

export function hostMatches(url, domain) {
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return hostname === domain || hostname.endsWith(`.${domain}`);
  } catch (_) {
    return false;
  }
}

export function cleanMultiline(value, limit = 5000) {
  return String(value ?? "")
    .replace(/\\r\\n|\\r|\\n/g, "\n")
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n")
    .slice(0, limit)
    .trim();
}

export function isStatsLine(line, platform = "") {
  const normalized = cleanMultiline(line, 256);
  if (/^(?:[\d.,]+\s*[KMB万萬億亿]?\s*)?(?:posts?|followers?|following|likes?|videos?|seguidores?|seguindo|publica(?:ç|c)[õo]es|inscritos?)\b/i.test(normalized)) {
    return true;
  }
  if (String(platform).toLowerCase() !== "instagram") return false;
  return /^(?:[\d.,]+\s*[KMB万萬億亿]?\s*)?(?:帖子|貼文|贴文|粉丝|粉絲|关注|關注|追蹤中|追踪中)$/i.test(normalized);
}

function isUiLine(line) {
  return /^(?:follow|following|message|contact|subscribe|subscribed|home|videos|shorts|live|posts|reels|tagged)$/i.test(line);
}

function isOnlyUrl(line) {
  return /^(?:https?:\/\/|www\.)\S+$/i.test(line);
}

function cleanLines(value, { username = "", creatorName = "", stripStats = true, platform = "" } = {}) {
  const aliases = [username, username.replace(/^@/, ""), creatorName]
    .map((item) => cleanMultiline(item).toLowerCase())
    .filter(Boolean);
  const lines = cleanMultiline(value)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !isUiLine(line))
    .filter((line) => !isOnlyUrl(line))
    .filter((line) => !stripStats || !isStatsLine(line, platform))
    .filter((line) => !aliases.includes(line.toLowerCase()));
  return [...new Set(lines)].join("\n").trim();
}

function cleanInstagramMeta(value) {
  return cleanMultiline(value)
    .replace(
      /^\s*[\d.,]+\s*[KMB万]?\s+Followers?,\s*[\d.,]+\s*[KMB万]?\s+Following,\s*[\d.,]+\s*[KMB万]?\s+Posts?\s*[-–—:]\s*/i,
      ""
    )
    .replace(/^See Instagram photos and videos from\s+[^:]+:?\s*/i, "")
    .replace(/\s+on Instagram:?\s*$/i, "")
    .trim();
}

function cleanTikTokMeta(value) {
  return cleanMultiline(value)
    .replace(/^.+?\(@[^)]+\)\s+on TikTok\s*\|\s*/i, "")
    .replace(/\b[\d.,]+\s*[KMB万]?\s+(?:Likes?|Followers?|Following)\.?\s*/gi, "")
    .replace(/\bWatch\s+[^.]*videos?\s+from\s+[^.]+\.?/gi, "")
    .trim();
}

function isMeaningfulYouTubeDescription(value, username, creatorName) {
  const text = cleanLines(value, { username, creatorName });
  if (!text) return false;
  if (/^(?:share your videos|youtube|home|videos|shorts|live|playlists|community)$/i.test(text)) return false;
  if (/^[\p{P}\p{S}\s]+$/u.test(text)) return false;
  const words = text.match(/[\p{L}\p{N}]+/gu) || [];
  if (text.length < 12 && words.length <= 2 && words.every((word) => word.length <= 3)) return false;
  return true;
}

export function selectBio(candidates = [], options = {}) {
  const platform = String(options.platform || "").toLowerCase();
  const missingReason = platform === "youtube"
    ? "The current YouTube channel page did not expose a public description."
    : "Creator bio was not exposed by the current public page.";
  const priorities = ["structured_data", "profile_dom", "meta"];

  for (const source of priorities) {
    for (const candidate of candidates.filter((item) => item?.source === source)) {
      let raw = candidate.value;
      if (source === "meta" && platform === "instagram") raw = cleanInstagramMeta(raw);
      if (source === "meta" && platform === "tiktok") raw = cleanTikTokMeta(raw);
      const value = cleanLines(raw, {
        username: options.username,
        creatorName: options.creatorName,
        stripStats: true,
        platform
      });
      if (!value) continue;
      if (platform === "youtube" && !isMeaningfulYouTubeDescription(value, options.username, options.creatorName)) {
        continue;
      }
      return {
        value,
        source,
        confidence: source === "structured_data" ? "high" : source === "profile_dom" ? "medium" : "low",
        missing_reason: ""
      };
    }
  }

  return {
    value: null,
    source: "missing",
    confidence: "missing",
    missing_reason: missingReason
  };
}

function publicField(value, source, missingReason) {
  const normalized = cleanMultiline(value, 512);
  return {
    value: normalized || null,
    source: normalized ? String(source || "page_dom") : "",
    confidence: normalized ? (source === "structured_data" ? "high" : "medium") : "missing",
    missing_reason: normalized ? "" : missingReason
  };
}

function firstCandidate(candidates, extractor) {
  for (const candidate of Array.isArray(candidates) ? candidates : []) {
    const value = extractor(String(candidate?.value ?? ""));
    if (value) return { value, source: candidate?.source || "page_dom" };
  }
  return { value: "", source: "" };
}

export function extractPublicProfileFields(publicProfile = {}) {
  const email = firstCandidate(publicProfile.email_candidates, (text) => (
    text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)?.[0] || ""
  ));
  const whatsapp = firstCandidate(publicProfile.whatsapp_candidates, (text) => {
    const waDigits = text.match(/(?:wa\.me\/|api\.whatsapp\.com\/send\/?\?phone=)(\d{7,15})/i)?.[1];
    if (waDigits) return `+${waDigits}`;
    const explicit = text.match(/(?:whats\s*app|whatsapp)\D{0,20}(\+?\d[\d\s().-]{6,20}\d)/i)?.[1];
    return explicit ? explicit.replace(/[^\d+]/g, "") : "";
  });
  const country = firstCandidate(publicProfile.country_candidates, (text) => cleanMultiline(text, 128));
  const language = firstCandidate(publicProfile.language_candidates, (text) => cleanMultiline(text, 128));
  return {
    email: publicField(email.value, email.source, "A public creator email was not exposed by the current page."),
    whatsapp: publicField(whatsapp.value, whatsapp.source, "A public WhatsApp contact was not exposed by the current page."),
    country: publicField(country.value, country.source, "Creator country was not explicitly exposed by the current page."),
    language: publicField(language.value, language.source, "Creator language was not explicitly exposed by the current page.")
  };
}

export function applyPublicProfileFields(result = {}) {
  const publicProfile = result.public_profile || {};
  result.fields ||= {};
  Object.assign(result.fields, extractPublicProfileFields(publicProfile));
  delete result.public_profile;
  return result;
}
