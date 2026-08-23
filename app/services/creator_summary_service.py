from __future__ import annotations

"""Deterministic, read-only Creator summary generation."""

import math
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol


class CreatorSummaryReader(Protocol):
    def getCreatorSummarySourceData(self, creator_id: str) -> dict[str, Any]: ...


RepositoryProvider = Callable[[], CreatorSummaryReader]


class CreatorSummaryService:
    """Build factual local summaries without AI providers or persistence."""

    _TIMESTAMPED_METRICS = (
        "average_views",
        "median_views",
        "video_count",
        "creator_score",
    )

    def __init__(
        self,
        repository_provider: RepositoryProvider,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository_provider = repository_provider
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def get_creator_summary(self, creator_id: str) -> dict[str, Any]:
        source_data = self._repository_provider().getCreatorSummarySourceData(
            str(creator_id or "").strip()
        )
        creator = source_data.get("creator") if isinstance(source_data.get("creator"), dict) else {}
        insight = source_data.get("insight") if isinstance(source_data.get("insight"), dict) else {}
        snapshots = source_data.get("snapshots") if isinstance(source_data.get("snapshots"), list) else []
        snapshots = sorted(
            (row for row in snapshots if isinstance(row, dict)),
            key=lambda row: str(row.get("captured_at") or ""),
            reverse=True,
        )

        performance = {
            "average_views": self._snapshot_measurement(snapshots, "average_views"),
            "median_views": self._snapshot_measurement(snapshots, "median_views"),
            "video_count": self._snapshot_measurement(snapshots, "video_count", integer=True),
            "creator_score": self._snapshot_measurement(snapshots, "creator_score", allow_zero=True),
        }
        for field in ("average_views", "median_views"):
            if performance[field] is None:
                performance[field] = self._insight_measurement(insight, field)
        performance["stability"] = self._insight_measurement(insight, "stability", allow_zero=True)

        insight_level = self._insight_level(snapshots, creator)
        profile = {
            "creator_id": str(creator.get("creator_id") or ""),
            "name": str(creator.get("name") or ""),
            "platform": str(creator.get("platform") or ""),
            "profile_url": str(creator.get("profile_url") or ""),
            "followers": self._stored_value(creator.get("followers")),
            "country": str(creator.get("country") or ""),
            "language": str(creator.get("language") or ""),
            "content_category": str(creator.get("content_category") or ""),
            "bio": str(creator.get("bio") or ""),
            "insight_level": insight_level,
        }
        campaign_creator_count = max(0, int(source_data.get("campaign_creator_count") or 0))
        limitations = self._limitations(profile, performance, campaign_creator_count)
        observations = self._observations(profile, performance, campaign_creator_count)
        core_performance = [performance[field] for field in ("average_views", "median_views", "video_count")]
        data_status = "sufficient" if all(core_performance) else "partial" if any(core_performance) else "insufficient"
        freshness = self._summary_freshness(performance)

        used_sources = ["creators"]
        if any(item and item["source"] == "creator_snapshot" for item in performance.values()):
            used_sources.append("creator_snapshots")
        if any(item and item["source"] == "insights" for item in performance.values()):
            used_sources.append("insights")
        if campaign_creator_count:
            used_sources.append("campaign_creators")

        return {
            "mode": "mock",
            "entity": {
                "type": "creator",
                "id": profile["creator_id"],
                "archived": bool(str(creator.get("archived_at") or "").strip()),
            },
            "data_status": data_status,
            "profile": profile,
            "performance": performance,
            "collaboration": {"recorded_count": campaign_creator_count},
            "observations": observations,
            "limitations": limitations,
            "data_sources": used_sources,
            "freshness": freshness,
        }

    def _snapshot_measurement(
        self,
        snapshots: list[dict[str, Any]],
        field: str,
        *,
        integer: bool = False,
        allow_zero: bool = False,
    ) -> dict[str, Any] | None:
        for snapshot in snapshots:
            number = self._number(snapshot.get(field))
            if number is None or (not allow_zero and number <= 0):
                continue
            if integer and (number <= 0 or not number.is_integer()):
                continue
            captured_at = str(snapshot.get("captured_at") or "").strip()
            return {
                "value": int(number) if integer or number.is_integer() else number,
                "source": "creator_snapshot",
                "measured_at": captured_at or None,
                "freshness": self._freshness(captured_at),
            }
        return None

    def _insight_measurement(
        self,
        insight: dict[str, Any],
        field: str,
        *,
        allow_zero: bool = False,
    ) -> dict[str, Any] | None:
        number = self._number(insight.get(field))
        if number is None or (not allow_zero and number <= 0):
            return None
        return {
            "value": int(number) if number.is_integer() else number,
            "source": "insights",
            "measured_at": None,
            "freshness": "unknown",
        }

    def _freshness(self, captured_at: str) -> str:
        try:
            captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return "unknown"
        now = self._now_provider()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        days = max(0, (now.astimezone(timezone.utc) - captured.astimezone(timezone.utc)).days)
        return "fresh" if days <= 7 else "update_recommended" if days <= 30 else "stale"

    @staticmethod
    def _number(value: object) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            number = float(value)
            return number if math.isfinite(number) and number >= 0 else None
        raw = str(value).strip().lower().replace(",", "")
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb])?", raw)
        if not match:
            return None
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(match.group(2) or "", 1)
        number = float(match.group(1)) * multiplier
        return number if math.isfinite(number) else None

    @staticmethod
    def _stored_value(value: object) -> object:
        return value if value not in (None, "") else ""

    @staticmethod
    def _insight_level(snapshots: list[dict[str, Any]], creator: dict[str, Any]) -> str:
        for snapshot in snapshots:
            value = str(snapshot.get("insight_level") or "").strip()
            if value:
                return value
        return str(creator.get("insight_level") or "").strip() or "insufficient"

    @staticmethod
    def _limitations(
        profile: dict[str, Any],
        performance: dict[str, dict[str, Any] | None],
        campaign_creator_count: int,
    ) -> list[dict[str, str]]:
        limitations: list[dict[str, str]] = []
        for field, message in (
            ("country", "国家/地区信息缺失。"),
            ("language", "语言信息缺失。"),
            ("content_category", "内容类型信息缺失。"),
        ):
            if not str(profile.get(field) or "").strip():
                limitations.append({"code": f"{field.upper()}_MISSING", "category": "metadata", "message": message})
        for field, message in (
            ("average_views", "缺少有效平均播放测量。"),
            ("median_views", "缺少有效中位播放测量。"),
            ("video_count", "缺少有效视频数量测量。"),
            ("creator_score", "缺少有效 Creator Score 测量，无法据此判断质量。"),
        ):
            if performance.get(field) is None:
                limitations.append({"code": f"{field.upper()}_UNAVAILABLE", "category": "performance", "message": message})
        if not any(performance.get(field) for field in ("average_views", "median_views", "video_count", "creator_score", "stability")):
            limitations.append({"code": "PERFORMANCE_DATA_INSUFFICIENT", "category": "performance", "message": "当前缺少可用于表现分析的数据。"})
        if campaign_creator_count == 0:
            limitations.append({"code": "NO_RECORDED_COLLABORATION", "category": "collaboration", "message": "暂无 CampaignCreator 合作历史记录。"})
        if profile.get("insight_level") == "insufficient":
            limitations.append({"code": "INSIGHT_DATA_INSUFFICIENT", "category": "performance", "message": "Insight 状态表示数据不足，不代表 Creator 质量。"})
        return limitations

    @staticmethod
    def _observations(
        profile: dict[str, Any],
        performance: dict[str, dict[str, Any] | None],
        campaign_creator_count: int,
    ) -> list[str]:
        observations: list[str] = []
        for field, label in (
            ("platform", "平台"),
            ("followers", "已存粉丝数"),
            ("country", "国家/地区"),
            ("language", "语言"),
            ("content_category", "内容类型"),
        ):
            value = profile.get(field)
            if value not in (None, ""):
                observations.append(f"{label}：{value}")
        for field, label in (
            ("average_views", "最近有效平均播放"),
            ("median_views", "最近有效中位播放"),
            ("video_count", "最近有效视频数量"),
            ("creator_score", "最近有效 Creator Score"),
        ):
            measurement = performance.get(field)
            if measurement:
                observations.append(f"{label}：{measurement['value']}")
        observations.append(
            f"已记录 CampaignCreator 合作历史：{campaign_creator_count} 条。"
            if campaign_creator_count
            else "暂无 CampaignCreator 合作历史记录。"
        )
        return observations

    @staticmethod
    def _summary_freshness(performance: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
        measurements = {
            field: measurement["freshness"]
            for field, measurement in performance.items()
            if measurement is not None
        }
        statuses = set(measurements.values())
        overall = (
            "stale" if "stale" in statuses
            else "update_recommended" if "update_recommended" in statuses
            else "fresh" if "fresh" in statuses
            else "unknown"
        )
        return {"status": overall, "measurements": measurements}
