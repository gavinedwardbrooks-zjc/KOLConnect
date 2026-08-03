from __future__ import annotations

"""Read-only dashboard data access built on top of local repositories."""

from typing import Any

from campaign_creator_repository import CampaignCreatorRepository
from campaign_repository import CampaignRepository
from creator_repository import CreatorRepository


class DashboardRepository:
    """Collect Dashboard source records without exposing workbook access to callers."""

    def __init__(
        self,
        creator_repository: CreatorRepository,
        campaign_creator_repository: CampaignCreatorRepository | None = None,
        campaign_repository: CampaignRepository | None = None,
    ) -> None:
        self._creator_repository = creator_repository
        workbook_path = creator_repository.workbook_path
        self._campaign_creator_repository = (
            campaign_creator_repository or CampaignCreatorRepository(workbook_path)
        )
        self._campaign_repository = campaign_repository or CampaignRepository(workbook_path)
        self._creators: list[dict[str, Any]] | None = None
        self._campaign_creators: list[dict[str, Any]] | None = None
        self._campaigns: list[dict[str, Any]] | None = None

    def get_creators(self) -> list[dict[str, Any]]:
        if self._creators is None:
            self._creators = self._creator_repository.getCreators()
        return self._creators

    def get_creator_health_records(self) -> list[dict[str, Any]]:
        """Creator records already include the latest snapshot trend and freshness."""
        return self.get_creators()

    def get_campaign_creator_records(
        self,
        creators: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return active CampaignCreator rows enriched for Dashboard rendering."""
        creators = creators if creators is not None else self.get_creators()
        if self._campaign_creators is None:
            self._campaign_creators = self._campaign_creator_repository.getCampaignCreators(
                include_archived=False
            )
        if self._campaigns is None:
            self._campaigns = self._campaign_repository.getCampaigns(include_archived=True)
        creators_by_id = {
            str(creator.get("creator_id") or creator.get("analysis_id") or ""): creator
            for creator in creators
        }
        campaigns_by_id = {
            str(campaign.get("campaign_id") or ""): campaign
            for campaign in self._campaigns
            if str(campaign.get("campaign_id") or "")
        }
        records: list[dict[str, Any]] = []
        for relation in self._campaign_creators:
            creator_id = str(relation.get("creator_id") or "").strip()
            campaign_id = str(relation.get("campaign_id") or "").strip()
            if not creator_id or not campaign_id:
                continue
            creator = creators_by_id.get(creator_id, {})
            campaign = campaigns_by_id.get(campaign_id, {})
            platform = str(
                relation.get("account_platform")
                or relation.get("creator_platform")
                or creator.get("platform")
                or ""
            )
            records.append({
                **relation,
                "creator_id": creator_id,
                "creator_name": str(
                    relation.get("creator_name")
                    or creator.get("creator_name")
                    or creator.get("name")
                    or ""
                ),
                "creator_platform": platform,
                "platform": platform,
                "profile_url": str(
                    relation.get("account_url") or creator.get("profile_url") or ""
                ),
                "campaign_id": campaign_id,
                "campaign": str(campaign.get("name") or ""),
                "campaign_name": str(campaign.get("name") or ""),
                "campaign_archived_at": (
                    str(campaign.get("archived_at") or "").strip() or None
                ),
            })
        return records

    def get_cooperation_records(
        self,
        creators: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Compatibility alias; Dashboard cooperation data now comes from CampaignCreator."""
        return self.get_campaign_creator_records(creators)
