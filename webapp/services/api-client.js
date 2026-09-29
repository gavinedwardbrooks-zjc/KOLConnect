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
    };
    return keys[code] ? message(keys[code], fallback) : fallback;
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
    try {
      response = await global.fetch(url, init);
    } catch (error) {
      if (error && error.name === "AbortError") throw error;
      const requestError = new Error(connectionError());
      requestError.code = "SERVER_UNREACHABLE";
      requestError.kind = "connection";
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
      const isServerError = response.status >= 500 || code === "INTERNAL_SERVER_ERROR";
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
