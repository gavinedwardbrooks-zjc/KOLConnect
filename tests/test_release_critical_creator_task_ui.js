"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const detail = fs.readFileSync(path.join(root, "webapp", "pages", "creator-library-detail.js"), "utf8");
const library = fs.readFileSync(path.join(root, "webapp", "pages", "creator-library.js"), "utf8");
const handler = fs.readFileSync(path.join(root, "app", "http_handlers", "creator_handler.py"), "utf8");

// Campaign membership is the only user-facing cooperation action. The legacy
// review-task endpoint stays available for compatibility, but is not reachable
// from Creator Library or Creator Detail.
assert.match(html, /id="creator-library-detail-add-campaign"/);
assert.doesNotMatch(html, /id="creator-library-detail-task"/);
assert.doesNotMatch(detail, /openCollaborationTask|\/create-task|navigate\("review"\)/);
assert.match(library, /creatorLibraryChooseCampaign/);
assert.doesNotMatch(library, /openCollaborationTask|\/create-task|creatorLibraryCreateTask/);
assert.match(handler, /\/api\/creator-library\/\(\[\^\/\]\+\)\/create-task/);

console.log("Creator cooperation action contract: OK");
