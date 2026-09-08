from __future__ import annotations

"""Pure M8.5 analytics over append-only Publication observations."""

from collections import defaultdict
from datetime import datetime, timezone
import math
from typing import Any

from domain.money import currency_code, grouped_amounts


METRICS = ("views", "likes", "comments", "engagement_rate")


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _rounded(value: float | None, digits: int = 2) -> int | float | None:
    if value is None:
        return None
    result = round(value, digits)
    return int(result) if result.is_integer() else result


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text) if text else None
        if parsed is not None:
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        return None
    except ValueError:
        return None


def _observation_key(item: dict[str, Any]) -> tuple:
    return (
        _parse_time(item.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc),
        str(item.get("observation_id") or ""),
    )


def _currency(value: object) -> str:
    try:
        return currency_code(value, "currency")
    except ValueError:
        return ""


def _group_publications(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    publications: dict[str, dict[str, Any]] = {}
    for row in rows:
        publication_id = str(row.get("publication_id") or "")
        if not publication_id:
            continue
        publication = publications.setdefault(publication_id, {
            key: row.get(key) for key in (
                "publication_id", "publication_url", "actual_account_uid", "platform", "video_id", "published_at",
                "campaign_creator_id", "campaign_id", "campaign_name", "creator_id", "creator_name",
            )
        })
        if row.get("observation_id"):
            publication.setdefault("observations", []).append({
                key: row.get(key) for key in (
                    "observation_id", "observed_at", "views", "likes", "comments", "shares",
                    "engagement_rate", "source", "confidence",
                )
            })
    for publication in publications.values():
        publication.setdefault("observations", []).sort(
            key=_observation_key
        )
    return publications


def publication_trend(publication: dict[str, Any]) -> dict[str, Any]:
    observations = sorted(publication.get("observations", []), key=_observation_key)
    growth = {}
    for metric in METRICS:
        valid = [item for item in observations if _number(item.get(metric)) is not None and _parse_time(item.get("observed_at"))]
        if len(valid) < 2:
            growth[metric] = None
            continue
        first, latest = valid[0], valid[-1]
        first_value, latest_value = _number(first[metric]), _number(latest[metric])
        delta = latest_value - first_value
        growth[metric] = {
            "absolute": _rounded(delta),
            "percentage": _rounded(delta / first_value * 100) if first_value else None,
            "start_observed_at": first["observed_at"],
            "end_observed_at": latest["observed_at"],
            "status": "decrease" if delta < 0 else ("unchanged" if delta == 0 else "increase"),
        }
    return {
        **{key: publication.get(key) for key in (
            "publication_id", "publication_url", "actual_account_uid", "platform", "video_id", "published_at",
            "campaign_creator_id", "campaign_id", "campaign_name", "creator_id", "creator_name",
        )},
        "series": [{
            key: item.get(key) for key in (
                "observation_id", "observed_at", "views", "likes", "comments", "shares",
                "engagement_rate", "source", "confidence",
            )
        } for item in observations],
        "growth": growth,
    }


def _latest_valid(publication: dict[str, Any], metric: str) -> float | None:
    for observation in reversed(publication.get("observations", [])):
        value = _number(observation.get(metric))
        if value is not None:
            return value
    return None


def _coverage(values: list[float | None]) -> dict[str, int | float | None]:
    valid = [value for value in values if value is not None]
    return {
        "total": _rounded(sum(valid)) if valid else None,
        "valid_count": len(valid),
        "missing_count": len(values) - len(valid),
        "total_publications": len(values),
    }


def campaign_performance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    publications = _group_publications(rows)
    values = {metric: [_latest_valid(item, metric) for item in publications.values()] for metric in METRICS}
    totals = {metric: _coverage(values[metric]) for metric in ("views", "likes", "comments")}
    valid_er = [value for value in values["engagement_rate"] if value is not None]
    average_er = _rounded(sum(valid_er) / len(valid_er)) if valid_er else None

    def video_key(item):
        views = _latest_valid(item, "views")
        er = _latest_valid(item, "engagement_rate")
        return (-(views if views is not None else -1), -(er if er is not None else -1), str(item["publication_id"]))

    valid_videos = [item for item in publications.values() if _latest_valid(item, "views") is not None]
    top_video = min(valid_videos, key=video_key) if valid_videos else None
    valid_er_publications = [item for item in publications.values() if _latest_valid(item, "engagement_rate") is not None]
    highest_er = min(valid_er_publications, key=lambda item: (-_latest_valid(item, "engagement_rate"), str(item["publication_id"]))) if valid_er_publications else None

    creators = defaultdict(lambda: {"views": 0.0, "valid": 0, "ers": [], "publications": 0})
    for item in publications.values():
        aggregate = creators[str(item.get("creator_id") or "")]
        aggregate.update({"creator_id": item.get("creator_id"), "creator_name": item.get("creator_name")})
        aggregate["publications"] += 1
        view = _latest_valid(item, "views")
        if view is not None:
            aggregate["views"] += view
            aggregate["valid"] += 1
        er = _latest_valid(item, "engagement_rate")
        if er is not None:
            aggregate["ers"].append(er)
    eligible_creators = [item for item in creators.values() if item["valid"]]
    top_creator = min(eligible_creators, key=lambda item: (-item["views"], -(sum(item["ers"]) / len(item["ers"]) if item["ers"] else -1), str(item["creator_id"]))) if eligible_creators else None

    fastest = []
    for item in publications.values():
        valid = [obs for obs in item["observations"] if _number(obs.get("views")) is not None and _parse_time(obs.get("observed_at"))]
        if len(valid) < 2:
            continue
        first, latest = valid[0], valid[-1]
        elapsed = (_parse_time(latest["observed_at"]) - _parse_time(first["observed_at"])).total_seconds() / 86400
        if elapsed <= 0:
            continue
        delta = _number(latest["views"]) - _number(first["views"])
        fastest.append({**{key: item.get(key) for key in (
                            "publication_id", "creator_id", "creator_name", "publication_url",
                            "actual_account_uid", "platform",
                        )},
                        "start_observed_at": first["observed_at"], "end_observed_at": latest["observed_at"],
                        "elapsed_days": elapsed, "elapsed_seconds": elapsed * 86400,
                        "views_delta": _rounded(delta), "growth_rate": delta / elapsed})
    fastest_growing = min(fastest, key=lambda item: (-item["growth_rate"], str(item["publication_id"]))) if fastest else None
    latest_times = [str(obs.get("observed_at")) for item in publications.values() for obs in item["observations"] if _parse_time(obs.get("observed_at"))]
    monetary = creator_historical_performance(rows)
    return {
        "publication_count": len(publications), "totals": totals,
        "average_er": average_er, "valid_er_count": len(valid_er), "total_publications": len(publications),
        "top_video": ({**{key: top_video.get(key) for key in (
            "publication_id", "creator_id", "creator_name", "publication_url",
            "actual_account_uid", "platform",
        )}, "views": _rounded(_latest_valid(top_video, "views")), "engagement_rate": _rounded(_latest_valid(top_video, "engagement_rate"))} if top_video else None),
        "top_creator": ({
            "creator_id": top_creator.get("creator_id"), "creator_name": top_creator.get("creator_name"),
            "views": _rounded(top_creator["views"]), "valid_publication_count": top_creator["valid"],
            "publication_count": top_creator["publications"],
            "average_er": _rounded(sum(top_creator["ers"]) / len(top_creator["ers"])) if top_creator["ers"] else None,
            "valid_er_count": len(top_creator["ers"]),
        } if top_creator else None),
        "highest_er": ({**{key: highest_er.get(key) for key in (
            "publication_id", "creator_id", "creator_name", "publication_url",
            "actual_account_uid", "platform",
        )}, "engagement_rate": _rounded(_latest_valid(highest_er, "engagement_rate"))} if highest_er else None),
        "fastest_growing": fastest_growing, "latest_observed_at": max(latest_times, key=_parse_time) if latest_times else None,
        "total_cost_by_currency": monetary["total_cost_by_currency"],
        "total_quote_by_currency": monetary["total_quote_by_currency"],
        "efficiency_by_currency": monetary["efficiency_by_currency"],
        "unknown_currency_records": monetary["unknown_currency_records"],
        "roi": monetary["roi"], "roi_reason": monetary["roi_reason"],
        "publications": [publication_trend(item) for item in publications.values()],
    }


def creator_historical_performance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    publications = _group_publications(rows)
    relation_rows = {}
    campaigns = {}
    for row in rows:
        relation_id = str(row.get("campaign_creator_id") or "")
        if relation_id:
            relation_rows.setdefault(relation_id, row)
        campaign_id = str(row.get("campaign_id") or "")
        if campaign_id:
            campaigns.setdefault(campaign_id, {key: row.get(key) for key in ("campaign_id", "campaign_name", "campaign_status", "start_date", "end_date")})
    views = [_latest_valid(item, "views") for item in publications.values()]
    ers = [_latest_valid(item, "engagement_rate") for item in publications.values()]
    valid_views, valid_ers = [v for v in views if v is not None], [v for v in ers if v is not None]
    costs = grouped_amounts(relation_rows.values(), "cost", "cost_currency")["totals_by_currency"]
    quotes = grouped_amounts(relation_rows.values(), "creator_quote", "quote_currency")["totals_by_currency"]
    unknown_currency_records = {"cost": 0, "quote": 0}
    efficiency = defaultdict(lambda: {
        "cost": 0.0,
        "views": 0.0,
        "engagements": 0.0,
        "views_complete": True,
        "engagement_complete": True,
        "cooperation_count": 0,
        "publication_count": 0,
    })
    for relation_id, row in relation_rows.items():
        currency = _currency(row.get("cost_currency"))
        cost = _number(row.get("cost"))
        quote_currency = _currency(row.get("quote_currency"))
        quote = _number(row.get("creator_quote"))
        if quote is not None and not quote_currency:
            unknown_currency_records["quote"] += 1
        if cost is not None and not currency:
            unknown_currency_records["cost"] += 1
        if cost is None or not currency:
            continue
        bucket = efficiency[currency]
        bucket["cost"] += cost
        owned = [item for item in publications.values() if item.get("campaign_creator_id") == relation_id]
        bucket["cooperation_count"] += 1
        bucket["publication_count"] += len(owned)
        relation_views = [_latest_valid(item, "views") for item in owned]
        if relation_views and all(value is not None for value in relation_views):
            bucket["views"] += sum(relation_views)
        else:
            bucket["views_complete"] = False
        engagements = []
        for item in owned:
            likes, comments = _latest_valid(item, "likes"), _latest_valid(item, "comments")
            if likes is None or comments is None:
                engagements = []
                break
            engagements.append(likes + comments)
        if engagements:
            bucket["engagements"] += sum(engagements)
        else:
            bucket["engagement_complete"] = False
    return {
        "cooperation_count": len(relation_rows), "historical_campaign_count": len(campaigns),
        "historical_campaigns": sorted(campaigns.values(), key=lambda item: (str(item.get("start_date") or ""), str(item["campaign_id"]))),
        "publication_count": len(publications),
        "average_latest_views": _rounded(sum(valid_views) / len(valid_views)) if valid_views else None,
        "valid_publication_views_count": len(valid_views), "total_historical_publications": len(publications),
        "average_latest_er": _rounded(sum(valid_ers) / len(valid_ers)) if valid_ers else None,
        "valid_publication_er_count": len(valid_ers),
        "total_cost_by_currency": {key: _rounded(costs[key]) for key in sorted(costs)},
        "total_quote_by_currency": {key: _rounded(quotes[key]) for key in sorted(quotes)},
        "unknown_currency_records": unknown_currency_records,
        "efficiency_by_currency": {key: {
            "cpv": _rounded(value["cost"] / value["views"], 6) if value["views_complete"] and value["views"] > 0 else None,
            "cpe": _rounded(value["cost"] / value["engagements"], 6) if value["engagement_complete"] and value["engagements"] > 0 else None,
            "costed_cooperation_count": value["cooperation_count"],
            "publication_count": value["publication_count"],
            "views_complete": value["views_complete"],
            "engagement_complete": value["engagement_complete"],
        } for key, value in sorted(efficiency.items())},
        "roi": None, "roi_reason": "AUTHORITATIVE_RETURN_INPUT_UNAVAILABLE",
    }
