from __future__ import annotations

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
from repositories.task_repository import TaskCsvDocument, TaskRepository
from services.creator_service import CreatorService
from services.task_service import TaskService


class SyncCreatorPort:
    def __init__(self, service: CreatorService) -> None:
        self.service = service
        self.prepare_calls = 0
        self.execute_calls = 0

    def prepare_four_table_sync(self, command):
        self.prepare_calls += 1
        return self.service.prepare_four_table_sync(command)

    def execute_four_table_sync(self, prepared):
        self.execute_calls += 1
        return self.service.execute_four_table_sync(prepared)


class SyncFourTablesBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.repository = TaskRepository(self.tasks_dir)
        self.task_port = TaskManagerAdapter(lambda: self.tasks_dir)
        self.protection: dict = {}
        self.saved_protection: list[dict] = []
        creator_service = CreatorService(
            lambda: object(),
            lambda: self.task_port,
            lambda: self.protection,
            lambda data: self.saved_protection.append(dict(data)),
            four_table_config_provider=lambda: {"configured": True},
        )
        self.creator_port = SyncCreatorPort(creator_service)
        self.sync_errors: list[tuple[str, str]] = []
        self.service = TaskService(
            lambda: self.task_port,
            lambda: self.creator_port,
            lambda: self.repository,
            sync_error_logger=lambda task_id, exc: self.sync_errors.append(
                (task_id, str(exc))
            ),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_task(self, *, scrape_status: str = "success") -> dict:
        url = "https://www.instagram.com/sync-demo/"
        task = self.repository.create_task([url], [], 1)
        task = self.repository.update_task(task["id"], status="completed")
        result = scraper.build_result(
            url=url,
            platform="Instagram",
            name="Sync Demo",
            emails=["sync@example.test"],
            scrape_status=scrape_status,
        )
        row = scraper.result_to_row(result)
        self.repository.write_task_documents(
            task["id"],
            results=TaskCsvDocument(tuple(scraper.OUTPUT_FIELDS), (row,)),
            progress=TaskCsvDocument(tuple(scraper.PROGRESS_FIELDS), (row,)),
            modifications=[],
            metadata_changes={"status": "completed"},
        )
        return self.repository.get_task(task["id"])

    @staticmethod
    def _summary(*, errors=None) -> dict:
        return {
            "created_creators": 1,
            "created_accounts": 1,
            "updated_accounts": 0,
            "updated_creators": 0,
            "skipped": 0,
            "errors": list(errors or []),
            "sync_logs": [],
        }

    def test_sync_success_preserves_response_and_metadata(self):
        task = self._create_task()
        with mock.patch.object(
            scraper,
            "push_to_feishu_four_tables",
            return_value=self._summary(),
        ):
            response = self.service.sync_four_tables(task["id"])

        stored = self.repository.get_task(task["id"])
        self.assertEqual(response["sync_status"], "success")
        self.assertEqual(response["record_count"], 1)
        self.assertEqual(response["sync_errors"], [])
        self.assertEqual(response["sync_warnings"], [])
        self.assertEqual(stored["sync_status"], "success")
        self.assertEqual(stored["sync_summary"], response["sync_summary"])
        self.assertEqual(stored["last_sync_source"], "系统抓取")
        self.assertEqual(self.creator_port.prepare_calls, 1)
        self.assertEqual(self.creator_port.execute_calls, 1)

    def test_partial_remote_failure_preserves_warning_and_error(self):
        task = self._create_task(scrape_status="partial_success")
        with mock.patch.object(
            scraper,
            "push_to_feishu_four_tables",
            return_value=self._summary(errors=["remote row failed"]),
        ):
            response = self.service.sync_four_tables(task["id"])

        stored = self.repository.get_task(task["id"])
        self.assertEqual(response["sync_status"], "failed")
        self.assertEqual(response["sync_errors"], ["remote row failed"])
        self.assertEqual(response["sync_summary"]["partial_records"], 1)
        self.assertEqual(len(response["sync_warnings"]), 1)
        self.assertEqual(stored["sync_errors"], ["remote row failed"])

    def test_sync_exception_is_aggregated_and_persisted(self):
        task = self._create_task()
        with mock.patch.object(
            scraper,
            "push_to_feishu_four_tables",
            side_effect=RuntimeError("Feishu unavailable"),
        ):
            response = self.service.sync_four_tables(task["id"])

        stored = self.repository.get_task(task["id"])
        self.assertEqual(response["sync_status"], "failed")
        self.assertEqual(response["sync_errors"], ["Feishu unavailable"])
        self.assertEqual(response["sync_summary"]["errors"], 1)
        self.assertEqual(stored["sync_status"], "failed")
        self.assertEqual(stored["sync_errors"], ["Feishu unavailable"])
        self.assertEqual(self.sync_errors, [(task["id"], "Feishu unavailable")])

    def test_duplicate_sync_remains_idempotent(self):
        task = self._create_task()
        with mock.patch.object(
            scraper,
            "push_to_feishu_four_tables",
            return_value=self._summary(),
        ) as sync:
            first = self.service.sync_four_tables(task["id"])
            second = self.service.sync_four_tables(task["id"])

        self.assertEqual(first, second)
        self.assertEqual(sync.call_count, 2)
        stored = self.repository.get_task(task["id"])
        self.assertEqual(stored["sync_summary"], second["sync_summary"])
        self.assertEqual(stored["sync_errors"], [])


if __name__ == "__main__":
    unittest.main()
