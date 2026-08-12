import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.listeners = {};
    this.classList = { toggle() {} };
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setPointerCapture() {}
  getBoundingClientRect() { return { left: 100, top: 100 }; }
  select() {}
  remove() {}
}

class FakeButtonElement extends FakeElement {}
const documentElement = new FakeElement("html");
const document = {
  documentElement,
  body: new FakeElement("body"),
  getElementById(id) {
    return documentElement.children.find((child) => child.id === id) || null;
  },
  createElement(tagName) {
    return tagName === "button" ? new FakeButtonElement(tagName) : new FakeElement(tagName);
  },
  execCommand() { return true; }
};
const messageListeners = [];
const context = vm.createContext({
  document,
  location: { href: "https://www.tiktok.com/@creator" },
  navigator: { clipboard: { writeText: async () => {} } },
  chrome: {
    runtime: {
      lastError: null,
      sendMessage(_message, callback) { callback({ ok: false, error: "test" }); },
      onMessage: { addListener(callback) { messageListeners.push(callback); } }
    }
  },
  HTMLButtonElement: FakeButtonElement,
  URL,
  Intl,
  innerWidth: 1440,
  innerHeight: 900,
  setTimeout() { return 1; },
  clearTimeout() {},
  setInterval() { return 1; },
  addEventListener() {},
  console
});
context.window = context;
const sessionSource = readFileSync(new URL("../core/analysis_session.js", import.meta.url), "utf8");
const pageSupportSource = readFileSync(new URL("../core/page_support.js", import.meta.url), "utf8");
const configSource = readFileSync(new URL("../config.js", import.meta.url), "utf8");
const source = readFileSync(new URL("../content/floating_assistant.js", import.meta.url), "utf8");
vm.runInContext(configSource, context);
vm.runInContext(sessionSource, context);
vm.runInContext(pageSupportSource, context);
vm.runInContext(source, context);
const assistant = context.__KOLCONNECT_NEXT_ASSISTANT__;
assert.equal(assistant.state.visible, true);
assistant.close();
assert.equal(assistant.state.visible, false);
assistant.open();
assert.equal(assistant.state.visible, false);
const firstSessionId = assistant.state.currentSessionId;
assistant.state.contentAnalysis = { returned_count: 12 };
assistant.state.contentLoading = true;
assistant.handleUrlChange("https://www.tiktok.com/@creator-b");
const secondSessionId = assistant.state.currentSessionId;
assert.equal(assistant.state.contentAnalysis, null);
assert.equal(assistant.state.contentLoading, false);
assistant.handleUrlChange("https://www.tiktok.com/@creator-c");
const thirdSessionId = assistant.state.currentSessionId;
vm.runInContext(source, context);

const assistants = documentElement.children.filter((child) => child.id === "kolconnect-next-root");
assert.equal(assistants.length, 1);
assert.equal(messageListeners.length, 1);
assert.equal(assistants[0].style.display, "block");
assert.notEqual(firstSessionId, secondSessionId);
assert.notEqual(secondSessionId, thirdSessionId);
assert.equal(assistant.state.lastUrl, "https://www.tiktok.com/@creator-c");
assert.equal(assistant.state.profile, null);
assert.equal(source.includes("分析最近30条"), true);
assert.equal(source.includes("内容分析超时，请稍后重试。"), true);
assert.equal(source.includes("内容分析已停止或超时，请重试。"), true);
assert.equal(source.includes("KOLConnect v0.2.3"), true);

console.log("Floating assistant duplicate-injection guard test passed.");
