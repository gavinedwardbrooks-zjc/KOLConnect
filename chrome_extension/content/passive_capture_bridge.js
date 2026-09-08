(function initializePassiveCaptureBridge(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    api.installIsolatedBridge(
      root,
      root.KOLConnectPassiveCaptureProtocol,
      root.KOLConnectTikTokNetwork,
    );
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createBridgeApi() {
  "use strict";

  const INSTALL_MARKER = "__kolconnectPassiveCaptureBridgeV1__";
  const PUBLIC_BRIDGE = "KOLConnectPassiveCaptureBridge";

  function installIsolatedBridge(target, protocol, tiktokNetwork, expectedToken = null) {
    if (!target || !protocol) return null;
    if (target[INSTALL_MARKER]) return target[PUBLIC_BRIDGE] || null;

    let bridgeToken = expectedToken;
    const listeners = new Set();
    const itemListListeners = new Set();
    const expectedOrigin = target.location?.origin;
    const counters = { accepted: 0, rejected: 0, parser_invocations: 0,
      parser_success: 0, parser_errors: 0, normalized_rows: 0, consumer_errors: 0 };
    const rejectedReasons = { source: 0, origin: 0, token_unavailable: 0,
      token_mismatch: 0, invalid_envelope: 0, receiver_exception: 0 };
    const parserReasons = { invalid_payload: 0, exception: 0 };
    const reject = (reason) => { counters.rejected += 1; rejectedReasons[reason] += 1; };

    function onMessage(event) {
      try {
        if (event.source !== target) { reject("source"); return; }
        if (event.origin !== expectedOrigin) { reject("origin"); return; }
        let message = event.data;
        if (!protocol.isValidCaptureEnvelope(message, bridgeToken)) {
          reject(!bridgeToken ? "token_unavailable"
            : message?.namespace === protocol.NAMESPACE && message?.bridgeToken !== bridgeToken
              ? "token_mismatch" : "invalid_envelope");
          return;
        }
        counters.accepted += 1;
        message = protocol.createCaptureEnvelope(message);
        if (
          message.endpointKind === "tiktok_item_list"
          && typeof tiktokNetwork?.parseTikTokItemListResponse === "function"
        ) {
          try {
            counters.parser_invocations += 1;
            const parsed = tiktokNetwork.parseTikTokItemListResponse(message.payload);
            if (parsed.diagnostic.status === "success") counters.parser_success += 1;
            else { counters.parser_errors += 1; parserReasons.invalid_payload += 1; }
            counters.normalized_rows += parsed.items.length;
            for (const listener of Array.from(itemListListeners)) {
              try {
                listener(parsed, message);
              } catch (_error) {
                counters.consumer_errors += 1;
                // Parsed-result consumers are isolated from the transport receiver.
              }
            }
          } catch (_error) {
            counters.parser_errors += 1; parserReasons.exception += 1;
            // Parser failures do not block the validated transport event.
          }
        }
        for (const listener of Array.from(listeners)) {
          try {
            listener(message);
          } catch (_error) {
            // One consumer cannot disrupt bridge validation or other consumers.
          }
        }
      } catch (_error) {
        reject("receiver_exception");
        // Forged or malformed page messages are ignored.
      }
    }

    const bridge = Object.freeze({
      diagnostics: () => ({ ...counters, token_configured: Boolean(bridgeToken),
        rejected_reasons: { ...rejectedReasons }, parser_reasons: { ...parserReasons } }),
      // Called only in the isolated world with the extension background reply.
      setExpectedToken(token) { bridgeToken = token; },
      subscribe(listener) {
        if (typeof listener !== "function") return () => {};
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      subscribeItemList(listener) {
        if (typeof listener !== "function") return () => {};
        itemListListeners.add(listener);
        return () => itemListListeners.delete(listener);
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
    return bridge;
  }

  return Object.freeze({ INSTALL_MARKER, PUBLIC_BRIDGE, installIsolatedBridge });
});
