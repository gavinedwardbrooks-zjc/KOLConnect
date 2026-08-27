from __future__ import annotations

"""Read-projected SQLite adapters for Campaign and Product contracts."""

from campaign_creator_repository import CampaignCreatorRepository
from campaign_repository import CampaignRepository
from product_repository import ProductRepository
from data_repository_base import utc_now
from local_storage_lock import shared_storage_lock
from storage.migration import _value


class SQLiteCampaignRepository(CampaignRepository):
    def getCampaigns(self, *args, **kwargs):
        with self.store.projection_scope(("Campaigns", "Products", "CampaignCreators")):
            return super().getCampaigns(*args, **kwargs)

    def getCampaign(self, campaign_id: str):
        with self.store.projection_scope(("Campaigns", "Products", "CampaignCreators")):
            return super().getCampaign(campaign_id)

    def updateCampaign(self, campaign_id: str, payload: dict):
        if not isinstance(payload, dict):
            raise ValueError("Campaign 数据无效。")
        campaign_id = self.require_text(campaign_id, "Campaign ID")
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            row = connection.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
            if row is None:
                raise ValueError("Campaign 不存在。")
            existing = dict(row)
            product_id = self.require_text(payload.get("product_id", existing.get("product_id")), "产品 ID")
            product = connection.execute("SELECT archived_at FROM products WHERE product_id=?", (product_id,)).fetchone()
            if product is None:
                raise ValueError("关联的产品不存在。")
            if str(product["archived_at"] or "").strip():
                raise ValueError("关联的产品已归档。")
            updated = {**existing, "product_id": product_id, "updated_at": utc_now()}
            updated["name"] = self.require_text(payload.get("name", existing.get("name")), "Campaign 名称")
            for field in ("country", "start_date", "end_date", "owner", "goal", "note"):
                if field in payload:
                    updated[field] = str(payload.get(field) or "").strip() or None
            if "status" in payload:
                updated["status"] = self._status(payload.get("status"))
            if "budget" in payload:
                updated["budget"] = _value("budget", payload.get("budget"))
            platforms = None
            if "platform" in payload or "platforms" in payload:
                platform, serialized = self._platform_values(payload, existing)
                updated["platform"] = platform or None
                platforms = self.parse_platforms(serialized, platform)
            columns = tuple(field for field in updated if field != "campaign_id")
            connection.execute(
                f"UPDATE campaigns SET {','.join(f'{field}=?' for field in columns)} WHERE campaign_id=?",
                tuple(updated[field] for field in columns) + (campaign_id,),
            )
            if platforms is not None:
                connection.execute("DELETE FROM campaign_platforms WHERE campaign_id=?", (campaign_id,))
                connection.executemany(
                    "INSERT INTO campaign_platforms(campaign_id,position,platform) VALUES (?,?,?)",
                    ((campaign_id, index, platform) for index, platform in enumerate(platforms)),
                )
            self.store.increment_business_revision(connection)
        return self.getCampaign(campaign_id)


class SQLiteCampaignCreatorRepository(CampaignCreatorRepository):
    _READ_SOURCES = ("CampaignCreators", "Creators", "CreatorAccounts", "Agencies")

    def getCampaignCreators(self, *args, **kwargs):
        with self.store.projection_scope(self._READ_SOURCES):
            return super().getCampaignCreators(*args, **kwargs)

    def getCampaignCreator(self, record_id: str):
        with self.store.projection_scope(self._READ_SOURCES):
            return super().getCampaignCreator(record_id)

    def updateCampaignCreator(self, record_id: str, payload: dict):
        scalar_fields = {
            "stage", "owner", "performance_note", "quote_currency",
            "quote_unit_amount", "quote_quantity", "quote_unit", "creator_quote",
            "cost", "cost_currency",
            "views", "likes", "comments", "roi",
        }
        if not isinstance(payload, dict) or not set(payload).issubset(scalar_fields):
            return super().updateCampaignCreator(record_id, payload)
        record_id = self.require_text(record_id, "Campaign 达人记录 ID")
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            row = connection.execute("SELECT * FROM campaign_creators WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise ValueError("Campaign 达人记录不存在。")
            existing = dict(row)
            updated = self._values(payload, existing)
            monetary_fields = {
                "quote_currency", "quote_unit_amount", "quote_quantity", "quote_unit",
                "creator_quote", "cost", "cost_currency",
            }
            requested_fields = set(payload)
            if requested_fields.intersection(monetary_fields):
                requested_fields.update(monetary_fields)
            updates = {
                field: updated.get(field) for field in scalar_fields if field in requested_fields
            }
            updates["updated_at"] = utc_now()
            connection.execute(
                f"UPDATE campaign_creators SET {','.join(f'{field}=?' for field in updates)} WHERE id=?",
                tuple(updates.values()) + (record_id,),
            )
            self.store.increment_business_revision(connection)
        return self.getCampaignCreator(record_id)


class SQLiteProductRepository(ProductRepository):
    def getProducts(self, *args, **kwargs):
        with self.store.projection_scope(("Products", "Campaigns")):
            return super().getProducts(*args, **kwargs)

    def getProduct(self, product_id: str):
        with self.store.projection_scope(("Products",)):
            return super().getProduct(product_id)
