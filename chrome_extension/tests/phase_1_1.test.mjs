import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

import { selectBio } from "../platform/common.js";

const context = vm.createContext({
  clearTimeout,
  setTimeout,
  Date
});
context.globalThis = context;
const sessionSource = readFileSync(new URL("../core/analysis_session.js", import.meta.url), "utf8");
vm.runInContext(sessionSource, context);
const SessionController = context.KOLConnectAnalysisSessionController;

const sessions = new SessionController(25);
const sessionA = sessions.begin();
const sessionB = sessions.begin();
const sessionC = sessions.begin();
assert.equal(sessions.isCurrent(sessionA), false);
assert.equal(sessions.isCurrent(sessionB), false);
assert.equal(sessions.isCurrent(sessionC), true);

let resolveOldResult;
const oldResult = new Promise((resolve) => {
  resolveOldResult = resolve;
});
const oldSession = sessions.begin();
const newSession = sessions.begin();
resolveOldResult({ session_id: oldSession });
const delayedResult = await oldResult;
assert.equal(sessions.isCurrent(delayedResult.session_id), false);
assert.equal(sessions.isCurrent(newSession), true);

await assert.rejects(
  sessions.waitFor(new Promise(() => {}), sessions.begin()),
  (error) => error.name === "AnalysisTimeoutError"
);

const instagramBio = selectBio([
  {
    source: "profile_dom",
    value: [
      "Digital creator",
      "+ de 15M de seguidores nas redes sociais",
      "publicidades: email@example.com",
      "links premio ibest"
    ].join("\n")
  }
], {
  platform: "instagram",
  username: "@maria",
  creatorName: "Maria"
});
assert.equal(
  instagramBio.value,
  "Digital creator\n+ de 15M de seguidores nas redes sociais\npublicidades: email@example.com\nlinks premio ibest"
);

const instagramMeta = selectBio([
  {
    source: "meta",
    value: "1M Followers, 500 Following, 100 Posts - Beauty creator\ncontact@example.com"
  }
], {
  platform: "instagram",
  username: "@beauty",
  creatorName: "Beauty"
});
assert.equal(instagramMeta.value, "Beauty creator\ncontact@example.com");
assert.equal(instagramMeta.source, "meta");

const invalidYouTubeBio = selectBio([
  { source: "profile_dom", value: "v, sz" }
], {
  platform: "youtube",
  username: "@channel",
  creatorName: "Channel"
});
assert.equal(invalidYouTubeBio.value, null);
assert.equal(invalidYouTubeBio.source, "missing");
assert.equal(
  invalidYouTubeBio.missing_reason,
  "The current YouTube channel page did not expose a public description."
);

const tiktokBio = selectBio([
  {
    source: "structured_data",
    value: "Gaming creator\nBusiness: creator@example.com"
  }
], {
  platform: "tiktok",
  username: "@gamer",
  creatorName: "Gamer"
});
assert.equal(tiktokBio.value, "Gaming creator\nBusiness: creator@example.com");
assert.equal(tiktokBio.source, "structured_data");

console.log("Phase 1.1 session lifecycle, timeout, and bio normalization tests passed.");
