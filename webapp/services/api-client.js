(function createApiClient(global) {
  "use strict";

  const CONNECTION_ERROR = "\u670d\u52a1\u8fde\u63a5\u5931\u8d25\uff0c\u8bf7\u786e\u8ba4 KOLConnect \u6b63\u5728\u8fd0\u884c\u3002";
  const RESPONSE_ERROR = "\u670d\u52a1\u8fd4\u56de\u5f02\u5e38\uff0c\u8bf7\u67e5\u770b\u7cfb\u7edf\u65e5\u5fd7\u4e2d\u7684\u8be6\u7ec6\u539f\u56e0\u3002";

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
      throw new Error(CONNECTION_ERROR);
    }

    let data;
    try {
      data = await response.json();
    } catch (_error) {
      throw new Error(RESPONSE_ERROR);
    }

    if (!response.ok) {
      const structuredMessage = typeof data?.error === "object" ? data.error?.message : "";
      const legacyMessage = typeof data?.error === "string" ? data.error : "";
      const baseMessage = structuredMessage || legacyMessage || `${method} ${url} failed`;
      const traceSuffix = data?.trace_id ? `\n\u9519\u8bef\u53c2\u8003\uff1a${data.trace_id}` : "";
      const error = new Error(`${baseMessage}${traceSuffix}`);
      error.responseData = data;
      error.status = response.status;
      error.code = typeof data?.error === "object" ? data.error?.code : "";
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
