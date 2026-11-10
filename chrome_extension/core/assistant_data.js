(() => {
  const RANGE_VALUES = new Set(["items:7", "items:30", "days:7", "days:30"]);

  const finiteMetric = (item, name) => {
    const value = item?.[name]?.value;
    return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
  };

  const publishedTime = (item) => {
    const raw = item?.published_at?.value;
    if (!raw) return null;
    const value = Date.parse(raw);
    return Number.isFinite(value) ? value : null;
  };

  const average = (values) => values.length
    ? values.reduce((total, value) => total + value, 0) / values.length
    : null;

  const median = (values) => {
    if (!values.length) return null;
    const sorted = [...values].sort((left, right) => left - right);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  };

  function selectContents(contents, options = {}) {
    const range = RANGE_VALUES.has(options.range) ? options.range : "items:30";
    const excludePinned = options.excludePinned !== false;
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    const source = Array.isArray(contents) ? contents : [];
    const eligible = source.filter((item) => !(excludePinned && item?.is_pinned === true));
    const unknownPinnedCount = excludePinned
      ? eligible.filter((item) => item?.is_pinned !== true && item?.is_pinned !== false).length
      : 0;
    const [kind, rawAmount] = range.split(":");
    const amount = Number(rawAmount);
    const withTime = eligible.map((item, index) => ({ item, index, time: publishedTime(item) }));
    let selected;
    if (kind === "days") {
      const cutoff = now - amount * 24 * 60 * 60 * 1000;
      selected = withTime.filter((row) => row.time !== null && row.time >= cutoff);
    } else {
      selected = withTime.sort((left, right) => {
        if (left.time === null && right.time === null) return left.index - right.index;
        if (left.time === null) return 1;
        if (right.time === null) return -1;
        return right.time - left.time;
      }).slice(0, amount);
    }
    const items = selected.map((row) => row.item);
    const views = items.map((item) => finiteMetric(item, "views")).filter((value) => value !== null);
    const likes = items.map((item) => finiteMetric(item, "likes")).filter((value) => value !== null);
    const comments = items.map((item) => finiteMetric(item, "comments")).filter((value) => value !== null);
    const engagementItems = items.filter((item) => (
      finiteMetric(item, "views") > 0
      && finiteMetric(item, "likes") !== null
      && finiteMetric(item, "comments") !== null
    ));
    const engagementViews = engagementItems.reduce((total, item) => total + finiteMetric(item, "views"), 0);
    const interactions = engagementItems.reduce(
      (total, item) => total + finiteMetric(item, "likes") + finiteMetric(item, "comments"), 0
    );
    return {
      range,
      excludePinned,
      items,
      excludedPinnedCount: source.filter((item) => excludePinned && item?.is_pinned === true).length,
      unknownPinnedCount,
      missingPublishedCount: eligible.filter((item) => publishedTime(item) === null).length,
      knownPublishedCount: eligible.filter((item) => publishedTime(item) !== null).length,
      timeCoverageComplete: kind !== "days",
      metrics: {
        averageViews: average(views),
        medianViews: median(views),
        averageLikes: average(likes),
        averageComments: average(comments),
        validViews: views.length,
        validLikes: likes.length,
        validComments: comments.length,
        sampleCount: items.length,
        weightedEngagementRate: engagementViews > 0 ? (interactions / engagementViews) * 100 : null
      }
    };
  }

  globalThis.KOLConnectAssistantData = Object.freeze({ selectContents, finiteMetric, publishedTime });
})();
