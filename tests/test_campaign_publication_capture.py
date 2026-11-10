from __future__ import annotations

from datetime import datetime, timedelta, timezone
import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from repositories.publication_capture_repository import PublicationCaptureRepository  # noqa: E402
from repositories.publication_capture_batch_repository import PublicationCaptureBatchRepository  # noqa: E402
from local_request_security import allowed_mutation_origin  # noqa: E402
from repositories.publication_performance_repository import PublicationPerformanceRepository  # noqa: E402
from services.publication_capture_security import PublicationCaptureSessionStore  # noqa: E402
from services.publication_capture_service import PublicationCaptureError, PublicationCaptureService  # noqa: E402
from services.publication_capture_batch_service import PublicationCaptureBatchService  # noqa: E402
from storage.schema import CURRENT_SCHEMA_VERSION, apply_schema_migrations, schema_version  # noqa: E402
from storage.sqlite_workbook_store import SQLiteWorkbookStore  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _Relations:
    def __init__(self):
        self.records = {
            "relation_tiktok": self._record("tiktok", "TikTok", "https://www.tiktok.com/@creator/video/100", "100"),
            "relation_instagram": self._record("instagram", "Instagram", "https://www.instagram.com/reel/ABC_1/", "ABC_1"),
            "relation_youtube": self._record("youtube", "YouTube", "https://www.youtube.com/shorts/yt_1", "yt_1"),
        }

    @staticmethod
    def _record(suffix, platform, url, video_id):
        return {
            "id": f"relation_{suffix}", "campaign_id": "campaign_1", "creator_id": "creator_1",
            "publications": [{
                "publication_id": f"publication_{suffix}", "platform": platform, "video_id": video_id,
                "actual_publish_url": url, "actual_account_uid": f"account_{suffix}",
            }],
        }

    def getCampaignCreator(self, relation_id):
        if relation_id not in self.records:
            raise ValueError("missing")
        return self.records[relation_id]

    def getCampaignCreators(self, campaign_id=""):
        return [row for row in self.records.values() if row["campaign_id"] == campaign_id]


class _Campaigns:
    def getCampaign(self, campaign_id):
        if campaign_id != "campaign_1":
            raise ValueError("missing")
        return {"campaign_id": campaign_id, "name": "Campaign"}


class _Creators:
    def getCreatorAccounts(self, creator_id=""):
        return [
            {"account_uid": "account_tiktok", "creator_id": "creator_1", "platform": "TikTok", "username": "creator"},
            {"account_uid": "account_instagram", "creator_id": "creator_1", "platform": "Instagram", "username": "creator"},
            {"account_uid": "account_youtube", "creator_id": "creator_1", "platform": "YouTube", "username": "creator"},
        ] if creator_id == "creator_1" else []


class CampaignPublicationCaptureTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = test_runtime_sandbox("publication_capture")
        runtime = self.sandbox.__enter__()
        self.root = runtime.root / uuid4().hex
        self.root.mkdir()
        self.store = SQLiteWorkbookStore.initialize_empty(self.root / "kolconnect.db")
        self.attempts = PublicationCaptureRepository(self.store)
        self.observations = PublicationPerformanceRepository(self.store)
        self.batches = PublicationCaptureBatchRepository(self.store)
        self.relations = _Relations()
        self.now = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('creator_1','Creator')")
            connection.execute("INSERT INTO products(product_id,name) VALUES ('product_1','Product')")
            connection.execute("INSERT INTO campaigns(campaign_id,product_id,name) VALUES ('campaign_1','product_1','Campaign')")
            for suffix, platform in (("tiktok", "TikTok"), ("instagram", "Instagram"), ("youtube", "YouTube")):
                connection.execute(
                    "INSERT INTO creator_accounts(account_uid,creator_id,platform,username) VALUES (?,?,?,?)",
                    (f"account_{suffix}", "creator_1", platform, "creator"),
                )
                connection.execute(
                    "INSERT INTO campaign_creators(id,campaign_id,creator_id) VALUES (?,?,?)",
                    (f"relation_{suffix}", "campaign_1", "creator_1"),
                )
                publication = self.relations.records[f"relation_{suffix}"]["publications"][0]
                connection.execute(
                    "INSERT INTO campaign_creator_publish_links("
                    "campaign_creator_id,position,publish_link,publication_id,actual_account_uid,platform,video_id,source) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (f"relation_{suffix}", 0, publication["actual_publish_url"], publication["publication_id"],
                     f"account_{suffix}", platform, publication["video_id"], "manual"),
                )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        self.sandbox.__exit__(None, None, None)

    def service(self):
        return PublicationCaptureService(
            lambda: self.relations, _Creators, lambda: self.attempts, lambda: self.observations,
            now=lambda: self.now,
        )

    def batch_service(self):
        return PublicationCaptureBatchService(
            _Campaigns, lambda: self.relations, lambda: self.batches, self.service,
            now=lambda: self.now,
        )

    @staticmethod
    def metrics(views=0, likes=None, comments=2, shares=None):
        values = {"views": views, "likes": likes, "comments": comments, "shares": shares}
        return {
            name: {
                "value": value,
                "source": "fixture" if value is not None else "missing",
                "confidence": "high" if value is not None else "low",
                "missing_reason": "" if value is not None else "not_exposed",
            }
            for name, value in values.items()
        }

    def submit(self, request, *, page_url=None, metrics=None, status="partial", token=None):
        capture_token = str(request["capture_code"]).split(".", 1)[1]
        return self.service().submit_result({
            "request_id": request["request_id"],
            "capability_token": token if token is not None else capture_token,
            "page_url": page_url or request["canonical_url"],
            "platform": request["platform"], "video_id": request["video_id"],
            "capture_status": status, "metrics": metrics if metrics is not None else self.metrics(),
            "collector_version": "2.0.1", "contract_version": "publication-capture-v1",
        })

    def test_schema_v11_and_three_platform_request_identity(self):
        with self.store.factory.read_connection() as connection:
            self.assertEqual(11, CURRENT_SCHEMA_VERSION)
            self.assertEqual(11, schema_version(connection))
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='publication_capture_attempts'"
            ).fetchone())
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='publication_capture_batch_runs'"
            ).fetchone())
        for suffix, platform in (("tiktok", "TikTok"), ("instagram", "Instagram"), ("youtube", "YouTube")):
            request = self.service().create_request(f"relation_{suffix}", f"publication_{suffix}")
            self.assertEqual(platform, request["platform"])
            self.assertTrue(request["capture_code"].startswith(f"{request['request_id']}."))
            self.assertNotIn("capability_token", request)
            stored = self.attempts.get(request["request_id"])
            self.assertNotIn("capability_hash", stored)
            self.assertNotIn("capability_token", stored)

    def test_schema_v8_upgrade_creates_attempt_and_batch_tables_without_losing_publications(self):
        with self.store.factory.write_transaction() as connection:
            connection.execute("DROP TABLE publication_capture_attempts")
            connection.execute("UPDATE storage_metadata SET value='8' WHERE key='schema_version'")
        with self.store.factory.read_connection() as connection:
            self.assertEqual(11, apply_schema_migrations(connection))
            self.assertEqual(3, connection.execute("SELECT COUNT(*) FROM campaign_creator_publish_links").fetchone()[0])
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='publication_capture_attempts'"
            ).fetchone())
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='publication_capture_batch_items'"
            ).fetchone())

    def test_one_click_batch_claims_three_items_and_persists_without_manual_codes(self):
        service = self.batch_service()
        created = service.create("campaign_1")
        batch_id = created["batch"]["batch_run_id"]
        self.assertEqual(3, created["total"])
        self.assertNotIn("claim_token_hash", created["batch"])
        claimed = service.claim(batch_id, created["claim_token"], "chrome-extension://fixture-id")
        executor = claimed["executor_token"]
        for expected in range(3):
            next_item = service.next_item(batch_id, executor, "chrome-extension://fixture-id")
            self.assertEqual("opening", next_item["state"])
            item = next_item["item"]
            request_id, token = str(item["capture_code"]).split(".", 1)
            result = service.submit_result({
                "request_id": request_id, "capability_token": token,
                "page_url": item["canonical_url"], "platform": item["platform"],
                "video_id": item["video_id"], "capture_status": "partial",
                "metrics": self.metrics(views=expected, likes=None, comments=0, shares=None),
                "collector_version": "2.0.1", "contract_version": "publication-capture-v1",
            })
            self.assertEqual("partial", result["attempt"]["capture_status"])
            if expected == 0:
                replay = service.submit_result({
                    "request_id": request_id, "capability_token": token,
                    "page_url": item["canonical_url"], "platform": item["platform"],
                    "video_id": item["video_id"], "capture_status": "partial",
                    "metrics": self.metrics(views=999, likes=999, comments=999, shares=999),
                    "collector_version": "2.0.1", "contract_version": "publication-capture-v1",
                })
                self.assertTrue(replay["replayed"])
        finished = service.next_item(batch_id, executor, "chrome-extension://fixture-id")
        self.assertEqual("completed", finished["state"])
        self.assertEqual(3, sum(len(self.observations.history(f"publication_{suffix}")) for suffix in ("tiktok", "instagram", "youtube")))

    def test_batch_authorization_pause_cancel_replay_and_origin_are_fail_closed(self):
        service = self.batch_service()
        created = service.create("campaign_1")
        batch_id = created["batch"]["batch_run_id"]
        claimed = service.claim(batch_id, created["claim_token"], "chrome-extension://fixture-id")
        executor = claimed["executor_token"]
        with self.assertRaises(PublicationCaptureError):
            service.claim(batch_id, created["claim_token"], "chrome-extension://fixture-id")
        with self.assertRaises(PublicationCaptureError):
            service.next_item(batch_id, executor, "chrome-extension://other-id")
        item = service.next_item(batch_id, executor, "chrome-extension://fixture-id")["item"]
        service.pause(batch_id)
        request_id, token = str(item["capture_code"]).split(".", 1)
        with self.assertRaises(PublicationCaptureError):
            service.submit_result({
                "request_id": request_id, "capability_token": token, "page_url": item["canonical_url"],
                "platform": item["platform"], "video_id": item["video_id"], "capture_status": "partial",
                "metrics": self.metrics(1, 0, 0, None), "collector_version": "2.0.1",
                "contract_version": "publication-capture-v1",
            })
        self.assertEqual("paused", service.next_item(batch_id, executor, "chrome-extension://fixture-id")["state"])
        resumed = service.resume(batch_id)
        new_executor = service.claim(batch_id, resumed["claim_token"], "chrome-extension://fixture-id")["executor_token"]
        next_item = service.next_item(batch_id, new_executor, "chrome-extension://fixture-id")["item"]
        service.cancel(batch_id)
        cancelled_state = service.executor_state(
            batch_id, new_executor, "chrome-extension://fixture-id", next_item["request_id"],
        )
        self.assertFalse(cancelled_state["continue_current"])
        self.assertEqual("cancelled", cancelled_state["state"])
        cancelled_id, cancelled_token = str(next_item["capture_code"]).split(".", 1)
        with self.assertRaises(PublicationCaptureError):
            service.submit_result({
                "request_id": cancelled_id, "capability_token": cancelled_token,
                "page_url": next_item["canonical_url"], "platform": next_item["platform"],
                "video_id": next_item["video_id"], "capture_status": "failed", "metrics": {},
                "collector_version": "2.0.1", "contract_version": "publication-capture-v1",
            })

    def test_batch_manifest_supports_thirty_bounded_items(self):
        relation = self.relations.records["relation_youtube"]
        with self.store.factory.write_transaction() as connection:
            for index in range(2, 29):
                publication_id = f"publication_youtube_{index}"
                video_id = f"yt_{index}"
                url = f"https://www.youtube.com/shorts/{video_id}"
                relation["publications"].append({
                    "publication_id": publication_id, "platform": "YouTube", "video_id": video_id,
                    "actual_publish_url": url, "actual_account_uid": "account_youtube",
                })
                connection.execute(
                    "INSERT INTO campaign_creator_publish_links("
                    "campaign_creator_id,position,publish_link,publication_id,actual_account_uid,platform,video_id,source) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    ("relation_youtube", index, url, publication_id, "account_youtube", "YouTube", video_id, "manual"),
                )
        created = self.batch_service().create("campaign_1")
        self.assertEqual(30, created["total"])
        self.assertEqual(30, created["counts"]["pending"])

    def test_expired_claim_and_stale_item_require_explicit_resume_with_new_authorization(self):
        service = self.batch_service()
        created = service.create("campaign_1")
        batch_id = created["batch"]["batch_run_id"]
        self.now += timedelta(minutes=2)
        state = service.status(batch_id)
        self.assertEqual("interrupted", state["batch"]["status"])
        self.assertEqual("BATCH_CLAIM_EXPIRED", state["batch"]["safe_error_code"])
        with self.assertRaises(PublicationCaptureError):
            service.claim(batch_id, created["claim_token"], "chrome-extension://fixture-id")
        resumed = service.resume(batch_id)
        claimed = service.claim(batch_id, resumed["claim_token"], "chrome-extension://fixture-id")
        item = service.next_item(batch_id, claimed["executor_token"], "chrome-extension://fixture-id")["item"]
        self.now += timedelta(seconds=91)
        interrupted = service.status(batch_id)
        self.assertEqual("interrupted", interrupted["batch"]["status"])
        item_state = next(row for row in interrupted["items"] if row["item_id"] == item["item_id"])
        self.assertEqual("interrupted", item_state["status"])
        self.assertEqual("CAPTURE_ITEM_INTERRUPTED", item_state["safe_error_code"])

    def test_all_invalid_publications_are_skipped_and_batch_closes_cleanly(self):
        for relation in self.relations.records.values():
            relation["publications"][0]["actual_publish_url"] = "https://www.youtube.com/@creator"
        service = self.batch_service()
        created = service.create("campaign_1")
        self.assertEqual(3, created["counts"]["skipped"])
        claimed = service.claim(
            created["batch"]["batch_run_id"], created["claim_token"], "chrome-extension://fixture-id",
        )
        state = service.next_item(
            created["batch"]["batch_run_id"], claimed["executor_token"], "chrome-extension://fixture-id",
        )
        self.assertEqual("completed", state["state"])

    def test_duplicate_video_is_skipped_without_second_capture_item(self):
        duplicate = {
            "publication_id": "publication_tiktok_duplicate", "platform": "TikTok", "video_id": "100",
            "actual_publish_url": "https://www.tiktok.com/@creator/video/100?lang=en",
            "actual_account_uid": "account_tiktok",
        }
        self.relations.records["relation_tiktok"]["publications"].append(duplicate)
        with self.store.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO campaign_creator_publish_links("
                "campaign_creator_id,position,publish_link,publication_id,actual_account_uid,platform,video_id,source) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("relation_tiktok", 2, duplicate["actual_publish_url"], duplicate["publication_id"],
                 "account_tiktok", "TikTok", "100", "manual"),
            )
        created = self.batch_service().create("campaign_1")
        self.assertEqual(4, created["total"])
        self.assertEqual(3, created["counts"]["pending"])
        self.assertEqual(1, created["counts"]["skipped"])
        skipped = next(item for item in created["items"] if item["status"] == "skipped")
        self.assertEqual("DUPLICATE_VIDEO_IN_BATCH", skipped["safe_error_code"])

    def test_failed_item_can_be_explicitly_retried_after_batch_completion(self):
        service = self.batch_service()
        created = service.create("campaign_1")
        batch_id = created["batch"]["batch_run_id"]
        executor = service.claim(
            batch_id, created["claim_token"], "chrome-extension://fixture-id",
        )["executor_token"]
        first_item_id = ""
        for _ in range(3):
            item = service.next_item(batch_id, executor, "chrome-extension://fixture-id")["item"]
            first_item_id = first_item_id or str(item["item_id"])
            request_id, token = str(item["capture_code"]).split(".", 1)
            service.submit_result({
                "request_id": request_id, "capability_token": token, "page_url": item["canonical_url"],
                "platform": item["platform"], "video_id": item["video_id"], "capture_status": "failed",
                "safe_error_code": "METRICS_NOT_FOUND", "metrics": self.metrics(None, None, None, None),
                "collector_version": "2.0.1", "contract_version": "publication-capture-v1",
            })
        self.assertEqual("completed", service.status(batch_id)["batch"]["status"])
        retried = service.retry(batch_id, first_item_id)
        self.assertEqual("interrupted", retried["batch"]["status"])
        self.assertEqual("pending", next(row for row in retried["items"] if row["item_id"] == first_item_id)["status"])
        resumed = service.resume(batch_id)
        new_executor = service.claim(
            batch_id, resumed["claim_token"], "chrome-extension://fixture-id",
        )["executor_token"]
        self.assertEqual(first_item_id, service.next_item(
            batch_id, new_executor, "chrome-extension://fixture-id",
        )["item"]["item_id"])

    def test_partial_capture_preserves_zero_missing_provenance_and_history(self):
        request = self.service().create_request("relation_youtube", "publication_youtube")
        result = self.submit(request)
        self.assertEqual("partial", result["attempt"]["capture_status"])
        self.assertEqual(0, result["observation"]["views"])
        self.assertIsNone(result["observation"]["likes"])
        self.assertEqual("fixture", result["attempt"]["field_provenance"]["views"]["source"])
        self.assertEqual(1, len(self.observations.history("publication_youtube")))
        replay = self.submit(request, metrics=self.metrics(views=999))
        self.assertTrue(replay["replayed"])
        self.assertEqual(1, len(self.observations.history("publication_youtube")))
        self.assertEqual(0, self.observations.latest("publication_youtube")["views"])

    def test_all_missing_writes_attempt_but_no_zero_observation(self):
        request = self.service().create_request("relation_instagram", "publication_instagram")
        result = self.submit(request, metrics=self.metrics(None, None, None, None), status="success")
        self.assertEqual("insufficient", result["attempt"]["capture_status"])
        self.assertEqual("none", result["attempt"]["completeness"])
        self.assertIsNone(result["observation"])
        self.assertEqual([], self.observations.history("publication_instagram"))

    def test_one_reliable_field_writes_partial_observation_without_inventing_views(self):
        request = self.service().create_request("relation_instagram", "publication_instagram")
        result = self.submit(
            request,
            metrics=self.metrics(None, 1538, None, None),
            status="partial",
        )
        self.assertEqual("partial", result["attempt"]["capture_status"])
        self.assertIsNone(result["observation"]["views"])
        self.assertEqual(1538, result["observation"]["likes"])
        self.assertIsNone(result["observation"]["comments"])

    def test_wrong_token_video_and_cross_relation_are_rejected(self):
        request = self.service().create_request("relation_tiktok", "publication_tiktok")
        with self.assertRaisesRegex(PublicationCaptureError, "授权无效"):
            self.submit(request, token="wrong")
        with self.assertRaisesRegex(PublicationCaptureError, "目标视频"):
            self.submit(request, page_url="https://www.tiktok.com/@creator/video/101")
        self.relations.records["relation_tiktok"]["publications"][0]["actual_account_uid"] = "account_youtube"
        with self.assertRaisesRegex(PublicationCaptureError, "账号"):
            self.submit(request)
        self.assertEqual([], self.observations.history("publication_tiktok"))

    def test_expired_request_fails_closed_without_observation(self):
        request = self.service().create_request("relation_youtube", "publication_youtube")
        self.now += timedelta(minutes=11)
        result = self.submit(request)
        self.assertEqual("expired", result["attempt"]["capture_status"])
        self.assertIsNone(result["observation"])

    def test_status_check_expires_abandoned_request_and_requires_a_new_request(self):
        request = self.service().create_request("relation_youtube", "publication_youtube")
        self.now += timedelta(minutes=9, seconds=59)
        pending = self.service().get_request(request["request_id"])
        self.assertEqual("pending", pending["attempt"]["capture_status"])
        self.now += timedelta(seconds=1)
        state = self.service().get_request(request["request_id"])
        self.assertEqual("expired", state["attempt"]["capture_status"])
        self.assertEqual("CAPTURE_REQUEST_EXPIRED", state["attempt"]["safe_error_code"])
        self.assertIsNone(state["observation"])
        replay = self.submit(request)
        self.assertTrue(replay["replayed"])
        self.assertIsNone(replay["observation"])

    def test_same_origin_session_rejects_extension_or_cross_site_creation(self):
        sessions = PublicationCaptureSessionStore(now=lambda: self.now)
        with self.assertRaises(PublicationCaptureError):
            sessions.issue({"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}, 8765)
        issued = sessions.issue({"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"}, 8765)
        session = sessions.validate({
            "Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin",
            "Cookie": issued["set_cookie"].split(";", 1)[0],
            "X-KOLConnect-Publication-Capture-CSRF": issued["csrf_token"],
        }, 8765)
        self.assertTrue(session)
        result_path = "/api/extension/publication-capture/result"
        self.assertTrue(allowed_mutation_origin("chrome-extension://test-extension", result_path, 8765))
        self.assertFalse(allowed_mutation_origin("https://evil.example", result_path, 8765))
        self.assertFalse(allowed_mutation_origin("chrome-extension://test-extension", result_path + "/other", 8765))
        batch_path = "/api/extension/publication-capture/batches/batch_1/claim"
        self.assertTrue(allowed_mutation_origin("chrome-extension://test-extension", batch_path, 8765))
        self.assertFalse(allowed_mutation_origin("https://evil.example", batch_path, 8765))
        self.assertTrue(allowed_mutation_origin("chrome-extension://test-extension", "/api/tasks", 8765))
        self.assertFalse(allowed_mutation_origin("https://evil.example", "/api/tasks", 8765))
        self.assertFalse(allowed_mutation_origin("chrome-extension://test-extension", "/api/scrape/start", 8765))


if __name__ == "__main__":
    unittest.main()
