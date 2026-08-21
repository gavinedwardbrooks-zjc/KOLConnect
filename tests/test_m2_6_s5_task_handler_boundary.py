from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from ports.task_port import CreatedTask, TaskSnapshot
from services.task_service import TaskService


class _TaskPortSpy:
    def __init__(self) -> None:
        self.command = None
        self.opened_task_id = ""

    def create_scrape_task(self, command):
        self.command = command
        return CreatedTask(TaskSnapshot(
            task_id="task_1", name=command.name, task_type="scrape", status="created",
            created_at="2026-01-01T00:00:00Z", _response={"id": "task_1", "task_type": "scrape"},
        ))

    def open_task_results(self, task_id: str) -> None:
        self.opened_task_id = task_id


class TaskHandlerBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.port = _TaskPortSpy()
        self.service = TaskService(lambda: self.port, lambda: object(), lambda: object())

    def test_scrape_task_creation_uses_task_port_command(self) -> None:
        task = self.service.create_scrape_task(
            normalized_links=["https://example.com/a"], invalid_links=["bad"], input_count=2,
            name="Audit", target_platform="TikTok", platforms=["TikTok"],
            platform_summary={"TikTok": 1}, filtered_links=[{"url": "bad"}],
        )
        self.assertEqual({"id": "task_1", "task_type": "scrape"}, task)
        self.assertEqual(("https://example.com/a",), self.port.command.normalized_links)
        self.assertEqual("scrape", task["task_type"])

    def test_open_results_stays_behind_task_port(self) -> None:
        self.service.open_task_results("task_1")
        self.assertEqual("task_1", self.port.opened_task_id)

    def test_handler_has_no_direct_task_manager_boundary_calls(self) -> None:
        source = (ROOT / "app" / "http_handlers" / "task_handler.py").read_text(encoding="utf-8")
        self.assertNotIn('context["task_manager"]', source)
        self.assertIn("task_service.create_scrape_task", source)
        self.assertIn("task_service.open_task_results", source)


if __name__ == "__main__":
    unittest.main()
