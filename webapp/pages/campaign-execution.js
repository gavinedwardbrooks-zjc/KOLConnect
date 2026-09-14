(function registerCampaignExecutionPage(global) {
  "use strict";

  const GROUPS = [
    ["today", "campaign-execution-today"],
    ["due_soon", "campaign-execution-due-soon"],
    ["overdue", "campaign-execution-overdue"],
    ["stalled", "campaign-execution-stalled"],
    ["waiting_creator", "campaign-execution-waiting-creator"],
    ["waiting_internal", "campaign-execution-waiting-internal"],
    ["need_my_decision", "campaign-execution-need-my-decision"],
  ];

  let resources = null;

  function element(id) {
    return document.getElementById(id);
  }

  function renderGroup(id, entries) {
    const target = element(id);
    if (!target) return;
    target.replaceChildren();
    if (!entries.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "暂无事项。";
      target.appendChild(empty);
      return;
    }
    entries.forEach(item => {
      const card = document.createElement("article");
      card.className = "campaign-publication-performance-card";
      const title = document.createElement("strong");
      title.textContent = `${item.campaign_name || item.campaign_id || "Campaign"} · ${item.creator_name || item.creator_id || "达人"}`;
      const detail = document.createElement("small");
      detail.textContent = `下一步：${item.next_action || "--"}；截止：${item.due_date || "--"}；负责人：${item.owner || "--"}`;
      const open = document.createElement("button");
      open.type = "button";
      open.className = "soft-btn compact-btn";
      open.textContent = "打开 Campaign";
      open.addEventListener("click", () => global.KOLConnectPages.navigate("campaign-detail", { campaignId: item.campaign_id }));
      card.append(title, detail, open);
      target.appendChild(card);
    });
  }

  function render(data) {
    GROUPS.forEach(([key, id]) => renderGroup(id, Array.isArray(data?.[key]) ? data[key] : []));
  }

  async function load() {
    const error = element("campaign-execution-error");
    if (error) error.hidden = true;
    try {
      const data = await global.KOLConnectAPI.get("/api/campaign-execution/workspace", { signal: resources.signal });
      render(data);
    } catch (requestError) {
      render({});
      if (error) {
        error.textContent = "执行看板暂时不可用，请稍后重试。";
        error.hidden = false;
      }
    }
  }

  global.KOLConnectPages.registerPage("campaign-execution", {
    async load() {
      resources?.cleanup();
      resources = global.KOLConnectPageResources.create();
      await load();
    },
    bind() {},
    unbind() {
      resources?.cleanup();
      resources = null;
    },
  });
})(window);
