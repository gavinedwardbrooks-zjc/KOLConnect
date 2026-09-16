(function registerAgencyPages(global) {
  "use strict";

  let listResources = null;
  let listController = null;
  let detailResources = null;
  let detailController = null;
  let agencies = [];
  let activeAgencyId = "";
  let activeAgency = null;
  let activeContacts = [];
  let activeCreators = [];
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
      action.appendChild(createLink("编辑", { agencyEditId: agencyId }));
      const more = document.createElement("details");
      more.className = "task-card-more";
      const summary = document.createElement("summary");
      summary.textContent = "更多";
      const moreActions = document.createElement("div");
      moreActions.className = "task-card-more-actions";
      moreActions.appendChild(createLink("删除 Agency", { agencyDeleteId: agencyId }));
      more.appendChild(summary);
      more.appendChild(moreActions);
      action.appendChild(more);
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
    activeContacts = contacts;
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
      const action = document.createElement("td");
      action.appendChild(createLink("编辑", { agencyContactEditId: String(contact.contact_id || "") }));
      action.appendChild(createLink("删除", { agencyContactDeleteId: String(contact.contact_id || "") }));
      row.appendChild(action);
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
      action.appendChild(createLink("解除关联", { agencyCreatorUnlinkId: creatorId }));
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
    activeAgency = agency;
    const creators = Array.isArray(detail.creators) ? detail.creators : [];
    activeCreators = creators;
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

  function setEditFormVisible(visible) {
    const form = element("agency-edit-form");
    if (!form) return;
    form.hidden = !visible;
    if (!visible || !activeAgency) return;
    [
      ["agency-edit-name", "name"], ["agency-edit-country", "country"],
      ["agency-edit-website", "website"], ["agency-edit-email", "public_email"],
      ["agency-edit-stage", "cooperation_stage"], ["agency-edit-owner", "owner"],
      ["agency-edit-note", "note"],
    ].forEach(([id, field]) => { element(id).value = String(activeAgency[field] || ""); });
  }

  function setContactEditFormVisible(visible, contact = null) {
    const form = element("agency-contact-edit-form");
    if (!form) return;
    form.hidden = !visible;
    if (!visible || !contact) return;
    form.dataset.contactId = String(contact.contact_id || "");
    [
      ["agency-contact-edit-name", "name"],
      ["agency-contact-edit-position", "position"],
      ["agency-contact-edit-email", "email"],
      ["agency-contact-edit-whatsapp", "whatsapp"],
    ].forEach(([id, field]) => { element(id).value = String(contact[field] || ""); });
  }

  async function saveAgencyEdit(event) {
    event.preventDefault();
    if (!activeAgencyId) return;
    const payload = {
      agency_id: activeAgencyId,
      name: element("agency-edit-name").value.trim(),
      country: element("agency-edit-country").value.trim(),
      website: element("agency-edit-website").value.trim(),
      public_email: element("agency-edit-email").value.trim(),
      cooperation_stage: element("agency-edit-stage").value.trim(),
      owner: element("agency-edit-owner").value.trim(),
      note: element("agency-edit-note").value.trim(),
    };
    try {
      await global.KOLConnectAPI.post("/api/local/agencies", payload, { signal: detailResources?.signal });
      setEditFormVisible(false);
      await loadAgencyDetail();
      app().showSaved("Agency 资料已保存。");
    } catch (error) {
      app().showError(agencyDeleteBlockerError(error));
    }
  }

  function agencyDeleteBlockerError(error) {
    const message = String(error?.message || "");
    const match = message.match(/仍关联\s*(\d+)\s*位达人和\s*(\d+)\s*位联系人/);
    if (!match) return error;
    const [creatorCount, contactCount] = match.slice(1).map(Number);
    const remaining = [
      creatorCount ? `${creatorCount} 位关联达人需要先解除关联` : "",
      contactCount ? `${contactCount} 位联系人需要先删除` : "",
    ].filter(Boolean).join("，");
    return new Error(`暂时无法删除 Agency。${remaining}。请在下方完成处理后再试。`);
  }

  async function deleteAgency() {
    if (!activeAgencyId) return;
    if (!global.confirm("删除 Agency？\n删除后无法恢复。")) return;
    try {
      await global.KOLConnectAPI.delete(`/api/local/agencies/${encodeURIComponent(activeAgencyId)}`, { signal: detailResources?.signal });
      app().showSaved("Agency 已删除。");
      app().navigate("agencies");
    } catch (error) {
      app().showError(agencyDeleteBlockerError(error));
    }
  }

  async function saveAgencyContact(event) {
    event.preventDefault();
    const form = element("agency-contact-edit-form");
    const contactId = String(form?.dataset.contactId || "").trim();
    if (!contactId || !activeAgencyId) return;
    const payload = {
      contact_id: contactId,
      agency_id: activeAgencyId,
      name: element("agency-contact-edit-name").value.trim(),
      position: element("agency-contact-edit-position").value.trim(),
      email: element("agency-contact-edit-email").value.trim(),
      whatsapp: element("agency-contact-edit-whatsapp").value.trim(),
    };
    try {
      await global.KOLConnectAPI.post("/api/local/agency-contacts", payload, { signal: detailResources?.signal });
      setContactEditFormVisible(false);
      await loadAgencyDetail();
      app().showSaved("联系人资料已保存。");
    } catch (error) {
      app().showError(error);
    }
  }

  async function deleteAgencyContact(contact) {
    if (!contact?.contact_id) return;
    const name = text(contact.name, "该联系人");
    if (!global.confirm(`确定删除联系人 ${name} 吗？\n此操作只删除该 Agency 下的联系人，不会删除达人、Campaign 或发布记录。`)) return;
    try {
      await global.KOLConnectAPI.delete(`/api/local/agency-contacts/${encodeURIComponent(contact.contact_id)}`, { signal: detailResources?.signal });
      setContactEditFormVisible(false);
      await loadAgencyDetail();
      app().showSaved("联系人已删除。");
    } catch (error) {
      app().showError(error);
    }
  }

  async function unlinkAgencyCreator(creator) {
    const creatorId = String(creator?.creator_id || "").trim();
    if (!creatorId) return;
    if (!global.confirm("确定解除该达人与此 Agency 的关联吗？\n达人资料和历史合作记录不会被删除。")) return;
    const agencyContactIds = new Set(activeContacts.map(contact => String(contact.contact_id || "")));
    const payload = { agency_id: "" };
    ["current_contact_id", "source_contact_id"].forEach(field => {
      if (agencyContactIds.has(String(creator[field] || ""))) payload[field] = "";
    });
    try {
      await global.KOLConnectAPI.post(`/api/creator-library/${encodeURIComponent(creatorId)}/relations`, payload, { signal: detailResources?.signal });
      await loadAgencyDetail();
      app().showSaved("已解除达人与 Agency 的关联。");
    } catch (error) {
      app().showError(error);
    }
  }

  async function deleteAgencyFromList(agencyId) {
    if (!agencyId || !global.confirm("删除 Agency？\n删除后无法恢复。")) return;
    try {
      await global.KOLConnectAPI.delete(`/api/local/agencies/${encodeURIComponent(agencyId)}`, { signal: listResources?.signal });
      app().showSaved("Agency 已删除。");
      await loadAgencies();
    } catch (error) {
      app().showError(agencyDeleteBlockerError(error));
    }
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
        const deleteButton = event.target.closest("[data-agency-delete-id]");
        if (deleteButton?.dataset.agencyDeleteId) return deleteAgencyFromList(deleteButton.dataset.agencyDeleteId);
        const editButton = event.target.closest("[data-agency-edit-id]");
        if (editButton?.dataset.agencyEditId) return app().navigate("agency-detail", { agencyId: editButton.dataset.agencyEditId });
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
      listen(detailResources, "agency-detail-edit", "click", () => setEditFormVisible(true));
      listen(detailResources, "agency-edit-cancel", "click", () => setEditFormVisible(false));
      listen(detailResources, "agency-edit-form", "submit", saveAgencyEdit);
      listen(detailResources, "agency-detail-delete", "click", deleteAgency);
      listen(detailResources, "agency-contact-edit-cancel", "click", () => setContactEditFormVisible(false));
      listen(detailResources, "agency-contact-edit-form", "submit", saveAgencyContact);
      listen(detailResources, "agency-contacts-body", "click", event => {
        const contactId = event.target.closest("[data-agency-contact-edit-id]")?.dataset.agencyContactEditId
          || event.target.closest("[data-agency-contact-delete-id]")?.dataset.agencyContactDeleteId;
        const contact = activeContacts.find(item => String(item.contact_id || "") === String(contactId || ""));
        if (!contact) return;
        if (event.target.closest("[data-agency-contact-delete-id]")) return deleteAgencyContact(contact);
        setContactEditFormVisible(true, contact);
      });
      listen(detailResources, "agency-creators-body", "click", event => {
        const unlinkButton = event.target.closest("[data-agency-creator-unlink-id]");
        if (unlinkButton?.dataset.agencyCreatorUnlinkId) {
          const creator = activeCreators.find(item => String(item.creator_id || "") === unlinkButton.dataset.agencyCreatorUnlinkId);
          return unlinkAgencyCreator(creator);
        }
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
      activeAgency = null;
      activeContacts = [];
      activeCreators = [];
    },
  };

  global.KOLConnectPages.registerPage("agencies", listPage);
  global.KOLConnectPages.registerPage("agency-detail", detailPage);
})(window);
