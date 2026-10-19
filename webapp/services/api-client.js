(function createApiClient(global) {
  "use strict";

  function message(key, fallback, params) {
    const localized = global.KOLConnectI18n?.t?.(key, params);
    return localized && !localized.startsWith("[missing:") ? localized : fallback;
  }

  function connectionError() {
    return message("apiServerUnreachable", "无法连接 KOLConnect 服务，请确认程序正在运行。");
  }

  function serverError() {
    return message("apiServerError", "服务处理请求时发生错误，请稍后重试。");
  }

  function responseError() {
    return message("apiInvalidResponse", "服务返回了无法识别的响应，请稍后重试。");
  }

  function traceReference(traceId) {
    return message("apiErrorReference", "错误参考：{trace_id}", { trace_id: traceId });
  }

  function domainErrorMessage(code, fallback) {
    const keys = {
      GMAIL_AUTH_REJECTED: "mailGmailAuthRejected",
      GMAIL_APP_PASSWORD_MAY_BE_REQUIRED: "mailGmailAppPasswordMayBeRequired",
      GMAIL_WEB_LOGIN_REQUIRED: "mailGmailWebLoginRequired",
      CHROME_BINARY_NOT_FOUND: "chromeBinaryNotFound",
      CHROME_PROFILE_NOT_FOUND: "chromeProfileNotFound",
      CHROME_PROFILE_LOCKED: "chromeProfileLocked",
      CHROME_LAUNCH_FAILED: "chromeLaunchFailed",
      CHROME_CONFIG_INVALID: "chromeConfigInvalid",
    };
    return keys[code] ? message(keys[code], fallback) : fallback;
  }

  async function localServiceDiagnosis() {
    const diagnose = global.pywebview?.api?.local_service_status;
    if (typeof diagnose !== "function") return null;
    try {
      return await diagnose(global.location?.href || "");
    } catch (_error) {
      return { reachable: false, code: "DESKTOP_BRIDGE_FAILED" };
    }
  }

  function waitForRetry(milliseconds) {
    const scheduler = global.setTimeout || (typeof setTimeout === "function" ? setTimeout : null);
    return scheduler ? new Promise(resolve => scheduler(resolve, milliseconds)) : Promise.resolve();
  }

  async function request(method, url, options = {}) {
    const headers = { ...(options.headers || {}) };
    const init = {
      method,
      cache: options.cache || "no-store",
      headers,
      signal: options.signal,
    };

    if (Object.prototype.hasOwnProperty.call(options, "payload")) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
      init.body = JSON.stringify(options.payload);
    } else if (Object.prototype.hasOwnProperty.call(options, "body")) {
      init.body = options.body;
    }

    let response;
    let networkError;
    const attempts = method === "GET" ? 2 : 1;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        response = await global.fetch(url, init);
        networkError = null;
        break;
      } catch (error) {
        if (error && error.name === "AbortError") throw error;
        networkError = error;
        if (attempt + 1 < attempts) await waitForRetry(150);
      }
    }
    if (!response) {
      const diagnosis = await localServiceDiagnosis();
      const code = String(diagnosis?.code || "SERVER_UNREACHABLE");
      const diagnosticKey = {
        LOCAL_SERVICE_NOT_READY: "localServiceNotReady",
        LOCAL_SERVICE_PORT_CONFLICT: "localServicePortConflict",
        LOCAL_SERVICE_CONNECTION_REFUSED: "localServiceConnectionRefused",
        LOCAL_SERVICE_TIMEOUT: "localServiceTimeout",
        LOCAL_SERVICE_BACKEND_EXITED: "localServiceBackendExited",
        LOCAL_SERVICE_URL_MISMATCH: "localServiceUrlMismatch",
        DESKTOP_BRIDGE_FAILED: "desktopBridgeFailed",
      }[code];
      const requestError = new Error(diagnosticKey ? message(diagnosticKey, connectionError()) : connectionError());
      requestError.code = code;
      requestError.kind = "connection";
      requestError.cause = networkError;
      requestError.diagnostics = diagnosis;
      throw requestError;
    }

    let data;
    try {
      data = await response.json();
    } catch (_error) {
      const requestError = new Error(responseError());
      requestError.code = "INVALID_SERVER_RESPONSE";
      requestError.status = response.status;
      throw requestError;
    }

    if (!response.ok) {
      const structuredMessage = typeof data?.error === "object" ? data.error?.message : "";
      const legacyMessage = typeof data?.error === "string" ? data.error : "";
      const code = typeof data?.error === "object" ? data.error?.code : "";
      const isServerError = code === "INTERNAL_SERVER_ERROR" || (response.status >= 500 && !code);
      const baseMessage = isServerError
        ? serverError()
        : domainErrorMessage(code, structuredMessage || legacyMessage || `${method} ${url} failed`);
      const traceSuffix = data?.trace_id ? `\n${traceReference(data.trace_id)}` : "";
      const error = new Error(`${baseMessage}${traceSuffix}`);
      error.responseData = data;
      error.status = response.status;
      error.code = code;
      error.kind = isServerError ? "server" : "domain";
      error.traceId = data?.trace_id || "";
      throw error;
    }
    return data;
  }

  global.KOLConnectAPI = Object.freeze({
    request,
    get(url, options = {}) {
      return request("GET", url, options);
    },
    post(url, payload, options = {}) {
      return request("POST", url, { ...options, payload });
    },
    postRaw(url, body, options = {}) {
      return request("POST", url, { ...options, body });
    },
    patch(url, payload, options = {}) {
      return request("PATCH", url, { ...options, payload });
    },
    getCreatorDeleteImpact(creatorId, options = {}) {
      return request(
        "GET",
        `/api/creator-library/${encodeURIComponent(creatorId)}/delete-impact`,
        options,
      );
    },
    deleteCreator(creatorId, payload, options = {}) {
      return request(
        "DELETE",
        `/api/creator-library/${encodeURIComponent(creatorId)}`,
        { ...options, payload },
      );
    },
    delete(url, options = {}) {
      return request("DELETE", url, options);
    },
  });
})(window);
