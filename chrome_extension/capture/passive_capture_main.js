(function initializePassiveCaptureMain(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    api.installMainWorldCapture(root, root.KOLConnectPassiveCaptureProtocol);
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

    function postBootstrap() {
      try {
        target.postMessage(protocol.createBootstrapEnvelope(bridgeToken), origin);
      } catch (_error) {
        // A bridge bootstrap miss must not affect page execution.
      }
    }

    target.addEventListener("message", (event) => {
      try {
        if (event.source !== target || event.origin !== origin) return;
        if (protocol.isValidBootstrapRequestEnvelope(event.data)) postBootstrap();
      } catch (_error) {
        // Invalid bootstrap requests are ignored.
      }
    });

    function emit(endpointKind, method, payload) {
      try {
        const envelope = protocol.createCaptureEnvelope({
          bridgeToken,
          endpointKind,
          method,
          payload,
        });
        target.postMessage(envelope, origin);
      } catch (_error) {
        // Capture must never affect page networking.
      }
    }

    function observeFetch(input, init, response) {
      const endpointKind = protocol.matchTikTokEndpoint(
        requestUrl(input),
        target.location?.href,
      );
      if (!endpointKind || !response || typeof response.clone !== "function") return;

      let clone;
      try {
        clone = response.clone();
      } catch (_error) {
        return;
      }
      Promise.resolve()
        .then(() => clone.json())
        .then((payload) => emit(endpointKind, requestMethod(input, init), payload))
        .catch(() => {});
    }

    if (typeof target.fetch === "function") {
      const originalFetch = target.fetch;
      target.fetch = function kolconnectPassiveFetch(...args) {
        let requestPromise;
        try {
          requestPromise = Reflect.apply(originalFetch, this, args);
        } catch (error) {
          throw error;
        }
        return Promise.resolve(requestPromise).then((response) => {
          try {
            observeFetch(args[0], args[1], response);
          } catch (_error) {
            // Preserve the original response even if observation fails.
          }
          return response;
        });
      };
    }

    const Xhr = target.XMLHttpRequest;
    if (Xhr?.prototype && typeof Xhr.prototype.open === "function" && typeof Xhr.prototype.send === "function") {
      const metadata = new WeakMap();
      const originalOpen = Xhr.prototype.open;
      const originalSend = Xhr.prototype.send;

      Xhr.prototype.open = function kolconnectPassiveXhrOpen(method, url, ...rest) {
        const result = Reflect.apply(originalOpen, this, [method, url, ...rest]);
        metadata.set(this, { method: String(method || "GET").toUpperCase(), url });
        return result;
      };

      Xhr.prototype.send = function kolconnectPassiveXhrSend(...args) {
        const xhr = this;
        const request = metadata.get(xhr);
        const endpointKind = protocol.matchTikTokEndpoint(
          request?.url,
          target.location?.href,
        );
        if (endpointKind && typeof xhr.addEventListener === "function") {
          xhr.addEventListener("loadend", function observeCompletedXhr() {
            try {
              if (xhr.status < 200 || xhr.status >= 300) return;
              let payload;
              if (xhr.responseType === "json") {
                payload = xhr.response;
              } else if (!xhr.responseType || xhr.responseType === "text") {
                payload = JSON.parse(xhr.responseText);
              } else {
                return;
              }
              if (payload !== null && typeof payload === "object") {
                emit(endpointKind, request.method, payload);
              }
            } catch (_error) {
              // Malformed or unavailable response data is a capture miss only.
            }
          }, { once: true });
        }
        return Reflect.apply(originalSend, xhr, args);
      };
    }

    Object.defineProperty(target, INSTALL_MARKER, {
      configurable: false,
      enumerable: false,
      value: true,
      writable: false,
    });

    postBootstrap();
    return true;
  }

  return Object.freeze({ INSTALL_MARKER, installMainWorldCapture });
});
