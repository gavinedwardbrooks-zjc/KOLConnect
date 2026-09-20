(function registerMailFollowUpPage(global) {
  "use strict";

  let resources = null;
  let groups = [];
  let queuedGroups = [];
  let filter = "actionable";
  let actionPending = false;

  const element = id => document.getElementById(id);
  const app = () => global.KOLConnectApp;

  function text(value, fallback = "—") {
    const normalized = String(value ?? "").trim();
    return normalized || fallback;
  }

  function waitingLabel(value) {
    return ({ me: "待我回复", creator: "待对方回复", unknown: "状态未知" })[value] || "状态未知";
  }

  function waitingHelp(value) {
    return value === "unknown"
      ? "当前邮件时间或联系人归属证据不足，暂时无法可靠判断由谁继续回复。"
      : "";
  }

  function historyLabel(value) {
    if (value === true) return "部分历史";
    if (value === null || value === undefined) return "历史范围未知";
    return "已同步范围内";
  }

  function historyHelp(value) {
    return value === null || value === undefined
      ? "当前同步的数据无法确认是否包含该联系人全部历史邮件，但不影响系统基于已同步邮件判断当前跟进状态。"
      : "";
  }

  function daysLabel(value) {
    return Number.isInteger(value) && value >= 0 ? `${value} 天` : "—";
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
      actions.appendChild(actionButton("恢复跟进", "resume", group, "secondary-btn"));
    } else {
      actions.appendChild(actionButton("明天提醒", "snooze:1", group));
      actions.appendChild(actionButton("3 天后", "snooze:3", group));
      actions.appendChild(actionButton("自定义提醒", "snooze:custom", group));
      if (group.actionability === "snoozed") actions.appendChild(actionButton("取消提醒", "clear_snooze", group));
      actions.appendChild(actionButton("停止跟进", "stop", group));
    }
    actions.appendChild(actionButton(
      group.export_queue_added_at ? "移出导出队列" : "加入导出队列",
      group.export_queue_added_at ? "export_remove" : "export_add", group,
    ));
    cell.appendChild(actions);
  }

  function appendGroupRow(body, group, queueOnly = false) {
    const row = document.createElement("tr");
    const cells = [
      [text(group.creator_name, "未命名达人")],
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
    element("mail-followup-summary").textContent = `当前显示 ${rows.length} 个邮件跟进项，共 ${groups.length} 个已同步联系人组。`;
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
    const raw = global.prompt("输入提醒时间（例如 2026-09-20T09:00:00Z）：", "");
    if (!raw || !raw.trim()) throw new Error("请选择有效的提醒时间。");
    const value = new Date(raw);
    if (!Number.isFinite(value.getTime())) throw new Error("提醒时间格式无效。");
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
      if (payload.action === "stop" && !global.confirm("停止后，该邮箱对应的跟进项将不再出现在正常待跟进列表中。邮件同步仍会继续。")) return;
      actionPending = true;
      render();
      await global.KOLConnectAPI.post("/api/mail/follow-up/actions", payload, { signal: resources?.signal });
      await load();
      if (!element("mail-followup-export-panel").hidden) await loadExportQueue();
      app().showSaved("邮件跟进状态已更新。");
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
      if (!response.ok) throw new Error("导出失败，请稍后重试。");
      const filename = format === "xlsx" ? "KOLConnect_Mail_Follow_Up_Queue.xlsx" : "KOLConnect_Mail_Follow_Up_Queue.csv";
      if (format === "xlsx" && global.pywebview?.api?.save_xlsx) {
        const bytes = new Uint8Array(await response.arrayBuffer());
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
        const result = await global.pywebview.api.save_xlsx(filename, global.btoa(binary));
        if (result?.canceled) return;
        if (!result?.saved) throw new Error(result?.error || "文件保存失败，请稍后重试。");
        app().showSaved(`导出完成：${result.path}`);
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
      app().showSaved("导出完成。");
    } catch (error) {
      app().showError(error);
    }
  }

  async function syncMail() {
    try {
      await global.KOLConnectAPI.post("/api/mail/inbox/sync", { limit_per_account: 20 }, { signal: resources?.signal });
      await global.KOLConnectAPI.post("/api/mail/sent/sync", {}, { signal: resources?.signal });
      await load();
      app().showSaved("邮件同步完成。");
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
      resources.listen(element("mail-followup-sync"), "click", syncMail);
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
