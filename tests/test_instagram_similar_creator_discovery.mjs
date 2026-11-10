import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../chrome_extension/content/similar_creator_discovery.js", import.meta.url), "utf8");

class ElementMock {
  constructor({ text = "", href = "", children = [], rect = { width: 700, height: 260 } } = {}) {
    this.textContent = text;
    this.href = href;
    this.children = children;
    this.parentElement = null;
    this.rect = rect;
    this.clientWidth = rect.width;
    this.scrollWidth = rect.width;
    this.clientHeight = rect.height;
    this.scrollHeight = rect.height;
    this.listeners = new Map();
    for (const child of children) child.parentElement = this;
  }
  getBoundingClientRect() { return this.rect; }
  querySelector(selector) {
    if (selector === "ul") return this.children.find((child) => child.isList) || null;
    return null;
  }
  querySelectorAll(selector) {
    if (selector === "a[href]") {
      if (this.href) return [this];
      return this.children.flatMap((child) => child.querySelectorAll(selector));
    }
    if (selector === "*") return this.children.flatMap((child) => [child, ...child.querySelectorAll("*")]);
    return [];
  }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  removeEventListener(name) { this.listeners.delete(name); }
  dispatch(name) { this.listeners.get(name)?.(); }
}

const anchor = (href) => new ElementMock({ href, rect: { width: 20, height: 20 } });
const list = new ElementMock({ children: [
  anchor("https://www.instagram.com/alpha/"),
  anchor("https://www.instagram.com/alpha/"),
  anchor("https://www.instagram.com/reel/not-a-profile/"),
  anchor("https://www.instagram.com/explore/"),
  anchor("https://www.instagram.com/beta/")
] });
list.isList = true;
list.scrollWidth = 1200;
list.clientWidth = 240;
const heading = new ElementMock({ text: "你可能喜欢的账户", rect: { width: 180, height: 18 } });
const region = new ElementMock({ children: [heading, list] });
heading.parentElement = region;

const stored = {};
const observers = [];
class MutationObserverMock {
  constructor(callback) { this.callback = callback; observers.push(this); }
  observe() {}
  disconnect() {}
}
const document = {
  body: new ElementMock(),
  documentElement: new ElementMock(),
  querySelectorAll(selector) {
    if (selector.includes("span,div")) return [heading];
    return [];
  }
};
const context = {
  globalThis: {}, location: { href: "https://www.instagram.com/seed/" },
  URL, Date, Map, Set, Element: ElementMock, document,
  MutationObserver: MutationObserverMock,
  window: { addEventListener() {}, removeEventListener() {} },
  chrome: { storage: { local: {
    async get(keys) {
      const names = Array.isArray(keys) ? keys : [keys];
      return Object.fromEntries(names.filter((key) => key in stored).map((key) => [key, stored[key]]));
    },
    async set(values) { Object.assign(stored, values); },
    async remove(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) delete stored[key]; }
  } } }
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);
await new Promise((resolve) => setImmediate(resolve));
const discovery = context.KOLConnectSimilarCreatorDiscovery;

assert.equal(discovery.canonicalInstagramProfile("https://www.instagram.com/Alpha/?x=1"), "https://www.instagram.com/Alpha/");
for (const invalid of [
  "https://www.instagram.com/explore/", "https://www.instagram.com/reel/abc/",
  "https://www.instagram.com/p/abc/", "https://example.com/alpha/"
]) assert.equal(discovery.canonicalInstagramProfile(invalid), "");

const started = await discovery.start();
assert.equal(started.ok, true);
assert.equal(started.state.platform, "Instagram");
assert.deepEqual(Array.from(started.state.candidates, (item) => item.profile_url), [
  "https://www.instagram.com/alpha/", "https://www.instagram.com/beta/"
]);
assert.ok(started.state.candidates.every((item) => item.recommendation_source === "instagram_recommendation_region"));
assert.ok(started.state.candidates.every((item) => item.seed_profile_url === "https://www.instagram.com/seed/"));

list.children.push(anchor("https://www.instagram.com/gamma/"));
list.dispatch("scroll");
await new Promise((resolve) => setImmediate(resolve));
assert.equal(discovery.getState().candidates.length, 3,
  "the collector must listen to an independent nested recommendation scroller");

await discovery.pause();
list.children.push(anchor("https://www.instagram.com/delta/"));
await discovery.resume();
assert.equal(discovery.getState().candidates.length, 4, "horizontal-list updates must accumulate without losing earlier candidates");
await discovery.finish();
assert.equal(discovery.getState().status, "finished");

context.location.href = "https://www.instagram.com/another_seed/";
assert.equal((await discovery.start()).ok, true);
assert.equal(discovery.getState().seed_url, "https://www.instagram.com/another_seed/");
assert.equal(discovery.getState().candidates.length, 4, "a new seed starts a distinct session and recollects only its own region");

console.log("Instagram similar creator discovery behavior tests passed.");
