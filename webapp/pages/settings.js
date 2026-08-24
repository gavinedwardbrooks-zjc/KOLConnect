(function registerSettingsPage(global) {
  "use strict";

  let resources = null;
  let accountBackfillPreviewReady = false;
  let creatorBackfillPreviewReady = false;

  function getApp() {
    if (!global.KOLConnectApp) throw new Error("KOLConnect application helpers are unavailable.");
    return global.KOLConnectApp;
  }

  function handleError(error) {
    if (error?.name !== "AbortError") getApp().showError(error);
  }

  async function reloadSettings() {
    const app = getApp();
    const result = await app.loadSettingsState({ signal: resources?.signal });
    const currentWorkbook = document.getElementById("creator-library-backup-workbook");
    if (currentWorkbook) {
      currentWorkbook.textContent = app.valueOf("creator-library-workbook-path").trim() || "--";
    }
    return result;
  }

  function renderWorkbookPathCapability() {
    const hint = document.getElementById("creator-library-workbook-path-hint");
    if (!hint) return;
    const desktopBridgeAvailable = Boolean(global.pywebview?.api?.save_xlsx);
    hint.dataset.runtimeMode = desktopBridgeAvailable ? "desktop" : "browser";
    hint.textContent = desktopBridgeAvailable
      ? "可设置为 WPS 云盘或其他同步文件夹。首次使用时会自动创建所需工作表。"
      : "高级本地文件设置：请填写运行 KOLConnect 的本机后端可访问路径；浏览器不会提供原生文件选择器，也不会上传工作簿。";

    const browserExitCard = document.getElementById("browser-mode-exit-card");
    if (browserExitCard) browserExitCard.hidden = desktopBridgeAvailable;
  }

  function listen(id, type, listener) {
    const element = document.getElementById(id);
    if (element) resources.listen(element, type, listener);
  }

  function setSyncText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value ?? "--";
  }

  function schemaTableLabel(table) {
    return table === "creator" ? "Creator 表" : table === "account" ? "Creator Account 表" : "未知表";
  }

  function renderSchemaValidationDetails(data) {
    const missing = Array.isArray(data?.missing_fields) ? data.missing_fields : [];
    const incompatible = Array.isArray(data?.incompatible_fields) ? data.incompatible_fields : [];
    const lines = ["飞书表结构需要补充"];
    for (const table of ["creator", "account"]) {
      const fields = missing
        .filter(item => item?.table === table && item?.field)
        .map(item => String(item.field));
      if (fields.length) {
        lines.push("", `${schemaTableLabel(table)}缺少：`, ...fields.map(field => `- ${field}`));
      }
    }
    for (const table of ["creator", "account"]) {
      const fields = incompatible.filter(item => item?.table === table && item?.field);
      if (fields.length) {
        lines.push("", `${schemaTableLabel(table)}字段类型不兼容:`);
        lines.push(...fields.map(item => `- ${String(item.field)}（当前类型：${String(item.actual_type ?? "未知")}）`));
      }
    }
    return lines.join("\n");
  }

  function renderSyncResult(data, operation) {
    const status = String(data?.status || "failed");
    const connectionLabel = data?.connection_ok === false
      ? "配置异常"
      : status === "failed"
        ? "不可用"
        : status === "blocked"
          ? "需处理"
          : "可用";
    setSyncText("feishu-sync-connection", connectionLabel);
    setSyncText("feishu-sync-local-creators", data?.local_creator_count);
    setSyncText("feishu-sync-remote-creators", data?.remote_creator_count);
    setSyncText("feishu-sync-create", data?.creator_create_count ?? data?.creator_created);
    setSyncText("feishu-sync-update", data?.creator_update_count ?? data?.creator_updated);
    setSyncText("feishu-sync-conflicts", data?.creator_conflict_count ?? data?.conflicts?.length ?? 0);
    setSyncText("feishu-sync-unmanaged", data?.remote_unmanaged_count);
    const message = document.getElementById("feishu-sync-result");
    if (!message) return;
    message.hidden = false;
    message.dataset.status = status;
    if (status === "success") {
      message.textContent = operation === "full"
        ? `同步完成：达人新增 ${data.creator_created || 0}、更新 ${data.creator_updated || 0}；账号新增 ${data.account_created || 0}、更新 ${data.account_updated || 0}。`
        : operation === "validate" ? "连接与字段合同验证通过。" : "预检查完成，未写入飞书。";
    } else if (status === "partial") {
      message.textContent = `同步部分完成，失败记录 ${Number(data.creator_failed || 0) + Number(data.account_failed || 0)} 条；后续批次已停止，可修复后重新同步。`;
    } else {
      const reason = data?.blocked_reason || data?.error_codes?.[0] || "FEISHU_SYNC_FAILED";
      const hasSchemaDetails = (data?.missing_fields?.length || 0) + (data?.incompatible_fields?.length || 0) > 0;
      message.textContent = reason === "FEISHU_SCHEMA_INVALID" && hasSchemaDetails
        ? renderSchemaValidationDetails(data)
        : `操作未执行：${reason}`;
    }
  }

  async function runSyncOperation(api, operation, options = {}) {
    const button = document.getElementById(`feishu-sync-${operation === "full" ? "full" : operation}`);
    if (button) button.disabled = true;
    try {
      const path = operation === "validate"
        ? "/api/feishu-sync/validate"
        : operation === "dry-run"
          ? "/api/feishu-sync/dry-run"
          : "/api/feishu-sync/full-sync";
      const data = await api.post(path, operation === "full" ? { confirm: true } : {}, options);
      renderSyncResult(data, operation);
      return data;
    } finally {
      if (button) button.disabled = false;
    }
  }

  function backfillReasonLabel(item) {
    const labels = {
      MISSING_REMOTE_RECORD_ID: "缺少远端记录 ID",
      MISSING_ACCOUNT_UID: "缺少 account_uid",
      DUPLICATE_REMOTE_ACCOUNT_UID: "远端 account_uid 重复",
      DUPLICATE_LOCAL_ACCOUNT_UID: "本地 account_uid 重复",
      UNMATCHED_ACCOUNT_UID: "未匹配",
      INVALID_LOCAL_CREATOR_ID: "本地 creator_id 无效",
      CREATOR_ID_CONFLICT: "身份冲突",
    };
    return labels[item?.reason] || String(item?.reason || "已阻塞");
  }

  function appendBackfillCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value || "--";
    row.appendChild(cell);
  }

  function renderBackfillRows(data) {
    const body = document.getElementById("feishu-account-backfill-rows");
    const details = document.getElementById("feishu-account-backfill-details");
    if (!body || !details) return;
    body.textContent = "";
    const rows = [
      ...(Array.isArray(data?.candidates) ? data.candidates.map(item => ({ ...item, displayStatus: "可安全认领" })) : []),
      ...(Array.isArray(data?.blocked) ? data.blocked.map(item => ({ ...item, displayStatus: backfillReasonLabel(item) })) : []),
    ];
    for (const item of rows) {
      const row = document.createElement("tr");
      appendBackfillCell(row, String(item.platform || ""));
      appendBackfillCell(row, String(item.profile_url || ""));
      appendBackfillCell(row, String(item.account_uid || ""));
      const identity = item.reason === "CREATOR_ID_CONFLICT"
        ? `远端 ${item.remote_creator_id || "--"} / 本地 ${item.local_creator_id || "--"}`
        : String(item.creator_id || "");
      appendBackfillCell(row, identity);
      appendBackfillCell(row, item.displayStatus);
      body.appendChild(row);
    }
    details.hidden = rows.length === 0;
  }

  function renderAccountBackfillResult(data, operation) {
    const summary = data?.summary || {};
    setSyncText("feishu-account-backfill-remote", summary.remote_accounts);
    setSyncText("feishu-account-backfill-eligible", summary.eligible);
    setSyncText("feishu-account-backfill-unchanged", summary.unchanged);
    setSyncText("feishu-account-backfill-unmatched", summary.unmatched);
    setSyncText("feishu-account-backfill-conflicts", summary.conflicts);
    renderBackfillRows(data);
    const message = document.getElementById("feishu-account-backfill-result");
    if (!message) return;
    const status = String(data?.status || "failed");
    message.hidden = false;
    message.dataset.status = status;
    if (operation === "preview" && status === "success") {
      message.textContent = `预览完成：可安全认领 ${summary.eligible || 0}，无需更新 ${summary.unchanged || 0}，未匹配 ${summary.unmatched || 0}，冲突 ${summary.conflicts || 0}。未写入飞书。`;
    } else if (status === "success") {
      message.textContent = `认领完成：成功 ${data.succeeded || 0}，无需更新 ${summary.unchanged || 0}，剩余 ${data.remaining || 0}。`;
    } else if (status === "partial") {
      message.textContent = `部分成功：已完成 ${data.succeeded || 0}，失败 ${data.failed || 0}，仍需处理 ${data.remaining || 0}。可重新生成预览后重试。`;
    } else if (status === "blocked") {
      message.textContent = `认领已阻塞：${data?.blocked_reason || "没有可安全自动认领的记录"}。冲突记录不会被覆盖。`;
    } else {
      message.textContent = `认领失败：${data?.error_codes?.[0] || "FEISHU_ACCOUNT_BACKFILL_FAILED"}`;
    }
  }

  async function runAccountBackfill(api, operation, options = {}) {
    const preview = operation === "preview";
    const button = document.getElementById(
      preview ? "feishu-account-backfill-preview" : "feishu-account-backfill-execute",
    );
    if (button) button.disabled = true;
    try {
      const path = preview
        ? "/api/feishu-sync/account-backfill/dry-run"
        : "/api/feishu-sync/account-backfill/execute";
      const data = await api.post(path, preview ? {} : { confirm: true }, options);
      renderAccountBackfillResult(data, operation);
      const execute = document.getElementById("feishu-account-backfill-execute");
      accountBackfillPreviewReady = preview
        && data?.status === "success"
        && Number(data?.summary?.eligible || 0) > 0;
      if (execute) execute.disabled = !accountBackfillPreviewReady;
      return data;
    } finally {
      if (button && preview) button.disabled = false;
    }
  }

  function creatorBackfillReasonLabel(item) {
    const labels = {
      MISSING_REMOTE_RECORD_ID: "缺少远端记录 ID",
      CREATOR_ID_CONFLICT: "Creator 身份冲突",
      NO_RECIPROCAL_ACCOUNT_EVIDENCE: "无双向账号证据",
      UNVERIFIED_REVERSE_ACCOUNT_RELATION: "关联账号未通过身份验证",
      MISSING_FORWARD_RELATION: "缺少 Account → Creator 关系",
      MISSING_REVERSE_RELATION: "缺少 Creator → Account 关系",
      RECIPROCAL_RELATION_DISAGREEMENT: "双向关系不一致",
      MULTIPLE_LOCAL_CREATOR_IDS: "关联到多个本地 Creator",
      LOCAL_CREATOR_MULTIPLE_REMOTE_CREATORS: "一个本地 Creator 对应多个远端 Creator",
    };
    return labels[item?.reason] || String(item?.reason || "已阻塞");
  }

  function renderCreatorBackfillRows(data) {
    const body = document.getElementById("feishu-creator-backfill-rows");
    const details = document.getElementById("feishu-creator-backfill-details");
    if (!body || !details) return;
    body.textContent = "";
    const rows = [
      ...(Array.isArray(data?.candidates) ? data.candidates.map(item => ({ ...item, displayStatus: "Tier-A 可安全认领" })) : []),
      ...(Array.isArray(data?.blocked) ? data.blocked.map(item => ({ ...item, displayStatus: creatorBackfillReasonLabel(item) })) : []),
    ];
    for (const item of rows) {
      const row = document.createElement("tr");
      appendBackfillCell(row, String(item.creator_name || item.remote_record_id || ""));
      appendBackfillCell(row, String(item.creator_id || item.remote_creator_id || ""));
      const accountEvidence = Array.isArray(item.accounts)
        ? item.accounts.map(account => `${account.platform || "账号"}: ${account.account_uid || "--"}`).join("\n")
        : "";
      appendBackfillCell(row, accountEvidence);
      appendBackfillCell(row, item.displayStatus);
      body.appendChild(row);
    }
    details.hidden = rows.length === 0;
  }

  function renderCreatorBackfillResult(data, operation) {
    const summary = data?.summary || {};
    setSyncText("feishu-creator-backfill-remote", summary.remote_creators);
    setSyncText("feishu-creator-backfill-eligible", summary.tier_a_eligible);
    setSyncText("feishu-creator-backfill-unchanged", summary.already_correct);
    setSyncText("feishu-creator-backfill-tier-b", summary.tier_b_manual_review);
    setSyncText(
      "feishu-creator-backfill-residual",
      Number(summary.ambiguous || 0) + Number(summary.unmatched || 0),
    );
    setSyncText("feishu-creator-backfill-conflicts", summary.conflicts);
    setSyncText("feishu-creator-backfill-blocked", summary.blocked);
    renderCreatorBackfillRows(data);
    const message = document.getElementById("feishu-creator-backfill-result");
    if (!message) return;
    const status = String(data?.status || "failed");
    message.hidden = false;
    message.dataset.status = status;
    if (operation === "preview" && status === "success") {
      message.textContent = `预览完成：Tier-A 可认领 ${summary.tier_a_eligible || 0}，已正确 ${summary.already_correct || 0}，Tier-B 待人工 ${summary.tier_b_manual_review || 0}，歧义 ${summary.ambiguous || 0}，未匹配 ${summary.unmatched || 0}。未写入飞书。`;
    } else if (status === "success") {
      message.textContent = `Creator 身份认领完成：成功 ${data.succeeded || 0}，剩余 ${data.remaining || 0}。请重新运行预览确认可认领数已收敛为 0。`;
    } else if (status === "partial") {
      message.textContent = `Creator 身份认领部分成功：已完成 ${data.succeeded || 0}，失败 ${data.failed || 0}，剩余 ${data.remaining || 0}。请重新预览后安全重试。`;
    } else if (status === "blocked") {
      message.textContent = `Creator 身份认领已阻塞：${data?.blocked_reason || "当前没有可安全自动认领的记录"}。不会覆盖冲突记录。`;
    } else {
      message.textContent = `Creator 身份认领失败：${data?.error_codes?.[0] || "FEISHU_CREATOR_BACKFILL_FAILED"}`;
    }
  }

  async function runCreatorBackfill(api, operation, options = {}) {
    const preview = operation === "preview";
    const button = document.getElementById(
      preview ? "feishu-creator-backfill-preview" : "feishu-creator-backfill-execute",
    );
    if (button) button.disabled = true;
    try {
      const path = preview
        ? "/api/feishu-sync/creator-backfill/dry-run"
        : "/api/feishu-sync/creator-backfill/execute";
      const data = await api.post(path, preview ? {} : { confirm: true }, options);
      renderCreatorBackfillResult(data, operation);
      const execute = document.getElementById("feishu-creator-backfill-execute");
      creatorBackfillPreviewReady = preview
        && data?.status === "success"
        && Number(data?.summary?.tier_a_eligible || 0) > 0;
      if (execute) execute.disabled = !creatorBackfillPreviewReady;
      return data;
    } finally {
      if (button && preview) button.disabled = false;
    }
  }

  const settingsPage = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      accountBackfillPreviewReady = false;
      creatorBackfillPreviewReady = false;
      await reloadSettings();
      renderWorkbookPathCapability();
      const execute = document.getElementById("feishu-account-backfill-execute");
      if (execute) execute.disabled = true;
      const creatorExecute = document.getElementById("feishu-creator-backfill-execute");
      if (creatorExecute) creatorExecute.disabled = true;
    },

    bind() {
      const app = getApp();
      const api = global.KOLConnectAPI;

      listen("save-ui-settings", "click", async () => {
        try {
          await api.post("/api/settings/ui", {
            language: app.valueOf("ui-language"),
            debug_mode: app.checkedOf("debug-mode"),
          }, { signal: resources.signal });
          await api.post("/api/settings/profiles", {
            selected: app.valueOf("default-profile"),
          }, { signal: resources.signal });
          app.setLanguage(app.valueOf("ui-language"));
          app.renderStaticText();
          app.showSaved();
          await reloadSettings();
        } catch (error) {
          handleError(error);
        }
      });

      listen("system-health-run", "click", async () => {
        try {
          await app.loadSystemHealth({ signal: resources.signal });
        } catch (error) {
          handleError(error);
        }
      });

      listen("debug-mode", "change", () => {
        app.setDebugModeVisible(app.checkedOf("debug-mode"));
      });

      listen("feishu-save", "click", async () => {
        try {
          await api.post("/api/settings/feishu", {
            app_id: app.valueOf("feishu-app-id").trim(),
            app_secret: app.valueOf("feishu-app-secret").trim(),
            app_token: app.valueOf("feishu-app-token").trim(),
            creator_table_id: app.valueOf("feishu-creator-table-id").trim(),
            account_table_id: app.valueOf("feishu-account-table-id").trim(),
            contact_table_id: app.valueOf("feishu-contact-table-id").trim(),
          }, { signal: resources.signal });
          app.showSaved();
          await reloadSettings();
        } catch (error) {
          handleError(error);
        }
      });

      listen("creator-library-save-config", "click", async () => {
        try {
          await api.post("/api/settings/creator-library", {
            workbook_path: app.valueOf("creator-library-workbook-path").trim(),
          }, { signal: resources.signal });
          app.showSaved("\u8fbe\u4eba\u5e93\u6587\u4ef6\u8bbe\u7f6e\u5df2\u4fdd\u5b58\u3002");
          await reloadSettings();
        } catch (error) {
          handleError(error);
        }
      });

      listen("feishu-sync-validate", "click", async () => {
        try {
          await runSyncOperation(api, "validate", { signal: resources.signal });
        } catch (error) {
          handleError(error);
        }
      });

      listen("feishu-sync-dry-run", "click", async () => {
        try {
          await runSyncOperation(api, "dry-run", { signal: resources.signal });
        } catch (error) {
          handleError(error);
        }
      });

      listen("feishu-sync-full", "click", async () => {
        const confirmed = global.confirm(
          "KOLConnect / Excel 将保持为权威数据源。同步可能在飞书创建缺失记录并更新精确匹配记录；M7.1 不会删除任何飞书记录。确认继续吗？",
        );
        if (!confirmed) return;
        try {
          await runSyncOperation(api, "full", { signal: resources.signal });
        } catch (error) {
          handleError(error);
        }
      });

      listen("feishu-account-backfill-preview", "click", async () => {
        try {
          await runAccountBackfill(api, "preview", { signal: resources.signal });
        } catch (error) {
          accountBackfillPreviewReady = false;
          const execute = document.getElementById("feishu-account-backfill-execute");
          if (execute) execute.disabled = true;
          handleError(error);
        }
      });

      listen("feishu-account-backfill-execute", "click", async () => {
        if (!accountBackfillPreviewReady) return;
        const confirmed = global.confirm(
          "将仅更新飞书【达人账号表】中可确认的身份字段：\n\n"
          + "• 账号唯一ID\n• KOLConnect Creator ID\n\n"
          + "不会创建记录\n不会删除记录\n不会修改达人表\n不会修改业务数据\n\n继续吗？",
        );
        if (!confirmed) return;
        try {
          await runAccountBackfill(api, "execute", { signal: resources.signal });
        } catch (error) {
          handleError(error);
        }
      });

      listen("feishu-creator-backfill-preview", "click", async () => {
        try {
          await runCreatorBackfill(api, "preview", { signal: resources.signal });
        } catch (error) {
          creatorBackfillPreviewReady = false;
          const execute = document.getElementById("feishu-creator-backfill-execute");
          if (execute) execute.disabled = true;
          handleError(error);
        }
      });

      listen("feishu-creator-backfill-execute", "click", async () => {
        if (!creatorBackfillPreviewReady) return;
        const confirmed = global.confirm(
          "这是历史数据安全迁移，将仅更新飞书【Creator 表】中的 KOLConnect Creator ID。\n\n"
          + "不会创建或删除 Creator\n不会修改 Creator 业务字段\n不会修改 Account\n不会修改本地 Excel\n\n继续吗？",
        );
        if (!confirmed) return;
        try {
          await runCreatorBackfill(api, "execute", { signal: resources.signal });
        } catch (error) {
          handleError(error);
        }
      });

      listen("creator-library-backup-create", "click", async () => {
        const button = document.getElementById("creator-library-backup-create");
        if (button) button.disabled = true;
        try {
          const data = await api.post(
            "/api/settings/creator-library/backup",
            {},
            { signal: resources.signal },
          );
          const backup = data?.backup || {};
          const latest = document.getElementById("creator-library-backup-latest");
          if (latest) {
            latest.textContent = backup.filename
              ? `${backup.filename} · ${backup.created_at || "--"}`
              : "--";
          }
          app.showSaved("达人库 Excel 备份已创建。");
        } catch (error) {
          handleError(error);
        } finally {
          if (button) button.disabled = false;
        }
      });

      listen("browser-mode-exit", "click", async () => {
        const button = document.getElementById("browser-mode-exit");
        if (button) button.disabled = true;
        try {
          await api.post("/api/runtime/shutdown", {});
          if (button) button.textContent = "KOLConnect 已退出，可关闭此页面";
        } catch (error) {
          if (button) button.disabled = false;
          handleError(error);
        }
      });

      listen("ui-language", "change", () => {
        app.setLanguage(app.valueOf("ui-language"));
        app.renderStaticText();
        app.renderCurrentTask();
      });
    },

    unbind() {
      resources?.cleanup();
      resources = null;
    },
  };

  global.KOLConnectPages.registerPage("settings", settingsPage);
})(window);
