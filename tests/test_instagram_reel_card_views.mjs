import assert from "node:assert/strict";
import { collectRecentContent } from "../chrome_extension/platform/instagram.js";

class Element {
  constructor(tagName, attributes = {}, text = "", children = []) {
    this.tagName = tagName.toUpperCase();
    this.attributes = attributes;
    this.text = text;
    this.children = children;
    for (const child of children) child.parentElement = this;
  }

  getAttribute(name) { return this.attributes[name] ?? null; }
  get href() { return new URL(this.getAttribute("href"), "https://www.instagram.com").href; }
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(""); }
  get innerText() {
    return this.tagName === "SVG" ? "" : this.text + this.children.map((child) => child.innerText).join("");
  }
  get nextElementSibling() {
    const siblings = this.parentElement?.children || [];
    return siblings[siblings.indexOf(this) + 1] || null;
  }
  querySelectorAll(selector) {
    const selectors = selector.split(",").map((part) => part.trim());
    const matches = (node, part) => {
      const attribute = part.match(/^(\w+)?\[([\w-]+)\*="([^"]+)"( i)?\]$/);
      if (attribute) {
        const [, tag, name, value, insensitive] = attribute;
        const actual = node.getAttribute(name) || "";
        return (!tag || node.tagName === tag.toUpperCase())
          && (insensitive ? actual.toLowerCase().includes(value.toLowerCase()) : actual.includes(value));
      }
      return part === "svg" && node.tagName === "SVG";
    };
    const result = [];
    const visit = (node) => {
      for (const child of node.children) {
        if (selectors.some((part) => matches(child, part))) result.push(child);
        visit(child);
      }
    };
    visit(this);
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

const node = (tag, attributes = {}, text = "", children = []) =>
  new Element(tag, attributes, text, children);

function reel(id, { view = "", label = "观看量图标", pinned = false, unrelated = "" } = {}) {
  const overlay = node("div", {}, "", [
    node("div", {}, "", [node("svg", { "aria-label": label }, label)]),
    node("span", {}, view)
  ]);
  const children = [overlay];
  if (pinned) children.push(node("svg", { "aria-label": "置顶帖图标" }));
  if (unrelated) children.push(node("div", {}, unrelated));
  return node("div", {}, "", [
    node("a", { href: `/_anna.pipolo/reel/${id}/` }, "", children)
  ]);
}

const cards = node("div", {}, "", [
  reel("pinned", { view: "999", pinned: true }),
  reel("english", { view: "1.2K", label: "play count" }),
  reel("chinese", { view: "1.1万" }),
  reel("chinese-other", { view: "2.3万", label: "播放量图标" }),
  reel("unrelated", { label: "音乐图标", unrelated: "999 followers" }),
  reel("missing", { label: "音乐图标" })
]);

const saved = { chrome: globalThis.chrome, document: globalThis.document, window: globalThis.window };
globalThis.document = {
  querySelectorAll(selector) {
    return selector.startsWith("script[") ? [] : cards.querySelectorAll(selector);
  }
};
globalThis.window = {};
globalThis.chrome = {
  scripting: {
    async executeScript({ func, args = [] }) {
      if (func.name === "fetchInstagramWebProfilePage") {
        return [{ result: { ok: false, reason: "fixture_api_unavailable" } }];
      }
      if (func.name === "discoverInstagramReels") return [{ result: func(...args) }];
      if (func.name === "fetchInstagramReelDetail") {
        return [{ result: { video_id: args[0].match(/\/reel\/([^/]+)/)?.[1] } }];
      }
      throw new Error(`Unexpected page function: ${func.name}`);
    }
  }
};

try {
  const result = await collectRecentContent(1, { limit: 6, excludePinned: true });
  const byId = Object.fromEntries(result.contents.map((item) => [item.video_id, item]));
  assert.equal(result.collector_mode, "legacy_fallback");
  assert.equal(result.discovered_count, 6);
  assert.equal(result.excluded_pinned_count, 1);
  assert.equal(result.returned_count, 5);
  assert.equal(byId.pinned, undefined);
  assert.deepEqual(result.contents.map((item) => item.video_id), [
    "english", "chinese", "chinese-other", "unrelated", "missing"
  ]);
  assert.equal(byId.english.views.value, 1200);
  assert.equal(byId.chinese.views.value, 11000);
  assert.equal(byId["chinese-other"].views.value, 23000);
  assert.equal(byId.chinese.views.source, "reel_card_icon_adjacent");
  assert.equal(byId.unrelated.views.value, null);
  assert.equal(byId.missing.views.value, null);
  assert.equal(byId.unrelated.views.missing_reason, "reel_card_view_candidate_not_found");
} finally {
  globalThis.chrome = saved.chrome;
  globalThis.document = saved.document;
  globalThis.window = saved.window;
}
