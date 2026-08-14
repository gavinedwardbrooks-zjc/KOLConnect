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

  function createCaptureEnvelope({ bridgeToken, endpointKind, method, payload }) {
    return {
      namespace: NAMESPACE,
      type: CAPTURE_TYPE,
      bridgeToken,
      platform: PLATFORM,
      endpointKind,
      method: String(method || "GET").toUpperCase(),
      pathname: endpointPathname(endpointKind),
      payload: sanitizePayload(payload),
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
    return value !== null && typeof value === "object";
  }

  function isValidCaptureEnvelope(value, expectedToken) {
    if (!value || typeof value !== "object") return false;
    if (value.namespace !== NAMESPACE || value.type !== CAPTURE_TYPE) return false;
    if (!isValidToken(expectedToken) || value.bridgeToken !== expectedToken) return false;
    if (value.platform !== PLATFORM || !ENDPOINT_KINDS.has(value.endpointKind)) return false;
    if (value.pathname !== endpointPathname(value.endpointKind)) return false;
    if (typeof value.method !== "string" || !/^[A-Z]+$/.test(value.method)) return false;
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
    sanitizePayload,
  });
});
