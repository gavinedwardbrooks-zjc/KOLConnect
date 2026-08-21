from __future__ import annotations

"""Read-only KPI calculations for the KOLConnect operational dashboard."""

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard_repository import DashboardRepository


class DashboardService:
    """Build dashboard responses from repository records, never from Excel directly."""

    _COOPERATION_STAGES = {"agreed", "executing", "completed"}
    _EXECUTING_STAGES = {"agreed", "executing"}

    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    def getOverview(self) -> dict[str, Any]:
        creators = self._repository.get_creators()
        relations = self._repository.get_campaign_creator_records(creators)
        cooperation_records = self._records_in_stages(relations, self._COOPERATION_STAGES)
        operational_records = [record for record in relations if self._is_operational(record)]
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return {
            "total_creators": len(creators),
            "new_creators_7d": sum(1 for creator in creators if self._is_on_or_after(creator.get("analysis_time"), recent_cutoff)),
            "discovered_count": self._stage_count(operational_records, {"pending_contact"}),
            "cooperating_count": self._stage_count(operational_records, self._EXECUTING_STAGES),
            "cooperation_spend": self._sum_valid_numbers(cooperation_records, "cost"),
            "average_roi": self._weighted_completed_roi(relations),
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
        relations = self._repository.get_campaign_creator_records(creators)
        cooperation_records = self._records_in_stages(relations, self._COOPERATION_STAGES)
        completed_records = self._records_in_stages(relations, {"completed"})
        totals_by_creator: dict[str, dict[str, Any]] = {}
        for relation in completed_records:
            creator_id = str(relation.get("creator_id") or "")
            if not creator_id:
                continue
            aggregate = totals_by_creator.setdefault(creator_id, {
                "creator_id": creator_id,
                "creator_name": str(relation.get("creator_name") or ""),
                "platform": str(relation.get("platform") or ""),
                "profile_url": str(relation.get("profile_url") or ""),
                "campaign_count": 0,
                "total_cost": 0.0,
                "total_views": 0.0,
                "roi_cost_total": 0.0,
                "roi_weighted_total": 0.0,
            })
            aggregate["campaign_count"] += 1
            cost = self._nonnegative_number(relation.get("cost"))
            views = self._nonnegative_number(relation.get("views"))
            aggregate["total_cost"] += cost or 0.0
            aggregate["total_views"] += views or 0.0
            roi = self._nonnegative_number(relation.get("roi"))
            if cost is not None and cost > 0 and roi is not None:
                aggregate["roi_cost_total"] += cost
                aggregate["roi_weighted_total"] += cost * roi

        top_creators = []
        for aggregate in totals_by_creator.values():
            roi_cost_total = aggregate.pop("roi_cost_total")
            roi_weighted_total = aggregate.pop("roi_weighted_total")
            aggregate["average_roi"] = (
                roi_weighted_total / roi_cost_total if roi_cost_total > 0 else None
            )
            top_creators.append(aggregate)
        top_creators.sort(
            key=lambda item: (
                -item["total_views"],
                0 if item["average_roi"] is not None else 1,
                -(item["average_roi"] or 0),
                -item["campaign_count"],
                item["creator_id"],
            )
        )

        return {
            "total_campaigns": len({
                str(record.get("campaign_id") or "")
                for record in relations
                if str(record.get("campaign_id") or "")
            }),
            "total_cost": self._sum_valid_numbers(cooperation_records, "cost"),
            "total_views": self._sum_valid_numbers(cooperation_records, "views"),
            "average_roi": self._weighted_completed_roi(relations),
            "top_creators": top_creators[:5],
        }

    def getActionItems(self) -> dict[str, list[dict[str, Any]]]:
        creators = self._repository.get_creators()
        health = self.getCreatorHealth()
        relations = self._repository.get_campaign_creator_records(creators)
        operational_records = [record for record in relations if self._is_operational(record)]
        pending_contact = [
            self._campaign_creator_summary(record)
            for record in operational_records
            if str(record.get("stage") or "") == "pending_contact"
        ]
        incomplete_cooperations = []
        for relation in operational_records:
            if str(relation.get("stage") or "") != "completed":
                continue
            if str(relation.get("performance_note") or "").strip():
                continue
            incomplete_cooperations.append({
                "cooperation_id": str(relation.get("id") or ""),
                "creator_id": str(relation.get("creator_id") or ""),
                "creator_name": str(relation.get("creator_name") or ""),
                "platform": str(relation.get("platform") or ""),
                "campaign": str(relation.get("campaign") or ""),
                "contact_date": str(
                    relation.get("publish_date") or relation.get("created_at") or ""
                ),
                "reason": "missing_performance_note",
            })
        return {
            "expired_creators": health["expired_creators"],
            "pending_contact": pending_contact,
            "incomplete_cooperations": incomplete_cooperations,
        }

    def getPlatformDistribution(self) -> list[dict[str, Any]]:
        """Return active Creator counts grouped by their stored platform value."""
        return self._distribution(self._repository.get_creators(), "platform")

    def getCreatorStatusDistribution(self) -> list[dict[str, Any]]:
        """Return active Creator counts grouped by the existing status field."""
        return self._distribution(self._repository.get_creators(), "status")

    def getCreatorGrowthTrend(self) -> list[dict[str, Any]]:
        """Return a zero-filled UTC calendar-day series for recent Creator additions."""
        today = datetime.now(timezone.utc).date()
        dates = [today - timedelta(days=offset) for offset in range(29, -1, -1)]
        counts = {day: 0 for day in dates}
        for creator in self._repository.get_creators():
            created_at = self._parse_datetime(creator.get("created_at"))
            if created_at is not None and created_at.date() in counts:
                counts[created_at.date()] += 1
        return [
            {"date": day.isoformat(), "count": counts[day]}
            for day in dates
        ]

    @staticmethod
    def _status_count(creators: list[dict[str, Any]], status: str) -> int:
        return sum(1 for creator in creators if str(creator.get("status") or "") == status)

    @staticmethod
    def _distribution(
        creators: list[dict[str, Any]],
        field: str,
    ) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for creator in creators:
            value = str(creator.get(field) or "").strip() or "Other/Unknown"
            counts[value] = counts.get(value, 0) + 1
        return [
            {field: value, "count": count}
            for value, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0].casefold()),
            )
        ]

    @classmethod
    def _records_in_stages(
        cls,
        records: list[dict[str, Any]],
        stages: set[str],
    ) -> list[dict[str, Any]]:
        return [
            record
            for record in records
            if not str(record.get("archived_at") or "").strip()
            and str(record.get("stage") or "") in stages
        ]

    @classmethod
    def _stage_count(cls, records: list[dict[str, Any]], stages: set[str]) -> int:
        return len(cls._records_in_stages(records, stages))

    @staticmethod
    def _is_operational(record: dict[str, Any]) -> bool:
        return (
            not str(record.get("archived_at") or "").strip()
            and not str(record.get("campaign_archived_at") or "").strip()
        )

    @staticmethod
    def _campaign_creator_summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "creator_id": str(record.get("creator_id") or ""),
            "creator_name": str(record.get("creator_name") or ""),
            "platform": str(record.get("platform") or ""),
            "profile_url": str(record.get("profile_url") or ""),
            "status": str(record.get("stage") or ""),
            "campaign_id": str(record.get("campaign_id") or ""),
            "campaign": str(record.get("campaign") or ""),
        }

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
            number = float(value)
            return number if math.isfinite(number) else None
        if isinstance(value, str) and value.strip():
            try:
                number = float(value.replace(",", "").strip())
                return number if math.isfinite(number) else None
            except ValueError:
                return None
        return None

    @classmethod
    def _nonnegative_number(cls, value: object) -> float | None:
        number = cls._number(value)
        return number if number is not None and number >= 0 else None

    @classmethod
    def _sum_valid_numbers(cls, rows: list[dict[str, Any]], field: str) -> float:
        return sum(
            value
            for row in rows
            if (value := cls._nonnegative_number(row.get(field))) is not None
        )

    @classmethod
    def _weighted_completed_roi(cls, rows: list[dict[str, Any]]) -> float:
        total_cost = 0.0
        weighted_roi = 0.0
        for row in rows:
            if str(row.get("archived_at") or "").strip():
                continue
            if str(row.get("stage") or "") != "completed":
                continue
            cost = cls._nonnegative_number(row.get("cost"))
            roi = cls._nonnegative_number(row.get("roi"))
            if cost is None or cost <= 0 or roi is None:
                continue
            total_cost += cost
            weighted_roi += cost * roi
        return weighted_roi / total_cost if total_cost > 0 else 0

    @classmethod
    def _sum_numbers(cls, rows: list[dict[str, Any]], field: str) -> float:
        return sum(value for row in rows if (value := cls._number(row.get(field))) is not None)

    @classmethod
    def _average_numbers(cls, rows: list[dict[str, Any]], field: str) -> float:
        values = [value for row in rows if (value := cls._number(row.get(field))) is not None]
        return sum(values) / len(values) if values else 0

    @staticmethod
    def _is_on_or_after(value: object, cutoff: datetime) -> bool:
        parsed = DashboardService._parse_datetime(value)
        return parsed is not None and parsed >= cutoff

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
