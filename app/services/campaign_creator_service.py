"""Focused CampaignCreator workflows shared by HTTP handlers."""

from collections.abc import Callable

from campaign_creator_repository import CampaignCreatorRepository


CampaignCreatorRepositoryProvider = Callable[[], CampaignCreatorRepository]
CacheInvalidator = Callable[[], None]


class CampaignCreatorService:
    """Own batch relation semantics without adding a second relation model."""

    def __init__(
        self,
        get_campaign_creator_repository: CampaignCreatorRepositoryProvider,
        invalidate_dashboard_response_cache: CacheInvalidator,
    ) -> None:
        self._get_campaign_creator_repository = get_campaign_creator_repository
        self._invalidate_dashboard_response_cache = invalidate_dashboard_response_cache

    def batch_add_creators(
        self, campaign_id: object, creator_ids: object
    ) -> dict[str, object]:
        normalized_campaign_id = str(campaign_id or "").strip()
        if not normalized_campaign_id:
            raise ValueError("Campaign ID不能为空。")
        if not isinstance(creator_ids, list):
            raise ValueError("creator_ids必须是数组。")
        if not creator_ids:
            raise ValueError("creator_ids不能为空。")

        unique_ids: list[str] = []
        seen: set[str] = set()
        for creator_id in creator_ids:
            if not isinstance(creator_id, str) or not creator_id.strip():
                raise ValueError("creator_ids包含无效的达人 ID。")
            normalized_creator_id = creator_id.strip()
            if normalized_creator_id not in seen:
                seen.add(normalized_creator_id)
                unique_ids.append(normalized_creator_id)

        results = self._get_campaign_creator_repository().batch_add_creators(
            normalized_campaign_id, unique_ids
        )
        counts = {
            status: sum(item["status"] == status for item in results)
            for status in ("added", "restored", "already_present", "failed")
        }
        if counts["added"] or counts["restored"]:
            self._invalidate_dashboard_response_cache()
        return {
            "campaign_id": normalized_campaign_id,
            "requested": len(unique_ids),
            **counts,
            "results": results,
        }
