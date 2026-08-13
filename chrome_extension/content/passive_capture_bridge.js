(function initializePassiveCaptureBridge(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    api.installIsolatedBridge(root, root.KOLConnectPassiveCaptureProtocol);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createBridgeApi() {
  "use strict";

  const INSTALL_MARKER = "__kolconnectPassiveCaptureBridgeV1__";
  const PUBLIC_BRIDGE = "KOLConnectPassiveCaptureBridge";

  function installIsolatedBridge(target, protocol) {
    if (!target || !protocol) return null;
    if (target[INSTALL_MARKER]) return target[PUBLIC_BRIDGE] || null;

    let bridgeToken = null;
    const listeners = new Set();
    const expectedOrigin = target.location?.origin;

    function onMessage(event) {
      try {
        if (event.source !== target || event.origin !== expectedOrigin) return;
        const message = event.data;
        if (protocol.isValidBootstrapEnvelope(message)) {
          if (bridgeToken === null) bridgeToken = message.bridgeToken;
          return;
        }
        if (!protocol.isValidCaptureEnvelope(message, bridgeToken)) return;
        for (const listener of Array.from(listeners)) {
          try {
            listener(message);
          } catch (_error) {
            // One consumer cannot disrupt bridge validation or other consumers.
          }
        }
      } catch (_error) {
        // Forged or malformed page messages are ignored.
      }
    }

    const bridge = Object.freeze({
      subscribe(listener) {
        if (typeof listener !== "function") return () => {};
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    });

    target.addEventListener("message", onMessage);
    Object.defineProperty(target, PUBLIC_BRIDGE, {
      configurable: false,
      enumerable: false,
      value: bridge,
      writable: false,
    });
    Object.defineProperty(target, INSTALL_MARKER, {
      configurable: false,
      enumerable: false,
      value: true,
      writable: false,
    });
    try {
      target.postMessage(protocol.createBootstrapRequestEnvelope(), expectedOrigin);
    } catch (_error) {
      // MAIN also broadcasts proactively, so a request failure is non-fatal.
    }
    return bridge;
  }

  return Object.freeze({ INSTALL_MARKER, PUBLIC_BRIDGE, installIsolatedBridge });
});
