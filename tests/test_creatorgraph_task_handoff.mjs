import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { pathToFileURL } from "node:url";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
globalThis.crypto ??= webcrypto;
globalThis.chrome = { storage: { local: { get: async () => ({}) } } };

const requests = [];
globalThis.fetch = async (url, options) => {
  requests.push({ url: String(url), body: JSON.parse(options.body) });
  return { ok: true, status: 200, json: async () => ({ ok: true, task: { id: "task_one" } }) };
};

const { createDiscoveryTask } = await import(pathToFileURL(
  path.join(root, "chrome_extension/services/local_api.js")
).href);

const links = ["https://www.tiktok.com/@beta", "https://www.tiktok.com/@alpha"];
await createDiscoveryTask(links, "https://www.tiktok.com/@seed");
await createDiscoveryTask(links.slice().reverse(), "https://www.tiktok.com/@seed");

assert.equal(requests.length, 2);
assert.match(requests[0].body.idempotency_key, /^creatorgraph:[0-9a-f]{64}$/);
assert.equal(requests[0].body.idempotency_key, requests[1].body.idempotency_key);
assert.deepEqual(requests[0].body.platforms, ["TikTok"]);
assert.equal(requests[0].body.text, links.join("\n"));

const instagramLinks = ["https://www.instagram.com/alpha/", "https://www.instagram.com/__shinyeeun/"];
await createDiscoveryTask(instagramLinks, "https://www.instagram.com/seed/", "Instagram");
assert.deepEqual(requests[2].body.platforms, ["Instagram"]);
assert.equal(requests[2].body.text, instagramLinks.join("\n"));
assert.match(requests[2].body.name, /seed/);
await assert.rejects(
  () => createDiscoveryTask([links[0], instagramLinks[0]], "https://www.tiktok.com/@seed"),
  (error) => error?.code === "VALIDATION_ERROR"
);
await assert.rejects(
  () => createDiscoveryTask(["https://www.instagram.com/explore/"], "https://www.instagram.com/seed/"),
  (error) => error?.code === "VALIDATION_ERROR"
);

console.log("CreatorGraph task handoff contract tests passed.");
