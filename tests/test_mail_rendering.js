const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.children = [];
    this.className = "";
    this.dataset = {};
    this.checked = false;
    this.textContent = "";
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this.children = children;
  }

  set innerHTML(_value) {
    throw new Error("Unsafe innerHTML was used while rendering mail data.");
  }
}

function allText(element) {
  return [element.textContent, ...element.children.map(allText)].join("");
}

const elements = new Map();
for (const id of [
  "mail-summary-accounts",
  "mail-summary-fetched",
  "mail-summary-new",
  "mail-summary-unread",
  "mail-summary-matched",
  "mail-inbox-updated-at",
  "mail-inbox-messages",
  "mail-matched-only",
]) {
  elements.set(id, new FakeElement());
}

const sandbox = {
  console,
  fetch: async () => {
    throw new Error("fetch should not run in this test");
  },
  document: {
    createElement: tagName => new FakeElement(tagName),
    getElementById: id => elements.get(id) || null,
    querySelectorAll: () => [],
  },
  window: {
    addEventListener: () => {},
    localStorage: {
      getItem: () => "",
      setItem: () => {},
      removeItem: () => {},
    },
  },
};
sandbox.globalThis = sandbox;

const appPath = path.join(__dirname, "..", "webapp", "app.js");
const source = `${fs.readFileSync(appPath, "utf8")}
globalThis.__mailTest = { renderMailInbox };`;
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: appPath });

const dangerous = "<script>alert(1)</script>";
sandbox.__mailTest.renderMailInbox({
  messages: [{
    subject: dangerous,
    from_name: dangerous,
    snippet: dangerous,
    matched_creator_name: dangerous,
    matched_platform: "TikTok",
    reply_status: "matched",
    is_unread: true,
  }],
});

const rendered = allText(elements.get("mail-inbox-messages"));
assert.ok(rendered.includes(dangerous));
assert.equal(elements.get("mail-inbox-messages").children.length, 1);
console.log("Mail rendering safety: OK");
