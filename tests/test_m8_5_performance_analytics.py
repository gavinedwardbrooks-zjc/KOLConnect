from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.performance_analytics import (  # noqa: E402
    campaign_performance,
    creator_historical_performance,
    publication_trend,
)
from services.similar_creator_search_service import SimilarCreatorSearchService  # noqa: E402
from services.analytics_service import AnalyticsService  # noqa: E402
from http_handlers import campaign_handler, creator_handler  # noqa: E402
from repositories.publication_performance_repository import PublicationPerformanceRepository
from storage.sqlite_workbook_store import SQLiteWorkbookStore
from test_support.runtime_sandbox import test_runtime_sandbox


def observation(observation_id, observed_at, **metrics):
    return {"observation_id": observation_id, "observed_at": observed_at, **metrics}


def publication(publication_id="publication_1", creator_id="creator_1", observations=None):
    return {
        "publication_id": publication_id,
        "creator_id": creator_id,
        "creator_name": creator_id,
        "publication_url": f"https://example.com/{publication_id}",
        "observations": observations or [],
    }


def row(
    publication_id,
    campaign_creator_id,
    creator_id,
    observation_id=None,
    observed_at=None,
    *,
    campaign_id="campaign_1",
    currency="USD",
    cost=100,
    quote=120,
    **metrics,
):
    return {
        "publication_id": publication_id,
        "publication_url": f"https://example.com/{publication_id}",
        "campaign_creator_id": campaign_creator_id,
        "campaign_id": campaign_id,
        "campaign_name": campaign_id,
        "campaign_status": "completed",
        "creator_id": creator_id,
        "creator_name": creator_id,
        "cost": cost,
        "cost_currency": currency,
        "creator_quote": quote,
        "quote_currency": currency,
        "observation_id": observation_id,
        "observed_at": observed_at,
        **metrics,
    }


class M85PerformanceAnalyticsTests(unittest.TestCase):
    def test_offset_chronology_currency_identity_and_multi_account_attribution(self):
        rows = [
            row("p1", "r1", "c1", "late", "2026-01-01T01:00:00Z", currency="", views=200,
                actual_account_uid="youtube:one", platform="YouTube"),
            row("p1", "r1", "c1", "early", "2026-01-01T08:00:00+08:00", currency="", views=100,
                actual_account_uid="youtube:one", platform="YouTube"),
            row("p2", "r1", "c1", "other", "2026-01-01T01:00:00Z", currency="", views=300,
                actual_account_uid="tiktok:one", platform="TikTok"),
        ]
        result = campaign_performance(rows)
        series = result["publications"][0]
        self.assertEqual([100, 200], [point["views"] for point in series["series"]])
        self.assertEqual(100, series["growth"]["views"]["absolute"])
        self.assertEqual(2400, result["fastest_growing"]["growth_rate"])
        self.assertEqual({"youtube:one", "tiktok:one"}, {p["actual_account_uid"] for p in result["publications"]})
        self.assertEqual(500, result["totals"]["views"]["total"])
        history = creator_historical_performance(rows)
        self.assertEqual(1, history["cooperation_count"])
        self.assertEqual({"cost": 1, "quote": 1}, history["unknown_currency_records"])
        self.assertEqual({}, history["efficiency_by_currency"])

    def test_sqlite_join_is_one_indexed_read_and_preserves_empty_relations(self):
        with test_runtime_sandbox("m8_5_queries") as runtime:
            store = SQLiteWorkbookStore.initialize_empty(runtime.root / "analytics.db")
            with store.factory.write_transaction() as connection:
                connection.execute("INSERT INTO creators(creator_id,name) VALUES ('c1','Creator')")
                connection.execute("INSERT INTO campaigns(campaign_id,name) VALUES ('c1','Campaign')")
                connection.execute("INSERT INTO campaign_creators(id,campaign_id,creator_id,cost,cost_currency) VALUES ('r1','c1','c1',10,'USD')")
                connection.execute("INSERT INTO campaign_creator_publish_links(campaign_creator_id,position,publish_link,publication_id) VALUES ('r1',0,'https://example.com/1','p1')")
            repository = PublicationPerformanceRepository(store)
            repository.append({
                "observation_id": "o1", "publication_id": "p1", "refresh_operation_id": "refresh1",
                "observed_at": "2026-01-01T00:00:00Z", "views": 100, "likes": 10,
                "comments": 0, "shares": None, "engagement_rate": 10,
                "source": "fixture", "confidence": "high",
            })
            queries = []
            original = store.factory.read_connection

            @contextmanager
            def traced():
                with original() as connection:
                    connection.set_trace_callback(queries.append)
                    yield connection

            with patch.object(store.factory, "read_connection", traced):
                result = AnalyticsService(None, None, repository).get_campaign_performance("c1")
            selects = [query for query in queries if query.startswith("SELECT cc.id")]
            self.assertEqual(1, len(selects))
            self.assertEqual(100, result["totals"]["views"]["total"])
            with original() as connection:
                plan = " ".join(str(tuple(row)) for row in connection.execute("EXPLAIN QUERY PLAN " + selects[0]))
                self.assertIn("idx_campaign_creators_campaign", plan)
                self.assertIn("SEARCH o USING INDEX", plan)
                self.assertIn("(publication_id=?)", plan)
                self.assertNotIn("SCAN o", plan)
            self.assertEqual([], repository.analytics_rows(creator_id="unknown"))
            self.assertEqual([], repository.analytics_rows(campaign_creator_id="wrong", publication_id="p1"))
            self.assertEqual(1, len(repository.analytics_rows(creator_ids=["c1"])))
            with store.factory.write_transaction() as connection:
                connection.execute("DELETE FROM publication_performance_observations")
                connection.execute("DELETE FROM campaign_creator_publish_links")
            history = AnalyticsService(None, None, repository).get_creator_historical_performance("c1")
            self.assertEqual(1, history["cooperation_count"])
            self.assertEqual(0, history["publication_count"])
            self.assertIsNone(history["average_latest_views"])

    def test_growth_equal_zero_time_negative_and_unrounded_ranking(self):
        equal = publication(observations=[
            observation("a", "2026-01-01T00:00:00Z", views=10),
            observation("b", "2026-01-02T00:00:00Z", views=10),
        ])
        self.assertEqual("unchanged", publication_trend(equal)["growth"]["views"]["status"])
        rows = [
            row("a", "ra", "ca", "a1", "2026-01-01T00:00:00Z", views=20),
            row("a", "ra", "ca", "a2", "2026-01-02T00:00:00Z", views=10),
            row("b", "rb", "cb", "b1", "2026-01-01T00:00:00Z", views=20),
            row("b", "rb", "cb", "b2", "2026-01-01T00:00:00Z", views=1000),
        ]
        result = campaign_performance(rows)
        self.assertEqual("a", result["fastest_growing"]["publication_id"])
        self.assertEqual(-10, result["fastest_growing"]["growth_rate"])
        self.assertEqual(86400, result["fastest_growing"]["elapsed_seconds"])

    def test_publication_growth_uses_metric_specific_valid_endpoints(self):
        item = publication(observations=[
            observation("o3", "2026-01-03T00:00:00Z", views=90, likes=20, comments=5, engagement_rate=10),
            observation("o1", "2026-01-01T00:00:00Z", views=100, likes=None, comments=0, engagement_rate=None),
            observation("o2", "2026-01-02T00:00:00Z", views=None, likes=10, comments=None, engagement_rate=5),
            observation("o4", "2026-01-04T00:00:00Z", views=None, likes=None, comments=5, engagement_rate=None),
        ])
        item["observations"].sort(key=lambda value: value["observed_at"])
        result = publication_trend(item)
        self.assertEqual(
            ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"],
            [item["observed_at"] for item in result["series"]],
        )
        self.assertEqual(-10, result["growth"]["views"]["absolute"])
        self.assertEqual(-10, result["growth"]["views"]["percentage"])
        self.assertEqual("decrease", result["growth"]["views"]["status"])
        self.assertEqual(10, result["growth"]["likes"]["absolute"])
        self.assertEqual(100, result["growth"]["likes"]["percentage"])
        self.assertEqual(5, result["growth"]["comments"]["absolute"])
        self.assertIsNone(result["growth"]["comments"]["percentage"])
        self.assertEqual("increase", result["growth"]["comments"]["status"])
        self.assertEqual(5, result["growth"]["engagement_rate"]["absolute"])
        self.assertIsNone(publication_trend(publication())["growth"]["views"])
        self.assertIsNone(publication_trend(publication(observations=[item["observations"][0]]))["growth"]["views"])

    def test_campaign_totals_average_top_entities_and_fastest_growth(self):
        rows = [
            row("p1", "r1", "c1", "p1o1", "2026-01-01T00:00:00Z", views=0, likes=0, comments=0, engagement_rate=0),
            row("p1", "r1", "c1", "p1o2", "2026-01-04T00:00:00Z", views=200, likes=20, comments=10, engagement_rate=15),
            row("p2", "r1", "c1", "p2o1", "2026-01-01T00:00:00Z", views=100, likes=5, comments=None, engagement_rate=5),
            row("p2", "r1", "c1", "p2o2", "2026-01-02T00:00:00Z", views=200, likes=None, comments=None, engagement_rate=None),
            row("p3", "r2", "c2", "p3o1", "2026-01-01T00:00:00Z", views=None, likes=10, comments=2, engagement_rate=10),
            row("p3", "r2", "c2", "p3o2", "2026-01-03T00:00:00Z", views=None, likes=30, comments=4, engagement_rate=20),
        ]
        result = campaign_performance(rows)
        self.assertEqual({"total": 400, "valid_count": 2, "missing_count": 1, "total_publications": 3}, result["totals"]["views"])
        self.assertEqual(55, result["totals"]["likes"]["total"])
        self.assertEqual(14, result["totals"]["comments"]["total"])
        self.assertEqual(13.33, result["average_er"])
        self.assertEqual(3, result["valid_er_count"])
        self.assertEqual("p1", result["top_video"]["publication_id"])
        self.assertEqual("c1", result["top_creator"]["creator_id"])
        self.assertEqual(400, result["top_creator"]["views"])
        self.assertEqual("p3", result["highest_er"]["publication_id"])
        self.assertEqual("p2", result["fastest_growing"]["publication_id"])
        self.assertEqual(100, result["fastest_growing"]["growth_rate"])
        self.assertEqual("2026-01-01T00:00:00Z", result["fastest_growing"]["start_observed_at"])
        self.assertEqual("2026-01-02T00:00:00Z", result["fastest_growing"]["end_observed_at"])
        self.assertEqual({"USD": 200}, result["total_cost_by_currency"])
        self.assertIsNone(result["roi"])

    def test_campaign_missing_true_zero_and_deterministic_ties(self):
        empty = campaign_performance([])
        self.assertIsNone(empty["totals"]["views"]["total"])
        self.assertIsNone(empty["average_er"])
        self.assertIsNone(empty["top_video"])
        rows = [
            row("p2", "r2", "c2", "o2", "2026-01-01T00:00:00Z", views=0, engagement_rate=0),
            row("p1", "r1", "c1", "o1", "2026-01-01T00:00:00Z", views=0, engagement_rate=0),
        ]
        result = campaign_performance(rows)
        self.assertEqual(0, result["totals"]["views"]["total"])
        self.assertEqual(0, result["average_er"])
        self.assertEqual("p1", result["top_video"]["publication_id"])
        self.assertEqual("c1", result["top_creator"]["creator_id"])
        self.assertEqual("p1", result["highest_er"]["publication_id"])
        self.assertIsNone(result["fastest_growing"])

    def test_creator_history_dedupes_relations_campaigns_and_groups_money(self):
        rows = [
            row("p1", "r1", "c1", "o1", "2026-01-01T00:00:00Z", views=100, likes=10, comments=10, engagement_rate=20),
            row("p1", "r1", "c1", "o2", "2026-01-02T00:00:00Z", views=200, likes=20, comments=20, engagement_rate=20),
            row("p2", "r1", "c1", "o3", "2026-01-02T00:00:00Z", views=300, likes=30, comments=30, engagement_rate=20),
            row("p3", "r2", "c1", "o4", "2026-01-02T00:00:00Z", campaign_id="campaign_2", currency="BRL", cost=600, quote=700, views=600, likes=60, comments=40, engagement_rate=16.67),
        ]
        result = creator_historical_performance(rows)
        self.assertEqual(2, result["cooperation_count"])
        self.assertEqual(2, result["historical_campaign_count"])
        self.assertEqual(3, result["publication_count"])
        self.assertEqual(366.67, result["average_latest_views"])
        self.assertEqual(18.89, result["average_latest_er"])
        self.assertEqual({"BRL": 600, "USD": 100}, result["total_cost_by_currency"])
        self.assertEqual({"BRL": 700, "USD": 120}, result["total_quote_by_currency"])
        self.assertEqual(0.2, result["efficiency_by_currency"]["USD"]["cpv"])
        self.assertEqual(1, result["efficiency_by_currency"]["USD"]["cpe"])
        self.assertIsNone(result["roi"])
        self.assertEqual("AUTHORITATIVE_RETURN_INPUT_UNAVAILABLE", result["roi_reason"])

    def test_efficiency_fails_closed_for_missing_zero_and_quote_only(self):
        missing = creator_historical_performance([
            row("p1", "r1", "c1", "o1", "2026-01-01T00:00:00Z", views=None, likes=1, comments=1),
            row("p2", "r2", "c1", "o2", "2026-01-01T00:00:00Z", views=100, likes=1, comments=1),
        ])
        self.assertIsNone(missing["efficiency_by_currency"]["USD"]["cpv"])
        zero = creator_historical_performance([
            row("p1", "r1", "c1", "o1", "2026-01-01T00:00:00Z", views=0, likes=0, comments=0),
        ])
        self.assertIsNone(zero["efficiency_by_currency"]["USD"]["cpv"])
        self.assertIsNone(zero["efficiency_by_currency"]["USD"]["cpe"])
        quote_only = creator_historical_performance([
            row("p1", "r1", "c1", "o1", "2026-01-01T00:00:00Z", cost=None, views=100, likes=1, comments=1),
        ])
        self.assertEqual({}, quote_only["total_cost_by_currency"])
        self.assertEqual({"USD": 120}, quote_only["total_quote_by_currency"])
        self.assertEqual({}, quote_only["efficiency_by_currency"])

    def test_m8_2_base_score_is_unchanged_and_history_is_evidence_only(self):
        data = {
            "creators": [
                {"creator_id": "source", "name": "Source", "platform": "TikTok", "tags": "gaming"},
                {"creator_id": "candidate", "name": "Candidate", "platform": "TikTok", "tags": "gaming"},
            ],
            "accounts": [], "snapshots": [], "analysis": [], "campaign_creators": [],
        }

        class Repository:
            def getSimilarCreatorSourceData(self):
                return data

        plain = SimilarCreatorSearchService(lambda: Repository()).find_scored("source")
        enriched = SimilarCreatorSearchService(
            lambda: Repository(),
            historical_performance_provider=lambda ids: {
                item: {"creator_id": item, "cooperation_count": 2, "publication_count": 3,
                       "average_latest_views": 100, "average_latest_er": 5}
                for item in ids
            },
        ).find_scored("source")
        self.assertEqual(
            plain["candidates"][0]["base_similarity_score"],
            enriched["candidates"][0]["base_similarity_score"],
        )
        self.assertEqual(2, enriched["candidates"][0]["historical_performance_evidence"]["cooperation_count"])
        self.assertEqual("publication_performance_observations", enriched["candidates"][0]["historical_performance_evidence"]["source"])

    def test_service_uses_scoped_batch_queries_and_routes_preserve_identity(self):
        class PerformanceRepository:
            def __init__(self):
                self.calls = []

            def analytics_rows(self, **filters):
                self.calls.append(filters)
                return [row("p1", "r1", "c1", "o1", "2026-01-01T00:00:00Z", views=10)]

        class Empty:
            pass

        repository = PerformanceRepository()
        service = AnalyticsService(Empty(), Empty(), repository)
        self.assertEqual("campaign_1", service.get_campaign_performance("campaign_1")["campaign_id"])
        self.assertEqual({"campaign_id": "campaign_1"}, repository.calls[-1])
        self.assertEqual("c1", service.get_creator_historical_performance("c1")["creator_id"])
        self.assertEqual({"creator_id": "c1"}, repository.calls[-1])
        service.get_publication_performance("r1", "p1")
        self.assertEqual({"campaign_creator_id": "r1", "publication_id": "p1"}, repository.calls[-1])

        class Handler:
            def _json(self, payload, status=200):
                self.payload, self.status = payload, status

            def _repository_error(self, error):
                raise error

        handler = Handler()
        request = {"method": "GET", "path": "/api/campaigns/campaign_1/performance", "query": {}, "get_payload": lambda: {}}
        campaign_repository = type(
            "CampaignRepository",
            (),
            {"getCampaign": lambda _self, campaign_id: {"campaign_id": campaign_id}},
        )()
        self.assertTrue(campaign_handler.handle(
            handler,
            request,
            {"repositories": {"campaign": lambda: campaign_repository}, "services": {"analytics": service}},
        ))
        self.assertEqual("campaign_1", handler.payload["campaign_id"])

        creator_request = {"method": "GET", "path": "/api/creator-library/c1/historical-performance", "query": {}, "get_payload": lambda: {}}
        creator_services = {
            "creator": type("Creator", (), {"get_creator_detail": lambda _self, _id: {"creator": {"creator_id": _id}}})(),
            "analytics": service,
            "agency": object(),
            "creator_delete_impact": object(),
            "creator_hard_delete": object(),
        }
        self.assertTrue(creator_handler.handle(handler, creator_request, {"repositories": {}, "services": creator_services}))
        self.assertEqual("c1", handler.payload["creator_id"])


if __name__ == "__main__":
    unittest.main()
