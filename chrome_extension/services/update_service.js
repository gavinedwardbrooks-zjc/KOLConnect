const RELEASES_API_URL = "https://api.github.com/repos/gavinedwardbrooks-zjc/KOLConnect/releases/latest";
const RELEASES_BASE_URL = "https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/";
const UPDATE_STATE_KEY = "extensionUpdateCheckState";
const UPDATE_SNOOZE_KEY = "extensionUpdateSnooze";
const SUCCESS_CACHE_MS = 6 * 60 * 60 * 1000;
const FAILURE_RETRY_MS = 60 * 60 * 1000;
const SNOOZE_MS = 24 * 60 * 60 * 1000;
const REQUEST_TIMEOUT_MS = 5000;
const FALLBACK_NOTES = ["包含稳定性优化和问题修复"];

function versionParts(value) {
  const match = String(value || "").trim().match(/^v?(\d+)\.(\d+)\.(\d+)$/);
  return match ? match.slice(1).map(Number) : null;
}

export function compareVersions(left, right) {
  const leftParts = versionParts(left);
  const rightParts = versionParts(right);
  if (!leftParts || !rightParts) return null;
  for (let index = 0; index < leftParts.length; index += 1) {
    if (leftParts[index] !== rightParts[index]) {
      return leftParts[index] > rightParts[index] ? 1 : -1;
    }
  }
  return 0;
}

export function summarizeReleaseNotes(body) {
  const lines = String(body || "")
    .replace(/```[\s\S]*?```/g, " ")
    .split(/\r?\n/)
    .map((line) => line
      .replace(/^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+)/, "")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/[*_~`>#]/g, "")
      .trim())
    .filter((line) => line && !/^(?:本次更新|更新内容|release notes|what'?s new)$/i.test(line));
  const unique = [];
  for (const line of lines) {
    const clipped = line.length > 120 ? `${line.slice(0, 117).trimEnd()}...` : line;
    if (!unique.includes(clipped)) unique.push(clipped);
    if (unique.length === 5) break;
  }
  return unique.length ? unique : [...FALLBACK_NOTES];
}

function safeReleaseUrl(value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol !== "https:" || url.hostname !== "github.com") return "";
    if (!url.pathname.startsWith("/gavinedwardbrooks-zjc/KOLConnect/releases/")) return "";
    return url.href;
  } catch (_) {
    return "";
  }
}

export function releaseUpdateFromResponse(release, currentVersion) {
  const latestVersion = String(release?.tag_name || "").replace(/^v/, "");
  if (release?.draft || release?.prerelease || compareVersions(latestVersion, currentVersion) !== 1) {
    return null;
  }
  const expectedAsset = `KOLConnect_Chrome_Extension_v${latestVersion}.zip`;
  const asset = Array.isArray(release?.assets)
    ? release.assets.find((candidate) => candidate?.name === expectedAsset && candidate?.state === "uploaded")
    : null;
  const downloadUrl = safeReleaseUrl(asset?.browser_download_url);
  if (!asset || !downloadUrl) return null;
  const releaseUrl = safeReleaseUrl(release?.html_url)
    || `${RELEASES_BASE_URL}tag/v${encodeURIComponent(latestVersion)}`;
  return {
    current_version: currentVersion,
    latest_version: latestVersion,
    download_url: downloadUrl,
    release_url: releaseUrl,
    release_notes: summarizeReleaseNotes(release?.body),
    published_at: typeof release?.published_at === "string" ? release.published_at : ""
  };
}

function updateIsVisible(update, currentVersion, snooze, now) {
  if (!update || compareVersions(update.latest_version, currentVersion) !== 1) return false;
  return !(snooze?.version === update.latest_version && Number(snooze?.until) > now);
}

async function readStoredState(storage) {
  const stored = await storage.get([UPDATE_STATE_KEY, UPDATE_SNOOZE_KEY]);
  return {
    check: stored?.[UPDATE_STATE_KEY] || {},
    snooze: stored?.[UPDATE_SNOOZE_KEY] || {}
  };
}

export async function checkForExtensionUpdate({
  currentVersion,
  fetchImpl = globalThis.fetch,
  storage = globalThis.chrome?.storage?.local,
  now = Date.now(),
  timeoutMs = REQUEST_TIMEOUT_MS
} = {}) {
  if (!versionParts(currentVersion) || typeof fetchImpl !== "function" || !storage) return null;
  let stored;
  try {
    stored = await readStoredState(storage);
  } catch (_) {
    return null;
  }
  if (Number(stored.check?.retry_after) > now) {
    return updateIsVisible(stored.check.update, currentVersion, stored.snooze, now)
      ? { ...stored.check.update, current_version: currentVersion }
      : null;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(RELEASES_API_URL, {
      method: "GET",
      cache: "no-store",
      headers: {
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
      },
      signal: controller.signal
    });
    if (!response?.ok) throw new Error("UPDATE_CHECK_FAILED");
    const update = releaseUpdateFromResponse(await response.json(), currentVersion);
    const nextState = { checked_at: now, retry_after: now + SUCCESS_CACHE_MS, update };
    await storage.set({ [UPDATE_STATE_KEY]: nextState });
    return updateIsVisible(update, currentVersion, stored.snooze, now) ? update : null;
  } catch (_) {
    try {
      await storage.set({
        [UPDATE_STATE_KEY]: {
          ...stored.check,
          checked_at: now,
          retry_after: now + FAILURE_RETRY_MS
        }
      });
    } catch (_) {}
    return updateIsVisible(stored.check?.update, currentVersion, stored.snooze, now)
      ? { ...stored.check.update, current_version: currentVersion }
      : null;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function snoozeExtensionUpdate(version, {
  storage = globalThis.chrome?.storage?.local,
  now = Date.now()
} = {}) {
  if (!versionParts(version) || !storage) return false;
  await storage.set({ [UPDATE_SNOOZE_KEY]: { version, until: now + SNOOZE_MS } });
  return true;
}

export function allowedUpdateUrl(value) {
  return safeReleaseUrl(value);
}

export const UPDATE_CHECK_POLICY = Object.freeze({
  releasesApiUrl: RELEASES_API_URL,
  successCacheMs: SUCCESS_CACHE_MS,
  failureRetryMs: FAILURE_RETRY_MS,
  snoozeMs: SNOOZE_MS,
  requestTimeoutMs: REQUEST_TIMEOUT_MS
});
