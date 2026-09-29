"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "webapp", "app.js"), "utf8");
const i18n = fs.readFileSync(path.join(root, "webapp", "i18n.js"), "utf8");

assert.match(app, /data-role="gmail-auth-hint"/);
assert.match(app, /gmailHint\.hidden = provider !== "gmail"/);
assert.match(app, /mailGmailPasswordHint/);
assert.match(app, /apiServerUnreachable/);
assert.match(app, /apiServerError/);
assert.match(i18n, /apiServerUnreachable:/);
assert.match(i18n, /apiServerError:/);
assert.match(i18n, /mailGmailPasswordHint:/);

console.log("Targeted Gate B mail and API i18n UI contract: OK");
