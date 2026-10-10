import "../config.js";
import { PROFILE_FIELD_NAMES } from "../core/schema.js";

const DEFAULT_API_URL = "http://127.0.0.1:8765";
export const CONTENT_CATEGORY_OPTIONS = globalThis.KOLConnectConfig.CONTENT_CATEGORY_OPTIONS;

const clean = (value) => String(value ?? "").trim();

export class LocalApiError extends Error {
  constructor(code, message, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export async function loadLocalApiUrl() {
  const stored = await chrome.storage.local.get("localApiUrl");
  return stored.localApiUrl || DEFAULT_API_URL;
}

export async function loadAgencies() {
  const apiUrl = await loadLocalApiUrl();
  const endpoint = new URL("/api/local/agencies", apiUrl);
  const response = await fetch(endpoint, { method: "GET", cache: "no-store" });
  let result = {};
  try {
    result = await response.json();
  } catch (_) {
    result = {};
  }
  if (!response.ok || result.ok === false) {
    throw new Error(result.error || `KOLConnect 请求失败（HTTP ${response.status}）。`);
  }
  return (Array.isArray(result.agencies) ? result.agencies : [])
    .filter((agency) => clean(agency?.agency_id))
    .map((agency) => ({
      agency_id: clean(agency.agency_id),
      name: clean(agency.name) || clean(agency.agency_id)
    }));
}

export async function lookupAccount(platform, profileUrl) {
  const cleanPlatform = clean(platform);
  const cleanProfileUrl = clean(profileUrl);
  if (!cleanPlatform || !cleanProfileUrl) return { state: "INVALID_REQUEST" };

  const apiUrl = await loadLocalApiUrl();
  const endpoint = new URL("/api/extension/accounts/lookup", apiUrl);
  endpoint.searchParams.set("platform", cleanPlatform);
  endpoint.searchParams.set("profile_url", cleanProfileUrl);
  let response;
  try {
    response = await fetch(endpoint, { method: "GET", cache: "no-store" });
  } catch (_) {
    throw new LocalApiError("APP_OFFLINE", "KOLConnect 未运行。");
  }
  let result = {};
  try {
    result = await response.json();
  } catch (_) {}
  if (!response.ok || result.ok === false) {
    throw new LocalApiError("LOOKUP_FAILED", result.error || `KOLConnect 请求失败（HTTP ${response.status}）。`);
  }
  const state = clean(result.state);
  if (!new Set(["ACCOUNT_NOT_FOUND", "ACCOUNT_EXISTS", "AMBIGUOUS", "INVALID_REQUEST"]).has(state)) {
    throw new LocalApiError("LOOKUP_FAILED", "KOLConnect 返回了无效的账号查询结果。");
  }
  return {
    state,
    creator: result.creator && typeof result.creator === "object" ? result.creator : null,
    account: result.account && typeof result.account === "object" ? result.account : null,
    linked_accounts: Array.isArray(result.linked_accounts) ? result.linked_accounts : []
  };
}

export async function searchCreators(query = "", page = 1) {
  const apiUrl = await loadLocalApiUrl();
  const endpoint = new URL("/api/creator-library", apiUrl);
  endpoint.searchParams.set("search", clean(query));
  endpoint.searchParams.set("page", String(page));
  endpoint.searchParams.set("page_size", "12");
  let response;
  try {
    response = await fetch(endpoint, { method: "GET", cache: "no-store" });
  } catch (_) {
    throw new LocalApiError("APP_OFFLINE", "KOLConnect 未运行。");
  }
  let result = {};
  try { result = await response.json(); } catch (_) {}
  if (!response.ok || result.ok !== true || !Array.isArray(result.creators)) {
    throw new LocalApiError("CREATOR_SEARCH_FAILED", "达人搜索暂不可用。", response.status);
  }
  return {
    creators: result.creators.filter((row) => clean(row?.creator_id)).map((row) => ({
      creator_id: clean(row.creator_id),
      creator_name: clean(row.creator_name),
      account_count: Number.isFinite(Number(row.account_count)) ? Number(row.account_count) : null,
      profile_url: clean(row.profile_url)
    })),
    page: Number(result.page) || page,
    pages: Number(result.pages) || 0
  };
}

export async function linkExistingCreator(creatorId, platform, profileUrl) {
  if (!clean(creatorId) || !clean(platform) || !clean(profileUrl)) {
    throw new LocalApiError("VALIDATION_ERROR", "缺少明确的达人或账号身份。", 422);
  }
  const apiUrl = await loadLocalApiUrl();
  const endpoint = new URL("/api/extension/accounts/link-existing-creator", apiUrl);
  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "LINK_EXISTING_CREATOR", creator_id: clean(creatorId),
        platform: clean(platform), profile_url: clean(profileUrl)
      })
    });
  } catch (_) {
    throw new LocalApiError("APP_OFFLINE", "KOLConnect 未运行。");
  }
  let result = {};
  try { result = await response.json(); } catch (_) {}
  if (!response.ok || result.ok !== true) {
    const error = result.error && typeof result.error === "object" ? result.error : {};
    throw new LocalApiError(clean(error.code) || "LINK_FAILED", "账号关联未完成。", response.status);
  }
  if (result.action !== "LINK_EXISTING_CREATOR" || !clean(result.creator_id) || !clean(result.account_uid)) {
    throw new LocalApiError("INVALID_RESPONSE", "账号关联结果无法核实。", response.status);
  }
  return result;
}

function buildVideoImportItem(video = {}, capturedAt = "") {
  const item = {
    platform: video.platform || "",
    content_type: video.content_type || "",
    video_id: video.video_id || "",
    video_url: video.video_url || "",
    title: video.title || null,
    is_pinned: Boolean(video.is_pinned),
    views: video.views?.value ?? null,
    likes: video.likes?.value ?? null,
    comments: video.comments?.value ?? null,
    published_at: video.published_at?.value ?? null,
    engagement_rate: video.engagement_rate?.value ?? null,
    captured_at: capturedAt,
    ...(video.capture_layer ? {
      capture_layer: video.capture_layer,
      observed_at: video.observed_at,
    } : {})
  };
  const metricFields = ["views", "likes", "comments", "shares", "published_at", "engagement_rate"];
  const fieldProvenance = { ...(video.field_provenance || {}) };
  for (const field of metricFields) {
    const state = video[field];
    if (!state || typeof state !== "object") continue;
    fieldProvenance[field] ||= {
      source: state.source || "",
      confidence: state.confidence || (state.value == null ? "missing" : ""),
      missing_reason: state.missing_reason || "",
      ...(state.raw_text !== undefined ? { raw_text: state.raw_text } : {}),
      ...(state.is_estimated !== undefined ? { is_estimated: Boolean(state.is_estimated) } : {})
    };
  }
  if (Object.keys(fieldProvenance).length) item.field_provenance = fieldProvenance;
  if (video.shares && typeof video.shares === "object") item.shares = video.shares.value ?? null;
  return item;
}

const MUTATION_ACTIONS = new Set(["ADD", "UPDATE"]);
const MUTATION_FIELD_NAMES = [...PROFILE_FIELD_NAMES, "content_category"];

function cloneFieldState(field) {
  if (!field || typeof field !== "object") return null;
  return {
    ...(Object.prototype.hasOwnProperty.call(field, "value") ? { value: field.value } : {}),
    source: clean(field.source),
    confidence: clean(field.confidence),
    missing_reason: clean(field.missing_reason)
  };
}

function mutationFields(profile) {
  const source = profile.fields && typeof profile.fields === "object" ? profile.fields : {};
  return Object.fromEntries(MUTATION_FIELD_NAMES.flatMap((name) => {
    const state = cloneFieldState(source[name]);
    return state ? [[name, state]] : [];
  }));
}

function fieldValue(profile, fields, name) {
  if (fields[name] && Object.prototype.hasOwnProperty.call(fields[name], "value")) {
    return fields[name].value;
  }
  return Object.prototype.hasOwnProperty.call(profile, name) ? profile[name] : undefined;
}

function assignPresent(target, name, value) {
  if (value !== undefined) target[name] = value;
}

export function buildMutationPayload(action, profile = {}, now = new Date()) {
  if (!MUTATION_ACTIONS.has(action)) {
    throw new LocalApiError("EXPLICIT_ACTION_REQUIRED", "必须明确指定 ADD 或 UPDATE 操作。", 422);
  }
  const capturedAt = now.toISOString();
  const fields = mutationFields(profile);
  const creator = { fields };
  for (const name of PROFILE_FIELD_NAMES) {
    assignPresent(creator, name, fieldValue(profile, fields, name));
  }
  assignPresent(creator, "platform", profile.platform);
  assignPresent(creator, "profile_url", fieldValue(profile, fields, "profile_url"));
  assignPresent(creator, "username", fieldValue(profile, fields, "username"));
  assignPresent(creator, "language_source", fields.language?.source || profile.language_source);
  assignPresent(creator, "agency_id", profile.agency_id);
  return {
    action,
    task_name: `Extension import ${now.toISOString().slice(0, 10)}`,
    creator,
    videos: Array.isArray(profile.videos)
      ? profile.videos.map((video) => buildVideoImportItem(video, capturedAt))
      : [],
    video_analysis: profile.video_analysis && typeof profile.video_analysis === "object"
      ? profile.video_analysis
      : {},
    creator_insight: {},
    content_category: fieldValue(profile, fields, "content_category"),
    note: profile.note ?? "",
    analysis: profile.analysis && typeof profile.analysis === "object"
      ? profile.analysis
      : {
          capture_status: profile.capture_status || "",
          analysis_url: profile.analysis_url || profile.profile_url || ""
        }
  };
}

export function validateMutationProfile(action, profile = {}) {
  if (!MUTATION_ACTIONS.has(action)) return ["明确操作"];
  const missing = [];
  if (!profile.platform) missing.push("平台");
  if (!profile.profile_url) missing.push("主页链接");
  if (!profile.username) missing.push("用户名");
  if (
    action === "ADD"
    &&
    profile.platform
    && profile.profile_url
    && profile.username
    && !CONTENT_CATEGORY_OPTIONS.includes(clean(profile.content_category))
  ) {
    missing.push("Content Category");
  }
  return missing;
}

async function mutateAccount(action, profile) {
  const missing = validateMutationProfile(action, profile);
  if (missing.length) throw new LocalApiError("VALIDATION_ERROR", `无法执行操作：缺少${missing.join("、")}。`, 422);
  const apiUrl = await loadLocalApiUrl();
  const endpoint = new URL("/api/extension/import", apiUrl);
  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildMutationPayload(action, profile))
    });
  } catch (_) {
    throw new LocalApiError("APP_OFFLINE", "KOLConnect 未运行。", 0);
  }
  let result = {};
  try {
    result = await response.json();
  } catch (_) {
    result = {};
  }
  if (!response.ok || result.ok === false) {
    const structured = result.error && typeof result.error === "object" ? result.error : null;
    const code = clean(structured?.code || result.code) || `HTTP_${response.status}`;
    const message = clean(structured?.message || result.message || (typeof result.error === "string" ? result.error : ""))
      || `KOLConnect 请求失败（HTTP ${response.status}）。`;
    throw new LocalApiError(code, message, response.status);
  }
  return result;
}

export function addAccount(profile) {
  return mutateAccount("ADD", profile);
}

export function updateAccount(profile) {
  return mutateAccount("UPDATE", profile);
}
