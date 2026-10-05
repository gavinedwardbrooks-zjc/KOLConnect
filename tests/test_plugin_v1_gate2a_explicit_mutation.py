from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))

import app_logging  # noqa: E402

with (
    mock.patch.object(app_logging, "log_event"),
    mock.patch.object(app_logging, "log_error"),
):
    import server  # noqa: E402

from adapters.task_manager_adapter import TaskManagerAdapter  # noqa: E402
from creator_repository import ExtensionMutationError  # noqa: E402
from http_handlers import creator_handler  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from storage.sqlite_creator_repository import SQLiteCreatorRepository  # noqa: E402
from storage.sqlite_workbook_store import SQLiteWorkbookStore  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _Handler:
    def __init__(self) -> None:
        self.status = 0
        self.payload: dict = {}

    def _json(self, payload: dict, status: int = 200) -> None:
        self.status = status
        self.payload = payload

    def _error(self, message: str, status: int = 400) -> None:
        self.status = status
        self.payload = {"ok": False, "error": message}


class PluginV1Gate2AExplicitMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_context = test_runtime_sandbox("plugin_v1_gate2a")
        self.runtime = self.runtime_context.__enter__()
        self.database = self.runtime.root / "data" / "kolconnect.db"
        self.factory = SQLiteConnectionFactory(self.database)
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection, migration_reference="plugin_v1_gate2a")
        self.repository = SQLiteCreatorRepository(SQLiteWorkbookStore(self.database))
        self.task_root = self.runtime.root / "tasks"
        self.task_port = TaskManagerAdapter(lambda: self.task_root)
        self.service = CreatorService(lambda: self.repository, lambda: self.task_port)
        self.patchers = [
            mock.patch.object(server, "get_creator_service", return_value=self.service),
            mock.patch.object(server, "get_task_port", return_value=self.task_port),
            mock.patch(
                "local_storage_lock.get_shared_storage_lock_path",
                return_value=self.runtime.root / "locks" / "shared_storage.lock",
            ),
            mock.patch("creator_repository.log_event"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.runtime_context.__exit__(None, None, None)

    @staticmethod
    def payload(
        profile_url: str = "https://www.tiktok.com/@gate2acreator",
        *,
        name: str = "Gate 2A Creator",
        followers: str = "100",
    ) -> dict:
        return {
            "task_name": "Gate 2A explicit mutation",
            "creator": {
                "creator_name": name,
                "platform": "TikTok",
                "profile_url": profile_url,
                "followers": followers,
            },
            "videos": [],
            "creator_insight": {"level": "medium"},
        }

    def counts(self) -> dict[str, int]:
        with self.factory.read_connection() as connection:
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "creators",
                    "creator_accounts",
                    "creator_snapshots",
                    "videos",
                    "insights",
                    "analysis_data",
                )
            }

    def task_count(self) -> int:
        if not self.task_root.exists():
            return 0
        return sum(path.is_dir() for path in self.task_root.iterdir())

    def call_handler(self, payload: dict) -> _Handler:
        handler = _Handler()
        context = {
            "services": {
                "creator": self.service,
                "agency": object(),
                "creator_delete_impact": object(),
                "creator_hard_delete": object(),
                "import_extension_capture": server.import_extension_capture,
                "record_diagnostic": mock.Mock(),
                "utc_now": lambda: "2026-10-05T00:00:00Z",
            },
            "config": {
                "legacy_cooperation_pattern": re.compile(r"$a"),
                "legacy_cooperation_read_only_message": "read only",
            },
            "logging": {"event": mock.Mock()},
        }
        handled = creator_handler.handle(
            handler,
            {
                "method": "POST",
                "path": "/api/extension/import",
                "query": {},
                "get_payload": lambda: payload,
            },
            context,
        )
        self.assertTrue(handled)
        return handler

    def test_http_add_update_and_conflict_contract(self) -> None:
        add = self.call_handler({**self.payload(), "action": "ADD"})
        self.assertEqual(201, add.status)
        self.assertTrue(add.payload["ok"])
        self.assertEqual("ADD", add.payload["action"])
        owner = add.payload["analysis_id"]
        self.assertEqual(1, self.counts()["creators"])
        self.assertEqual(1, self.counts()["creator_accounts"])

        duplicate = self.call_handler(
            {
                **self.payload("https://tiktok.com/@gate2acreator?lang=en"),
                "action": "ADD",
            }
        )
        self.assertEqual(409, duplicate.status)
        self.assertEqual("ACCOUNT_ALREADY_EXISTS", duplicate.payload["error"]["code"])

        update = self.call_handler(
            {**self.payload(name="Updated Name", followers="250"), "action": "UPDATE"}
        )
        self.assertEqual(200, update.status)
        self.assertEqual("UPDATE", update.payload["action"])
        self.assertEqual(owner, update.payload["analysis_id"])
        self.assertEqual(1, self.counts()["creators"])
        self.assertEqual(1, self.counts()["creator_accounts"])
        with self.factory.read_connection() as connection:
            account_owner = connection.execute(
                "SELECT creator_id FROM creator_accounts WHERE account_uid=?",
                (update.payload["account_uid"],),
            ).fetchone()[0]
        self.assertEqual(owner, account_owner)

    def test_update_missing_returns_404_without_creating_task_or_entities(self) -> None:
        before = self.counts()
        response = self.call_handler({**self.payload(), "action": "UPDATE"})
        self.assertEqual(404, response.status)
        self.assertEqual("ACCOUNT_NOT_FOUND", response.payload["error"]["code"])
        self.assertEqual(before, self.counts())
        self.assertEqual(0, self.task_count())

    def test_missing_null_empty_unknown_and_lowercase_actions_are_422_without_mutation(self) -> None:
        cases = (
            ({}, "EXPLICIT_ACTION_REQUIRED"),
            ({"action": None}, "EXPLICIT_ACTION_REQUIRED"),
            ({"action": ""}, "EXPLICIT_ACTION_REQUIRED"),
            ({"action": "UPSERT"}, "VALIDATION_ERROR"),
            ({"action": "add"}, "VALIDATION_ERROR"),
            ({"action": ["ADD"]}, "VALIDATION_ERROR"),
        )
        for additions, expected_code in cases:
            with self.subTest(action=additions.get("action", "missing")):
                response = self.call_handler({**self.payload(), **additions})
                self.assertEqual(422, response.status)
                self.assertEqual(expected_code, response.payload["error"]["code"])
        self.assertEqual(0, self.task_count())
        self.assertEqual(0, sum(self.counts().values()))

    def test_add_conflict_leaves_all_business_rows_and_tasks_unchanged(self) -> None:
        server.import_extension_capture(self.payload(), "ADD")
        before = self.counts()
        before_tasks = self.task_count()
        with self.assertRaises(ExtensionMutationError) as raised:
            server.import_extension_capture(self.payload(followers="999"), "ADD")
        self.assertEqual("ACCOUNT_ALREADY_EXISTS", raised.exception.code)
        self.assertEqual(before, self.counts())
        self.assertEqual(before_tasks, self.task_count())

    def test_repository_recheck_rejects_stale_add_and_compensates_created_task(self) -> None:
        first = server.import_extension_capture(self.payload(), "ADD")
        before = self.counts()
        before_tasks = self.task_count()
        with (
            mock.patch.object(self.service, "assert_extension_mutation_allowed"),
            self.assertRaises(ExtensionMutationError) as raised,
        ):
            server.import_extension_capture(self.payload(followers="999"), "ADD")
        self.assertEqual("ACCOUNT_ALREADY_EXISTS", raised.exception.code)
        self.assertEqual(before, self.counts())
        self.assertEqual(before_tasks, self.task_count())
        self.assertEqual(first["analysis_id"], self.repository.getCreatorAccounts("")[0]["creator_id"])

    def test_repository_recheck_rejects_stale_update_without_replacement_creation(self) -> None:
        before = self.counts()
        before_tasks = self.task_count()
        with (
            mock.patch.object(self.service, "assert_extension_mutation_allowed"),
            self.assertRaises(ExtensionMutationError) as raised,
        ):
            server.import_extension_capture(self.payload(), "UPDATE")
        self.assertEqual("ACCOUNT_NOT_FOUND", raised.exception.code)
        self.assertEqual(before, self.counts())
        self.assertEqual(before_tasks, self.task_count())
        self.assertEqual(0, before["creators"])
        self.assertEqual(0, before["creator_accounts"])

    def test_ambiguous_preflight_fails_closed(self) -> None:
        repository = mock.Mock()
        repository.getExtensionAccountLookup.return_value = {"ambiguous": True}
        service = CreatorService(lambda: repository, lambda: self.task_port)
        for action in ("ADD", "UPDATE"):
            with self.subTest(action=action), self.assertRaises(ExtensionMutationError) as raised:
                service.assert_extension_mutation_allowed(action, "tiktok|identity")
            self.assertEqual("AMBIGUOUS", raised.exception.code)

    def test_http_error_mapping_survives_module_class_reload(self) -> None:
        class ReloadedMutationError(ValueError):
            code = "VALIDATION_ERROR"
            status = 422

        with mock.patch.object(
            server,
            "import_extension_capture",
            side_effect=ReloadedMutationError("invalid action"),
        ):
            response = self.call_handler({**self.payload(), "action": "invalid"})
        self.assertEqual(422, response.status)
        self.assertEqual("VALIDATION_ERROR", response.payload["error"]["code"])


if __name__ == "__main__":
    unittest.main()
