from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from test_support.runtime_sandbox import test_runtime_sandbox


class TikTokPassiveImportTests(unittest.TestCase):
    def test_passive_fixture_preview_import_reuses_sqlite_identity_and_observation_contract(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the capture-to-import contract test")
        with test_runtime_sandbox("m8_3_t_import") as runtime:
            captured = subprocess.run(
                [node, str(ROOT / "tests/test_m8_3_t_tiktok_passive_capture.mjs"), "--payload"],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(0, captured.returncode, captured.stderr)
            payload = json.loads(captured.stdout)
            import app_logging
            with patch.object(app_logging, "log_event"), patch.object(app_logging, "log_error"):
                import server
            from adapters.task_manager_adapter import TaskManagerAdapter
            from services.creator_service import CreatorService
            from storage.connection import SQLiteConnectionFactory
            from storage.schema import apply_schema_migrations
            from storage.sqlite_creator_repository import SQLiteCreatorRepository
            from storage.sqlite_workbook_store import SQLiteWorkbookStore

            database = runtime.root / "data" / "kolconnect.db"
            connections = SQLiteConnectionFactory(database)
            with connections.read_connection() as connection:
                apply_schema_migrations(connection, migration_reference="m8_3_t_test")
            repository = SQLiteCreatorRepository(SQLiteWorkbookStore(database))
            task_port = TaskManagerAdapter(lambda: runtime.root / "tasks")
            service = CreatorService(lambda: repository, lambda: task_port)
            with (
                patch.object(server, "get_creator_service", return_value=service),
                patch.object(server, "get_task_port", return_value=task_port),
                patch("local_storage_lock.get_shared_storage_lock_path", return_value=runtime.root / "locks/shared_storage.lock"),
                patch("creator_repository.log_event"),
            ):
                first = server.import_extension_capture(payload)
                second = server.import_extension_capture(payload)
            self.assertEqual(first["account_uid"], second["account_uid"])
            self.assertEqual(first["account_id"], second["account_id"])
            self.assertEqual(first["analysis_id"], second["analysis_id"])
            self.assertTrue(first["is_new_creator"])
            self.assertFalse(second["is_new_creator"])
            with connections.read_connection() as connection:
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM creators").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM creator_accounts").fetchone()[0])
                # Current contract: one logical video per capture, new captures retain history.
                for snapshot in (first["snapshot_id"], second["snapshot_id"]):
                    rows = connection.execute("SELECT video_id FROM video_snapshots WHERE snapshot_id=?", (snapshot,)).fetchall()
                    self.assertEqual(2, len(rows))
                    self.assertEqual(2, len({row[0] for row in rows}))
                stored = json.loads(connection.execute("SELECT analysis_json FROM analysis_data").fetchone()[0])
                self.assertEqual("L1", stored["videos"][0]["field_provenance"]["views"]["layer"])
                self.assertEqual(payload["videos"][0]["observed_at"], stored["videos"][0]["observed_at"])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM campaign_creators").fetchone()[0])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM campaign_creator_publish_links").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
