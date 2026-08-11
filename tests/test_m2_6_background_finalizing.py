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
import server
from adapters.task_manager_adapter import TaskManagerAdapter
from ports.creator_port import CreatorImportSummary
from repositories.task_repository import TaskCsvDocument, TaskRepository
from repository_factory import get_active_repository_factory
from services.task_service import TaskService


class FinalizingCreatorPort:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.import_calls = 0
        self.commands = []

    def import_task_results(self, command):
        self.import_calls += 1
        self.commands.append(command)
        if self.error:
            raise self.error
        return CreatorImportSummary(
            input_records=len(command.items),
            created_creators=1,
            created_accounts=1,
            updated_accounts=0,
            duplicate_records=0,
            skipped_failed=0,
            skipped_invalid=0,
            creator_ids=("creator-1",),
            account_ids=("account-1",),
        )


class BackgroundFinalizingBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.tasks_dir = self.root / "tasks"
        self.repository = TaskRepository(self.tasks_dir)
        self.task_port = TaskManagerAdapter(lambda: self.tasks_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_finalizing_task(self) -> dict:
        url = "https://www.instagram.com/finalizing-demo/"
        task = self.repository.create_task([url], [], 1)
        task = self.repository.update_task(task["id"], status="finalizing")
        row = scraper.result_to_row(
            scraper.build_result(
                url=url,
                platform="Instagram",
                name="Finalizing Demo",
                emails=["finalizing@example.test"],
                status="completed",
            )
        )
        self.repository.write_task_documents(
            task["id"],
            results=TaskCsvDocument(tuple(scraper.OUTPUT_FIELDS), (row,)),
            progress=TaskCsvDocument(tuple(scraper.PROGRESS_FIELDS), (row,)),
            modifications=[],
            metadata_changes={"status": "finalizing"},
        )
        return self.repository.get_task(task["id"])

    def _service(self, creator_port, errors=None) -> TaskService:
        errors = errors if errors is not None else []
        return TaskService(
            lambda: self.task_port,
            lambda: creator_port,
            lambda: self.repository,
            finalization_error_logger=lambda task_id, exc: errors.append(
                (task_id, str(exc))
            ),
        )

    def test_finalizing_success_reads_repository_imports_and_links(self):
        task = self._create_finalizing_task()
        creator_port = FinalizingCreatorPort()

        result = self._service(creator_port).finalize_background_task(task["id"])

        stored = self.repository.get_task(task["id"])
        self.assertEqual(result.status, "completed")
        self.assertEqual(stored["status"], "completed")
        self.assertTrue(stored["finished_at"])
        self.assertEqual(stored["creator_library_creator_ids"], ["creator-1"])
        self.assertEqual(stored["creator_library_account_ids"], ["account-1"])
        self.assertEqual(creator_port.import_calls, 1)
        item = creator_port.commands[0].items[0]
        self.assertEqual(item.creator_name, "Finalizing Demo")
        self.assertEqual(item.email, "finalizing@example.test")

    def test_creator_import_failure_marks_task_failed(self):
        task = self._create_finalizing_task()
        errors = []
        creator_port = FinalizingCreatorPort(OSError("workbook unavailable"))

        result = self._service(creator_port, errors).finalize_background_task(
            task["id"]
        )

        stored = self.repository.get_task(task["id"])
        self.assertEqual(result.status, "failed")
        self.assertEqual(stored["status"], "failed")
        self.assertTrue(stored["finished_at"])
        self.assertEqual(stored["creator_library_import_error"], "workbook unavailable")
        self.assertIn("workbook unavailable", stored["last_error"])
        self.assertEqual(errors, [(task["id"], "workbook unavailable")])

    def test_repeated_finalizing_does_not_repeat_creator_import(self):
        task = self._create_finalizing_task()
        creator_port = FinalizingCreatorPort()
        service = self._service(creator_port)

        first = service.finalize_background_task(task["id"])
        second = service.finalize_background_task(task["id"])

        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertEqual(creator_port.import_calls, 1)

    def test_background_scope_is_new_and_does_not_reuse_http_context(self):
        workbook = self.root / "Creator_Library.xlsx"
        tasks_dir = self.root / "tasks"
        with (
            mock.patch.object(server, "TASKS_DIR", tasks_dir),
            mock.patch.object(
                server,
                "_creator_library_workbook_path",
                return_value=workbook,
            ),
        ):
            self.assertIsNone(get_active_repository_factory())
            with server.background_task_service_scope() as first:
                self.assertIsNone(get_active_repository_factory())
            with server.background_task_service_scope() as second:
                self.assertIsNone(get_active_repository_factory())
        self.assertIsNot(first, second)
        self.assertIsNone(get_active_repository_factory())

    def test_task_repository_has_no_creator_row_mapping(self):
        source = (APP_DIR / "repositories" / "task_repository.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            {"scraper", "creator_repository", "creator_port"}.isdisjoint(imported)
        )
        self.assertNotIn("map_task_rows_for_creator_library", source)


if __name__ == "__main__":
    unittest.main()
