(function publicationBatchClaim(root) {
  "use strict";
  const match = String(root.location.hash || "").match(/^#publication-capture-claim=([^\.]+)\.([A-Za-z0-9_-]{20,})$/);
  if (!match) return;
  root.history.replaceState(null, "", root.location.pathname + root.location.search);
  let notice = null;
  const showNotice = (message) => {
    if (!notice && document.documentElement) {
      notice = document.createElement("div");
      notice.id = "kolconnect-publication-batch-claim";
      Object.assign(notice.style, {
        position: "fixed", right: "20px", bottom: "20px", zIndex: "2147483647", padding: "14px 18px",
        borderRadius: "12px", color: "#f7f4ed", background: "#17211f", font: "14px/1.45 sans-serif"
      });
      document.documentElement.appendChild(notice);
    }
    if (notice) notice.textContent = message;
  };
  showNotice("正在连接 KOLConnect 批量视频采集…");
  chrome.runtime.sendMessage({
    type: "KOLCONNECT_PUBLICATION_BATCH_CLAIM", batch_run_id: match[1], claim_token: match[2]
  }, response => {
    showNotice(response?.ok
      ? "批量采集已开始。KOLConnect 会逐条打开并检查视频。"
      : "批量采集未能启动，请返回 KOLConnect 重试。");
    if (notice) setTimeout(() => notice.remove(), 8000);
  });
})(globalThis);
