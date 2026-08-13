(function initializeTikTokNetworkParser(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.KOLConnectTikTokNetwork = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createTikTokNetworkParser() {
  "use strict";

  const ENDPOINT_KIND = "tiktok_item_list";
  const SOURCE = "tiktok_item_list_api";
  const CONFIDENCE = "high";
  const METRICS = Object.freeze({
    views: "playCount",
    likes: "diggCount",
    comments: "commentCount",
    shares: "shareCount",
  });

  function missingField(reason) {
    return {
      value: null,
      source: "",
      confidence: "missing",
      missing_reason: reason,
      source_path: "",
    };
  }

  function presentField(value, sourcePath, extra = {}) {
    return {
      value,
      source: SOURCE,
      confidence: CONFIDENCE,
      missing_reason: "",
      source_path: sourcePath,
      ...extra,
    };
  }

  function validInteger(value) {
    return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
  }

  function strictDecimalInteger(value) {
    if (typeof value !== "string" || !/^(?:0|[1-9]\d*)$/.test(value)) return null;
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) ? parsed : null;
  }

  function metricField(item, fieldName) {
    const primary = item?.stats;
    const fallback = item?.statsV2;
    const primaryPresent = primary && Object.prototype.hasOwnProperty.call(primary, fieldName);
    const fallbackPresent = fallback && Object.prototype.hasOwnProperty.call(fallback, fieldName);

    if (primaryPresent && validInteger(primary[fieldName])) {
      return presentField(primary[fieldName], `stats.${fieldName}`);
    }
    if (fallbackPresent) {
      const parsed = strictDecimalInteger(fallback[fieldName]);
      if (parsed !== null) return presentField(parsed, `statsV2.${fieldName}`);
    }
    return missingField(primaryPresent || fallbackPresent ? "invalid_value" : "field_absent");
  }

  function titleField(item) {
    if (!Object.prototype.hasOwnProperty.call(item, "desc")) return missingField("field_absent");
    if (typeof item.desc !== "string") return missingField("invalid_value");
    const value = item.desc.trim();
    return value ? presentField(value, "desc") : missingField("empty_value");
  }

  function publishedField(item) {
    if (!Object.prototype.hasOwnProperty.call(item, "createTime")) {
      return { ...missingField("field_absent"), raw_text: "", is_estimated: false };
    }
    let seconds = null;
    if (validInteger(item.createTime)) {
      seconds = item.createTime;
    } else {
      seconds = strictDecimalInteger(item.createTime);
    }
    const date = seconds === null ? null : new Date(seconds * 1000);
    if (!date || Number.isNaN(date.getTime())) {
      return { ...missingField("invalid_value"), raw_text: "", is_estimated: false };
    }
    return presentField(date.toISOString(), "createTime", {
      raw_text: String(item.createTime),
      is_estimated: false,
    });
  }

  function parseItem(item) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return null;
    if (typeof item.id !== "string" || !/^\d+$/.test(item.id) || !item.id) return null;

    const title = titleField(item);
    return {
      platform: "TikTok",
      content_type: "video",
      video_id: item.id,
      video_id_provenance: {
        source: SOURCE,
        confidence: CONFIDENCE,
        source_path: "id",
      },
      title: title.value,
      title_provenance: {
        source: title.source,
        confidence: title.confidence,
        missing_reason: title.missing_reason,
        source_path: title.source_path,
      },
      views: metricField(item, METRICS.views),
      likes: metricField(item, METRICS.likes),
      comments: metricField(item, METRICS.comments),
      shares: metricField(item, METRICS.shares),
      published_at: publishedField(item),
      is_pinned: null,
    };
  }

  function fillMissing(existing, incoming) {
    for (const fieldName of ["views", "likes", "comments", "shares", "published_at"]) {
      if (existing[fieldName].value === null && incoming[fieldName].value !== null) {
        existing[fieldName] = incoming[fieldName];
      }
    }
    if (existing.title === null && incoming.title !== null) {
      existing.title = incoming.title;
      existing.title_provenance = incoming.title_provenance;
    }
    return existing;
  }

  function invalidResult(reason) {
    return {
      endpoint_kind: ENDPOINT_KIND,
      items: [],
      metadata: { cursor: null, has_more: null },
      diagnostic: {
        status: "invalid_payload",
        reason,
        input_count: 0,
        parsed_count: 0,
        rejected_count: 0,
        duplicate_count: 0,
      },
    };
  }

  function parseTikTokItemListResponse(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return invalidResult("payload_not_object");
    }
    if (!Array.isArray(payload.itemList)) return invalidResult("item_list_not_array");

    const itemsById = new Map();
    let rejectedCount = 0;
    let duplicateCount = 0;
    for (const rawItem of payload.itemList) {
      const item = parseItem(rawItem);
      if (!item) {
        rejectedCount += 1;
        continue;
      }
      const existing = itemsById.get(item.video_id);
      if (existing) {
        duplicateCount += 1;
        fillMissing(existing, item);
      } else {
        itemsById.set(item.video_id, item);
      }
    }

    return {
      endpoint_kind: ENDPOINT_KIND,
      items: Array.from(itemsById.values()),
      metadata: {
        cursor: typeof payload.cursor === "string" ? payload.cursor : null,
        has_more: typeof payload.hasMore === "boolean" ? payload.hasMore : null,
      },
      diagnostic: {
        status: "success",
        reason: "",
        input_count: payload.itemList.length,
        parsed_count: itemsById.size,
        rejected_count: rejectedCount,
        duplicate_count: duplicateCount,
      },
    };
  }

  return Object.freeze({
    ENDPOINT_KIND,
    SOURCE,
    parseTikTokItemListResponse,
  });
});
