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
    return app.loadSettingsState({ signal: resources?.signal });
  }

  function listen(id, type, listener) {
    const element = document.getElementById(id);
    if (element) resources.listen(element, type, listener);
  }

  const settingsPage = {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      await reloadSettings();
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
