from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper
import uuid_compat


class Uuid7CompatibilityTests(unittest.TestCase):
    def test_uses_native_uuid7_when_available(self) -> None:
        expected = uuid.UUID("018f0c5e-5ce0-7a7d-8000-000000000001")
        with mock.patch.object(uuid_compat.uuid, "uuid7", return_value=expected, create=True):
            self.assertEqual(expected, uuid_compat.uuid7_or_uuid4())

    def test_falls_back_to_uuid4_when_uuid7_is_unavailable(self) -> None:
        expected = uuid.UUID("12345678-1234-4234-8234-123456789abc")
        with mock.patch.object(uuid_compat.uuid, "uuid4", return_value=expected):
            with mock.patch.object(uuid_compat.uuid, "uuid7", None, create=True):
                self.assertEqual(expected, uuid_compat.uuid7_or_uuid4())

    def test_four_table_creator_creation_keeps_id_format_on_uuid4_fallback(self) -> None:
        fallback_uuid = uuid.UUID("12345678-1234-4234-8234-123456789abc")
        created: list[tuple[str, dict]] = []

        def create(table_id: str, fields: dict, _config: dict, _headers: dict) -> str:
            created.append((table_id, fields))
            return "creator-record" if len(created) == 1 else "account-record"

        result = {
            "url": "https://www.instagram.com/uuid7-compat/",
            "platform": "Instagram",
            "name": "UUID7 Compat",
            "scrape_status": "success",
        }
        config = {
            "app_id": "app-id",
            "app_secret": "secret",
            "app_token": "token",
            "creator_table_id": "creator-table",
            "account_table_id": "account-table",
        }
        with mock.patch.object(scraper, "uuid7_or_uuid4", return_value=fallback_uuid):
            with mock.patch.object(scraper, "fetch_existing_creator_accounts", return_value=({}, set())):
                with mock.patch.object(scraper, "fetch_existing_creators", return_value={}):
                    with mock.patch.object(scraper, "_four_table_access_token", return_value="access-token"):
                        with mock.patch.object(scraper, "_four_table_batch_create", side_effect=create):
                            summary = scraper.push_to_feishu_four_tables([result], config)

        self.assertEqual(1, summary["created_creators"])
        self.assertEqual(1, summary["created_accounts"])
        self.assertEqual([], summary["errors"])
        self.assertEqual("creator-table", created[0][0])
        self.assertEqual(
            "creator_12345678123442348234123456789abc",
            created[0][1][scraper.FOUR_TABLE_CREATOR_FIELD_ID],
        )


if __name__ == "__main__":
    unittest.main()
