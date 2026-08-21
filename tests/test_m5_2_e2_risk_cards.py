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

    def _json(self, response, status=200):
        self.response = response

    def _repository_error(self, exc):
        raise exc


class RiskCardsTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "campaigns": [
                {"campaign_id": "campaign_publish", "name": "Publish", "product_id": "product", "start_date": "2026-08-01"},
                {"campaign_id": "campaign_dirty", "name": "Legacy Dirty", "product_id": "", "start_date": ""},
            ],
            "campaign_creators": [{
                "campaign_id": "campaign_publish", "creator_id": "creator_missing",
                "stage": "completed", "publish_links": "", "publish_date": "2026-08-20",
            }],
            "creators": [
                {"creator_id": "creator_missing", "name": "No Email", "email": ""},
                {"creator_id": "creator_account_email", "name": "Account Email", "email": ""},
                {"creator_id": "creator_direct_email", "name": "Direct Email", "email": "direct@example.com"},
            ],
            "creator_accounts": [{
                "creator_id": "creator_account_email", "account_email": "account@example.com",
            }],
        }

    def risks(self):
        return RiskService(_RiskRepository(self.source)).get_risks(today=date(2026, 8, 21))

    def test_missing_publish_link_risk_and_severity(self):
        cards = self.risks()["cards"]
        publish = [card for card in cards if card["risk_type"] == "missing_publish_links"]
        self.assertEqual(1, len(publish))
        self.assertEqual("high", publish[0]["risk_level"])

    def test_missing_email_uses_creator_and_account_email(self):
        cards = self.risks()["cards"]
        missing = [
            card["creator_id"]
            for card in cards
            if card["risk_type"] == "missing_creator_email"
        ]
        self.assertEqual(["creator_missing"], missing)
        self.assertEqual("medium", next(
            card["risk_level"] for card in cards
            if card["risk_type"] == "missing_creator_email"
        ))

    def test_incomplete_campaign_reports_real_missing_fields(self):
        dirty = next(
            card for card in self.risks()["cards"]
            if card["risk_type"] == "incomplete_campaign_data"
        )
        self.assertEqual("medium", dirty["risk_level"])
        self.assertEqual(["product_id", "start_date"], dirty["missing_fields"])

    def test_summary_aggregates_all_severities(self):
        result = self.risks()
        self.assertEqual({"high": 1, "medium": 2, "low": 0}, result["summary"])
        self.assertEqual(sum(result["summary"].values()), len(result["cards"]))

    def test_risks_route_returns_frozen_wrapper(self):
        handler = _Handler()
        handled = risk_handler.handle(
            handler,
            {"method": "GET", "path": "/api/risks"},
            {"services": {"risk": RiskService(_RiskRepository(self.source))}},
        )
        self.assertTrue(handled)
        self.assertTrue(handler.response["ok"])
        self.assertEqual({"high", "medium", "low"}, set(handler.response["summary"]))
        self.assertIsInstance(handler.response["cards"], list)


if __name__ == "__main__":
    unittest.main()
