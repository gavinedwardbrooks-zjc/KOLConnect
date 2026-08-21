from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from dashboard_service import DashboardService


class DashboardVisualizationRepository:
    def __init__(self, creators: list[dict]) -> None:
        self.creators = creators

    def get_creators(self) -> list[dict]:
        return self.creators


class DashboardVisualizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = datetime.now(timezone.utc).date()
        self.service = DashboardService(DashboardVisualizationRepository([
            {
                "creator_id": "creator_today",
                "platform": "TikTok",
                "status": "discovered",
                "created_at": f"{self.today.isoformat()}T09:00:00Z",
            },
            {
                "creator_id": "creator_yesterday",
                "platform": "TikTok",
                "status": "",
                "created_at": f"{(self.today - timedelta(days=1)).isoformat()}T09:00:00Z",
            },
            {
                "creator_id": "creator_midpoint",
                "platform": "",
                "status": "contacted",
                "created_at": f"{(self.today - timedelta(days=15)).isoformat()}T09:00:00Z",
            },
            {
                "creator_id": "creator_old",
                "platform": "YouTube",
                "status": "discovered",
                "created_at": f"{(self.today - timedelta(days=30)).isoformat()}T09:00:00Z",
            },
            {
                "creator_id": "creator_invalid",
                "platform": "Instagram",
                "status": "",
                "created_at": "not-a-date",
            },
        ]))

    def test_platform_and_status_distributions_preserve_values_and_group_empty(self) -> None:
        self.assertEqual(
            [
                {"platform": "TikTok", "count": 2},
                {"platform": "Instagram", "count": 1},
                {"platform": "Other/Unknown", "count": 1},
                {"platform": "YouTube", "count": 1},
            ],
            self.service.getPlatformDistribution(),
        )
        self.assertEqual(
            [
                {"status": "discovered", "count": 2},
                {"status": "Other/Unknown", "count": 2},
                {"status": "contacted", "count": 1},
            ],
            self.service.getCreatorStatusDistribution(),
        )

    def test_creator_growth_trend_is_30_days_oldest_first_and_zero_filled(self) -> None:
        trend = self.service.getCreatorGrowthTrend()

        self.assertEqual(30, len(trend))
        self.assertEqual((self.today - timedelta(days=29)).isoformat(), trend[0]["date"])
        self.assertEqual(self.today.isoformat(), trend[-1]["date"])
        self.assertEqual(1, trend[-1]["count"])
        self.assertEqual(1, trend[-2]["count"])
        self.assertEqual(1, trend[-16]["count"])
        self.assertEqual(0, trend[-3]["count"])
        self.assertEqual(3, sum(item["count"] for item in trend))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
