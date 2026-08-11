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

import scraper
from adapters.task_manager_adapter import TaskManagerAdapter
from ports.creator_port import ExternalAgencyContactCommand
from repositories.task_repository import TaskRepository
from services.creator_service import CreatorService
from services.task_service import TaskService


class ManualCreatorRepository:
    def __init__(self) -> None:
        self.contact_calls: list[tuple[str, str, str, str]] = []

    def upsertExternalAgencyContact(
        self,
        external_record_id: str,
        *,
        name: str,
        whatsapp: str = "",
        source: str = "feishu_compat",
    ) -> dict:
        self.contact_calls.append((external_record_id, name, whatsapp, source))
        return {
            "contact_id": "contact-local-1",
            "external_record_id": external_record_id,
            "name": name,
            "agency_id": "",
            "whatsapp": whatsapp,
            "source": source,
            "created_at": "2026-08-11T00:00:00Z",
            "updated_at": "2026-08-11T00:00:00Z",
        }


class CreatorPortSpy:
    def __init__(self, service: CreatorService) -> None:
        self.service = service
        self.prepare_calls = 0
        self.protection_calls = 0
        self.contact_calls = 0
        self.import_calls = 0

    def prepare_manual_task(self, command):
        self.prepare_calls += 1
        return self.service.prepare_manual_task(command)

    def commit_manual_task_protection(self, command):
        self.protection_calls += 1
        return self.service.commit_manual_task_protection(command)

    def upsert_external_agency_contact(self, command: ExternalAgencyContactCommand):
        self.contact_calls += 1
        return self.service.upsert_external_agency_contact(command)

    def import_task_results(self, _command):
        self.import_calls += 1
        raise AssertionError("manual task creation must defer Creator import")


class TaskPortSpy:
    def __init__(self, adapter: TaskManagerAdapter) -> None:
        self.adapter = adapter
        self.create_commands = []
        self.initialize_commands = []

    def create_manual_task(self, command):
        self.create_commands.append(command)
        return self.adapter.create_manual_task(command)

    def initialize_manual_task(self, task_id, command):
        self.initialize_commands.append((task_id, command))
        return self.adapter.initialize_manual_task(task_id, command)


class FailingTaskPort(TaskPortSpy):
    def create_manual_task(self, command):
        self.create_commands.append(command)
        raise RuntimeError("task creation failed")


class ManualTaskBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.repository = TaskRepository(self.tasks_dir)
        self.adapter = TaskManagerAdapter(lambda: self.tasks_dir)
        self.task_port = TaskPortSpy(self.adapter)
        self.creator_repository = ManualCreatorRepository()
        self.protection: dict = {}
        self.saved_protection: list[dict] = []
        self.creator_service = CreatorService(
            lambda: self.creator_repository,
            lambda: self.task_port,
            lambda: self.protection,
            lambda data: self.saved_protection.append(data.copy()),
            lambda record_id: {
                "record_id": str(record_id),
                "name": "Agency Contact",
                "whatsapp": "+5511999999999",
            }
            if record_id
            else None,
        )
        self.creator_port = CreatorPortSpy(self.creator_service)
        self.service = TaskService(
            lambda: self.task_port,
            lambda: self.creator_port,
            lambda: self.repository,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_manual_task_uses_ports_and_preserves_deferred_files(self):
        response = self.service.create_manual_task(
            {
                "task_name": "Manual Review",
                "name": "Demo Creator",
                "platform": "Instagram",
                "profile_url": "https://www.instagram.com/demo/",
                "follower_count": "10K",
                "email": "demo@example.test",
                "whatsapp": "+5511999999999",
                "note": "manual note",
                "source_contact_record_id": "feishu-record-1",
            }
        )

        task = response["task"]
        stored = self.repository.get_task(task["id"])
        self.assertEqual(response["creator_library_import"], None)
        self.assertEqual(stored["status"], "manual_created")
        self.assertEqual(stored["task_type"], "manual")
        self.assertEqual(stored["target_platform"], "Instagram")
        self.assertEqual(stored["input_count"], 1)
        self.assertEqual(stored["valid_count"], 1)
        self.assertEqual(stored["modified_count"], 1)
        self.assertEqual(stored["source_contact_record_id"], "feishu-record-1")
        self.assertEqual(stored["local_source_contact_id"], "contact-local-1")
        self.assertEqual(stored["source_contact_name"], "Agency Contact")
        self.assertEqual(
            self.repository.read_links(task["id"]),
            ["https://www.instagram.com/demo/"],
        )
        self.assertEqual(
            self.repository.read_results_document(task["id"]).fieldnames,
            tuple(scraper.OUTPUT_FIELDS),
        )
        self.assertEqual(
            self.repository.read_progress_document(task["id"]).fieldnames,
            tuple(scraper.PROGRESS_FIELDS),
        )
        metadata = json.loads(
            (self.tasks_dir / task["id"] / "task.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata, stored)
        self.assertTrue(self.task_port.create_commands[0].defer_library_import)
        self.assertEqual(len(self.task_port.initialize_commands), 1)
        self.assertEqual(self.creator_port.prepare_calls, 1)
        self.assertEqual(self.creator_port.contact_calls, 1)
        self.assertEqual(self.creator_port.protection_calls, 1)
        self.assertEqual(self.creator_port.import_calls, 0)
        self.assertEqual(len(self.saved_protection), 1)

    def test_validation_precedes_task_creation(self):
        with self.assertRaisesRegex(ValueError, "主页链接不能为空"):
            self.service.create_manual_task(
                {"profile_url": "", "platform": "Instagram"}
            )
        self.assertEqual(self.creator_port.prepare_calls, 1)
        self.assertEqual(self.task_port.create_commands, [])
        self.assertFalse(self.tasks_dir.exists())

    def test_task_creation_failure_precedes_contact_and_protection(self):
        failing_port = FailingTaskPort(self.adapter)
        service = TaskService(
            lambda: failing_port,
            lambda: self.creator_port,
            lambda: self.repository,
        )
        with self.assertRaisesRegex(RuntimeError, "task creation failed"):
            service.create_manual_task(
                {
                    "name": "Demo",
                    "platform": "Instagram",
                    "profile_url": "https://www.instagram.com/demo/",
                    "source_contact_record_id": "feishu-record-1",
                }
            )
        self.assertEqual(self.creator_port.contact_calls, 0)
        self.assertEqual(self.creator_port.protection_calls, 0)

    def test_task_service_has_no_forbidden_manual_task_dependencies(self):
        source = (APP_DIR / "services" / "task_service.py").read_text(
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
            {
                "server",
                "http_handlers",
                "task_manager",
                "scraper",
                "creator_repository",
                "pathlib",
                "csv",
                "json",
            }.isdisjoint(imported)
        )


if __name__ == "__main__":
    unittest.main()
