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
        self.calls = []

    def getCreators(self, include_archived=False):
        self.calls.append(include_archived)
        return self.creators


class _CampaignCreatorRepository:
    def getCampaignCreators(self, *args, **kwargs):
        raise AssertionError("Geography analytics must not read CampaignCreator")


class _Handler:
    def __init__(self):
        self.response = None

    def _json(self, response, status=200):
        self.response = response
        self.status = status

    def _repository_error(self, exc):
        raise exc


def creator(creator_id, country="", language="", archived_at=""):
    return {
        "creator_id": creator_id,
        "country": country,
        "language": language,
        "archived_at": archived_at,
    }


class GeographyAnalyticsTests(unittest.TestCase):
    def analytics(self, creators):
        repository = _CreatorRepository(creators)
        result = AnalyticsService(
            repository, _CampaignCreatorRepository()
        ).get_geography_analytics()
        self.assertEqual([True], repository.calls)
        return result

    def test_country_and_language_aggregation_normalizes_trim_and_case(self):
        result = self.analytics([
            creator("one", " China ", "English"),
            creator("two", "china", " english "),
            creator("three", "中国", "中文"),
        ])
        self.assertEqual(
            [
                {"name": "China", "creator_count": 2, "active_creator_count": 2},
                {"name": "中国", "creator_count": 1, "active_creator_count": 1},
            ],
            result["countries"],
        )
        self.assertEqual(2, result["languages"][0]["creator_count"])
        self.assertEqual("English", result["languages"][0]["name"])

    def test_unknown_is_separate_and_archived_only_reduces_active_count(self):
        result = self.analytics([
            creator("active", "", None),
            creator("archived", "  ", "", archived_at="2026-08-01T00:00:00Z"),
        ])
        self.assertEqual(
            [{"name": "Unknown", "creator_count": 2, "active_creator_count": 1}],
            result["countries"],
        )
        self.assertEqual(
            [{"name": "Unknown", "creator_count": 2}],
            result["languages"],
        )

    def test_top_ten_and_other_do_not_absorb_unknown(self):
        creators = []
        for index in range(12):
            creators.extend(
                creator(f"{index}-{item}", f"Country {index}", f"Language {index}")
                for item in range(12 - index)
            )
        creators.append(creator("unknown", "", ""))
        result = self.analytics(creators)

        self.assertEqual(12, len(result["countries"]))
        self.assertEqual("Country 0", result["countries"][0]["name"])
        country_by_name = {row["name"]: row for row in result["countries"]}
        language_by_name = {row["name"]: row for row in result["languages"]}
        self.assertEqual(3, country_by_name["Other"]["creator_count"])
        self.assertEqual(1, country_by_name["Unknown"]["creator_count"])
        self.assertEqual(3, language_by_name["Other"]["creator_count"])
        self.assertEqual(1, language_by_name["Unknown"]["creator_count"])
        self.assertEqual(
            sorted(
                (row["creator_count"] for row in result["countries"]),
                reverse=True,
            ),
            [row["creator_count"] for row in result["countries"]],
        )

    def test_geography_route_contract(self):
        service = AnalyticsService(
            _CreatorRepository([creator("one", "Brazil", "Portuguese")]),
            _CampaignCreatorRepository(),
        )
        handler = _Handler()
        self.assertTrue(analytics_handler.handle(
            handler,
            {"method": "GET", "path": "/api/analytics/geography"},
            {"services": {"analytics": service}},
        ))
        self.assertEqual(200, handler.status)
        self.assertEqual({"ok", "countries", "languages"}, set(handler.response))
        self.assertTrue(handler.response["ok"])


if __name__ == "__main__":
    unittest.main()
