from __future__ import annotations

import copy
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from feishu_client import FeishuClientError  # noqa: E402
from creator_repository import CreatorRepository  # noqa: E402
from excel_workbook_store import ExcelWorkbookStore  # noqa: E402
from http_handlers import account_identity_backfill_handler  # noqa: E402
from services.account_identity_backfill_service import (  # noqa: E402
    AccountIdentityBackfillService,
)


def local_account(uid="uid-1", creator_id="creator-1", **changes):
    row = {
        "account_uid": uid,
        "creator_id": creator_id,
        "platform": "TikTok",
        "profile_url": "https://www.tiktok.com/@one",
        "email": "private@example.com",
        "note": "private note",
    }
    row.update(changes)
    return row


def remote_account(uid="uid-1", creator_id="", record_id="remote-1", **changes):
    fields = {
        "账号唯一ID": uid,
        "KOLConnect Creator ID": creator_id,
        "平台": "TikTok",
        "主页链接": "https://www.tiktok.com/@one",
        "粉丝数": 123,
        "邮箱": "remote-private@example.com",
    }
    fields.update(changes)
    return {"record_id": record_id, "fields": fields}


class Source:
    def __init__(self, accounts=None, creators=None):
        self.data = {
            "creators": creators or [{"creator_id": "creator-1"}],
            "accounts": accounts or [local_account()],
        }
        self.reads = 0

    def getCreatorAccountIdentityRows(self):
        self.reads += 1
        return copy.deepcopy(self.data)


class Client:
    account_table_id = "account-table"
    creator_table_id = "creator-table"
    batch_size = 2

    def __init__(self, records=None):
        self.records = copy.deepcopy(records or [remote_account()])
        self.update_calls = []
        self.creator_calls = []
        self.create_calls = []
        self.delete_calls = []
        self.list_calls = []
        self.update_attempts = 0
        self.fail_update_attempt = 0

    def authenticate(self):
        return None

    def list_fields(self, table_id):
        self.list_calls.append(("fields", table_id))
        self._account_only(table_id)
        return [
            {"field_name": "账号唯一ID", "type": 1},
            {"field_name": "KOLConnect Creator ID", "type": 1},
            {"field_name": "平台", "type": 1},
            {"field_name": "主页链接", "type": 15},
        ]

    def list_records(self, table_id):
        self.list_calls.append(("records", table_id))
        self._account_only(table_id)
        return copy.deepcopy(self.records)

    def batch_update(self, table_id, updates):
        self._account_only(table_id)
        updates = copy.deepcopy(list(updates))
        self.update_attempts += 1
        if self.fail_update_attempt == self.update_attempts:
            raise FeishuClientError("TRANSIENT_REMOTE_ERROR", "temporary")
        for update in updates:
            record = next(row for row in self.records if row["record_id"] == update["record_id"])
            record["fields"].update(update["fields"])
        self.update_calls.append((table_id, updates))
        return updates

    def batch_create(self, table_id, payloads):
        self.create_calls.append((table_id, list(payloads)))
        raise AssertionError("backfill must never create")

    def delete(self, table_id, record_id):
        self.delete_calls.append((table_id, record_id))
        raise AssertionError("backfill must never delete")

    def _account_only(self, table_id):
        if table_id != self.account_table_id:
            self.creator_calls.append(table_id)
            raise AssertionError("Creator table access is prohibited")


class Handler:
    def __init__(self):
        self.responses = []

    def _json(self, payload, status=200):
        self.responses.append((status, payload))

    def _error(self, message, status=400):
        self.responses.append((status, {"ok": False, "error": message}))


class AccountIdentityBackfillTests(unittest.TestCase):
    def setUp(self):
        self.source = Source()
        self.client = Client()
        self.service = AccountIdentityBackfillService(self.source, lambda: self.client)

    def test_exact_account_uid_is_eligible_and_preview_is_privacy_safe(self):
        result = self.service.dry_run()
        self.assertEqual("success", result["status"])
        self.assertEqual(1, result["summary"]["eligible"])
        self.assertEqual("uid-1", result["candidates"][0]["account_uid"])
        serialized = repr(result).casefold()
        self.assertNotIn("private@example.com", serialized)
        self.assertNotIn("note", serialized)
        self.assertFalse(result["writable"])

    def test_duplicate_remote_uid_is_blocked(self):
        self.client.records.append(remote_account(record_id="remote-2"))
        result = self.service.dry_run()
        self.assertEqual("blocked", result["status"])
        self.assertEqual(2, result["summary"]["duplicate_remote_uid"])
        self.assertEqual(0, result["summary"]["eligible"])

    def test_duplicate_local_uid_is_blocked(self):
        self.source.data["accounts"].append(local_account(creator_id="creator-2"))
        self.source.data["creators"].append({"creator_id": "creator-2"})
        result = self.service.dry_run()
        self.assertEqual(1, result["summary"]["duplicate_local_uid"])
        self.assertEqual("DUPLICATE_LOCAL_ACCOUNT_UID", result["blocked"][0]["reason"])

    def test_missing_uid_is_blocked(self):
        self.client.records = [remote_account(uid="")]
        result = self.service.dry_run()
        self.assertEqual(1, result["summary"]["missing_uid"])
        self.assertEqual(0, result["summary"]["eligible"])

    def test_unmatched_uid_is_blocked(self):
        self.client.records = [remote_account(uid="unknown")]
        result = self.service.dry_run()
        self.assertEqual(1, result["summary"]["unmatched"])
        self.assertEqual("UNMATCHED_ACCOUNT_UID", result["blocked"][0]["reason"])

    def test_already_correct_is_unchanged(self):
        self.client.records[0]["fields"]["KOLConnect Creator ID"] = "creator-1"
        result = self.service.dry_run()
        self.assertEqual(0, result["summary"]["eligible"])
        self.assertEqual(1, result["summary"]["unchanged"])

    def test_missing_creator_id_is_updated_with_identity_fields_only(self):
        result = self.service.execute(confirm=True)
        self.assertEqual("success", result["status"])
        self.assertEqual(1, result["succeeded"])
        fields = self.client.update_calls[0][1][0]["fields"]
        self.assertEqual({"账号唯一ID", "KOLConnect Creator ID"}, set(fields))
        self.assertEqual(123, self.client.records[0]["fields"]["粉丝数"])

    def test_conflicting_creator_id_is_never_overwritten(self):
        self.client.records[0]["fields"]["KOLConnect Creator ID"] = "creator-other"
        result = self.service.execute(confirm=True)
        self.assertEqual("blocked", result["status"])
        self.assertEqual(1, result["summary"]["conflicts"])
        self.assertEqual([], self.client.update_calls)
        self.assertEqual("creator-other", self.client.records[0]["fields"]["KOLConnect Creator ID"])

    def test_execute_reruns_precheck(self):
        preview = self.service.dry_run()
        self.assertEqual(1, preview["summary"]["eligible"])
        self.client.records[0]["fields"]["KOLConnect Creator ID"] = "creator-other"
        execute = self.service.execute(confirm=True)
        self.assertEqual("blocked", execute["status"])
        self.assertEqual([], self.client.update_calls)
        self.assertEqual(2, self.source.reads)

    def test_creator_table_is_never_read_or_written(self):
        self.service.dry_run()
        self.service.execute(confirm=True)
        self.assertEqual([], self.client.creator_calls)
        self.assertTrue(all(table == "account-table" for _, table in self.client.list_calls))

    def test_no_create_or_delete_transport_is_used(self):
        self.service.execute(confirm=True)
        self.assertEqual([], self.client.create_calls)
        self.assertEqual([], self.client.delete_calls)

    def test_partial_batch_failure_stops_remaining_batches(self):
        self.source = Source(
            [local_account(f"uid-{i}", f"creator-{i}") for i in range(5)],
            [{"creator_id": f"creator-{i}"} for i in range(5)],
        )
        self.client = Client([
            remote_account(f"uid-{i}", record_id=f"remote-{i}") for i in range(5)
        ])
        self.client.fail_update_attempt = 2
        result = AccountIdentityBackfillService(self.source, lambda: self.client).execute(confirm=True)
        self.assertEqual("partial", result["status"])
        self.assertEqual(4, result["attempted"])
        self.assertEqual(2, result["succeeded"])
        self.assertEqual(2, result["failed"])
        self.assertEqual(3, result["remaining"])
        self.assertEqual(1, len(self.client.update_calls))
        self.assertEqual(["success", "failed"], [item["status"] for item in result["batches"]])

    def test_rerun_converges_without_rewriting_successful_rows(self):
        self.source = Source(
            [local_account(f"uid-{i}", f"creator-{i}") for i in range(3)],
            [{"creator_id": f"creator-{i}"} for i in range(3)],
        )
        self.client = Client([
            remote_account(f"uid-{i}", record_id=f"remote-{i}") for i in range(3)
        ])
        self.client.fail_update_attempt = 2
        service = AccountIdentityBackfillService(self.source, lambda: self.client)
        first = service.execute(confirm=True)
        self.assertEqual(2, first["succeeded"])
        self.client.fail_update_attempt = 0
        second = service.execute(confirm=True)
        self.assertEqual(2, second["summary"]["unchanged"])
        self.assertEqual(1, second["succeeded"])
        third = service.execute(confirm=True)
        self.assertEqual(3, third["summary"]["unchanged"])
        self.assertEqual(0, third["attempted"])

    def test_source_snapshot_is_unchanged_and_only_read_capability_is_used(self):
        before = copy.deepcopy(self.source.data)
        self.service.execute(confirm=True)
        self.assertEqual(before, self.source.data)
        self.assertEqual(1, self.source.reads)

    def test_repository_identity_inventory_uses_read_only_workbook_and_never_saves(self):
        workbook = Workbook()
        creators = workbook.active
        creators.title = "Creators"
        creators.append(["creator_id"])
        creators.append(["creator-1"])
        accounts = workbook.create_sheet("CreatorAccounts")
        accounts.append(["account_uid", "creator_id"])
        accounts.append(["uid-1", "creator-1"])
        store = ExcelWorkbookStore(ROOT / "unused-account-backfill.xlsx")
        repository = CreatorRepository(store)
        with (
            mock.patch.object(store, "read_only_workbook", return_value=nullcontext(workbook)) as read_only,
            mock.patch.object(store, "open", side_effect=AssertionError("normal workbook open is prohibited")),
            mock.patch.object(store, "save", side_effect=AssertionError("workbook save is prohibited")) as save,
            mock.patch("creator_repository.shared_storage_lock", return_value=nullcontext()),
        ):
            result = repository.getCreatorAccountIdentityRows()
        self.assertEqual("creator-1", result["creators"][0]["creator_id"])
        self.assertEqual("uid-1", result["accounts"][0]["account_uid"])
        read_only.assert_called_once_with()
        save.assert_not_called()

    def test_dry_run_is_deterministic(self):
        first = self.service.dry_run()
        second = self.service.dry_run()
        self.assertEqual(first, second)
        self.assertEqual([], self.client.update_calls)

    def test_confirmation_and_api_routes(self):
        with self.assertRaisesRegex(ValueError, "FEISHU_ACCOUNT_BACKFILL_CONFIRMATION_REQUIRED"):
            self.service.execute(confirm=False)
        context = {
            "services": {"account_identity_backfill": self.service},
            "logging": {"error": lambda *_args: None},
        }
        preview_handler = Handler()
        self.assertTrue(account_identity_backfill_handler.handle(
            preview_handler,
            {"method": "POST", "path": account_identity_backfill_handler.DRY_RUN_PATH},
            context,
        ))
        self.assertEqual(200, preview_handler.responses[0][0])
        execute_handler = Handler()
        self.assertTrue(account_identity_backfill_handler.handle(
            execute_handler,
            {
                "method": "POST",
                "path": account_identity_backfill_handler.EXECUTE_PATH,
                "get_payload": lambda: {"confirm": True},
            },
            context,
        ))
        self.assertEqual(200, execute_handler.responses[0][0])


if __name__ == "__main__":
    unittest.main()
