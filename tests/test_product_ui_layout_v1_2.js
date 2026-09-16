const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const html = read("webapp/index.html");
const css = read("webapp/styles.css");
const app = read("webapp/app.js");
const agencies = read("webapp/pages/agencies.js");
const library = read("webapp/pages/creator-library.js");

assert.match(css, /review-table th:first-child[\s\S]*white-space: nowrap/);
assert.match(css, /review-table td:nth-child\(2\).*min-width: 220px/);
assert.match(css, /review-table td:nth-child\(2\) a[\s\S]*text-overflow: ellipsis/);
assert.match(css, /page\[data-page="mail"\][\s\S]*max-width: 100%/);
assert.match(css, /mail-message-snippet[\s\S]*overflow-wrap: anywhere/);
assert.match(html, /开始日期/);
assert.match(html, /结束日期/);
assert.match(html, /应用筛选/);
assert.match(css, /campaign-filter-grid[\s\S]*minmax\(170px/);
assert.match(app, /capturePanel\.after\(emailPanel\)/);
assert.match(html, /id="email-enrichment-card"/);
assert.match(html, /creator-library-more-filters/);
assert.match(library, /more-filters-open/);
assert.match(css, /creator-library-secondary-filter \{ display: none/);
assert.match(html, /id="agency-detail-edit"/);
assert.match(agencies, /\/api\/local\/agencies/);
assert.match(agencies, /setEditFormVisible/);
assert.match(html, /agency-related-table/);
assert.match(css, /\.agency-related-table\s*\{[\s\S]*min-width:\s*0[\s\S]*table-layout:\s*fixed/);
assert.match(css, /\.agency-related-table\s*\{[\s\S]*min-width:\s*680px/);

console.log("Product UI Layout V1.2: OK");
