const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

class FakeClassList {
  constructor(values = []) {
    this.values = new Set(values);
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
  constructor(tagName = "div", id = "", classes = []) {
    this.tagName = tagName;
    this.id = id;
    this.className = classes.join(" ");
    this.classList = new FakeClassList(classes);
    this.dataset = {};
    this.children = [];
    this.options = [];
    this.listeners = new Map();
    this.parentElement = null;
    this.hidden = false;
    this.textContent = "";
    this.value = "";
    this.disabled = false;
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  listenerCount(type) {
    return this.listeners.get(type)?.size || 0;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  append(...children) {
    children.forEach(child => this.appendChild(child));
  }

  replaceChildren(...children) {
    this.children = [];
    this.options = [];
    this.append(...children);
    if (this.tagName === "select") this.options = [...children];
  }

  add(option) {
    option.parentElement = this;
    this.options.push(option);
    this.children.push(option);
    if (option.selected) this.value = option.value;
  }

  closest(selector) {
    if (selector === "[data-creator-action]" && this.dataset.creatorAction) return this;
    if (selector === "[data-creator-status-id]" && this.dataset.creatorStatusId) return this;
    if (selector === "[data-creator-campaign-id]" && this.dataset.creatorCampaignId) return this;
    if (selector === "[data-creator-page]" && this.dataset.creatorPage) return this;
    return this.parentElement?.closest(selector) || null;
  }

  async dispatch(type, overrides = {}) {
    const event = { target: this, preventDefault() {}, ...overrides };
    for (const listener of [...(this.listeners.get(type) || [])]) await listener(event);
  }
}

class FakeOption extends FakeElement {
  constructor(text = "", value = "", _defaultSelected = false, selected = false) {
    super("option");
    this.textContent = text;
    this.value = value;
    this.selected = selected;
  }
}

function findNode(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children || []) {
    const match = findNode(child, predicate);
    if (match) return match;
  }
  return null;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function creatorDetail(creatorId, name, accounts = []) {
  return {
    record: {
      creator_id: creatorId,
      creator_name: name,
      platform: "TikTok",
      profile_url: `https://www.tiktok.com/@${creatorId}`,
      insight_level: "good",
      source: "extension",
      analysis_time: "2026-08-01T00:00:00Z",
      last_analysis_time: "2026-08-02T00:00:00Z",
      data_updated_at: "2026-08-02T00:00:00Z",
      agency_id: `${creatorId}_agency`,
      agency_name: `${name} Agency`,
    },
    analysis: {
      creator: {
        creator_name: name,
        platform: "TikTok",
        profile_url: `https://www.tiktok.com/@${creatorId}`,
        followers: "10K",
        bio: `${name} bio`,
      },
      content_category: "Gaming",
      video_analysis: { sample_size: 2, average_views: 1000, median_views: 900, view_coverage: 1 },
      creator_insight: { strengths: ["稳定"], risks: [], recommendation: "联系" },
      videos: [],
    },
    snapshots: [{ captured_at: "2026-08-02T00:00:00Z", followers: "10K" }],
    trend: { freshness: { status: "fresh", days: 1 } },
    cooperations: [],
    cooperation_statistics: {},
    accounts,
  };
}

async function run() {
  const ids = [
    "creator-library-search", "creator-library-country",
    "creator-library-language", "creator-library-category", "creator-library-tag",
    "creator-library-level", "creator-library-status", "creator-library-sort",
    "creator-library-card-view", "creator-library-table-view", "creator-library-refresh",
    "creator-library-cards", "creator-library-table-wrap", "creator-library-body",
    "creator-library-empty", "creator-library-detail-summary", "creator-library-detail-level",
    "creator-library-page-size", "creator-library-pagination", "creator-library-page-summary",
    "creator-library-page-buttons",
    "creator-library-basic", "creator-library-video-metrics", "creator-library-data-meta",
    "creator-library-freshness", "creator-library-recommendation", "creator-library-strengths",
    "creator-library-risks", "creator-library-snapshots", "creator-library-snapshots-empty",
    "creator-library-videos", "creator-library-detail-back", "creator-library-detail-task",
    "creator-library-detail-edit", "creator-library-detail-archive",
    "cooperation-stat-count", "cooperation-stat-spend", "cooperation-stat-views",
    "cooperation-stat-roi", "creator-cooperations-body", "creator-cooperations-empty",
    "cooperation-platform", "cooperation-campaign", "cooperation-contact-date",
    "cooperation-price", "cooperation-published-count", "cooperation-total-views",
    "cooperation-average-views", "cooperation-roi", "cooperation-result",
    "cooperation-note", "cooperation-status", "cooperation-save",
    "creator-library-detail-add-campaign", "creator-campaigns-body", "creator-campaigns-empty",
    "creator-campaigns-error", "creator-campaign-modal", "creator-campaign-modal-close",
    "creator-campaign-modal-cancel", "creator-campaign-modal-title", "creator-campaign-creator-name",
    "creator-campaign-agency-name", "creator-campaign-form", "creator-campaign-select",
    "creator-campaign-account-select", "creator-campaign-account-hint",
    "creator-campaign-modal-message", "creator-campaign-submit",
    "creator-edit-modal", "creator-edit-modal-close", "creator-edit-cancel",
    "creator-edit-form", "creator-edit-name", "creator-edit-platform",
    "creator-edit-profile-url", "creator-edit-followers", "creator-edit-content-category",
    "creator-edit-agency", "creator-edit-bio", "creator-edit-message", "creator-edit-save",
  ];
  const selectIds = new Set(ids.filter(id => id.includes("platform") || id.includes("language")
    || id.includes("category") || id.includes("tag") || id.includes("level")
    || id.includes("status") || id.includes("sort")));
  selectIds.add("creator-campaign-select");
  selectIds.add("creator-campaign-account-select");
  selectIds.add("creator-edit-agency");
  selectIds.add("creator-library-page-size");
  const elements = new Map(ids.map(id => [id, new FakeElement(selectIds.has(id) ? "select" : "div", id)]));
  elements.get("creator-library-sort").value = "created_at_desc";
  elements.get("creator-library-page-size").value = "24";
  elements.get("creator-campaign-modal").hidden = true;
  elements.get("creator-edit-modal").hidden = true;

  const tabs = ["overview", "content", "history", "cooperations"].map(name => {
    const tab = new FakeElement("button");
    tab.dataset.detailTab = name;
    return tab;
  });
  const panels = ["overview", "content", "history", "cooperations"].map(name => {
    const panel = new FakeElement("section");
    panel.dataset.detailPanel = name;
    return panel;
  });
  const navButtons = ["dashboard", "creator-library"].map(name => {
    const button = new FakeElement("button", "", ["nav-btn"]);
    button.dataset.page = name;
    button.dataset.primary = name;
    return button;
  });
  const sections = ["dashboard", "creator-library", "creator-library-detail"].map(name => {
    const section = new FakeElement("section", "", ["page"]);
    section.dataset.page = name;
    return section;
  });

  const documentListeners = new Map();
  const document = {
    getElementById(id) {
      return elements.get(id) || null;
    },
    createElement(tagName) {
      return new FakeElement(tagName);
    },
    querySelector(selector) {
      const match = selector.match(/^\.nav-btn\[data-page="(.+)"\]$/);
      return match ? navButtons.find(button => button.dataset.page === match[1]) || null : null;
    },
    querySelectorAll(selector) {
      if (selector === ".nav-btn") return navButtons;
      if (selector === ".page") return sections;
      if (selector === ".detail-tab") return tabs;
      if (selector === ".detail-panel") return panels;
      return [];
    },
    addEventListener(type, listener) {
      const listeners = documentListeners.get(type) || new Set();
      listeners.add(listener);
      documentListeners.set(type, listeners);
    },
    removeEventListener(type, listener) {
      documentListeners.get(type)?.delete(listener);
    },
  };

  const records = [
    { creator_id: "creator_a", analysis_id: "creator_a", creator_name: "Ana", agency_name: "Ana Agency", platform: "TikTok", country: "Brazil", status: "discovered", followers: "10K", analysis_time: "2026-08-01T00:00:00Z" },
    { creator_id: "creator_b", analysis_id: "creator_b", creator_name: "Bella", agency_name: "Bella Agency", platform: "TikTok", country: "USA", status: "discovered", followers: "20K", analysis_time: "2026-08-02T00:00:00Z" },
  ];
  const details = {
    creator_a: creatorDetail("creator_a", "Ana", [
      { account_id: "account_a", platform: "TikTok", username: "ana" },
    ]),
    creator_b: creatorDetail("creator_b", "Bella", [
      { account_id: "account_b_ig", platform: "Instagram", username: "bella.ig" },
      { account_id: "account_b_tt", platform: "TikTok", username: "bella.tt" },
    ]),
  };
  details.creator_b.cooperations = [{
    cooperation_id: "legacy_one",
    campaign: "Legacy Project",
    platform: "TikTok",
    price: 500,
    average_views: 1000,
    roi: 2,
  }];
  details.creator_b.cooperation_statistics = {
    cooperation_count: 1,
    total_spend: 500,
    average_views: 1000,
    average_roi: 2,
  };
  const campaigns = [
    { campaign_id: "campaign_one", name: "Launch One", product_name: "Product A", platform: "TikTok", status: "running", start_date: "2026-08-01", end_date: "2026-08-31" },
    { campaign_id: "campaign_two", name: "Launch Two", product_name: "Product B", platform: "Instagram", status: "draft", start_date: "2026-09-01", end_date: "2026-09-30" },
  ];
  const creatorCampaigns = { creator_a: [], creator_b: [campaigns[0]] };
  const calls = [];
  let paginationTotal = null;
  let holdCreatorA = false;
  let resolveCreatorA = null;
  const api = {
    async get(url, options = {}) {
      calls.push({ method: "GET", url, signal: options.signal });
      if (url.startsWith("/api/creator-library?")) {
        const queryValue = key => {
          const match = url.match(new RegExp(`[?&]${key}=([^&]*)`));
          return match ? decodeURIComponent(match[1]) : "";
        };
        let visible = url.includes("include_archived=true")
          ? records
          : records.filter(record => !record.archived_at);
        const filters = {
          search: queryValue("search"),
          country: queryValue("country"),
          language: queryValue("language"),
          content_category: queryValue("content_category"),
          tag: queryValue("tag"),
          insight_level: queryValue("insight_level"),
          status: queryValue("status"),
        };
        visible = visible.filter(record => {
          const searchable = Object.values(record).join(" ").toLowerCase();
          return (!filters.search || searchable.includes(filters.search.toLowerCase()))
            && (!filters.country || record.country === filters.country)
            && (!filters.language || record.language === filters.language)
            && (!filters.content_category || record.content_category === filters.content_category)
            && (!filters.tag || String(record.tags || "").includes(filters.tag))
            && (!filters.insight_level || record.insight_level === filters.insight_level)
            && (filters.status === "archived"
              ? Boolean(record.archived_at)
              : !filters.status || record.status === filters.status);
        });
        const pageSize = url.includes("page_size=50") ? 50 : 24;
        const total = paginationTotal ?? visible.length;
        return {
          total,
          page: Number(url.match(/[?&]page=(\d+)/)?.[1] || 1),
          page_size: pageSize,
          pages: total ? Math.ceil(total / pageSize) : 0,
          creators: clone(visible),
          records: clone(visible),
          filter_options: {
            country: ["Brazil", "USA"],
            language: [],
            content_category: [],
            tag: [],
          },
        };
      }
      if (url === "/api/local/agencies") {
        return { agencies: [{ agency_id: "agency_new", name: "New Agency" }] };
      }
      if (url === "/api/campaigns") return { campaigns: clone(campaigns) };
      if (url.startsWith("/api/campaigns?creator_id=")) {
        const id = decodeURIComponent(url.split("=").at(-1));
        return { campaigns: clone(creatorCampaigns[id] || []) };
      }
      const match = url.match(/^\/api\/creator-library\/(.+)$/);
      if (!match) throw new Error(`Unexpected GET ${url}`);
      const id = decodeURIComponent(match[1]);
      if (id === "creator_a" && holdCreatorA) {
        return new Promise(resolve => { resolveCreatorA = () => resolve(clone(details.creator_a)); });
      }
      return clone(details[id]);
    },
    async post(url, payload, options = {}) {
      calls.push({ method: "POST", url, payload: clone(payload), signal: options.signal });
      if (url.endsWith("/status")) {
        const id = decodeURIComponent(url.split("/").at(-2));
        records.find(record => record.creator_id === id).status = payload.status;
        return { ok: true };
      }
      const campaignMatch = url.match(/^\/api\/campaigns\/([^/]+)\/creators$/);
      if (campaignMatch) {
        const campaignId = decodeURIComponent(campaignMatch[1]);
        const existing = (creatorCampaigns[payload.creator_id] || []).some(
          campaign => campaign.campaign_id === campaignId,
        );
        if (existing) {
          const error = new Error("duplicate");
          error.status = 409;
          throw error;
        }
        creatorCampaigns[payload.creator_id] ||= [];
        creatorCampaigns[payload.creator_id].push(campaigns.find(item => item.campaign_id === campaignId));
        return {
          campaign_creator: {
            id: "relation_new",
            campaign_id: campaignId,
            creator_id: payload.creator_id,
            account_id: payload.account_id,
          },
        };
      }
      throw new Error(`Unexpected POST ${url}`);
    },
    async patch(url, payload, options = {}) {
      calls.push({ method: "PATCH", url, payload: clone(payload), signal: options.signal });
      const match = url.match(/^\/api\/creator-library\/(.+)$/);
      if (!match) throw new Error(`Unexpected PATCH ${url}`);
      const id = decodeURIComponent(match[1]);
      const record = records.find(item => item.creator_id === id);
      const creator = details[id].analysis.creator;
      if (Object.hasOwn(payload, "archived_at")) {
        record.archived_at = payload.archived_at;
        details[id].record.archived_at = payload.archived_at;
      } else {
        record.creator_name = payload.creator_name;
        record.profile_url = payload.profile_url;
        record.followers = payload.followers;
        record.content_category = payload.content_category;
        record.agency_id = payload.agency_id;
        record.agency_name = payload.agency_id ? "New Agency" : "";
        Object.assign(details[id].record, clone(record));
        Object.assign(creator, {
          creator_name: payload.creator_name,
          profile_url: payload.profile_url,
          followers: payload.followers,
          bio: payload.bio,
        });
        details[id].analysis.content_category = payload.content_category;
      }
      return { creator: clone(record) };
    },
  };

  const notices = [];
  const storage = new Map();
  const window = {
    AbortController,
    localStorage: {
      getItem: key => storage.get(key) || "",
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: key => storage.delete(key),
    },
    setInterval,
    clearInterval,
    setTimeout,
    clearTimeout,
    confirm: () => true,
  };
  const sandbox = { window, document, console, AbortController, Option: FakeOption, Intl, Date, Set, Map };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  for (const file of [
    "webapp/core/page-resources.js",
    "webapp/core/page-registry.js",
    "webapp/pages/creator-library.js",
    "webapp/pages/creator-library-detail.js",
  ]) {
    vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), sandbox, { filename: file });
  }
  window.KOLConnectPages.registerPage("dashboard", { load() {}, bind() {}, unbind() {} });
  let navigatedCampaignId = "";
  window.KOLConnectPages.registerPage("campaign-detail", {
    load(context) { navigatedCampaignId = context.campaignId; },
    bind() {},
    unbind() {},
  });

  const state = {
    currentTaskId: "",
    currentTask: null,
    review: { taskId: "" },
    creatorLibrary: { records: [], viewMode: "card", detailTab: "overview" },
  };
  async function navigate(name, params = {}) {
    const creatorPage = name === "creator-library" || name === "creator-library-detail";
    return window.KOLConnectPages.navigate(name, creatorPage ? {
      state,
      api,
      resources: window.KOLConnectPageResources.create(),
      params,
      navigate,
      ui: { showSaved: message => notices.push(message), showError: error => { throw error; } },
    } : params);
  }

  await navigate("creator-library");
  assert.equal(window.KOLConnectPages.getCurrentPage(), "creator-library");
  assert.equal(elements.get("creator-library-cards").children.length, 2);
  assert.equal(elements.get("creator-library-refresh").listenerCount("click"), 1);
  paginationTotal = 30;
  await elements.get("creator-library-refresh").dispatch("click");
  const nextPage = findNode(
    elements.get("creator-library-page-buttons"),
    node => node.dataset.creatorPage === "2",
  );
  await elements.get("creator-library-page-buttons").dispatch("click", { target: nextPage });
  assert.ok(calls.at(-1).url.includes("page=2"), "pagination must request the selected server page");
  paginationTotal = null;
  state.creatorLibrary.page = 1;
  await elements.get("creator-library-refresh").dispatch("click");
  assert.equal(
    calls.filter(call => call.url.startsWith("/api/campaigns?creator_id=")).length,
    0,
    "Creator list must not query Campaigns per creator",
  );

  const anaCampaignButton = findNode(
    elements.get("creator-library-cards"),
    node => node.dataset.creatorAction === "campaign" && node.dataset.creatorId === "creator_a",
  );
  await elements.get("creator-library-cards").dispatch("click", { target: anaCampaignButton });
  assert.equal(elements.get("creator-campaign-modal").hidden, false, "list must open Campaign modal");
  assert.equal(elements.get("creator-campaign-select").options.length, 3, "Campaign list must load once");
  assert.equal(elements.get("creator-campaign-account-select").options.length, 2, "account list must load from creator detail");
  assert.equal(elements.get("creator-campaign-account-select").value, "account_a", "single account must auto-select");
  await elements.get("creator-campaign-modal-cancel").dispatch("click");

  const bellaCampaignButton = findNode(
    elements.get("creator-library-cards"),
    node => node.dataset.creatorAction === "campaign" && node.dataset.creatorId === "creator_b",
  );
  await elements.get("creator-library-cards").dispatch("click", { target: bellaCampaignButton });
  assert.equal(elements.get("creator-campaign-account-select").value, "", "multiple accounts require manual selection");
  elements.get("creator-campaign-select").value = "campaign_one";
  await elements.get("creator-campaign-select").dispatch("change");
  assert.equal(elements.get("creator-campaign-account-select").options[1].value, "account_b_tt", "matching platform account must be shown first");
  elements.get("creator-campaign-account-select").value = "account_b_tt";
  await elements.get("creator-campaign-form").dispatch("submit");
  assert.equal(elements.get("creator-campaign-modal-message").textContent, "该达人已经加入此 Campaign。", "409 must show a friendly duplicate message");

  elements.get("creator-campaign-select").value = "campaign_two";
  await elements.get("creator-campaign-select").dispatch("change");
  elements.get("creator-campaign-account-select").value = "account_b_ig";
  await elements.get("creator-campaign-form").dispatch("submit");
  assert.equal(elements.get("creator-campaign-modal").hidden, true, "successful creation must close modal");
  const createCall = calls.find(call => call.method === "POST" && call.url === "/api/campaigns/campaign_two/creators");
  assert.deepEqual(createCall.payload, { creator_id: "creator_b", account_id: "account_b_ig" });

  const savedAccounts = details.creator_a.accounts;
  details.creator_a.accounts = [];
  await elements.get("creator-library-cards").dispatch("click", { target: anaCampaignButton });
  assert.equal(elements.get("creator-campaign-submit").disabled, true, "creator without account cannot submit");
  assert.match(elements.get("creator-campaign-account-hint").textContent, /暂无可用社交账号/);
  details.creator_a.accounts = savedAccounts;
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("creator-campaign-modal").hidden, true, "leaving page must close modal");
  assert.equal(elements.get("creator-campaign-form").listenerCount("submit"), 0, "leaving page must release modal listeners");
  assert.equal(documentListeners.get("keydown")?.size || 0, 0, "leaving page must release keyboard listener");
  await navigate("creator-library");

  elements.get("creator-library-search").value = "Bella";
  await elements.get("creator-library-search").dispatch("input");
  await new Promise(resolve => setTimeout(resolve, 300));
  assert.equal(elements.get("creator-library-cards").children.length, 1, "search must filter cards");

  elements.get("creator-library-search").value = "";
  elements.get("creator-library-country").value = "Brazil";
  await elements.get("creator-library-country").dispatch("change");
  assert.equal(elements.get("creator-library-cards").children.length, 1, "country filter must update cards");
  elements.get("creator-library-country").value = "";
  await elements.get("creator-library-country").dispatch("change");
  await elements.get("creator-library-table-view").dispatch("click");
  assert.equal(state.creatorLibrary.viewMode, "table");
  assert.equal(storage.get("creator_library_view_mode"), "table");
  assert.equal(elements.get("creator-library-table-wrap").hidden, false);
  assert.equal(elements.get("creator-library-cards").children.length, 0, "table mode must not render cards");
  assert.ok(calls.at(-1).url.includes("page_size=50"), "table mode must request its default page size");
  await window.KOLConnectPages.navigate("dashboard");
  state.creatorLibrary.viewMode = "card";
  await navigate("creator-library");
  assert.equal(state.creatorLibrary.viewMode, "table", "stored view mode must survive a page reload");
  await elements.get("creator-library-card-view").dispatch("click");
  assert.equal(state.creatorLibrary.viewMode, "card");
  assert.equal(elements.get("creator-library-body").children.length, 0, "card mode must not render table rows");
  elements.get("creator-library-sort").value = "followers_desc";
  await elements.get("creator-library-sort").dispatch("change");
  assert.ok(calls.at(-1).url.includes("sort=followers&order=desc"), "sorting must be requested from the API");

  elements.get("creator-library-search").value = "Bella";
  await elements.get("creator-library-search").dispatch("input");
  await new Promise(resolve => setTimeout(resolve, 300));

  await elements.get("creator-library-table-view").dispatch("click");
  const statusSelect = findNode(elements.get("creator-library-body"), node => node.dataset.creatorStatusId === "creator_b");
  statusSelect.value = "contacted";
  await elements.get("creator-library-body").dispatch("change", { target: statusSelect });
  assert.equal(records[1].status, "contacted");

  await elements.get("creator-library-card-view").dispatch("click");
  const detailButton = findNode(elements.get("creator-library-cards"), node => node.dataset.creatorAction === "detail");
  await elements.get("creator-library-cards").dispatch("click", { target: detailButton });
  assert.equal(window.KOLConnectPages.getCurrentPage(), "creator-library-detail");
  assert.match(elements.get("creator-library-detail-summary").textContent, /Bella/);
  assert.equal(elements.get("creator-library-snapshots").children.length, 1, "snapshot history must render");
  assert.match(elements.get("creator-library-freshness").textContent, /最新/, "trend freshness must render");
  assert.equal(elements.get("creator-campaigns-body").children.length, 2, "detail must show joined Campaigns");
  assert.equal(elements.get("creator-library-detail-back").listenerCount("click"), 1);

  const profileLink = findNode(
    elements.get("creator-library-basic"),
    node => node.tagName === "a" && node.href === details.creator_b.record.profile_url,
  );
  assert.ok(profileLink, "profile URL must render as a link");
  assert.equal(profileLink.target, "_blank");
  assert.equal(profileLink.rel, "noopener noreferrer");

  await elements.get("creator-library-detail-edit").dispatch("click");
  assert.equal(elements.get("creator-edit-modal").hidden, false);
  assert.equal(elements.get("creator-edit-agency").children.length, 2);
  elements.get("creator-edit-name").value = "Bella Updated";
  elements.get("creator-edit-profile-url").value = "https://www.tiktok.com/@bella-updated";
  elements.get("creator-edit-followers").value = "25K";
  elements.get("creator-edit-content-category").value = "Lifestyle";
  elements.get("creator-edit-bio").value = "Updated bio";
  elements.get("creator-edit-agency").value = "agency_new";
  await elements.get("creator-edit-form").dispatch("submit");
  const profilePatch = calls.find(call => call.method === "PATCH" && call.payload.creator_name);
  assert.ok(profilePatch, "profile edit must use the Creator PATCH endpoint");
  assert.equal(profilePatch.payload.agency_id, "agency_new");
  assert.match(elements.get("creator-library-detail-summary").textContent, /Bella Updated/);

  assert.equal(elements.get("creator-cooperations-body").children.length, 1, "legacy cooperation history must remain visible");
  assert.equal(elements.get("cooperation-save").listenerCount("click"), 0, "legacy cooperation must be read-only");
  assert.equal(calls.some(call => call.url.endsWith("/cooperations")), false);

  const campaignDetailButton = findNode(
    elements.get("creator-campaigns-body"),
    node => node.dataset.creatorCampaignId === "campaign_one",
  );
  await elements.get("creator-campaigns-body").dispatch("click", { target: campaignDetailButton });
  assert.equal(navigatedCampaignId, "campaign_one", "Campaign row must navigate with campaignId context");
  await navigate("creator-library-detail", { creatorId: "creator_b" });
  await elements.get("creator-library-detail-add-campaign").dispatch("click");
  assert.equal(elements.get("creator-campaign-modal").hidden, false, "detail must open the shared Campaign modal");
  assert.equal(elements.get("creator-campaign-creator-name").textContent, "Bella Updated");
  await elements.get("creator-campaign-modal-cancel").dispatch("click");

  await elements.get("creator-library-detail-archive").dispatch("click");
  assert.ok(details.creator_b.record.archived_at, "archive must preserve the record with archived_at");
  assert.equal(elements.get("creator-library-detail-add-campaign").disabled, true);

  elements.get("creator-library-search").value = "";
  await elements.get("creator-library-detail-back").dispatch("click");
  assert.equal(window.KOLConnectPages.getCurrentPage(), "creator-library");
  assert.equal(elements.get("creator-library-detail-back").listenerCount("click"), 0);
  assert.equal(elements.get("creator-library-refresh").listenerCount("click"), 1);
  assert.equal(elements.get("creator-library-cards").children.length, 1, "archived Creator must be hidden by default");
  elements.get("creator-library-status").value = "archived";
  await elements.get("creator-library-status").dispatch("change");
  assert.equal(elements.get("creator-library-cards").children.length, 1, "archived filter must show archived Creators");
  const restoreButton = findNode(
    elements.get("creator-library-cards"),
    node => node.dataset.creatorAction === "restore" && node.dataset.creatorId === "creator_b",
  );
  await elements.get("creator-library-cards").dispatch("click", { target: restoreButton });
  assert.equal(details.creator_b.record.archived_at, null, "restore must clear archived_at");

  await navigate("creator-library");
  assert.equal(elements.get("creator-library-refresh").listenerCount("click"), 1, "repeat entry must not duplicate listeners");
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("creator-library-refresh").listenerCount("click"), 0, "leaving page must release listeners");

  holdCreatorA = true;
  const creatorANavigation = navigate("creator-library-detail", { creatorId: "creator_a" });
  await Promise.resolve();
  const creatorBNavigation = navigate("creator-library-detail", { creatorId: "creator_b" });
  await creatorBNavigation;
  resolveCreatorA();
  await creatorANavigation;
  assert.match(elements.get("creator-library-detail-summary").textContent, /Bella/, "stale detail must not overwrite current creator");

  await assert.rejects(() => navigate("creator-library-detail"), /Creator ID is required/);
  assert.match(elements.get("creator-library-detail-summary").textContent, /缺少 Creator ID/);

  const appSource = fs.readFileSync(path.join(root, "webapp/app.js"), "utf8");
  assert.doesNotMatch(appSource, /"creator-library": \(\) =>/);
  assert.doesNotMatch(appSource, /creator-library-refresh"\)\.addEventListener/);
  const html = fs.readFileSync(path.join(root, "webapp/index.html"), "utf8");
  assert.match(html, /pages\/creator-library\.js/);
  assert.match(html, /pages\/creator-library-detail\.js/);
  assert.match(html, /Legacy Cooperation/);
  assert.match(html, /历史合作（只读）/);
  assert.doesNotMatch(html, /id="cooperation-save"/);
  assert.doesNotMatch(html, /新增合作记录/);
  const detailSource = fs.readFileSync(path.join(root, "webapp/pages/creator-library-detail.js"), "utf8");
  assert.doesNotMatch(detailSource, /saveCooperation/);
  assert.doesNotMatch(detailSource, /\/cooperations`/);
  console.log("Phase 3.11.3 Creator Library lifecycle migration: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
