from __future__ import annotations

import copy
import json
import socket
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from http_handlers import creator_handler  # noqa: E402
from services.creator_summary_service import CreatorSummaryService  # noqa: E402


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def source_data(**overrides):
    data = {
        "creator": {
            "creator_id": "creator_one",
            "name": "Creator One",
            "platform": "TikTok",
            "profile_url": "https://www.tiktok.com/@one",
            "followers": "12000",
            "country": "Brazil",
            "language": "Portuguese",
            "content_category": "Gaming",
            "bio": "Public creator bio",
            "insight_level": "insufficient",
            "archived_at": "",
        },
        "insight": {},
        "snapshots": [],
        "campaign_creator_count": 0,
    }
    data.update(overrides)
    return data


class FakeRepository:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error
        self.calls = 0

    def getCreatorSummarySourceData(self, creator_id):
        self.calls += 1
        if self.error:
            raise self.error
        return copy.deepcopy(self.data)


class FakeHandler:
    def __init__(self):
        self.response = None

    def _json(self, payload, status=200):
        self.response = (status, payload)

    def _error(self, message, status=400):
        self.response = (status, {"ok": False, "error": message})


class CreatorAIMockTests(unittest.TestCase):
    def service(self, data=None, error=None):
        repository = FakeRepository(data or source_data(), error)
        return CreatorSummaryService(lambda: repository, now_provider=lambda: NOW), repository

    @staticmethod
    def snapshot(captured_at, **values):
        return {"captured_at": captured_at, **values}

    def test_01_creator_basic_profile_summary_works(self):
        service, repository = self.service()
        result = service.get_creator_summary("creator_one")
        self.assertEqual("mock", result["mode"])
        self.assertEqual("Creator One", result["profile"]["name"])
        self.assertEqual("TikTok", result["profile"]["platform"])
        self.assertEqual(1, repository.calls)

    def test_02_identical_input_produces_identical_output(self):
        service, _repository = self.service()
        self.assertEqual(
            service.get_creator_summary("creator_one"),
            service.get_creator_summary("creator_one"),
        )

    def test_03_most_recent_valid_average_views_snapshot_wins(self):
        service, _ = self.service(source_data(snapshots=[
            self.snapshot("2026-08-20T00:00:00Z", average_views="2,000"),
            self.snapshot("2026-08-10T00:00:00Z", average_views=1000),
        ]))
        metric = service.get_creator_summary("creator_one")["performance"]["average_views"]
        self.assertEqual(2000, metric["value"])
        self.assertEqual("2026-08-20T00:00:00Z", metric["measured_at"])

    def test_04_latest_empty_average_views_does_not_erase_earlier_measurement(self):
        service, _ = self.service(source_data(snapshots=[
            self.snapshot("2026-08-20T00:00:00Z", average_views=""),
            self.snapshot("2026-08-10T00:00:00Z", average_views=12000),
        ]))
        metric = service.get_creator_summary("creator_one")["performance"]["average_views"]
        self.assertEqual(12000, metric["value"])
        self.assertEqual("2026-08-10T00:00:00Z", metric["measured_at"])

    def test_05_most_recent_valid_median_views_snapshot_wins(self):
        service, _ = self.service(source_data(snapshots=[
            self.snapshot("2026-08-21T00:00:00Z", median_views=900),
            self.snapshot("2026-08-01T00:00:00Z", median_views=500),
        ]))
        self.assertEqual(900, service.get_creator_summary("creator_one")["performance"]["median_views"]["value"])

    def test_06_video_count_uses_most_recent_valid_positive_measurement(self):
        service, _ = self.service(source_data(snapshots=[
            self.snapshot("2026-08-21T00:00:00Z", video_count=40),
            self.snapshot("2026-08-01T00:00:00Z", video_count=20),
        ]))
        self.assertEqual(40, service.get_creator_summary("creator_one")["performance"]["video_count"]["value"])

    def test_07_latest_zero_video_count_does_not_erase_earlier_positive_value(self):
        service, _ = self.service(source_data(snapshots=[
            self.snapshot("2026-08-21T00:00:00Z", video_count=0),
            self.snapshot("2026-08-01T00:00:00Z", video_count=30),
        ]))
        metric = service.get_creator_summary("creator_one")["performance"]["video_count"]
        self.assertEqual(30, metric["value"])
        self.assertEqual("2026-08-01T00:00:00Z", metric["measured_at"])

    def test_08_zero_video_count_without_history_is_unavailable_not_factual_zero(self):
        service, _ = self.service(source_data(snapshots=[self.snapshot("2026-08-21T00:00:00Z", video_count=0)]))
        result = service.get_creator_summary("creator_one")
        self.assertIsNone(result["performance"]["video_count"])
        self.assertIn("VIDEO_COUNT_UNAVAILABLE", {item["code"] for item in result["limitations"]})

    def test_09_invalid_video_counts_are_unavailable(self):
        for value in ("", "   ", None, "invalid", -1, 1.5, float("nan"), float("inf")):
            with self.subTest(value=value):
                service, _ = self.service(source_data(snapshots=[self.snapshot("2026-08-21T00:00:00Z", video_count=value)]))
                self.assertIsNone(service.get_creator_summary("creator_one")["performance"]["video_count"])

    def test_10_insights_average_views_fallback_works(self):
        service, _ = self.service(source_data(
            insight={"average_views": "5k"},
            snapshots=[self.snapshot("2026-08-21T00:00:00Z", average_views="")],
        ))
        metric = service.get_creator_summary("creator_one")["performance"]["average_views"]
        self.assertEqual(5000, metric["value"])
        self.assertEqual("insights", metric["source"])

    def test_11_insights_fallback_freshness_is_unknown(self):
        service, _ = self.service(source_data(insight={"average_views": 5000}))
        metric = service.get_creator_summary("creator_one")["performance"]["average_views"]
        self.assertEqual("unknown", metric["freshness"])
        self.assertIsNone(metric["measured_at"])

    def test_12_missing_values_create_structured_limitations(self):
        creator = source_data()["creator"]
        creator.update({"country": "", "language": "", "content_category": ""})
        service, _ = self.service(source_data(creator=creator))
        codes = {item["code"] for item in service.get_creator_summary("creator_one")["limitations"]}
        self.assertTrue({"COUNTRY_MISSING", "LANGUAGE_MISSING", "CONTENT_CATEGORY_MISSING"} <= codes)

    def test_13_missing_values_are_never_converted_to_zero(self):
        creator = source_data()["creator"]
        creator["followers"] = ""
        service, _ = self.service(source_data(creator=creator))
        result = service.get_creator_summary("creator_one")
        self.assertEqual("", result["profile"]["followers"])
        self.assertTrue(all(metric is None for key, metric in result["performance"].items() if key != "stability"))
        self.assertNotIn("：0", "\n".join(result["observations"]))

    def test_14_stale_snapshot_is_labeled_stale(self):
        service, _ = self.service(source_data(snapshots=[
            self.snapshot("2026-06-01T00:00:00Z", average_views=1000),
        ]))
        result = service.get_creator_summary("creator_one")
        self.assertEqual("stale", result["performance"]["average_views"]["freshness"])
        self.assertEqual("stale", result["freshness"]["status"])

    def test_15_creator_score_remains_factual_without_quality_language(self):
        service, _ = self.service(source_data(snapshots=[
            self.snapshot("2026-08-20T00:00:00Z", creator_score=93),
        ]))
        result = service.get_creator_summary("creator_one")
        self.assertEqual(93, result["performance"]["creator_score"]["value"])
        rendered = json.dumps(result, ensure_ascii=False).lower()
        for forbidden in ("high quality", "low quality", "good creator", "bad creator", "优质达人", "劣质达人"):
            self.assertNotIn(forbidden, rendered)

    def test_16_insights_risks_are_not_exposed(self):
        service, _ = self.service(source_data(insight={"average_views": 100, "risks": ["private risk"]}))
        self.assertNotIn("private risk", json.dumps(service.get_creator_summary("creator_one")))

    def test_17_insights_recommendation_is_not_exposed(self):
        service, _ = self.service(source_data(insight={"median_views": 100, "recommendation": "private advice"}))
        self.assertNotIn("private advice", json.dumps(service.get_creator_summary("creator_one")))

    def test_18_nonexistent_creator_returns_404(self):
        service, _ = self.service(error=ValueError("未找到达人分析记录。"))
        handler = FakeHandler()
        handled = creator_handler.handle(handler, {
            "method": "GET",
            "path": "/api/creator-library/missing/ai-summary",
            "query": {},
        }, {
            "services": {
                "creator": object(),
                "agency": object(),
                "creator_summary": service,
                "creator_delete_impact": object(),
                "creator_hard_delete": object(),
            },
            "config": {"legacy_cooperation_pattern": __import__("re").compile(r"$^")},
        })
        self.assertTrue(handled)
        self.assertEqual(404, handler.response[0])

    def test_19_archived_creator_remains_readable_and_marked_archived(self):
        creator = source_data()["creator"]
        creator["archived_at"] = "2026-08-01T00:00:00Z"
        service, _ = self.service(source_data(creator=creator))
        self.assertTrue(service.get_creator_summary("creator_one")["entity"]["archived"])

    def test_20_summary_generation_does_not_mutate_workbook_or_source(self):
        data = source_data(snapshots=[self.snapshot("2026-08-20T00:00:00Z", average_views=10)])
        original = copy.deepcopy(data)
        with mock.patch("builtins.open", side_effect=AssertionError("file write attempted")), \
             mock.patch.object(Path, "write_bytes", side_effect=AssertionError("file write attempted")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("file write attempted")):
            service, _ = self.service(data)
            service.get_creator_summary("creator_one")
        self.assertEqual(original, data)

    def test_21_no_external_ai_or_network_provider_is_called(self):
        service, _ = self.service()
        with mock.patch.object(socket, "create_connection", side_effect=AssertionError("network called")):
            result = service.get_creator_summary("creator_one")
        self.assertEqual("mock", result["mode"])


if __name__ == "__main__":
    unittest.main()
