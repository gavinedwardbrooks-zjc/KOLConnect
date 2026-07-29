import { EXTENSION_VERSION } from "./schema.js";
import { safeAnalysisUrl } from "./normalize.js";

const DIAGNOSTIC_FIELDS = ["username", "creator_name", "followers", "bio"];

export function buildDiagnosticReport(profile = {}) {
  const profileFields = Object.fromEntries(DIAGNOSTIC_FIELDS.map((name) => {
    const field = profile.fields?.[name] || {};
    const hasValue = typeof field.value === "string" && field.value.trim().length > 0;
    const diagnostic = {
      has_value: hasValue,
      source: field.source || "",
      confidence: field.confidence || "missing",
      missing_reason: field.missing_reason || ""
    };
    if (name === "creator_name") {
      diagnostic.value_preview = hasValue ? field.value.trim().slice(0, 120) : "";
    }
    if (name === "bio") {
      diagnostic.character_count = String(field.value || "").length;
    }
    return [name, diagnostic];
  }));
  return {
    extension_version: EXTENSION_VERSION,
    platform: profile.platform || "",
    analysis_url: safeAnalysisUrl(profile.analysis_url),
    capture_status: profile.capture_status || "failed",
    profile_capture_status: profile.capture_status || "failed",
    profile_fields: profileFields,
    searched_sources: Array.isArray(profile.searched_sources) ? profile.searched_sources : [],
    errors: Array.isArray(profile.errors) ? profile.errors : []
  };
}
