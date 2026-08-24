from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from feishu_client import FeishuClientError  # noqa: E402
from services.feishu_sync_service import (  # noqa: E402
    ACCOUNT_CREATOR_RELATION_FIELD,
    ACCOUNT_FIELDS,
    CREATOR_ACCOUNT_RELATION_FIELD,
    CREATOR_FIELDS,
    FeishuSyncService,
)


def schema(specs):
    preferred = {
        "boolean": 7,
        "url": 15,
        "number": 2,
        "datetime": 5,
        "text": 1,
    }
    fields = [
        {"field_name": spec.remote_name, "type": preferred[spec.kind]}
        for spec in specs
    ]
    relation_name = (
        CREATOR_ACCOUNT_RELATION_FIELD if specs is CREATOR_FIELDS
        else ACCOUNT_CREATOR_RELATION_FIELD
    )
    fields.append({"field_name": relation_name, "type": 18})
    return fields


class Source:
    def __init__(self, creators=None, accounts=None):
        self.data = {
            "creators": creators or [],
            "accounts": accounts or [],
            "insights": [],
            "snapshots": [],
        }

    def getCreatorInventoryRows(self):
        return copy.deepcopy(self.data)


class FakeClient:
    creator_table_id = "creators"
    account_table_id = "accounts"
    batch_size = 2

    def __init__(self):
        self.schemas = {"creators": schema(CREATOR_FIELDS), "accounts": schema(ACCOUNT_FIELDS)}
        self.records = {"creators": [], "accounts": []}
        self.create_calls = []
        self.update_calls = []
        self.fail_next_account_create = False
        self.authenticated = 0

    def authenticate(self):
        self.authenticated += 1

    def list_fields(self, table_id):
        return copy.deepcopy(self.schemas[table_id])

    def list_records(self, table_id):
        return copy.deepcopy(self.records[table_id])

    def batch_create(self, table_id, payloads):
        payloads = list(payloads)
        if table_id == "accounts" and self.fail_next_account_create:
            self.fail_next_account_create = False
            raise FeishuClientError("TRANSIENT_REMOTE_ERROR", "temporary")
        created = []
        for payload in payloads:
            record = {
                "record_id": f"{table_id}-{len(self.records[table_id]) + 1}",
                "fields": copy.deepcopy(payload),
            }
            self.records[table_id].append(record)
            created.append(copy.deepcopy(record))
        self.create_calls.append((table_id, copy.deepcopy(payloads)))
        return created

    def batch_update(self, table_id, updates):
        updates = list(updates)
        for update in updates:
            record = next(item for item in self.records[table_id] if item["record_id"] == update["record_id"])
            record["fields"].update(copy.deepcopy(update["fields"]))
        self.update_calls.append((table_id, copy.deepcopy(updates)))
        return copy.deepcopy(updates)


def creator(identity="creator-1", **changes):
    row = {
        "creator_id": identity,
        "name": "Creator One",
        "country": "Brazil",
        "language": "Portuguese",
        "content_category": "Gaming",
        "archived_at": "",
        "insight_level": "high",
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
        "email": "private@example.com",
        "whatsapp": "+123",
        "note": "private note",
        "quote": "500",
        "cost": "400",
    }
    row.update(changes)
    return row


def account(identity="account-1", creator_id="creator-1", **changes):
    row = {
        "account_uid": identity,
        "creator_id": creator_id,
        "platform": "TikTok",
        "profile_url": "https://www.tiktok.com/@creator-one",
        "followers": "1200",
        "account_email": "private@example.com",
        "note": "private account note",
    }
    row.update(changes)
    return row


class FeishuSyncFoundationTests(unittest.TestCase):
    def setUp(self):
        self.source = Source([creator()], [account()])
        self.client = FakeClient()
        self.service = FeishuSyncService(
            self.source,
            lambda: self.client,
            now_provider=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
        )

    def test_valid_schema_and_validation_do_not_mutate_records(self):
        before = copy.deepcopy(self.client.records)
        result = self.service.validate_connection()
        self.assertEqual("success", result["status"])
        self.assertTrue(result["connection_ok"])
        self.assertEqual(before, self.client.records)
        self.assertEqual([], self.client.create_calls)

    def test_missing_creator_or_account_identity_field_blocks(self):
        for table, field in (("creators", "KOLConnect Creator ID"), ("accounts", "账号唯一ID")):
            with self.subTest(table=table, field=field):
                current = self.client.schemas[table]
                self.client.schemas[table] = [item for item in current if item["field_name"] != field]
                result = self.service.dry_run()
                self.assertEqual("blocked", result["status"])
                self.assertEqual("FEISHU_SCHEMA_INVALID", result["blocked_reason"])
                self.assertIn({"table": "creator" if table == "creators" else "account", "field": field}, result["missing_fields"])
                self.client.schemas[table] = current

    def test_incompatible_or_inaccessible_table_blocks(self):
        field = next(item for item in self.client.schemas["creators"] if item["field_name"] == "KOLConnect Creator ID")
        field["type"] = 2
        incompatible = self.service.validate_connection()
        self.assertEqual("blocked", incompatible["status"])
        self.assertEqual("FEISHU_SCHEMA_INVALID", incompatible["blocked_reason"])
        self.assertEqual("KOLConnect Creator ID", incompatible["incompatible_fields"][0]["field"])

        original = self.client.list_fields
        self.client.list_fields = lambda table_id: (
            (_ for _ in ()).throw(FeishuClientError("PERMISSION_DENIED", "denied"))
            if table_id == "accounts" else original(table_id)
        )
        inaccessible = self.service.validate_connection()
        self.assertFalse(inaccessible["account_table_ok"])
        self.assertIn("PERMISSION_DENIED", inaccessible["error_codes"])

    def test_missing_local_identities_are_counted_and_blocked(self):
        self.source.data["creators"].append(creator(identity=""))
        self.source.data["accounts"].append(account(identity=""))
        result = self.service.dry_run()
        self.assertEqual("blocked", result["status"])
        self.assertEqual(2, result["local_creator_count"])
        self.assertEqual(2, result["local_account_count"])
        self.assertEqual(1, result["local_creators_missing_creator_id"])
        self.assertEqual(1, result["local_accounts_missing_account_uid"])

    def test_empty_remote_plans_creates_and_archived_value(self):
        self.source.data["creators"][0]["archived_at"] = "2026-08-20T00:00:00Z"
        result = self.service.dry_run()
        self.assertEqual("success", result["status"])
        self.assertEqual(1, result["creator_create_count"])
        self.assertEqual(1, result["account_create_count"])
        self.assertEqual(1, result["local_archived_creator_count"])
        self.assertEqual([], self.client.create_calls)

    def test_empty_local_and_remote_inventory_is_a_clean_noop(self):
        service = FeishuSyncService(Source([], []), lambda: self.client)
        result = service.dry_run()
        self.assertEqual("success", result["status"])
        self.assertEqual(0, result["creator_create_count"])
        self.assertEqual(0, result["creator_update_count"])
        self.assertEqual(0, result["creator_conflict_count"])
        self.assertEqual(0, result["account_create_count"])
        self.assertEqual(0, result["account_update_count"])
        self.assertEqual(0, result["account_conflict_count"])
        self.assertEqual(0, result["remote_unmanaged_count"])

    def test_three_local_records_converge_against_empty_remote(self):
        creators = [creator(f"creator-{index}", name=f"Creator {index}") for index in range(3)]
        accounts = [
            account(f"account-{index}", f"creator-{index}", profile_url=f"https://www.tiktok.com/@creator-{index}")
            for index in range(3)
        ]
        service = FeishuSyncService(Source(creators, accounts), lambda: self.client)
        first = service.dry_run()
        self.assertEqual((3, 3), (first["creator_create_count"], first["account_create_count"]))
        self.assertEqual((0, 0), (first["creator_update_count"], first["account_update_count"]))
        self.assertEqual((0, 0), (first["creator_conflict_count"], first["account_conflict_count"]))
        self.assertEqual(0, first["remote_unmanaged_count"])

        synced = service.full_sync(confirm=True)
        self.assertEqual("success", synced["status"])
        converged = service.dry_run()
        self.assertEqual((0, 0), (converged["creator_create_count"], converged["account_create_count"]))
        self.assertEqual((0, 0), (converged["creator_update_count"], converged["account_update_count"]))
        self.assertEqual((0, 0), (converged["creator_conflict_count"], converged["account_conflict_count"]))

    def test_one_creator_with_three_accounts_converges_idempotently(self):
        accounts = [
            account("account-youtube", platform="YouTube", profile_url="https://youtube.com/@creator-one"),
            account("account-tiktok", platform="TikTok", profile_url="https://tiktok.com/@creator-one"),
            account("account-instagram", platform="Instagram", profile_url="https://instagram.com/creator-one"),
        ]
        service = FeishuSyncService(Source([creator()], accounts), lambda: self.client)

        first = service.dry_run()
        self.assertEqual((1, 3), (first["creator_create_count"], first["account_create_count"]))
        self.assertEqual((0, 0), (first["creator_update_count"], first["account_update_count"]))
        self.assertEqual((0, 0), (first["creator_conflict_count"], first["account_conflict_count"]))

        synced = service.full_sync(confirm=True)
        self.assertEqual("success", synced["status"])
        self.assertEqual(1, len(self.client.records["creators"]))
        self.assertEqual(3, len(self.client.records["accounts"]))

        converged = service.dry_run()
        self.assertEqual((0, 0), (converged["creator_create_count"], converged["creator_update_count"]))
        self.assertEqual((0, 0), (converged["account_create_count"], converged["account_update_count"]))
        self.assertEqual((0, 0), (converged["creator_conflict_count"], converged["account_conflict_count"]))

    def test_one_creator_with_two_accounts_plans_one_creator_without_conflict(self):
        accounts = [
            account("account-youtube", platform="YouTube", profile_url="https://youtube.com/@creator-one"),
            account("account-tiktok", platform="TikTok", profile_url="https://tiktok.com/@creator-one"),
        ]
        result = FeishuSyncService(Source([creator()], accounts), lambda: self.client).dry_run()
        self.assertEqual(1, result["creator_create_count"])
        self.assertEqual(2, result["account_create_count"])
        self.assertEqual(0, result["creator_conflict_count"])
        self.assertEqual(0, result["account_conflict_count"])

    def test_explicit_privacy_whitelist_excludes_sensitive_fields(self):
        result = self.service.full_sync(confirm=True)
        self.assertEqual("success", result["status"])
        serialized = repr(self.client.create_calls).casefold()
        for forbidden in ("email", "whatsapp", "note", "quote", "cost", "private@example.com", "+123"):
            self.assertNotIn(forbidden, serialized)

    def test_exact_matches_are_unchanged_and_changed_field_updates(self):
        self.service.full_sync(confirm=True)
        dry = self.service.dry_run()
        self.assertEqual(1, dry["creator_unchanged_count"])
        self.assertEqual(1, dry["account_unchanged_count"])
        self.source.data["creators"][0]["country"] = "Portugal"
        changed = self.service.dry_run()
        self.assertEqual(1, changed["creator_update_count"])

    def test_duplicate_local_and_remote_identities_block(self):
        self.source.data["creators"].append(creator(name="Duplicate"))
        local = self.service.dry_run()
        self.assertEqual("blocked", local["status"])
        self.assertGreater(local["duplicate_identity_count"], 0)

        self.source.data["creators"].pop()
        self.service.full_sync(confirm=True)
        self.client.records["accounts"].append(copy.deepcopy(self.client.records["accounts"][0]))
        self.client.records["accounts"][-1]["record_id"] = "accounts-duplicate"
        remote = self.service.dry_run()
        self.assertEqual("blocked", remote["status"])
        self.assertEqual(1, remote["account_conflict_count"])

        self.client.records["accounts"].pop()
        self.client.records["creators"].append(copy.deepcopy(self.client.records["creators"][0]))
        self.client.records["creators"][-1]["record_id"] = "creators-duplicate"
        remote_creator = self.service.dry_run()
        self.assertEqual("blocked", remote_creator["status"])
        self.assertEqual(1, remote_creator["creator_conflict_count"])

    def test_unmanaged_remote_is_reported_and_never_deleted(self):
        self.client.records["creators"].append({"record_id": "legacy", "fields": {"达人ID": "random"}})
        result = self.service.dry_run()
        self.assertEqual(1, result["remote_unmanaged_count"])
        self.assertFalse(hasattr(self.client, "delete"))

    def test_full_sync_is_idempotent_and_last_synced_does_not_loop(self):
        first = self.service.full_sync(confirm=True)
        second = self.service.full_sync(confirm=True)
        self.assertEqual((1, 1), (first["creator_created"], first["account_created"]))
        self.assertEqual((0, 0), (second["creator_created"], second["account_created"]))
        self.assertEqual((0, 0), (second["creator_updated"], second["account_updated"]))
        self.assertEqual((1, 1), (second["creator_unchanged"], second["account_unchanged"]))

    def test_full_sync_keeps_archived_creator_and_updates_exact_account(self):
        self.source.data["creators"][0]["archived_at"] = "2026-08-20T00:00:00Z"
        self.service.full_sync(confirm=True)
        creator_fields = self.client.records["creators"][0]["fields"]
        self.assertIs(True, creator_fields["已归档"])
        self.source.data["accounts"][0]["followers"] = "1300"
        result = self.service.full_sync(confirm=True)
        self.assertEqual(1, result["account_updated"])
        self.assertEqual(1300, self.client.records["accounts"][0]["fields"]["粉丝数"])

    def test_blocked_plan_prevents_full_sync(self):
        self.client.schemas["creators"] = []
        result = self.service.full_sync(confirm=True)
        self.assertEqual("blocked", result["status"])
        self.assertEqual([], self.client.create_calls)

    def test_confirmation_is_required(self):
        with self.assertRaisesRegex(ValueError, "FEISHU_SYNC_CONFIRMATION_REQUIRED"):
            self.service.full_sync(confirm=False)

    def test_partial_failure_then_rerun_converges(self):
        self.client.fail_next_account_create = True
        first = self.service.full_sync(confirm=True)
        self.assertEqual("partial", first["status"])
        self.assertEqual(1, first["creator_created"])
        self.assertEqual(1, first["account_failed"])
        second = self.service.full_sync(confirm=True)
        self.assertEqual("success", second["status"])
        self.assertEqual(0, second["creator_created"])
        self.assertEqual(1, second["account_created"])

    def test_exact_legacy_creator_relation_can_be_backfilled(self):
        self.client.records["creators"] = [{"record_id": "legacy-creator", "fields": {"达人ID": "random"}}]
        self.client.records["accounts"] = [{
            "record_id": "legacy-account",
            "fields": {"账号唯一ID": "account-1", "达人": ["legacy-creator"]},
        }]
        result = self.service.dry_run()
        self.assertEqual("success", result["status"])
        self.assertEqual(0, result["creator_create_count"])
        self.assertEqual(1, result["creator_update_count"])


if __name__ == "__main__":
    unittest.main()
