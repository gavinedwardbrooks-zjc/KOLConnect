(function exposePublicationCaptureCode(root) {
  "use strict";

  function parse(value) {
    const normalized = String(value || "")
      .normalize("NFKC")
      .replace(/[\u200B-\u200D\uFEFF\s]/g, "");
    const match = normalized.match(/^(capture_[a-f0-9]{32})\.([A-Za-z0-9_-]{20,})$/);
    return match ? { request_id: match[1], capability_token: match[2] } : null;
  }

  root.KOLConnectPublicationCaptureCode = Object.freeze({ parse });
})(globalThis);
