"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");
const html = read("webapp/index.html");
const source = read("webapp/pages/mail-workspace.js");
const followup = read("webapp/pages/mail-follow-up.js");
const detail = read("webapp/pages/creator-library-detail.js");
const styles = read("webapp/styles.css");
const i18n = read("webapp/i18n.js");

assert.match(html, /id="mail-workspace-account"[\s\S]*mailWorkspaceChooseAccount/);
assert.match(html, /id="mail-workspace-recipient"[\s\S]*mailWorkspaceChooseRecipient/);
assert.match(html, /id="mail-workspace-read-body"/);
assert.match(html, /id="mail-workspace-confirm"/);
assert.match(html, /id="mail-workspace-send"[^>]*disabled/);
assert.match(source, /\/api\/mail\/messages\/\$\{encodeURIComponent\(state\.context\.mailMessageId\)\}\/body/);
assert.match(source, /authorization_source:[\s\S]*human_approved_ai_proposal[\s\S]*human_direct/);
assert.match(source, /X-KOLConnect-Mail-CSRF/);
assert.match(source, /state\.generation/);
assert.match(source, /beforeunload/);
assert.doesNotMatch(source, /localStorage|sessionStorage/);
assert.match(followup, /latest_mail_message_id/);
assert.match(followup, /KOLConnectMailWorkspace\.open/);
assert.match(detail, /creator-library-detail-mail[\s\S]*KOLConnectMailWorkspace\.open/);
assert.match(styles, /\.mail-workspace-grid[\s\S]*grid-template-columns/);
assert.match(i18n, /mailWorkspaceOutcome_unknown/);
assert.match(i18n, /不要自动重发/);

console.log("M9.2-D mail workspace UI contract passed");
