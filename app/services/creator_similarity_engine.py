"""Pure M8.2 scoring: exact rational arithmetic until the JSON boundary."""

from copy import deepcopy
from fractions import Fraction
import json

from domain.normalization import normalize_tags


WEIGHTS = {"tag": 30, "content": 20, "followers": 15, "price": 15,
           "engagement": 10, "country_language": 5, "platform": 5}
LABELS = {"tag": "标签", "content": "内容类型", "followers": "粉丝",
          "price": "报价", "engagement": "互动率", "country_language": "国家/语言",
          "platform": "平台"}
MISSING = {"", "--", "unknown", "unavailable", "n/a", "none", "null"}


def tokens(value):
    result = set()
    for tag in normalize_tags(value):
        normalized = tag.casefold()
        payload = normalized.rsplit(":", 1)[-1].strip()
        if normalized not in MISSING and payload not in MISSING:
            result.add(normalized)
    return result


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Fraction(str(value))
        return result if result >= 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def ratio(left, right):
    a, b = number(left), number(right)
    if a is None or b is None:
        return None
    return min(a, b) / max(a, b) if max(a, b) else Fraction(1)


def set_score(sets, source):
    left, right = tokens(sets.get("source")), tokens(sets.get("candidate"))
    if not left or not right:
        return None, {"source": source, "reason": "missing_tokens"}
    overlap = sorted(left & right)
    return Fraction(len(overlap), len(left | right)), {
        "source": source, "matched": overlap, "source_count": len(left),
        "candidate_count": len(right), "union_count": len(left | right),
    }


def best_per_platform(pairs):
    """Each shared platform contributes once; UID/record ties ignore row order."""
    chosen = {}
    for score, evidence in pairs:
        platform = str(evidence.get("platform") or "").strip().casefold()
        if not platform or score is None:
            continue
        tie = json.dumps(evidence, sort_keys=True, ensure_ascii=False)
        old = chosen.get(platform)
        if old is None or (-score, tie) < (-old[0], old[1]):
            chosen[platform] = (score, tie, evidence)
    ordered = [chosen[key] for key in sorted(chosen)]
    if not ordered:
        return None, {"reason": "no_comparable_account_pair", "pairs": []}
    return sum((item[0] for item in ordered), Fraction()) / len(ordered), {
        "aggregation": "best_pair_per_shared_platform_mean",
        "pairs": [{**item[2], "pair_score": float(item[0])} for item in ordered],
    }


class CreatorSimilarityEngine:
    def _dimensions(self, evidence):
        user_sets = evidence.get("user_tag_sets", {})
        tag = set_score(user_sets, "user_tags")
        if tag[0] is None:
            tag = set_score(evidence.get("ai_tag_sets", {}), "ai_tags_fallback")
        content = set_score(evidence.get("content_category_sets", {}), "Creators.content_category")
        pairs = []
        for row in evidence.get("follower_pairs", []):
            if not row.get("source_account_uid") or not row.get("candidate_account_uid"):
                continue
            score = ratio(row.get("source_followers"), row.get("candidate_followers"))
            pairs.append((score, {key: row.get(key) for key in (
                "platform", "source_account_uid", "candidate_account_uid",
                "source_followers", "candidate_followers",
            )}))
        followers = best_per_platform(pairs)
        selected = {str(row["platform"]).casefold(): row for row in followers[1]["pairs"]}

        quote = evidence.get("quote", {})
        price_pairs = []
        for left in quote.get("source_contracts", []):
            for right in quote.get("candidate_contracts", []):
                if not left.get("currency") or not left.get("pricing_unit"):
                    continue
                if any(left.get(key) != right.get(key) for key in ("currency", "pricing_unit", "value_type")):
                    continue
                score = ratio(left.get("amount"), right.get("amount"))
                if score is not None:
                    price_pairs.append((score, {
                        "currency": left["currency"], "pricing_unit": left["pricing_unit"],
                        "value_type": left["value_type"], "source_amount": left["amount"],
                        "candidate_amount": right["amount"],
                    }))
        price = max(price_pairs, key=lambda item: (item[0], json.dumps(item[1], sort_keys=True))) if price_pairs else (
            None, {"reason": "missing_or_incompatible_price_contract"})

        engagement_pairs = []
        engagement = evidence.get("engagement", {})
        for left in engagement.get("source_records", []):
            for right in engagement.get("candidate_records", []):
                platform = str(left.get("platform") or "").casefold()
                if not platform or platform != str(right.get("platform") or "").casefold():
                    continue
                if not left.get("account_uid") or not right.get("account_uid"):
                    continue
                pair = selected.get(platform)
                if pair and (pair["source_account_uid"], pair["candidate_account_uid"]) != (left["account_uid"], right["account_uid"]):
                    continue
                # Same formula as AnalyticsService.visible_engagement_rate, with
                # complete recorded metrics and proven actual account attribution.
                rates = []
                for row in (left, right):
                    views, likes, comments = (number(row.get(key)) for key in ("views", "likes", "comments"))
                    rates.append((likes + comments) / views * 100 if views and likes is not None and comments is not None else None)
                score = ratio(*rates)
                if score is not None:
                    engagement_pairs.append((score, {
                        "platform": platform, "source_account_uid": left["account_uid"],
                        "candidate_account_uid": right["account_uid"],
                        "source_rate": float(rates[0]), "candidate_rate": float(rates[1]),
                        "source_relation_id": left.get("relation_id"), "candidate_relation_id": right.get("relation_id"),
                        "source": "recorded_visible_engagement_rate", "freshness": "unknown",
                        "measured_at": None,
                    }))
        er = best_per_platform(engagement_pairs)

        geography = evidence.get("country_language", {})
        sub_signals = {}
        for key in ("country", "language"):
            a, b = (str(geography.get(f"{side}_{key}") or "").strip().casefold() for side in ("source", "candidate"))
            if a not in MISSING and b not in MISSING:
                sub_signals[key] = {"source": a, "candidate": b, "score": int(a == b)}
        geo = (sum((Fraction(row["score"]) for row in sub_signals.values()), Fraction()) / len(sub_signals) if sub_signals else None,
               {"sub_signals": sub_signals, "unavailable": [key for key in ("country", "language") if key not in sub_signals]})
        platforms = evidence.get("platforms", {})
        a, b = tokens(platforms.get("source")), tokens(platforms.get("candidate"))
        matched = [row for row in evidence.get("platform_accounts", [])
                   if row.get("source_account_uid") and row.get("candidate_account_uid")]
        platform = (Fraction(bool(matched)) if a and b else None,
                    {"matched": sorted(a & b) if matched else [], "pairs": matched})
        return {"tag": tag, "content": content, "followers": followers, "price": price,
                "engagement": er, "country_language": geo, "platform": platform}

    def _score(self, candidate):
        values = self._dimensions(candidate.get("evidence", {}))
        weight = sum(WEIGHTS[key] for key, (score, _) in values.items() if score is not None)
        raw = sum((score * WEIGHTS[key] for key, (score, _) in values.items() if score is not None), Fraction())
        final = raw / weight if weight else None
        dimensions, reasons, missing = {}, [], []
        for key, (score, evidence) in values.items():
            contribution = score * WEIGHTS[key] / weight if score is not None and weight else None
            dimensions[key] = {
                "available": score is not None, "nominal_weight": WEIGHTS[key],
                "score": float(score) if score is not None else None,
                "normalized_weight": WEIGHTS[key] / weight if score is not None and weight else None,
                "normalized_contribution": float(contribution) if contribution is not None else None,
                "evidence": evidence,
            }
            if score is None:
                missing.append(key)
            elif score > 0:
                text = f"{LABELS[key]}：{float(score) * 100:.1f}%"
                if key in {"tag", "content"}:
                    text += f"，共同项 {len(evidence['matched'])}/{evidence['union_count']}：" + "、".join(evidence["matched"])
                    if evidence["source"] == "ai_tags_fallback":
                        text += "（AI 标签补充，非人工标签）"
                elif key == "price":
                    text += f"，{evidence['currency']}/{evidence['pricing_unit']}：{evidence['source_amount']} vs {evidence['candidate_amount']}"
                elif key in {"followers", "engagement"}:
                    text += "，" + "、".join(row["platform"] for row in evidence["pairs"])
                    if key == "engagement":
                        text += "（历史记录；测量时间未知）"
                reasons.append({"id": key, "text": text})
        payload = deepcopy(candidate)
        payload.update({
            "base_similarity_score": round(float(final * 100), 2) if final is not None else None,
            "similarity_percentage": round(float(final * 100), 2) if final is not None else None,
            "raw_weighted_score": float(raw), "available_nominal_weight": weight,
            "dimensions": dimensions, "why_recommended": reasons, "unavailable_dimensions": missing,
        })
        return final, payload

    def score(self, candidate):
        return self._score(candidate)[1]

    def rank(self, candidates):
        scored = [self._score(row) for row in candidates]
        scored.sort(key=lambda item: (-(item[0] if item[0] is not None else Fraction(-1)),
                                      -item[1]["available_nominal_weight"], item[1]["creator_id"]))
        return [item[1] for item in scored]
