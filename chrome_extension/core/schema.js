import {
  normalizeFollowerText,
  normalizeMultilineText,
  normalizeProfileUrl,
  normalizeText,
  safeAnalysisUrl
} from "./normalize.js";

export const EXTENSION_VERSION = "v1.0.0";
export const PROFILE_FIELD_NAMES = Object.freeze([
  "profile_url",
  "username",
  "creator_name",
  "followers",
  "bio",
  "email",
  "whatsapp",
  "country",
  "language"
]);
const DEFAULT_MISSING_REASONS = Object.freeze({
  profile_url: "Creator profile URL was not available.",
  username: "Creator username was not available in the current URL.",
  creator_name: "Creator name was not exposed by the current public page.",
  followers: "Follower or subscriber count was not exposed by the current public page.",
  bio: "Creator bio or channel description was not exposed by the current public page.",
  email: "A public creator email was not exposed by the current page.",
  whatsapp: "A public WhatsApp contact was not exposed by the current page.",
  country: "Creator country was not explicitly exposed by the current page.",
  language: "Creator language was not explicitly exposed by the current page."
});

export function createField(value, source = "", confidence = "missing", missingReason = "") {
  const normalized = normalizeMultilineText(value) || null;
  return {
    value: normalized,
    source: normalized ? normalizeText(source) : normalizeText(source) === "missing" ? "missing" : "",
    confidence: normalized ? confidence : "missing",
    missing_reason: normalized ? "" : normalizeText(missingReason)
  };
}

function normalizeField(name, field) {
  const rawValue = field?.value;
  const value = name === "followers"
    ? normalizeFollowerText(rawValue)
    : name === "profile_url"
      ? normalizeProfileUrl(rawValue)
      : name === "bio"
        ? normalizeMultilineText(rawValue) || null
        : normalizeText(rawValue) || null;
  return createField(
    value,
    field?.source,
    field?.confidence || "medium",
    field?.missing_reason || DEFAULT_MISSING_REASONS[name]
  );
}

export function finalizeProfile(raw = {}) {
  const rawFields = raw.fields || {};
  const fields = Object.fromEntries(PROFILE_FIELD_NAMES.map((name) => [
    name,
    normalizeField(name, rawFields[name])
  ]));
  const hasUsername = Boolean(fields.username.value);
  const hasProfileUrl = Boolean(fields.profile_url.value);
  const optionalCount = ["creator_name", "followers", "bio"]
    .filter((name) => Boolean(fields[name].value)).length;
  const supported = raw.supported !== false && Boolean(raw.platform);
  let captureStatus = "unavailable";
  if (supported && hasProfileUrl && hasUsername && optionalCount === 3) captureStatus = "success";
  else if (supported && hasProfileUrl && hasUsername && optionalCount > 0) captureStatus = "partial_success";

  return {
    extension_version: EXTENSION_VERSION,
    platform: normalizeText(raw.platform),
    analysis_url: safeAnalysisUrl(raw.analysis_url),
    profile_url: fields.profile_url.value,
    username: fields.username.value,
    creator_name: fields.creator_name.value,
    followers: fields.followers.value,
    bio: fields.bio.value,
    email: fields.email.value,
    whatsapp: fields.whatsapp.value,
    country: fields.country.value,
    language: fields.language.value,
    language_source: fields.language.value ? fields.language.source : "",
    fields,
    capture_status: captureStatus,
    searched_sources: Array.isArray(raw.searched_sources)
      ? raw.searched_sources.map(normalizeText).filter(Boolean)
      : [],
    errors: Array.isArray(raw.errors) ? raw.errors.map(normalizeText).filter(Boolean) : []
  };
}

export function failedProfile(platform, analysisUrl, message) {
  const reason = normalizeText(message) || "Profile collection failed.";
  return {
    extension_version: EXTENSION_VERSION,
    platform: normalizeText(platform),
    analysis_url: safeAnalysisUrl(analysisUrl),
    profile_url: null,
    username: null,
    creator_name: null,
    followers: null,
    bio: null,
    fields: Object.fromEntries(PROFILE_FIELD_NAMES.map((name) => [
      name,
      createField(null, "", "missing", reason)
    ])),
    capture_status: "failed",
    searched_sources: [],
    errors: [reason]
  };
}
