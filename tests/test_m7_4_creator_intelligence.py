from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.creator_intelligence_service import CreatorIntelligenceService  # noqa: E402


class FakeReader:
    def __init__(self, data):
        self.data = data

    def getCreatorIntelligenceSourceData(self, creator_id):
        self.last_creator_id = creator_id
        return self.data


class M74CreatorIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "creator": {
                "creator_id": "creator_insa", "name": "INSA", "country": "Brasil",
                "language": "Portuguese", "content_category": "POV",
                "tags": "priority, manual", "updated_at": "2026-08-24T00:00:00Z",
            },
            "accounts": [
                {"account_uid": "youtube:insa011", "platform": "YouTube", "username": "insa011", "followers": "1.14M"},
                {"account_uid": "tiktok:insa011_", "platform": "TikTok", "username": "insa011_", "followers": "627.6K"},
            ],
            "snapshots": [
                {"account_uid": "youtube:insa011", "followers": "1.14M", "average_views": 100000, "captured_at": "2026-08-24T00:00:00Z"},
                {"account_uid": "tiktok:insa011_", "followers": "627.6K", "captured_at": "2026-08-24T00:00:00Z"},
            ],
            "videos": [],
            "campaign_creators": [],
        }

    def service(self):
        reader = FakeReader(self.source)
        return CreatorIntelligenceService(
            lambda: reader,
            now=lambda: datetime(2026, 8, 25, tzinfo=timezone.utc),
        )

    def test_multi_account_metrics_are_separate_and_not_summed(self):
        result = self.service().get_creator_intelligence("creator_insa")
        self.assertEqual([1140000, 627600], [item["followers"] for item in result["accounts"]])
        self.assertEqual("multi_account", result["follower_band"])
        self.assertNotIn(1767600, [item["followers"] for item in result["accounts"]])

    def test_user_tags_remain_separate_from_ai_tags(self):
        result = self.service().get_creator_intelligence("creator_insa")
        self.assertEqual(["priority", "manual"], result["user_tags"])
        self.assertIn("category:POV", result["ai_tags"])
        self.assertNotEqual(result["user_tags"], result["ai_tags"])

    def test_grounded_contract_and_unknown_metrics(self):
        result = self.service().get_creator_intelligence("creator_insa")
        self.assertEqual("BR", result["profile"]["country"])
        self.assertEqual("unavailable", result["price_band"])
        self.assertIn("insufficient_price_data", result["limitations"])
        self.assertNotIn("demographics", result["audience_signals"])
        self.assertIn(result["confidence"], {"high", "medium", "low", "insufficient"})

    def test_missing_values_are_not_zero_or_negative_labels(self):
        self.source["accounts"][0]["followers"] = ""
        self.source["accounts"][1]["followers"] = "--"
        self.source["snapshots"] = []
        result = self.service().get_creator_intelligence("creator_insa")
        self.assertTrue(all(item["followers"] is None for item in result["accounts"]))
        self.assertEqual("unavailable", result["follower_band"])
        self.assertIn("missing_followers", result["limitations"])

    def test_freshness_uses_the_injected_utc_clock(self):
        result = self.service().get_creator_intelligence("creator_insa")
        self.assertEqual("fresh", result["data_freshness"])


if __name__ == "__main__":
    unittest.main()
