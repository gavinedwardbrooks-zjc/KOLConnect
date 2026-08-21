from __future__ import annotations

import contextlib
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from adapters.task_manager_adapter import TaskManagerAdapter
from repositories.task_repository import TaskCsvDocument, TaskRepository
import scraper as scraper_module


class ReviewReadModelTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / f".d4_read_{uuid.uuid4().hex}"
        self.root.mkdir()
        self.lock = mock.patch("repositories.task_repository.shared_storage_lock", lambda: contextlib.nullcontext())
        self.lock.start()
        self.repo = TaskRepository(self.root)
        self.task = self.repo.create_task(["https://www.tiktok.com/@one"], [], 1)
        self.adapter = TaskManagerAdapter(lambda: self.root)

    def tearDown(self):
        self.lock.stop(); shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rows, state=None):
        doc = TaskCsvDocument(tuple(rows[0]), tuple(rows))
        self.repo.write_task_documents(self.task["id"], results=doc, progress=doc, modifications=[], metadata_changes={}, review_state=state)

    def test_legacy_states_eligibility_counts_and_order(self):
        rows = [
            {scraper_module.FIELD_PLATFORM: "TikTok", scraper_module.FIELD_URL: "https://www.tiktok.com/@one", scraper_module.FIELD_SCRAPE_STATUS: "success", scraper_module.FIELD_NAME: "one"},
            {scraper_module.FIELD_PLATFORM: "TikTok", scraper_module.FIELD_URL: "https://www.tiktok.com/@two", scraper_module.FIELD_SCRAPE_STATUS: "failed", scraper_module.FIELD_NAME: "two"},
            {scraper_module.FIELD_PLATFORM: "TikTok", scraper_module.FIELD_URL: "https://www.tiktok.com/@three", scraper_module.FIELD_SCRAPE_STATUS: "missing_data", scraper_module.FIELD_NAME: "three"},
            {scraper_module.FIELD_PLATFORM: "TikTok", scraper_module.FIELD_URL: "https://www.tiktok.com/@four", scraper_module.FIELD_SCRAPE_STATUS: "login_required", scraper_module.FIELD_NAME: "four"},
            {scraper_module.FIELD_PLATFORM: "TikTok", scraper_module.FIELD_URL: "https://www.tiktok.com/@five", scraper_module.FIELD_SCRAPE_STATUS: "platform_error", scraper_module.FIELD_NAME: "five"},
        ]
        self._write(rows)
        data = self.adapter.get_task_results(self.task["id"]).to_response()
        self.assertFalse((self.repo._paths(self.task["id"])["review_state"]).exists())
        self.assertEqual(
            [
                "tiktok|https://www.tiktok.com/@one",
                "tiktok|https://www.tiktok.com/@two",
                "tiktok|https://www.tiktok.com/@three",
                "tiktok|https://www.tiktok.com/@four",
                "tiktok|https://www.tiktok.com/@five",
            ],
            [r["account_uid"] for r in data["records"]],
        )
        self.assertEqual(
            ["partial_success"] * 5,
            [r[scraper_module.FIELD_SCRAPE_STATUS] for r in data["records"]],
        )
        self.assertEqual(
            ["one", "two", "three", "four", "five"],
            [r[scraper_module.FIELD_NAME] for r in data["records"]],
        )
        self.assertEqual(
            ["TikTok"] * 5,
            [r[scraper_module.FIELD_PLATFORM] for r in data["records"]],
        )
        self.assertEqual(
            [
                "https://www.tiktok.com/@one",
                "https://www.tiktok.com/@two",
                "https://www.tiktok.com/@three",
                "https://www.tiktok.com/@four",
                "https://www.tiktok.com/@five",
            ],
            [r[scraper_module.FIELD_URL] for r in data["records"]],
        )
        self.assertEqual([True, False, False, False, False], [r["review_eligible"] for r in data["records"]])
        self.assertEqual("pending", data["records"][0]["review_state"])
        self.assertEqual("", data["records"][0]["reviewed_at"])
        self.assertEqual("", data["records"][0]["rejection_reason"])
        self.assertEqual((1, 0, 1), (data["review_total"], data["reviewed_count"], data["pending_count"]))
        self._write(rows, {"version": 1, "rows": {
            data["records"][1]["account_uid"]: {"review_state": "approved"},
        }})
        persisted = self.adapter.get_task_results(self.task["id"]).to_response()
        self.assertEqual("approved", persisted["records"][1]["review_state"])
        self.assertFalse(persisted["records"][1]["review_eligible"])
        self.assertEqual((1, 0, 1), (persisted["review_total"], persisted["reviewed_count"], persisted["pending_count"]))

    def test_persisted_states_are_exposed_and_counted(self):
        rows = [{scraper_module.FIELD_PLATFORM: "TikTok", scraper_module.FIELD_URL: f"https://www.tiktok.com/@{name}", scraper_module.FIELD_SCRAPE_STATUS: "success", scraper_module.FIELD_NAME: name} for name in ("one", "two", "three")]
        self._write(rows)
        account_uids = [
            record["account_uid"]
            for record in self.adapter.get_task_results(self.task["id"]).to_response()["records"]
        ]
        self.assertTrue(all(account_uids))
        self.assertEqual(len(account_uids), len(set(account_uids)))
        state = {"version": 1, "rows": {account_uids[0]: {"review_state": "approved", "reviewed_at": "2026-01-01T00:00:00Z"}, account_uids[1]: {"review_state": "rejected", "rejection_reason": "duplicate"}}}
        self._write(rows, state)
        data = self.adapter.get_task_results(self.task["id"]).to_response()
        self.assertEqual(["approved", "rejected", "pending"], [r["review_state"] for r in data["records"]])
        self.assertEqual("2026-01-01T00:00:00Z", data["records"][0]["reviewed_at"])
        self.assertEqual("duplicate", data["records"][1]["rejection_reason"])
        self.assertEqual((3, 2, 1), (data["review_total"], data["reviewed_count"], data["pending_count"]))
