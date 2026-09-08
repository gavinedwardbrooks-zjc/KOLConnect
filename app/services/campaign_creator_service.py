"""Focused CampaignCreator workflows shared by HTTP handlers."""

from collections.abc import Callable
from typing import Any

from campaign_creator_repository import CampaignCreatorRepository
from domain.creator_url_resolver import CreatorURLResolver


CampaignCreatorRepositoryProvider = Callable[[], CampaignCreatorRepository]
CreatorRepositoryProvider = Callable[[], Any]
CacheInvalidator = Callable[[], None]


class CampaignCreatorService:
    """Own batch relation semantics without adding a second relation model."""

    def __init__(
        self,
        get_campaign_creator_repository: CampaignCreatorRepositoryProvider,
        invalidate_dashboard_response_cache: CacheInvalidator,
        get_creator_repository: CreatorRepositoryProvider | None = None,
    ) -> None:
        self._get_campaign_creator_repository = get_campaign_creator_repository
        self._invalidate_dashboard_response_cache = invalidate_dashboard_response_cache
        self._get_creator_repository = get_creator_repository

    def create_campaign_creator(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Campaign 达人数据无效。")
        creator_id = str(payload.get("creator_id") or "").strip()
        prepared = self._prepare_publications(creator_id, payload)
        return self._get_campaign_creator_repository().createCampaignCreator(prepared)

    def update_campaign_creator(self, record_id: object, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Campaign 达人数据无效。")
        repository = self._get_campaign_creator_repository()
        relation = repository.getCampaignCreator(str(record_id or ""))
        prepared = self._prepare_publications(
            str(relation.get("creator_id") or ""), payload
        )
        return repository.updateCampaignCreator(str(record_id or ""), prepared)

    def list_publications(self, record_id: object) -> list[dict[str, object]]:
        relation = self._get_campaign_creator_repository().getCampaignCreator(
            str(record_id or "")
        )
        return [dict(item) for item in relation.get("publications", []) if isinstance(item, dict)]

    def add_publication(self, record_id: object, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("实际发布内容记录无效。")
        repository = self._get_campaign_creator_repository()
        relation = repository.getCampaignCreator(str(record_id or ""))
        existing = [dict(item) for item in relation.get("publications", []) if isinstance(item, dict)]
        return self.update_campaign_creator(
            record_id, {"publications": [*existing, dict(payload, source=payload.get("source") or "manual")]}
        )

    def delete_publication(self, record_id: object, publication_id: object) -> dict[str, object]:
        normalized_publication_id = str(publication_id or "").strip()
        if not normalized_publication_id:
            raise ValueError("实际发布内容 ID 不能为空。")
        repository = self._get_campaign_creator_repository()
        relation = repository.getCampaignCreator(str(record_id or ""))
        existing = [dict(item) for item in relation.get("publications", []) if isinstance(item, dict)]
        remaining = [
            item for item in existing
            if str(item.get("publication_id") or "") != normalized_publication_id
        ]
        if len(remaining) == len(existing):
            raise ValueError("实际发布内容不存在。")
        self.update_campaign_creator(record_id, {"publications": remaining})
        return {"campaign_creator_id": str(record_id or ""), "publication_id": normalized_publication_id, "deleted": True}

    def _prepare_publications(
        self, creator_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        if "publications" not in payload:
            return dict(payload)
        if not isinstance(payload["publications"], list):
            raise ValueError("实际发布内容必须为列表。")
        if self._get_creator_repository is None:
            raise RuntimeError("实际发布内容解析服务未配置。")

        accounts = list(self._get_creator_repository().getCreatorAccounts())
        accounts_by_uid = {
            str(item.get("account_uid") or ""): dict(item)
            for item in accounts
            if str(item.get("account_uid") or "").strip()
        }
        resolver = CreatorURLResolver(lambda: accounts)
        records: list[dict[str, object]] = []
        for item in payload["publications"]:
            if not isinstance(item, dict):
                raise ValueError("实际发布内容记录无效。")
            record = dict(item)
            result = resolver.resolve(record.get("actual_publish_url") or record.get("publish_url"))
            if result.get("input_type") == "content" and result.get("canonical_url"):
                record["actual_publish_url"] = str(result["canonical_url"])
                record["platform"] = str(result.get("platform") or "")
                record["video_id"] = str(result.get("video_id") or "")
            elif not record.get("publication_id") and str(record.get("source") or "manual") == "manual" and result.get("platform"):
                raise ValueError("实际发布链接必须是受支持的平台内容链接。")

            resolved_account_uid = str(result.get("account_uid") or "").strip()
            if resolved_account_uid:
                account = accounts_by_uid.get(resolved_account_uid)
                if not account or str(account.get("creator_id") or "") != creator_id:
                    raise ValueError("实际发布账号与合作达人不一致。")
                if not str(record.get("actual_account_id") or "").strip():
                    record["actual_account_id"] = str(account.get("account_id") or "")
            records.append(record)
        return {**payload, "publications": records}

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
