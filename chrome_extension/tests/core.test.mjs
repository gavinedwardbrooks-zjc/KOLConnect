import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { buildDiagnosticReport } from "../core/diagnostics.js";
import { normalizeFollowerText } from "../core/normalize.js";
import { createField, finalizeProfile } from "../core/schema.js";
import { matches as matchesInstagram } from "../platform/instagram.js";
import { matches as matchesTikTok } from "../platform/tiktok.js";
import { matches as matchesYouTube } from "../platform/youtube.js";
import { buildImportPayload, validateImportProfile } from "../services/local_api.js";

assert.equal(normalizeFollowerText("1.2K"), "1200");
assert.equal(normalizeFollowerText("3.5M"), "3500000");
assert.equal(normalizeFollowerText("1,234"), "1234");
assert.equal(normalizeFollowerText("1.234"), "1234");
assert.equal(normalizeFollowerText("1,2 mil"), "1200");
assert.equal(normalizeFollowerText("1,2 mi"), "1200000");
assert.equal(normalizeFollowerText("350 mil"), "350000");

assert.equal(matchesTikTok("https://www.tiktok.com/@creator"), true);
assert.equal(matchesInstagram("https://instagram.com/creator/"), true);
assert.equal(matchesYouTube("https://www.youtube.com/@creator/shorts"), true);
assert.equal(matchesTikTok("https://www.youtube.com/@creator"), false);

const partialProfile = finalizeProfile({
  platform: "TikTok",
  analysis_url: "https://www.tiktok.com/@creator?token=private#section",
  supported: true,
  fields: {
    profile_url: createField("https://www.tiktok.com/@creator", "url", "high"),
    username: createField("@creator", "url", "high"),
    creator_name: createField(null, "", "missing", "Creator name was not exposed by the current public page."),
    followers: createField("1.2K", "page_dom", "high"),
    bio: createField("Gaming creator", "page_dom", "medium")
  },
  searched_sources: ["page_dom", "url"],
  errors: []
});
partialProfile.content_category = "Gaming";
assert.equal(partialProfile.capture_status, "partial_success");
assert.equal(partialProfile.creator_name, null);
assert.equal(partialProfile.fields.creator_name.confidence, "missing");

const report = buildDiagnosticReport(partialProfile);
const reportText = JSON.stringify(report);
assert.equal(report.analysis_url, "https://www.tiktok.com/@creator");
assert.equal(report.profile_fields.creator_name.has_value, false);
assert.equal(report.profile_fields.bio.character_count, "Gaming creator".length);
const whitespaceNameReport = buildDiagnosticReport({
  fields: {
    creator_name: {
      value: "   ",
      source: "test",
      confidence: "high",
      missing_reason: ""
    }
  }
});
assert.equal(whitespaceNameReport.profile_fields.creator_name.has_value, false);
assert.equal(whitespaceNameReport.profile_fields.creator_name.value_preview, "");
for (const forbidden of ["token", "authorization", "cookie", "Gaming creator"]) {
  assert.equal(reportText.toLowerCase().includes(forbidden.toLowerCase()), false);
}

const payload = buildImportPayload(partialProfile, new Date("2026-07-29T00:00:00.000Z"));
assert.deepEqual(Object.keys(payload), [
  "task_name",
  "creator",
  "videos",
  "video_analysis",
  "creator_insight",
  "content_category",
  "note",
  "analysis"
]);
assert.deepEqual(Object.keys(payload.creator), [
  "creator_name",
  "platform",
  "profile_url",
  "followers",
  "bio",
  "email",
  "whatsapp",
  "country",
  "language",
  "language_source"
]);
assert.equal(payload.creator.creator_name, "@creator");
assert.deepEqual(payload.videos, []);
assert.deepEqual(validateImportProfile(partialProfile), []);
assert.deepEqual(validateImportProfile({ platform: "TikTok" }), ["主页链接", "用户名"]);

const manifest = JSON.parse(readFileSync(new URL("../manifest.json", import.meta.url), "utf8"));
assert.equal(manifest.manifest_version, 3);
assert.equal(manifest.version, "0.2.3");
assert.equal(manifest.version_name, "KOLConnect v0.2.3");
const runtimeFiles = JSON.stringify(manifest);
for (const forbidden of ["popup", "sidepanel", "interceptor", "bridge"]) {
  assert.equal(runtimeFiles.toLowerCase().includes(forbidden), false);
}

console.log("Core, schema, diagnostics, URL matching, and import compatibility tests passed.");
