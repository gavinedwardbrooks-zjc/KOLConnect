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

  function publicationIdentity(value) {
    try {
      const url = new URL(value);
      const host = url.hostname.toLowerCase();
      const parts = url.pathname.split("/").filter(Boolean);
      if (host === "tiktok.com" || host.endsWith(".tiktok.com")) {
        const match = url.pathname.match(/^\/@[A-Za-z0-9._-]+\/video\/(\d+)/);
        return match ? { platform: "TikTok", video_id: match[1] } : null;
      }
      if (host === "instagram.com" || host.endsWith(".instagram.com")) {
        const match = url.pathname.match(/^\/(?:[A-Za-z0-9._]+\/)?(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/i);
        return match ? { platform: "Instagram", video_id: match[1] } : null;
      }
      if (host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtu.be") {
        const videoId = host === "youtu.be" ? parts[0]
          : parts[0] === "shorts" ? parts[1] : url.searchParams.get("v");
        return /^[A-Za-z0-9_-]+$/.test(videoId || "")
          ? { platform: "YouTube", video_id: videoId } : null;
      }
    } catch (_) {}
    return null;
  }

  function isSupportedCreatorPage(value) {
    try {
      const url = new URL(value);
      const host = url.hostname.toLowerCase();
      const parts = url.pathname.split("/").filter(Boolean);

      if (host === "tiktok.com" || host.endsWith(".tiktok.com")) {
        return parts.length === 1 && /^@[^/]+$/.test(parts[0] || "");
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

  function pageMode(value) {
    if (publicationIdentity(value)) return "video";
    if (isSupportedCreatorPage(value)) return "creator";
    return "unsupported";
  }

  globalThis.KOLConnectPageSupport = Object.freeze({ isSupportedCreatorPage, publicationIdentity, pageMode });
})();
