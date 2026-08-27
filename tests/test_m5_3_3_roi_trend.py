from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from http_handlers import analytics_handler  # noqa: E402
from services.analytics_service import AnalyticsService  # noqa: E402


class _CreatorRepository:
    def getCreators(self, *args, **kwargs):
        raise AssertionError("ROI trend must not read Creator")


class _CampaignCreatorRepository:
    def __init__(self, relations):
        self.relations = relations
        self.calls = []

    def getCampaignCreators(self, campaign_id="", creator_id="", *, include_archived=False):
        self.calls.append(include_archived)
        return self.relations


class _Handler:
    def _json(self, response, status=200):
        self.response = response
        self.status = status

    def _repository_error(self, exc):
        raise exc


def relation(record_id, publish_date="", **extra):
    return {"id": record_id, "publish_date": publish_date, **extra}


class RecordedRoiTrendTests(unittest.TestCase):
    def analytics(self, relations):
        repository = _CampaignCreatorRepository(relations)
        result = AnalyticsService(
            _CreatorRepository(), repository
        ).get_recorded_roi_trend()
        self.assertEqual([False], repository.calls)
        return result

    def test_month_aggregation_uses_publish_date_and_sums_cost(self):
        result = self.analytics([
            relation("one", "2026-08-01", cost="1,000", roi=1, views=100, likes=10, comments=5),
            relation("two", "2026-08-20T12:00:00Z", cost=500, roi=3, views=300, likes=30, comments=15),
            relation("ignored", "", cost=9999, roi=99, campaign_start_date="2026-08-01"),
        ])
        self.assertEqual(1, len(result))
        august = result[0]
        self.assertEqual("2026-08", august["month"])
        self.assertEqual(2, august["campaign_creator_count"])
        self.assertEqual(1500, august["total_cost"])
        self.assertEqual(2, august["average_recorded_roi"])
        self.assertEqual(400, august["total_views"])
        self.assertEqual(15, august["engagement_rate"])

    def test_invalid_metrics_are_ignored_and_no_roi_is_null(self):
        result = self.analytics([
            relation("one", "2026-07-01", cost=-1, roi="", views=0, likes="bad", comments=-2),
            relation("two", "2026-07-02", cost="bad", roi=None, views="bad", likes=10, comments=5),
            relation("invalid-date", "2026-99-99", cost=500, roi=5),
        ])
        self.assertEqual([{
            "month": "2026-07",
            "campaign_creator_count": 2,
            "total_cost": 0,
            "cost_totals_by_currency": {},
            "cost_unknown_currency_total": None,
            "cost_multiple_currencies": False,
            "average_recorded_roi": None,
            "total_views": 0,
            "engagement_rate": None,
        }], result)

    def test_mixed_cost_currencies_do_not_produce_a_scalar_trend_total(self):
        result = self.analytics([
            relation("usd", "2026-08-01", cost=200, cost_currency="USD"),
            relation("brl", "2026-08-02", cost=1000, cost_currency="BRL"),
        ])
        self.assertIsNone(result[0]["total_cost"])
        self.assertEqual(
            {"BRL": 1000.0, "USD": 200.0}, result[0]["cost_totals_by_currency"]
        )
        self.assertTrue(result[0]["cost_multiple_currencies"])

    def test_sparse_months_are_sorted_without_zero_filling(self):
        result = self.analytics([
            relation("march", "2026-03-10", roi=2),
            relation("january", "2026-01-15", roi=1),
            relation("archived", "2026-02-01", roi=9, archived_at="2026-03-01"),
        ])
        self.assertEqual(["2026-01", "2026-03"], [row["month"] for row in result])
        self.assertNotIn("2026-02", [row["month"] for row in result])

    def test_roi_trend_route_contract(self):
        service = AnalyticsService(
            _CreatorRepository(),
            _CampaignCreatorRepository([relation("one", "2026-08-01", roi=2)]),
        )
        handler = _Handler()
        self.assertTrue(analytics_handler.handle(
            handler,
            {"method": "GET", "path": "/api/analytics/roi-trend"},
            {"services": {"analytics": service}},
        ))
        self.assertEqual(200, handler.status)
        self.assertEqual({"ok", "trend"}, set(handler.response))
        self.assertTrue(handler.response["ok"])


if __name__ == "__main__":
    unittest.main()
