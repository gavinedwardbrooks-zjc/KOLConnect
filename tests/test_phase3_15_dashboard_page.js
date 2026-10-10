const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

class FakeClassList {
  constructor(values = []) {
    this.values = new Set(values);
  }

  contains(value) {
    return this.values.has(value);
  }

  add(value) {
    this.values.add(value);
  }

  remove(value) {
    this.values.delete(value);
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
    this.listeners = new Map();
    this.parentElement = null;
    this.textContent = "";
    this.type = "";
    this.open = false;
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
    const existingIndex = this.children.indexOf(child);
    if (existingIndex >= 0) this.children.splice(existingIndex, 1);
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  append(...children) {
    children.forEach(child => this.appendChild(child));
  }

  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }

  querySelectorAll(selector) {
    if (selector === "[data-dashboard-v2-module]") {
      return this.children.filter(child => child.dataset.dashboardV2Module);
    }
    return [];
  }

  closest(selector) {
    if (selector === "[data-dashboard-campaign-id]" && this.dataset.dashboardCampaignId) return this;
    if (selector === "[data-dashboard-creator-id]" && this.dataset.dashboardCreatorId) return this;
    if (selector === "[data-dashboard-v2-open]" && this.dataset.dashboardV2Open) return this;
    if (selector === "[data-dashboard-v2-drawer-close]" && this.dataset.dashboardV2DrawerClose !== undefined) return this;
    if (selector === "[data-dashboard-v2-drawer-primary]" && this.dataset.dashboardV2DrawerPrimary) return this;
    if (selector === "#dashboard-v2-customize" && this.id === "dashboard-v2-customize") return this;
    return this.parentElement?.closest(selector) || null;
  }

  focus() {}

  showModal() {
    this.open = true;
  }

  close() {
    this.open = false;
  }

  async dispatch(type, overrides = {}) {
    const event = { target: this, currentTarget: this, preventDefault() {}, ...overrides };
    for (const listener of [...(this.listeners.get(type) || [])]) await listener(event);
  }

  getContext() {
    return { canvas: this };
  }
}

function dashboardResponse(totalCreators = 12) {
  return {
    overview: {
      total_creators: totalCreators,
      new_creators_7d: 2,
      discovered_count: 4,
      cooperating_count: 3,
      cooperation_spend: 1500,
      average_roi: 1.8,
    },
    creator_health: {
      rising_creators: [{ creator_id: "creator_one", creator_name: "Maria", platform: "TikTok", change: { metric: "followers", direction: "growth", delta: 200 } }],
      falling_creators: [],
      expired_creators: [],
    },
    cooperation_performance: {
      total_campaigns: 3,
      total_cost: 1500,
      total_views: 80000,
      average_roi: 1.8,
      top_creators: [],
    },
    action_items: {
      expired_creators: [],
      pending_contact: [],
      incomplete_cooperations: [],
    },
    action_center: { as_of_date: "2026-10-10", items: [] },
    platform_distribution: [
      { platform: "TikTok", count: 8 },
      { platform: "YouTube", count: 4 },
    ],
    creator_status_distribution: [
      { status: "discovered", count: 9 },
      { status: "contacted", count: 3 },
    ],
    creator_growth_trend: [
      { date: "2026-08-20", count: 1 },
      { date: "2026-08-21", count: 2 },
    ],
    dashboard_v2: {
      creator_count: totalCreators,
      account_count: totalCreators + 3,
      platform_accounts: [{ platform: "TikTok", count: 8 }],
      missing: {
        email_accounts: [{ creator_id: "creator_one", creator_name: "Maria", platform: "TikTok", username: "maria", profile_url: "https://www.tiktok.com/@maria" }],
        country_creators: [],
        language_creators: [],
        content_type_creators: [],
      },
      campaigns: [{ campaign_id: "campaign_one", name: "Campaign One", status: "running", creator_count: 2, published_count: 1 }],
    },
  };
}

function risksResponse() {
  return {
    summary: { high: 0, medium: 0, low: 0 },
    cards: [],
  };
}

function platformAnalyticsResponse() {
  return {
    platforms: [
      { platform: "tiktok", creator_count: 8, campaign_creator_count: 4, published_count: 3 },
      { platform: "instagram", creator_count: 2, campaign_creator_count: 1, published_count: 1 },
      { platform: "youtube", creator_count: 4, campaign_creator_count: 2, published_count: 1 },
    ],
    summary: { platform_count: 3, creator_count: 14, campaign_creator_count: 7, ignored_campaign_creator_count: 0 },
  };
}

function geographyResponse() {
  return {
    countries: [{ name: "Brazil", creator_count: 5, active_creator_count: 4 }],
    languages: [{ name: "Portuguese", creator_count: 5 }],
  };
}

function roiTrendResponse() {
  return {
    trend: [
      { month: "2026-01", average_recorded_roi: 1.2 },
      { month: "2026-03", average_recorded_roi: 2.4 },
    ],
  };
}

function mailFollowUpResponse() {
  return {
    groups: [
      { creator_id: "creator_internal", creator_name: "邮件达人", correspondent_email: "creator@example.com", waiting_for: "me", actionability: "normal" },
      { creator_id: "creator_internal_2", creator_name: "", correspondent_email: "reply@example.com", waiting_for: "creator", actionability: "normal" },
      { creator_id: "creator_internal_3", creator_name: "待确认达人", correspondent_email: "unknown@example.com", waiting_for: "unknown", actionability: "normal" },
      { creator_id: "creator_internal_4", creator_name: "已停止达人", correspondent_email: "stopped@example.com", waiting_for: "me", actionability: "stopped" },
      { creator_id: "creator_internal_5", creator_name: "已延后达人", correspondent_email: "snoozed@example.com", waiting_for: "creator", actionability: "snoozed" },
    ],
  };
}

function deferred() {
  let resolve;
  const promise = new Promise(next => { resolve = next; });
  return { promise, resolve };
}

async function run() {
  const ids = [
    "dashboard-refresh", "dashboard-total-creators", "dashboard-new-creators",
    "dashboard-discovered", "dashboard-cooperating", "dashboard-spend",
    "dashboard-average-roi", "dashboard-campaigns", "dashboard-total-cost",
    "dashboard-total-views", "dashboard-cooperation-roi", "dashboard-rising-creators",
    "dashboard-falling-creators", "dashboard-expired-creators", "dashboard-action-expired",
    "dashboard-pending-contact", "dashboard-incomplete-cooperations", "dashboard-top-creators",
    "dashboard-platform-chart", "dashboard-status-chart", "dashboard-growth-chart",
    "dashboard-platform-chart-empty", "dashboard-status-chart-empty", "dashboard-growth-chart-empty",
    "dashboard-risk-high", "dashboard-risk-medium", "dashboard-risk-low", "dashboard-risk-error",
    "dashboard-platform-analytics-chart", "dashboard-platform-analytics-empty",
    "dashboard-platform-analytics-error", "dashboard-country-list", "dashboard-language-list",
    "dashboard-geography-error", "dashboard-roi-trend-chart", "dashboard-roi-trend-empty",
    "dashboard-roi-trend-error", "dashboard-roi-latest",
    "dashboard-v2-creator-count", "dashboard-v2-account-count", "dashboard-v2-campaign-count",
    "dashboard-v2-spend", "dashboard-v2-roi", "dashboard-v2-missing-email",
    "dashboard-v2-missing-country", "dashboard-v2-missing-language", "dashboard-v2-missing-content-type",
    "dashboard-v2-today-list", "dashboard-v2-campaign-list", "dashboard-v2-platform-list",
    "dashboard-v2-mail-waiting-me", "dashboard-v2-mail-waiting-creator", "dashboard-v2-mail-waiting-unknown",
    "dashboard-v2-mail-actionable-total", "dashboard-v2-mail-followup-list", "dashboard-v2-mail-followup-empty",
    "dashboard-v2-mail-followup-error",
    "dashboard-v2-health-score", "dashboard-v2-health-healthy", "dashboard-v2-health-warning",
    "dashboard-v2-health-critical", "dashboard-v2-country-list", "dashboard-v2-language-list",
    "dashboard-v2-roi-latest",
    "dashboard-v2-drawer", "dashboard-v2-drawer-title", "dashboard-v2-drawer-count",
    "dashboard-v2-drawer-search", "dashboard-v2-drawer-list", "dashboard-v2-drawer-primary",
    "dashboard-v2-customize", "dashboard-customization-dialog", "dashboard-customization-modules",
    "dashboard-customization-reset", "dashboard-customization-done", "dashboard-customization-close",
  ];
  for (const platform of ["tiktok", "instagram", "youtube"]) {
    for (const metric of ["creators", "followers-median", "followers-average", "relations", "publish-rate", "views", "likes", "comments", "engagement", "cost", "roi"]) {
      ids.push(`platform-${platform}-${metric}`);
    }
  }
  const elements = new Map(ids.map(id => [id, new FakeElement("div", id)]));
  const v2Modules = ["today", "mail_follow_up", "missing_info", "campaigns", "creator_overview", "data_freshness", "geography", "roi"];
  const v2ModuleContainer = new FakeElement("div", "dashboard-v2-modules");
  v2Modules.forEach(id => {
    const module = new FakeElement("section");
    module.dataset.dashboardV2Module = id;
    v2ModuleContainer.appendChild(module);
  });
  elements.set("dashboard-v2-modules", v2ModuleContainer);
  const navButtons = ["dashboard", "products"].map(name => {
    const button = new FakeElement("button", "", ["nav-btn"]);
    button.dataset.page = name;
    button.dataset.primary = name;
    return button;
  });
  const sections = ["dashboard", "products"].map(name => {
    const section = new FakeElement("section", "", ["page"]);
    section.dataset.page = name;
    return section;
  });

  const document = {
    getElementById(id) {
      return elements.get(id) || null;
    },
    createElement(tagName) {
      return new FakeElement(tagName);
    },
    querySelector(selector) {
      const navMatch = selector.match(/^\.nav-btn\[data-page="(.+)"\]$/);
      if (navMatch) return navButtons.find(button => button.dataset.page === navMatch[1]) || null;
      const pageMatch = selector.match(/^\.page\[data-page="(.+)"\]$/);
      if (pageMatch) return sections.find(section => section.dataset.page === pageMatch[1]) || null;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".nav-btn") return navButtons;
      if (selector === ".page") return sections;
      return [];
    },
  };

  const calls = [];
  const navigations = [];
  const errors = [];
  const responses = [];
  const mailFollowUpResponses = [];
  const chartCalls = [];
  class FakeChart {
    constructor(context, config) {
      this.context = context;
      this.config = config;
      this.destroyed = false;
      chartCalls.push(this);
    }

    destroy() {
      this.destroyed = true;
    }
  }
  const api = {
    async get(url, options = {}) {
      calls.push({ url, signal: options.signal });
      if (url === "/api/risks") return clone(risksResponse());
      if (url === "/api/analytics/platforms") return clone(platformAnalyticsResponse());
      if (url === "/api/analytics/geography") return clone(geographyResponse());
      if (url === "/api/analytics/roi-trend") return clone(roiTrendResponse());
      if (url === "/api/mail/follow-up") {
        const response = mailFollowUpResponses.length ? mailFollowUpResponses.shift() : mailFollowUpResponse();
        return response instanceof Promise ? response : clone(response);
      }
      if (url !== "/api/dashboard") throw new Error(`Unexpected GET ${url}`);
      const response = responses.length ? responses.shift() : dashboardResponse();
      return response instanceof Promise ? response : clone(response);
    },
  };
  const window = {
    AbortController,
    KOLConnectAPI: api,
    Chart: FakeChart,
    KOLConnectApp: {
      showError(error) { errors.push(error); },
      t(key, values = {}) {
        const translations = {
          dashboardDrawerCount: "共 {count} {unit}", dashboardAccountUnit: "个账号", dashboardBulkFillEmail: "批量补全邮箱",
          dashboardUnnamedCreator: "未命名达人", dashboardNoRisingCreators: "暂无上升达人。", dashboardNoFallingCreators: "暂无下滑达人。",
          dashboardNoExpiredData: "暂无过期数据。", dashboardNoDataToUpdate: "暂无需要更新的数据。", dashboardNoPendingContact: "暂无待联系达人。",
          dashboardNoReviewItems: "暂无待复盘事项。", dashboardNoCooperationData: "暂无合作数据。", dashboardRecentAnalysis: "最近分析：{time}",
          dashboardExpiredDays: "已过期 {days} 天", dashboardPendingContactStatus: "状态：待联系", dashboardCampaignLabel: "Campaign：{campaign}",
          dashboardUnnamedCampaign: "未命名 Campaign", dashboardRoiUnavailable: "ROI 暂无", dashboardCampaignSummary: "{count} 个 Campaign · {roi}",
          dashboardNoPriorityItems: "暂无需要优先处理的事项。", dashboardDataExpired: "数据过期", dashboardPendingContact: "待联系",
          dashboardNoNextActions: "暂无需要处理的事项。", dashboardActionOverdue: "逾期", dashboardActionDueToday: "今天到期",
          dashboardActionNeedDecision: "需要我决定", dashboardActionContentReview: "内容待审核", dashboardActionContentScript: "脚本",
          dashboardWaitingToConnect: "等待建立联系", dashboardUnnamedObject: "未命名对象", dashboardNoCampaigns: "暂无 Campaign。",
          dashboardCampaignProgress: "{status} · {creators} 位达人 · 已发布 {published}", dashboardNoPlatformAccounts: "暂无平台账号数据。",
          dashboardOtherPlatform: "其他", dashboardAccountCount: "{count} 个账号", dashboardHealthScore: "{score} 分", dashboardNoData: "暂无数据",
          dashboardNoSearchMatches: "没有符合当前搜索条件的对象。", dashboardAccountUnavailable: "账号信息未录入", dashboardCountryLanguageMissing: "国家/语言待补充",
          dashboardViewCreator: "查看达人", dashboardMissingEmailAccounts: "缺少邮箱的账号", dashboardMissingCountryCreators: "缺少国家/地区的达人",
          dashboardMissingLanguageCreators: "缺少语言的达人", dashboardMissingContentTypeCreators: "缺少内容类型的达人", dashboardCreatorUnit: "位达人",
          dashboardCreatorChart: "达人", dashboardCooperationChart: "合作", dashboardPublishedChart: "已发布", dashboardActiveCreators: "活跃 {count}",
          dashboardNoRecordedRoi: "暂无已录入 ROI", dashboardNoTrend: "暂无趋势数据", dashboardMedianViews: "中位播放", dashboardFollowers: "粉丝",
          dashboardGrowth: "增长", dashboardDecline: "下降", dashboardUnspecifiedCurrency: "未标币种", mailFollowupWaitingMe: "待我回复",
          mailFollowupWaitingCreator: "待对方回复", mailFollowupWaitingUnknown: "状态未知",
        };
        return String(translations[key] || key).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
      },
      navigate(pageName, params) {
        navigations.push({ pageName, params });
        return Promise.resolve();
      },
    },
    setInterval,
    clearInterval,
    setTimeout,
    clearTimeout,
    Event: class Event { constructor(type, options = {}) { this.type = type; this.bubbles = options.bubbles; } },
    localStorage: {
      values: new Map([
        ["kolconnect-dashboard-layout-v1", JSON.stringify({ order: ["cooperation_overview"], visible: { cooperation_overview: false } })],
        ["kolconnect-dashboard-layout-v2", JSON.stringify({ version: 2, order: v2Modules, visible: {} })],
      ]),
      getItem(key) { return this.values.get(key) || null; },
      setItem(key, value) { this.values.set(key, String(value)); },
    },
    dispatchEvent() {},
  };
  const sandbox = { AbortController, console, document, Intl, window };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(read("webapp/core/page-resources.js"), sandbox);
  vm.runInContext(read("webapp/core/page-registry.js"), sandbox);
  vm.runInContext(read("webapp/pages/dashboard.js"), sandbox);
  window.KOLConnectPages.registerPage("products", {
    load: () => {},
    bind: () => {},
    unbind: () => {},
  });

  const initialDashboard = dashboardResponse(30);
  initialDashboard.action_items.incomplete_cooperations = [{
    cooperation_id: "relation_one",
    creator_id: "creator_one",
    creator_name: "Maria",
    platform: "TikTok",
    campaign: "Campaign One",
    campaign_id: "campaign_one",
  }];
  initialDashboard.action_items.expired_creators = [{ creator_id: "stale_creator", creator_name: "Old stale creator" }];
  initialDashboard.action_items.pending_contact = [{ creator_id: "old_contact", creator_name: "Old pending contact" }];
  initialDashboard.action_center.items = [
    { type: "due_action", priority: "overdue", campaign_id: "campaign_one", creator_name: "Maria", campaign_name: "Campaign One", next_action: "Send brief", due_date: "2026-10-08", need_my_decision: true },
    { type: "due_action", priority: "due_today", campaign_id: "campaign_two", creator_name: "Ana", campaign_name: "Campaign Two", next_action: "Confirm quote", due_date: "2026-10-10", need_my_decision: false },
    { type: "need_my_decision", priority: "need_my_decision", campaign_id: "campaign_three", creator_name: "Jo", campaign_name: "Campaign Three", next_action: "Pick a format" },
    { type: "content_review", priority: "pending_review", campaign_id: "campaign_four", creator_name: "Lee", campaign_name: "Campaign Four", content_type: "script" },
    { type: "content_review", priority: "pending_review", creator_id: "unrelated_creator", creator_name: "No campaign", campaign_name: "Orphan", content_type: "script" },
    { type: "content_review", priority: "pending_review", campaign_id: "campaign_six", creator_name: "Six", campaign_name: "Campaign Six" },
    { type: "content_review", priority: "pending_review", campaign_id: "campaign_seven", creator_name: "Seven", campaign_name: "Campaign Seven" },
  ];
  responses.push(initialDashboard);
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(calls.length, 6);
  const dashboardCall = calls.find(call => call.url === "/api/dashboard");
  const riskCall = calls.find(call => call.url === "/api/risks");
  const analyticsCall = calls.find(call => call.url === "/api/analytics/platforms");
  const geographyCall = calls.find(call => call.url === "/api/analytics/geography");
  const roiTrendCall = calls.find(call => call.url === "/api/analytics/roi-trend");
  const mailFollowUpCall = calls.find(call => call.url === "/api/mail/follow-up");
  assert.ok(dashboardCall, "Dashboard should request its existing aggregate payload");
  assert.ok(riskCall, "Dashboard should request the independent risk summary");
  assert.ok(analyticsCall, "Dashboard should request independent platform analytics");
  assert.ok(geographyCall, "Dashboard should request independent geography analytics");
  assert.ok(roiTrendCall, "Dashboard should request independent recorded ROI trend");
  assert.ok(mailFollowUpCall, "Dashboard should request the canonical Mail Follow-up read model");
  assert.ok(dashboardCall.signal instanceof AbortSignal);
  assert.ok(riskCall.signal instanceof AbortSignal);
  assert.ok(analyticsCall.signal instanceof AbortSignal);
  assert.ok(geographyCall.signal instanceof AbortSignal);
  assert.ok(roiTrendCall.signal instanceof AbortSignal);
  assert.ok(mailFollowUpCall.signal instanceof AbortSignal);
  assert.equal(elements.get("dashboard-total-creators").textContent, "30");
  assert.equal(elements.get("dashboard-campaigns").textContent, "3");
  assert.equal(elements.get("dashboard-risk-high").textContent, "0");
  assert.equal(elements.get("dashboard-risk-medium").textContent, "0");
  assert.equal(elements.get("dashboard-risk-low").textContent, "0");
  assert.equal(elements.get("dashboard-v2-creator-count").textContent, "30");
  assert.equal(elements.get("dashboard-v2-account-count").textContent, "33");
  assert.equal(elements.get("dashboard-v2-missing-email").textContent, "1");
  const nextActions = elements.get("dashboard-v2-today-list").children;
  assert.equal(nextActions.length, 6, "existing Dashboard list stays compact and preserves backend ordering");
  assert.equal(nextActions[0].children[0].textContent, "逾期 · 需要我决定", "due and decision stay on one item");
  assert.equal(nextActions[0].children[1].textContent, "Send brief");
  assert.equal(nextActions[0].children[2].textContent, "Maria · Campaign One");
  assert.equal(nextActions[1].children[0].textContent, "今天到期");
  assert.equal(nextActions[1].children[1].textContent, "Confirm quote");
  assert.equal(nextActions[2].children[1].textContent, "需要我决定");
  assert.match(nextActions[2].children[2].textContent, /Jo · Campaign Three · Pick a format/);
  assert.equal(nextActions[3].children[1].textContent, "内容待审核");
  assert.equal(nextActions[3].children[2].textContent, "Lee · Campaign Four · 脚本");
  assert.equal(nextActions[4].disabled, true, "missing Campaign ID must fail closed");
  assert.equal(nextActions[4].dataset.dashboardCreatorId, undefined, "no Creator detail fallback on Action Center rows");
  assert.doesNotMatch(nextActions.flatMap(row => row.children.map(child => child.textContent)).join(" "), /Old stale creator|Old pending contact|数据过期|待联系/);
  assert.equal(elements.get("dashboard-v2-mail-waiting-me").textContent, "1");
  assert.equal(elements.get("dashboard-v2-mail-waiting-creator").textContent, "1");
  assert.equal(elements.get("dashboard-v2-mail-waiting-unknown").textContent, "1");
  assert.equal(elements.get("dashboard-v2-mail-actionable-total").textContent, "3");
  assert.equal(elements.get("dashboard-v2-mail-followup-list").children.length, 3);
  assert.match(elements.get("dashboard-v2-mail-followup-list").children[0].children[0].textContent, /邮件达人/);
  assert.doesNotMatch(elements.get("dashboard-v2-mail-followup-list").children.map(row => row.children.map(child => child.textContent).join("")).join(""), /creator_internal/);
  assert.equal(elements.get("dashboard-v2-campaign-list").children[0].dataset.dashboardCampaignId, "campaign_one");
  await sections[0].dispatch("click", { target: nextActions[0].children[1] });
  assert.equal(navigations.at(-1).pageName, "campaign-detail");
  assert.equal(navigations.at(-1).params.campaignId, "campaign_one");
  const navigationCount = navigations.length;
  await sections[0].dispatch("click", { target: nextActions[4].children[1] });
  assert.equal(navigations.length, navigationCount, "missing Campaign ID cannot navigate to an unrelated Creator");
  navigations.pop();
  const missingEmailButton = new FakeElement("button");
  missingEmailButton.dataset.dashboardV2Open = "missing-email";
  await sections[0].dispatch("click", { target: missingEmailButton });
  assert.equal(elements.get("dashboard-v2-drawer").hidden, false);
  assert.equal(elements.get("dashboard-v2-drawer-count").textContent, "共 1 个账号");
  assert.equal(elements.get("dashboard-v2-drawer-list").children.length, 1, "drawer must use the same collection as the missing-email metric");
  assert.equal(elements.get("dashboard-v2-drawer-primary").textContent, "批量补全邮箱");
  const drawerViewCreator = elements.get("dashboard-v2-drawer-list").children[0].children[3].children.at(-1);
  await elements.get("dashboard-v2-drawer").dispatch("click", { target: drawerViewCreator });
  assert.equal(navigations.length, 1);
  assert.equal(navigations[0].pageName, "creator-library-detail", "drawer must open the existing Creator detail workflow");
  assert.equal(navigations[0].params.creatorId, "creator_one");
  const campaignOverview = new FakeElement("button");
  campaignOverview.dataset.dashboardV2Open = "campaigns";
  await sections[0].dispatch("click", { target: campaignOverview });
  assert.equal(navigations[1].pageName, "campaigns", "Campaign overview opens the existing Campaign workflow");
  const accountOverview = new FakeElement("button");
  accountOverview.dataset.dashboardV2Open = "accounts";
  await sections[0].dispatch("click", { target: accountOverview });
  assert.equal(navigations[2].pageName, "creator-library", "Account overview opens the existing Creator Library workflow");
  const mailFollowUpOverview = new FakeElement("button");
  mailFollowUpOverview.dataset.dashboardV2Open = "mail-follow-up";
  await sections[0].dispatch("click", { target: mailFollowUpOverview });
  assert.equal(navigations[3].pageName, "mail-follow-up", "Mail Follow-up overview opens the existing Mail Follow-up page");
  assert.equal(chartCalls.length, 5);
  assert.deepEqual(chartCalls[0].config.data.labels, ["TikTok", "YouTube"]);
  assert.deepEqual(chartCalls[1].config.data.datasets[0].data, [9, 3]);
  assert.deepEqual(chartCalls[2].config.data.datasets[0].data, [1, 2]);
  assert.deepEqual(Array.from(chartCalls[3].config.data.labels), ["TikTok", "Instagram", "YouTube"]);
  assert.deepEqual(Array.from(chartCalls[4].config.data.labels), ["2026-01", "2026-03"]);
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 1);
  assert.equal(sections[0].listenerCount("click"), 1);

  const preferences = window.KOLConnectDashboardPreferences;
  assert.deepEqual(Array.from(preferences.get().order), v2Modules, "V2 must ignore retired V1 layouts");
  assert.equal(preferences.get().visible.today, true, "today remains fixed and visible");

  const customizeButton = elements.get("dashboard-v2-customize");
  await sections[0].dispatch("click", { target: customizeButton });
  const customizationDialog = elements.get("dashboard-customization-dialog");
  const customizationModules = elements.get("dashboard-customization-modules");
  assert.equal(customizationDialog.open, true, "customization opens in the Dashboard modal");
  assert.equal(customizationModules.children.length, v2Modules.length, "modal renders every V2 module");
  const todayInput = customizationModules.children[0].children[0].children[0];
  assert.equal(todayInput.disabled, true, "Today Actions remains fixed first and visible");
  const missingInfoInput = customizationModules.children.find(row => row.children[0].children[0].dataset.dashboardVisible === "missing_info").children[0].children[0];
  missingInfoInput.checked = false;
  await customizationModules.dispatch("change", { target: missingInfoInput });
  assert.equal(preferences.get().visible.missing_info, false, "modal visibility control persists through V2 preferences");
  await elements.get("dashboard-customization-reset").dispatch("click");
  assert.deepEqual(Array.from(preferences.get().order), v2Modules, "modal reset restores V2 defaults");
  await elements.get("dashboard-customization-done").dispatch("click");
  assert.equal(customizationDialog.open, false, "Done closes the modal");

  // This mirrors Settings -> Dashboard without a browser reload: Settings only
  // mutates the shared preferences, then the page registry reactivates Dashboard.
  preferences.setVisible("missing_info", false);
  assert.equal(v2ModuleContainer.children.find(node => node.dataset.dashboardV2Module === "missing_info").hidden, true);
  assert.equal(v2ModuleContainer.children[0].dataset.dashboardV2Module, "today", "today remains first");
  preferences.move("campaigns", -1);
  assert.deepEqual(Array.from(preferences.get().order).slice(0, 4), ["today", "mail_follow_up", "campaigns", "missing_info"]);
  await window.KOLConnectPages.navigate("products");
  responses.push(dashboardResponse(30));
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(v2ModuleContainer.children.find(node => node.dataset.dashboardV2Module === "missing_info").hidden, true, "hidden optional section stays absent after Settings -> Dashboard navigation");
  assert.deepEqual(
    Array.from(v2ModuleContainer.children).map(node => node.dataset.dashboardV2Module).slice(0, 4),
    ["today", "mail_follow_up", "campaigns", "missing_info"],
    "Dashboard reapplies the persisted V2 order when it becomes active",
  );
  preferences.setVisible("missing_info", true);
  await window.KOLConnectPages.navigate("products");
  const reenabledDashboard = dashboardResponse(30);
  reenabledDashboard.action_items.incomplete_cooperations = [{
    cooperation_id: "relation_one",
    creator_id: "creator_one",
    creator_name: "Maria",
    platform: "TikTok",
    campaign: "Campaign One",
    campaign_id: "campaign_one",
  }];
  responses.push(reenabledDashboard);
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(v2ModuleContainer.children.find(node => node.dataset.dashboardV2Module === "missing_info").hidden, false, "re-enabled optional section returns without an application reload");
  preferences.reset();
  assert.deepEqual(Array.from(preferences.get().order), v2Modules);
  window.localStorage.setItem("kolconnect-dashboard-layout-v2", "{not-json");
  assert.deepEqual(Array.from(preferences.get().order), v2Modules, "malformed V2 settings must safely fall back");

  const creatorButton = elements.get("dashboard-rising-creators").children[0];
  await sections[0].dispatch("click", { target: creatorButton });
  assert.equal(navigations.length, 5);
  assert.equal(navigations[4].pageName, "creator-library-detail");
  assert.equal(navigations[4].params.creatorId, "creator_one");

  const reviewButton = elements.get("dashboard-incomplete-cooperations").children[0];
  await sections[0].dispatch("click", { target: reviewButton });
  assert.equal(navigations.length, 6);
  assert.equal(navigations[5].pageName, "campaign-detail");
  assert.equal(navigations[5].params.campaignId, "campaign_one");

  await window.KOLConnectPages.navigate("products");
  assert.equal(chartCalls.filter(chart => chart.destroyed).length, 15, "each Dashboard exit must clean up its own chart set");
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 0);
  assert.equal(sections[0].listenerCount("click"), 0);
  responses.push(dashboardResponse(31));
  await window.KOLConnectPages.navigate("dashboard");
  assert.equal(elements.get("dashboard-refresh").listenerCount("click"), 1);
  assert.equal(sections[0].listenerCount("click"), 1);
  assert.equal(elements.get("dashboard-total-creators").textContent, "31");
  assert.equal(elements.get("dashboard-v2-today-list").children.length, 1);
  assert.equal(elements.get("dashboard-v2-today-list").children[0].textContent, "暂无需要处理的事项。");

  const legacyDashboard = dashboardResponse(31);
  delete legacyDashboard.action_center;
  legacyDashboard.action_items.pending_contact = [{ creator_id: "legacy", creator_name: "Legacy contact" }];
  responses.push(legacyDashboard);
  await elements.get("dashboard-refresh").dispatch("click");
  assert.equal(elements.get("dashboard-v2-today-list").children[0].textContent, "暂无需要处理的事项。", "missing Action Center must not fall back to legacy items");

  const emptyCharts = dashboardResponse(32);
  emptyCharts.platform_distribution = [];
  emptyCharts.creator_status_distribution = [];
  emptyCharts.creator_growth_trend = [];
  responses.push(emptyCharts);
  await elements.get("dashboard-refresh").dispatch("click");
  assert.equal(elements.get("dashboard-platform-chart-empty").hidden, false);
  assert.equal(elements.get("dashboard-status-chart-empty").hidden, false);
  assert.equal(elements.get("dashboard-growth-chart-empty").hidden, false);
  assert.equal(elements.get("dashboard-total-creators").textContent, "32");

  mailFollowUpResponses.push({ groups: [{ creator_id: "hidden_creator", creator_name: "已停止", correspondent_email: "stopped@example.com", waiting_for: "me", actionability: "stopped" }] });
  await elements.get("dashboard-refresh").dispatch("click");
  assert.equal(elements.get("dashboard-v2-mail-actionable-total").textContent, "0");
  assert.equal(elements.get("dashboard-v2-mail-followup-list").children.length, 0, "stopped and snoozed groups are not actionable Dashboard items");
  assert.equal(elements.get("dashboard-v2-mail-followup-empty").hidden, false);

  mailFollowUpResponses.push(Promise.reject(new Error("mail follow-up unavailable")));
  await elements.get("dashboard-refresh").dispatch("click");
  assert.equal(elements.get("dashboard-v2-mail-followup-error").hidden, false, "Mail Follow-up failure must degrade without breaking Dashboard");
  assert.equal(elements.get("dashboard-v2-mail-actionable-total").textContent, "--");

  const stale = deferred();
  responses.push(stale.promise);
  const callsBeforeStaleRefresh = calls.length;
  const refreshPromise = elements.get("dashboard-refresh").dispatch("click");
  await Promise.resolve();
  const staleCall = calls.slice(callsBeforeStaleRefresh).find(call => call.url === "/api/dashboard");
  assert.ok(staleCall, "refresh should make a Dashboard request");
  await window.KOLConnectPages.navigate("products");
  assert.equal(staleCall.signal.aborted, true, "leaving Dashboard must abort its active request");
  stale.resolve(dashboardResponse(999));
  await refreshPromise;
  assert.equal(elements.get("dashboard-total-creators").textContent, "12", "stale responses must not update Dashboard DOM");
  assert.equal(errors.length, 0);

  const appSource = read("webapp/app.js");
  assert.doesNotMatch(appSource, /function\s+loadDashboard\s*\(/);
  assert.doesNotMatch(appSource, /function\s+renderDashboard\s*\(/);
  assert.doesNotMatch(appSource, /dashboard-refresh[^\n]*addEventListener/);
  assert.doesNotMatch(appSource, /dashboard:\s*\(\)\s*=>\s*loadDashboard/);

  const html = read("webapp/index.html");
  assert.match(html, /src="vendor\/chart\.umd\.min\.js"/);
  assert.doesNotMatch(html, /https?:\/\/.*chart/i);
  assert.match(html, /id="dashboard-platform-chart"/);
  assert.match(html, /id="dashboard-status-chart"/);
  assert.match(html, /id="dashboard-growth-chart"/);
  assert.match(html, /src="pages\/dashboard\.js"/);
  assert.match(html, /id="dashboard-v2-modules"/);
  assert.match(html, /id="dashboard-v2-drawer"/);
  assert.match(html, /data-dashboard-v2-open="missing-email"/);
  assert.match(html, /data-dashboard-v2-module="mail_follow_up"/);
  assert.match(html, /data-dashboard-v2-module="today" aria-label="下一步"/);
  assert.match(html, /data-i18n="dashboardModuleToday">下一步</);
  assert.match(html, /data-dashboard-v2-open="mail-follow-up"/);
  assert.doesNotMatch(read("webapp/pages/dashboard.js"), /account_uid/);
  const styles = read("webapp/styles.css");
  assert.match(styles, /\.dashboard-v2-grid \{ display: grid; grid-template-columns: minmax\(0, 1\.2fr\) minmax\(320px, \.8fr\)/);
  assert.match(styles, /\.dashboard-v2-module\.dashboard-v2-wide \{ grid-column: 1 \/ -1; \}/);
  assert.match(styles, /\.dashboard-v2-grid \{ grid-template-columns: 1fr; \}/);
  assert.match(html, />活跃 Campaign</);
  assert.match(html, />待复盘</);
  assert.doesNotMatch(html, />合作数量</);
  assert.doesNotMatch(html, />合作记录缺失</);
  console.log("Phase 3.15 Dashboard page migration: OK");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
