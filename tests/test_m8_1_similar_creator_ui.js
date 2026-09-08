"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const detail = fs.readFileSync(
  path.join(root, "webapp", "pages", "creator-library-detail.js"),
  "utf8",
);

assert.match(html, /id="creator-library-detail-similar"/);
assert.match(html, /id="creator-library-similar-results"/);
assert.match(detail, /\/api\/creator-library\/\$\{encodeURIComponent\(creatorId\)\}\/similar/);
assert.match(detail, /textContent = String\(candidate\?\.creator_name/);
assert.match(detail, /dataset\.similarCreatorId/);
assert.match(detail, /pageContext\.navigate\("creator-library-detail", \{ creatorId: candidateId \}\)/);
assert.doesNotMatch(detail, /weighted_similarity|相似度评分\s*[:=]\s*\d/);

console.log("M8.1 similar Creator UI: OK");
