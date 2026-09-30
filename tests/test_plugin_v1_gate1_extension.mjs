import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const localApiUrl = new URL("../chrome_extension/services/local_api.js", import.meta.url);
const instagramUrl = new URL("../chrome_extension/platform/instagram.js", import.meta.url);

const originalChrome = globalThis.chrome;
const originalFetch = globalThis.fetch;
const originalLocation = globalThis.location;
globalThis.chrome = { storage: { local: { get: async () => ({}) } } };

const { LocalApiError, lookupAccount } = await import(localApiUrl);
let requestedUrl = "";
globalThis.fetch = async (url, options) => {
  requestedUrl = String(url);
  assert.equal(options.method, "GET");
  return {
    ok: true,
    json: async () => ({
      ok: true,
      state: "ACCOUNT_EXISTS",
      creator: { display_name: "Creator" },
      account: { platform: "TikTok", profile_url: "https://www.tiktok.com/@creator", handle: "creator", updated_at: null },
      linked_accounts: [{ platform: "YouTube", profile_url: "https://www.youtube.com/@creator", handle: "creator" }]
    })
  };
};
const lookup = await lookupAccount("TikTok", "https://www.tiktok.com/@creator?unsafe=value");
assert.equal(lookup.state, "ACCOUNT_EXISTS");
assert.match(requestedUrl, /platform=TikTok/);
assert.match(requestedUrl, /profile_url=https%3A%2F%2Fwww\.tiktok\.com%2F%40creator%3Funsafe%3Dvalue/);
assert.deepEqual(await lookupAccount("", ""), { state: "INVALID_REQUEST" });
globalThis.fetch = async () => { throw new Error("offline"); };
await assert.rejects(
  () => lookupAccount("TikTok", "https://www.tiktok.com/@creator"),
  (error) => error instanceof LocalApiError && error.code === "APP_OFFLINE"
);

globalThis.location = { href: "https://www.instagram.com/@CreatorName/" };
globalThis.fetch = async () => ({
  ok: true,
  status: 200,
  json: async () => ({ data: { user: { username: "creatorname", id: "1" } } })
});
const Instagram = await import(instagramUrl);
assert.equal(Instagram.normalizeInstagramIdentity(" @CreatorName "), "creatorname");
assert.equal((await Instagram.fetchInstagramWebProfilePage("fixture")).ok, true);
globalThis.fetch = async () => ({
  ok: true,
  status: 200,
  json: async () => ({ data: { user: { username: "differentcreator", id: "2" } } })
});
const mismatch = await Instagram.fetchInstagramWebProfilePage("fixture");
assert.equal(mismatch.ok, false);
assert.equal(mismatch.reason, "web_profile_info_identity_mismatch");

let fallbackCollectorCalls = 0;
globalThis.chrome = {
  scripting: {
    async executeScript({ func }) {
      if (func.name === "fetchInstagramWebProfilePage") {
        return [{ result: { ok: false, reason: "web_profile_info_identity_mismatch" } }];
      }
      if (func.name === "collectInstagramPage") {
        fallbackCollectorCalls += 1;
        return [{ result: {
          platform: "Instagram",
          analysis_url: "https://www.instagram.com/creatorname/",
          supported: true,
          fields: {
            profile_url: { value: "https://www.instagram.com/creatorname/" },
            username: { value: "@creatorname" },
            creator_name: { value: "Fallback Creator" },
            followers: { value: null }
          },
          bio_candidates: [],
          public_profile: { email_candidates: [], whatsapp_candidates: [], country_candidates: [], language_candidates: [] },
          searched_sources: ["structured_data"],
          errors: []
        } }];
      }
      throw new Error(`Unexpected collector: ${func.name}`);
    }
  }
};
const fallbackProfile = await Instagram.collectProfile(1);
assert.equal(fallbackCollectorCalls, 1);
assert.equal(fallbackProfile.fields.creator_name.value, "Fallback Creator");
assert.equal(fallbackProfile.api_fallback_reason, "web_profile_info_identity_mismatch");

const assistantSource = readFileSync(new URL("../chrome_extension/content/floating_assistant.js", import.meta.url), "utf8");
const backgroundSource = readFileSync(new URL("../chrome_extension/background.js", import.meta.url), "utf8");
assert.match(assistantSource, /ACCOUNT_NOT_FOUND/);
assert.match(assistantSource, /ACCOUNT_EXISTS/);
assert.match(assistantSource, /AMBIGUOUS/);
assert.match(assistantSource, /APP_OFFLINE/);
assert.match(assistantSource, /state\.accountLookup = null/);
assert.match(assistantSource, /MESSAGE\.LOOKUP_ACCOUNT/);
assert.match(backgroundSource, /MESSAGE\.LOOKUP_ACCOUNT/);
assert.match(backgroundSource, /lookupAccount\(platform, profileUrl\)/);

globalThis.chrome = originalChrome;
globalThis.fetch = originalFetch;
globalThis.location = originalLocation;
console.log("Plugin V1 Gate 1 extension tests passed");
