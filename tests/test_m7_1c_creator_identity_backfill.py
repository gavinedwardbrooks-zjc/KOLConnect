from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from feishu_client import FeishuClientError  # noqa: E402
from http_handlers import creator_identity_backfill_handler  # noqa: E402
from services.creator_identity_backfill_service import (  # noqa: E402
    CreatorIdentityBackfillService,
)
from services.feishu_sync_service import FeishuSyncService  # noqa: E402


def relation(*record_ids):
    return [{"record_ids": list(record_ids), "text": "display text"}]


def local_account(uid="uid-1", creator_id="creator-1"):
    return {"account_uid": uid, "creator_id": creator_id, "email": "private@example.com"}


def remote_account(
    record_id="account-1", uid="uid-1", creator_id="creator-1", creator_records=("creator-remote-1",)
):
    return {
        "record_id": record_id,
        "fields": {
            "账号唯一ID": uid,
            "KOLConnect Creator ID": creator_id,
            "平台": "TikTok",
            "达人": relation(*creator_records),
            "疑似达人候选": relation("must-not-qualify"),
            "邮箱": "remote-private@example.com",
        },
    }


def remote_creator(
    record_id="creator-remote-1", creator_id="", account_records=("account-1",), **fields
):
    payload = {
        "KOLConnect Creator ID": creator_id,
        "达人名称": "Creator One",
        "社媒账号": relation(*account_records),
        "待确认账号": relation("must-not-qualify"),
        "达人ID": "creator_legacy_only",
        "备注": "private note",
    }
    payload.update(fields)
    return {"record_id": record_id, "fields": payload}


class Source:
    def __init__(self, creators=None, accounts=None):
        self.data = {
            "creators": creators or [{"creator_id": "creator-1", "name": "Creator One"}],
            "accounts": accounts or [local_account()],
        }
        self.reads = 0

    def getCreatorAccountIdentityRows(self):
        self.reads += 1
        return copy.deepcopy(self.data)


class Client:
    creator_table_id = "creator-table"
    account_table_id = "account-table"
    batch_size = 2

    def __init__(self, creators=None, accounts=None):
        self.creators = copy.deepcopy(creators or [remote_creator()])
        self.accounts = copy.deepcopy(accounts or [remote_account()])
        self.update_calls = []
        self.create_calls = []
        self.delete_calls = []
        self.update_attempts = 0
        self.fail_update_attempt = 0
        self.list_record_calls = 0

    def authenticate(self):
        return None

    def list_fields(self, table_id):
        if table_id == self.creator_table_id:
            return [
                {"field_name": "KOLConnect Creator ID", "type": 1},
                {"field_name": "社媒账号", "type": 18},
            ]
        if table_id == self.account_table_id:
            return [
                {"field_name": "账号唯一ID", "type": 1},
                {"field_name": "KOLConnect Creator ID", "type": 1},
                {"field_name": "达人", "type": 18},
            ]
        raise AssertionError("unexpected table")

    def list_records(self, table_id):
        self.list_record_calls += 1
        if table_id == self.creator_table_id:
            return copy.deepcopy(self.creators)
        if table_id == self.account_table_id:
            return copy.deepcopy(self.accounts)
        raise AssertionError("unexpected table")

    def batch_update(self, table_id, updates):
        self.assert_creator_table(table_id)
        updates = copy.deepcopy(list(updates))
        self.update_attempts += 1
        if self.update_attempts == self.fail_update_attempt:
            raise FeishuClientError("TRANSIENT_REMOTE_ERROR", "temporary")
        for update in updates:
            record = next(item for item in self.creators if item["record_id"] == update["record_id"])
            record["fields"].update(update["fields"])
        self.update_calls.append((table_id, updates))
        return updates

    def batch_create(self, table_id, payloads):
        self.create_calls.append((table_id, list(payloads)))
        raise AssertionError("Creator backfill must never create")

    def delete(self, table_id, record_id):
        self.delete_calls.append((table_id, record_id))
        raise AssertionError("Creator backfill must never delete")

    def assert_creator_table(self, table_id):
        if table_id != self.creator_table_id:
            raise AssertionError("Account mutation is prohibited")


class Handler:
    def __init__(self):
        self.responses = []

    def _json(self, payload, status=200):
        self.responses.append((status, payload))

    def _error(self, message, status=400):
        self.responses.append((status, {"ok": False, "error": message}))


class CreatorIdentityBackfillTests(unittest.TestCase):
    def setUp(self):
        self.source = Source()
        self.client = Client()
        self.service = CreatorIdentityBackfillService(self.source, lambda: self.client)

    def test_real_relation_payload_legacy_shape_deduplication_and_malformed_safety(self):
        actual = [{"record_ids": ["rec-1", "rec-1", "rec-2"], "text": "ignored"}]
        self.assertEqual(["rec-1", "rec-2"], FeishuSyncService._relation_ids(actual))
        self.assertEqual(["rec-1"], FeishuSyncService._relation_ids([{"record_id": "rec-1"}]))
        self.assertEqual(["rec-1"], FeishuSyncService._relation_ids(["rec-1"]))
        self.assertEqual([], FeishuSyncService._relation_ids({"text": "rec-fake"}))
        self.assertEqual([], FeishuSyncService._relation_ids([{"record_ids": {"text": "bad"}}]))
        self.assertEqual([], FeishuSyncService._legacy_relation_ids(actual))

    def test_valid_reciprocal_tier_a_is_eligible_and_preview_is_read_only_private(self):
        before = copy.deepcopy(self.source.data)
        result = self.service.dry_run()
        self.assertEqual("success", result["status"])
        self.assertEqual(1, result["summary"]["tier_a_eligible"])
        self.assertEqual("creator-1", result["candidates"][0]["creator_id"])
        self.assertEqual([], self.client.update_calls)
        self.assertEqual(before, self.source.data)
        serialized = repr(result).casefold()
        for secret in ("private@example.com", "private note", "token", "app_secret"):
            self.assertNotIn(secret, serialized)

    def test_verified_account_invariant_is_required(self):
        for change in ("", "creator-other"):
            with self.subTest(remote_creator_id=change):
                self.client.accounts[0]["fields"]["KOLConnect Creator ID"] = change
                result = self.service.dry_run()
                self.assertEqual(0, result["summary"]["tier_a_eligible"])
                self.assertGreaterEqual(result["summary"]["blocked"], 1)

    def test_forward_reverse_relations_are_both_required_and_must_agree(self):
        cases = (
            ([], ("account-1",), "MISSING_FORWARD_RELATION"),
            (("creator-remote-1",), (), "MISSING_REVERSE_RELATION"),
            (("creator-other",), ("account-1",), "MISSING_FORWARD_RELATION"),
        )
        for forward, reverse, reason in cases:
            with self.subTest(reason=reason):
                client = Client(
                    [remote_creator(account_records=reverse)],
                    [remote_account(creator_records=forward)],
                )
                result = CreatorIdentityBackfillService(self.source, lambda: client).dry_run()
                self.assertEqual(0, result["summary"]["tier_a_eligible"])
                self.assertIn(reason, [item["reason"] for item in result["blocked"]])

    def test_multiple_verified_accounts_for_same_creator_are_allowed(self):
        source = Source(
            accounts=[local_account("uid-1"), local_account("uid-2")]
        )
        client = Client(
            [remote_creator(account_records=("account-1", "account-2"))],
            [
                remote_account("account-1", "uid-1"),
                remote_account("account-2", "uid-2"),
            ],
        )
        result = CreatorIdentityBackfillService(source, lambda: client).dry_run()
        self.assertEqual(1, result["summary"]["tier_a_eligible"])
        self.assertEqual(2, len(result["candidates"][0]["accounts"]))

    def test_multiple_local_id_disagreement_is_blocked(self):
        source = Source(
            creators=[{"creator_id": "creator-1"}, {"creator_id": "creator-2"}],
            accounts=[local_account("uid-1", "creator-1"), local_account("uid-2", "creator-2")],
        )
        client = Client(
            [remote_creator(account_records=("account-1", "account-2"))],
            [
                remote_account("account-1", "uid-1", "creator-1"),
                remote_account("account-2", "uid-2", "creator-2"),
            ],
        )
        result = CreatorIdentityBackfillService(source, lambda: client).dry_run()
        self.assertEqual(0, result["summary"]["tier_a_eligible"])
        self.assertEqual("MULTIPLE_LOCAL_CREATOR_IDS", result["blocked"][0]["reason"])

    def test_one_local_creator_cannot_claim_multiple_remote_creators(self):
        client = Client(
            [
                remote_creator("creator-remote-1"),
                remote_creator("creator-remote-2"),
            ],
            [remote_account(creator_records=("creator-remote-1", "creator-remote-2"))],
        )
        result = CreatorIdentityBackfillService(self.source, lambda: client).dry_run()
        self.assertEqual(0, result["summary"]["tier_a_eligible"])
        self.assertEqual(2, result["summary"]["ambiguous"])

    def test_existing_same_id_is_unchanged_and_different_id_is_conflict(self):
        self.client.creators[0]["fields"]["KOLConnect Creator ID"] = "creator-1"
        same = self.service.dry_run()
        self.assertEqual(1, same["summary"]["already_correct"])
        self.client.creators[0]["fields"]["KOLConnect Creator ID"] = "creator-other"
        different = self.service.execute(confirm=True)
        self.assertEqual(1, different["summary"]["conflicts"])
        self.assertEqual([], self.client.update_calls)
        self.assertEqual("creator-other", self.client.creators[0]["fields"]["KOLConnect Creator ID"])

    def test_names_legacy_ids_and_candidate_relations_never_qualify(self):
        self.client.accounts[0]["fields"]["达人"] = []
        self.client.creators[0]["fields"]["社媒账号"] = []
        result = self.service.dry_run()
        self.assertEqual(0, result["summary"]["tier_a_eligible"])
        self.assertEqual(1, result["summary"]["unmatched"])

    def test_execute_requires_confirmation_revalidates_and_writes_only_creator_id(self):
        with self.assertRaisesRegex(ValueError, "FEISHU_CREATOR_BACKFILL_CONFIRMATION_REQUIRED"):
            self.service.execute(confirm=False)
        result = self.service.execute(confirm=True)
        self.assertEqual("success", result["status"])
        self.assertEqual(1, result["succeeded"])
        self.assertGreaterEqual(self.source.reads, 2)
        table, updates = self.client.update_calls[0]
        self.assertEqual("creator-table", table)
        self.assertEqual({"KOLConnect Creator ID"}, set(updates[0]["fields"]))
        self.assertEqual([], self.client.create_calls)
        self.assertEqual([], self.client.delete_calls)
        self.assertEqual(0, result["account_mutation_count"])
        self.assertEqual(0, result["excel_mutation_count"])

    def test_execute_blocks_when_reciprocal_evidence_changes_during_revalidation(self):
        original_list_records = self.client.list_records

        def changing_list_records(table_id):
            if self.client.list_record_calls == 2:
                self.client.accounts[0]["fields"]["达人"] = []
            return original_list_records(table_id)

        self.client.list_records = changing_list_records
        result = self.service.execute(confirm=True)
        self.assertEqual("blocked", result["status"])
        self.assertEqual("CREATOR_IDENTITY_EVIDENCE_CHANGED", result["blocked_reason"])
        self.assertEqual([], self.client.update_calls)

    def test_batch_failure_stops_and_rerun_converges_without_rewriting_success(self):
        creators = [{"creator_id": f"creator-{index}"} for index in range(5)]
        accounts = [local_account(f"uid-{index}", f"creator-{index}") for index in range(5)]
        remote_creators = [
            remote_creator(f"remote-creator-{index}", account_records=(f"remote-account-{index}",))
            for index in range(5)
        ]
        remote_accounts = [
            remote_account(
                f"remote-account-{index}", f"uid-{index}", f"creator-{index}",
                (f"remote-creator-{index}",),
            )
            for index in range(5)
        ]
        source = Source(creators, accounts)
        client = Client(remote_creators, remote_accounts)
        client.fail_update_attempt = 2
        service = CreatorIdentityBackfillService(source, lambda: client)
        first = service.execute(confirm=True)
        self.assertEqual("partial", first["status"])
        self.assertEqual(2, first["succeeded"])
        self.assertEqual(3, first["remaining"])
        self.assertEqual(1, len(client.update_calls))
        client.fail_update_attempt = 0
        second = service.execute(confirm=True)
        self.assertEqual(2, second["summary"]["already_correct"])
        self.assertEqual(3, second["succeeded"])
        calls_after_second = len(client.update_calls)
        third = service.execute(confirm=True)
        self.assertEqual(5, third["summary"]["already_correct"])
        self.assertEqual(0, third["attempted"])
        self.assertEqual(calls_after_second, len(client.update_calls))

    def test_handler_routes_preserve_confirmation_contract(self):
        context = {
            "services": {"creator_identity_backfill": self.service},
            "logging": {"error": lambda *_args: None},
        }
        preview = Handler()
        self.assertTrue(creator_identity_backfill_handler.handle(
            preview,
            {"method": "POST", "path": creator_identity_backfill_handler.DRY_RUN_PATH},
            context,
        ))
        self.assertEqual(200, preview.responses[0][0])
        denied = Handler()
        self.assertTrue(creator_identity_backfill_handler.handle(
            denied,
            {
                "method": "POST",
                "path": creator_identity_backfill_handler.EXECUTE_PATH,
                "get_payload": lambda: {"confirm": False},
            },
            context,
        ))
        self.assertEqual(400, denied.responses[0][0])
        self.assertEqual([], self.client.update_calls)


if __name__ == "__main__":
    unittest.main()
