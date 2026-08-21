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
from ports.creator_port import CreatorImportResult, PreparedTaskResultUpdate
from repositories.task_repository import TaskCsvDocument, TaskRepository
from services.task_service import TaskReviewError, TaskService


class CreatorPortSpy:
    def __init__(self) -> None:
        self.import_calls = 0
        self.protection_calls = 0
        self.import_failure: Exception | None = None
        self.last_rows = ()

    def prepare_task_result_update(self, command):
        allowed = {scraper_module.FIELD_NAME, scraper_module.FIELD_EMAIL}
        if set(command.fields) - allowed:
            raise ValueError("unsupported field")
        result_rows = [dict(row) for row in command.result_rows]
        progress_rows = [dict(row) for row in command.progress_rows]
        updates = {key: str(value or "") for key, value in command.fields.items()}
        for rows in (result_rows, progress_rows):
            for row in rows:
                result = scraper_module.row_to_result(dict(row))
                if scraper_module.build_creator_uid(result) == command.account_uid:
                    row.update(updates)
        return PreparedTaskResultUpdate(
            account_uid=command.account_uid,
            modified_fields={key: {"old": "", "new": value} for key, value in updates.items()},
            updated_at=command.updated_at,
            data_status="待同步",
            result_fieldnames=command.result_fieldnames,
            result_rows=tuple(result_rows),
            progress_fieldnames=command.progress_fieldnames,
            progress_rows=tuple(progress_rows),
            protection_values=updates,
            protection_source="审核修改",
        )

    def commit_task_result_protection(self, _task_id, _prepared) -> None:
        self.protection_calls += 1

    def import_task_results(self, command):
        self.import_calls += 1
        self.last_rows = command.rows
        if self.import_failure:
            raise self.import_failure
        return CreatorImportResult(
            response={"status": "success", "created_creators": 1, "created_accounts": 1},
            imported_at="2026-01-01T00:00:00Z",
            creator_ids=("creator_one",),
            account_ids=("account_one",),
            summary={"created_creators": 1, "created_accounts": 1},
        )


class FinalReviewTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / f".d4_final_{uuid.uuid4().hex}"
        self.root.mkdir()
        self.lock = mock.patch("repositories.task_repository.shared_storage_lock", lambda: contextlib.nullcontext())
        self.lock.start()
        self.repository = TaskRepository(self.root)
        self.task = self.repository.create_task(["https://www.tiktok.com/@one"], [], 1)
        self.task = self.repository.update_task(
            self.task["id"], status="completed", creator_library_import_eligible=True
        )
        self.rows = [
            {
                scraper_module.FIELD_PLATFORM: "TikTok",
                scraper_module.FIELD_URL: "https://www.tiktok.com/@one",
                scraper_module.FIELD_NAME: "Original",
                scraper_module.FIELD_EMAIL: "old@example.test",
                scraper_module.FIELD_SCRAPE_STATUS: "success",
            },
            {
                scraper_module.FIELD_PLATFORM: "TikTok",
                scraper_module.FIELD_URL: "https://www.tiktok.com/@failed",
                scraper_module.FIELD_NAME: "Failed",
                scraper_module.FIELD_SCRAPE_STATUS: "failed",
            },
        ]
        document = TaskCsvDocument(tuple(self.rows[0]), tuple(self.rows))
        self.repository.write_task_documents(self.task["id"], results=document, progress=document, modifications=[], metadata_changes={})
        self.adapter = TaskManagerAdapter(lambda: self.root)
        self.creator = CreatorPortSpy()
        self.service = TaskService(lambda: self.adapter, lambda: self.creator, lambda: self.repository)
        self.records = self.service.get_task_results(self.task["id"])["records"]
        self.uids = {record[scraper_module.FIELD_NAME]: record["account_uid"] for record in self.records}

    def tearDown(self) -> None:
        self.lock.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def assert_error(self, code, callback):
        with self.assertRaises(TaskReviewError) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def test_approve_is_reload_safe_and_idempotent(self) -> None:
        first = self.service.approve_task_result(self.task["id"], self.uids["Original"])
        second = self.service.approve_task_result(self.task["id"], self.uids["Original"])
        self.assertEqual("approved", first["review_state"])
        self.assertTrue(first["reviewed_at"])
        self.assertEqual("", first["rejection_reason"])
        self.assertEqual((1, 1, 0), (first["review_total"], first["reviewed_count"], first["pending_count"]))
        self.assertEqual(first["reviewed_at"], second["reviewed_at"])
        self.assertEqual(1, self.creator.import_calls)
        reloaded = TaskManagerAdapter(lambda: self.root).get_task_results(self.task["id"]).to_response()
        self.assertEqual("approved", reloaded["records"][0]["review_state"])
        self.assertEqual(first["reviewed_at"], reloaded["records"][0]["reviewed_at"])
        metadata = self.repository.get_task(self.task["id"])
        self.assertEqual(["creator_one"], metadata["creator_library_creator_ids"])
        self.assertEqual(["account_one"], metadata["creator_library_account_ids"])

    def test_edit_approve_writes_edits_and_review_state_together(self) -> None:
        self.assert_error(
            "REVIEW_FIELDS_INVALID",
            lambda: self.service.edit_approve_task_result(self.task["id"], self.uids["Original"], {"bad": "x"}),
        )
        result = self.service.edit_approve_task_result(
            self.task["id"], self.uids["Original"],
            {scraper_module.FIELD_NAME: "Edited", scraper_module.FIELD_EMAIL: "new@example.test"},
        )
        self.assertEqual("approved", result["review_state"])
        self.assertEqual(1, self.creator.protection_calls)
        self.assertEqual(1, self.creator.import_calls)
        row = self.repository.read_results(self.task["id"])[0]
        self.assertEqual("Edited", row[scraper_module.FIELD_NAME])
        self.assertEqual("new@example.test", row[scraper_module.FIELD_EMAIL])
        self.assertEqual("Edited", self.creator.last_rows[0][scraper_module.FIELD_NAME])

    def test_conflicts_non_reviewable_and_partial_import_failure(self) -> None:
        self.service.reject_task_result(self.task["id"], self.uids["Original"])
        self.assert_error("REVIEW_TRANSITION_CONFLICT", lambda: self.service.approve_task_result(self.task["id"], self.uids["Original"]))
        self.assert_error("REVIEW_RESULT_NOT_ELIGIBLE", lambda: self.service.approve_task_result(self.task["id"], self.uids["Failed"]))

        task = self.repository.create_task(["https://www.tiktok.com/@partial"], [], 1)
        task = self.repository.update_task(task["id"], status="completed", creator_library_import_eligible=True)
        row = dict(self.rows[0]); row[scraper_module.FIELD_URL] = "https://www.tiktok.com/@partial"; row[scraper_module.FIELD_NAME] = "Partial"
        document = TaskCsvDocument(tuple(row), (row,))
        self.repository.write_task_documents(task["id"], results=document, progress=document, modifications=[], metadata_changes={})
        partial_uid = self.adapter.get_task_results(task["id"]).to_response()["records"][0]["account_uid"]
        self.creator.import_failure = RuntimeError("workbook unavailable")
        failure = self.assert_error("REVIEW_CREATOR_MUTATION_FAILED", lambda: self.service.approve_task_result(task["id"], partial_uid))
        self.assertEqual(502, failure.status)
        self.assertEqual("approved", failure.details["review"]["review_state"])

    def test_created_task_approval_does_not_import(self) -> None:
        self.repository.update_task(self.task["id"], status="created")
        result = self.service.approve_task_result(self.task["id"], self.uids["Original"])
        self.assertEqual("approved", result["review_state"])
        self.assertIsNone(result["creator_library_import"])
        self.assertEqual(0, self.creator.import_calls)


if __name__ == "__main__":
    unittest.main()
