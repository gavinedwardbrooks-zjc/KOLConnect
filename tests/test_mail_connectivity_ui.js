const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "webapp", "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "webapp", "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "webapp", "styles.css"), "utf8");

assert.match(app, /qq:\s*\{[\s\S]*?imap\.qq\.com[\s\S]*?smtp\.qq\.com/);
assert.match(app, /netease126:\s*\{[\s\S]*?imap\.126\.com[\s\S]*?smtp\.126\.com/);
assert.match(app, /aliyun:\s*\{[\s\S]*?imap\.qiye\.aliyun\.com[\s\S]*?smtp\.qiye\.aliyun\.com/);
assert.match(app, /if \(!result\?\.usable\)[\s\S]*?updateMailAccountStatus\(card, "failed"\)/);
assert.match(app, /if \(smtp\.status === "fail"\)[\s\S]*?updateMailAccountStatus\(card, "warning"\)/);
assert.match(app, /button\.disabled = true[\s\S]*?finally[\s\S]*?button\.disabled = false/);
assert.match(app, /mailTestSmtpWarning: "收件同步可用；SMTP 验证失败，不影响当前邮件同步/);
assert.match(html, /IMAP 用于邮件同步，必须可用；SMTP 仅作提示/);
assert.match(css, /\.status-pill\[data-status="warning"\]/);
assert.match(css, /\.mail-test-result\[data-status="failed"\]/);

console.log("mail connectivity UI contract tests passed");
