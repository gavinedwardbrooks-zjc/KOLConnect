(() => {
  const match = location.hash.match(/^#mail-handoff=([^&]+)$/);
  if (!match) return;
  const token = decodeURIComponent(match[1]);
  chrome.runtime.sendMessage({ type: "KOLCONNECT_NEXT_CONSUME_MAIL_HANDOFF", token }, (response) => {
    if (chrome.runtime.lastError || !response?.ok || !response.context) return;
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    const dispatch = () => document.dispatchEvent(new CustomEvent("kolconnect:mail-workspace-handoff", {
      detail: response.context
    }));
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", dispatch, { once: true });
    else dispatch();
  });
})();
