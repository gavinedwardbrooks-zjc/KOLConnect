const DEFAULT_API_URL = "http://127.0.0.1:8765";

export async function loadLocalApiUrl() {
  const stored = await chrome.storage.local.get("localApiUrl");
  return stored.localApiUrl || DEFAULT_API_URL;
}

function buildVideoImportItem(video = {}, capturedAt = "") {
  return {
    platform: video.platform || "",
    content_type: video.content_type || "",
    video_id: video.video_id || "",
    video_url: video.video_url || "",
    title: video.title || null,
    is_pinned: Boolean(video.is_pinned),
    views: video.views?.value ?? null,
    likes: video.likes?.value ?? null,
    comments: video.comments?.value ?? null,
    published_at: video.published_at?.value ?? null,
    engagement_rate: video.engagement_rate?.value ?? null,
    captured_at: capturedAt
  };
}

export function buildImportPayload(profile, now = new Date()) {
  const capturedAt = now.toISOString();
  return {
    task_name: `Extension import ${now.toISOString().slice(0, 10)}`,
    creator: {
      creator_name: profile.creator_name || profile.username || "",
      platform: profile.platform || "",
      profile_url: profile.profile_url || "",
      followers: profile.followers || "",
      bio: profile.bio || "",
      country: "",
      language: "",
      language_source: ""
    },
    videos: Array.isArray(profile.videos)
      ? profile.videos.map((video) => buildVideoImportItem(video, capturedAt))
      : [],
    video_analysis: profile.video_analysis && typeof profile.video_analysis === "object"
      ? profile.video_analysis
      : {},
    creator_insight: {},
    content_category: "",
    note: ""
  };
}

export function validateImportProfile(profile = {}) {
  const missing = [];
  if (!profile.platform) missing.push("平台");
  if (!profile.profile_url) missing.push("主页链接");
  if (!profile.username) missing.push("用户名");
  return missing;
}

export async function importProfile(profile) {
  const missing = validateImportProfile(profile);
  if (missing.length) throw new Error(`无法导入：缺少${missing.join("、")}。`);
  const apiUrl = await loadLocalApiUrl();
  const endpoint = new URL("/api/extension/import", apiUrl);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildImportPayload(profile))
  });
  let result = {};
  try {
    result = await response.json();
  } catch (_) {
    result = {};
  }
  if (!response.ok || result.ok === false) {
    throw new Error(result.error || `KOLConnect 请求失败（HTTP ${response.status}）。`);
  }
  return result;
}
