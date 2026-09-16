from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from http_handlers import task_handler  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from storage.sqlite_creator_repository import SQLiteCreatorRepository  # noqa: E402
from storage.sqlite_workbook_store import SQLiteWorkbookStore  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _ResponseHandler:
    def __init__(self) -> None:
        self.payload: dict = {}

    def _ok(self, **payload) -> None:
        self.payload = payload


class EmailDeduplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = test_runtime_sandbox("pre_m9_email_dedup")
        self.runtime = self.sandbox.__enter__()
        self.store = SQLiteWorkbookStore.initialize_empty(self.runtime.data_root / "kolconnect.db")
        self.repository = SQLiteCreatorRepository(self.store)
        with self.store.factory.write_transaction() as connection:
            connection.executemany(
                "INSERT INTO creators(creator_id,name) VALUES (?,?)",
                [("creator-a", "Alice"), ("creator-b", "Bob")],
            )
            connection.executemany(
                "INSERT INTO creator_accounts(account_uid,creator_id,platform,username,profile_url,account_email) "
                "VALUES (?,?,?,?,?,?)",
                [
                    ("account-a", "creator-a", "TikTok", "alice", "https://www.tiktok.com/@alice", "Alice@Example.com"),
                    ("account-b", "creator-b", "YouTube", "bob", "https://www.youtube.com/@bob", "alice@example.com"),
                    ("account-c", "creator-b", "Instagram", "bob.ig", "https://www.instagram.com/bob.ig", "bob@example.com"),
                ],
            )
        self.service = CreatorService(lambda: self.repository, lambda: None)

    def tearDown(self) -> None:
        self.sandbox.__exit__(None, None, None)

    def test_case_whitespace_blank_duplicates_and_multiple_sqlite_matches(self) -> None:
        result = self.service.check_email_deduplication([
            " Alice@Example.com ", "", "ALICE@example.com", "new@example.com", "not-an-email",
        ])

        self.assertEqual(4, result["summary"]["non_empty_count"])
        self.assertEqual(1, result["summary"]["input_duplicate_count"])
        self.assertEqual(1, result["summary"]["existing_database_count"])
        self.assertEqual(["new@example.com"], result["unrecorded_emails"])
        self.assertEqual("alice@example.com", result["existing_emails"][0]["email"])
        self.assertEqual(2, len(result["existing_emails"][0]["database_matches"]))
        self.assertEqual(1, result["input_duplicates"][0]["input_duplicate_of_line"])
        self.assertEqual("邮箱格式无效", result["invalid_inputs"][0]["reason"])

    def test_handler_reuses_local_creator_service_and_never_mutates_sqlite(self) -> None:
        handler = _ResponseHandler()
        before = self.store.business_revision()
        handled = task_handler.handle(
            handler,
            {
                "method": "POST",
                "path": "/api/normalize-emails",
                "get_payload": lambda: {"text": "BOB@example.com\nmissing@example.com"},
            },
            {"services": {"task": object(), "creator": self.service}, "modules": {}},
        )

        self.assertTrue(handled)
        self.assertEqual(before, self.store.business_revision())
        self.assertEqual(["missing@example.com"], handler.payload["unrecorded_emails"])
        self.assertEqual("Bob", handler.payload["existing_emails"][0]["database_matches"][0]["creator_name"])


if __name__ == "__main__":
    unittest.main()
