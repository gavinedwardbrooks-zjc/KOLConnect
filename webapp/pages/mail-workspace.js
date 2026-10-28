(function createMailWorkspace(global) {
  "use strict";

  const $ = id => document.getElementById(id);
  const state = { generation: 0, csrf: "", context: null, options: null, templates: [], draft: null, preview: null, authorization: null, dirty: false, busy: false };
  const t = (key, values) => global.KOLConnectApp?.t?.(key, values) || key;

  async function session() {
    const data = await global.KOLConnectAPI.get("/api/mail/send-security/session");
    state.csrf = data.csrf_token;
  }

  function secure(method, url, payload, signal) {
    const options = { signal, headers: { "X-KOLConnect-Mail-CSRF": state.csrf } };
    if (method !== "GET") options.payload = payload;
    return global.KOLConnectAPI.request(method, url, options);
  }

  function setStatus(value) { $("mail-workspace-status").textContent = String(value || ""); }
  function setBusy(value) {
    state.busy = value;
    $("mail-workspace-modal").querySelectorAll("button,select,input,textarea").forEach(node => {
      node.disabled = value;
    });
    if (!value) {
      $("mail-workspace-send").disabled = !state.preview || !$("mail-workspace-confirm").checked;
      updateTemplateActions();
    }
  }

  function account() {
    return state.options?.mail_accounts?.find(item => item.mail_account_id === $("mail-workspace-account").value);
  }

  function draftType() { return state.context?.draftType || "initial_outreach"; }

  function resetTransient() {
    state.preview = null;
    state.authorization = null;
    $("mail-workspace-preview").hidden = true;
    $("mail-workspace-confirm").checked = false;
    $("mail-workspace-send").disabled = true;
  }

  function markDirty() {
    state.dirty = true;
    resetTransient();
  }

  function populateOptions() {
    const accountSelect = $("mail-workspace-account");
    accountSelect.replaceChildren(new Option(t("mailWorkspaceChooseAccount"), ""));
    (state.options.mail_accounts || []).forEach(item => accountSelect.add(new Option(`${item.name} · ${item.email}`, item.mail_account_id)));
    const recipientSelect = $("mail-workspace-recipient");
    recipientSelect.replaceChildren(new Option(t("mailWorkspaceChooseRecipient"), ""));
    const seen = new Set();
    (state.options.creator_contacts || []).forEach(item => {
      const email = String(item.account_email || "").trim().toLowerCase();
      if (!email || seen.has(email)) return;
      seen.add(email);
      recipientSelect.add(new Option(`${email} · ${item.platform || "--"} ${item.username || ""}`, email));
    });
    const contextEmail = String(state.context.recipientEmail || "").trim().toLowerCase();
    if (contextEmail && !seen.has(contextEmail)) recipientSelect.add(new Option(`${contextEmail} · ${t("mailWorkspaceObservedEmail")}`, contextEmail));
    const ai = state.options.ai_provider || {};
    $("mail-workspace-ai-provider").textContent = ai.enabled
      ? t("mailWorkspaceAIProvider", { provider: ai.provider, model: ai.model })
      : t("mailWorkspaceAIDisabled");
    $("mail-workspace-ai-generate").hidden = !ai.enabled;
  }

  async function loadTemplates(generation) {
    const language = $("mail-workspace-language").value.trim().toLowerCase();
    const tone = $("mail-workspace-template-tone").value.trim().toLowerCase();
    const data = await secure("GET", `/api/mail/templates?draft_type=${encodeURIComponent(draftType())}`, undefined);
    if (generation !== state.generation) return;
    state.templates = (data.templates || []).filter(item => (!language || String(item.language).toLowerCase() === language)
      && (!tone || String(item.tone).toLowerCase() === tone));
    const select = $("mail-workspace-template");
    select.replaceChildren(new Option(t("mailWorkspaceChooseTemplate"), ""));
    state.templates.forEach(item => select.add(new Option(`${item.name} · ${item.language} · ${item.tone}`, item.template_id)));
    updateTemplateActions();
  }

  function selectedTemplate() { return state.templates.find(item => item.template_id === $("mail-workspace-template").value); }
  function requiredTemplateVariables(...values) {
    const names = new Set();
    const pattern = /{{\s*([a-z][a-z0-9_]*)\s*}}/g;
    values.forEach(value => {
      for (const match of String(value || "").matchAll(pattern)) names.add(match[1]);
    });
    return Array.from(names).sort();
  }
  function selectTemplate(template) {
    if (!template) return;
    $("mail-workspace-template-tone").value = template.tone || "";
    return loadTemplates(state.generation).then(() => {
      if (state.templates.some(item => item.template_id === template.template_id)) {
        $("mail-workspace-template").value = template.template_id;
      }
      updateTemplateActions();
    });
  }
  function updateTemplateActions() {
    const selected = selectedTemplate();
    const editable = selected?.template_source === "user";
    $("mail-workspace-update-template").disabled = !editable || state.busy;
    $("mail-workspace-deactivate-template").disabled = !editable || state.busy;
  }

  async function open(context = {}) {
    state.generation += 1;
    const generation = state.generation;
    state.context = { ...context };
    state.dirty = false;
    state.draft = null;
    state.preview = null;
    state.authorization = null;
    $("mail-workspace-modal").hidden = false;
    $("mail-workspace-context").textContent = context.creatorName || context.recipientEmail || t("mailWorkspaceNewMessage");
    $("mail-workspace-subject").value = context.subject ? `Re: ${context.subject}` : "";
    $("mail-workspace-body").value = "";
    $("mail-workspace-source").hidden = true;
    $("mail-workspace-source-body").textContent = "";
    $("mail-workspace-read-body").hidden = !context.mailMessageId;
    resetTransient();
    setStatus(t("mailWorkspaceLoading"));
    try {
      await session();
      const data = await secure("GET", `/api/mail/workspace/options?creator_id=${encodeURIComponent(context.creatorId || "")}`, undefined);
      if (generation !== state.generation) return;
      state.options = data;
      populateOptions();
      await loadTemplates(generation);
      setStatus(t("mailWorkspaceReady"));
    } catch (error) {
      if (generation === state.generation) global.KOLConnectApp.showError(error);
    }
  }

  function close() {
    if (state.dirty && !global.confirm(t("mailWorkspaceDiscardConfirm"))) return;
    state.generation += 1;
    $("mail-workspace-modal").hidden = true;
    state.context = null;
  }

  function draftPayload() {
    const selected = account();
    return {
      context_type: state.context.mailMessageId ? "reply" : "initial",
      reply_mail_message_id: state.context.mailMessageId || null,
      mail_account_id: selected?.mail_account_id || "",
      from_address: selected?.email || "",
      to_addresses: [$("mail-workspace-recipient").value],
      cc_addresses: [],
      subject: $("mail-workspace-subject").value,
      body_text: $("mail-workspace-body").value,
    };
  }

  async function saveDraft() {
    const payload = draftPayload();
    const data = state.draft
      ? await secure("PUT", `/api/mail/drafts/${encodeURIComponent(state.draft.draft_id)}`, { ...payload, version: state.draft.version })
      : await secure("POST", "/api/mail/drafts", payload);
    state.draft = data.draft;
    state.dirty = false;
    return state.draft;
  }

  async function readBody() {
    if (!state.context.mailMessageId) return;
    const generation = state.generation;
    setBusy(true);
    try {
      const data = await secure("POST", `/api/mail/messages/${encodeURIComponent(state.context.mailMessageId)}/body`, {});
      if (generation !== state.generation) return;
      $("mail-workspace-source-body").textContent = data.message.body_text || t("mailWorkspaceBodyEmpty");
      $("mail-workspace-source").hidden = false;
      setStatus(t("mailWorkspaceBodyLoaded"));
    } finally { setBusy(false); }
  }

  async function applyTemplate() {
    const templateId = $("mail-workspace-template").value;
    if (!templateId) return;
    const creatorName = state.context.creatorName || "Creator";
    const senderName = account()?.sender_name || account()?.name || "KOLConnect";
    const variables = {
      creator_name: creatorName, sender_name: senderName, brand_name: "KOLConnect",
      collaboration_type: "creator", campaign_name: "", game_name: "",
    };
    setBusy(true);
    try {
      const data = await secure("POST", `/api/mail/templates/${encodeURIComponent(templateId)}/render`, { variables });
      $("mail-workspace-subject").value = data.rendered.subject;
      $("mail-workspace-body").value = data.rendered.body;
      markDirty();
    } finally { setBusy(false); }
  }

  async function saveTemplate() {
    const name = global.prompt(t("mailWorkspaceTemplateName"), "")?.trim();
    if (!name) return;
    const subject = $("mail-workspace-subject").value;
    const body = $("mail-workspace-body").value;
    setBusy(true);
    try {
      const data = await secure("POST", "/api/mail/templates", {
        draft_type: draftType(), language: $("mail-workspace-language").value.trim(), name,
        tone: $("mail-workspace-tone").value.trim() || "professional",
        subject_template: subject, body_template: body,
        required_variables: requiredTemplateVariables(subject, body),
      });
      await selectTemplate(data.template);
      setStatus(t("mailWorkspaceTemplateSaved"));
    } finally { setBusy(false); }
  }

  async function updateTemplate() {
    const template = selectedTemplate();
    if (!template || template.template_source !== "user") return;
    const subject = $("mail-workspace-subject").value;
    const body = $("mail-workspace-body").value;
    setBusy(true);
    try {
      const data = await secure("PUT", `/api/mail/templates/${encodeURIComponent(template.template_id)}`, {
        template_version: template.template_version,
        draft_type: template.draft_type, language: template.language, name: template.name,
        tone: $("mail-workspace-template-tone").value.trim() || template.tone,
        subject_template: subject,
        body_template: body,
        required_variables: requiredTemplateVariables(subject, body),
      });
      await selectTemplate(data.template);
      setStatus(t("mailWorkspaceTemplateUpdated"));
    } finally { setBusy(false); updateTemplateActions(); }
  }

  async function deactivateTemplate() {
    const template = selectedTemplate();
    if (!template || template.template_source !== "user" || !global.confirm(t("mailWorkspaceDeactivateConfirm"))) return;
    setBusy(true);
    try {
      await secure("DELETE", `/api/mail/templates/${encodeURIComponent(template.template_id)}`, { template_version: template.template_version });
      await loadTemplates(state.generation);
      setStatus(t("mailWorkspaceTemplateDeactivated"));
    } finally { setBusy(false); updateTemplateActions(); }
  }

  async function generateAI() {
    if (!$("mail-workspace-ai-consent").checked) throw new Error(t("mailWorkspaceAIConsentRequired"));
    setBusy(true);
    try {
      const draft = await saveDraft();
      const context = {
        creator_name: String(state.context.creatorName || ""),
        source_subject: String(state.context.subject || ""),
        source_body: $("mail-workspace-source").hidden ? $("mail-workspace-body").value : $("mail-workspace-source-body").textContent,
      };
      Object.keys(context).forEach(key => { if (!context[key]) delete context[key]; });
      const provider = state.options.ai_provider.provider;
      const result = await secure("POST", "/api/mail/ai-draft-candidates", {
        draft_id: draft.draft_id, draft_version: draft.version,
        operation: $("mail-workspace-ai-operation").value, draft_type: draftType(),
        language_selection: { mode: "explicit", target_language: $("mail-workspace-language").value.trim() },
        tone: $("mail-workspace-tone").value.trim() || "professional", context, protected_facts: [],
        consent: { confirmed: true, provider, purpose: "mail_ai_draft", context_fields: Object.keys(context).sort() },
      });
      if (!result.candidate) throw new Error(result.error_code || t("mailWorkspaceAIFailed"));
      const adopted = await secure("POST", `/api/mail/ai-draft-candidates/${encodeURIComponent(result.candidate.candidate_id)}/adopt`, { draft_id: draft.draft_id, draft_version: draft.version });
      state.draft = adopted.draft;
      state.context.aiAdopted = true;
      $("mail-workspace-subject").value = state.draft.subject;
      $("mail-workspace-body").value = state.draft.body_text;
      state.dirty = true;
      resetTransient();
      setStatus(t("mailWorkspaceAICandidateReady"));
    } finally { setBusy(false); }
  }

  async function preview() {
    setBusy(true);
    try {
      const draft = await saveDraft();
      const data = await secure("POST", `/api/mail/drafts/${encodeURIComponent(draft.draft_id)}/preview`, {});
      state.preview = data.preview;
      $("mail-workspace-preview-envelope").textContent = `${state.preview.from_address} → ${state.preview.to_addresses.join(", ")}`;
      $("mail-workspace-preview-subject").textContent = state.preview.subject;
      $("mail-workspace-preview-body").textContent = state.preview.body_text;
      $("mail-workspace-preview").hidden = false;
      $("mail-workspace-confirm").checked = false;
      setStatus(t("mailWorkspacePreviewReady"));
    } finally { setBusy(false); }
  }

  async function send() {
    if (!state.preview || !$("mail-workspace-confirm").checked) return;
    setBusy(true);
    try {
      const authData = await secure("POST", `/api/mail/drafts/${encodeURIComponent(state.draft.draft_id)}/preview`, {
        confirm: true, preview_id: state.preview.preview_id,
        authorization_source: state.context.aiAdopted ? "human_approved_ai_proposal" : "human_direct",
      });
      state.authorization = authData.authorization;
      const idempotency = global.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const data = await secure("POST", "/api/mail/send", {
        preview_id: state.preview.preview_id,
        confirmation_token: state.authorization.confirmation_token,
        idempotency_key: idempotency,
      });
      const attempt = data.attempt;
      const recipients = (attempt.recipients || []).map(item => `${item.recipient_address}: ${item.outcome}`).join(" · ");
      setStatus(t(`mailWorkspaceOutcome_${attempt.outcome}`) + (recipients ? ` · ${recipients}` : ""));
      state.dirty = false;
      state.preview = null;
      $("mail-workspace-confirm").checked = false;
      $("mail-workspace-send").disabled = true;
    } finally { setBusy(false); }
  }

  function bind() {
    $("mail-workspace-close")?.addEventListener("click", close);
    $("mail-workspace-read-body")?.addEventListener("click", () => readBody().catch(global.KOLConnectApp.showError));
    $("mail-workspace-apply-template")?.addEventListener("click", () => applyTemplate().catch(global.KOLConnectApp.showError));
    $("mail-workspace-save-template")?.addEventListener("click", () => saveTemplate().catch(global.KOLConnectApp.showError));
    $("mail-workspace-update-template")?.addEventListener("click", () => updateTemplate().catch(global.KOLConnectApp.showError));
    $("mail-workspace-deactivate-template")?.addEventListener("click", () => deactivateTemplate().catch(global.KOLConnectApp.showError));
    $("mail-workspace-ai-generate")?.addEventListener("click", () => generateAI().catch(global.KOLConnectApp.showError));
    $("mail-workspace-preview-button")?.addEventListener("click", () => preview().catch(global.KOLConnectApp.showError));
    $("mail-workspace-send")?.addEventListener("click", () => send().catch(global.KOLConnectApp.showError));
    $("mail-workspace-confirm")?.addEventListener("change", event => { $("mail-workspace-send").disabled = !state.preview || !event.target.checked; });
    ["mail-workspace-language", "mail-workspace-template-tone"].forEach(id => $(id)?.addEventListener("change", () => loadTemplates(state.generation).catch(global.KOLConnectApp.showError)));
    $("mail-workspace-template")?.addEventListener("change", updateTemplateActions);
    ["mail-workspace-account", "mail-workspace-recipient", "mail-workspace-subject", "mail-workspace-body"].forEach(id => $(id)?.addEventListener("input", markDirty));
    global.addEventListener("beforeunload", event => { if (state.dirty && !$("mail-workspace-modal").hidden) { event.preventDefault(); event.returnValue = ""; } });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind, { once: true }); else bind();
  global.KOLConnectMailWorkspace = Object.freeze({ open });
})(window);
