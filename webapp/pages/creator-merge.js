(function createCreatorMergeModal(global) {
  "use strict";

  function create(context) {
    let primary = null;
    let secondary = null;
    let preview = null;
    let onMerged = null;
    let searchRequest = 0;
    let submitting = false;
    const target = id => document.getElementById(id);
    const setText = (id, value) => {
      const node = target(id);
      if (node) node.textContent = String(value ?? "--");
    };
    const accountLabel = value => {
      const accounts = Array.isArray(value?.accounts) ? value.accounts : [];
      return accounts.length
        ? accounts.map(item => `${item.platform || "账号"}${item.username ? ` · ${item.username}` : ""}`).join("；")
        : (Array.isArray(value?.platforms) && value.platforms.length ? value.platforms.join(" / ") : "暂无账号");
    };
    function setMessage(value, status = "") {
      const node = target("creator-merge-message");
      if (!node) return;
      node.hidden = !value;
      node.textContent = value || "";
      node.dataset.status = status;
    }
    function setButtons() {
      const previewButton = target("creator-merge-preview");
      const confirmButton = target("creator-merge-confirm");
      if (previewButton) previewButton.disabled = !primary || !secondary || submitting;
      if (confirmButton) confirmButton.disabled = !preview?.safe_to_merge || submitting;
    }
    function clearPreview() {
      preview = null;
      ["accounts", "videos", "snapshots", "campaigns"].forEach(key => {
        setText(`creator-merge-count-${key}`, "--");
      });
      ["creators", "accounts", "platforms"].forEach(key => {
        setText(`creator-merge-result-${key}`, "--");
      });
      const conflicts = target("creator-merge-conflicts");
      conflicts?.replaceChildren();
      if (conflicts) conflicts.hidden = true;
      setButtons();
    }
    function renderSelection() {
      setText("creator-merge-primary-name", primary?.creator_name || primary?.display_name || "--");
      setText("creator-merge-primary-accounts", accountLabel(primary));
      setText("creator-merge-secondary-name", secondary?.creator_name || secondary?.display_name || "尚未选择");
      setText("creator-merge-secondary-accounts", accountLabel(secondary));
      clearPreview();
    }
    function renderPreview(data) {
      preview = data;
      const summary = data?.migration_summary || {};
      setText("creator-merge-count-accounts", summary.accounts || 0);
      setText("creator-merge-count-videos", summary.videos || 0);
      setText("creator-merge-count-snapshots", Number(summary.creator_snapshots || 0) + Number(summary.video_snapshots || 0));
      setText("creator-merge-count-campaigns", summary.campaign_creators || 0);
      const primaryCount = Number(data?.primary?.account_count || 0);
      const secondaryCount = Number(data?.secondary?.account_count || 0);
      const accountTotal = primaryCount + secondaryCount;
      setText("creator-merge-result-creators", "2 → 1");
      setText("creator-merge-result-accounts", `${accountTotal} → ${accountTotal}`);
      setText("creator-merge-result-platforms", accountLabel({
        accounts: [...(data?.primary?.accounts || []), ...(data?.secondary?.accounts || [])],
      }));
      setText("creator-merge-primary-accounts", accountLabel(data?.primary));
      setText("creator-merge-secondary-accounts", accountLabel(data?.secondary));
      const conflicts = target("creator-merge-conflicts");
      conflicts.replaceChildren();
      (data?.conflicts || []).forEach(item => {
        const row = document.createElement("li");
        row.textContent = `${item.code || "MERGE_BLOCKED"}${item.source ? ` · ${item.source}` : ""}`;
        conflicts.appendChild(row);
      });
      conflicts.hidden = !(data?.conflicts || []).length;
      setMessage(
        data?.safe_to_merge ? "预览已通过，可继续明确确认。" : "当前合并存在安全冲突，未修改任何数据。",
        data?.safe_to_merge ? "success" : "warning",
      );
      setButtons();
    }
    async function search() {
      const query = String(target("creator-merge-search")?.value || "").trim();
      const results = target("creator-merge-search-results");
      results.replaceChildren();
      if (!query || !primary) return;
      const current = ++searchRequest;
      const data = await context.api.get(
        `/api/creator-library?page=1&page_size=100&search=${encodeURIComponent(query)}&include_archived=true`,
        { signal: context.resources.signal },
      );
      if (current !== searchRequest) return;
      (data.creators || data.records || [])
        .filter(item => String(item.creator_id || item.analysis_id || "") !== String(primary.creator_id || ""))
        .forEach(item => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "creator-merge-search-result";
          const identity = document.createElement("span");
          const name = document.createElement("strong");
          const detail = document.createElement("span");
          name.textContent = item.creator_name || "未命名达人";
          detail.textContent = [item.platform, item.profile_url, item.followers ? `粉丝 ${item.followers}` : ""].filter(Boolean).join(" · ");
          identity.append(name, detail);
          const choose = document.createElement("b");
          choose.textContent = "选择";
          button.append(identity, choose);
          context.resources.listen(button, "click", async () => {
            const detailData = await context.api.get(
              `/api/creator-library/${encodeURIComponent(item.creator_id || item.analysis_id)}`,
              { signal: context.resources.signal },
            );
            secondary = {
              ...item,
              ...detailData.record,
              creator_name: detailData.record?.creator_name || item.creator_name,
              accounts: detailData.accounts || [],
            };
            results.replaceChildren();
            renderSelection();
          });
          results.appendChild(button);
        });
    }
    async function runPreview() {
      if (!primary || !secondary || submitting) return;
      submitting = true;
      clearPreview();
      setMessage("正在重新读取所有关联数据...", "loading");
      setButtons();
      try {
        renderPreview(await context.api.post(
          "/api/creator-library/merge/preview",
          { primary_creator_id: primary.creator_id, secondary_creator_id: secondary.creator_id },
          { signal: context.resources.signal },
        ));
      } finally {
        submitting = false;
        setButtons();
      }
    }
    async function execute() {
      if (!preview?.safe_to_merge || !primary || !secondary || submitting) return;
      const primaryName = primary.creator_name || primary.display_name || primary.creator_id;
      const secondaryName = secondary.creator_name || secondary.display_name || secondary.creator_id;
      if (!global.confirm(
        `确认将【${secondaryName}】合并到【${primaryName}】？\n\n`
        + "SECONDARY Creator 将被删除，但其账号和历史记录会迁移到 PRIMARY。",
      )) return;
      submitting = true;
      setButtons();
      try {
        const data = await context.api.post(
          "/api/creator-library/merge/execute",
          {
            primary_creator_id: primary.creator_id,
            secondary_creator_id: secondary.creator_id,
            confirm: true,
            preview_fingerprint: preview.preview_fingerprint,
          },
          { signal: context.resources.signal },
        );
        const callback = onMerged;
        close();
        if (callback) await callback(data);
        context.ui.showSaved(
          `达人合并完成。已将 ${data?.migrated?.CreatorAccounts || 0} 个账号和相关历史记录迁移到【${primaryName}】。如使用飞书同步，请先运行 Dry Run。`,
        );
      } catch (error) {
        preview = null;
        setMessage(error?.responseData?.error || "MERGE_FAILED", "error");
      } finally {
        submitting = false;
        setButtons();
      }
    }
    async function open(record, options = {}) {
      close();
      const creatorId = String(record?.creator_id || record?.analysis_id || "");
      const detail = await context.api.get(
        `/api/creator-library/${encodeURIComponent(creatorId)}`,
        { signal: context.resources.signal },
      );
      primary = { ...record, ...detail.record, creator_id: creatorId, accounts: detail.accounts || [] };
      onMerged = typeof options.onMerged === "function" ? options.onMerged : null;
      target("creator-merge-modal").hidden = false;
      renderSelection();
      target("creator-merge-search")?.focus();
    }
    function close() {
      primary = null;
      secondary = null;
      preview = null;
      onMerged = null;
      submitting = false;
      searchRequest += 1;
      const modal = target("creator-merge-modal");
      if (modal) modal.hidden = true;
      target("creator-merge-search-results")?.replaceChildren();
      if (target("creator-merge-search")) target("creator-merge-search").value = "";
      setMessage("");
      clearPreview();
    }
    function bind() {
      context.resources.listen(target("creator-merge-close"), "click", close);
      context.resources.listen(target("creator-merge-cancel"), "click", close);
      context.resources.listen(target("creator-merge-preview"), "click", () => runPreview().catch(context.ui.showError));
      context.resources.listen(target("creator-merge-confirm"), "click", () => execute().catch(context.ui.showError));
      context.resources.listen(target("creator-merge-search"), "input", () => {
        context.resources.setTimeout(() => search().catch(context.ui.showError), 200);
      });
    }
    function destroy() {
      close();
    }
    return Object.freeze({ open, bind, close, destroy });
  }

  global.KOLConnectCreatorMergeModal = Object.freeze({ create });
})(window);
