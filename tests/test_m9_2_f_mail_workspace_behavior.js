"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.resolve(__dirname, "../webapp/pages/mail-workspace.js"), "utf8");

class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = "";
    this.checked = false;
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.listeners = new Map();
    this.options = [];
  }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
  querySelectorAll() { return []; }
  replaceChildren(...items) {
    this.options = [...items];
    this.value = items[0]?.value || "";
  }
  add(item) { this.options.push(item); }
  async fire(type) { return this.listeners.get(type)?.({ target: this }); }
}

function createHarness() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, new FakeElement(id));
    return elements.get(id);
  };
  const requests = [];
  const errors = [];
  let templates = [];
  let failCreate = false;
  let aiEnabled = false;
  let nextVersion = 2;
  const api = {
    async get(url) {
      assert.equal(url, "/api/mail/send-security/session");
      return { csrf_token: "csrf" };
    },
    async request(method, url, options = {}) {
      requests.push({ method, url, payload: options.payload });
      if (method === "GET" && url.startsWith("/api/mail/workspace/options")) {
        return {
          mail_accounts: aiEnabled ? [{ mail_account_id: "account-1", name: "Primary", email: "sender@example.com" }] : [],
          creator_contacts: [],
          ai_provider: { enabled: aiEnabled, provider: "openai", model: "test-model" },
        };
      }
      if (method === "GET" && url.startsWith("/api/mail/templates?")) return { templates };
      if (method === "POST" && url === "/api/mail/templates") {
        if (failCreate) throw new Error("create failed");
        const template = {
          ...options.payload,
          template_id: "template-created",
          template_group_id: "group-created",
          template_version: 1,
          template_source: "user",
          active: true,
        };
        templates = [template];
        return { template };
      }
      if (method === "PUT" && url.startsWith("/api/mail/templates/")) {
        const current = templates.find(item => url.endsWith(item.template_id));
        const template = {
          ...current,
          ...options.payload,
          template_id: `template-updated-${nextVersion}`,
          template_version: nextVersion++,
          template_source: "user",
          active: true,
        };
        templates = [template];
        return { template };
      }
      if (method === "POST" && url === "/api/mail/drafts") {
        return { draft: { draft_id: "draft-1", version: 1, subject: options.payload.subject, body_text: options.payload.body_text } };
      }
      if (method === "POST" && url === "/api/mail/ai-draft-candidates") {
        return { candidate: { candidate_id: "candidate-1", status: "ready", subject: "AI subject", body_text: "AI body" } };
      }
      if (method === "POST" && url === "/api/mail/ai-draft-candidates/candidate-1/adopt") {
        return { draft: { draft_id: "draft-1", version: 2, subject: "AI subject", body_text: "AI body" } };
      }
      throw new Error(`unexpected request: ${method} ${url}`);
    },
  };
  const window = {
    KOLConnectAPI: api,
    KOLConnectApp: { t: key => key, showError: error => errors.push(error) },
    confirm: () => true,
    prompt: () => "用户模板",
    addEventListener() {},
    crypto: { randomUUID: () => "00000000-0000-4000-8000-000000000000" },
  };
  const document = { readyState: "complete", getElementById: element };
  window.document = document;
  vm.runInNewContext(source, {
    window,
    document,
    Option: function Option(text, value = "") { this.text = text; this.value = value; },
    console,
    setTimeout,
    clearTimeout,
  });
  element("mail-workspace-language").value = "pt-BR";
  element("mail-workspace-tone").value = "friendly";
  return {
    element,
    requests,
    errors,
    window,
    setTemplates(value) { templates = value; },
    setFailCreate(value) { failCreate = value; },
    setAIEnabled(value) { aiEnabled = value; },
  };
}

async function run() {
  const harness = createHarness();
  await harness.window.KOLConnectMailWorkspace.open({ draftType: "initial_outreach" });
  harness.element("mail-workspace-subject").value = "Hello {{creator_name}}";
  harness.element("mail-workspace-body").value = "Campaign {{campaign_name}} costs 0.";
  await harness.element("mail-workspace-save-template").fire("click");

  assert.deepEqual(harness.errors, [], "create must not raise ReferenceError");
  const create = harness.requests.find(item => item.method === "POST" && item.url === "/api/mail/templates");
  assert.deepEqual(JSON.parse(JSON.stringify(create.payload)), {
    draft_type: "initial_outreach",
    language: "pt-BR",
    name: "用户模板",
    tone: "friendly",
    audience_type: "all",
    subject_template: "Hello {{creator_name}}",
    body_template: "Campaign {{campaign_name}} costs 0.",
    required_variables: ["campaign_name", "creator_name"],
  });
  assert.equal(harness.element("mail-workspace-template").value, "template-created");

  const subjectBeforeFailure = "Keep {{creator_name}}";
  const bodyBeforeFailure = "Keep this user text";
  harness.element("mail-workspace-subject").value = subjectBeforeFailure;
  harness.element("mail-workspace-body").value = bodyBeforeFailure;
  harness.setFailCreate(true);
  await harness.element("mail-workspace-save-template").fire("click");
  assert.equal(harness.errors.at(-1).message, "create failed");
  assert.equal(harness.element("mail-workspace-subject").value, subjectBeforeFailure);
  assert.equal(harness.element("mail-workspace-body").value, bodyBeforeFailure);
  harness.setFailCreate(false);

  harness.element("mail-workspace-template").value = "template-created";
  await harness.element("mail-workspace-template").fire("change");
  harness.element("mail-workspace-subject").value = "Hello {{creator_name}}";
  harness.element("mail-workspace-body").value = "Brand {{brand_name}} costs 0.";
  await harness.element("mail-workspace-update-template").fire("click");
  const update = harness.requests.find(item => item.method === "PUT" && item.url === "/api/mail/templates/template-created");
  assert.deepEqual(Array.from(update.payload.required_variables), ["brand_name", "creator_name"]);
  assert.equal(harness.element("mail-workspace-template").value, "template-updated-2");

  harness.setTemplates([
    { template_id: "tone-professional", template_source: "user", template_version: 1, draft_type: "initial_outreach", language: "pt-BR", tone: "professional", name: "Professional", required_variables: [] },
    { template_id: "tone-friendly", template_source: "user", template_version: 1, draft_type: "initial_outreach", language: "pt-BR", tone: "friendly", name: "Friendly", required_variables: [] },
  ]);
  harness.element("mail-workspace-template-tone").value = "friendly";
  await harness.element("mail-workspace-template-tone").fire("change");
  assert.deepEqual(harness.element("mail-workspace-template").options.map(item => item.value), ["", "tone-friendly"]);

  harness.setTemplates([{
    template_id: "builtin-en-initial",
    template_source: "builtin",
    template_version: 1,
    draft_type: "initial_outreach",
    language: "pt-BR",
    tone: "friendly",
    name: "Built in",
    required_variables: [],
  }]);
  await harness.window.KOLConnectMailWorkspace.open({ draftType: "initial_outreach" });
  harness.element("mail-workspace-template").value = "builtin-en-initial";
  await harness.element("mail-workspace-template").fire("change");
  assert.equal(harness.element("mail-workspace-update-template").disabled, true);

  assert.equal(harness.requests.some(item => item.url.includes("ai-draft") || item.url === "/api/mail/send"), false);

  const aiHarness = createHarness();
  aiHarness.setAIEnabled(true);
  await aiHarness.window.KOLConnectMailWorkspace.open({
    draftType: "initial_outreach", recipientEmail: "creator@example.com", creatorName: "Creator",
  });
  aiHarness.element("mail-workspace-account").value = "account-1";
  aiHarness.element("mail-workspace-recipient").value = "creator@example.com";
  aiHarness.element("mail-workspace-subject").value = "Manual subject";
  aiHarness.element("mail-workspace-body").value = "Manual body";
  aiHarness.element("mail-workspace-ai-consent").checked = true;
  await aiHarness.element("mail-workspace-ai-generate").fire("click");
  assert.equal(aiHarness.errors.length, 0);
  assert.equal(aiHarness.element("mail-workspace-subject").value, "Manual subject", "candidate must not overwrite the draft automatically");
  assert.equal(aiHarness.element("mail-workspace-body").value, "Manual body");
  assert.equal(aiHarness.element("mail-workspace-ai-candidate").hidden, false);
  assert.equal(aiHarness.element("mail-workspace-ai-candidate-body").textContent, "AI body");
  assert.equal(aiHarness.requests.some(item => item.url.endsWith("/adopt")), false);
  await aiHarness.element("mail-workspace-ai-adopt").fire("click");
  assert.equal(aiHarness.element("mail-workspace-subject").value, "AI subject");
  assert.equal(aiHarness.element("mail-workspace-body").value, "AI body");
  assert.equal(aiHarness.requests.filter(item => item.url.endsWith("/adopt")).length, 1);
  assert.equal(aiHarness.requests.some(item => item.url === "/api/mail/send"), false);
  console.log("M9.2-F mail workspace behavioral tests passed");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
