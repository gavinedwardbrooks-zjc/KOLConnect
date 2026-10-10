from __future__ import annotations

import sys
import re
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))

from creator_data_compat import build_creator_uid  # noqa: E402
from creator_repository import ExtensionMutationError  # noqa: E402
from http_handlers import creator_handler  # noqa: E402
from local_request_security import allowed_mutation_origin  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from storage.sqlite_creator_repository import SQLiteCreatorRepository  # noqa: E402
from storage.sqlite_workbook_store import SQLiteWorkbookStore  # noqa: E402
from storage.errors import SQLiteBusyError  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _Handler:
    def __init__(self):
        self.payload = None

    def _json(self, payload, status=200):
        self.payload = {"status": status, **payload}


class LinkExistingCreatorTests(unittest.TestCase):
    def setUp(self):
        self.runtime_context = test_runtime_sandbox("plugin_gate3b_link")
        self.runtime = self.runtime_context.__enter__()
        database = self.runtime.root / "data" / "kolconnect.db"
        self.factory = SQLiteConnectionFactory(database)
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection, migration_reference="plugin_gate3b_link")
        self.repository = SQLiteCreatorRepository(SQLiteWorkbookStore(database))
        self.service = CreatorService(lambda: self.repository, lambda: None)
        with self.factory.write_transaction() as connection:
            for creator_id, name, status in (
                ("creator_a", "Same Display", "contacted"),
                ("creator_b", "Same Display", "negotiating"),
                ("creator_archived", "Archived", "completed"),
            ):
                connection.execute(
                    "INSERT INTO creators(creator_id,name,status,note,archived_at) VALUES (?,?,?,?,?)",
                    (creator_id, name, status, "preserve", "2026-01-01T00:00:00Z" if creator_id == "creator_archived" else None),
                )
        self.url = "https://www.instagram.com/gate3b/"
        self.uid = build_creator_uid({"platform": "Instagram", "url": self.url})

    def tearDown(self):
        self.runtime_context.__exit__(None, None, None)

    def request(self, creator_id="creator_a", **overrides):
        return {
            "action": "LINK_EXISTING_CREATOR", "creator_id": creator_id,
            "platform": "Instagram", "profile_url": self.url, **overrides,
        }

    def rows(self):
        with self.factory.read_connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM creator_accounts")]

    def test_new_link_and_same_creator_idempotency_do_not_change_business_fields(self):
        with self.factory.read_connection() as connection:
            creators_before = [tuple(row) for row in connection.execute("SELECT * FROM creators ORDER BY creator_id")]
            campaign_before = connection.execute("SELECT COUNT(*) FROM campaign_creators").fetchone()[0]
        first = self.service.link_existing_creator_account(self.request())
        self.assertEqual({"action": "LINK_EXISTING_CREATOR", "changed": True, "account_uid": self.uid,
                          "creator_id": "creator_a", "relationship_state": "LINKED", "platform": "Instagram",
                          "profile_url": self.url, "warnings": []}, first)
        before = self.rows()
        self.assertEqual("creator_a", before[0]["creator_id"])
        self.assertIsNone(before[0]["account_email"])
        self.assertIsNone(before[0]["followers"])
        second = self.service.link_existing_creator_account(self.request())
        self.assertFalse(second["changed"])
        self.assertEqual(before, self.rows())
        with self.factory.read_connection() as connection:
            self.assertEqual(creators_before, [tuple(row) for row in connection.execute("SELECT * FROM creators ORDER BY creator_id")])
            self.assertEqual(campaign_before, connection.execute("SELECT COUNT(*) FROM campaign_creators").fetchone()[0])

    def test_cross_creator_link_is_conflict_and_atomic(self):
        self.service.link_existing_creator_account(self.request())
        before = self.rows()
        with self.assertRaises(ExtensionMutationError) as caught:
            self.service.link_existing_creator_account(self.request("creator_b"))
        self.assertEqual("ACCOUNT_OWNED_BY_OTHER_CREATOR", caught.exception.code)
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(before, self.rows())

    def test_missing_or_archived_creator_fails_closed(self):
        for creator_id, code in (("missing", "CREATOR_NOT_FOUND"), ("creator_archived", "CREATOR_ARCHIVED")):
            with self.subTest(creator_id=creator_id), self.assertRaises(ExtensionMutationError) as caught:
                self.service.link_existing_creator_account(self.request(creator_id))
            self.assertEqual(code, caught.exception.code)
        self.assertEqual([], self.rows())

    def test_invalid_stale_and_ambiguous_identity_fails_closed(self):
        for payload, code in (
            (self.request(action="ADD"), "EXPLICIT_ACTION_REQUIRED"),
            (self.request(creator_id=""), "ACCOUNT_IDENTITY_INVALID"),
            (self.request(platform="TikTok"), "ACCOUNT_IDENTITY_INVALID"),
            (self.request(profile_url="https://www.instagram.com/accounts/login/"), "ACCOUNT_IDENTITY_INVALID"),
            (self.request(expected_account_uid="stale"), "ACCOUNT_IDENTITY_STALE"),
        ):
            with self.subTest(code=code), self.assertRaises(ExtensionMutationError) as caught:
                self.service.link_existing_creator_account(payload)
            self.assertEqual(code, caught.exception.code)
        self.assertEqual([], self.rows())

    def test_existing_alias_identity_is_not_duplicated(self):
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO creator_accounts(account_uid, creator_id, platform, username, profile_url) "
                "VALUES (?,?,?,?,?)",
                ("legacy_uid", "creator_a", "Instagram", "gate3b", self.url),
            )
        with self.assertRaises(ExtensionMutationError) as caught:
            self.service.link_existing_creator_account(self.request())
        self.assertEqual("ACCOUNT_IDENTITY_CONFLICT", caught.exception.code)
        self.assertEqual(1, len(self.rows()))

    def test_ambiguous_legacy_identity_fails_closed(self):
        with self.factory.write_transaction() as connection:
            for uid in ("legacy_one", "legacy_two"):
                connection.execute(
                    "INSERT INTO creator_accounts(account_uid, creator_id, platform, username, profile_url) "
                    "VALUES (?,?,?,?,?)",
                    (uid, "creator_a", "Instagram", "gate3b", self.url),
                )
        before = self.rows()
        with self.assertRaises(ExtensionMutationError) as caught:
            self.service.link_existing_creator_account(self.request())
        self.assertEqual("ACCOUNT_IDENTITY_AMBIGUOUS", caught.exception.code)
        self.assertEqual(before, self.rows())

    def test_database_uniqueness_conflict_is_structured_and_atomic(self):
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO creator_accounts(account_uid, creator_id, platform, username, profile_url) "
                "VALUES (?,?,?,?,?)",
                ("other_uid", "creator_a", "Instagram", "other", "https://www.instagram.com/other/"),
            )
            connection.execute("CREATE UNIQUE INDEX test_unique_platform ON creator_accounts(platform)")
        before = self.rows()
        with self.assertRaises(ExtensionMutationError) as caught:
            self.service.link_existing_creator_account(self.request())
        self.assertEqual("ACCOUNT_IDENTITY_CONFLICT", caught.exception.code)
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(before, self.rows())

    def test_handler_uses_structured_result_and_error(self):
        def call(payload):
            handler = _Handler()
            self.assertTrue(creator_handler.handle(handler, {
                "method": "POST", "path": "/api/extension/accounts/link-existing-creator",
                "query": {}, "get_payload": lambda: payload,
            }, {"services": {
                "creator": self.service, "agency": object(),
                "creator_delete_impact": object(), "creator_hard_delete": object(),
            }, "config": {"legacy_cooperation_pattern": re.compile(r"/api/creator-library/[^/]+/cooperations")}, "logging": {}}))
            return handler.payload

        success = call(self.request())
        self.assertEqual(200, success["status"])
        self.assertEqual(self.uid, success["account_uid"])
        self.assertEqual("creator_a", success["creator_id"])
        conflict = call(self.request("creator_b"))
        self.assertEqual(409, conflict["status"])
        self.assertEqual("ACCOUNT_OWNED_BY_OTHER_CREATOR", conflict["error"]["code"])
        with patch.object(self.service, "link_existing_creator_account", side_effect=SQLiteBusyError()):
            unavailable = call(self.request())
        self.assertEqual(503, unavailable["status"])
        self.assertEqual("LOCAL_AUTHORITY_UNAVAILABLE", unavailable["error"]["code"])
        with patch.object(self.service, "link_existing_creator_account", side_effect=RuntimeError("secret path")):
            internal = call(self.request())
        self.assertEqual(500, internal["status"])
        self.assertEqual("LINK_INTERNAL_ERROR", internal["error"]["code"])
        self.assertNotIn("secret path", str(internal))

    def test_extension_origin_is_allowed_only_for_explicit_link_path(self):
        path = "/api/extension/accounts/link-existing-creator"
        self.assertTrue(allowed_mutation_origin("chrome-extension://test-extension", path, 8765))
        self.assertTrue(allowed_mutation_origin("http://127.0.0.1:8765", path, 8765))
        self.assertFalse(allowed_mutation_origin("https://example.com", path, 8765))
        self.assertFalse(allowed_mutation_origin("chrome-extension://test-extension", path + "/other", 8765))


if __name__ == "__main__":
    unittest.main()
