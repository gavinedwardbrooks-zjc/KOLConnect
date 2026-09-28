(function registerSettingsPage(global) {
  "use strict";

  let resources = null;
  let cleanResetPreview = null;
  let storageMigrationPreview = null;
  let feishuChatPollGeneration = 0;
  const FEISHU_CHAT_POLL_INTERVAL_MS = 1000;
  const storageMigrationSession = `settings-${global.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  let fxRates = [];
  let showAllFxRates = false;

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
    renderFxSettings(result?.fx);
    return result;
  }

  function t(key, values) {
    return getApp().t(key, values);
  }

  function renderWorkbookPathCapability() {
    const hint = document.getElementById("creator-library-workbook-path-hint");
    if (!hint) return;
    hint.textContent = t("settingsWorkbookPathHint");
  }

  function listen(id, type, listener) {
    const element = document.getElementById(id);
    if (element) resources.listen(element, type, listener);
  }

  function setSyncText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value ?? "--";
  }

  function renderFxSettings(data) {
    fxRates = Array.isArray(data?.rates) ? data.rates : [];
    const fields = document.getElementById("fx-rate-fields");
    const currencies = document.getElementById("fx-calculator-currency");
    if (fields) {
      fields.replaceChildren();
      fxRates.filter(rate => showAllFxRates || rate.currency_code === "USD" || rate.rate_per_usd != null).forEach(rate => {
        const label = document.createElement("label");
        label.className = "field";
        const title = document.createElement("span");
        title.textContent = rate.currency_code === "USD"
          ? t("settingsFxUsdFixed")
          : t("settingsFxRate", { currency: rate.currency_code });
        const input = document.createElement("input");
        input.type = "number";
        input.step = "any";
        input.min = "0";
        input.dataset.fxCurrency = rate.currency_code;
        input.value = rate.rate_per_usd ?? "";
        input.disabled = !rate.editable;
        label.append(title, input);
        fields.appendChild(label);
      });
    }
    if (currencies) {
      currencies.replaceChildren();
      fxRates.forEach(rate => {
        const option = document.createElement("option");
        option.value = rate.currency_code;
        option.textContent = rate.currency_code;
        currencies.appendChild(option);
      });
    }
    updateFxCalculator();
    const showAll = document.getElementById("fx-show-all");
    const cancel = document.getElementById("fx-cancel");
    if (showAll) showAll.textContent = t(showAllFxRates ? "settingsFxCollapse" : "settingsFxManage");
    if (cancel) cancel.hidden = !showAllFxRates;
  }

  function updateFxCalculator() {
    const output = document.getElementById("fx-calculator-result");
    const amount = Number(document.getElementById("fx-calculator-amount")?.value);
    const code = document.getElementById("fx-calculator-currency")?.value;
    const rate = fxRates.find(item => item.currency_code === code)?.rate_per_usd;
    if (!output) return;
    if (!Number.isFinite(amount) || !rate || Number(rate) <= 0) {
      output.textContent = t("settingsFxUnavailable");
      return;
    }
    output.textContent = t("settingsFxResult", { amount, currency: code, usd: (amount / Number(rate)).toFixed(2), rate });
  }

  function renderGoogleSheetsResult(data, message = "") {
    const labels = { CONNECTED: "settingsConnected", AUTH_REQUIRED: "settingsAuthRequired", NOT_CONNECTED: "settingsNotConnected", NOT_CONFIGURED: "settingsNotConfigured" };
    setSyncText("google-sheets-status", labels[data?.status] ? t(labels[data.status]) : data?.status || t("settingsNotConfigured"));
    const result = document.getElementById("google-sheets-result");
    if (result) {
      result.hidden = false;
      result.textContent = message || (data?.error ? t("settingsOperationNotRun", { reason: data.error }) : t("googleSheetsSaved"));
    }
  }

  function renderFeishuChatStatus(data) {
    const labels = {
      disabled: "settingsDisabled",
      connecting: "settingsConnecting",
      connected: "settingsConnected",
      error: "settingsConnectionFailed",
    };
    const state = String(data?.state || "disabled");
    setSyncText("feishu-chat-status", labels[state] ? t(labels[state]) : t("settingsUnknown"));
    setSyncText("feishu-chat-transport", data?.transport === "long_connection" ? t("settingsFeishuLongConnection") : "--");
    setSyncText("feishu-chat-bot", data?.bot_enabled ? t("settingsEnabled") : t("settingsDisabled"));
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
        ? t("settingsFeishuChatTestPassed")
        : operation === "disable"
          ? t("settingsFeishuChatStopped")
          : data?.state === "connected"
            ? t("settingsFeishuChatConnected")
            : t("settingsFeishuChatConnecting");
    } else {
      const code = String(data?.error_code || data?.last_error_code || "LONG_CONNECTION_FAILED");
      const guidance = {
        INVALID_APP_CREDENTIALS: "settingsFeishuCredentialsInvalid",
        FEISHU_CHAT_INVALID_CREDENTIALS: "settingsFeishuCredentialsInvalid",
        SDK_NOT_AVAILABLE: "settingsFeishuSdkUnavailable",
        BOT_CAPABILITY_NOT_ENABLED: "settingsFeishuBotCapabilityMissing",
        BOT_PERMISSION_MISSING: "settingsFeishuBotPermissionMissing",
        FEISHU_CHAT_PERMISSION_DENIED: "settingsFeishuBotPermissionMissing",
        EVENT_PERMISSION_MISSING: "settingsFeishuEventPermissionMissing",
        FEISHU_CHAT_EVENT_CONFIGURATION_ERROR: "settingsFeishuEventConfigurationError",
        FEISHU_CHAT_NETWORK_ERROR: "settingsFeishuNetworkError",
        FEISHU_CHAT_CONNECT_TIMEOUT: "settingsFeishuConnectTimeout",
        FEISHU_CHAT_SDK_ERROR: "settingsFeishuSdkError",
        LONG_CONNECTION_FAILED: "settingsFeishuLongConnectionFailed",
      };
      message.textContent = t("settingsFeishuChatFailed", { code, guidance: t(guidance[code] || "settingsFeishuReviewLogs") });
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
    return table === "creator" ? "Creator" : table === "account" ? "Creator Account" : t("settingsUnknown");
  }

  function renderSchemaValidationDetails(data) {
    const missing = Array.isArray(data?.missing_fields) ? data.missing_fields : [];
    const incompatible = Array.isArray(data?.incompatible_fields) ? data.incompatible_fields : [];
    const lines = [t("settingsFeishuSchemaNeedsReview")];
    for (const table of ["creator", "account"]) {
      const fields = missing
        .filter(item => item?.table === table && item?.field)
        .map(item => String(item.field));
      if (fields.length) {
        lines.push("", t("settingsFeishuMissingFields", { table: schemaTableLabel(table) }), ...fields.map(field => `- ${field}`));
      }
    }
    for (const table of ["creator", "account"]) {
      const fields = incompatible.filter(item => item?.table === table && item?.field);
      if (fields.length) {
        lines.push("", t("settingsFeishuIncompatibleFields", { table: schemaTableLabel(table) }));
        lines.push(...fields.map(item => `- ${t("settingsFeishuCurrentType", { field: String(item.field), type: String(item.actual_type ?? t("settingsUnknown")) })}`));
      }
    }
    return lines.join("\n");
  }

  function renderSyncResult(data, operation) {
    const status = String(data?.status || "failed");
    const connectionLabel = data?.connection_ok === false
      ? t("settingsConfigurationError")
      : status === "failed"
        ? t("settingsUnavailable")
        : status === "blocked"
          ? t("settingsNeedsAttention")
          : t("settingsAvailable");
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
        ? t("settingsFeishuSyncComplete", { creatorCreated: data.creator_created || 0, creatorUpdated: data.creator_updated || 0, accountCreated: data.account_created || 0, accountUpdated: data.account_updated || 0, relationUpdated: data.relation_updated || 0 })
        : operation === "validate" ? t("settingsFeishuValidationPassed") : t("settingsFeishuDryRunComplete");
    } else if (status === "partial") {
      message.textContent = t("settingsFeishuSyncPartial", { count: Number(data.creator_failed || 0) + Number(data.account_failed || 0) });
    } else {
      const reason = data?.blocked_reason || data?.error_codes?.[0] || "FEISHU_SYNC_FAILED";
      const hasSchemaDetails = (data?.missing_fields?.length || 0) + (data?.incompatible_fields?.length || 0) > 0;
      message.textContent = reason === "FEISHU_SCHEMA_INVALID" && hasSchemaDetails
        ? renderSchemaValidationDetails(data)
        : t("settingsOperationNotRun", { reason });
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
      message.textContent = t("settingsResetPreviewDone");
    } else if (data?.status === "success") {
      message.textContent = t("settingsResetDone", { backup: String(data?.backup?.filename || "--") });
    } else {
      const review = Array.isArray(data?.review_items) ? data.review_items.join(t("settingsListSeparator")) : "";
      message.textContent = t("settingsOperationNotRun", { reason: review || data?.error || "CLEAN_RESET_FAILED" });
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

  function renderStorageMigration(data) {
    const authority = String(data?.authority || "legacy_excel");
    const labels = { legacy_excel: "Excel", sqlite_active: "SQLite", migration_error: "settingsMigrationError", unsupported_schema: "settingsUnsupportedSchema" };
    setSyncText("storage-migration-authority", labels[authority]?.startsWith("settings") ? t(labels[authority]) : labels[authority] || authority);
    setSyncText("storage-migration-status", data?.migration_status || data?.status || "--");
    setSyncText("storage-migration-id", data?.migration_id || "--");
    setSyncText("storage-migration-backup", data?.backup?.filename || (data?.backup_ready ? t("settingsCreated") : "--"));
    const message = document.getElementById("storage-migration-result");
    if (message) {
      message.hidden = false;
      message.dataset.status = data?.status === "success" || data?.status === "ready_for_activation" ? "success" : String(data?.status || "");
      if (data?.status === "ready_for_activation") {
        const counts = data.counts || {};
        message.textContent = t("settingsMigrationReady", { creators: counts.creators || 0, accounts: counts.creator_accounts || 0, campaigns: counts.campaigns || 0 });
      } else if (authority === "sqlite_active") {
        message.textContent = t("settingsSqliteActive");
      } else if (data?.status === "cancelled") {
        message.textContent = t("settingsMigrationCancelled");
      } else if (data?.error) {
        message.textContent = t("settingsOperationNotRun", { reason: String(data.error) });
      } else {
        message.textContent = data?.migration_required ? t("settingsMigrationDetected") : t("settingsMigrationNotRequired");
      }
    }
    const prepared = data?.status === "ready_for_activation" && data?.confirmation_token;
    storageMigrationPreview = prepared ? data : null;
    const confirm = document.getElementById("storage-migration-confirm");
    const cancel = document.getElementById("storage-migration-cancel");
    const prepare = document.getElementById("storage-migration-prepare");
    const recover = document.getElementById("storage-migration-recover");
    if (confirm) confirm.disabled = !prepared;
    if (cancel) cancel.disabled = !prepared;
    if (prepare) prepare.disabled = authority === "sqlite_active";
    if (recover) recover.hidden = data?.migration_status !== "activation_recovery_required";
  }

  async function loadStorageMigrationStatus(api, options = {}) {
    const data = await api.get("/api/settings/storage-migration/status", options);
    renderStorageMigration(data);
    return data;
  }

  async function postStorageMigration(api, operation, payload = {}) {
    const data = await api.post(`/api/settings/storage-migration/${operation}`, {
      session_id: storageMigrationSession,
      ...payload,
    }, { signal: resources.signal });
    renderStorageMigration(data);
    return data;
  }
  const settingsPage = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      cleanResetPreview = null;
      storageMigrationPreview = null;
      await reloadSettings();
      if (typeof global.KOLConnectAPI?.get === "function") {
        try {
          const chatStatus = await loadFeishuChatStatus(
            global.KOLConnectAPI,
            { signal: resources.signal },
          );
          if (chatStatus?.state === "connecting") startFeishuChatPolling(global.KOLConnectAPI);
          await loadStorageMigrationStatus(global.KOLConnectAPI, { signal: resources.signal });
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
        const language = app.valueOf("ui-language");
        try {
          // Keep the selected locale as the live authority even if a later
          // settings read returns an older persisted snapshot.
          app.setLanguage(language, { refreshCurrent: false });
          await api.post("/api/settings/ui", {
            language,
            debug_mode: app.checkedOf("debug-mode"),
          }, { signal: resources.signal });
          await api.post("/api/settings/profiles", {
            selected: app.valueOf("default-profile"),
          }, { signal: resources.signal });
          app.showSaved();
          await reloadSettings();
        } catch (error) {
          handleError(error);
        }
      });

      listen("fx-save", "click", async () => {
        try {
          const rates = Object.fromEntries(fxRates
            .filter(rate => rate.currency_code !== "USD" && rate.rate_per_usd != null)
            .map(rate => [rate.currency_code, rate.rate_per_usd]));
          document.querySelectorAll("[data-fx-currency]").forEach(input => {
            if (input.dataset.fxCurrency === "USD") return;
            const raw = String(input.value || "").trim();
            if (!raw) { delete rates[input.dataset.fxCurrency]; return; }
            const value = Number(raw);
            if (!Number.isFinite(value) || value <= 0) throw new Error(app.t("settingsExchangeRateInvalid", { currency: input.dataset.fxCurrency }));
            rates[input.dataset.fxCurrency] = value;
          });
          const data = await api.post("/api/settings/fx", { rates }, { signal: resources.signal });
          renderFxSettings(data);
          app.showSaved(app.t("settingsExchangeRateSaved"));
        } catch (error) {
          handleError(error);
        }
      });

      listen("fx-show-all", "click", () => {
        showAllFxRates = !showAllFxRates;
        renderFxSettings({ rates: fxRates });
      });
      listen("fx-cancel", "click", () => { showAllFxRates = false; renderFxSettings({ rates: fxRates }); });

      for (const id of ["fx-calculator-amount", "fx-calculator-currency"]) {
        listen(id, "input", updateFxCalculator);
        listen(id, "change", updateFxCalculator);
      }

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

      listen("google-sheets-save", "click", async () => {
        try {
          await api.post("/api/settings/google-sheets", {
            client_id: app.valueOf("google-sheets-client-id").trim(),
            client_secret: app.valueOf("google-sheets-client-secret").trim(),
            spreadsheet_id: app.valueOf("google-sheets-spreadsheet-id").trim(),
          }, { signal: resources.signal });
          const data = await reloadSettings();
          renderGoogleSheetsResult(data.google_sheets, app.t("googleSheetsSaved"));
        } catch (error) { handleError(error); }
      });

      listen("google-sheets-connect", "click", async () => {
        try {
          const data = await api.post("/api/google-sheets/connect", {}, { signal: resources.signal });
          renderGoogleSheetsResult(data, app.t("googleSheetsConnected"));
        } catch (error) { handleError(error); }
      });

      listen("google-sheets-disconnect", "click", async () => {
        try {
          const data = await api.post("/api/google-sheets/disconnect", {}, { signal: resources.signal });
          renderGoogleSheetsResult(data, app.t("googleSheetsDisconnected"));
        } catch (error) { handleError(error); }
      });

      listen("google-sheets-sync", "click", async () => {
        try {
          const data = await api.post("/api/google-sheets/sync", {}, { signal: resources.signal });
          const completed = (data.worksheets || []).filter(item => item.status === "SUCCESS").length;
          renderGoogleSheetsResult(data, app.t("googleSheetsSynced", { count: completed }));
        } catch (error) {
          if (error?.responseData?.error === "AUTH_REQUIRED") {
            renderGoogleSheetsResult({ status: "AUTH_REQUIRED" }, app.t("googleSheetsAuthRequired"));
          } else handleError(error);
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
          t("settingsFeishuSyncConfirm"),
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
      listen("storage-migration-check", "click", async () => {
        try { await loadStorageMigrationStatus(api, { signal: resources.signal }); } catch (error) { handleError(error); }
      });
      listen("storage-migration-prepare", "click", async () => {
        storageMigrationPreview = null;
        try { await postStorageMigration(api, "prepare"); } catch (error) { handleError(error); }
      });
      listen("storage-migration-confirm", "click", async () => {
        if (!storageMigrationPreview) return;
        const confirmed = global.confirm(t("settingsMigrationConfirmText"));
        if (!confirmed) return;
        const preview = storageMigrationPreview;
        storageMigrationPreview = null;
        try {
          await postStorageMigration(api, "confirm", {
            confirm: true,
            migration_id: preview.migration_id,
            confirmation_token: preview.confirmation_token,
          });
        } catch (error) { handleError(error); }
      });
      listen("storage-migration-cancel", "click", async () => {
        if (!storageMigrationPreview) return;
        const preview = storageMigrationPreview;
        storageMigrationPreview = null;
        try {
          await postStorageMigration(api, "cancel", {
            migration_id: preview.migration_id,
            confirmation_token: preview.confirmation_token,
          });
        } catch (error) { handleError(error); }
      });
      listen("storage-migration-recover", "click", async () => {
        const migrationId = document.getElementById("storage-migration-id")?.textContent || "";
        try { await postStorageMigration(api, "recover", { migration_id: migrationId }); } catch (error) { handleError(error); }
      });

      listen("clean-reset-execute", "click", async () => {
        if (!cleanResetPreview) return;
        const summary = cleanResetPreview.summary || {};
        const confirmed = global.confirm(
          t("settingsResetConfirm", { creators: summary.creators || 0, accounts: summary.accounts || 0, videos: summary.videos || 0, snapshots: summary.snapshots || 0, campaigns: summary.campaigns || 0 }),
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
          app.showSaved(t("settingsBackupCreated"));
        } catch (error) {
          handleError(error);
        } finally {
          if (button) button.disabled = false;
        }
      });

      listen("ui-language", "change", () => {
        app.setLanguage(app.valueOf("ui-language"), { refreshCurrent: false });
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
