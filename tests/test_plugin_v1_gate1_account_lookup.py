from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))

from creator_data_compat import build_creator_uid  # noqa: E402
from http_handlers import creator_handler  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from storage.sqlite_creator_repository import SQLiteCreatorRepository  # noqa: E402
from storage.sqlite_workbook_store import SQLiteWorkbookStore  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _Handler:
    def __init__(self) -> None:
        self.payload: dict | None = None

    def _json(self, payload: dict, status: int = 200) -> None:
        self.payload = {"status": status, **payload}


class PluginV1AccountLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_context = test_runtime_sandbox("plugin_v1_lookup")
        self.runtime = self.runtime_context.__enter__()
        self.database = self.runtime.root / "data" / "kolconnect.db"
        self.factory = SQLiteConnectionFactory(self.database)
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection, migration_reference="plugin_v1_lookup")
        self.repository = SQLiteCreatorRepository(SQLiteWorkbookStore(self.database))
        self.service = CreatorService(lambda: self.repository, lambda: None)
        self.creator_id = "creator_plugin_lookup"
        self.urls = {
            "TikTok": "https://www.tiktok.com/@creatorlookup",
            "Instagram": "https://www.instagram.com/creatorlookup/",
            "YouTube": "https://www.youtube.com/@creatorlookup",
        }
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO creators(creator_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (self.creator_id, "Lookup Creator", "2026-09-30T00:00:00Z", "2026-09-30T00:00:00Z"),
            )
            for platform, url in self.urls.items():
                account_uid = build_creator_uid({"platform": platform, "url": url})
                connection.execute(
                    "INSERT INTO creator_accounts(account_uid, account_id, creator_id, platform, username, profile_url, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        account_uid,
                        f"account_{platform.casefold()}",
                        self.creator_id,
                        platform,
                        "creatorlookup",
                        url,
                        "2026-09-30T01:02:03Z",
                    ),
                )

    def tearDown(self) -> None:
        self.runtime_context.__exit__(None, None, None)

    def test_three_platform_lookup_returns_only_safe_summary_without_mutation(self) -> None:
        with self.factory.read_connection() as connection:
            before = connection.execute("SELECT COUNT(*) FROM creator_accounts").fetchone()[0]
        for platform, url in self.urls.items():
            result = self.service.lookup_extension_account(platform.casefold(), url)
            self.assertEqual("ACCOUNT_EXISTS", result["state"])
            self.assertEqual("Lookup Creator", result["creator"]["display_name"])
            self.assertEqual(platform, result["account"]["platform"])
            self.assertEqual("2026-09-30T01:02:03Z", result["account"]["updated_at"])
            self.assertEqual(3, len(result["linked_accounts"]))
            self.assertNotIn("account_uid", result["account"])
            self.assertNotIn("account_email", result["account"])
            self.assertNotIn("creator_id", result["creator"])
        with self.factory.read_connection() as connection:
            after = connection.execute("SELECT COUNT(*) FROM creator_accounts").fetchone()[0]
        self.assertEqual(before, after)

    def test_not_found_and_invalid_requests_fail_closed(self) -> None:
        self.assertEqual(
            {"state": "ACCOUNT_NOT_FOUND"},
            self.service.lookup_extension_account("TikTok", "https://www.tiktok.com/@not-recorded"),
        )
        self.assertEqual(
            {"state": "INVALID_REQUEST"},
            self.service.lookup_extension_account("TikTok", "https://www.instagram.com/creatorlookup/"),
        )
        self.assertEqual(
            {"state": "INVALID_REQUEST"},
            self.service.lookup_extension_account("Unknown", self.urls["TikTok"]),
        )

    def test_handler_exposes_the_same_read_only_contract(self) -> None:
        handler = _Handler()
        handled = creator_handler.handle(handler, {
            "method": "GET",
            "path": "/api/extension/accounts/lookup",
            "query": {"platform": ["youtube"], "profile_url": [self.urls["YouTube"]]},
        }, {
            "services": {
                "creator": self.service,
                "agency": object(),
                "creator_delete_impact": object(),
                "creator_hard_delete": object(),
            },
            "config": {},
            "logging": {},
        })
        self.assertTrue(handled)
        self.assertEqual(200, handler.payload["status"])
        self.assertEqual("ACCOUNT_EXISTS", handler.payload["state"])
        self.assertNotIn("account_uid", handler.payload["account"])


if __name__ == "__main__":
    unittest.main()
