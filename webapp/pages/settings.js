(function registerSettingsPage(global) {
  "use strict";

  let resources = null;

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
      message.textContent = `部分同步成功，失败记录 ${Number(data.creator_failed || 0) + Number(data.account_failed || 0)} 条，可修复后重新同步。`;
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

  const settingsPage = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      await reloadSettings();
      renderWorkbookPathCapability();
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
