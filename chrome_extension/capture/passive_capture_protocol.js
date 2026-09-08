(function initializePassiveCaptureProtocol(root, factory) {
  const isCommonJs = typeof module === "object"
    && module.exports
    && typeof window === "undefined";
  if (!isCommonJs) root.__kolconnectPassiveCaptureProtocolScriptV1__ = "executing";
  try {
    const api = factory();
    if (isCommonJs) {
      module.exports = api;
    } else {
      root.KOLConnectPassiveCaptureProtocol = api;
      root.__kolconnectPassiveCaptureProtocolScriptV1__ = "exposed";
      root.__kolconnectPassiveCaptureProtocolErrorV1__ = "";
    }
  } catch (error) {
    if (isCommonJs) throw error;
    root.__kolconnectPassiveCaptureProtocolScriptV1__ = "failed";
    root.__kolconnectPassiveCaptureProtocolErrorV1__ = String(error?.name || "Error");
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createProtocol() {
  "use strict";

  const NAMESPACE = "kolconnect.passive-capture.v1";
  const BOOTSTRAP_REQUEST_TYPE = "bridge-bootstrap-request";
  const BOOTSTRAP_TYPE = "bridge-bootstrap";
  const CAPTURE_TYPE = "network-capture";
  const PLATFORM = "tiktok";
  const ALLOWED_HOSTS = new Set([
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
  ]);
  const ENDPOINTS = Object.freeze({
    "/api/post/item_list/": "tiktok_item_list",
    "/api/user/detail/": "tiktok_user_detail",
    "/api/comment/list/": "tiktok_comment_list",
  });
  const ENDPOINT_KINDS = new Set(Object.values(ENDPOINTS));
  const SENSITIVE_KEY = /^(?:authorization|cookie|cookies|credentials?|headers?|query|querystring|signature|x[-_]?bogus|ms[-_]?token|device[-_]?id|raw[-_]?(?:request|response)|request[-_]?url|response[-_]?url|full[-_]?url)$/i;
  const TOKEN_PATTERN = /^[a-f0-9]{32}$/;

  function matchTikTokEndpoint(rawUrl, baseUrl) {
    try {
      const parsed = new URL(rawUrl, baseUrl);
      if (parsed.protocol !== "https:" || !ALLOWED_HOSTS.has(parsed.hostname.toLowerCase())) {
        return null;
      }
      return ENDPOINTS[parsed.pathname] || null;
    } catch (_error) {
      return null;
    }
  }

  function endpointPathname(endpointKind) {
    for (const [pathname, kind] of Object.entries(ENDPOINTS)) {
      if (kind === endpointKind) return pathname;
    }
    return null;
  }

  function createBridgeToken(cryptoObject) {
    if (!cryptoObject || typeof cryptoObject.getRandomValues !== "function") {
      throw new Error("A cryptographically strong random source is required");
    }
    const bytes = new Uint8Array(16);
    cryptoObject.getRandomValues(bytes);
    return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  }

  function sanitizeString(value) {
    if (!/^https?:\/\//i.test(value)) return value;
    try {
      return new URL(value).pathname;
    } catch (_error) {
      return "";
    }
  }

  function sanitizePayload(value, seen) {
    if (value === null || typeof value === "boolean" || typeof value === "number") {
      return value;
    }
    if (typeof value === "string") return sanitizeString(value);
    if (typeof value !== "object") return null;

    const visited = seen || new WeakSet();
    if (visited.has(value)) return null;
    visited.add(value);

    if (Array.isArray(value)) {
      return value.map((item) => sanitizePayload(item, visited));
    }

    const sanitized = {};
    for (const [key, item] of Object.entries(value)) {
      if (SENSITIVE_KEY.test(key)) continue;
      sanitized[key] = sanitizePayload(item, visited);
    }
    return sanitized;
  }

  function createBootstrapEnvelope(bridgeToken) {
    return {
      namespace: NAMESPACE,
      type: BOOTSTRAP_TYPE,
      bridgeToken,
    };
  }

  function createBootstrapRequestEnvelope() {
    return {
      namespace: NAMESPACE,
      type: BOOTSTRAP_REQUEST_TYPE,
    };
  }

  // Only the item-list contract is consumed. Other observed endpoint families
  // deliberately carry no user/contact/comment payload into the extension.
  function sanitizeCapturePayload(payload, endpointKind) {
    if (endpointKind !== "tiktok_item_list") return {};
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.itemList)) return {};
    const scalar = (value, limit = 2000) => (
      typeof value === "string" ? value.slice(0, limit)
        : typeof value === "number" && Number.isFinite(value) ? value : null
    );
    const counts = (value) => {
      const result = {};
      for (const key of ["playCount", "diggCount", "commentCount", "shareCount"]) {
        if (value && Object.prototype.hasOwnProperty.call(value, key)) result[key] = scalar(value[key], 32);
      }
      return result;
    };
    return {
      cursor: typeof payload.cursor === "string" ? payload.cursor.slice(0, 128) : null,
      hasMore: typeof payload.hasMore === "boolean" ? payload.hasMore : null,
      itemList: payload.itemList.slice(0, 100).map((item) => {
        const result = {};
        if (!item || typeof item !== "object") return result;
        for (const key of ["id", "desc", "createTime"]) {
          if (Object.prototype.hasOwnProperty.call(item, key)) result[key] = scalar(item[key]);
        }
        result.stats = counts(item.stats);
        result.statsV2 = counts(item.statsV2);
        if (typeof item.author?.uniqueId === "string" && /^[A-Za-z0-9._]{1,128}$/.test(item.author.uniqueId)) {
          result.author = { uniqueId: item.author.uniqueId };
        }
        if (typeof item.isPinnedItem === "boolean") result.isPinnedItem = item.isPinnedItem;
        return result;
      }),
    };
  }

  function profileUsername(rawUrl) {
    try {
      const url = new URL(rawUrl);
      if (!ALLOWED_HOSTS.has(url.hostname.toLowerCase()) || url.protocol !== "https:") return "";
      return url.pathname.match(/^\/@([A-Za-z0-9._]{1,128})\/?$/)?.[1] || "";
    } catch (_) { return ""; }
  }

  function createCaptureEnvelope({ bridgeToken, endpointKind, method, payload, profile = "", observedAt = "" }) {
    return {
      namespace: NAMESPACE,
      type: CAPTURE_TYPE,
      bridgeToken,
      platform: PLATFORM,
      endpointKind,
      method: String(method || "GET").toUpperCase(),
      pathname: endpointPathname(endpointKind),
      profile,
      observedAt,
      payload: sanitizeCapturePayload(payload, endpointKind),
    };
  }

  function isValidToken(value) {
    return typeof value === "string" && TOKEN_PATTERN.test(value);
  }

  function isValidBootstrapEnvelope(value) {
    return Boolean(
      value
      && typeof value === "object"
      && value.namespace === NAMESPACE
      && value.type === BOOTSTRAP_TYPE
      && isValidToken(value.bridgeToken)
    );
  }

  function isValidBootstrapRequestEnvelope(value) {
    return Boolean(
      value
      && typeof value === "object"
      && value.namespace === NAMESPACE
      && value.type === BOOTSTRAP_REQUEST_TYPE
    );
  }

  function isPayloadShapeValid(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isValidCaptureEnvelope(value, expectedToken) {
    if (!value || typeof value !== "object") return false;
    if (value.namespace !== NAMESPACE || value.type !== CAPTURE_TYPE) return false;
    if (!isValidToken(expectedToken) || value.bridgeToken !== expectedToken) return false;
    if (value.platform !== PLATFORM || !ENDPOINT_KINDS.has(value.endpointKind)) return false;
    if (value.pathname !== endpointPathname(value.endpointKind)) return false;
    if (typeof value.method !== "string" || !/^[A-Z]{1,16}$/.test(value.method)) return false;
    if (typeof value.profile !== "string" || !/^[A-Za-z0-9._]{1,128}$/.test(value.profile)) return false;
    if (typeof value.observedAt !== "string" || value.observedAt.length > 32 || !Number.isFinite(Date.parse(value.observedAt))) return false;
    return isPayloadShapeValid(value.payload);
  }

  return Object.freeze({
    ALLOWED_HOSTS,
    BOOTSTRAP_REQUEST_TYPE,
    BOOTSTRAP_TYPE,
    CAPTURE_TYPE,
    ENDPOINTS,
    NAMESPACE,
    PLATFORM,
    createBootstrapEnvelope,
    createBootstrapRequestEnvelope,
    createBridgeToken,
    createCaptureEnvelope,
    endpointPathname,
    isValidBootstrapEnvelope,
    isValidBootstrapRequestEnvelope,
    isValidCaptureEnvelope,
    matchTikTokEndpoint,
    profileUsername,
    sanitizeCapturePayload,
    sanitizePayload,
  });
});
