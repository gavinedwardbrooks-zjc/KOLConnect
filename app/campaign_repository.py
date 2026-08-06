from __future__ import annotations

"""Campaign data access for the Product-Campaign model."""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app_logging import log_event
from data_repository_base import ExcelDataRepository, utc_now


CAMPAIGNS_HEADERS = [
    "campaign_id", "product_id", "name", "country", "platform", "start_date",
    "end_date", "owner", "status", "budget", "goal", "note", "created_at",
    "updated_at", "archived_at",
]

CAMPAIGN_STATUSES = {"draft", "sourcing", "running", "completed"}
LEGACY_ARCHIVED_STATUS = "archived"


def migrate_legacy_campaign_archives(workbook) -> tuple[bool, list[dict[str, str]]]:
    """Report invalid statuses and mark legacy archives without guessing business state."""
    sheet = workbook["Campaigns"]
    headers = [str(cell.value or "") for cell in sheet[1]]
    status_column = headers.index("status") + 1
    archived_at_column = headers.index("archived_at") + 1
    campaign_id_column = headers.index("campaign_id") + 1
    name_column = headers.index("name") + 1
    changed = False
    review_required: list[dict[str, str]] = []
    migration_time = utc_now()

    for row_index in range(2, sheet.max_row + 1):
        campaign_id = str(sheet.cell(row_index, campaign_id_column).value or "").strip()
        if not campaign_id:
            continue
        status = str(sheet.cell(row_index, status_column).value or "").strip()
        if status in CAMPAIGN_STATUSES:
            continue
        archived_at = str(sheet.cell(row_index, archived_at_column).value or "").strip()
        if status == LEGACY_ARCHIVED_STATUS and not archived_at:
            archived_at = migration_time
            sheet.cell(row_index, archived_at_column, archived_at)
            changed = True
        review_required.append({
            "campaign_id": campaign_id,
            "name": str(sheet.cell(row_index, name_column).value or ""),
            "status": status,
            "archived_at": archived_at,
            "reason": (
                "legacy_archived_status_requires_business_status_confirmation"
                if status == LEGACY_ARCHIVED_STATUS
                else "invalid_campaign_status_requires_confirmation"
            ),
        })
    return changed, review_required


class CampaignRepository(ExcelDataRepository):
    def __init__(self, workbook_path: Path) -> None:
        super().__init__(workbook_path)

    def _require_product(self, workbook, product_id: object) -> str:
        product_id = self.require_text(product_id, "产品 ID")
        product = self.row_by_key(workbook["Products"], "product_id", product_id)
        if not product:
            raise ValueError("关联的产品不存在。")
        if str(product.get("archived_at") or "").strip():
            raise ValueError("关联的产品已归档。")
        return product_id

    @classmethod
    def _campaign_response_indexes(cls, workbook) -> tuple[dict[str, str], dict[str, int]]:
        product_names = {
            str(product.get("product_id") or ""): str(product.get("name") or "")
            for product in cls.rows(workbook["Products"])
            if str(product.get("product_id") or "")
        }
        creator_counts: dict[str, int] = {}
        for relation in cls.rows(workbook["CampaignCreators"]):
            if str(relation.get("archived_at") or "").strip():
                continue
            campaign_id = str(relation.get("campaign_id") or "")
            if campaign_id:
                creator_counts[campaign_id] = creator_counts.get(campaign_id, 0) + 1
        return product_names, creator_counts

    @staticmethod
    def _campaign_response(
        campaign: dict[str, Any],
        product_names: dict[str, str],
        creator_counts: dict[str, int],
    ) -> dict[str, Any]:
        campaign_id = str(campaign.get("campaign_id") or "")
        product_id = str(campaign.get("product_id") or "")
        return {
            **campaign,
            "archived_at": str(campaign.get("archived_at") or "").strip() or None,
            "product_name": product_names.get(product_id, ""),
            "creators_count": creator_counts.get(campaign_id, 0),
        }

    @staticmethod
    def _warn_missing_products(
        campaigns: list[dict[str, Any]],
        product_names: dict[str, str],
    ) -> None:
        orphaned = [
            (
                str(campaign.get("campaign_id") or "<missing_campaign_id>"),
                str(campaign.get("product_id") or "<missing_product_id>"),
            )
            for campaign in campaigns
            if not str(campaign.get("product_id") or "")
            or str(campaign.get("product_id") or "") not in product_names
        ]
        if not orphaned:
            return
        references = ", ".join(f"{campaign_id}->{product_id}" for campaign_id, product_id in orphaned)
        log_event(
            "CampaignRepository",
            f"Campaign 关联 Product 缺失 | count={len(orphaned)} | references={references}",
            level=logging.WARNING,
        )

    @staticmethod
    def _status(value: object, *, default: str = "draft") -> str:
        status = str(value or default).strip()
        if status not in CAMPAIGN_STATUSES:
            raise ValueError("Campaign 状态无效。")
        return status

    def createCampaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Campaign 数据无效。")
        now = utc_now()
        with self.workbook(write=True) as workbook:
            product_id = self._require_product(workbook, payload.get("product_id"))
            campaign = {
                "campaign_id": f"campaign_{uuid.uuid4().hex[:16]}",
                "product_id": product_id,
                "name": self.require_text(payload.get("name"), "Campaign 名称"),
                "country": str(payload.get("country") or "").strip(),
                "platform": str(payload.get("platform") or "").strip(),
                "start_date": str(payload.get("start_date") or "").strip(),
                "end_date": str(payload.get("end_date") or "").strip(),
                "owner": str(payload.get("owner") or "").strip(),
                "status": self._status(payload.get("status")),
                "budget": self.optional_number(payload.get("budget"), "Campaign 预算"),
                "goal": str(payload.get("goal") or "").strip(),
                "note": str(payload.get("note") or "").strip(),
                "created_at": now,
                "updated_at": now,
                "archived_at": None,
            }
            self.upsert_row(workbook["Campaigns"], "campaign_id", campaign["campaign_id"], campaign)
        return campaign

    def getCampaigns(
        self,
        product_id: str = "",
        status: str = "",
        creator_id: str = "",
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        creator_id = str(creator_id or "").strip()
        with self.workbook() as workbook:
            campaigns = self.rows(workbook["Campaigns"])
            product_names, creator_counts = self._campaign_response_indexes(workbook)
            self._warn_missing_products(campaigns, product_names)
            creator_campaign_ids = {
                str(relation.get("campaign_id") or "")
                for relation in self.rows(workbook["CampaignCreators"])
                if creator_id
                and str(relation.get("creator_id") or "") == creator_id
                and not str(relation.get("archived_at") or "").strip()
            }
        product_id = str(product_id or "").strip()
        if product_id:
            campaigns = [row for row in campaigns if str(row.get("product_id") or "") == product_id]
        status = str(status or "").strip()
        if status:
            status = self._status(status)
            campaigns = [row for row in campaigns if str(row.get("status") or "") == status]
        if creator_id:
            campaigns = [
                row
                for row in campaigns
                if str(row.get("campaign_id") or "") in creator_campaign_ids
            ]
        if not include_archived:
            campaigns = [row for row in campaigns if not str(row.get("archived_at") or "").strip()]
        campaigns.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("campaign_id") or "")), reverse=True)
        return [
            self._campaign_response(campaign, product_names, creator_counts)
            for campaign in campaigns
        ]

    def getCampaign(self, campaign_id: str) -> dict[str, Any]:
        campaign_id = self.require_text(campaign_id, "Campaign ID")
        with self.workbook() as workbook:
            campaign = self.row_by_key(workbook["Campaigns"], "campaign_id", campaign_id)
            product_names, creator_counts = self._campaign_response_indexes(workbook)
        if not campaign:
            raise ValueError("Campaign 不存在。")
        self._warn_missing_products([campaign], product_names)
        return self._campaign_response(campaign, product_names, creator_counts)

    def updateCampaign(self, campaign_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Campaign 数据无效。")
        campaign_id = self.require_text(campaign_id, "Campaign ID")
        with self.workbook(write=True) as workbook:
            existing = self.row_by_key(workbook["Campaigns"], "campaign_id", campaign_id)
            if not existing:
                raise ValueError("Campaign 不存在。")
            product_id = self._require_product(workbook, payload.get("product_id", existing.get("product_id")))
            updated = {**existing, "product_id": product_id, "updated_at": utc_now()}
            text_fields = (
                "country", "platform", "start_date", "end_date", "owner", "status",
                "goal", "note",
            )
            updated["name"] = self.require_text(payload.get("name", existing.get("name")), "Campaign 名称")
            for field in text_fields:
                if field in payload:
                    updated[field] = (
                        self._status(payload.get(field))
                        if field == "status"
                        else str(payload.get(field) or "").strip()
                    )
            if "budget" in payload:
                updated["budget"] = self.optional_number(payload.get("budget"), "Campaign 预算")
            self.upsert_row(workbook["Campaigns"], "campaign_id", campaign_id, updated)
        return {**updated, "archived_at": str(updated.get("archived_at") or "").strip() or None}

    @staticmethod
    def _require_iso_timestamp(value: object) -> str:
        timestamp = str(value or "").strip()
        if not timestamp:
            raise ValueError("归档时间必须是有效的 ISO 时间。")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("归档时间必须是有效的 ISO 时间。") from exc
        if parsed.tzinfo is None:
            raise ValueError("归档时间必须包含时区。")
        return timestamp

    def setCampaignArchivedAt(self, campaign_id: str, archived_at: object) -> dict[str, Any]:
        campaign_id = self.require_text(campaign_id, "Campaign ID")
        archive_requested = archived_at is not None
        archived_at_value = self._require_iso_timestamp(archived_at) if archive_requested else ""
        with self.workbook(write=True) as workbook:
            campaign = self.row_by_key(workbook["Campaigns"], "campaign_id", campaign_id)
            if not campaign:
                raise ValueError("Campaign 不存在。")
            status = str(campaign.get("status") or "").strip()
            if not archive_requested and status not in CAMPAIGN_STATUSES:
                raise ValueError("Campaign 业务状态异常，请先人工确认后再恢复。")
            current_archived_at = str(campaign.get("archived_at") or "").strip()
            if archive_requested and not current_archived_at:
                now = utc_now()
                campaign = {**campaign, "archived_at": archived_at_value, "updated_at": now}
                self.upsert_row(workbook["Campaigns"], "campaign_id", campaign_id, campaign)
            elif not archive_requested and current_archived_at:
                campaign = {**campaign, "archived_at": "", "updated_at": utc_now()}
                self.upsert_row(workbook["Campaigns"], "campaign_id", campaign_id, campaign)
            product_names, creator_counts = self._campaign_response_indexes(workbook)
        return self._campaign_response(campaign, product_names, creator_counts)

    def archiveCampaign(self, campaign_id: str) -> dict[str, Any]:
        return self.setCampaignArchivedAt(campaign_id, utc_now())

    def deleteCampaign(self, campaign_id: str) -> None:
        """Backward-compatible name; Campaign records are archived, never deleted."""
        self.archiveCampaign(campaign_id)

    def delete_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Permanently delete one Campaign and only its relationship rows."""
        campaign_id = self.require_text(campaign_id, "Campaign ID")
        with self.workbook(write=True) as workbook:
            relation_sheet = workbook["CampaignCreators"]
            relation_headers = [str(cell.value or "") for cell in relation_sheet[1]]
            campaign_column = relation_headers.index("campaign_id") + 1
            removed_relations = 0
            for row_index in range(relation_sheet.max_row, 1, -1):
                if str(relation_sheet.cell(row_index, campaign_column).value or "") == campaign_id:
                    relation_sheet.delete_rows(row_index, 1)
                    removed_relations += 1
            deleted = self.delete_row(workbook["Campaigns"], "campaign_id", campaign_id)
        return {
            "campaign_id": campaign_id,
            "deleted": deleted,
            "removed_campaign_creators": removed_relations,
        }
