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
    def __init__(self, creators):
        self.creators = creators
        self.calls = 0

    def getCreators(self, include_archived=False):
        self.calls += 1
        self.include_archived = include_archived
        return self.creators


class _CampaignCreatorRepository:
    def __init__(self, relations):
        self.relations = relations
        self.calls = 0

    def getCampaignCreators(self, campaign_id="", creator_id="", *, include_archived=False):
        self.calls += 1
        self.include_archived = include_archived
        return self.relations


class _Handler:
    def __init__(self):
        self.response = None
        self.status = None

    def _json(self, response, status=200):
        self.response = response
        self.status = status

    def _repository_error(self, exc):
        raise exc


def creator(creator_id, platform, followers="", **extra):
    return {
        "creator_id": creator_id,
        "platform": platform,
        "followers": followers,
        **extra,
    }


def relation(creator_id, **extra):
    return {
        "id": f"relation_{creator_id}_{extra.get('campaign_id', 'one')}",
        "creator_id": creator_id,
        "campaign_id": extra.pop("campaign_id", "campaign_one"),
        "publish_links": "",
        **extra,
    }


class PlatformAnalyticsTests(unittest.TestCase):
    def analytics(self, creators, relations):
        return AnalyticsService(
            _CreatorRepository(creators), _CampaignCreatorRepository(relations)
        ).get_platform_analytics()

    @staticmethod
    def platform(result, name):
        return next(row for row in result["platforms"] if row["platform"] == name)

    def test_canonical_entries_order_and_empty_contract(self):
        result = self.analytics([], [])
        self.assertEqual(
            ["tiktok", "instagram", "youtube"],
            [row["platform"] for row in result["platforms"]],
        )
        self.assertEqual(
            {
                "platform_count": 3,
                "creator_count": 0,
                "campaign_creator_count": 0,
                "ignored_campaign_creator_count": 0,
            },
            result["summary"],
        )
        for row in result["platforms"]:
            self.assertEqual(0, row["creator_count"])
            self.assertEqual(0, row["campaign_creator_count"])
            self.assertIsNone(row["followers_average"])
            self.assertIsNone(row["followers_median"])
            self.assertIsNone(row["publish_rate"])
            self.assertIsNone(row["visible_engagement_rate"])
            self.assertIsNone(row["recorded_roi_average"])

    def test_creator_count_is_unique_normalized_and_excludes_archived(self):
        result = self.analytics([
            creator("one", " TikTok ", "1K"),
            creator("one", "TikTok", "9K"),
            creator("two", "INSTAGRAM", "2K"),
            creator("three", "YouTube", "3K", archived_at="2026-01-01"),
            creator("four", "Other", "4K"),
        ], [])
        self.assertEqual(1, self.platform(result, "tiktok")["creator_count"])
        self.assertEqual(1, self.platform(result, "instagram")["creator_count"])
        self.assertEqual(0, self.platform(result, "youtube")["creator_count"])
        self.assertEqual(2, result["summary"]["creator_count"])

    def test_follower_average_median_and_actual_invalid_values(self):
        result = self.analytics([
            creator("one", "TikTok", "1K"),
            creator("two", "TikTok", "2,000"),
            creator("three", "TikTok", "3K"),
            creator("blank", "TikTok", ""),
            creator("none", "TikTok", None),
            creator("malformed", "TikTok", "not-a-number"),
            creator("negative", "TikTok", "-10"),
        ], [])
        tiktok = self.platform(result, "tiktok")
        self.assertEqual(2000, tiktok["followers_average"])
        self.assertEqual(2000, tiktok["followers_median"])
        self.assertEqual(7, tiktok["creator_count"])

    def test_creator_main_platform_owns_all_relation_metrics(self):
        # The related Campaign is Instagram, but Campaign data is deliberately
        # not an AnalyticsService input. Creator.platform remains authoritative.
        campaign = {"campaign_id": "campaign_instagram", "platform": "instagram"}
        result = self.analytics(
            [creator("one", "TikTok", "10K")],
            [relation(
                "one",
                campaign_id=campaign["campaign_id"],
                publish_links='["https://example.test/post"]',
                views=1000,
                likes=100,
                comments=20,
                cost=250,
                creator_quote=999,
                roi=1.5,
            )],
        )
        tiktok = self.platform(result, "tiktok")
        instagram = self.platform(result, "instagram")
        self.assertEqual(1, tiktok["campaign_creator_count"])
        self.assertEqual(1000, tiktok["views_total"])
        self.assertEqual(0, instagram["campaign_creator_count"])

    def test_account_platform_is_not_a_fallback(self):
        result = self.analytics(
            [creator("one", "", "1K")],
            [relation("one", account_platform="YouTube", account_id="account_one")],
        )
        self.assertEqual(0, self.platform(result, "youtube")["campaign_creator_count"])
        self.assertEqual(1, result["summary"]["ignored_campaign_creator_count"])

    def test_orphan_unsupported_and_archived_relations_are_auditable(self):
        result = self.analytics(
            [creator("unsupported", "Other"), creator("valid", "TikTok")],
            [
                relation("missing"),
                relation("unsupported"),
                relation("valid", archived_at="2026-01-01"),
            ],
        )
        self.assertEqual(2, result["summary"]["ignored_campaign_creator_count"])
        self.assertEqual(0, result["summary"]["campaign_creator_count"])

    def test_publication_rate_and_performance_totals(self):
        result = self.analytics(
            [creator("one", "TikTok")],
            [
                relation(
                    "one", campaign_id="one", publish_links='["https://post.test/1"]',
                    views="1,000", likes=100, comments=25, cost=200,
                ),
                relation(
                    "one", campaign_id="two", publish_links="[]",
                    views="bad", likes="bad", comments="", cost="bad",
                ),
            ],
        )
        tiktok = self.platform(result, "tiktok")
        self.assertEqual(2, tiktok["campaign_creator_count"])
        self.assertEqual(1, tiktok["published_count"])
        self.assertEqual(50, tiktok["publish_rate"])
        self.assertEqual(1000, tiktok["views_total"])
        self.assertEqual(100, tiktok["likes_total"])
        self.assertEqual(25, tiktok["comments_total"])
        self.assertEqual(12.5, tiktok["visible_engagement_rate"])
        self.assertEqual(200, tiktok["cost_total"])

    def test_cost_does_not_use_quote_and_roi_is_unweighted_arithmetic_mean(self):
        result = self.analytics(
            [creator("one", "YouTube")],
            [
                relation("one", campaign_id="one", creator_quote=500, cost="", roi=1),
                relation("one", campaign_id="two", creator_quote=700, cost=300, roi=3),
                relation("one", campaign_id="three", cost=100, roi="bad"),
                relation("one", campaign_id="four", cost=0, roi=""),
            ],
        )
        youtube = self.platform(result, "youtube")
        self.assertEqual(400, youtube["cost_total"])
        self.assertEqual(2, youtube["recorded_roi_average"])

    def test_zero_denominators_and_no_roi_are_null(self):
        result = self.analytics(
            [creator("one", "Instagram")],
            [relation("one", views=0, likes=5, comments=2, roi="")],
        )
        instagram = self.platform(result, "instagram")
        self.assertEqual(0, instagram["publish_rate"])
        self.assertIsNone(instagram["visible_engagement_rate"])
        self.assertIsNone(instagram["recorded_roi_average"])
        self.assertIsNone(self.platform(result, "youtube")["publish_rate"])

    def test_sources_are_read_once_with_active_lifecycle_semantics(self):
        creators = _CreatorRepository([creator("one", "TikTok")])
        relations = _CampaignCreatorRepository([relation("one")])
        AnalyticsService(creators, relations).get_platform_analytics()
        self.assertEqual(1, creators.calls)
        self.assertEqual(1, relations.calls)
        self.assertFalse(creators.include_archived)
        self.assertFalse(relations.include_archived)

    def test_api_route_schema_and_existing_routes_are_not_claimed(self):
        service = AnalyticsService(
            _CreatorRepository([creator("one", "TikTok", "1K")]),
            _CampaignCreatorRepository([relation("one")]),
        )
        handler = _Handler()
        handled = analytics_handler.handle(
            handler,
            {"method": "GET", "path": "/api/analytics/platforms"},
            {"services": {"analytics": service}},
        )
        self.assertTrue(handled)
        self.assertEqual(200, handler.status)
        self.assertTrue(handler.response["ok"])
        self.assertEqual(
            ["tiktok", "instagram", "youtube"],
            [row["platform"] for row in handler.response["platforms"]],
        )
        self.assertEqual({"ok", "platforms", "summary"}, set(handler.response))
        self.assertEqual(
            {
                "platform", "creator_count", "followers_average", "followers_median",
                "campaign_creator_count", "published_count", "publish_rate",
                "views_total", "likes_total", "comments_total",
                "visible_engagement_rate", "cost_total", "recorded_roi_average",
            },
            set(handler.response["platforms"][0]),
        )
        self.assertEqual(
            {
                "platform_count", "creator_count", "campaign_creator_count",
                "ignored_campaign_creator_count",
            },
            set(handler.response["summary"]),
        )
        forbidden = {"creator_id", "campaign_id", "account_id", "publish_links"}
        self.assertTrue(all(not forbidden.intersection(row) for row in handler.response["platforms"]))
        for path in ("/api/dashboard", "/api/risks"):
            self.assertFalse(analytics_handler.handle(
                _Handler(), {"method": "GET", "path": path},
                {"services": {"analytics": service}},
            ))


if __name__ == "__main__":
    unittest.main()
