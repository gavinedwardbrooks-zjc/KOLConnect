from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper
import server
from ports.task_port import TaskRuntimeSnapshot, TaskSummaryDocuments


class _TaskServiceSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.snapshot = TaskRuntimeSnapshot(
            task_id="task_20260821T000000Z_deadbeef", status="running",
            task_type="scrape", profile="", started_at="", finished_at="",
            heartbeat_time="", stop_requested=False, pause_requested=False,
            retry_round=0, retry_requested_urls=(),
        )

    def get_runtime_task_snapshot(self, task_id):
        self.calls.append(("snapshot", task_id))
        return self.snapshot

    def list_recovery_candidates(self):
        self.calls.append(("recovery_candidates", None))
        return (self.snapshot,)

    def mark_task_interrupted(self, task_id, **kwargs):
        self.calls.append(("interrupted", (task_id, kwargs)))

    def recover_stopping_task(self, task_id, **kwargs):
        self.calls.append(("recovered", (task_id, kwargs)))

    def mark_runtime_paused(self, task_id):
        self.calls.append(("paused", task_id))

    def mark_runtime_resumed(self, task_id):
        self.calls.append(("resumed", task_id))

    def request_runtime_stop(self, task_id):
        self.calls.append(("stopping", task_id))

    def get_task_summary_documents(self, task_id):
        self.calls.append(("summary", task_id))
        return TaskSummaryDocuments(
            links=("https://www.instagram.com/example/",),
            progress_rows=({scraper.FIELD_URL: "https://www.instagram.com/example/", scraper.FIELD_STATUS: "完成"},),
            result_rows=({"邮箱": "creator@example.test"},),
            results_available=True,
        )


class ServerDelegationTests(unittest.TestCase):
    def setUp(self):
        self.spy = _TaskServiceSpy()
        self.patch = mock.patch.object(server, "get_task_service", return_value=self.spy)
        self.patch.start()
        server.SCRAPE_JOB.running = True
        server.SCRAPE_JOB.task_id = self.spy.snapshot.task_id
        server.SCRAPE_JOB.pause_requested = False
        server.SCRAPE_JOB.stop_requested = False
        server.SCRAPE_JOB.process = None

    def tearDown(self):
        self.patch.stop()
        server.SCRAPE_JOB.running = False
        server.SCRAPE_JOB.task_id = ""

    def test_recovery_and_controls_delegate_to_task_service(self):
        self.assertEqual(server.detect_interrupted_tasks(), 1)
        server.pause_scrape()
        server.resume_scrape()
        server.request_stop_scrape()
        names = [name for name, _value in self.spy.calls]
        self.assertIn("recovery_candidates", names)
        self.assertIn("interrupted", names)
        self.assertLess(names.index("paused"), names.index("resumed"))
        self.assertLess(names.index("resumed"), names.index("stopping"))

    def test_summary_reads_delegate_and_preserve_counts(self):
        progress = server._task_progress(self.spy.snapshot.task_id, fallback_total=1)
        summary = server._email_recheck_summary(self.spy.snapshot.task_id)
        self.assertEqual(progress["completed_links"], 1)
        self.assertEqual(progress["progress"], 100.0)
        self.assertEqual(summary, {"email_found_count": 1, "email_failed_count": 0})
        self.assertEqual([name for name, _value in self.spy.calls].count("summary"), 2)


class S5StaticArchitectureTests(unittest.TestCase):
    def test_server_has_no_direct_task_manager_persistence_calls(self):
        source = (APP_DIR / "server.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        forbidden = {"load_task", "list_tasks", "update_task", "create_task", "atomic_write_files"}
        calls = {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "task_manager"
        }
        self.assertTrue(forbidden.isdisjoint(calls))


if __name__ == "__main__":
    unittest.main()
