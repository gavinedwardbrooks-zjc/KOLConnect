from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from repository_factory import RepositoryFactory
from http_handlers import campaign_handler


class _Handler:
    def __init__(self) -> None:
        self.payload = None
        self.status = None

    def _json(self, payload, status=200) -> None:
        self.payload = payload
        self.status = status

    def _repository_error(self, exc) -> None:
        self.payload = {"ok": False, "error": str(exc)}
        self.status = 400


class _CapturingCampaignRepository:
    def __init__(self) -> None:
        self.filters = None

    def getCampaigns(self, **filters):
        self.filters = filters
        return []


class CampaignStartDateHandlerTests(unittest.TestCase):
    def test_handler_forwards_new_and_existing_filters_without_alias_route(self) -> None:
        repository = _CapturingCampaignRepository()
        handler = _Handler()
        handled = campaign_handler.handle(
            handler,
            {
                "method": "GET",
                "path": "/api/campaigns",
                "query": {
                    "product_id": ["product_one"],
                    "status": ["running"],
                    "creator_id": ["creator_one"],
                    "start_date_from": ["2026-08-01"],
                    "start_date_to": ["2026-08-31"],
                    "include_archived": ["true"],
                },
            },
            {"repositories": {"campaign": lambda: repository}},
        )

        self.assertTrue(handled)
        self.assertEqual(200, handler.status)
        self.assertEqual(
            {
                "product_id": "product_one",
                "status": "running",
                "creator_id": "creator_one",
                "start_date_from": "2026-08-01",
                "start_date_to": "2026-08-31",
                "include_archived": True,
            },
            repository.filters,
        )


class CampaignStartDateFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".m5_4_e4_")
        self.root = Path(self.temp.name)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "APPDATA": str(self.root / "runtime"),
                "HOME": str(self.root),
                "XDG_DATA_HOME": str(self.root / "runtime"),
            },
        )
        self.environment.start()
        factory = RepositoryFactory.for_path(self.root / "Creator_Library.xlsx")
        self.products = factory.product()
        self.campaigns = factory.campaign()
        product_one = self.products.createProduct({"name": "Product One"})
        product_two = self.products.createProduct({"name": "Product Two"})
        self.product_one = product_one["product_id"]
        self.product_two = product_two["product_id"]
        self._create("Early", self.product_one, "2026-07-31", "draft")
        self._create("Boundary", self.product_one, "2026-08-01", "running")
        self._create("Middle", self.product_one, "2026-08-15", "running")
        self._create("Late", self.product_two, "2026-09-01", "running")

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def _create(self, name: str, product_id: str, start_date: str, status: str) -> None:
        self.campaigns.createCampaign(
            {
                "name": name,
                "product_id": product_id,
                "start_date": start_date,
                "status": status,
            }
        )

    @staticmethod
    def _names(rows) -> set[str]:
        return {row["name"] for row in rows}

    def test_from_filter_is_inclusive(self) -> None:
        rows = self.campaigns.getCampaigns(start_date_from="2026-08-01")
        self.assertEqual({"Boundary", "Middle", "Late"}, self._names(rows))

    def test_to_filter_is_inclusive(self) -> None:
        rows = self.campaigns.getCampaigns(start_date_to="2026-08-01")
        self.assertEqual({"Early", "Boundary"}, self._names(rows))

    def test_missing_date_params_preserve_existing_behavior(self) -> None:
        self.assertEqual(4, len(self.campaigns.getCampaigns()))

    def test_date_filters_combine_with_product_and_status(self) -> None:
        rows = self.campaigns.getCampaigns(
            product_id=self.product_one,
            status="running",
            start_date_from="2026-08-01",
            start_date_to="2026-08-15",
        )
        self.assertEqual({"Boundary", "Middle"}, self._names(rows))

    def test_invalid_date_or_reversed_range_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.campaigns.getCampaigns(start_date_from="20260801")
        with self.assertRaisesRegex(ValueError, "不能晚于"):
            self.campaigns.getCampaigns(
                start_date_from="2026-09-01",
                start_date_to="2026-08-01",
            )


if __name__ == "__main__":
    unittest.main()
