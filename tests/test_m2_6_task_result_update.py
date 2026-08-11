from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper
from adapters.task_manager_adapter import TaskManagerAdapter
from ports.creator_port import TaskResultImportCommand
from repositories.task_repository import TaskRepository
from services.creator_service import CreatorService
from services.task_service import TaskService


class FakeCreatorRepository:
    def __init__(self) -> None:
        self.imports: list[tuple[str, list[dict], str, str]] = []
        self.import_error: Exception | None = None

    def importTaskResults(
        self, task_id: str, records: list[dict], *, source: str, imported_at: str
    ) -> dict:
        if self.import_error:
            raise self.import_error
        self.imports.append((task_id, records, source, imported_at))
        return {
            "input_records": len(records),
            "created_creators": 1,
            "created_accounts": 1,
            "updated_accounts": 0,
            "duplicate_records": 0,
            "skipped_failed": 0,
            "skipped_invalid": 0,
            "creator_ids": ["creator-1"],
            "account_ids": ["account-1"],
        }


class CreatorPortSpy:
    def __init__(self, service: CreatorService) -> None:
        self.service = service
        self.prepare_calls = 0
        self.protection_calls = 0
        self.import_calls = 0

    def prepare_task_result_update(self, command):
        self.prepare_calls += 1
        return self.service.prepare_task_result_update(command)

    def commit_task_result_protection(self, task_id, update):
        self.protection_calls += 1
        return self.service.commit_task_result_protection(task_id, update)

    def import_task_results(self, command):
        self.import_calls += 1
        return self.service.import_task_results(command)


class TaskResultUpdateBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.task_repository = TaskRepository(self.tasks_dir)
        self.task_port = TaskManagerAdapter(
            lambda: self.tasks_dir,
            scrape_status_provider=lambda: {"running": False, "task_id": ""},
        )
        self.creator_repository = FakeCreatorRepository()
        self.protection: dict = {}
        self.saved_protection: list[dict] = []
        creator_service = CreatorService(
            lambda: self.creator_repository,
            lambda: self.task_port,
            lambda: self.protection,
            lambda data: self.saved_protection.append(data.copy()),
        )
        self.creator_port = CreatorPortSpy(creator_service)
        self.service = TaskService(
            lambda: self.task_port,
            lambda: self.creator_port,
            lambda: self.task_repository,
        )

        self.task = self.task_repository.create_task(
            ["https://www.instagram.com/example/"], [], 1
        )
        self.task = self.task_repository.update_task(
            self.task["id"],
            status="completed",
            creator_library_import_eligible=True,
        )
        result = scraper.build_result(
            url="https://www.instagram.com/example/",
            platform="Instagram",
            name="Original Name",
            emails=["old@example.test"],
        )
        self.row = scraper.result_to_row(result)
        fields = list(self.row)
        self.task_repository.write_results(self.task["id"], [self.row], fields)
        self.task_repository.write_progress(self.task["id"], [self.row], fields)
        self.account_uid = scraper.build_creator_uid(result)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_update_uses_repository_creator_port_and_preserves_response(self):
        response = self.service.update_task_results(
            self.task["id"],
            self.account_uid,
            {scraper.FIELD_EMAIL: "new@example.test"},
        )

        self.assertEqual(
            set(response),
            {
                "task_id",
                "account_uid",
                "modified_fields",
                "data_status",
                "modified_at",
                "creator_library_import",
            },
        )
        self.assertEqual(response["task_id"], self.task["id"])
        self.assertEqual(response["account_uid"], self.account_uid)
        self.assertEqual(response["data_status"], "待同步")
        self.assertEqual(
            response["modified_fields"][scraper.FIELD_EMAIL],
            {"old": "old@example.test", "new": "new@example.test"},
        )
        self.assertEqual(response["creator_library_import"]["status"], "success")
        self.assertEqual(self.creator_port.prepare_calls, 1)
        self.assertEqual(self.creator_port.protection_calls, 1)
        self.assertEqual(self.creator_port.import_calls, 1)

        result_row = self.task_repository.read_results(self.task["id"])[0]
        progress_row = self.task_repository.read_progress(self.task["id"])[0]
        self.assertEqual(result_row[scraper.FIELD_EMAIL], "new@example.test")
        self.assertEqual(progress_row[scraper.FIELD_EMAIL], "new@example.test")
        self.assertEqual(len(self.task_repository.read_modifications(self.task["id"])), 1)
        stored_task = self.task_repository.get_task(self.task["id"])
        self.assertEqual(stored_task["creator_library_creator_ids"], ["creator-1"])
        self.assertEqual(stored_task["creator_library_account_ids"], ["account-1"])
        self.assertTrue(self.saved_protection)

    def test_creator_import_remains_idempotent_for_same_input(self):
        command = TaskResultImportCommand(
            task_id=self.task["id"],
            task=self.task,
            rows=(self.row,),
            allowed_statuses=("completed",),
        )
        first = self.creator_port.service.import_task_results(command)
        second = self.creator_port.service.import_task_results(command)

        self.assertEqual(dict(first.response), dict(second.response))
        self.assertEqual(first.creator_ids, second.creator_ids)
        self.assertEqual(first.account_ids, second.account_ids)

    def test_csv_update_failure_propagates_before_creator_side_effects(self):
        with mock.patch.object(
            self.task_repository,
            "write_review_update",
            side_effect=OSError("disk unavailable"),
        ):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                self.service.update_task_results(
                    self.task["id"],
                    self.account_uid,
                    {scraper.FIELD_EMAIL: "new@example.test"},
                )

        self.assertEqual(self.creator_port.protection_calls, 0)
        self.assertEqual(self.creator_port.import_calls, 0)
        self.assertEqual(
            self.task_repository.read_results(self.task["id"])[0][scraper.FIELD_EMAIL],
            "old@example.test",
        )

    def test_creator_import_failure_keeps_review_and_response_contract(self):
        self.creator_repository.import_error = ValueError("workbook unavailable")

        response = self.service.update_task_results(
            self.task["id"],
            self.account_uid,
            {scraper.FIELD_EMAIL: "new@example.test"},
        )

        self.assertEqual(
            response["creator_library_import"],
            {"status": "failed", "error": "workbook unavailable"},
        )
        self.assertEqual(
            self.task_repository.read_results(self.task["id"])[0][scraper.FIELD_EMAIL],
            "new@example.test",
        )
        self.assertEqual(
            self.task_repository.get_task(self.task["id"])["status"], "completed"
        )

    def test_creator_protection_rules_are_not_in_task_service(self):
        source = (APP_DIR / "services" / "task_service.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        string_values = {
            node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
        }
        self.assertNotIn(scraper.FIELD_NAME, string_values)
        self.assertNotIn(scraper.FIELD_EMAIL, string_values)
        self.assertNotIn(scraper.FIELD_FOLLOWER_COUNT, string_values)
        self.assertNotIn("WhatsApp", string_values)


if __name__ == "__main__":
    unittest.main()
