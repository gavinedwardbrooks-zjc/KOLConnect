(() => {
  const RESERVED_INSTAGRAM_PATHS = new Set([
    "accounts",
    "direct",
    "explore",
    "p",
    "reel",
    "reels",
    "stories"
  ]);

  function isSupportedCreatorPage(value) {
    try {
      const url = new URL(value);
      const host = url.hostname.toLowerCase();
      const parts = url.pathname.split("/").filter(Boolean);

      if (host === "tiktok.com" || host.endsWith(".tiktok.com")) {
        return /^@[^/]+/.test(parts[0] || "");
      }

      if (host === "instagram.com" || host.endsWith(".instagram.com")) {
        const handle = (parts[0] || "").toLowerCase();
        return Boolean(handle)
          && !RESERVED_INSTAGRAM_PATHS.has(handle)
          && (parts.length === 1 || (parts.length === 2 && parts[1].toLowerCase() === "reels"));
      }

      if (host === "youtube.com" || host.endsWith(".youtube.com")) {
        const root = parts[0] || "";
        const isHandle = root.startsWith("@");
        const isNamedRoot = ["channel", "c", "user"].includes(root);
        if (!isHandle && !isNamedRoot) return false;
        const section = isHandle ? parts[1] : parts[2];
        return !section || ["videos", "shorts"].includes(section.toLowerCase());
      }
    } catch (_) {}
    return false;
  }

  globalThis.KOLConnectPageSupport = Object.freeze({ isSupportedCreatorPage });
})();
