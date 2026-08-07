import { normalizeText, parseHumanCount } from "./normalize.js";

export const CONTENT_ANALYSIS_TIMEOUT_MS = 90000;
export const CONTENT_DETAIL_CONCURRENCY = 2;
export const CONTENT_DETAIL_DELAY_MS = 900;

export function metric(value, source = "", confidence = "missing", missingReason = "") {
  const parsed = parseHumanCount(value);
  return {
    value: parsed,
    source: parsed == null ? "" : normalizeText(source),
    confidence: parsed == null ? "missing" : confidence,
    missing_reason: parsed == null ? normalizeText(missingReason) : ""
  };
}

export function publishedAt(value, rawText = "", source = "", confidence = "missing", missingReason = "", estimated = false) {
  let normalized = null;
  if (value != null && value !== "") {
    const numeric = Number(value);
    const date = Number.isFinite(numeric)
      ? new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric)
      : new Date(value);
    if (!Number.isNaN(date.getTime())) normalized = date.toISOString();
  }
  return {
    value: normalized,
    raw_text: normalizeText(rawText || value),
    is_estimated: Boolean(normalized && estimated),
    source: normalized ? normalizeText(source) : "",
    confidence: normalized ? confidence : "missing",
    missing_reason: normalized ? "" : normalizeText(missingReason)
  };
}

export function parsePublishedText(rawText, now = new Date()) {
  const raw = normalizeText(rawText);
  if (!raw) return { value: null, is_estimated: false };
  const exact = new Date(raw);
  if (!Number.isNaN(exact.getTime()) && !/ago|há|hace|前$/i.test(raw)) {
    return { value: exact.toISOString(), is_estimated: false };
  }
  const patterns = [
    { regex: /(\d+)\s*(seconds?|segundos?|秒)\s*(?:ago|atrás|前)?/i, ms: 1000 },
    { regex: /(\d+)\s*(minutes?|minutos?|分钟)\s*(?:ago|atrás|前)?/i, ms: 60_000 },
    { regex: /(\d+)\s*(hours?|horas?|小时)\s*(?:ago|atrás|前)?/i, ms: 3_600_000 },
    { regex: /(\d+)\s*(days?|dias?|天)\s*(?:ago|atrás|前)?/i, ms: 86_400_000 },
    { regex: /(\d+)\s*(weeks?|semanas?|周)\s*(?:ago|atrás|前)?/i, ms: 604_800_000 },
    { regex: /(\d+)\s*(months?|meses?|个月|月)\s*(?:ago|atrás|前)?/i, ms: 2_629_746_000 },
    { regex: /(\d+)\s*(years?|anos?|años?|年)\s*(?:ago|atrás|前)?/i, ms: 31_556_952_000 }
  ];
  for (const { regex, ms } of patterns) {
    const match = raw.match(regex);
    if (!match) continue;
    return {
      value: new Date(now.getTime() - Number(match[1]) * ms).toISOString(),
      is_estimated: true
    };
  }
  return { value: null, is_estimated: false };
}

export function engagementRate(views, likes, comments) {
  if (views?.value > 0 && likes?.value != null && comments?.value != null) {
    return {
      value: ((likes.value + comments.value) / views.value) * 100,
      missing_reason: ""
    };
  }
  return {
    value: null,
    missing_reason: "Likes or comments were not publicly available."
  };
}

export function contentItem(raw = {}) {
  const views = raw.views?.value !== undefined
    ? raw.views
    : metric(raw.views, raw.views_source, raw.views_confidence || "medium", raw.views_missing_reason);
  const likes = raw.likes?.value !== undefined
    ? raw.likes
    : metric(raw.likes, raw.likes_source, raw.likes_confidence || "medium", raw.likes_missing_reason);
  const comments = raw.comments?.value !== undefined
    ? raw.comments
    : metric(raw.comments, raw.comments_source, raw.comments_confidence || "medium", raw.comments_missing_reason);
  const published = raw.published_at?.value !== undefined
    ? raw.published_at
    : publishedAt(
      raw.published_at,
      raw.published_raw_text,
      raw.published_source,
      raw.published_confidence || "medium",
      raw.published_missing_reason,
      raw.published_estimated
    );
  return {
    platform: normalizeText(raw.platform),
    content_type: normalizeText(raw.content_type),
    video_id: normalizeText(raw.video_id),
    video_url: normalizeText(raw.video_url),
    title: normalizeText(raw.title) || null,
    is_pinned: Boolean(raw.is_pinned),
    views,
    likes,
    comments,
    published_at: published,
    engagement_rate: engagementRate(views, likes, comments)
  };
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function calculateViewSummary(contents = []) {
  const validViews = contents
    .map((item) => item?.views?.value)
    .filter((value) => value != null && value !== "")
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value >= 0);
  const sumViews = validViews.reduce((sum, value) => sum + value, 0);
  return {
    valid_views_count: validViews.length,
    sum_views: sumViews,
    minimum_views: validViews.length ? Math.min(...validViews) : null,
    maximum_views: validViews.length ? Math.max(...validViews) : null,
    average_views: validViews.length ? sumViews / validViews.length : null,
    median_views: median(validViews)
  };
}

export function ensureContentSummaryConsistency(analysis = {}) {
  const validation = calculateViewSummary(Array.isArray(analysis.contents) ? analysis.contents : []);
  const consistent = validation.valid_views_count === Number(analysis.valid_views_count || 0)
    && validation.average_views === analysis.average_views
    && validation.median_views === analysis.median_views;
  if (consistent) {
    return { ...analysis, summary_validation: validation };
  }
  return {
    ...analysis,
    capture_status: "failed",
    error: "CONTENT_VIEW_SUMMARY_MISMATCH",
    summary_validation: validation
  };
}

export function finalizeContentAnalysis(rawItems = [], options = {}) {
  const maximumCount = Math.max(1, Number(options.maximumCount) || 30);
  const requestedCount = Math.max(1, Math.min(maximumCount, Number(options.limit) || 30));
  const seen = new Set();
  const discovered = [];
  for (const raw of rawItems) {
    const item = contentItem(raw);
    const key = item.video_id || item.video_url;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    discovered.push(item);
  }

  const pinned = discovered.filter((item) => item.is_pinned);
  let eligible = options.excludePinned === false
    ? discovered
    : discovered.filter((item) => !item.is_pinned);
  const hasPublishedTimes = eligible.some((item) => item.published_at.value);
  const sortingBasis = hasPublishedTimes ? "published_at_then_platform_order" : "platform_order";
  if (hasPublishedTimes) {
    eligible = eligible
      .map((item, index) => ({ item, index }))
      .sort((left, right) => {
        const a = left.item.published_at.value ? Date.parse(left.item.published_at.value) : null;
        const b = right.item.published_at.value ? Date.parse(right.item.published_at.value) : null;
        if (a == null && b == null) return left.index - right.index;
        if (a == null) return 1;
        if (b == null) return -1;
        return b - a || left.index - right.index;
      })
      .map(({ item }) => item);
  }
  const contents = eligible.slice(0, requestedCount);
  const summaryValidation = calculateViewSummary(contents);
  const views = contents.map((item) => item.views.value).filter((value) => value != null);
  const validPublished = contents.filter((item) => item.published_at.value).length;
  const engagementItems = contents.filter((item) => item.engagement_rate.value != null);
  const totalEngagementViews = engagementItems.reduce((sum, item) => sum + item.views.value, 0);
  const totalInteractions = engagementItems.reduce(
    (sum, item) => sum + item.likes.value + item.comments.value,
    0
  );
  const returnedCount = contents.length;
  const viewCoverage = returnedCount ? views.length / returnedCount : 0;
  const publishTimeCoverage = returnedCount ? validPublished / returnedCount : 0;
  const engagementCoverage = returnedCount ? engagementItems.length / returnedCount : 0;
  let captureStatus = "unavailable";
  if (returnedCount >= 10 && viewCoverage >= 0.8) captureStatus = "success";
  else if (returnedCount && (views.length || validPublished || engagementItems.length)) captureStatus = "partial_success";

  return {
    requested_count: requestedCount,
    discovered_count: discovered.length,
    excluded_pinned_count: options.excludePinned === false ? 0 : pinned.length,
    returned_count: returnedCount,
    valid_views_count: summaryValidation.valid_views_count,
    valid_publish_time_count: validPublished,
    valid_engagement_count: engagementItems.length,
    view_coverage: viewCoverage,
    publish_time_coverage: publishTimeCoverage,
    engagement_coverage: engagementCoverage,
    average_views: summaryValidation.average_views,
    median_views: summaryValidation.median_views,
    weighted_engagement_rate: totalEngagementViews > 0
      ? (totalInteractions / totalEngagementViews) * 100
      : null,
    sorting_basis: sortingBasis,
    content_type: contents[0]?.content_type || normalizeText(options.contentType),
    capture_status: captureStatus,
    missing_field_summary: {
      views: returnedCount - views.length,
      published_at: returnedCount - validPublished,
      engagement_rate: returnedCount - engagementItems.length
    },
    summary_validation: summaryValidation,
    contents
  };
}

export function failedContentAnalysis(message, options = {}) {
  const result = finalizeContentAnalysis([], options);
  result.capture_status = "failed";
  result.error = normalizeText(message) || "Recent content analysis failed.";
  return result;
}

function abortError() {
  const error = new Error("CONTENT_ANALYSIS_CANCELLED");
  error.name = "AbortError";
  return error;
}

export async function sleepWithSignal(delay, signal) {
  if (signal?.aborted) throw abortError();
  await new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, delay);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export async function mapWithConcurrency(items, worker, options = {}) {
  const concurrency = Math.max(1, Math.min(2, Number(options.concurrency) || 2));
  const delay = Math.max(0, Number(options.delay) || CONTENT_DETAIL_DELAY_MS);
  const signal = options.signal;
  const results = new Array(items.length);
  let nextIndex = 0;
  let completed = 0;

  async function runWorker() {
    while (true) {
      if (signal?.aborted) throw abortError();
      const index = nextIndex;
      nextIndex += 1;
      if (index >= items.length) return;
      let attempt = 0;
      while (attempt < 2) {
        try {
          results[index] = await worker(items[index], index, signal);
          break;
        } catch (error) {
          if (error?.name === "AbortError") throw error;
          attempt += 1;
          if (attempt >= 2) {
            results[index] = items[index];
            break;
          }
        }
      }
      completed += 1;
      options.onProgress?.({ phase: "details", current: completed, total: items.length });
      if (nextIndex < items.length) await sleepWithSignal(delay, signal);
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, runWorker));
  return results;
}
