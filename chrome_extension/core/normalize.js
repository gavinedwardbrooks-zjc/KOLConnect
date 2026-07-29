export function normalizeText(value) {
  return String(value ?? "")
    .replace(/\\u002F/gi, "/")
    .replace(/\\n/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeMultilineText(value) {
  return String(value ?? "")
    .replace(/\\u002F/gi, "/")
    .replace(/\\r\\n|\\r|\\n/g, "\n")
    .split("\n")
    .map((line) => line.replace(/[^\S\n]+/g, " ").trim())
    .filter((line, index, lines) => line || (index > 0 && lines[index - 1]))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function normalizeProfileUrl(value) {
  try {
    const url = new URL(normalizeText(value));
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/$/, "");
  } catch (_) {
    return "";
  }
}

export function normalizeFollowerText(value) {
  const parsed = parseHumanCount(value);
  return parsed == null ? null : String(parsed);
}

export function parseHumanCount(value) {
  let raw = normalizeText(value)
    .replace(/\b(followers?|subscribers?|seguidores?|inscritos?|suscriptores?|abonn[ée]s?)\b/gi, "")
    .trim()
    .toLowerCase();
  if (!raw) return null;

  const multiplierMatch = raw.match(/(mio|mil|mi|m|k|b|万|億|亿)(?:\b|$)/i);
  const unit = multiplierMatch?.[1]?.toLowerCase() || "";
  raw = raw.replace(/[^\d.,-]/g, "");
  if (!raw || raw === "-") return null;

  let numericText = raw;
  if (unit) {
    if (numericText.includes(",") && numericText.includes(".")) {
      const lastComma = numericText.lastIndexOf(",");
      const lastDot = numericText.lastIndexOf(".");
      const decimalSeparator = lastComma > lastDot ? "," : ".";
      numericText = numericText
        .replace(decimalSeparator === "," ? /\./g : /,/g, "")
        .replace(decimalSeparator, ".");
    } else if (numericText.includes(",")) {
      numericText = numericText.replace(",", ".");
    }
  } else if (/^\d{1,3}(?:[.,]\d{3})+$/.test(numericText)) {
    numericText = numericText.replace(/[.,]/g, "");
  } else if (numericText.includes(",") && !numericText.includes(".")) {
    numericText = numericText.replace(",", ".");
  } else {
    numericText = numericText.replace(/,/g, "");
  }

  const number = Number(numericText);
  if (!Number.isFinite(number) || number < 0) return null;
  const multipliers = {
    k: 1_000,
    mil: 1_000,
    m: 1_000_000,
    mi: 1_000_000,
    mio: 1_000_000,
    b: 1_000_000_000,
    万: 10_000,
    億: 100_000_000,
    亿: 100_000_000
  };
  return Math.round(number * (multipliers[unit] || 1));
}

export function safeAnalysisUrl(value) {
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`;
  } catch (_) {
    return "";
  }
}
