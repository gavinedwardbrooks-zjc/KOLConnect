const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const detailSource = fs.readFileSync(
  path.join(root, "webapp", "pages", "creator-library-detail.js"),
  "utf8",
);

assert.match(html, /id="creator-edit-country"/);
assert.match(html, /id="creator-edit-language"/);
assert.match(html, /完善国家和语言信息，可提升达人分析准确度/);
assert.match(detailSource, /setValue\("creator-edit-country", record\.country \|\| creator\.country\)/);
assert.match(detailSource, /setValue\("creator-edit-language", record\.language \|\| creator\.language\)/);
assert.match(detailSource, /country: valueOf\("creator-edit-country"\)\.trim\(\)/);
assert.match(detailSource, /language: valueOf\("creator-edit-language"\)\.trim\(\)/);

console.log("M3.0 P1 Creator metadata edit UI: OK");
