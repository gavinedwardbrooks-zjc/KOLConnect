from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from feishu_client import FeishuClientError  # noqa: E402
from http_handlers import legacy_creator_cleanup_handler  # noqa: E402
from services.legacy_creator_cleanup_service import (  # noqa: E402
    LegacyCreatorCleanupService,
)


def field(name):
    return {"field_name": name, "type": 1}


class Source:
    def __init__(self):
        self.read_count = 0
        self.data = {
            "creators": [{"creator_id": "creator-1"}],
            "accounts": [{"account_uid": "account-1", "creator_id": "creator-1"}],
        }

    def getCreatorAccountIdentityRows(self):
        self.read_count += 1
        return copy.deepcopy(self.data)


class Client:
    creator_table_id = "creator-table"
    account_table_id = "account-table"

    def __init__(self, *, batch_size=100):
        self.batch_size = batch_size
        self.authenticate_count = 0
        self.list_count = 0
        self.delete_calls = []
        self.fail_delete_call = 0
        self.records = {
            "creator-table": [{
                "record_id": "managed-1",
                "fields": {"KOLConnect Creator ID": "creator-1", "达人名称": "Managed"},
            }] + [{
                "record_id": f"legacy-{index:02d}",
                "fields": {
                    "达人名称": f"Legacy {index}",
                    "达人ID": f"old-{index}",
                    "email": "must-not-leak@example.com",
                    "备注": "must-not-leak",
                },
            } for index in range(16)],
            "account-table": [{
                "record_id": "account-record-1",
                "fields": {
                    "账号唯一ID": "account-1",
                    "KOLConnect Creator ID": "creator-1",
                    "平台": "TikTok",
                    "达人": [{"record_id": "legacy-00"}],
                },
            }],
        }

    def authenticate(self):
        self.authenticate_count += 1

    def list_fields(self, table_id):
        if table_id == self.creator_table_id:
            return [field("KOLConnect Creator ID")]
        return [field("账号唯一ID"), field("KOLConnect Creator ID"), field("达人")]

    def list_records(self, table_id):
        self.list_count += 1
        return copy.deepcopy(self.records[table_id])

    def batch_delete(self, table_id, record_ids):
        ids = list(record_ids)
        self.delete_calls.append((table_id, ids))
        if self.fail_delete_call == len(self.delete_calls):
            raise FeishuClientError("TRANSIENT_REMOTE_ERROR", "temporary")
        self.records[table_id] = [
            record for record in self.records[table_id]
            if record["record_id"] not in set(ids)
        ]
        for account in self.records[self.account_table_id]:
            relations = account["fields"].get("达人") or []
            account["fields"]["达人"] = [
                relation for relation in relations
                if relation.get("record_id") not in set(ids)
            ]
        return [{"deleted": True, "record_id": record_id} for record_id in ids]


class Handler:
    def __init__(self):
        self.response = None

    def _json(self, payload, status=200):
        self.response = (status, payload)

    def _error(self, message):
        self.response = (400, {"error": message})


class LegacyCreatorCleanupTests(unittest.TestCase):
    def setUp(self):
        self.source = Source()
        self.client = Client()
        self.service = LegacyCreatorCleanupService(self.source, lambda: self.client)

    def test_preview_contains_only_exact_unmanaged_inventory_and_is_privacy_safe(self):
        result = self.service.preview()
        self.assertEqual("success", result["status"])
        self.assertEqual(16, result["summary"]["unmanaged_remote_creators"])
        self.assertEqual(1, result["summary"]["managed_remote_creators"])
        self.assertEqual(16, len(result["targets"]))
        self.assertNotIn("managed-1", {item["remote_record_id"] for item in result["targets"]})
        self.assertEqual(
            "ACTIVE_MANAGED_ACCOUNT_RELATION", result["targets"][0]["relation_status"]
        )
        self.assertNotIn("must-not-leak", repr(result))
        self.assertNotIn("email", repr(result))
        self.assertTrue(all(result["gates"].values()))

    def test_confirmation_is_required_and_browser_ids_are_ignored(self):
        with self.assertRaisesRegex(ValueError, "CONFIRMATION_REQUIRED"):
            self.service.execute(confirm=False)
        handler = Handler()
        request = {
            "method": "POST",
            "path": legacy_creator_cleanup_handler.EXECUTE_PATH,
            "get_payload": lambda: {"confirm": False, "record_ids": ["managed-1"]},
        }
        handled = legacy_creator_cleanup_handler.handle(
            handler,
            request,
            {"services": {"legacy_creator_cleanup": self.service},
             "logging": {"error": lambda *args: None}},
        )
        self.assertTrue(handled)
        self.assertEqual(400, handler.response[0])
        self.assertEqual([], self.client.delete_calls)

        missing_handler = Handler()
        legacy_creator_cleanup_handler.handle(
            missing_handler,
            {**request, "get_payload": lambda: {}},
            {"services": {"legacy_creator_cleanup": self.service},
             "logging": {"error": lambda *args: None}},
        )
        self.assertEqual(400, missing_handler.response[0])

    def test_confirmed_handler_ignores_arbitrary_managed_record_id(self):
        handler = Handler()
        handled = legacy_creator_cleanup_handler.handle(
            handler,
            {
                "method": "POST",
                "path": legacy_creator_cleanup_handler.EXECUTE_PATH,
                "get_payload": lambda: {
                    "confirm": True,
                    "record_ids": ["managed-1"],
                },
            },
            {"services": {"legacy_creator_cleanup": self.service},
             "logging": {"error": lambda *args: None}},
        )
        self.assertTrue(handled)
        self.assertEqual(200, handler.response[0])
        deleted_ids = {record_id for _table, ids in self.client.delete_calls for record_id in ids}
        self.assertNotIn("managed-1", deleted_ids)
        self.assertEqual({f"legacy-{index:02d}" for index in range(16)}, deleted_ids)

    def test_execute_revalidates_deletes_creator_only_and_verifies_no_other_writes(self):
        result = self.service.execute(confirm=True)
        self.assertEqual("success", result["status"])
        self.assertGreaterEqual(self.source.read_count, 3)
        self.assertEqual(["creator-table"], [call[0] for call in self.client.delete_calls])
        self.assertEqual(16, result["creator_delete_count"])
        self.assertEqual(0, result["account_delete_count"])
        self.assertEqual(0, result["excel_write_count"])
        self.assertEqual(1, result["verification"]["remote_creator_total"])
        self.assertEqual(1, result["verification"]["remote_account_total"])
        self.assertTrue(result["verification"]["account_authoritative_fields_unchanged"])
        self.assertTrue(result["verification"]["local_inventory_unchanged"])

    def test_count_change_and_managed_identity_conflict_fail_closed(self):
        self.client.records["creator-table"].pop(0)
        result = self.service.preview()
        self.assertEqual("success", result["status"])
        self.client.records["creator-table"].append({
            "record_id": "new-legacy", "fields": {"达人名称": "unexpected"},
        })
        blocked = self.service.preview()
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual("CLEANUP_BLOCKED_COUNT_MISMATCH", blocked["blocked_reason"])

        self.client.records["creator-table"].pop()
        self.client.records["creator-table"].append({
            "record_id": "unknown-managed",
            "fields": {"KOLConnect Creator ID": "not-local"},
        })
        conflict = self.service.preview()
        self.assertEqual("blocked", conflict["status"])
        self.assertEqual("CLEANUP_BLOCKED_IDENTITY_CONFLICT", conflict["blocked_reason"])

    def test_ambiguous_account_relation_blocks_cleanup(self):
        self.client.records["account-table"][0]["fields"]["KOLConnect Creator ID"] = "other"
        result = self.service.preview()
        self.assertEqual("blocked", result["status"])
        self.assertEqual("CLEANUP_BLOCKED_RELATION_RISK", result["blocked_reason"])
        self.assertEqual([], self.client.delete_calls)

    def test_first_failed_batch_stops_later_batches_and_reports_remaining(self):
        self.client.batch_size = 5
        self.client.fail_delete_call = 2
        result = self.service.execute(confirm=True)
        self.assertEqual("partial", result["status"])
        self.assertEqual(2, len(self.client.delete_calls))
        self.assertEqual(5, result["succeeded"])
        self.assertEqual(5, result["failed"])
        self.assertEqual(11, result["remaining"])
        still_unmanaged = [
            record for record in self.client.records["creator-table"]
            if not record["fields"].get("KOLConnect Creator ID")
        ]
        self.assertEqual(11, len(still_unmanaged))
        rerun = self.service.preview()
        self.assertEqual("blocked", rerun["status"])
        self.assertEqual(11, rerun["summary"]["unmanaged_remote_creators"])

    def test_handler_has_isolated_paths_and_does_not_expose_secrets(self):
        handler = Handler()
        handled = legacy_creator_cleanup_handler.handle(
            handler,
            {
                "method": "POST",
                "path": legacy_creator_cleanup_handler.PREVIEW_PATH,
                "get_payload": lambda: {},
            },
            {"services": {"legacy_creator_cleanup": self.service},
             "logging": {"error": lambda *args: None}},
        )
        self.assertTrue(handled)
        self.assertEqual(200, handler.response[0])
        self.assertNotIn("secret", repr(handler.response).casefold())
        self.assertNotIn("token", repr(handler.response).casefold())


if __name__ == "__main__":
    unittest.main()
