from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import creator_repository
from campaign_creator_repository import CampaignCreatorRepository
from campaign_repository import CampaignRepository
from product_repository import ProductRepository
from services.campaign_creator_service import CampaignCreatorService


class BatchAddCreatorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workbook_path = Path(self.temp_dir.name) / "Creator_Library.xlsx"
        creator_repository.CreatorRepository(self.workbook_path).getCreators()
        self._seed_creator("creator_one", "account_one", "TikTok")
        self._seed_creator("creator_two", "account_two", "Instagram")
        self._seed_creator("creator_archived", "account_archived", "TikTok", archived=True)
        self._seed_creator("creator_without_account", "", "TikTok")
        self.campaigns = CampaignRepository(self.workbook_path)
        self.relations = CampaignCreatorRepository(self.workbook_path)
        product = ProductRepository(self.workbook_path).createProduct({"name": "Product"})
        self.campaign = self.campaigns.createCampaign({
            "product_id": product["product_id"],
            "name": "Launch",
            "platform": "TikTok",
        })
        self.invalidations = 0
        self.service = CampaignCreatorService(
            lambda: self.relations,
            self._invalidate_dashboard,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _invalidate_dashboard(self) -> None:
        self.invalidations += 1

    def _seed_creator(
        self, creator_id: str, account_id: str, platform: str, *, archived: bool = False
    ) -> None:
        workbook = load_workbook(self.workbook_path)
        self._append(workbook["Creators"], {
            "creator_id": creator_id,
            "name": creator_id,
            "platform": platform,
            "status": "discovered",
            "archived_at": "2026-01-01T00:00:00Z" if archived else "",
        })
        if account_id:
            self._append(workbook["CreatorAccounts"], {
                "account_id": account_id,
                "creator_id": creator_id,
                "account_uid": f"{platform.lower()}|{creator_id}",
                "platform": platform,
            })
        workbook.save(self.workbook_path)
        workbook.close()

    @staticmethod
    def _append(sheet, values: dict[str, object]) -> None:
        headers = [str(cell.value or "") for cell in sheet[1]]
        sheet.append([values.get(header, "") for header in headers])

    def _batch(self, creator_ids: list[str]) -> dict[str, object]:
        return self.service.batch_add_creators(self.campaign["campaign_id"], creator_ids)

    def test_adds_multiple_creators_once_and_reports_per_item_results(self) -> None:
        result = self._batch(["creator_one", "creator_two", "missing_creator"])

        self.assertEqual(3, result["requested"])
        self.assertEqual(1, result["added"])
        self.assertEqual(2, result["failed"])
        self.assertEqual(
            ["added", "failed", "failed"],
            [item["status"] for item in result["results"]],
        )
        self.assertIn("Campaign", result["results"][1]["error"])
        self.assertEqual(1, self.invalidations)
        records = self.relations.getCampaignCreators(campaign_id=self.campaign["campaign_id"])
        self.assertEqual({"creator_one"}, {row["creator_id"] for row in records})
        self.assertEqual("account_one", next(row for row in records if row["creator_id"] == "creator_one")["account_id"])

    def test_duplicate_request_and_retry_are_idempotent(self) -> None:
        first = self._batch(["creator_one", "creator_one"])
        second = self._batch(["creator_one"])

        self.assertEqual(1, first["requested"])
        self.assertEqual("added", first["results"][0]["status"])
        self.assertEqual("already_present", second["results"][0]["status"])
        self.assertEqual(1, self.invalidations)
        self.assertEqual(1, len(self.relations.getCampaignCreators(campaign_id=self.campaign["campaign_id"])))

    def test_archived_relation_restores_and_existing_creator_archive_rule_is_preserved(self) -> None:
        relation = self.relations.createCampaignCreator({
            "campaign_id": self.campaign["campaign_id"],
            "creator_id": "creator_one",
            "account_id": "account_one",
        })
        self.relations.archiveCampaignCreator(relation["id"])

        restored = self._batch(["creator_one"])
        archived_creator = self._batch(["creator_archived"])

        self.assertEqual("restored", restored["results"][0]["status"])
        self.assertEqual("added", archived_creator["results"][0]["status"])
        records = self.relations.getCampaignCreators(campaign_id=self.campaign["campaign_id"])
        self.assertEqual(2, len(records))
        self.assertEqual(relation["id"], next(row for row in records if row["creator_id"] == "creator_one")["id"])

    def test_invalid_campaign_and_unavailable_accounts_are_reported_without_false_invalidation(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能为空"):
            self.service.batch_add_creators(self.campaign["campaign_id"], [])
        with self.assertRaisesRegex(ValueError, "数组"):
            self.service.batch_add_creators(self.campaign["campaign_id"], "creator_one")
        with self.assertRaisesRegex(ValueError, "无效"):
            self.service.batch_add_creators(self.campaign["campaign_id"], [""])
        self.campaigns.archiveCampaign(self.campaign["campaign_id"])
        with self.assertRaisesRegex(ValueError, "已归档"):
            self._batch(["creator_one"])
        self.assertEqual(0, self.invalidations)

        replacement = self.campaigns.createCampaign({
            "product_id": self.campaign["product_id"], "name": "Replacement"
        })
        result = self.service.batch_add_creators(
            replacement["campaign_id"], ["creator_without_account"]
        )
        self.assertEqual("failed", result["results"][0]["status"])
        self.assertEqual(0, self.invalidations)


if __name__ == "__main__":
    unittest.main()
