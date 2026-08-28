from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT / "tests"))

import task_manager
from adapters.task_manager_adapter import TaskManagerAdapter
from ports.task_port import RuntimeProgressUpdate, TaskFinalizationDocuments
from repositories.task_repository import TaskCsvDocument, TaskRepository
from services.task_service import TaskService
from test_support.runtime_sandbox import test_artifact_directory


class TaskLifecyclePortContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=test_artifact_directory("temporary"))
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.lock_patch = mock.patch(
            "repositories.task_repository.shared_storage_lock",
            side_effect=lambda *args, **kwargs: nullcontext(),
        )
        self.lock_patch.start()
        self.repository = TaskRepository(self.tasks_dir)
        self.adapter = TaskManagerAdapter(lambda: self.tasks_dir)
        self.service = TaskService(
            lambda: self.adapter, lambda: object(), lambda: self.repository
        )
        self.task = self.repository.create_task(
            ["https://www.instagram.com/lifecycle-contract/"], [], 1
        )

    def tearDown(self) -> None:
        self.lock_patch.stop()
        self.temp_dir.cleanup()

    def test_runtime_snapshot_is_bounded_and_recovery_transitions_preserve_status_vocabulary(self):
        self.repository.update_task(
            self.task["id"], status="running", profile="Default", retry_round=2,
            retry_requested_urls=["https://www.instagram.com/lifecycle-contract/"],
        )

        snapshot = self.service.get_runtime_task_snapshot(self.task["id"])

        self.assertEqual(snapshot.status, "running")
        self.assertEqual(snapshot.profile, "Default")
        self.assertEqual(snapshot.retry_round, 2)
        self.assertFalse(hasattr(snapshot, "metadata_path"))
        self.assertFalse(hasattr(snapshot, "paths"))

        self.service.mark_task_interrupted(
            self.task["id"], interrupted_at="2026-08-21T00:00:00Z", reason="worker missing"
        )
        interrupted = self.repository.get_task(self.task["id"])
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertEqual(interrupted["worker_status"], "stopped")
        self.assertEqual(interrupted["interrupted_reason"], "worker missing")

        self.repository.update_task(self.task["id"], status="stopping", stop_requested=True)
        self.service.recover_stopping_task(
            self.task["id"], finished_at="2026-08-21T00:00:01Z"
        )
        self.assertEqual(self.repository.get_task(self.task["id"])["status"], "stopped")

    def test_runtime_progress_and_finalization_documents_use_existing_atomic_repository_contract(self):
        task_id = self.task["id"]
        self.service.start_runtime_task(
            task_id,
            profile="Default",
            started_at="2026-08-21T00:00:00Z",
            heartbeat_interval=240,
            completed_count=0,
            current_item="https://www.instagram.com/lifecycle-contract/",
            last_progress_time="",
        )
        self.service.persist_runtime_progress(
            task_id,
            RuntimeProgressUpdate(
                completed_count=1,
                current_item="",
                last_progress_time="2026-08-21T00:01:00Z",
                heartbeat_time="2026-08-21T00:01:00Z",
            ),
        )
        row = {"url": "https://www.instagram.com/lifecycle-contract/", "status": "completed"}
        documents = TaskFinalizationDocuments(
            results=TaskCsvDocument(("url", "status"), (row,)),
            progress=TaskCsvDocument(("url", "status"), (row,)),
            modifications=(),
            metadata_changes={"status": "finalizing"},
        )

        self.service.finalize_task_documents(task_id, documents)

        legacy_task, legacy_paths = task_manager.load_task(self.tasks_dir, task_id)
        self.assertEqual(legacy_task["status"], "finalizing")
        self.assertTrue(legacy_paths["results"].exists())
        self.assertEqual(self.repository.read_progress(task_id)[0]["status"], "completed")

    def test_document_read_and_write_failures_propagate(self):
        with self.assertRaisesRegex(ValueError, "任务文件"):
            self.service.get_task_finalization_documents(self.task["id"])

        with self.assertRaisesRegex(ValueError, "任务不存在"):
            self.service.mark_task_interrupted(
                "task_20260821T000000Z_deadbeef",
                interrupted_at="2026-08-21T00:00:00Z",
                reason="missing",
            )


class TaskLifecyclePortStaticBoundaryTests(unittest.TestCase):
    def test_port_does_not_expose_generic_task_manager_or_filesystem_operations(self):
        source = (APP_DIR / "ports" / "task_port.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(base, ast.Name) and base.id == "TaskPort"
                for parent in ast.walk(tree)
                if isinstance(parent, ast.ClassDef) and node in parent.body
                for base in parent.bases
            )
        }
        self.assertTrue({"load_task", "update_task", "atomic_write_files", "get_task_paths"}.isdisjoint(methods))

    def test_task_service_keeps_task_manager_and_creator_repository_out_of_imports(self):
        source = (APP_DIR / "services" / "task_service.py").read_text(encoding="utf-8")
        self.assertNotIn("import task_manager", source)
        self.assertNotIn("creator_repository", source)


if __name__ == "__main__":
    unittest.main()
