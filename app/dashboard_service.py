from __future__ import annotations

"""Read-only KPI calculations for the KOLConnect operational dashboard."""

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard_repository import DashboardRepository
from domain.money import grouped_amounts


class DashboardService:
    """Build dashboard responses from repository records, never from Excel directly."""

    _COOPERATION_STAGES = {"agreed", "executing", "completed"}
    _EXECUTING_STAGES = {"agreed", "executing"}
    _ACTION_ITEMS_PER_CATEGORY_LIMIT = 5

    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    def getOverview(self) -> dict[str, Any]:
        creators = self._repository.get_creators()
        relations = self._repository.get_campaign_creator_records(creators)
        cooperation_records = self._records_in_stages(relations, self._COOPERATION_STAGES)
        operational_records = [record for record in relations if self._is_operational(record)]
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        spend = grouped_amounts(cooperation_records, "cost", "cost_currency")
        return {
            "total_creators": len(creators),
            "new_creators_7d": sum(1 for creator in creators if self._is_on_or_after(creator.get("analysis_time"), recent_cutoff)),
            "discovered_count": self._stage_count(operational_records, {"pending_contact"}),
            "cooperating_count": self._stage_count(operational_records, self._EXECUTING_STAGES),
            "cooperation_spend": spend["total"],
            "cooperation_spend_by_currency": spend["totals_by_currency"],
            "cooperation_spend_unknown_currency": spend["unknown_currency_total"],
            "cooperation_spend_multiple_currencies": spend["multiple_currencies"],
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

    def getHealthSummary(self) -> dict[str, int | None]:
        """Summarize active Creator health without inventing new health states."""
        active_creator_ids = {
            str(creator.get("creator_id") or creator.get("analysis_id") or "").strip()
            for creator in self._repository.get_creators()
            if str(creator.get("creator_id") or creator.get("analysis_id") or "").strip()
        }
        health = self.getCreatorHealth()
        expired_creator_ids = {
            str(record.get("creator_id") or "").strip()
            for record in health["expired_creators"]
            if str(record.get("creator_id") or "").strip() in active_creator_ids
        }
        falling_creator_ids = {
            str(record.get("creator_id") or "").strip()
            for record in health["falling_creators"]
            if str(record.get("creator_id") or "").strip() in active_creator_ids
        }
        # Expired is the stricter state, so overlap is counted as critical only.
        critical = len(expired_creator_ids)
        warning = len(falling_creator_ids - expired_creator_ids)
        total = len(active_creator_ids)
        healthy = max(0, total - critical - warning)
        return {
            "score": round(healthy / total * 100) if total else None,
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
            "total": total,
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
                "cost_records": [],
                "total_views": 0.0,
                "roi_records": [],
            })
            aggregate["campaign_count"] += 1
            cost = self._nonnegative_number(relation.get("cost"))
            views = self._nonnegative_number(relation.get("views"))
            if cost is not None:
                aggregate["cost_records"].append(relation)
            aggregate["total_views"] += views or 0.0
            roi = self._nonnegative_number(relation.get("roi"))
            if cost is not None and cost > 0 and roi is not None:
                aggregate["roi_records"].append(relation)

        top_creators = []
        for aggregate in totals_by_creator.values():
            cost_summary = grouped_amounts(
                aggregate.pop("cost_records"), "cost", "cost_currency"
            )
            aggregate["total_cost"] = cost_summary["total"]
            aggregate["cost_totals_by_currency"] = cost_summary["totals_by_currency"]
            aggregate["cost_unknown_currency_total"] = cost_summary["unknown_currency_total"]
            aggregate["cost_multiple_currencies"] = cost_summary["multiple_currencies"]
            aggregate["average_roi"] = self._weighted_completed_roi(
                aggregate.pop("roi_records")
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

        cost_summary = grouped_amounts(cooperation_records, "cost", "cost_currency")
        return {
            "total_campaigns": len({
                str(record.get("campaign_id") or "")
                for record in relations
                if str(record.get("campaign_id") or "")
            }),
            "total_cost": cost_summary["total"],
            "cost_totals_by_currency": cost_summary["totals_by_currency"],
            "cost_unknown_currency_total": cost_summary["unknown_currency_total"],
            "cost_multiple_currencies": cost_summary["multiple_currencies"],
            "total_views": self._sum_valid_numbers(cooperation_records, "views"),
            "average_roi": self._weighted_completed_roi(relations),
            "top_creators": top_creators[:5],
        }

    def getActionItems(self) -> dict[str, list[dict[str, Any]]]:
        creators = self._repository.get_creators()
        health = self.getCreatorHealth()
        relations = self._repository.get_campaign_creator_records(creators)
        active_creator_ids = {
            str(creator.get("creator_id") or creator.get("analysis_id") or "")
            for creator in creators
            if not str(creator.get("archived_at") or "").strip()
        }
        operational_records = [
            record
            for record in relations
            if self._is_operational(record)
            and str(record.get("creator_id") or "") in active_creator_ids
        ]
        expired_creators = [
            record
            for record in health["expired_creators"]
            if str(record.get("creator_id") or "") in active_creator_ids
        ]
        expired_creators.sort(
            key=lambda record: (
                -self._freshness_days(record),
                self._oldest_first_timestamp(record.get("last_analysis_time")),
                str(record.get("creator_id") or ""),
            )
        )
        pending_records = [
            record
            for record in operational_records
            if str(record.get("stage") or "") == "pending_contact"
        ]
        pending_records.sort(
            key=lambda record: (
                self._oldest_first_timestamp(record.get("created_at")),
                str(record.get("id") or ""),
            )
        )
        pending_contact = [
            self._campaign_creator_summary(record)
            for record in pending_records[: self._ACTION_ITEMS_PER_CATEGORY_LIMIT]
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
                "campaign_id": str(relation.get("campaign_id") or ""),
                "contact_date": str(
                    relation.get("publish_date") or relation.get("created_at") or ""
                ),
                "reason": "missing_performance_note",
            })
        incomplete_cooperations.sort(
            key=lambda record: (
                self._oldest_first_timestamp(record.get("contact_date")),
                str(record.get("cooperation_id") or ""),
            )
        )
        return {
            "expired_creators": expired_creators[: self._ACTION_ITEMS_PER_CATEGORY_LIMIT],
            "pending_contact": pending_contact,
            "incomplete_cooperations": incomplete_cooperations[
                : self._ACTION_ITEMS_PER_CATEGORY_LIMIT
            ],
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
            "created_at": str(record.get("created_at") or ""),
        }

    @staticmethod
    def _freshness_days(record: dict[str, Any]) -> int:
        freshness = record.get("freshness")
        if not isinstance(freshness, dict):
            return 0
        try:
            return max(0, int(freshness.get("days") or 0))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _oldest_first_timestamp(cls, value: object) -> tuple[int, datetime, str]:
        parsed = cls._parse_datetime(value)
        if parsed is None:
            return (1, datetime.max.replace(tzinfo=timezone.utc), str(value or ""))
        return (0, parsed, "")

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
    def _weighted_completed_roi(cls, rows: list[dict[str, Any]]) -> float | None:
        totals: dict[str, list[float]] = {}
        for row in rows:
            if str(row.get("archived_at") or "").strip():
                continue
            if str(row.get("stage") or "") != "completed":
                continue
            cost = cls._nonnegative_number(row.get("cost"))
            roi = cls._nonnegative_number(row.get("roi"))
            if cost is None or cost <= 0 or roi is None:
                continue
            currency = str(row.get("cost_currency") or "").strip().upper() or "__UNKNOWN__"
            aggregate = totals.setdefault(currency, [0.0, 0.0])
            aggregate[0] += cost
            aggregate[1] += cost * roi
        if not totals:
            return 0
        if len(totals) != 1:
            return None
        total_cost, weighted_roi = next(iter(totals.values()))
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
