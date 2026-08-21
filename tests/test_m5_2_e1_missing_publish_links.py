from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from http_handlers import risk_handler  # noqa: E402
from services.risk_service import RiskService  # noqa: E402


class _RiskRepository:
    def __init__(self, source):
        self.source = source

    def read_risk_source(self):
        return self.source


class _Handler:
    def __init__(self):
        self.response = None
        self.status = None

    def _json(self, response, status=200):
        self.response = response
        self.status = status

    def _repository_error(self, exc):
        self.response = {"ok": False, "error": str(exc)}
        self.status = 404 if "不存在" in str(exc) else 400


def source(relations):
    return {
        "campaigns": [{"campaign_id": "campaign_1", "name": "Launch"}],
        "creators": [
            {"creator_id": "creator_1", "name": "Alice"},
            {"creator_id": "creator_2", "name": "Bob"},
        ],
        "creator_accounts": [],
        "campaign_creators": relations,
    }


def relation(creator_id, *, stage="completed", links="", publish_date=""):
    return {
        "campaign_id": "campaign_1",
        "creator_id": creator_id,
        "stage": stage,
        "publish_links": links,
        "publish_date": publish_date,
    }


class MissingPublishLinksTests(unittest.TestCase):
    def service(self, relations):
        return RiskService(_RiskRepository(source(relations)))

    def test_completed_empty_link_is_included_with_frozen_fields(self):
        records = self.service([relation("creator_1")]).get_missing_publish_links(
            "campaign_1", today=date(2026, 8, 21)
        )
        self.assertEqual(1, len(records))
        self.assertEqual(
            {
                "campaign_id", "campaign_name", "creator_id", "creator_name",
                "stage", "publish_links", "publish_date", "risk_level",
            },
            set(records[0]),
        )
        self.assertEqual("Alice", records[0]["creator_name"])

    def test_completed_existing_link_is_excluded(self):
        self.assertEqual(
            [],
            self.service([relation("creator_1", links='["https://example.com/post"]')])
            .get_missing_publish_links("campaign_1", today=date(2026, 8, 21)),
        )

    def test_executing_empty_link_is_excluded(self):
        self.assertEqual(
            [],
            self.service([relation("creator_1", stage="executing")])
            .get_missing_publish_links("campaign_1", today=date(2026, 8, 21)),
        )

    def test_expired_publish_date_is_high(self):
        record = self.service([
            relation("creator_1", publish_date="2026-08-20")
        ]).get_missing_publish_links("campaign_1", today=date(2026, 8, 21))[0]
        self.assertEqual("high", record["risk_level"])

    def test_empty_publish_date_is_low(self):
        record = self.service([relation("creator_1")]).get_missing_publish_links(
            "campaign_1", today=date(2026, 8, 21)
        )[0]
        self.assertEqual("low", record["risk_level"])

    def test_route_uses_service_and_preserves_response_contract(self):
        handler = _Handler()
        service = self.service([relation("creator_1")])
        handled = risk_handler.handle(
            handler,
            {"method": "GET", "path": "/api/campaigns/campaign_1/missing-publish-links"},
            {"services": {"risk": service}},
        )
        self.assertTrue(handled)
        self.assertEqual(200, handler.status)
        self.assertTrue(handler.response["ok"])
        self.assertEqual(1, len(handler.response["missing_publish_links"]))


if __name__ == "__main__":
    unittest.main()
