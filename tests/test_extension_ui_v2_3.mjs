import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const dataSource = readFileSync(new URL("chrome_extension/core/assistant_data.js", root), "utf8");
const context = { globalThis: {}, Date, Number, Set };
vm.createContext(context);
vm.runInContext(dataSource, context);
const { selectContents } = context.globalThis.KOLConnectAssistantData;

const metric = value => ({ value });
const base = Date.parse("2026-11-06T00:00:00Z");
const contents = [
  { video_id: "pinned", is_pinned: true, published_at: metric("2026-11-06T00:00:00Z"), views: metric(999), likes: metric(99), comments: metric(9) },
  { video_id: "zero", is_pinned: false, published_at: metric("2026-11-05T00:00:00Z"), views: metric(0), likes: metric(0), comments: metric(0) },
  { video_id: "recent", is_pinned: false, published_at: metric("2026-11-03T00:00:00Z"), views: metric(100), likes: metric(10), comments: metric(null) },
  { video_id: "old", is_pinned: false, published_at: metric("2026-10-01T00:00:00Z"), views: metric(200), likes: metric(null), comments: metric(2) },
  { video_id: "unknown-time", views: metric(null), likes: metric(5), comments: metric(1) },
];

const sevenItems = selectContents(contents, { range: "items:7", excludePinned: true, now: base });
assert.deepEqual(Array.from(sevenItems.items, item => item.video_id), ["zero", "recent", "old", "unknown-time"]);
assert.equal(sevenItems.excludedPinnedCount, 1);
assert.equal(sevenItems.unknownPinnedCount, 1);
assert.equal(sevenItems.metrics.validViews, 3);
assert.equal(sevenItems.metrics.averageViews, 100);
assert.equal(sevenItems.metrics.validLikes, 3);
assert.equal(sevenItems.metrics.averageLikes, 5);

const sevenDays = selectContents(contents, { range: "days:7", excludePinned: true, now: base });
assert.deepEqual(Array.from(sevenDays.items, item => item.video_id), ["zero", "recent"]);
assert.equal(sevenDays.missingPublishedCount, 1);
assert.equal(sevenDays.metrics.averageViews, 50);

const includePinned = selectContents(contents, { range: "items:30", excludePinned: false, now: base });
assert.equal(includePinned.items[0].video_id, "pinned");
assert.equal(includePinned.excludedPinnedCount, 0);

const assistantSource = readFileSync(new URL("chrome_extension/content/floating_assistant.js", root), "utf8");
for (const label of ["概览", "数据", "联系", "工具", "最近7条", "最近30条", "最近7天", "最近30天", "排除明确置顶"]) {
  assert.ok(assistantSource.includes(label), `missing UI contract: ${label}`);
}
assert.ok(assistantSource.includes("KOLCONNECT_NEXT_OPEN_MAIL_WORKSPACE"));
assert.ok(assistantSource.includes("KOLCONNECT_NEXT_CREATE_DISCOVERY_TASK"));
assert.ok(assistantSource.includes("KOLCONNECT_NEXT_LOAD_MAIL_OPTIONS"));
assert.ok(assistantSource.includes("KOLCONNECT_NEXT_CREATE_MAIL_DRAFT"));
assert.ok(assistantSource.includes("使用此模板创建邮件草稿"));
assert.ok(assistantSource.includes("查询本地状态"));
assert.ok(assistantSource.includes("暂无法查询收录状态"));
assert.ok(assistantSource.includes("不会自动发送"));
assert.ok(assistantSource.includes('state.mailOptions?.identity?.account_email'));
assert.ok(assistantSource.includes('!state.previewDirty.has("email")'));

const discoverySource = readFileSync(new URL("chrome_extension/content/similar_creator_discovery.js", root), "utf8");
assert.ok(discoverySource.includes("modalCandidates"));
assert.ok(discoverySource.includes("recommendationSignal"));
assert.ok(discoverySource.includes("MutationObserver"));
assert.ok(discoverySource.includes("seed_urls"));
assert.ok(!discoverySource.includes("document.querySelectorAll(\"a\")"));

const backgroundSource = readFileSync(new URL("chrome_extension/background.js", root), "utf8");
assert.ok(backgroundSource.includes("MAIL_HANDOFF_TTL_MS"));
assert.ok(backgroundSource.includes("chrome.storage.session.remove"));
assert.ok(backgroundSource.includes("CREATE_DISCOVERY_TASK"));
assert.ok(backgroundSource.includes("LOOKUP_DISCOVERY_CANDIDATES"));
assert.ok(backgroundSource.includes("CREATE_MAIL_DRAFT"));
assert.ok(backgroundSource.includes("draftId"));

const apiSource = readFileSync(new URL("chrome_extension/services/local_api.js", root), "utf8");
assert.ok(apiSource.includes("/api/extension/workspace/options"));
assert.ok(apiSource.includes("/api/extension/workspace/drafts"));
assert.ok(apiSource.includes("/api/extension/discovery/candidates/lookup"));

console.log("Extension UI V2.3 behavior tests passed");
