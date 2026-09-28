from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import google_sheets_client as sheets  # noqa: E402
from services import mail_follow_up_google_sheets_replica_service as replica  # noqa: E402


class _Factory:
    @contextmanager
    def read_connection(self):
        import sqlite3

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE creators (creator_id TEXT PRIMARY KEY, name TEXT)")
        connection.executemany(
            "INSERT INTO creators(creator_id, name) VALUES (?, ?)",
            [("creator-a", "Creator A"), ("creator-b", "Creator B")],
        )
        try:
            yield connection
        finally:
            connection.close()


class _Response:
    status_code = 200

    def __init__(self, payload=None):
        self.payload = payload or {}

    def json(self):
        return self.payload


class _Session:
    def __init__(self, values, *, worksheet_exists=True):
        self.values = values
        self.calls = []
        self.worksheet_exists = worksheet_exists

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if "/values/" in url:
            return _Response({"values": self.values})
        sheets = [{"properties": {"title": replica.WORKSHEET}}] if self.worksheet_exists else []
        return _Response({"sheets": sheets})

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if url.endswith(":batchUpdate"):
            self.worksheet_exists = True
        if url.endswith(":append"):
            self.values.extend(kwargs["json"]["values"])
        return _Response()

    def put(self, url, **kwargs):
        self.calls.append(("put", url, kwargs))
        rows = kwargs["json"]["values"]
        location = unquote(url).rsplit("!A", 1)[-1]
        if location == "1":
            self.values[:] = rows
        else:
            self.values[int(location) - 1:int(location)] = rows
        return _Response()


class MailFollowUpGoogleSheetsReplicaTests(unittest.TestCase):
    def test_mapper_uses_authoritative_groups_and_safe_fixed_columns(self):
        groups = [
            {"creator_id": "creator-a", "correspondent_email": "a@example.com", "waiting_for": "me", "days_waiting": 3, "last_mail_at": "2026-09-20T10:00:00Z", "synced_inbound_count": 2, "synced_outbound_count": 1, "partial_history": True},
            {"creator_id": "creator-b", "correspondent_email": "b@example.com", "waiting_for": "creator", "days_waiting": 0, "last_mail_at": None, "synced_inbound_count": 0, "synced_outbound_count": 4, "partial_history": False},
            {"creator_id": "missing", "correspondent_email": "missing@example.com", "waiting_for": "unknown", "days_waiting": None, "last_mail_at": None, "synced_inbound_count": 0, "synced_outbound_count": 0, "partial_history": None},
        ]
        with mock.patch.object(replica.preferences, "follow_up_state", return_value=groups):
            rows = replica.MailFollowUpGoogleSheetsReplicaService(_Factory()).rows()

        self.assertEqual(replica.HEADERS, ["KOLConnect Creator ID", "达人名称", "联系邮箱", "跟进状态", "等待天数", "最近邮件时间", "已同步收件数", "已同步发件数", "历史范围"])
        self.assertEqual(["creator-a", "Creator A", "a@example.com", "待我回复", 3, "2026-09-20T10:00:00Z", 2, 1, "部分历史"], rows[0])
        self.assertEqual(["creator-b", "Creator B", "b@example.com", "待对方回复", 0, "", 0, 4, "已同步范围内"], rows[1])
        self.assertEqual(["missing", "未命名达人", "missing@example.com", "状态未知", "", "", 0, 0, "历史范围未知"], rows[2])
        self.assertEqual(1, replica.HEADERS.count("KOLConnect Creator ID"))
        self.assertEqual(1, replica.HEADERS.count("联系邮箱"))
        forbidden = ("body", "html", "attachments", "bcc", "oauth", "token", "credentials", "secret")
        self.assertFalse(any(word in " ".join(replica.HEADERS).lower() for word in forbidden))

    def test_keyed_upsert_updates_existing_appends_new_and_never_clears(self):
        values = [replica.HEADERS, ["creator-a", "Old name", "a@example.com", "状态未知", "", "", 0, 0, "历史范围未知"]]
        session = _Session(values)
        with tempfile.TemporaryDirectory() as directory:
            client = sheets.GoogleSheetsClient(
                {"client_id": "id", "client_secret": "secret"},
                sheets.GoogleOAuthTokenStore(Path(directory) / "token.json"),
            )
            client._authorized_session = lambda: session
            result = client.upsert_managed_worksheet(
                "a-valid_sheet-ID_123456789", replica.WORKSHEET, replica.HEADERS,
                [
                    ["creator-a", "Creator A", "a@example.com", "待我回复", 1, "at", 1, 0, "部分历史"],
                    ["creator-b", "Creator B", "b@example.com", "待对方回复", 0, "", 0, 1, "已同步范围内"],
                    ["creator-b", "Duplicate", "b@example.com", "待对方回复", 0, "", 0, 1, "已同步范围内"],
                ],
                ("KOLConnect Creator ID", "联系邮箱"),
            )

        self.assertEqual({"created": 1, "updated": 1, "row_count": 3}, {key: result[key] for key in ("created", "updated", "row_count")})
        self.assertFalse(any(":clear" in url for _, url, _ in session.calls))
        self.assertEqual(1, sum(method == "put" and "A2" in url for method, url, _ in session.calls))
        self.assertEqual(1, sum(method == "post" and ":append" in url for method, url, _ in session.calls))

    def test_second_sync_is_idempotent_and_preserves_orphan_and_multi_email_rows(self):
        orphan = ["creator-orphan", "External", "old@example.com", "状态未知", "", "", 0, 0, "历史范围未知"]
        session = _Session([replica.HEADERS, orphan])
        rows = [
            ["creator-1", "Maria", "first@example.com", "待我回复", 1, "at", 1, 0, "部分历史"],
            ["creator-1", "Maria", "second@example.com", "待对方回复", 2, "at", 0, 1, "已同步范围内"],
            ["creator-2", "Maria", "first@example.com", "状态未知", "", "", 0, 0, "历史范围未知"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            client = sheets.GoogleSheetsClient(
                {"client_id": "id", "client_secret": "secret"},
                sheets.GoogleOAuthTokenStore(Path(directory) / "token.json"),
            )
            client._authorized_session = lambda: session
            first = client.upsert_managed_worksheet("a-valid_sheet-ID_123456789", replica.WORKSHEET, replica.HEADERS, rows, ("KOLConnect Creator ID", "联系邮箱"))
            second = client.upsert_managed_worksheet("a-valid_sheet-ID_123456789", replica.WORKSHEET, replica.HEADERS, rows, ("KOLConnect Creator ID", "联系邮箱"))

        self.assertEqual(3, first["created"])
        self.assertEqual(0, second["created"])
        self.assertEqual(3, second["updated"])
        self.assertEqual(orphan, session.values[1])
        self.assertEqual(5, len(session.values))
        self.assertFalse(any(":clear" in url for _, url, _ in session.calls))

    def test_missing_worksheet_is_created_once_with_one_header_write(self):
        session = _Session([], worksheet_exists=False)
        row = ["creator-a", "Creator A", "a@example.com", "待我回复", 1, "at", 1, 0, "部分历史"]
        with tempfile.TemporaryDirectory() as directory:
            client = sheets.GoogleSheetsClient(
                {"client_id": "id", "client_secret": "secret"},
                sheets.GoogleOAuthTokenStore(Path(directory) / "token.json"),
            )
            client._authorized_session = lambda: session
            client.upsert_managed_worksheet("a-valid_sheet-ID_123456789", replica.WORKSHEET, replica.HEADERS, [row], ("KOLConnect Creator ID", "联系邮箱"))
            client.upsert_managed_worksheet("a-valid_sheet-ID_123456789", replica.WORKSHEET, replica.HEADERS, [row], ("KOLConnect Creator ID", "联系邮箱"))

        self.assertEqual(1, sum(method == "post" and url.endswith(":batchUpdate") for method, url, _ in session.calls))
        self.assertEqual(1, sum(method == "put" and "A1" in url for method, url, _ in session.calls))
        self.assertEqual([replica.HEADERS, row], session.values)

    def test_conflicting_existing_worksheet_fails_closed(self):
        session = _Session([["another header"]])
        with tempfile.TemporaryDirectory() as directory:
            client = sheets.GoogleSheetsClient(
                {"client_id": "id", "client_secret": "secret"},
                sheets.GoogleOAuthTokenStore(Path(directory) / "token.json"),
            )
            client._authorized_session = lambda: session
            with self.assertRaisesRegex(sheets.GoogleSheetsError, "WORKSHEET_NAME_CONFLICT"):
                client.upsert_managed_worksheet("a-valid_sheet-ID_123456789", replica.WORKSHEET, replica.HEADERS, [], ("KOLConnect Creator ID", "联系邮箱"))


if __name__ == "__main__":
    unittest.main()
