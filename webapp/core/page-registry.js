(function createPageRegistry(global) {
  "use strict";

  const pages = new Map();
  let currentPage = null;
  let navigationId = 0;

  function validateLifecycle(name, page) {
    ["load", "bind", "unbind"].forEach(method => {
      if (typeof page?.[method] !== "function") {
        throw new TypeError(`Page "${name}" must define ${method}(context).`);
      }
    });
  }

  function registerPage(name, page) {
    const normalizedName = String(name || "").trim();
    if (!normalizedName) throw new TypeError("Page name is required.");
    validateLifecycle(normalizedName, page);
    if (pages.has(normalizedName)) {
      throw new Error(`Page "${normalizedName}" is already registered.`);
    }
    pages.set(normalizedName, page);
    return page;
  }

  function getPage(name) {
    return pages.get(String(name || "")) || null;
  }

  function activateSection(pageName) {
    const pageButton = document.querySelector(`.nav-btn[data-page="${pageName}"]`);
    const primaryName = pageButton?.dataset.primary || pageName;
    document.querySelectorAll(".nav-btn").forEach(button => {
      const isPrimary = button.classList.contains("nav-primary");
      button.classList.toggle(
        "active",
        isPrimary ? button.dataset.primary === primaryName : button.dataset.page === pageName,
      );
    });
    document.querySelectorAll(".page").forEach(section => {
      section.classList.toggle("active", section.dataset.page === pageName);
    });
  }

  async function navigate(name, context = {}) {
    const pageName = String(name || "").trim();
    const nextPage = getPage(pageName);
    if (!nextPage) throw new Error(`Page "${pageName}" is not registered.`);

    const thisNavigation = ++navigationId;
    const previousPage = currentPage;
    if (previousPage) await previousPage.page.unbind(previousPage.context);
    if (thisNavigation !== navigationId) return null;

    activateSection(pageName);
    const pageContext = { ...context, pageName, navigationId: thisNavigation };
    currentPage = { name: pageName, page: nextPage, context: pageContext };

    let loadError = null;
    try {
      await nextPage.load(pageContext);
    } catch (error) {
      loadError = error;
    }
    if (thisNavigation !== navigationId || currentPage?.name !== pageName) return null;

    await nextPage.bind({ ...pageContext, loadError });
    if (loadError) throw loadError;
    return pageContext;
  }

  global.KOLConnectPages = Object.freeze({
    registerPage,
    getPage,
    navigate,
    getCurrentPage() {
      return currentPage?.name || null;
    },
  });
})(window);
