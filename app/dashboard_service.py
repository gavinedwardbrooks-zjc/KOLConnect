from __future__ import annotations

"""Read-only KPI calculations for the KOLConnect operational dashboard."""

from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard_repository import DashboardRepository


class DashboardService:
    """Build dashboard responses from repository records, never from Excel directly."""

    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    def getOverview(self) -> dict[str, Any]:
        creators = self._repository.get_creators()
        cooperations = self._repository.get_cooperation_records(creators)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return {
            "total_creators": len(creators),
            "new_creators_7d": sum(1 for creator in creators if self._is_on_or_after(creator.get("analysis_time"), recent_cutoff)),
            "discovered_count": self._status_count(creators, "discovered"),
            "cooperating_count": self._status_count(creators, "cooperating"),
            "cooperation_spend": self._sum_numbers(cooperations, "price"),
            "average_roi": self._average_numbers(cooperations, "roi"),
        }

    def getCreatorHealth(self) -> dict[str, list[dict[str, Any]]]:
        rising_creators: list[dict[str, Any]] = []
        falling_creators: list[dict[str, Any]] = []
        expired_creators: list[dict[str, Any]] = []

        for creator in self._repository.get_creator_health_records():
            trend = creator.get("trend") if isinstance(creator.get("trend"), dict) else {}
            freshness = trend.get("freshness") if isinstance(trend.get("freshness"), dict) else {}
            if freshness.get("status") == "stale":
                expired_creators.append(self._creator_summary(creator, freshness=freshness))

            change = self._primary_performance_change(trend)
            if not change:
                continue
            summary = self._creator_summary(creator, change=change)
            if change.get("direction") == "growth":
                rising_creators.append(summary)
            elif change.get("direction") == "decline":
                falling_creators.append(summary)

        return {
            "rising_creators": rising_creators,
            "falling_creators": falling_creators,
            "expired_creators": expired_creators,
        }

    def getCooperationPerformance(self) -> dict[str, Any]:
        creators = self._repository.get_creators()
        cooperations = self._repository.get_cooperation_records(creators)
        totals_by_creator: dict[str, dict[str, Any]] = {}
        for cooperation in cooperations:
            creator_id = str(cooperation.get("creator_id") or "")
            if not creator_id:
                continue
            aggregate = totals_by_creator.setdefault(creator_id, {
                "creator_id": creator_id,
                "creator_name": str(cooperation.get("creator_name") or ""),
                "campaign_count": 0,
                "total_cost": 0.0,
                "total_views": 0.0,
                "roi_values": [],
            })
            aggregate["campaign_count"] += 1
            aggregate["total_cost"] += self._number(cooperation.get("price")) or 0.0
            aggregate["total_views"] += self._number(cooperation.get("total_views")) or 0.0
            roi = self._number(cooperation.get("roi"))
            if roi is not None:
                aggregate["roi_values"].append(roi)

        top_creators = []
        for aggregate in totals_by_creator.values():
            roi_values = aggregate.pop("roi_values")
            aggregate["average_roi"] = sum(roi_values) / len(roi_values) if roi_values else None
            top_creators.append(aggregate)
        top_creators.sort(key=lambda item: (item["average_roi"] is not None, item["average_roi"] or item["total_views"]), reverse=True)

        return {
            "total_campaigns": len(cooperations),
            "total_cost": self._sum_numbers(cooperations, "price"),
            "total_views": self._sum_numbers(cooperations, "total_views"),
            "average_roi": self._average_numbers(cooperations, "roi"),
            "top_creators": top_creators[:5],
        }

    def getActionItems(self) -> dict[str, list[dict[str, Any]]]:
        creators = self._repository.get_creators()
        health = self.getCreatorHealth()
        pending_contact = [
            self._creator_summary(creator)
            for creator in creators
            if str(creator.get("status") or "") == "discovered"
        ]
        incomplete_cooperations = []
        for cooperation in self._repository.get_cooperation_records(creators):
            if str(cooperation.get("result") or "").strip():
                continue
            incomplete_cooperations.append({
                "cooperation_id": str(cooperation.get("cooperation_id") or ""),
                "creator_id": str(cooperation.get("creator_id") or ""),
                "creator_name": str(cooperation.get("creator_name") or ""),
                "campaign": str(cooperation.get("campaign") or ""),
                "contact_date": str(cooperation.get("contact_date") or ""),
                "reason": "missing_result",
            })
        return {
            "expired_creators": health["expired_creators"],
            "pending_contact": pending_contact,
            "incomplete_cooperations": incomplete_cooperations,
        }

    @staticmethod
    def _status_count(creators: list[dict[str, Any]], status: str) -> int:
        return sum(1 for creator in creators if str(creator.get("status") or "") == status)

    @staticmethod
    def _creator_summary(creator: dict[str, Any], *, change: dict[str, Any] | None = None, freshness: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "creator_id": str(creator.get("creator_id") or creator.get("analysis_id") or ""),
            "creator_name": str(creator.get("creator_name") or ""),
            "platform": str(creator.get("platform") or ""),
            "profile_url": str(creator.get("profile_url") or ""),
            "last_analysis_time": str(creator.get("last_analysis_time") or ""),
            "status": str(creator.get("status") or ""),
            **({"change": change} if change else {}),
            **({"freshness": freshness} if freshness else {}),
        }

    @staticmethod
    def _primary_performance_change(trend: dict[str, Any]) -> dict[str, Any] | None:
        changes = trend.get("changes") if isinstance(trend.get("changes"), dict) else {}
        for metric in ("median_views", "followers"):
            change = changes.get(metric) if isinstance(changes.get(metric), dict) else {}
            if change.get("status") == "available" and change.get("direction") in {"growth", "decline"}:
                return {"metric": metric, **change}
        return None

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value.replace(",", "").strip())
            except ValueError:
                return None
        return None

    @classmethod
    def _sum_numbers(cls, rows: list[dict[str, Any]], field: str) -> float:
        return sum(value for row in rows if (value := cls._number(row.get(field))) is not None)

    @classmethod
    def _average_numbers(cls, rows: list[dict[str, Any]], field: str) -> float:
        values = [value for row in rows if (value := cls._number(row.get(field))) is not None]
        return sum(values) / len(values) if values else 0

    @staticmethod
    def _is_on_or_after(value: object, cutoff: datetime) -> bool:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed >= cutoff
        except ValueError:
            return False
