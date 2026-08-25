from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import mail_sync  # noqa: E402
from feishu_relation import relation_record_ids  # noqa: E402


class FeishuRelationParserTests(unittest.TestCase):
    def test_supported_shapes_are_explicit_deduplicated_and_ordered(self):
        cases = (
            ({"record_id": "rec1"}, ["rec1"]),
            ({"record_ids": ["rec1", "rec2"]}, ["rec1", "rec2"]),
            ([{"record_id": "rec1"}, {"record_id": "rec2"}], ["rec1", "rec2"]),
            ({"record_ids": ["rec1", "rec1"]}, ["rec1"]),
            ({"record_ids": "rec1"}, []),
            ("Creator display text", []),
            (None, []),
            (
                {"value": [{"record_ids": ["rec2", "rec1"]}, {"record_id": "rec2"}]},
                ["rec2", "rec1"],
            ),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(expected, relation_record_ids(value))

    def test_mail_matching_uses_plural_relation_identity(self):
        accounts = [
            {
                "record_id": "rec_account",
                "fields": {
                    mail_sync.FOUR_TABLE_ACCOUNT_FIELD_UID: "account_uid_1",
                    mail_sync.FOUR_TABLE_ACCOUNT_FIELD_EMAIL: "creator@example.com",
                    mail_sync.FOUR_TABLE_ACCOUNT_FIELD_PLATFORM: "TikTok",
                    mail_sync.FOUR_TABLE_ACCOUNT_FIELD_CREATOR: {"record_ids": ["rec_creator"]},
                    mail_sync.FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS: "已归属",
                },
            }
        ]
        creators = [
            {
                "record_id": "rec_creator",
                "fields": {
                    mail_sync.FOUR_TABLE_CREATOR_FIELD_ID: "creator_1",
                    mail_sync.FOUR_TABLE_CREATOR_FIELD_NAME: "Creator One",
                    mail_sync.FOUR_TABLE_CREATOR_FIELD_STAGE: "已联系",
                },
            }
        ]
        [result] = mail_sync.match_messages_to_four_tables(
            [{"id": "mail_1", "from_email": "creator@example.com"}],
            accounts,
            creators,
        )
        self.assertEqual("matched", result["match_status"])
        self.assertEqual("creator_1", result["matched_creator_id"])
        self.assertEqual("rec_creator", result["matched_creator_record_id"])


if __name__ == "__main__":
    unittest.main()
