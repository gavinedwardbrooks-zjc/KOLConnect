(function initializePassiveCaptureMain(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports && typeof window === "undefined") {
    module.exports = api;
  } else {
    root.__kolconnectPassiveCaptureMainScriptV1__ = "executing";
    try {
      const protocol = root.KOLConnectPassiveCaptureProtocol;
      const alreadyInstalled = Boolean(root[api.INSTALL_MARKER]);
      const installed = api.installMainWorldCapture(root, protocol);
      root.__kolconnectPassiveCaptureMainScriptV1__ = installed
        ? "installed"
        : !root
          ? "skipped_target_unavailable"
          : !protocol
            ? "skipped_protocol_unavailable"
            : alreadyInstalled
              ? "skipped_already_installed"
              : "skipped";
      root.__kolconnectPassiveCaptureMainErrorV1__ = "";
    } catch (error) {
      root.__kolconnectPassiveCaptureMainScriptV1__ = "failed";
      root.__kolconnectPassiveCaptureMainErrorV1__ = String(error?.name || "Error");
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createMainCaptureApi() {
  "use strict";

  const INSTALL_MARKER = "__kolconnectPassiveCaptureMainV1__";

  function requestUrl(input) {
    if (typeof input === "string") return input;
    if (input && typeof input.url === "string") return input.url;
    return String(input || "");
  }

  function requestMethod(input, init) {
    return String(init?.method || input?.method || "GET").toUpperCase();
  }

  function installMainWorldCapture(target, protocol) {
    if (!target || !protocol || target[INSTALL_MARKER]) return false;

    const bridgeToken = protocol.createBridgeToken(target.crypto);
    const origin = target.location?.origin;
    const pending = [];
    let generation = 0;
    // Document-lifetime counters only: never retain URLs, payloads or tokens.
    const counters = { fetch_interceptions: 0, xhr_interceptions: 0,
      target_matches: 0, envelopes_emitted: 0, envelopes_replayed: 0 };
    const matchedFamilies = { tiktok_item_list: 0, tiktok_user_detail: 0, tiktok_comment_list: 0 };
    const misses = { profile_missing: 0, old_generation: 0, response_unavailable: 0,
      response_rejected: 0, redirect_mismatch: 0, clone_failed: 0,
      body_too_large: 0, decode_failed: 0, emit_failed: 0, observation_failed: 0,
      xhr_response_type: 0 };
    let fetchWrapper, xhrOpenWrapper, xhrSendWrapper;
    const context = () => ({
      profile: protocol.profileUsername(target.location?.href),
      observedAt: new Date().toISOString(),
      generation,
    });
    Object.defineProperty(target, "KOLConnectPassiveCaptureControl", {
      value: Object.freeze({
        token: () => bridgeToken,
        replay: () => pending.splice(0).forEach((message) => {
          target.postMessage(message, origin); counters.envelopes_replayed += 1;
        }),
        reset: () => { pending.length = 0; generation += 1; },
        diagnostics: () => ({ installed: Boolean(target[INSTALL_MARKER]),
          fetch_wrapper_current: Boolean(fetchWrapper && target.fetch === fetchWrapper),
          xhr_open_wrapper_current: Boolean(xhrOpenWrapper && target.XMLHttpRequest?.prototype.open === xhrOpenWrapper),
          xhr_send_wrapper_current: Boolean(xhrSendWrapper && target.XMLHttpRequest?.prototype.send === xhrSendWrapper),
          ...counters, matched_families: { ...matchedFamilies }, misses: { ...misses }, pending_envelopes: pending.length, generation }),
      }),
    });


    function emit(endpointKind, method, payload, captured) {
      try {
        if (!captured?.profile) { misses.profile_missing += 1; return; }
        if (captured.generation !== generation) { misses.old_generation += 1; return; }
        const envelope = protocol.createCaptureEnvelope({
          bridgeToken,
          endpointKind,
          method,
          payload,
          profile: captured.profile,
          observedAt: captured.observedAt,
        });
        pending.push(envelope);
        if (pending.length > 10) pending.shift();
        target.postMessage(envelope, origin);
        counters.envelopes_emitted += 1;
      } catch (_error) {
        misses.emit_failed += 1;
        // Capture must never affect page networking.
      }
    }

    function observeFetch(input, init, response, captured) {
      const endpointKind = protocol.matchTikTokEndpoint(
        requestUrl(input),
        target.location?.href,
      );
      if (!endpointKind) return;
      counters.target_matches += 1;
      matchedFamilies[endpointKind] += 1;
      if (!response || typeof response.clone !== "function") { misses.response_unavailable += 1; return; }
      if (response.ok === false || Number(response.headers?.get?.("content-length")) > 3_000_000) { misses.response_rejected += 1; return; }
      if (response.url && protocol.matchTikTokEndpoint(response.url, target.location?.href) !== endpointKind) { misses.redirect_mismatch += 1; return; }

      let clone;
      try {
        clone = response.clone();
      } catch (_error) {
        misses.clone_failed += 1;
        return;
      }
      Promise.resolve()
        .then(async () => {
          if (!clone.body?.getReader) return clone.json();
          const reader = clone.body.getReader();
          const decoder = new TextDecoder();
          let size = 0, text = "";
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              size += value.byteLength;
              if (size > 3_000_000) { misses.body_too_large += 1; reader.cancel().catch(() => {}); return null; }
              text += decoder.decode(value, { stream: true });
            }
            return JSON.parse(text + decoder.decode());
          } finally { reader.releaseLock(); }
        })
        .then((payload) => emit(endpointKind, requestMethod(input, init), payload, captured))
        .catch(() => { misses.decode_failed += 1; });
    }

    if (typeof target.fetch === "function") {
      const originalFetch = target.fetch;
      target.fetch = function kolconnectPassiveFetch(...args) {
        counters.fetch_interceptions += 1;
        let captured;
        try { captured = context(); } catch (_) {}
        let requestPromise;
        try {
          requestPromise = Reflect.apply(originalFetch, this, args);
        } catch (error) {
          throw error;
        }
        return Promise.resolve(requestPromise).then((response) => {
          try {
            observeFetch(args[0], args[1], response, captured);
          } catch (_error) {
            misses.observation_failed += 1;
            // Preserve the original response even if observation fails.
          }
          return response;
        });
      };
      fetchWrapper = target.fetch;
    }

    const Xhr = target.XMLHttpRequest;
    if (Xhr?.prototype && typeof Xhr.prototype.open === "function" && typeof Xhr.prototype.send === "function") {
      const metadata = new WeakMap();
      const originalOpen = Xhr.prototype.open;
      const originalSend = Xhr.prototype.send;

      Xhr.prototype.open = function kolconnectPassiveXhrOpen(method, url, ...rest) {
        const result = Reflect.apply(originalOpen, this, [method, url, ...rest]);
        try { metadata.set(this, { method: String(method || "GET").toUpperCase(), url }); } catch (_) {}
        return result;
      };

      Xhr.prototype.send = function kolconnectPassiveXhrSend(...args) {
        counters.xhr_interceptions += 1;
        const xhr = this;
        try {
        const captured = context();
        const request = metadata.get(xhr);
        const endpointKind = protocol.matchTikTokEndpoint(
          request?.url,
          target.location?.href,
        );
        if (endpointKind) { counters.target_matches += 1; matchedFamilies[endpointKind] += 1; }
        if (endpointKind && typeof xhr.addEventListener === "function") {
          xhr.addEventListener("loadend", function observeCompletedXhr() {
            try {
              if (xhr.status < 200 || xhr.status >= 300) { misses.response_rejected += 1; return; }
              let payload;
              if (xhr.responseType === "json") {
                payload = xhr.response;
              } else if (!xhr.responseType || xhr.responseType === "text") {
                if (xhr.responseText.length > 3_000_000) { misses.body_too_large += 1; return; }
                payload = JSON.parse(xhr.responseText);
              } else {
                misses.xhr_response_type += 1;
                return;
              }
              if (payload !== null && typeof payload === "object") {
                emit(endpointKind, request.method, payload, captured);
              }
            } catch (_error) {
              misses.decode_failed += 1;
              // Malformed or unavailable response data is a capture miss only.
            }
          }, { once: true });
        }
        } catch (_) { misses.observation_failed += 1; /* Preserve original send. */ }
        return Reflect.apply(originalSend, xhr, args);
      };
      xhrOpenWrapper = Xhr.prototype.open;
      xhrSendWrapper = Xhr.prototype.send;
    }

    Object.defineProperty(target, INSTALL_MARKER, {
      configurable: false,
      enumerable: false,
      value: true,
      writable: false,
    });

    return true;
  }

  return Object.freeze({ INSTALL_MARKER, installMainWorldCapture });
});
