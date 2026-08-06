from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import server


class FinishedProcess:
    def __init__(self) -> None:
        self.stdout = iter(())

    def wait(self) -> int:
        return 0

    def poll(self) -> int:
        return 0


class TaskLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.tasks_patch = mock.patch.object(server, "TASKS_DIR", self.tasks_dir)
        self.tasks_patch.start()
        self.reset_job()
        self.task = server.task_manager.create_task(
            self.tasks_dir,
            ["https://www.tiktok.com/@lifecycle_test"],
            [],
            1,
            name="Lifecycle test",
        )

    def tearDown(self) -> None:
        self.reset_job()
        self.tasks_patch.stop()
        self.temp_dir.cleanup()

    def reset_job(self) -> None:
        with server.SCRAPE_JOB.lock:
            server.SCRAPE_JOB.running = False
            server.SCRAPE_JOB.process = None
            server.SCRAPE_JOB.task_id = ""
            server.SCRAPE_JOB.results_file = None
            server.SCRAPE_JOB.pause_requested = False
            server.SCRAPE_JOB.stop_requested = False
            server.SCRAPE_JOB.logs = []

    def persisted_task(self) -> dict:
        task, _paths = server.task_manager.load_task(self.tasks_dir, self.task["id"])
        return task

    def set_finalizing_job(self) -> None:
        server.task_manager.update_task(
            self.tasks_dir,
            self.task["id"],
            status="finalizing",
            worker_status="stopped",
            browser_status="closed",
        )
        server.SCRAPE_JOB.running = True
        server.SCRAPE_JOB.task_id = self.task["id"]
        server.SCRAPE_JOB.process = FinishedProcess()

    def wait_for_job_release(self) -> None:
        deadline = time.monotonic() + 5
        while server.SCRAPE_JOB.running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(server.SCRAPE_JOB.running)

    def run_worker_with_import(self, import_side_effect) -> None:
        with (
            mock.patch.object(server, "resolve_chrome_launch_config", return_value=(Path(self.temp_dir.name), "Default")),
            mock.patch.object(server, "save_state"),
            mock.patch.object(server, "scraper_worker_command", return_value=["python", "scraper.py"]),
            mock.patch.object(server.subprocess, "Popen", return_value=FinishedProcess()),
            mock.patch.object(server, "_monitor_scrape_task"),
            mock.patch.object(server.scraper_module, "load_progress", return_value={}),
            mock.patch.object(server, "_instagram_error_count", return_value=0),
            mock.patch.object(server, "import_task_results_to_creator_library", side_effect=import_side_effect),
        ):
            server.start_scrape({"taskId": self.task["id"], "profile": "Default"})
            self.wait_for_job_release()

    def test_finalizing_blocks_review_sync(self) -> None:
        task = {"status": "finalizing"}
        with self.assertRaisesRegex(RuntimeError, "任务入库收尾中"):
            server._assert_task_sync_lifecycle(task)

    def test_completed_and_failed_allow_review_sync(self) -> None:
        server._assert_task_sync_lifecycle({"status": "completed"})
        server._assert_task_sync_lifecycle({"status": "failed"})

    def test_finalizing_stop_does_not_change_status(self) -> None:
        self.set_finalizing_job()
        with self.assertRaisesRegex(RuntimeError, "正在处理中"):
            server.request_stop_scrape()
        self.assertEqual("finalizing", self.persisted_task()["status"])

    def test_finalizing_pause_does_not_change_status(self) -> None:
        self.set_finalizing_job()
        with self.assertRaisesRegex(RuntimeError, "正在处理中"):
            server.pause_scrape()
        self.assertEqual("finalizing", self.persisted_task()["status"])

    def test_successful_import_transitions_through_finalizing(self) -> None:
        observed: list[str] = []

        def import_results(task_id: str, *, allowed_task_statuses=None) -> dict:
            observed.append(self.persisted_task()["status"])
            self.assertEqual({"finalizing"}, allowed_task_statuses)
            self.assertEqual("finalizing", server.SCRAPE_JOB.snapshot()["status"])
            return {"status": "success"}

        self.run_worker_with_import(import_results)

        task = self.persisted_task()
        self.assertEqual(["finalizing"], observed)
        self.assertEqual("completed", task["status"])
        self.assertTrue(task["finished_at"])
        self.assertEqual("stopped", task["worker_status"])
        self.assertIsNone(server.SCRAPE_JOB.process)

    def test_import_failure_marks_failed_and_releases_memory(self) -> None:
        def fail_import(_task_id: str, *, allowed_task_statuses=None) -> dict:
            self.assertEqual({"finalizing"}, allowed_task_statuses)
            raise OSError("workbook unavailable")

        self.run_worker_with_import(fail_import)

        task = self.persisted_task()
        self.assertEqual("failed", task["status"])
        self.assertTrue(task["finished_at"])
        self.assertIn("workbook unavailable", task["last_error"])
        self.assertFalse(server.SCRAPE_JOB.running)
        self.assertIsNone(server.SCRAPE_JOB.process)

    def test_startup_recovers_stopping_task_without_worker(self) -> None:
        server.task_manager.update_task(
            self.tasks_dir,
            self.task["id"],
            status="stopping",
            stop_requested=True,
            worker_status="stopping",
            finished_at="2026-08-06T09:52:38Z",
        )

        recovered = server.detect_interrupted_tasks()
        task = self.persisted_task()

        self.assertEqual(1, recovered)
        self.assertEqual("stopped", task["status"])
        self.assertFalse(task["stop_requested"])
        self.assertEqual("stopped", task["worker_status"])
        self.assertEqual("2026-08-06T09:52:38Z", task["finished_at"])


if __name__ == "__main__":
    unittest.main()
