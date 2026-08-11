from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import task_manager
import scraper
from adapters.task_manager_adapter import TaskManagerAdapter
from ports.task_port import RetryFailedResultsCommand, TaskLinksUpdateCommand
from repositories.task_repository import TaskRepository


class TaskRepositoryCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.repository = TaskRepository(self.tasks_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reads_task_created_by_legacy_manager(self):
        legacy_task = task_manager.create_task(
            self.tasks_dir,
            ["https://www.instagram.com/example/"],
            ["invalid"],
            2,
            name="Legacy task",
            platforms=["instagram"],
            filtered_links=[{"url": "invalid", "reason": "unsupported"}],
        )

        self.assertEqual(self.repository.get_task(legacy_task["id"]), legacy_task)
        self.assertEqual(
            self.repository.read_links(legacy_task["id"]),
            ["https://www.instagram.com/example/"],
        )
        self.assertEqual(
            self.repository.read_filtered_links(legacy_task["id"]),
            [{"url": "invalid", "reason": "unsupported"}],
        )

    def test_created_task_is_readable_by_legacy_manager(self):
        task = self.repository.create_task(
            ["https://www.tiktok.com/@example"],
            [],
            1,
            name="Repository task",
            target_platform="TikTok",
            platforms=["tiktok"],
            platform_summary={"TikTok": 1},
        )

        legacy_task, paths = task_manager.load_task(self.tasks_dir, task["id"])
        self.assertEqual(legacy_task, task)
        self.assertEqual(paths["links"].read_text(encoding="utf-8"),
                         "https://www.tiktok.com/@example\n")
        self.assertEqual(json.loads(paths["metadata"].read_text(encoding="utf-8")), task)
        self.assertEqual(json.loads(paths["filtered_links"].read_text(encoding="utf-8")), [])

    def test_metadata_update_remains_legacy_compatible(self):
        task = self.repository.create_task(
            ["https://www.youtube.com/@example"], [], 1
        )
        updated = self.repository.update_task(
            task["id"], status="running", completed_count=1
        )

        legacy_task, _paths = task_manager.load_task(self.tasks_dir, task["id"])
        self.assertEqual(legacy_task, updated)
        self.assertEqual(legacy_task["status"], "running")
        self.assertEqual(legacy_task["completed_count"], 1)

    def test_manages_task_scoped_csv_and_json_files(self):
        task = self.repository.create_task(
            ["https://www.instagram.com/example/"], [], 1
        )
        root = self.tasks_dir / task["id"]
        self.repository.write_results(
            task["id"],
            [{"url": "profile", "status": "success"}],
            ["url", "status"],
        )
        self.repository.write_progress(
            task["id"],
            [{"url": "profile", "status": "完成"}],
            ["url", "status"],
        )
        self.repository.write_modifications(task["id"], [{"field": "email"}])
        self.repository.write_sync_result(task["id"], {"status": "success"})

        self.assertEqual(self.repository.read_results(task["id"])[0]["status"], "success")
        self.assertEqual(self.repository.read_progress(task["id"])[0]["status"], "完成")
        self.assertEqual(
            self.repository.read_modifications(task["id"]), [{"field": "email"}]
        )
        self.assertEqual(
            self.repository.read_sync_result(task["id"]), {"status": "success"}
        )
        self.assertTrue((root / ".sync_result.json").exists())

    def test_empty_progress_file_keeps_legacy_tolerant_read(self):
        task = self.repository.create_task(
            ["https://www.instagram.com/example/"], [], 1
        )
        (self.tasks_dir / task["id"] / "progress.csv").write_text("", encoding="utf-8")

        self.assertEqual(self.repository.read_progress(task["id"]), [])


class TaskRepositoryBoundaryTests(unittest.TestCase):
    def test_repository_has_no_forbidden_imports(self):
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
            {"server", "http_handlers", "task_manager", "scraper", "creator_repository"}
            .isdisjoint(imported)
        )

    def test_adapter_has_no_direct_filesystem_storage(self):
        source = (APP_DIR / "adapters" / "task_manager_adapter.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertTrue({"task_manager", "json", "csv"}.isdisjoint(imported))
        self.assertNotIn("open", called_names)
        self.assertTrue(
            {
                "read_text",
                "write_text",
                "read_bytes",
                "write_bytes",
                "mkdir",
                "rmtree",
                "unlink",
            }.isdisjoint(called_attributes)
        )


class TaskManagerAdapterRepositoryCutoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.repository = TaskRepository(self.tasks_dir)
        self.adapter = TaskManagerAdapter(lambda: self.tasks_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_task(self) -> dict:
        return self.repository.create_task(
            ["https://www.instagram.com/example/"], [], 1
        )

    def test_mutations_and_lifecycle_use_repository_storage(self):
        task = self._create_task()
        task_id = task["id"]

        self.adapter.rename_task(task_id, "Renamed")
        self.adapter.update_task_links(
            task_id,
            TaskLinksUpdateCommand(
                action="add", url="https://www.tiktok.com/@example"
            ),
        )
        stopped = self.adapter.stop_task(task_id)
        resumed = self.adapter.resume_task(task_id)

        stored = self.repository.get_task(task_id)
        self.assertEqual(stored["name"], "Renamed")
        self.assertEqual(stored["status"], "stopped")
        self.assertEqual(stopped.status, "stopped")
        self.assertEqual(resumed.status, "stopped")
        self.assertEqual(
            self.repository.read_links(task_id),
            [
                "https://www.instagram.com/example/",
                "https://www.tiktok.com/@example",
            ],
        )

        self.adapter.delete_task(task_id)
        with self.assertRaisesRegex(ValueError, "任务不存在"):
            self.repository.get_task(task_id)

    def test_retry_reads_results_and_updates_metadata_through_repository(self):
        task = self._create_task()
        row = scraper.result_to_row(
            scraper.build_result(
                url="https://www.instagram.com/example/",
                platform="Instagram",
                scrape_status="failed",
                status_reason="selenium_exception",
            )
        )
        self.repository.write_results(task["id"], [row], list(row))

        result = self.adapter.retry_failed_results(
            task["id"], RetryFailedResultsCommand()
        ).to_response()

        stored = self.repository.get_task(task["id"])
        self.assertEqual(result["retried_count"], 1)
        self.assertEqual(stored["status"], "created")
        self.assertEqual(
            stored["retry_requested_urls"],
            ["https://www.instagram.com/example/"],
        )


if __name__ == "__main__":
    unittest.main()
