(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports && typeof window === "undefined") module.exports = api;
  else root.KOLConnectTikTokSession = api;
})(globalThis, function () {
  "use strict";
  const ranks = { L1: 3, L2: 2, L3: 1 };
  const fields = ["views", "likes", "comments", "shares", "published_at"];
  function createSession(profile, clock = () => Date.now()) {
    const sessionKey = globalThis.crypto.randomUUID();
    let rows = new Map(), stopped = "", generation = 0, cutoff = 0;
    // Counts are row observations, including duplicates; current_rows is deduped.
    const counts = { accepted_rows: 0, rejected_rows: 0, l1_accepted_rows: 0, l1_rejected_rows: 0 };
    const reasons = { stopped: 0, profile_missing: 0, profile_mismatch: 0,
      timestamp: 0, layer: 0, invalid_id: 0, author_mismatch: 0, capacity: 0, batch_limit: 0 };
    const l1Reasons = { ...reasons };
    const reject = (reason, count, layer) => {
      counts.rejected_rows += count; reasons[reason] += count;
      if (layer === "L1") { counts.l1_rejected_rows += count; l1Reasons[reason] += count; }
    };
    const identity = () => `${sessionKey}:${profile}:${generation}`;
    function reset(nextProfile = profile) {
      profile = nextProfile;
      rows.clear(); stopped = ""; generation += 1; cutoff = clock();
    }
    return Object.freeze({
      reset,
      stop(reason = "CAPTURE_BLOCKED") { stopped = reason; rows.clear(); },
      add(items, context) {
        if (stopped) { reject("stopped", items.length, context.layer); return; }
        if (!profile) { reject("profile_missing", items.length, context.layer); return; }
        if (context.profile.toLowerCase() !== profile.toLowerCase()) { reject("profile_mismatch", items.length, context.layer); return; }
        const observed = Date.parse(context.observedAt);
        if (!Number.isFinite(observed) || observed <= cutoff) { reject("timestamp", items.length, context.layer); return; }
        if (!ranks[context.layer]) { reject("layer", items.length, context.layer); return; }
        if (items.length > 200) reject("batch_limit", items.length - 200, context.layer);
        for (const raw of items.slice(0, 200)) {
          if (!/^\d{1,32}$/.test(raw.video_id || "")) { reject("invalid_id", 1, context.layer); continue; }
          if (raw.author_username && raw.author_username.toLowerCase() !== profile.toLowerCase()) { reject("author_mismatch", 1, context.layer); continue; }
          let row = rows.get(raw.video_id);
          if (!row) {
            if (rows.size >= 200) { reject("capacity", 1, context.layer); continue; }
            row = { platform: "TikTok", content_type: "video", video_id: raw.video_id,
              video_url: `https://www.tiktok.com/@${profile}/video/${raw.video_id}`,
              title: null, is_pinned: null, capture_layer: context.layer,
              observed_at: context.observedAt, field_provenance: {}, _ranks: {}, _times: {} };
            rows.set(raw.video_id, row);
          }
          for (const key of [...fields, "title", "is_pinned"]) {
            const incoming = raw[key];
            const value = fields.includes(key) ? incoming?.value : incoming;
            if (value == null || value === "") {
              if (fields.includes(key) && !row[key]) row[key] = { value: null, source: "", confidence: "missing", missing_reason: "field_absent" };
              continue;
            }
            const rank = ranks[context.layer];
            if (rank < (row._ranks[key] || 0) || (rank === row._ranks[key] && observed < row._times[key])) continue;
            row[key] = fields.includes(key) ? { ...incoming, observed_at: context.observedAt } : value;
            row._ranks[key] = rank; row._times[key] = observed;
            row.field_provenance[key] = { layer: context.layer,
              source: fields.includes(key) ? incoming.source : context.layer === "L1" ? "tiktok_item_list_api" : context.layer === "L2" ? "hydration" : "dom",
              confidence: fields.includes(key) ? incoming.confidence : { L1: "high", L2: "medium", L3: "low" }[context.layer],
              observed_at: context.observedAt };
          }
          if (ranks[context.layer] > ranks[row.capture_layer]) row.capture_layer = context.layer;
          if (observed > Date.parse(row.observed_at)) row.observed_at = context.observedAt;
          counts.accepted_rows += 1;
          if (context.layer === "L1") counts.l1_accepted_rows += 1;
        }
      },
      diagnostics: () => ({ ...counts, rejected_reasons: { ...reasons },
        l1_rejected_reasons: { ...l1Reasons }, current_rows: rows.size,
        current_l1_rows: Array.from(rows.values()).filter(row => row.capture_layer === "L1").length,
        generation, stopped: Boolean(stopped) }),
      snapshot() {
        return JSON.parse(JSON.stringify({ profile, session_id: identity(), stopped,
          items: Array.from(rows.values(), ({ _ranks, _times, ...row }) => row) }));
      },
    });
  }
  return Object.freeze({ createSession });
});
