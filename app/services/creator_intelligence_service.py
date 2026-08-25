from __future__ import annotations

"""Deterministic Creator intelligence built only from recorded local facts."""

from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from domain.normalization import normalize_country, normalize_followers, normalize_number, normalize_tags


class CreatorIntelligenceReader(Protocol):
    def getCreatorIntelligenceSourceData(self, creator_id: str) -> dict[str, Any]: ...


class CreatorIntelligenceService:
    VERSION = "m7.4-v1"

    def __init__(self, repository_provider: Callable[[], CreatorIntelligenceReader], *, now=None) -> None:
        self._repository_provider = repository_provider
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get_creator_intelligence(self, creator_id: str) -> dict[str, Any]:
        source = self._repository_provider().getCreatorIntelligenceSourceData(str(creator_id or "").strip())
        creator = dict(source.get("creator") or {})
        accounts = [self._account_signal(row, source.get("snapshots") or []) for row in source.get("accounts") or []]
        categories = self._categories(creator, source)
        user_tags = normalize_tags(creator.get("tags"))
        ai_tags = self._ai_tags(categories, accounts)
        country = normalize_country(creator.get("country"))
        limitations = self._limitations(creator, accounts, source)
        freshness = self._freshness(creator, accounts)
        confidence = self._confidence(creator, accounts, source)
        price_values = [normalize_number(row.get("creator_quote") or row.get("cost")) for row in source.get("campaign_creators") or []]
        has_price = any(value is not None for value in price_values)
        engagement_available = any(
            normalize_number(snapshot.get("average_views")) is not None
            for snapshot in source.get("snapshots") or []
        )
        summary = self._summary(creator, accounts, categories, engagement_available)
        return {
            "mode": "deterministic",
            "version": self.VERSION,
            "source": "kolconnect_recorded_data",
            "generated_at": self._now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "entity": {"type": "creator", "id": str(creator.get("creator_id") or "")},
            "summary": summary,
            "profile": {
                "creator_id": str(creator.get("creator_id") or ""),
                "name": str(creator.get("name") or ""),
                "country": country,
                "country_recorded": str(creator.get("country") or "") or None,
                "language": str(creator.get("language") or "") or None,
                "content_category": str(creator.get("content_category") or "") or None,
            },
            "user_tags": user_tags,
            "ai_tags": ai_tags,
            "content_categories": categories,
            "audience_signals": {
                "country": country,
                "language": str(creator.get("language") or "") or None,
                "platforms": [row["platform"] for row in accounts if row["platform"]],
                "account_scale": [{"account_uid": row["account_uid"], "follower_band": row["follower_band"]} for row in accounts],
            },
            "content_signals": [{"value": value, "source": "recorded_content_category"} for value in categories],
            "accounts": accounts,
            "follower_band": self._creator_follower_band(accounts),
            "engagement_band": "unavailable" if not engagement_available else "recorded_metrics_available",
            "price_band": "recorded_data_available" if has_price else "unavailable",
            "data_freshness": freshness,
            "limitations": limitations,
            "confidence": confidence,
            "observed_facts": {
                "account_count": len(accounts),
                "campaign_relation_count": len(source.get("campaign_creators") or []),
            },
        }


    @staticmethod
    def _account_signal(account: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        uid = str(account.get("account_uid") or "")
        candidates = [row for row in snapshots if str(row.get("account_uid") or "") == uid]
        candidates.sort(key=lambda row: str(row.get("captured_at") or ""), reverse=True)
        latest = candidates[0] if candidates else {}
        followers = normalize_followers(account.get("followers") or latest.get("followers"))
        return {
            "account_uid": uid,
            "platform": str(account.get("platform") or ""),
            "username": str(account.get("username") or ""),
            "followers": followers,
            "follower_band": CreatorIntelligenceService._follower_band(followers),
            "average_views": normalize_number(latest.get("average_views")),
            "median_views": normalize_number(latest.get("median_views")),
            "measured_at": str(latest.get("captured_at") or account.get("last_scrape_time") or "") or None,
        }

    @staticmethod
    def _categories(creator: dict[str, Any], source: dict[str, Any]) -> list[str]:
        values = [str(creator.get("content_category") or "").strip()]
        values.extend(str(item.get("content_category") or "").strip() for item in source.get("videos") or [])
        return normalize_tags([value for value in values if value])

    @staticmethod
    def _ai_tags(categories: list[str], accounts: list[dict[str, Any]]) -> list[str]:
        # These are transparent deterministic labels, not persisted user tags.
        tags = [f"category:{item}" for item in categories]
        tags.extend(f"platform:{row['platform']}" for row in accounts if row["platform"])
        return normalize_tags(tags)

    @staticmethod
    def _follower_band(value: int | None) -> str:
        if value is None:
            return "unavailable"
        limits = ((10_000, "<10K"), (50_000, "10K-50K"), (100_000, "50K-100K"), (500_000, "100K-500K"), (1_000_000, "500K-1M"), (5_000_000, "1M-5M"))
        return next((label for limit, label in limits if value < limit), "5M+")

    @staticmethod
    def _creator_follower_band(accounts: list[dict[str, Any]]) -> str:
        bands = {row["follower_band"] for row in accounts if row["follower_band"] != "unavailable"}
        return next(iter(bands)) if len(bands) == 1 else "multi_account" if bands else "unavailable"

    @staticmethod
    def _limitations(creator: dict[str, Any], accounts: list[dict[str, Any]], source: dict[str, Any]) -> list[str]:
        items = []
        if not any(row["followers"] is not None for row in accounts): items.append("missing_followers")
        if normalize_country(creator.get("country")) is None: items.append("missing_country")
        if not str(creator.get("language") or "").strip(): items.append("missing_language")
        if not source.get("videos"): items.append("no_video_history")
        if not any(normalize_number(row.get("average_views")) is not None for row in source.get("snapshots") or []): items.append("insufficient_engagement_data")
        if not any(normalize_number(row.get("creator_quote") or row.get("cost")) is not None for row in source.get("campaign_creators") or []): items.append("insufficient_price_data")
        return items

    def _freshness(self, creator: dict[str, Any], accounts: list[dict[str, Any]]) -> str:
        timestamps = [str(row.get("measured_at") or "") for row in accounts if row.get("measured_at")]
        timestamps.append(str(creator.get("updated_at") or ""))
        parsed = []
        for value in timestamps:
            try: parsed.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except (TypeError, ValueError): pass
        if not parsed: return "unknown"
        latest = max(item if item.tzinfo else item.replace(tzinfo=timezone.utc) for item in parsed)
        days = max(0, (self._now().astimezone(timezone.utc) - latest.astimezone(timezone.utc)).days)
        return "fresh" if days <= 7 else "aging" if days <= 30 else "stale"

    @staticmethod
    def _confidence(creator: dict[str, Any], accounts: list[dict[str, Any]], source: dict[str, Any]) -> str:
        evidence = sum((bool(accounts), any(row["followers"] is not None for row in accounts), bool(normalize_country(creator.get("country"))), bool(str(creator.get("content_category") or "").strip()), bool(source.get("snapshots"))))
        return "high" if evidence >= 5 else "medium" if evidence >= 3 else "low" if evidence >= 1 else "insufficient"

    @staticmethod
    def _summary(creator: dict[str, Any], accounts: list[dict[str, Any]], categories: list[str], engagement: bool) -> str:
        name = str(creator.get("name") or "该达人")
        facts = [f"{name} 当前记录了 {len(accounts)} 个平台账号。"]
        for account in accounts:
            follower_text = str(account["followers"]) if account["followers"] is not None else "粉丝数据缺失"
            facts.append(f"{account['platform'] or '未知平台'}账号粉丝记录为 {follower_text}。")
        if categories: facts.append(f"当前内容元数据为 {', '.join(categories)}。")
        if not engagement: facts.append("可靠互动数据不足，因此不提供互动评级。")
        return "".join(facts)


class CreatorIntelligenceSummaryFacade:
    """Preserve the M6.2 response while adding the M7.4 model."""

    def __init__(self, summary_service: Any, intelligence_service: CreatorIntelligenceService) -> None:
        self.summary_service = summary_service
        self.intelligence_service = intelligence_service

    def get_creator_summary(self, creator_id: str) -> dict[str, Any]:
        summary = self.summary_service.get_creator_summary(creator_id)
        intelligence = self.intelligence_service.get_creator_intelligence(creator_id)
        return {**summary, "intelligence": intelligence}
