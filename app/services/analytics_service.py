from __future__ import annotations

"""Read-only descriptive analytics built from existing Creator data."""

import json
import math
from datetime import date
from statistics import median
from typing import Any, Protocol

from creator_repository import CreatorRepository


class CreatorAnalyticsSource(Protocol):
    def getCreators(self, include_archived: bool = False) -> list[dict[str, Any]]: ...


class CampaignCreatorAnalyticsSource(Protocol):
    def getCampaignCreators(
        self,
        campaign_id: str = "",
        creator_id: str = "",
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]: ...


class AnalyticsService:
    """Build read-only analytics from existing Creator-domain records."""

    PLATFORMS = ("tiktok", "instagram", "youtube")

    def __init__(
        self,
        creator_repository: CreatorAnalyticsSource,
        campaign_creator_repository: CampaignCreatorAnalyticsSource,
    ) -> None:
        self._creator_repository = creator_repository
        self._campaign_creator_repository = campaign_creator_repository

    def get_platform_analytics(self) -> dict[str, Any]:
        creators = self._creator_repository.getCreators(include_archived=False)
        relations = self._campaign_creator_repository.getCampaignCreators(
            include_archived=False
        )
        return self.build_platform_analytics(creators, relations)

    def get_geography_analytics(self) -> dict[str, Any]:
        creators = self._creator_repository.getCreators(include_archived=True)
        return self.build_geography_analytics(creators)

    def get_recorded_roi_trend(self) -> list[dict[str, Any]]:
        relations = self._campaign_creator_repository.getCampaignCreators(
            include_archived=False
        )
        return self.build_recorded_roi_trend(relations)

    @classmethod
    def build_geography_analytics(
        cls,
        creators: list[dict[str, Any]],
    ) -> dict[str, Any]:
        countries: dict[str, dict[str, Any]] = {}
        languages: dict[str, dict[str, Any]] = {}

        for creator in creators:
            country_key, country_name = cls._category(creator.get("country"))
            country = countries.setdefault(
                country_key,
                {"name": country_name, "creator_count": 0, "active_creator_count": 0},
            )
            country["creator_count"] += 1
            if not cls._text(creator.get("archived_at")):
                country["active_creator_count"] += 1

            language_key, language_name = cls._category(creator.get("language"))
            language = languages.setdefault(
                language_key,
                {"name": language_name, "creator_count": 0},
            )
            language["creator_count"] += 1

        return {
            "countries": cls._top_categories(list(countries.values())),
            "languages": cls._top_categories(list(languages.values())),
        }

    @classmethod
    def build_recorded_roi_trend(
        cls,
        relations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        monthly: dict[str, dict[str, Any]] = {}
        for relation in relations:
            if cls._text(relation.get("archived_at")):
                continue
            month = cls._publish_month(relation.get("publish_date"))
            if month is None:
                continue
            aggregate = monthly.setdefault(
                month,
                {
                    "campaign_creator_count": 0,
                    "total_cost": 0.0,
                    "recorded_roi": [],
                    "total_views": 0.0,
                    "total_likes": 0.0,
                    "total_comments": 0.0,
                },
            )
            aggregate["campaign_creator_count"] += 1
            for field in ("cost", "views", "likes", "comments"):
                value = cls._nonnegative_number(relation.get(field))
                if value is not None:
                    target = {
                        "cost": "total_cost",
                        "views": "total_views",
                        "likes": "total_likes",
                        "comments": "total_comments",
                    }[field]
                    aggregate[target] += value
            roi = cls._number(relation.get("roi"))
            if roi is not None:
                aggregate["recorded_roi"].append(roi)

        trend = []
        for month in sorted(monthly):
            aggregate = monthly[month]
            roi_values = aggregate["recorded_roi"]
            views = aggregate["total_views"]
            trend.append({
                "month": month,
                "campaign_creator_count": aggregate["campaign_creator_count"],
                "total_cost": cls._rounded(aggregate["total_cost"]),
                "average_recorded_roi": cls._rounded(sum(roi_values) / len(roi_values))
                if roi_values else None,
                "total_views": cls._rounded(views),
                "engagement_rate": cls._rounded(
                    (aggregate["total_likes"] + aggregate["total_comments"])
                    / views * 100
                ) if views else None,
            })
        return trend

    @classmethod
    def build_platform_analytics(
        cls,
        creators: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        aggregates = {
            platform: {
                "platform": platform,
                "creator_count": 0,
                "followers": [],
                "campaign_creator_count": 0,
                "published_count": 0,
                "views_total": 0.0,
                "likes_total": 0.0,
                "comments_total": 0.0,
                "cost_total": 0.0,
                "recorded_roi": [],
            }
            for platform in cls.PLATFORMS
        }
        creators_by_id: dict[str, str | None] = {}
        seen_creator_ids: set[str] = set()

        for creator in creators:
            if cls._text(creator.get("archived_at")):
                continue
            creator_id = cls._text(
                creator.get("creator_id") or creator.get("analysis_id")
            )
            if not creator_id or creator_id in seen_creator_ids:
                continue
            seen_creator_ids.add(creator_id)
            platform = cls._canonical_platform(creator.get("platform"))
            creators_by_id[creator_id] = platform
            if platform is None:
                continue
            aggregate = aggregates[platform]
            aggregate["creator_count"] += 1
            followers = cls._follower_number(creator.get("followers"))
            if followers is not None:
                aggregate["followers"].append(followers)

        ignored_campaign_creator_count = 0
        for relation in relations:
            if cls._text(relation.get("archived_at")):
                continue
            creator_id = cls._text(relation.get("creator_id"))
            platform = creators_by_id.get(creator_id)
            if platform is None:
                ignored_campaign_creator_count += 1
                continue

            aggregate = aggregates[platform]
            aggregate["campaign_creator_count"] += 1
            if cls._has_publish_links(relation.get("publish_links")):
                aggregate["published_count"] += 1

            for field in ("views", "likes", "comments", "cost"):
                value = cls._nonnegative_number(relation.get(field))
                if value is not None:
                    target = "cost_total" if field == "cost" else f"{field}_total"
                    aggregate[target] += value
            roi = cls._number(relation.get("roi"))
            if roi is not None:
                aggregate["recorded_roi"].append(roi)

        platforms = [cls._finalize(aggregates[platform]) for platform in cls.PLATFORMS]
        return {
            "platforms": platforms,
            "summary": {
                "platform_count": len(cls.PLATFORMS),
                "creator_count": sum(row["creator_count"] for row in platforms),
                "campaign_creator_count": sum(
                    row["campaign_creator_count"] for row in platforms
                ),
                "ignored_campaign_creator_count": ignored_campaign_creator_count,
            },
        }

    @classmethod
    def _finalize(cls, aggregate: dict[str, Any]) -> dict[str, Any]:
        followers = aggregate.pop("followers")
        roi_values = aggregate.pop("recorded_roi")
        relation_count = aggregate["campaign_creator_count"]
        views_total = aggregate["views_total"]
        return {
            **aggregate,
            "followers_average": cls._rounded(sum(followers) / len(followers))
            if followers else None,
            "followers_median": cls._rounded(median(followers))
            if followers else None,
            "publish_rate": cls._rounded(
                aggregate["published_count"] / relation_count * 100
            ) if relation_count else None,
            "visible_engagement_rate": cls._rounded(
                (aggregate["likes_total"] + aggregate["comments_total"])
                / views_total * 100
            ) if views_total else None,
            "recorded_roi_average": cls._rounded(sum(roi_values) / len(roi_values))
            if roi_values else None,
            "views_total": cls._rounded(aggregate["views_total"]),
            "likes_total": cls._rounded(aggregate["likes_total"]),
            "comments_total": cls._rounded(aggregate["comments_total"]),
            "cost_total": cls._rounded(aggregate["cost_total"]),
        }

    @staticmethod
    def _canonical_platform(value: object) -> str | None:
        normalized = str(value or "").strip().casefold()
        return normalized if normalized in AnalyticsService.PLATFORMS else None

    @classmethod
    def _category(cls, value: object) -> tuple[str, str]:
        name = cls._text(value)
        if not name or name.casefold() == "unknown":
            return "unknown", "Unknown"
        return name.casefold(), name

    @staticmethod
    def _top_categories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unknown = [row for row in rows if row["name"] == "Unknown"]
        known = [row for row in rows if row["name"] != "Unknown"]
        known.sort(key=lambda row: (-row["creator_count"], row["name"].casefold()))
        top = known[:10]
        overflow = known[10:]
        if overflow:
            other = next(
                (row for row in top if row["name"].casefold() == "other"),
                None,
            )
            if other is None:
                other = {"name": "Other", "creator_count": 0}
                if "active_creator_count" in known[0]:
                    other["active_creator_count"] = 0
                top.append(other)
            other["creator_count"] += sum(row["creator_count"] for row in overflow)
            if "active_creator_count" in other:
                other["active_creator_count"] += sum(
                    row["active_creator_count"] for row in overflow
                )
        result = top + unknown
        result.sort(key=lambda row: (-row["creator_count"], row["name"].casefold()))
        return result

    @classmethod
    def _publish_month(cls, value: object) -> str | None:
        text = cls._text(value)
        if len(text) < 10:
            return None
        try:
            parsed = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return parsed.strftime("%Y-%m")

    @staticmethod
    def _follower_number(value: object) -> float | None:
        # Reuse Creator Library's established numeric/K/M/B/万/亿 parsing rules.
        number = CreatorRepository._metric_sort_value(value)
        return number if number is not None and math.isfinite(number) and number >= 0 else None

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _nonnegative_number(cls, value: object) -> float | None:
        number = cls._number(value)
        return number if number is not None and number >= 0 else None

    @classmethod
    def _has_publish_links(cls, value: object) -> bool:
        if isinstance(value, (list, tuple)):
            return any(cls._text(item) for item in value)
        text = cls._text(value)
        if not text:
            return False
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return True
            return not isinstance(parsed, list) or any(cls._text(item) for item in parsed)
        return True

    @staticmethod
    def _rounded(value: float) -> int | float:
        rounded = round(value, 2)
        return int(rounded) if rounded.is_integer() else rounded

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()
