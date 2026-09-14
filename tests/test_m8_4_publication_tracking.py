from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from http_handlers import campaign_handler  # noqa: E402
from repositories.publication_performance_repository import PublicationPerformanceRepository  # noqa: E402
from services.publication_tracking_service import (  # noqa: E402
    PublicationTrackingService,
    UnavailablePublicationMetricProvider,
)
from storage.schema import CURRENT_SCHEMA_VERSION, apply_schema_migrations, schema_version  # noqa: E402
from storage.sqlite_workbook_store import SQLiteWorkbookStore  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _Campaigns:
    def getCampaign(self, campaign_id):
        if campaign_id not in {"campaign_1", "campaign_2"}:
            raise ValueError("Campaign 不存在。")
        return {"campaign_id": campaign_id}


class _Relations:
    def __init__(self):
        self.records = [
            {
                "id": "relation_1", "campaign_id": "campaign_1", "creator_id": "creator_1",
                "publications": [
                    {"publication_id": "publication_1", "platform": "YouTube", "video_id": "video_1", "actual_publish_url": "https://youtube.com/shorts/video_1"},
                    {"publication_id": "publication_2", "platform": "TikTok", "video_id": "video_2", "actual_publish_url": "https://tiktok.com/@a/video/2"},
                ],
            },
            {
                "id": "relation_2", "campaign_id": "campaign_2", "creator_id": "creator_1",
                "publications": [
                    {"publication_id": "publication_3", "platform": "Instagram", "video_id": "video_3", "actual_publish_url": "https://instagram.com/reel/video_3"},
                ],
            },
        ]

    def getCampaignCreator(self, record_id):
        for record in self.records:
            if record["id"] == record_id:
                return record
        raise ValueError("Campaign 达人关系不存在。")

    def getCampaignCreators(self, campaign_id="", **_kwargs):
        return [record for record in self.records if record["campaign_id"] == campaign_id]


class _Provider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def track(self, publication):
        self.calls.append(dict(publication))
        response = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return dict(response)


class M84PublicationTrackingTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = test_runtime_sandbox("m8_4_focused")
        runtime = self.sandbox.__enter__()
        self.runtime = runtime.root / uuid4().hex
        self.runtime.mkdir()
        self.database = self.runtime / "kolconnect.db"
        self.store = SQLiteWorkbookStore.initialize_empty(self.database)
        self.repository = PublicationPerformanceRepository(self.store)
        self.relations = _Relations()
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('creator_1','Creator')")
            connection.execute("INSERT INTO products(product_id,name) VALUES ('product_1','Product')")
            connection.executemany(
                "INSERT INTO campaigns(campaign_id,product_id,name) VALUES (?,?,?)",
                (("campaign_1", "product_1", "One"), ("campaign_2", "product_1", "Two")),
            )
            connection.executemany(
                "INSERT INTO campaign_creators(id,campaign_id,creator_id) VALUES (?,?,?)",
                (("relation_1", "campaign_1", "creator_1"), ("relation_2", "campaign_2", "creator_1")),
            )
            connection.executemany(
                "INSERT INTO campaign_creator_publish_links(campaign_creator_id,position,publish_link,publication_id,platform,video_id,source) VALUES (?,?,?,?,?,?,?)",
                (
                    ("relation_1", 0, "https://youtube.com/shorts/video_1", "publication_1", "YouTube", "video_1", "manual"),
                    ("relation_1", 1, "https://tiktok.com/@a/video/2", "publication_2", "TikTok", "video_2", "manual"),
                    ("relation_2", 0, "https://instagram.com/reel/video_3", "publication_3", "Instagram", "video_3", "manual"),
                ),
            )

    def tearDown(self):
        shutil.rmtree(self.runtime, ignore_errors=True)
        self.sandbox.__exit__(None, None, None)

    def service(self, provider):
        return PublicationTrackingService(
            lambda: self.relations,
            _Campaigns,
            lambda: self.repository,
            provider,
            clock=lambda: "2026-09-03T10:00:00Z",
        )

    @staticmethod
    def success(metrics, observed_at="2026-09-03T10:00:00Z"):
        return {
            "status": "SUCCESS", "metrics": metrics, "observed_at": observed_at,
            "source": "browser_capture", "confidence": "high",
        }

    def test_schema_current_fresh_and_v3_upgrade_preserve_publication_and_video_snapshot(self):
        with self.store.factory.read_connection() as connection:
            self.assertEqual(CURRENT_SCHEMA_VERSION, schema_version(connection))
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='publication_performance_observations'"
            ).fetchone())
            plan = " ".join(
                str(column)
                for row in connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM publication_performance_observations "
                    "WHERE publication_id=? ORDER BY observed_at DESC, observation_id DESC LIMIT 1",
                    ("publication_1",),
                )
                for column in row
            )
            self.assertIn("idx_publication_observations_latest", plan)
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creator_snapshots(snapshot_id,creator_id) VALUES ('snapshot_1','creator_1')")
            connection.execute("INSERT INTO video_snapshots(video_snapshot_id,snapshot_id,creator_id,video_id) VALUES ('vs_1','snapshot_1','creator_1','video_1')")
            connection.execute("DROP TABLE publication_performance_observations")
            connection.execute("UPDATE storage_metadata SET value='3' WHERE key='schema_version'")
        with self.store.factory.read_connection() as connection:
            self.assertEqual(CURRENT_SCHEMA_VERSION, apply_schema_migrations(connection))
            self.assertEqual(CURRENT_SCHEMA_VERSION, apply_schema_migrations(connection))
            self.assertEqual(3, connection.execute("SELECT COUNT(*) FROM campaign_creator_publish_links").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM video_snapshots").fetchone()[0])
            compatibility = connection.execute("SELECT value FROM storage_metadata WHERE key='application_compatibility'").fetchone()[0]
            self.assertEqual("m8-campaign-execution", compatibility)

    def test_append_only_idempotency_latest_missing_zero_and_provenance(self):
        provider = _Provider([
            self.success({"views": 0, "likes": 0, "comments": 0, "shares": None}),
            self.success({"views": 0, "likes": 0, "comments": 0, "shares": None}),
            self.success({"views": 25, "likes": None, "comments": 2}, "2026-09-04T10:00:00Z"),
            self.success({"views": 25, "likes": None, "comments": 2}, "2026-09-05T10:00:00Z"),
        ])
        service = self.service(provider)
        first = service.refresh_publication("relation_1", "publication_1", refresh_operation_id="operation_1")
        retry = service.refresh_publication("relation_1", "publication_1", refresh_operation_id="operation_1")
        later = service.refresh_publication("relation_1", "publication_1", refresh_operation_id="operation_2")
        same_metrics_later = service.refresh_publication(
            "relation_1", "publication_1", refresh_operation_id="operation_3"
        )
        self.assertTrue(first["created"])
        self.assertFalse(retry["created"])
        self.assertTrue(later["created"])
        self.assertTrue(same_metrics_later["created"])
        history = service.history("relation_1", "publication_1")
        self.assertEqual(3, len(history))
        self.assertEqual(0, history[0]["views"])
        self.assertIsNone(history[0]["shares"])
        self.assertIsNone(history[1]["likes"])
        self.assertEqual("browser_capture", history[0]["source"])
        self.assertEqual("high", history[0]["confidence"])
        self.assertEqual("operation_3", service.latest("relation_1", "publication_1")["refresh_operation_id"])

    def test_trackability_and_metric_boundaries_fail_closed(self):
        self.relations.records[0]["publications"].append({
            "publication_id": "publication_missing", "platform": "YouTube", "actual_publish_url": ""
        })
        missing = self.service(_Provider([self.success({"views": 1})])).refresh_publication(
            "relation_1", "publication_missing"
        )
        self.assertEqual("UNTRACKABLE_IDENTITY", missing["status"])
        unsupported = UnavailablePublicationMetricProvider().track({"platform": "Vimeo"})
        self.assertEqual("UNSUPPORTED_PLATFORM", unsupported["status"])
        unavailable = self.service(_Provider([self.success({
            "views": None, "likes": None, "comments": None, "shares": None,
        })])).refresh_publication("relation_1", "publication_1")
        self.assertEqual("METRIC_UNAVAILABLE", unavailable["status"])
        partial = self.service(_Provider([self.success({
            "views": 100, "likes": 5, "comments": None, "shares": None,
        })])).refresh_publication("relation_1", "publication_1", refresh_operation_id="partial")
        self.assertEqual("SUCCESS", partial["status"])
        self.assertIsNone(partial["observation"]["comments"])
        self.assertIsNone(partial["observation"]["shares"])
        self.assertIsNone(partial["observation"]["engagement_rate"])

    def test_nested_identity_isolation_and_failed_refresh_preserves_history(self):
        service = self.service(_Provider([self.success({"views": 10, "likes": 1, "comments": 1})]))
        service.refresh_publication("relation_1", "publication_1", refresh_operation_id="ok")
        with self.assertRaisesRegex(ValueError, "不属于"):
            service.history("relation_2", "publication_1")
        self.assertEqual([], self.repository.history("publication_3"))
        failed = self.service(_Provider([OSError("offline")])).refresh_publication(
            "relation_1", "publication_1", refresh_operation_id="failed"
        )
        self.assertEqual("NETWORK_ERROR", failed["status"])
        self.assertEqual(1, len(self.repository.history("publication_1")))

    def test_tiktok_is_deferred_without_network_and_batch_is_partial(self):
        provider = _Provider([
            self.success({"views": 100, "likes": 10, "comments": 5}),
            {"status": "CAPTURE_UNAVAILABLE", "reason": "TIKTOK_DEFERRED"},
        ])
        result = self.service(provider).refresh_campaign("campaign_1", refresh_operation_id="batch_1")
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(1, result["succeeded"])
        self.assertEqual(1, result["failed"])
        self.assertEqual(1, len(self.repository.history("publication_1")))
        self.assertEqual([], self.repository.history("publication_2"))
        deferred = UnavailablePublicationMetricProvider().track({"platform": "TikTok"})
        self.assertEqual({"status": "CAPTURE_UNAVAILABLE", "reason": "TIKTOK_DEFERRED"}, deferred)

    def test_batch_statuses_retry_and_routes(self):
        provider = _Provider([self.success({"views": 1, "likes": 0, "comments": 0})])
        service = self.service(provider)
        first = service.refresh_campaign("campaign_1", refresh_operation_id="batch")
        second = service.refresh_campaign("campaign_1", refresh_operation_id="batch")
        self.assertEqual("SUCCESS", first["status"])
        self.assertEqual("SUCCESS", second["status"])
        self.assertEqual(1, len(self.repository.history("publication_1")))
        # The batch operation key includes each Publication and stays idempotent per retry.
        self.assertEqual(2, sum(len(self.repository.history(pid)) for pid in ("publication_1", "publication_2")))

        failed = self.service(_Provider([
            {"status": "CAPTURE_UNAVAILABLE", "reason": "NO_CAPTURE"}
        ])).refresh_campaign("campaign_1")
        self.assertEqual("FAILED", failed["status"])

        class Handler:
            def _json(self, payload, status=200): self.payload, self.status = payload, status
            def _repository_error(self, exc): raise exc

        handler = Handler()
        context = {"repositories": {}, "services": {"publication_tracking": service}}
        request = {
            "method": "GET",
            "path": "/api/campaign-creators/relation_1/publications/publication_1/performance/history",
            "query": {}, "get_payload": lambda: {},
        }
        self.assertTrue(campaign_handler.handle(handler, request, context))
        self.assertEqual(1, len(handler.payload["observations"]))


if __name__ == "__main__":
    unittest.main()
