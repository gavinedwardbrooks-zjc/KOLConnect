from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.feishu_sync_service import (  # noqa: E402
    ACCOUNT_CREATOR_RELATION_FIELD,
    ACCOUNT_FIELDS,
    CREATOR_ACCOUNT_RELATION_FIELD,
    CREATOR_FIELDS,
    FeishuSyncService,
)


def _fields(specs, relation_name, relation):
    preferred = {"boolean": 7, "url": 15, "number": 2, "datetime": 5, "text": 1}
    return [
        {"field_name": spec.remote_name, "type": preferred[spec.kind]}
        for spec in specs
    ] + [{"field_name": relation_name, **relation}]


class Source:
    def getCreatorInventoryRows(self):
        return {"creators": [], "accounts": [], "insights": [], "snapshots": []}


class Client:
    creator_table_id = "creators"
    account_table_id = "accounts"

    def __init__(self, creator_relation, account_relation):
        self.schemas = {
            "creators": _fields(
                CREATOR_FIELDS, CREATOR_ACCOUNT_RELATION_FIELD, creator_relation
            ),
            "accounts": _fields(
                ACCOUNT_FIELDS, ACCOUNT_CREATOR_RELATION_FIELD, account_relation
            ),
        }

    def authenticate(self):
        return None

    def list_fields(self, table_id):
        return copy.deepcopy(self.schemas[table_id])


class FeishuRelationSchemaTests(unittest.TestCase):
    def validate(self, creator_relation, account_relation):
        client = Client(creator_relation, account_relation)
        return FeishuSyncService(Source(), lambda: client).validate_connection()

    def test_legacy_type_18_remains_compatible(self):
        result = self.validate({"type": 18}, {"type": 18})

        self.assertEqual("success", result["status"])
        self.assertEqual([], result["incompatible_fields"])

    def test_bidirectional_type_21_requires_correct_linked_tables(self):
        result = self.validate(
            {"type": 21, "property": {"table_id": "accounts", "multiple": True}},
            {"type": 21, "property": {"table_id": "creators", "multiple": True}},
        )

        self.assertEqual("success", result["status"])
        self.assertEqual([], result["incompatible_fields"])

    def test_bidirectional_type_21_wrong_linked_table_fails_closed(self):
        for table, creator_target, account_target in (
            ("creator", "wrong-table", "creators"),
            ("account", "accounts", "wrong-table"),
        ):
            with self.subTest(table=table):
                result = self.validate(
                    {
                        "type": 21,
                        "property": {"table_id": creator_target, "multiple": True},
                    },
                    {
                        "type": 21,
                        "property": {"table_id": account_target, "multiple": True},
                    },
                )
                self.assertEqual("blocked", result["status"])
                self.assertIn(
                    {
                        "table": table,
                        "field": (
                            CREATOR_ACCOUNT_RELATION_FIELD
                            if table == "creator"
                            else ACCOUNT_CREATOR_RELATION_FIELD
                        ),
                        "actual_type": 21,
                        "reason": "linked_table_mismatch",
                    },
                    result["incompatible_fields"],
                )

    def test_unrelated_type_21_without_relation_property_fails_closed(self):
        result = self.validate(
            {"type": 21, "property": {}},
            {"type": 21, "property": {"table_id": "creators", "multiple": True}},
        )

        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            "linked_table_mismatch", result["incompatible_fields"][0]["reason"]
        )

    def test_creator_relation_must_support_multiple_accounts(self):
        result = self.validate(
            {"type": 21, "property": {"table_id": "accounts", "multiple": False}},
            {"type": 21, "property": {"table_id": "creators", "multiple": True}},
        )

        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            "multiple_records_required", result["incompatible_fields"][0]["reason"]
        )

    def test_text_lookup_and_formula_fields_are_not_relations(self):
        valid_account = {
            "type": 21,
            "property": {"table_id": "creators", "multiple": True},
        }
        for field_type in (1, 19, 20):
            with self.subTest(field_type=field_type):
                result = self.validate({"type": field_type}, valid_account)
                self.assertEqual("blocked", result["status"])
                self.assertEqual(
                    "unsupported_relation_type",
                    result["incompatible_fields"][0]["reason"],
                )


if __name__ == "__main__":
    unittest.main()
