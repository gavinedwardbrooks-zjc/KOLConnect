from __future__ import annotations

"""Campaign-Creator relationship data access."""

import uuid
from pathlib import Path
from typing import Any

from data_repository_base import ExcelDataRepository, utc_now


CAMPAIGN_CREATORS_HEADERS = [
    "id", "campaign_id", "creator_id", "account_id", "stage", "owner",
    "creator_quote", "cost", "publish_links", "publish_date", "views", "likes",
    "comments", "roi", "performance_note", "created_at", "updated_at",
    "archived_at",
]

CAMPAIGN_CREATOR_STAGES = {
    "pending_contact", "contacted", "quoted", "negotiating", "agreed",
    "executing", "completed", "rejected",
}
ROI_DEFINITION = "revenue / cost"


class CampaignCreatorRepository(ExcelDataRepository):
    def __init__(self, workbook_path: Path) -> None:
        super().__init__(workbook_path)

    def _validated_relations(
        self,
        workbook,
        campaign_id: object,
        creator_id: object,
        account_id: object,
        *,
        current_id: str = "",
        allow_archived_duplicate: bool = False,
    ) -> tuple[str, str, str]:
        campaign_id = self.require_text(campaign_id, "Campaign ID")
        creator_id = self.require_text(creator_id, "达人 ID")
        account_id = self.require_text(account_id, "达人账号 ID")
        campaign = self.row_by_key(workbook["Campaigns"], "campaign_id", campaign_id)
        if not campaign:
            raise ValueError("关联的 Campaign 不存在。")
        if str(campaign.get("archived_at") or "").strip():
            raise ValueError("关联的 Campaign 已归档。")
        if not self.row_by_key(workbook["Creators"], "creator_id", creator_id):
            raise ValueError("关联的达人不存在。")
        account = self.row_by_key(workbook["CreatorAccounts"], "account_id", account_id)
        if not account:
            raise ValueError("关联的达人账号不存在。")
        if str(account.get("creator_id") or "") != creator_id:
            raise ValueError("达人账号不属于所选达人。")
        for row in self.rows(workbook["CampaignCreators"]):
            if str(row.get("id") or "") == current_id:
                continue
            if (
                str(row.get("campaign_id") or "") == campaign_id
                and str(row.get("creator_id") or "") == creator_id
            ):
                if allow_archived_duplicate and str(row.get("archived_at") or "").strip():
                    continue
                raise ValueError("该达人已加入此 Campaign。")
        return campaign_id, creator_id, account_id

    @staticmethod
    def _stage(value: object, *, default: str = "pending_contact") -> str:
        stage = str(value or default).strip()
        if stage not in CAMPAIGN_CREATOR_STAGES:
            raise ValueError("Campaign 达人合作阶段无效。")
        return stage

    @classmethod
    def _display_indexes(
        cls,
        workbook,
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
    ]:
        creators = {
            str(creator.get("creator_id") or ""): creator
            for creator in cls.rows(workbook["Creators"])
            if str(creator.get("creator_id") or "")
        }
        accounts = {
            str(account.get("account_id") or ""): account
            for account in cls.rows(workbook["CreatorAccounts"])
            if str(account.get("account_id") or "")
        }
        agencies = {
            str(agency.get("agency_id") or ""): agency
            for agency in cls.rows(workbook["Agencies"])
            if str(agency.get("agency_id") or "")
        }
        return creators, accounts, agencies

    @staticmethod
    def _campaign_creator_response(
        record: dict[str, Any],
        creators: dict[str, dict[str, Any]],
        accounts: dict[str, dict[str, Any]],
        agencies: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        creator = creators.get(str(record.get("creator_id") or ""), {})
        account = accounts.get(str(record.get("account_id") or ""), {})
        agency_id = str(creator.get("agency_id") or "").strip()
        agency = agencies.get(agency_id, {})
        return {
            **record,
            "archived_at": str(record.get("archived_at") or "").strip() or None,
            "creator_name": str(creator.get("name") or ""),
            "agency_id": agency_id or None,
            "agency_name": str(agency.get("name") or "").strip() or None,
            "account_platform": str(account.get("platform") or ""),
            "account_url": str(account.get("profile_url") or ""),
        }

    def _values(self, payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
        existing = existing or {}
        values = dict(existing)
        for field in ("stage", "owner", "publish_date", "performance_note"):
            if field in payload or not existing:
                values[field] = (
                    self._stage(payload.get(field, existing.get(field)))
                    if field == "stage"
                    else str(payload.get(field, existing.get(field)) or "").strip()
                )
        for field, label, integer in (
            ("creator_quote", "达人报价", False),
            ("cost", "合作成本", False),
            ("views", "播放量", True),
            ("likes", "点赞数", True),
            ("comments", "评论数", True),
            ("roi", "ROI", False),
        ):
            if field in payload or not existing:
                values[field] = self.optional_number(
                    payload.get(field, existing.get(field)), label, integer=integer
                )
        if "publish_links" in payload or not existing:
            values["publish_links"] = self.publish_links_value(
                payload.get("publish_links", existing.get("publish_links"))
            )
        return values

    def createCampaignCreator(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Campaign 达人数据无效。")
        now = utc_now()
        with self.workbook(write=True) as workbook:
            campaign_id, creator_id, account_id = self._validated_relations(
                workbook,
                payload.get("campaign_id"),
                payload.get("creator_id"),
                payload.get("account_id"),
                allow_archived_duplicate=True,
            )
            archived_record = next(
                (
                    row
                    for row in self.rows(workbook["CampaignCreators"])
                    if str(row.get("campaign_id") or "") == campaign_id
                    and str(row.get("creator_id") or "") == creator_id
                    and str(row.get("archived_at") or "").strip()
                ),
                None,
            )
            record = {
                **self._values(payload, archived_record),
                "id": (
                    str(archived_record.get("id") or "")
                    if archived_record
                    else f"campaign_creator_{uuid.uuid4().hex[:16]}"
                ),
                "campaign_id": campaign_id,
                "creator_id": creator_id,
                "account_id": account_id,
                "created_at": (
                    str(archived_record.get("created_at") or now)
                    if archived_record
                    else now
                ),
                "updated_at": now,
                "archived_at": "",
            }
            self.upsert_row(workbook["CampaignCreators"], "id", record["id"], record)
            creators, accounts, agencies = self._display_indexes(workbook)
        return self._campaign_creator_response(record, creators, accounts, agencies)

    def batch_add_creators(
        self, campaign_id: object, creator_ids: list[str]
    ) -> list[dict[str, str]]:
        """Add creators in one workbook write while preserving relation semantics."""
        campaign_id = self.require_text(campaign_id, "Campaign ID")
        now = utc_now()
        with self.workbook(write=True) as workbook:
            campaign = self.row_by_key(workbook["Campaigns"], "campaign_id", campaign_id)
            if not campaign:
                raise ValueError("关联的 Campaign 不存在。")
            if str(campaign.get("archived_at") or "").strip():
                raise ValueError("关联的 Campaign 已归档。")

            creators = {
                str(row.get("creator_id") or ""): row
                for row in self.rows(workbook["Creators"])
                if str(row.get("creator_id") or "")
            }
            accounts_by_creator: dict[str, list[dict[str, Any]]] = {}
            for account in self.rows(workbook["CreatorAccounts"]):
                creator_id = str(account.get("creator_id") or "")
                if creator_id and str(account.get("account_id") or ""):
                    accounts_by_creator.setdefault(creator_id, []).append(account)
            for accounts in accounts_by_creator.values():
                accounts.sort(
                    key=lambda account: (
                        str(account.get("created_at") or ""),
                        str(account.get("account_id") or ""),
                    )
                )

            relations_by_creator = {
                str(row.get("creator_id") or ""): row
                for row in self.rows(workbook["CampaignCreators"])
                if str(row.get("campaign_id") or "") == campaign_id
                and str(row.get("creator_id") or "")
            }
            campaign_platform = str(campaign.get("platform") or "").strip().casefold()
            results: list[dict[str, str]] = []
            for creator_id in creator_ids:
                creator = creators.get(creator_id)
                if not creator:
                    results.append({
                        "creator_id": creator_id,
                        "status": "failed",
                        "error": "关联的达人不存在。",
                    })
                    continue
                accounts = accounts_by_creator.get(creator_id, [])
                if not accounts:
                    results.append({
                        "creator_id": creator_id,
                        "status": "failed",
                        "error": "该达人暂无可用社交账号。",
                    })
                    continue
                account = next(
                    (
                        item
                        for item in accounts
                        if campaign_platform
                        and str(item.get("platform") or "").strip().casefold()
                        == campaign_platform
                    ),
                    accounts[0],
                )
                existing = relations_by_creator.get(creator_id)
                if existing and not str(existing.get("archived_at") or "").strip():
                    results.append({
                        "creator_id": creator_id,
                        "status": "already_present",
                        "error": "",
                    })
                    continue

                record = {
                    **self._values({}, existing),
                    "id": (
                        str(existing.get("id") or "")
                        if existing
                        else f"campaign_creator_{uuid.uuid4().hex[:16]}"
                    ),
                    "campaign_id": campaign_id,
                    "creator_id": creator_id,
                    "account_id": str(account.get("account_id") or ""),
                    "created_at": (
                        str(existing.get("created_at") or now) if existing else now
                    ),
                    "updated_at": now,
                    "archived_at": "",
                }
                self.upsert_row(workbook["CampaignCreators"], "id", record["id"], record)
                relations_by_creator[creator_id] = record
                results.append({
                    "creator_id": creator_id,
                    "status": "restored" if existing else "added",
                    "error": "",
                })
        return results

    def getCampaignCreators(
        self,
        campaign_id: str = "",
        creator_id: str = "",
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        with self.workbook() as workbook:
            records = self.rows(workbook["CampaignCreators"])
            creators, accounts, agencies = self._display_indexes(workbook)
        if not include_archived:
            records = [row for row in records if not str(row.get("archived_at") or "").strip()]
        campaign_id = str(campaign_id or "").strip()
        creator_id = str(creator_id or "").strip()
        if campaign_id:
            records = [row for row in records if str(row.get("campaign_id") or "") == campaign_id]
        if creator_id:
            records = [row for row in records if str(row.get("creator_id") or "") == creator_id]
        records.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")), reverse=True)
        return [
            self._campaign_creator_response(record, creators, accounts, agencies)
            for record in records
        ]

    def getCampaignCreator(self, record_id: str) -> dict[str, Any]:
        record_id = self.require_text(record_id, "Campaign 达人记录 ID")
        with self.workbook() as workbook:
            record = self.row_by_key(workbook["CampaignCreators"], "id", record_id)
            creators, accounts, agencies = self._display_indexes(workbook)
        if not record:
            raise ValueError("Campaign 达人记录不存在。")
        return self._campaign_creator_response(record, creators, accounts, agencies)

    def updateCampaignCreator(self, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Campaign 达人数据无效。")
        record_id = self.require_text(record_id, "Campaign 达人记录 ID")
        with self.workbook(write=True) as workbook:
            existing = self.row_by_key(workbook["CampaignCreators"], "id", record_id)
            if not existing:
                raise ValueError("Campaign 达人记录不存在。")
            campaign_id, creator_id, account_id = self._validated_relations(
                workbook,
                payload.get("campaign_id", existing.get("campaign_id")),
                payload.get("creator_id", existing.get("creator_id")),
                payload.get("account_id", existing.get("account_id")),
                current_id=record_id,
            )
            updated = {
                **self._values(payload, existing),
                "id": record_id,
                "campaign_id": campaign_id,
                "creator_id": creator_id,
                "account_id": account_id,
                "created_at": existing.get("created_at") or utc_now(),
                "updated_at": utc_now(),
            }
            self.upsert_row(workbook["CampaignCreators"], "id", record_id, updated)
            creators, accounts, agencies = self._display_indexes(workbook)
        return self._campaign_creator_response(updated, creators, accounts, agencies)

    def archiveCampaignCreator(self, record_id: str) -> dict[str, Any]:
        record_id = self.require_text(record_id, "Campaign 达人记录 ID")
        with self.workbook(write=True) as workbook:
            record = self.row_by_key(workbook["CampaignCreators"], "id", record_id)
            if not record:
                raise ValueError("Campaign 达人记录不存在。")
            if not str(record.get("archived_at") or "").strip():
                now = utc_now()
                record = {**record, "archived_at": now, "updated_at": now}
                self.upsert_row(workbook["CampaignCreators"], "id", record_id, record)
            creators, accounts, agencies = self._display_indexes(workbook)
        return self._campaign_creator_response(record, creators, accounts, agencies)

    def deleteCampaignCreator(self, record_id: str) -> None:
        """Backward-compatible name; relationship records are archived, never deleted."""
        self.archiveCampaignCreator(record_id)

    def remove_creator_from_campaign(self, record_id: str) -> dict[str, Any]:
        """Permanently remove only the Campaign-Creator relationship row."""
        record_id = self.require_text(record_id, "Campaign 达人记录 ID")
        with self.workbook(write=True) as workbook:
            existing = self.row_by_key(workbook["CampaignCreators"], "id", record_id)
            deleted = self.delete_row(workbook["CampaignCreators"], "id", record_id)
        return {
            "campaign_creator_id": record_id,
            "campaign_id": str(existing.get("campaign_id") or ""),
            "creator_id": str(existing.get("creator_id") or ""),
            "deleted": deleted,
        }
