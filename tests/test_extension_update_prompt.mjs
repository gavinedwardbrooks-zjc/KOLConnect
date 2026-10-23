import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const serviceUrl = new URL("../chrome_extension/services/update_service.js", import.meta.url);
const {
  UPDATE_CHECK_POLICY,
  allowedUpdateUrl,
  checkForExtensionUpdate,
  compareVersions,
  releaseUpdateFromResponse,
  snoozeExtensionUpdate
} = await import(serviceUrl);

assert.equal(compareVersions("2.4.11", "2.4.10"), 1);
assert.equal(compareVersions("2.10.0", "2.9.9"), 1);
assert.equal(compareVersions("2.4.10", "2.4.10"), 0);
assert.equal(compareVersions("invalid", "2.4.10"), null);

const release = {
  tag_name: "v2.4.11",
  draft: false,
  prerelease: false,
  html_url: "https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/tag/v2.4.11",
  body: "## 本次更新\n- 修复抓取状态\n- 改善稳定性",
  published_at: "2026-10-23T00:00:00Z",
  assets: [{
    name: "KOLConnect_Chrome_Extension_v2.4.11.zip",
    state: "uploaded",
    browser_download_url: "https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/download/v2.4.11/KOLConnect_Chrome_Extension_v2.4.11.zip"
  }]
};
const normalized = releaseUpdateFromResponse(release, "2.4.10");
assert.equal(normalized.latest_version, "2.4.11");
assert.deepEqual(normalized.release_notes, ["修复抓取状态", "改善稳定性"]);
assert.match(normalized.download_url, /KOLConnect_Chrome_Extension_v2\.4\.11\.zip$/);
assert.equal(releaseUpdateFromResponse(release, "2.4.11"), null);
assert.equal(allowedUpdateUrl("https://evil.example/download.zip"), "");

function memoryStorage(initial = {}) {
  const values = structuredClone(initial);
  return {
    values,
    async get(keys) {
      return Object.fromEntries(keys.filter((key) => key in values).map((key) => [key, values[key]]));
    },
    async set(next) { Object.assign(values, structuredClone(next)); }
  };
}

const now = Date.UTC(2026, 9, 23, 8, 0, 0);
const storage = memoryStorage();
const update = await checkForExtensionUpdate({
  currentVersion: "2.4.10",
  storage,
  now,
  fetchImpl: async () => ({ ok: true, json: async () => release })
});
assert.equal(update.latest_version, "2.4.11");
assert.equal(await snoozeExtensionUpdate("2.4.11", { storage, now }), true);
assert.equal(await checkForExtensionUpdate({
  currentVersion: "2.4.10",
  storage,
  now: now + UPDATE_CHECK_POLICY.snoozeMs - 1,
  fetchImpl: async () => { throw new Error("cache should be used"); }
}), null);
assert.equal((await checkForExtensionUpdate({
  currentVersion: "2.4.10",
  storage,
  now: now + UPDATE_CHECK_POLICY.snoozeMs + 1,
  fetchImpl: async () => ({ ok: true, json: async () => release })
})).latest_version, "2.4.11");

const higherRelease = structuredClone(release);
higherRelease.tag_name = "v2.4.12";
higherRelease.html_url = higherRelease.html_url.replaceAll("2.4.11", "2.4.12");
higherRelease.assets[0].name = "KOLConnect_Chrome_Extension_v2.4.12.zip";
higherRelease.assets[0].browser_download_url = higherRelease.assets[0].browser_download_url.replaceAll("2.4.11", "2.4.12");
const higherStorage = memoryStorage({
  extensionUpdateSnooze: { version: "2.4.11", until: now + UPDATE_CHECK_POLICY.snoozeMs },
  extensionUpdateCheckState: { retry_after: 0, update: normalized }
});
assert.equal((await checkForExtensionUpdate({
  currentVersion: "2.4.10",
  storage: higherStorage,
  now,
  fetchImpl: async () => ({ ok: true, json: async () => higherRelease })
})).latest_version, "2.4.12");

const failedStorage = memoryStorage();
assert.equal(await checkForExtensionUpdate({
  currentVersion: "2.4.10",
  storage: failedStorage,
  now,
  fetchImpl: async () => { throw new Error("offline"); }
}), null);
const extensionAssetMissing = await checkForExtensionUpdate({
  currentVersion: "2.4.10",
  storage: memoryStorage(),
  now,
  fetchImpl: async () => ({ ok: true, json: async () => ({ tag_name: "v2.4.11" }) })
});
assert.equal(extensionAssetMissing, null, "a newer product release without the extension zip is not an update");
const noNotesRelease = structuredClone(release);
noNotesRelease.body = "";
assert.deepEqual(
  releaseUpdateFromResponse(noNotesRelease, "2.4.10").release_notes,
  ["包含稳定性优化和问题修复"]
);
assert.equal(await checkForExtensionUpdate({
  currentVersion: "2.4.10",
  storage: memoryStorage(),
  now,
  fetchImpl: async () => ({ ok: true, json: async () => ({ body: "missing version" }) })
}), null);

class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.className = "";
    this.textContent = "";
    this.disabled = false;
    this.removed = false;
  }
  append(...children) { this.children.push(...children); }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  setAttribute(name, value) { this.attributes[name] = value; }
  remove() { this.removed = true; }
}
const documentRef = { createElement: (tag) => new Element(tag) };
const context = { globalThis: {}, document: documentRef };
vm.runInNewContext(
  readFileSync(new URL("../chrome_extension/content/update_prompt.js", import.meta.url), "utf8"),
  context
);
let downloaded = false;
let snoozed = false;
const card = context.globalThis.KOLConnectUpdatePrompt.render({
  document: documentRef,
  update,
  onDownload: async () => { downloaded = true; },
  onSnooze: async () => { snoozed = true; return true; }
});
const all = [];
const visit = (node) => { all.push(node); node.children.forEach(visit); };
visit(card);
assert.equal(card.attributes.role, "dialog");
assert.ok(all.some((node) => node.textContent === "发现新版本"));
assert.ok(all.some((node) => node.textContent === "当前 2.4.10，可升级到 2.4.11。"));
assert.ok(all.some((node) => node.textContent === "本次更新"));
const downloadButton = all.find((node) => node.textContent === "立即下载 zip");
const snoozeButton = all.find((node) => node.textContent === "一天后再提醒");
const dismissButton = all.find((node) => node.attributes["aria-label"] === "关闭并在一天后提醒");
assert.ok(dismissButton);
await downloadButton.listeners.click();
await snoozeButton.listeners.click();
assert.equal(downloaded, true);
assert.equal(snoozed, true);
assert.equal(card.removed, true);

const manifest = JSON.parse(readFileSync(new URL("../chrome_extension/manifest.json", import.meta.url), "utf8"));
assert.ok(manifest.host_permissions.includes("https://api.github.com/*"));
assert.ok(manifest.content_scripts.at(-1).js.includes("content/update_prompt.js"));

console.log("Extension update prompt tests passed");
