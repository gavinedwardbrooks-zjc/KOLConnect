"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const elements = new Map([
  ["mail-template-subject", { value: "Subject T2" }],
  ["mail-template-body", { value: "Body T2" }],
]);
const accountCard = {
  querySelector(selector) {
    const values = {
      '[data-key="name"]': { value: "Account B" },
      '[data-key="provider"]': { value: "custom" },
      '[data-key="email"]': { value: "b@example.com" },
      '[data-key="sender_name"]': { value: "Sender B" },
      '[data-key="imap_host"]': { value: "imap.example.com" },
      '[data-key="imap_port"]': { value: "993" },
      '[data-key="smtp_host"]': { value: "smtp.example.com" },
      '[data-key="smtp_port"]': { value: "465" },
      '[data-key="username"]': { value: "b@example.com" },
      '[data-key="password"]': { value: "secret-b" },
      '[data-key="enabled"]': { checked: true },
    };
    return values[selector] || null;
  },
};
const posts = [];
const sandbox = {
  console,
  document: {
    getElementById: id => elements.get(id) || null,
    querySelectorAll: selector => selector === "#mail-accounts-list .mail-account-card" ? [accountCard] : [],
    createElement: () => ({ classList: { toggle() {} } }),
  },
  window: {
    alert() {},
    addEventListener() {},
    localStorage: { getItem: () => "", setItem() {}, removeItem() {} },
    KOLConnectAPI: {
      post: async (url, payload) => {
        posts.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
        return { ok: true };
      },
      get: async url => url === "/api/mail/inbox/messages"
        ? { messages: [], summary: {} }
        : { ui: {}, profiles: [], accounts: [], feishu: {}, creator_library: {}, mail: {} },
    },
  },
};
sandbox.globalThis = sandbox;

const appPath = path.join(__dirname, "..", "webapp", "app.js");
const source = `${fs.readFileSync(appPath, "utf8")}
globalThis.__mailPartialUpdateTest = { saveMailTemplate, saveMailAccounts };`;
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: appPath });

async function run() {
  await sandbox.__mailPartialUpdateTest.saveMailTemplate();
  assert.deepEqual(posts[0], {
    url: "/api/settings/mail",
    payload: { template_subject: "Subject T2", template_body: "Body T2" },
  });
  assert.equal(Object.hasOwn(posts[0].payload, "accounts"), false);

  await sandbox.__mailPartialUpdateTest.saveMailAccounts();
  assert.equal(posts[1].url, "/api/settings/mail");
  assert.equal(Array.isArray(posts[1].payload.accounts), true);
  assert.equal(posts[1].payload.accounts[0].name, "Account B");
  assert.equal(Object.hasOwn(posts[1].payload, "template_subject"), false);
  assert.equal(Object.hasOwn(posts[1].payload, "template_body"), false);
  console.log("M4.8 mail partial update payload tests passed");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
