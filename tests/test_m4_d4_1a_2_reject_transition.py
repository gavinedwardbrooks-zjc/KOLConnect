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

import scraper as scraper_module
from adapters.task_manager_adapter import TaskManagerAdapter
from http_handlers import task_handler
from repositories.task_repository import TaskCsvDocument, TaskRepository
from services.task_service import TaskReviewError, TaskService


class FakeHandler:
    def __init__(self) -> None:
        self.response = None

    def _json(self, data, status=200) -> None:
        self.response = (status, data)


class RejectTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / f".d4_reject_{uuid.uuid4().hex}"
        self.root.mkdir()
        self.lock = mock.patch(
            "repositories.task_repository.shared_storage_lock",
            lambda: contextlib.nullcontext(),
        )
        self.lock.start()
        self.repository = TaskRepository(self.root)
        self.task = self.repository.create_task(
            ["https://www.tiktok.com/@normal"], [], 1
        )
        self.adapter = TaskManagerAdapter(lambda: self.root)
        self.service = TaskService(
            lambda: self.adapter,
            lambda: None,
            lambda: self.repository,
        )
        self.rows = [
            self._row("normal", "success"),
            self._row("failed", "failed"),
            self._row("missing", "missing_data"),
            self._row("login", "login_required"),
            self._row("platform", "platform_error"),
        ]
        self._write(self.rows)
        self.records = self.service.get_task_results(self.task["id"])["records"]
        self.uids = {record[scraper_module.FIELD_NAME]: record["account_uid"] for record in self.records}

    def tearDown(self) -> None:
        self.lock.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def _row(name: str, scrape_status: str) -> dict[str, str]:
        return {
            scraper_module.FIELD_PLATFORM: "TikTok",
            scraper_module.FIELD_URL: f"https://www.tiktok.com/@{name}",
            scraper_module.FIELD_NAME: name,
            scraper_module.FIELD_SCRAPE_STATUS: scrape_status,
            scraper_module.FIELD_RETRY_COUNT: "2" if scrape_status != "success" else "0",
        }

    def _write(self, rows, review_state=None) -> None:
        document = TaskCsvDocument(tuple(rows[0]), tuple(rows))
        self.repository.write_task_documents(
            self.task["id"],
            results=document,
            progress=document,
            modifications=[],
            metadata_changes={},
            review_state=review_state,
        )

    def _reject(self, uid: str, reason=None) -> dict:
        return self.service.reject_task_result(self.task["id"], uid, reason)

    def assert_review_error(self, code: str, callback) -> TaskReviewError:
        with self.assertRaises(TaskReviewError) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def test_pending_reject_persists_reload_and_preserves_task_data(self) -> None:
        before_rows = self.repository.read_results(self.task["id"])
        before_progress = self.repository.read_progress(self.task["id"])
        before_task = self.repository.get_task(self.task["id"])
        result = self._reject(self.uids["normal"], "not a fit")

        self.assertEqual("rejected", result["review_state"])
        self.assertTrue(result["reviewed_at"])
        self.assertEqual("not a fit", result["rejection_reason"])
        self.assertEqual((1, 1, 0), (result["review_total"], result["reviewed_count"], result["pending_count"]))
        self.assertEqual(before_rows, self.repository.read_results(self.task["id"]))
        self.assertEqual(before_progress, self.repository.read_progress(self.task["id"]))
        self.assertEqual(before_task["retry_round"], self.repository.get_task(self.task["id"])["retry_round"])

        reloaded = TaskService(
            lambda: TaskManagerAdapter(lambda: self.root),
            lambda: None,
            lambda: TaskRepository(self.root),
        ).get_task_results(self.task["id"])
        record = next(item for item in reloaded["records"] if item["account_uid"] == self.uids["normal"])
        self.assertEqual("rejected", record["review_state"])
        self.assertEqual(result["reviewed_at"], record["reviewed_at"])
        self.assertEqual("not a fit", record["rejection_reason"])
        self.assertEqual("partial_success", record[scraper_module.FIELD_SCRAPE_STATUS])

    def test_repeated_reject_is_idempotent_and_can_replace_nonempty_reason(self) -> None:
        first = self._reject(self.uids["normal"], "first reason")
        repeated = self._reject(self.uids["normal"])
        blank = self._reject(self.uids["normal"], "  ")
        replacement = self._reject(self.uids["normal"], "replacement reason")

        self.assertEqual(first["reviewed_at"], repeated["reviewed_at"])
        self.assertEqual(first["reviewed_at"], blank["reviewed_at"])
        self.assertEqual("first reason", repeated["rejection_reason"])
        self.assertEqual("first reason", blank["rejection_reason"])
        self.assertEqual("replacement reason", replacement["rejection_reason"])

    def test_non_reviewable_and_approved_rows_fail_closed(self) -> None:
        for name in ("failed", "missing", "login", "platform"):
            self.assert_review_error(
                "REVIEW_RESULT_NOT_ELIGIBLE", lambda name=name: self._reject(self.uids[name])
            )
        self.assertFalse(self.repository._paths(self.task["id"])["review_state"].exists())

        self._write(self.rows, {"version": 1, "rows": {
            self.uids["normal"]: {"review_state": "approved", "reviewed_at": "2026-01-01T00:00:00Z"},
        }})
        conflict = self.assert_review_error(
            "REVIEW_TRANSITION_CONFLICT", lambda: self._reject(self.uids["normal"], "no")
        )
        self.assertEqual(409, conflict.status)
        state = self.repository.read_review_state(self.task["id"])["rows"][self.uids["normal"]]
        self.assertEqual("approved", state["review_state"])
        self.assertEqual("2026-01-01T00:00:00Z", state["reviewed_at"])

    def test_atomic_failure_does_not_publish_rejection(self) -> None:
        with mock.patch.object(
            self.repository, "write_task_documents", side_effect=OSError("disk unavailable")
        ):
            failure = self.assert_review_error(
                "REVIEW_PERSISTENCE_FAILED", lambda: self._reject(self.uids["normal"])
            )
        self.assertEqual(500, failure.status)
        self.assertFalse(self.repository._paths(self.task["id"])["review_state"].exists())

    def test_endpoint_contract(self) -> None:
        def request(payload, task_id=None):
            handler = FakeHandler()
            handled = task_handler.handle(
                handler,
                {
                    "method": "POST",
                    "path": f"/api/tasks/{task_id or self.task['id']}/results/review",
                    "get_payload": lambda: payload,
                },
                {"services": {"task": self.service}},
            )
            self.assertTrue(handled)
            return handler.response

        status, body = request({"account_uid": self.uids["normal"], "action": "reject"})
        self.assertEqual(200, status)
        self.assertTrue(body["ok"])
        self.assertEqual("rejected", body["review_state"])
        for payload, code in (
            ({"action": "reject"}, "REVIEW_ACCOUNT_UID_REQUIRED"),
            ({"account_uid": self.uids["normal"]}, "REVIEW_ACTION_REQUIRED"),
            ({"account_uid": self.uids["normal"], "action": "unknown"}, "REVIEW_ACTION_UNSUPPORTED"),
            ({"account_uid": "missing", "action": "reject"}, "REVIEW_RESULT_NOT_FOUND"),
            ({"account_uid": self.uids["failed"], "action": "reject"}, "REVIEW_RESULT_NOT_ELIGIBLE"),
        ):
            status, body = request(payload)
            self.assertEqual(code, body["error"])
            self.assertGreaterEqual(status, 400)

        status, body = request(
            {"account_uid": self.uids["normal"], "action": "reject"},
            "task_20260101T000000Z_deadbeef",
        )
        self.assertEqual((404, "TASK_NOT_FOUND"), (status, body["error"]))

        self._write(self.rows, {"version": 1, "rows": {
            self.uids["normal"]: {"review_state": "approved", "reviewed_at": "2026-01-01T00:00:00Z"},
        }})
        status, body = request({"account_uid": self.uids["normal"], "action": "reject"})
        self.assertEqual((409, "REVIEW_TRANSITION_CONFLICT"), (status, body["error"]))


if __name__ == "__main__":
    unittest.main()
