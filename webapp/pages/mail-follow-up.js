(function registerMailFollowUpPage(global) {
  "use strict";

  let resources = null;
  let groups = [];
  let queuedGroups = [];
  let filter = "actionable";
  let actionPending = false;

  const element = id => document.getElementById(id);
  const app = () => global.KOLConnectApp;
  const t = (key, values) => {
    const translated = app()?.t?.(key, values);
    const template = translated && translated !== key ? translated : key;
    return String(template).replace(/\{(\w+)\}/g, (_, name) => String(values?.[name] ?? ""));
  };

  function text(value, fallback = "—") {
    const normalized = String(value ?? "").trim();
    return normalized || fallback;
  }

  function waitingLabel(value) {
    return ({ me: "mailFollowupWaitingMe", creator: "mailFollowupWaitingCreator", unknown: "mailFollowupWaitingUnknown" })[value]
      ? t(({ me: "mailFollowupWaitingMe", creator: "mailFollowupWaitingCreator", unknown: "mailFollowupWaitingUnknown" })[value])
      : t("mailFollowupWaitingUnknown");
  }

  function waitingHelp(value) {
    return value === "unknown"
      ? t("mailFollowupUnknownHelp")
      : "";
  }

  function historyLabel(value) {
    if (value === true) return t("mailFollowupHistoryPartial");
    if (value === null || value === undefined) return t("mailFollowupHistoryUnknown");
    return t("mailFollowupHistorySynced");
  }

  function historyHelp(value) {
    return value === null || value === undefined
      ? t("mailFollowupHistoryHelp")
      : "";
  }

  function daysLabel(value) {
    return Number.isInteger(value) && value >= 0 ? t("mailFollowupDays", { days: value }) : "—";
  }

  function rowKey(group) {
    return `${group.creator_id}\u0000${group.correspondent_email}`;
  }

  function visibleGroups() {
    return groups.filter(group => {
      if (filter === "actionable") return group.actionability === "normal";
      if (filter === "all") return true;
      return group.waiting_for === filter;
    });
  }

  function actionButton(label, action, group, className = "soft-btn") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${className} compact-btn`;
    button.textContent = label;
    button.dataset.followupAction = action;
    button.dataset.creatorId = group.creator_id;
    button.dataset.correspondentEmail = group.correspondent_email;
    button.disabled = actionPending;
    return button;
  }

  function appendActionButtons(cell, group) {
    const actions = document.createElement("div");
    actions.className = "mail-followup-actions";
    if (group.actionability === "stopped") {
      actions.appendChild(actionButton(t("mailFollowupResume"), "resume", group, "secondary-btn"));
    } else {
      const defer = document.createElement("details");
      defer.className = "mail-followup-defer-menu";
      const toggle = document.createElement("summary");
      toggle.className = "secondary-btn compact-btn";
      toggle.textContent = t("mailFollowupSnooze");
      const menu = document.createElement("div");
      menu.className = "mail-followup-defer-options";
      [
        [t("mailFollowupTomorrow"), "snooze:1"],
        [t("mailFollowupThreeDays"), "snooze:3"],
        [t("mailFollowupChooseDate"), "snooze:custom"],
        [t("mailFollowupClearSnooze"), "clear_snooze"],
      ].forEach(([label, action]) => menu.appendChild(actionButton(label, action, group, "secondary-btn")));
      defer.append(toggle, menu);
      actions.appendChild(defer);
      actions.appendChild(actionButton(t("mailFollowupStop"), "stop", group));
    }
    actions.appendChild(actionButton(
      group.export_queue_added_at ? t("mailFollowupExportRemove") : t("mailFollowupExportAdd"),
      group.export_queue_added_at ? "export_remove" : "export_add", group,
      "secondary-btn",
    ));
    cell.appendChild(actions);
  }

  function appendGroupRow(body, group, queueOnly = false) {
    const row = document.createElement("tr");
    const cells = [
      [text(group.creator_name, t("unnamedCreator"))],
      [text(group.correspondent_email)],
      [waitingLabel(group.waiting_for), waitingHelp(group.waiting_for)],
      [daysLabel(group.days_waiting)],
      [text(group.last_mail_at)],
    ];
    if (!queueOnly) cells.push(
      [text(group.synced_inbound_count, "0")],
      [text(group.synced_outbound_count, "0")],
      [historyLabel(group.partial_history), historyHelp(group.partial_history)],
    );
    cells.forEach(([value, help]) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (help) cell.title = help;
      row.appendChild(cell);
    });
    const actions = document.createElement("td");
    appendActionButtons(actions, group);
    row.appendChild(actions);
    body.appendChild(row);
  }

  function render() {
    const rows = visibleGroups();
    const body = element("mail-followup-list");
    const empty = element("mail-followup-empty");
    body.replaceChildren();
    rows.forEach(group => appendGroupRow(body, group));
    empty.hidden = rows.length !== 0;
    element("mail-followup-summary").textContent = t("mailFollowupSummary", { visible: rows.length, total: groups.length });
    document.querySelectorAll("[data-followup-filter]").forEach(button => {
      button.classList.toggle("active", button.dataset.followupFilter === filter);
    });
  }

  function renderExportQueue() {
    const body = element("mail-followup-export-list");
    const empty = element("mail-followup-export-empty");
    body.replaceChildren();
    queuedGroups.forEach(group => appendGroupRow(body, group, true));
    empty.hidden = queuedGroups.length !== 0;
  }

  async function load() {
    const data = await global.KOLConnectAPI.get("/api/mail/follow-up", { signal: resources?.signal });
    groups = Array.isArray(data.groups) ? data.groups : [];
    render();
  }

  async function loadExportQueue() {
    const data = await global.KOLConnectAPI.get("/api/mail/follow-up/export-queue", { signal: resources?.signal });
    queuedGroups = Array.isArray(data.groups) ? data.groups : [];
    renderExportQueue();
  }

  function futureUtc(days) {
    const value = new Date();
    value.setUTCDate(value.getUTCDate() + days);
    return value.toISOString();
  }

  function customSnooze() {
    const raw = global.prompt(t("mailFollowupPromptDate"), "");
    if (!raw || !raw.trim()) throw new Error(t("mailFollowupInvalidDate"));
    const value = new Date(raw);
    if (!Number.isFinite(value.getTime())) throw new Error(t("mailFollowupInvalidDateFormat"));
    return value.toISOString();
  }

  async function performAction(button) {
    if (actionPending) return;
    try {
      const action = String(button.dataset.followupAction || "");
      const payload = {
        creator_id: button.dataset.creatorId,
        correspondent_email: button.dataset.correspondentEmail,
        action,
      };
      if (action.startsWith("snooze:")) {
        const choice = action.slice("snooze:".length);
        payload.action = "snooze";
        payload.until = choice === "custom" ? customSnooze() : futureUtc(Number(choice));
      }
      if (payload.action === "stop" && !global.confirm(t("mailFollowupStopConfirm"))) return;
      actionPending = true;
      render();
      await global.KOLConnectAPI.post("/api/mail/follow-up/actions", payload, { signal: resources?.signal });
      await load();
      if (!element("mail-followup-export-panel").hidden) await loadExportQueue();
      app().showSaved(t("mailFollowupUpdated"));
    } catch (error) {
      app().showError(error);
    } finally {
      actionPending = false;
      render();
    }
  }

  async function downloadExport(format) {
    try {
      const response = await global.fetch(`/api/mail/follow-up/export?format=${format}`, { cache: "no-store", signal: resources?.signal });
      if (!response.ok) throw new Error(t("mailFollowupExportFailed"));
      const filename = format === "xlsx" ? "KOLConnect_Mail_Follow_Up_Queue.xlsx" : "KOLConnect_Mail_Follow_Up_Queue.csv";
      if (format === "xlsx" && global.pywebview?.api?.save_xlsx) {
        const bytes = new Uint8Array(await response.arrayBuffer());
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
        const result = await global.pywebview.api.save_xlsx(filename, global.btoa(binary));
        if (result?.canceled) return;
        if (!result?.saved) throw new Error(result?.error || t("mailFollowupFileSaveFailed"));
        app().showSaved(t("mailFollowupExportSaved", { path: result.path }));
        return;
      }
      const objectUrl = global.URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      global.URL.revokeObjectURL(objectUrl);
      app().showSaved(t("mailFollowupExported"));
    } catch (error) {
      app().showError(error);
    }
  }

  const page = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      await load();
    },
    bind() {
      resources.listen(element("mail-followup-refresh"), "click", () => load().catch(app().showError));
      resources.listen(element("mail-followup-list"), "click", event => {
        const button = event.target.closest("[data-followup-action]");
        if (button) performAction(button);
      });
      resources.listen(element("mail-followup-export-list"), "click", event => {
        const button = event.target.closest("[data-followup-action]");
        if (button) performAction(button);
      });
      resources.listen(element("mail-followup-show-export"), "click", async () => {
        await loadExportQueue();
        element("mail-followup-export-panel").hidden = false;
      });
      resources.listen(element("mail-followup-hide-export"), "click", () => { element("mail-followup-export-panel").hidden = true; });
      resources.listen(element("mail-followup-export-csv"), "click", () => downloadExport("csv"));
      resources.listen(element("mail-followup-export-xlsx"), "click", () => downloadExport("xlsx"));
      document.querySelectorAll("[data-followup-filter]").forEach(button => {
        resources.listen(button, "click", () => { filter = button.dataset.followupFilter || "actionable"; render(); });
      });
    },
    unbind() {
      resources?.cleanup();
      resources = null;
      groups = [];
      queuedGroups = [];
    },
  };

  global.KOLConnectPages.registerPage("mail-follow-up", page);
})(window);
