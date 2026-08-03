from __future__ import annotations

"""Product data access for the Product-Campaign model."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from data_repository_base import ExcelDataRepository, utc_now


PRODUCTS_HEADERS = [
    "product_id", "name", "company_name", "note", "created_at", "updated_at",
    "archived_at",
]


class ProductRepository(ExcelDataRepository):
    def __init__(self, workbook_path: Path) -> None:
        super().__init__(workbook_path)

    def createProduct(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("产品数据无效。")
        now = utc_now()
        product = {
            "product_id": f"product_{uuid.uuid4().hex[:16]}",
            "name": self.require_text(payload.get("name"), "产品名称"),
            "company_name": str(payload.get("company_name") or "").strip(),
            "note": str(payload.get("note") or "").strip(),
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
        }
        with self.workbook(write=True) as workbook:
            self.upsert_row(workbook["Products"], "product_id", product["product_id"], product)
        return product

    @staticmethod
    def _product_response(product: dict[str, Any]) -> dict[str, Any]:
        response = dict(product)
        response["archived_at"] = str(response.get("archived_at") or "").strip() or None
        return response

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

    @classmethod
    def _active_campaigns(cls, workbook, product_id: str) -> list[dict[str, Any]]:
        return [
            row
            for row in cls.rows(workbook["Campaigns"])
            if str(row.get("product_id") or "") == product_id
            and not str(row.get("archived_at") or "").strip()
        ]

    def getProducts(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        with self.workbook() as workbook:
            products = self.rows(workbook["Products"])
            active_campaign_counts: dict[str, int] = {}
            for campaign in self.rows(workbook["Campaigns"]):
                if str(campaign.get("archived_at") or "").strip():
                    continue
                product_id = str(campaign.get("product_id") or "")
                if product_id:
                    active_campaign_counts[product_id] = active_campaign_counts.get(product_id, 0) + 1
        if not include_archived:
            products = [row for row in products if not str(row.get("archived_at") or "").strip()]
        products.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("product_id") or "")), reverse=True)
        return [
            {
                **self._product_response(product),
                "campaigns_count": active_campaign_counts.get(str(product.get("product_id") or ""), 0),
            }
            for product in products
        ]

    def getProduct(self, product_id: str) -> dict[str, Any]:
        product_id = self.require_text(product_id, "产品 ID")
        with self.workbook() as workbook:
            product = self.row_by_key(workbook["Products"], "product_id", product_id)
        if not product:
            raise ValueError("产品不存在。")
        return self._product_response(product)

    def updateProduct(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("产品数据无效。")
        product_id = self.require_text(product_id, "产品 ID")
        with self.workbook(write=True) as workbook:
            existing = self.row_by_key(workbook["Products"], "product_id", product_id)
            if not existing:
                raise ValueError("产品不存在。")
            if str(existing.get("archived_at") or "").strip():
                raise ValueError("产品已归档，不能继续修改。")
            updated = {
                **existing,
                "name": self.require_text(payload.get("name", existing.get("name")), "产品名称"),
                "company_name": str(payload.get("company_name", existing.get("company_name")) or "").strip(),
                "note": str(payload.get("note", existing.get("note")) or "").strip(),
                "updated_at": utc_now(),
            }
            self.upsert_row(workbook["Products"], "product_id", product_id, updated)
        return self._product_response(updated)

    def setProductArchivedAt(self, product_id: str, archived_at: object) -> dict[str, Any]:
        product_id = self.require_text(product_id, "产品 ID")
        archive_requested = archived_at is not None
        if archive_requested:
            self._require_iso_timestamp(archived_at)

        with self.workbook(write=True) as workbook:
            product = self.row_by_key(workbook["Products"], "product_id", product_id)
            if not product:
                raise ValueError("产品不存在。")
            current_archived_at = str(product.get("archived_at") or "").strip()

            if archive_requested:
                if self._active_campaigns(workbook, product_id):
                    raise ValueError("产品仍有关联的未归档 Campaign，不能归档。")
                if not current_archived_at:
                    now = utc_now()
                    product = {**product, "archived_at": now, "updated_at": now}
                    self.upsert_row(workbook["Products"], "product_id", product_id, product)
            elif current_archived_at:
                # openpyxl treats value=None as "do not assign" in Worksheet.cell().
                # Persist an empty string, then normalize it to null in API responses.
                product = {**product, "archived_at": "", "updated_at": utc_now()}
                self.upsert_row(workbook["Products"], "product_id", product_id, product)

        return self._product_response(product)

    def archiveProduct(self, product_id: str) -> dict[str, Any]:
        return self.setProductArchivedAt(product_id, utc_now())

    def deleteProduct(self, product_id: str) -> None:
        """Backward-compatible name; Product records are archived, never deleted."""
        self.archiveProduct(product_id)
