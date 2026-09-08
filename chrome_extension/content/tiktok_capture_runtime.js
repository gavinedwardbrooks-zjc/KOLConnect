(function (root) {
  "use strict";
  if (root.KOLConnectTikTokCapture || !root.KOLConnectTikTokSession) return;
  const protocol = root.KOLConnectPassiveCaptureProtocol;
  const session = root.KOLConnectTikTokSession.createSession(protocol.profileUsername(root.location.href));
  let l1 = false, parserError = false;
  function check() {
    const profile = protocol.profileUsername(root.location.href);
    if (session.snapshot().profile !== profile) { session.reset(profile); parserError = false; }
    const visible = (selector) => [...root.document.querySelectorAll(selector)].some((node) =>
      node.getClientRects().length > 0 && root.getComputedStyle(node).visibility !== "hidden");
    let reason = "";
    if (/captcha/i.test(root.location.pathname) || visible('iframe[src*="captcha"], [id*="captcha"], [class*="captcha-verify"]')) reason = "CAPTCHA_DETECTED";
    else if (/\/login(?:\/|$)/i.test(root.location.pathname) || visible('[data-e2e="login-modal"], [role="dialog"] form[action*="login"]')) reason = "LOGIN_REQUIRED";
    else if (/\/(verify|challenge|security)(?:\/|$)/i.test(root.location.pathname) || visible('[data-e2e="security-check"], [data-e2e="verify-page"]')) reason = "CAPTURE_BLOCKED";
    if (reason) session.stop(reason);
    return profile;
  }
  root.KOLConnectPassiveCaptureBridge.subscribeItemList((parsed, message) => {
    check();
    if (parsed.diagnostic.status !== "success") { parserError = true; return; }
    session.add(parsed.items, { profile: message.profile, observedAt: message.observedAt, layer: "L1" });
  });
  root.KOLConnectTikTokCapture = Object.freeze({
    // Unlike snapshot(), this does not run navigation/challenge checks or merge.
    diagnostics: () => ({ bridge_connected: l1, parser_error: parserError,
      bridge: root.KOLConnectPassiveCaptureBridge.diagnostics(), session: session.diagnostics() }),
    snapshot(expectedProfile, fallback = []) {
      const profile = check();
      if (session.snapshot().stopped) return { ...session.snapshot(), l1_available: l1, parser_error: parserError };
      if (!profile || profile.toLowerCase() !== String(expectedProfile).toLowerCase()) throw new Error("CAPTURE_PROFILE_CHANGED");
      for (const row of fallback.slice(0, 200)) session.add([row], { profile, layer: row.capture_layer, observedAt: row.observed_at });
      return { ...session.snapshot(), l1_available: l1, parser_error: parserError };
    },
    stop() { session.stop("CAPTURE_STOPPED"); },
    reset() { session.reset(protocol.profileUsername(root.location.href)); parserError = false; check(); },
  });
  root.chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "KOLCONNECT_NEXT_PAGE_CHANGED") check();
  });
  // The trusted token arrives through extension messaging, not page postMessage.
  root.chrome.runtime.sendMessage({ type: "KOLCONNECT_PASSIVE_CONNECT" }).then((reply) => {
    if (!protocol.isValidBootstrapEnvelope(protocol.createBootstrapEnvelope(reply?.token))) return;
    root.KOLConnectPassiveCaptureBridge.setExpectedToken(reply.token);
    l1 = true;
    return root.chrome.runtime.sendMessage({ type: "KOLCONNECT_PASSIVE_REPLAY" });
  }).catch(() => { l1 = false; });
})(globalThis);
