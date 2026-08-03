const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  contains(value) {
    return this.values.has(value);
  }

  toggle(value, enabled) {
    if (enabled) this.values.add(value);
    else this.values.delete(value);
  }
}

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.children = [];
    this.className = "";
    this.classList = new FakeClassList();
    this.dataset = {};
    this.hidden = false;
    this.textContent = "";
    this.value = "";
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  addEventListener() {}
}

const ids = [
  "creator-analysis-panel",
  "creator-analysis-summary",
  "creator-analysis-level",
  "creator-analysis-metrics",
  "creator-analysis-strengths",
  "creator-analysis-risks",
  "creator-analysis-recommendation",
  "creator-analysis-videos",
  "creator-library-detail-summary",
  "creator-library-detail-level",
  "creator-library-basic",
  "creator-library-video-metrics",
  "creator-library-data-meta",
  "creator-library-freshness",
  "creator-library-recommendation",
  "creator-library-strengths",
  "creator-library-risks",
  "creator-library-snapshots",
  "creator-library-snapshots-empty",
  "cooperation-stat-count",
  "cooperation-stat-spend",
  "cooperation-stat-views",
  "cooperation-stat-roi",
  "creator-cooperations-body",
  "creator-cooperations-empty",
  "cooperation-platform",
  "creator-library-videos",
];
const elements = new Map(ids.map(id => [id, new FakeElement()]));
const tabs = ["overview", "content", "history", "cooperations"].map(name => {
  const element = new FakeElement("button");
  element.dataset.detailTab = name;
  return element;
});
const panels = ["overview", "content", "history", "cooperations"].map(name => {
  const element = new FakeElement("section");
  element.dataset.detailPanel = name;
  return element;
});

let apiPayload = {};
const sandbox = {
  console,
  fetch: async () => ({
    ok: true,
    json: async () => apiPayload,
  }),
  Option: function Option() {},
  document: {
    createElement: tagName => new FakeElement(tagName),
    getElementById: id => elements.get(id) || null,
    querySelector: () => null,
    querySelectorAll: selector => {
      if (selector === ".detail-tab") return tabs;
      if (selector === ".detail-panel") return panels;
      return [];
    },
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
sandbox.window.fetch = sandbox.fetch;

const apiClientPath = path.join(__dirname, "..", "webapp", "services", "api-client.js");
const appPath = path.join(__dirname, "..", "webapp", "app.js");
const source = `${fs.readFileSync(apiClientPath, "utf8")}
${fs.readFileSync(appPath, "utf8")}
globalThis.__frontendTest = {
  state,
  viewCreatorAnalysis
};`;
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: appPath });

async function run() {
  const api = sandbox.__frontendTest;
  api.state.review.taskId = "task_20260729T100000Z_aaaaaaaa";
  apiPayload = {
    available: true,
    analysis: {
      creator: {
        creator_name: "Maria",
        platform: "TikTok",
        profile_url: "https://www.tiktok.com/@maria",
      },
      video_analysis: {
        sample_size: 2,
        average_views: 1200,
        median_views: 1000,
        view_stability: 0.83,
        view_coverage: 1,
      },
      creator_insight: {
        level: "good",
        strengths: ["播放稳定"],
        risks: [],
        recommendation: "建议联系",
      },
      videos: [],
    },
  };

  await api.viewCreatorAnalysis();
  assert.equal(elements.get("creator-analysis-panel").hidden, false);
  assert.match(elements.get("creator-analysis-summary").textContent, /Maria/);

  console.log("Creator analysis panel: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
