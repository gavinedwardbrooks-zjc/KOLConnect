(() => {
  const create = (documentRef, tag, className = "", text = "") => {
    const element = documentRef.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  };

  const render = ({ document: documentRef = document, update, onDownload, onSnooze }) => {
    if (!update?.current_version || !update?.latest_version) return null;
    const card = create(documentRef, "section", "kol-update-card");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "发现新版本");

    const top = create(documentRef, "div", "kol-update-top");
    const eyebrow = create(documentRef, "span", "kol-update-eyebrow", "KOLCONNECT UPDATE");
    const dismiss = create(documentRef, "button", "kol-update-dismiss", "×");
    dismiss.type = "button";
    dismiss.title = "一天后再提醒";
    dismiss.setAttribute("aria-label", "关闭并在一天后提醒");
    top.append(eyebrow, dismiss);
    const title = create(documentRef, "h3", "kol-update-title", "发现新版本");
    const version = create(
      documentRef,
      "p",
      "kol-update-version",
      `当前 ${update.current_version}，可升级到 ${update.latest_version}。`
    );
    const notesTitle = create(documentRef, "h4", "kol-update-notes-title", "本次更新");
    const notes = create(documentRef, "ul", "kol-update-notes");
    const noteItems = Array.isArray(update.release_notes) && update.release_notes.length
      ? update.release_notes.slice(0, 5)
      : ["包含稳定性优化和问题修复"];
    for (const item of noteItems) notes.append(create(documentRef, "li", "", String(item)));

    const installHint = create(
      documentRef,
      "p",
      "kol-update-hint",
      "下载后，请在浏览器扩展页面重新加载或更新插件。"
    );
    const actions = create(documentRef, "div", "kol-update-actions");
    const download = create(documentRef, "button", "kol-update-download", "立即下载 zip");
    const snooze = create(documentRef, "button", "kol-update-snooze", "一天后再提醒");
    download.type = "button";
    snooze.type = "button";
    download.addEventListener("click", async () => {
      download.disabled = true;
      try { await onDownload?.(update); } finally { download.disabled = false; }
    });
    const defer = async (button) => {
      button.disabled = true;
      try {
        if (await onSnooze?.(update)) card.remove();
      } finally {
        button.disabled = false;
      }
    };
    snooze.addEventListener("click", () => defer(snooze));
    dismiss.addEventListener("click", () => defer(dismiss));
    actions.append(download, snooze);
    card.append(top, title, version, notesTitle, notes, installHint, actions);
    return card;
  };

  globalThis.KOLConnectUpdatePrompt = Object.freeze({ render });
})();
