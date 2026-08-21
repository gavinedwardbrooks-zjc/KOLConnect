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

import server
from ports.task_port import CreatedTask, ManualTaskCreationResult, TaskSnapshot


class _ManualTaskPort:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.task = TaskSnapshot(
            task_id="task_20260821T000000Z_deadbeef", name="Manual", task_type="manual",
            status="manual_created", created_at="2026-08-21T00:00:00Z",
            _response={"id": "task_20260821T000000Z_deadbeef", "task_type": "manual", "status": "manual_created", "target_platform": "Instagram"},
        )
        self.create_command = None
        self.initialize_command = None

    def create_manual_task(self, command):
        self.create_command = command
        return CreatedTask(self.task)

    def initialize_manual_task(self, task_id, command):
        self.initialize_command = command
        if self.error:
            raise self.error
        return ManualTaskCreationResult(self.task, "instagram:manual", "2026-08-21T00:00:00Z")

    def get_task(self, task_id):
        return self.task


class ManualCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.port = _ManualTaskPort()
        self.patches = [
            mock.patch.object(server, "_resolve_source_contact", return_value=None),
            mock.patch.object(server, "load_data_protection", return_value={}),
            mock.patch.object(server, "_save_data_protection"),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()

    def test_success_contact_fields_and_readback_use_task_port(self):
        result = server._create_manual_task_legacy(
            {"profile_url": "https://www.instagram.com/manual-demo/", "platform": "Instagram", "name": "Manual Demo", "email": "demo@example.test", "whatsapp": "+15551234567", "task_name": "Manual"},
            task_port=self.port,
        )
        self.assertEqual(result["task"]["task_type"], "manual")
        self.assertEqual(result["task"]["status"], "manual_created")
        self.assertEqual(result["account_uid"], "instagram:manual")
        self.assertEqual(self.port.create_command.platform, "Instagram")
        self.assertEqual(self.port.initialize_command.email, "demo@example.test")
        self.assertEqual(self.port.initialize_command.whatsapp, "+15551234567")

    def test_invalid_url_and_document_failure_remain_explicit(self):
        with self.assertRaisesRegex(ValueError, "主页链接不能为空"):
            server._create_manual_task_legacy({}, task_port=self.port)
        failing = _ManualTaskPort(OSError("document unavailable"))
        with self.assertRaisesRegex(OSError, "document unavailable"):
            server._create_manual_task_legacy(
                {"profile_url": "https://www.instagram.com/manual-demo/", "platform": "Instagram"},
                task_port=failing,
            )


class ManualCompatibilityArchitectureTests(unittest.TestCase):
    def test_legacy_wrapper_has_no_direct_task_manager_persistence(self):
        source = (APP_DIR / "server.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_create_manual_task_legacy")
        calls = {
            node.func.attr for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "task_manager"
        }
        self.assertTrue({"create_task", "load_task", "update_task", "atomic_write_files"}.isdisjoint(calls))


if __name__ == "__main__":
    unittest.main()
