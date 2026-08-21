from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from repositories.task_repository import TaskCsvDocument, TaskRepository


class ReviewStateTransactionTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / f".d4_0a_{uuid.uuid4().hex}"
        self.root.mkdir()
        self.repository = TaskRepository(self.root)
        self.task = self.repository.create_task(["https://www.tiktok.com/@creator"], [], 1)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, review_state=None):
        return self.repository.write_task_documents(
            self.task["id"],
            results=TaskCsvDocument(("url",), ({"url": "https://www.tiktok.com/@creator"},)),
            progress=TaskCsvDocument(("url",), ({"url": "https://www.tiktok.com/@creator"},)),
            modifications=[], metadata_changes={}, review_state=review_state,
        )

    def test_optional_review_state_is_transaction_member_and_legacy_read_is_empty(self):
        self.assertEqual({"version": 1, "rows": {}}, self.repository.read_review_state(self.task["id"]))
        payload = {"version": 1, "rows": {"uid": {"review_state": "approved", "reviewed_at": "2026-01-01T00:00:00Z", "rejection_reason": ""}}}
        self._write(payload)
        self.assertEqual(payload, self.repository.read_review_state(self.task["id"]))

    def test_failed_transaction_does_not_publish_review_state(self):
        paths = self.repository._paths(self.task["id"])
        original = TaskRepository._atomic_write_files
        with mock.patch.object(TaskRepository, "_atomic_write_files", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                self._write({"version": 1, "rows": {"uid": {"review_state": "rejected"}}})
        self.assertFalse(paths["review_state"].exists())
        self.assertEqual({"version": 1, "rows": {}}, self.repository.read_review_state(self.task["id"]))
