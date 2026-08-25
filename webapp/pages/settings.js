(function registerSettingsPage(global) {
  "use strict";

  let resources = null;
  let cleanResetPreview = null;
  let feishuChatPollGeneration = 0;
  const FEISHU_CHAT_POLL_INTERVAL_MS = 1000;

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

  function renderFeishuChatStatus(data) {
    const labels = {
      disabled: "未启用",
      connecting: "正在连接",
      connected: "已连接",
      error: "连接失败",
    };
    const state = String(data?.state || "disabled");
    setSyncText("feishu-chat-status", labels[state] || "未知");
    setSyncText("feishu-chat-transport", data?.transport === "long_connection" ? "飞书官方长连接" : "--");
    setSyncText("feishu-chat-bot", data?.bot_enabled ? "已启用" : "未启用");
    setSyncText("feishu-chat-last-connected", data?.last_connected_at || "--");
    setSyncText("feishu-chat-last-error", data?.last_error_code || "--");

    const enable = document.getElementById("feishu-chat-enable");
    const disable = document.getElementById("feishu-chat-disable");
    if (enable) enable.disabled = state === "connecting" || state === "connected";
    if (disable) disable.disabled = state === "disabled";
  }

  async function loadFeishuChatStatus(api, options = {}) {
    const data = await api.get("/api/feishu-chat/status", options);
    renderFeishuChatStatus(data);
    return data;
  }

  function stopFeishuChatPolling() {
    feishuChatPollGeneration += 1;
  }

  function startFeishuChatPolling(api) {
    const generation = ++feishuChatPollGeneration;
    const poll = async () => {
      if (!resources || resources.disposed || generation !== feishuChatPollGeneration) return;
      try {
        const data = await loadFeishuChatStatus(api, { signal: resources.signal });
        if (generation !== feishuChatPollGeneration) return;
        if (data?.state === "connecting") {
          resources.setTimeout(poll, FEISHU_CHAT_POLL_INTERVAL_MS);
          return;
        }
        if (data?.state === "error") renderFeishuChatResult(data, "status");
      } catch (error) {
        handleError(error);
      }
    };
    resources.setTimeout(poll, FEISHU_CHAT_POLL_INTERVAL_MS);
  }

  function renderFeishuChatResult(data, operation) {
    const message = document.getElementById("feishu-chat-result");
    if (!message) return;
    message.hidden = false;
    const ok = operation === "test" ? data?.ok === true : data?.state !== "error";
    message.dataset.status = ok ? "success" : "failed";
    if (ok) {
      message.textContent = operation === "test"
        ? "本机配置与 SDK 检查通过。连接状态请以启用后的实时状态为准。"
        : operation === "disable"
          ? "飞书 AI 助手已停止。"
          : data?.state === "connected"
            ? "飞书 AI 助手已连接。"
            : "飞书 AI 助手正在连接。";
    } else {
      const code = String(data?.error_code || data?.last_error_code || "LONG_CONNECTION_FAILED");
      const guidance = {
        INVALID_APP_CREDENTIALS: "请检查并重新保存 App ID / App Secret。",
        FEISHU_CHAT_INVALID_CREDENTIALS: "请检查并重新保存 App ID / App Secret。",
        SDK_NOT_AVAILABLE: "飞书官方 SDK 未安装或未包含在当前应用包中。",
        BOT_CAPABILITY_NOT_ENABLED: "请在飞书开放平台启用机器人能力并发布应用。",
        BOT_PERMISSION_MISSING: "请启用机器人发送消息权限并重新发布应用。",
        FEISHU_CHAT_PERMISSION_DENIED: "请检查机器人消息权限并重新发布应用。",
        EVENT_PERMISSION_MISSING: "请订阅消息接收事件并授予消息读取权限。",
        FEISHU_CHAT_EVENT_CONFIGURATION_ERROR: "请检查长连接模式、消息事件订阅和机器人能力。",
        FEISHU_CHAT_NETWORK_ERROR: "请检查本机网络、代理、防火墙和飞书服务状态。",
        FEISHU_CHAT_CONNECT_TIMEOUT: "飞书长连接建立超时。请检查网络、飞书应用长连接配置及应用凭据后重试。",
        FEISHU_CHAT_SDK_ERROR: "飞书官方 SDK 无法建立长连接，请查看安全日志后重试。",
        LONG_CONNECTION_FAILED: "请检查网络、应用发布状态和飞书服务状态。",
      };
      message.textContent = `操作未完成：${code}\n${guidance[code] || "请查看运行日志中的 trace 信息。"}`;
    }
  }

  async function runFeishuChatOperation(api, operation, options = {}) {
    const button = document.getElementById(`feishu-chat-${operation}`);
    if (button) button.disabled = true;
    try {
      const data = await api.post(`/api/feishu-chat/${operation}`, {}, options);
      renderFeishuChatStatus(data);
      renderFeishuChatResult(data, operation);
      if (operation === "enable" && data?.state === "connecting") {
        startFeishuChatPolling(api);
      } else if (operation === "disable" || data?.state !== "connecting") {
        stopFeishuChatPolling();
      }
      return data;
    } finally {
      if (button) button.disabled = false;
    }
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
    setSyncText("feishu-sync-relation-add", data?.relation_add_count ?? data?.relation_added);
    setSyncText("feishu-sync-relation-update", data?.relation_update_count ?? data?.relation_updated);
    setSyncText("feishu-sync-relation-remove", data?.relation_remove_count ?? data?.relation_removed);
    setSyncText("feishu-sync-relation-conflicts", data?.relation_conflict_count ?? 0);
    const message = document.getElementById("feishu-sync-result");
    if (!message) return;
    message.hidden = false;
    message.dataset.status = status;
    if (status === "success") {
      message.textContent = operation === "full"
        ? `同步完成：达人新增 ${data.creator_created || 0}、更新 ${data.creator_updated || 0}；账号新增 ${data.account_created || 0}、更新 ${data.account_updated || 0}；关系更新 ${data.relation_updated || 0}。`
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

  function renderCleanResetResult(data, operation) {
    const summary = data?.summary || {};
    setSyncText("clean-reset-creators", summary.creators);
    setSyncText("clean-reset-accounts", summary.accounts);
    setSyncText("clean-reset-videos", summary.videos);
    setSyncText("clean-reset-snapshots", summary.snapshots);
    setSyncText("clean-reset-campaigns", summary.campaigns);
    const message = document.getElementById("clean-reset-result");
    if (!message) return;
    message.hidden = false;
    message.dataset.status = String(data?.status || "failed");
    if (operation === "preview" && data?.status === "success") {
      message.textContent = "预览完成，尚未修改任何本地数据。确认数量后方可执行清空。";
    } else if (data?.status === "success") {
      message.textContent = `本地业务数据已清空。备份：${String(data?.backup?.filename || "--")}`;
    } else {
      const review = Array.isArray(data?.review_items) ? data.review_items.join("、") : "";
      message.textContent = `操作未执行：${review || data?.error || "CLEAN_RESET_FAILED"}`;
    }
  }

  async function runCleanReset(api, operation, options = {}) {
    const preview = operation === "preview";
    const button = document.getElementById(preview ? "clean-reset-preview" : "clean-reset-execute");
    if (button) button.disabled = true;
    try {
      const data = await api.post(
        preview ? "/api/settings/clean-reset/preview" : "/api/settings/clean-reset/execute",
        preview ? {} : { confirm: true },
        options,
      );
      renderCleanResetResult(data, operation);
      cleanResetPreview = preview
        && data?.status === "success"
        && Array.isArray(data?.review_items)
        && data.review_items.length === 0
        ? data
        : null;
      const execute = document.getElementById("clean-reset-execute");
      if (execute) execute.disabled = !cleanResetPreview;
      return data;
    } finally {
      if (button && preview) button.disabled = false;
    }
  }
  const settingsPage = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      cleanResetPreview = null;
      await reloadSettings();
      if (typeof global.KOLConnectAPI?.get === "function") {
        try {
          const chatStatus = await loadFeishuChatStatus(
            global.KOLConnectAPI,
            { signal: resources.signal },
          );
          if (chatStatus?.state === "connecting") startFeishuChatPolling(global.KOLConnectAPI);
        } catch (error) {
          handleError(error);
        }
      }
      renderWorkbookPathCapability();
      const resetExecute = document.getElementById("clean-reset-execute");
      if (resetExecute) resetExecute.disabled = true;
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

      for (const operation of ["test", "enable", "disable"]) {
        listen(`feishu-chat-${operation}`, "click", async () => {
          try {
            await runFeishuChatOperation(api, operation, { signal: resources.signal });
          } catch (error) {
            handleError(error);
          }
        });
      }

      listen("clean-reset-preview", "click", async () => {
        cleanResetPreview = null;
        const execute = document.getElementById("clean-reset-execute");
        if (execute) execute.disabled = true;
        try {
          await runCleanReset(api, "preview", { signal: resources.signal });
        } catch (error) {
          handleError(error);
        }
      });

      listen("clean-reset-execute", "click", async () => {
        if (!cleanResetPreview) return;
        const summary = cleanResetPreview.summary || {};
        const confirmed = global.confirm(
          "将永久清空本机历史业务数据：\n\n"
          + `Creators: ${summary.creators || 0}\nAccounts: ${summary.accounts || 0}\n`
          + `Videos: ${summary.videos || 0}\nSnapshots: ${summary.snapshots || 0}\n`
          + `Campaigns: ${summary.campaigns || 0}\n\n`
          + "Chrome 配置：保留\n邮箱配置：保留\n飞书配置：保留\nSchema：保留\n\n"
          + "执行前将创建可恢复的时间戳备份。确认继续吗？",
        );
        if (!confirmed) return;
        cleanResetPreview = null;
        const execute = document.getElementById("clean-reset-execute");
        if (execute) execute.disabled = true;
        try {
          await runCleanReset(api, "execute", { signal: resources.signal });
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
      stopFeishuChatPolling();
      resources?.cleanup();
      resources = null;
    },
  };

  global.KOLConnectPages.registerPage("settings", settingsPage);
})(window);
