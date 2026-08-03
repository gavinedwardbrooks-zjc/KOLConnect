const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function runLifecycleIntegration() {
  const result = spawnSync(
    process.execPath,
    [path.join(__dirname, "test_phase3_11_3_creator_library_lifecycle.js")],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

function verifyIntegrationContract() {
  const listSource = read("webapp/pages/creator-library.js");
  const detailSource = read("webapp/pages/creator-library-detail.js");
  const appSource = read("webapp/app.js");
  const html = read("webapp/index.html");

  assert.match(listSource, /KOLConnectCreatorCampaignModal/);
  assert.match(listSource, /\/api\/campaigns\/\$\{encodeURIComponent\(campaignId\)\}\/creators/);
  assert.match(listSource, /creator_id:\s*creator\.creator_id,\s*account_id:\s*accountId/);
  assert.doesNotMatch(listSource, /@command:creators/);
  assert.match(detailSource, /\/api\/campaigns\?creator_id=/);
  assert.match(detailSource, /navigate\("campaign-detail",\s*\{ campaignId \}\)/);
  assert.doesNotMatch(appSource, /creator-campaign-modal|creator-library-detail-add-campaign/);
  assert.match(html, /id="creator-campaign-modal"/);
  assert.match(html, /id="creator-campaigns-body"/);
}

runLifecycleIntegration();
verifyIntegrationContract();
console.log("Phase 3.11.5 Creator Campaign integration UI: OK");
