(function registerAgencyPages(global) {
  "use strict";

  let listResources = null;
  let listController = null;
  let detailResources = null;
  let detailController = null;
  let agencies = [];
  let activeAgencyId = "";
  let listLifecycle = 0;
  let detailLifecycle = 0;

  function element(id) {
    return document.getElementById(id);
  }

  function app() {
    if (!global.KOLConnectApp) throw new Error("KOLConnect application helpers are unavailable.");
    return global.KOLConnectApp;
  }

  function text(value, fallback = "--") {
    const normalized = String(value ?? "").trim();
    return normalized || fallback;
  }

  function count(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;
  }

  function formatDate(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }

  function createCell(value, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = value;
    return cell;
  }

  function createLink(label, dataset) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mini-btn";
    Object.assign(button.dataset, dataset);
    button.textContent = label;
    return button;
  }

  function setListState(state, message = "") {
    element("agency-list-loading").hidden = state !== "loading";
    element("agency-list-error").hidden = state !== "error";
    element("agency-list-error").style.display = state === "error" ? "" : "none";
    element("agency-list-error-message").textContent = message;
    element("agency-list-empty").hidden = state !== "empty";
    element("agency-list-table-wrap").hidden = state !== "loaded";
  }

  function renderAgencyList() {
    const body = element("agency-list-body");
    body.replaceChildren();
    const creatorTotal = agencies.reduce((total, agency) => total + count(agency.creator_count), 0);
    const contactTotal = agencies.reduce((total, agency) => total + count(agency.contact_count), 0);
    element("agency-overview-total").textContent = String(agencies.length);
    element("agency-overview-creators").textContent = String(creatorTotal);
    element("agency-overview-contacts").textContent = String(contactTotal);
    element("agency-list-count").textContent = `${agencies.length} 个 Agency`;

    if (!agencies.length) {
      setListState("empty");
      return;
    }

    agencies.forEach(agency => {
      const row = document.createElement("tr");
      const agencyId = String(agency.agency_id || "");
      row.dataset.agencyId = agencyId;
      row.appendChild(createCell(text(agency.name), "agency-name-cell"));
      row.appendChild(createCell(text(agency.country)));
      row.appendChild(createCell(`${count(agency.contact_count)} 位联系人`));
      row.appendChild(createCell(`${count(agency.creator_count)} 位达人`));
      row.appendChild(createCell(formatDate(agency.updated_at || agency.created_at)));
      const action = document.createElement("td");
      action.appendChild(createLink("查看", { agencyDetailId: agencyId }));
      row.appendChild(action);
      body.appendChild(row);
    });
    setListState("loaded");
  }

  async function loadAgencies() {
    if (!listResources) return;
    const lifecycle = listLifecycle;
    listController?.abort();
    listController = listResources.createAbortController();
    setListState("loading");
    try {
      const data = await global.KOLConnectAPI.get("/api/local/agencies", {
        signal: listController.signal,
      });
      if (!listResources || lifecycle !== listLifecycle) return;
      if (!Array.isArray(data.agencies)) throw new Error("Agency 列表响应格式异常。");
      agencies = data.agencies;
      renderAgencyList();
    } catch (error) {
      if (error?.name === "AbortError" || lifecycle !== listLifecycle) return;
      agencies = [];
      element("agency-overview-total").textContent = "--";
      element("agency-overview-creators").textContent = "--";
      element("agency-overview-contacts").textContent = "--";
      element("agency-list-count").textContent = "0 个 Agency";
      setListState("error", error.message || "Agency 列表加载失败，请稍后重试。");
    }
  }

  function setDetailState(state, message = "") {
    element("agency-detail-loading").hidden = state !== "loading";
    element("agency-detail-error").hidden = state !== "error";
    element("agency-detail-error").style.display = state === "error" ? "" : "none";
    element("agency-detail-error-message").textContent = message;
    element("agency-detail-content").hidden = state !== "loaded";
  }

  function setField(id, value) {
    element(id).textContent = text(value);
  }

  function renderContacts(contacts) {
    const body = element("agency-contacts-body");
    body.replaceChildren();
    element("agency-contact-count").textContent = `${contacts.length} 位`;
    element("agency-contacts-empty").hidden = contacts.length > 0;
    element("agency-contacts-table-wrap").hidden = contacts.length === 0;
    contacts.forEach(contact => {
      const row = document.createElement("tr");
      row.appendChild(createCell(text(contact.name)));
      row.appendChild(createCell(text(contact.position)));
      row.appendChild(createCell(text(contact.email)));
      row.appendChild(createCell(text(contact.whatsapp)));
      row.appendChild(createCell(text(contact.status)));
      body.appendChild(row);
    });
  }

  function renderCreators(creators) {
    const body = element("agency-creators-body");
    body.replaceChildren();
    element("agency-creator-count").textContent = `${creators.length} 位`;
    element("agency-creators-empty").hidden = creators.length > 0;
    element("agency-creators-table-wrap").hidden = creators.length === 0;
    creators.forEach(creator => {
      const row = document.createElement("tr");
      const creatorId = String(creator.creator_id || "");
      row.appendChild(createCell(text(creator.name || creator.creator_name)));
      row.appendChild(createCell(text(creator.platform)));
      row.appendChild(createCell(text(creator.country)));
      row.appendChild(createCell(text(creator.status)));
      const action = document.createElement("td");
      action.appendChild(createLink("查看达人", { agencyCreatorId: creatorId }));
      row.appendChild(action);
      body.appendChild(row);
    });
  }

  function renderCampaigns(campaigns, unavailable) {
    const body = element("agency-campaigns-body");
    body.replaceChildren();
    element("agency-campaign-count").textContent = unavailable ? "部分不可用" : `${campaigns.length} 个`;
    element("agency-campaigns-unavailable").hidden = !unavailable;
    element("agency-campaigns-empty").hidden = unavailable || campaigns.length > 0;
    element("agency-campaigns-table-wrap").hidden = campaigns.length === 0;
    campaigns.forEach(campaign => {
      const row = document.createElement("tr");
      const campaignId = String(campaign.campaign_id || "");
      row.appendChild(createCell(text(campaign.name)));
      row.appendChild(createCell(text(campaign.product_name)));
      row.appendChild(createCell(text(campaign.status)));
      row.appendChild(createCell(String(count(campaign.creators_count))));
      const action = document.createElement("td");
      action.appendChild(createLink("查看", { agencyCampaignId: campaignId }));
      row.appendChild(action);
      body.appendChild(row);
    });
  }

  async function loadCampaignsForCreators(creators, signal) {
    const creatorIds = [...new Set(creators.map(item => String(item.creator_id || "").trim()).filter(Boolean))];
    if (!creatorIds.length) return { campaigns: [], unavailable: false };
    const results = await Promise.allSettled(creatorIds.map(creatorId =>
      global.KOLConnectAPI.get(`/api/campaigns?creator_id=${encodeURIComponent(creatorId)}`, { signal })
    ));
    const campaignsById = new Map();
    results.forEach(result => {
      if (result.status !== "fulfilled") return;
      const records = Array.isArray(result.value.campaigns) ? result.value.campaigns : [];
      records.forEach(campaign => {
        const campaignId = String(campaign.campaign_id || "");
        if (campaignId) campaignsById.set(campaignId, campaign);
      });
    });
    return {
      campaigns: [...campaignsById.values()],
      unavailable: results.some(result => result.status === "rejected"),
    };
  }

  function renderAgencyDetail(detail, contacts, campaignResult) {
    const agency = detail.agency || {};
    const creators = Array.isArray(detail.creators) ? detail.creators : [];
    element("agency-detail-title").textContent = text(agency.name, "Agency 详情");
    element("agency-detail-subtitle").textContent = agency.country
      ? `${agency.country} · 机构资料与合作关系`
      : "机构资料、联系人、达人和 Campaign 关系。";
    setField("agency-detail-name", agency.name);
    setField("agency-detail-country", agency.country);
    setField("agency-detail-website", agency.website);
    setField("agency-detail-email", agency.public_email);
    setField("agency-detail-stage", agency.cooperation_stage);
    setField("agency-detail-owner", agency.owner);
    setField("agency-detail-note", agency.note);
    renderContacts(contacts);
    renderCreators(creators);
    renderCampaigns(campaignResult.campaigns, campaignResult.unavailable);
    setDetailState("loaded");
  }

  async function loadAgencyDetail() {
    if (!detailResources || !activeAgencyId) return;
    const lifecycle = detailLifecycle;
    detailController?.abort();
    detailController = detailResources.createAbortController();
    setDetailState("loading");
    const encodedId = encodeURIComponent(activeAgencyId);
    try {
      const [detail, contactsData] = await Promise.all([
        global.KOLConnectAPI.get(`/api/local/agencies/${encodedId}`, { signal: detailController.signal }),
        global.KOLConnectAPI.get("/api/local/agency-contacts", { signal: detailController.signal }),
      ]);
      if (!detailResources || lifecycle !== detailLifecycle) return;
      if (!detail.agency || !Array.isArray(detail.creators)) throw new Error("Agency 详情响应格式异常。");
      const contacts = Array.isArray(contactsData.contacts)
        ? contactsData.contacts.filter(contact => String(contact.agency_id || "") === activeAgencyId)
        : [];
      const campaignResult = await loadCampaignsForCreators(detail.creators, detailController.signal);
      if (!detailResources || lifecycle !== detailLifecycle) return;
      renderAgencyDetail(detail, contacts, campaignResult);
    } catch (error) {
      if (error?.name === "AbortError" || lifecycle !== detailLifecycle) return;
      setDetailState("error", error.message || "Agency 详情加载失败，请返回列表重试。");
    }
  }

  function listen(resources, id, type, listener) {
    const target = element(id);
    if (target) resources.listen(target, type, listener);
  }

  const listPage = {
    async load() {
      listResources?.cleanup();
      listResources = global.KOLConnectPageResources.create();
      listLifecycle += 1;
      await loadAgencies();
    },
    bind() {
      listen(listResources, "agency-list-refresh", "click", loadAgencies);
      listen(listResources, "agency-list-retry", "click", loadAgencies);
      listen(listResources, "agency-list-body", "click", event => {
        const button = event.target.closest("[data-agency-detail-id]");
        if (button?.dataset.agencyDetailId) {
          app().navigate("agency-detail", { agencyId: button.dataset.agencyDetailId });
        }
      });
    },
    unbind() {
      listLifecycle += 1;
      listResources?.cleanup();
      listResources = null;
      listController = null;
    },
  };

  const detailPage = {
    async load(context) {
      detailResources?.cleanup();
      detailResources = global.KOLConnectPageResources.create();
      detailLifecycle += 1;
      activeAgencyId = String(context?.agencyId || "").trim();
      if (!activeAgencyId) {
        setDetailState("error", "缺少 Agency ID，请返回列表重新进入。");
        return;
      }
      await loadAgencyDetail();
    },
    bind() {
      listen(detailResources, "agency-detail-back", "click", () => app().navigate("agencies"));
      listen(detailResources, "agency-detail-retry", "click", loadAgencyDetail);
      listen(detailResources, "agency-creators-body", "click", event => {
        const button = event.target.closest("[data-agency-creator-id]");
        if (button?.dataset.agencyCreatorId) {
          app().navigate("creator-library-detail", { creatorId: button.dataset.agencyCreatorId });
        }
      });
      listen(detailResources, "agency-campaigns-body", "click", event => {
        const button = event.target.closest("[data-agency-campaign-id]");
        if (button?.dataset.agencyCampaignId) {
          app().navigate("campaign-detail", { campaignId: button.dataset.agencyCampaignId });
        }
      });
    },
    unbind() {
      detailLifecycle += 1;
      detailResources?.cleanup();
      detailResources = null;
      detailController = null;
      activeAgencyId = "";
    },
  };

  global.KOLConnectPages.registerPage("agencies", listPage);
  global.KOLConnectPages.registerPage("agency-detail", detailPage);
})(window);
