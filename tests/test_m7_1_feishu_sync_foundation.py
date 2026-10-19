from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from feishu_client import FieldFetchResult, FeishuClientError  # noqa: E402
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

    def batch_delete(self, _table_id, _record_ids):
        raise AssertionError("Feishu Full Sync must never delete remote records")


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
        self.assertEqual("FEISHU_FIELD_FETCH_FAILED", inaccessible["blocked_reason"])
        self.assertEqual(["FEISHU_FIELD_FETCH_FAILED"], inaccessible["error_codes"])
        self.assertEqual([], inaccessible["missing_fields"])
        self.assertEqual([], inaccessible["incompatible_fields"])

    def test_fallback_success_validates_normally_and_logs_only_safe_metadata(self):
        events = []
        creator_fields = copy.deepcopy(self.client.schemas["creators"])
        account_fields = copy.deepcopy(self.client.schemas["accounts"])
        creator_relation = next(
            item for item in creator_fields
            if item["field_name"] == CREATOR_ACCOUNT_RELATION_FIELD
        )
        creator_relation.update({
            "type": 21,
            "property": {"table_id": "accounts", "multiple": True},
        })
        account_relation = next(
            item for item in account_fields
            if item["field_name"] == ACCOUNT_CREATOR_RELATION_FIELD
        )
        account_relation.update({
            "type": 21,
            "property": {"table_id": "creators", "multiple": False},
        })
        creator_fields.extend(
            {"field_name": f"Creator Extra {index}", "type": 1}
            for index in range(22 - len(creator_fields))
        )
        account_fields.extend(
            {"field_name": f"Account Extra {index}", "type": 1}
            for index in range(16 - len(account_fields))
        )

        def fetch_fields(table_id):
            fields = creator_fields if table_id == "creators" else account_fields
            return FieldFetchResult(
                True,
                tuple(fields),
                used_fallback=True,
                primary_error=FeishuClientError(
                    "INVALID_REQUEST", "secret-value", http_status=400, api_code=999
                ),
            )

        self.client.fetch_fields = fetch_fields
        service = FeishuSyncService(
            self.source,
            lambda: self.client,
            event_logger=events.append,
        )
        result = service.validate_connection()
        self.assertEqual("success", result["status"])
        self.assertIn("FEISHU_FIELD_FETCH_FALLBACK_USED:creator", result["warnings"])
        self.assertIn("FEISHU_FIELD_FETCH_FALLBACK_USED:account", result["warnings"])
        self.assertTrue(any("primary_code=INVALID_REQUEST" in item for item in events))
        self.assertTrue(any("table_role=creator" in item and "remote_field_count=22" in item for item in events))
        self.assertTrue(any("table_role=account" in item and "remote_field_count=16" in item for item in events))
        self.assertTrue(all("primary_fetch_ok=false" in item for item in events))
        self.assertTrue(all("fallback_used=true" in item for item in events))
        self.assertTrue(all("fallback_ok=true" in item for item in events))
        combined = "\n".join(events)
        self.assertNotIn("secret-value", combined)
        self.assertNotIn("base-token", combined)

    def test_double_field_fetch_failure_never_becomes_missing_schema(self):
        events = []
        self.client.fetch_fields = lambda _table_id: FieldFetchResult(
            False,
            used_fallback=True,
            primary_error=FeishuClientError("INVALID_REQUEST", "rejected"),
            fallback_error=FeishuClientError(
                "TRANSIENT_NETWORK_ERROR",
                "safe failure",
                failure_stage="transport",
                exception_class="URLError",
                transport_reason_type="SSLCertVerificationError",
                transport_reason_category="CERTIFICATE_VERIFY_FAILED",
                transport_reason_message="certificate verification failed",
                transport_errno=1,
            ),
        )
        result = FeishuSyncService(
            self.source, lambda: self.client, event_logger=events.append
        ).validate_connection()
        self.assertEqual("blocked", result["status"])
        self.assertEqual("FEISHU_FIELD_FETCH_FAILED", result["blocked_reason"])
        self.assertEqual([], result["missing_fields"])
        self.assertEqual([], result["incompatible_fields"])
        self.assertTrue(all("reason_type=SSLCertVerificationError" in item for item in events))
        self.assertTrue(all("reason_category=CERTIFICATE_VERIFY_FAILED" in item for item in events))
        self.assertTrue(all("reason_message=certificate verification failed" in item for item in events))
        self.assertTrue(all("reason_errno=1" in item for item in events))

    def test_successful_empty_schema_is_explicit_schema_invalid_not_fetch_failure(self):
        events = []
        self.client.fetch_fields = lambda _table_id: FieldFetchResult(
            True, (), pagination_pages=1
        )
        result = FeishuSyncService(
            self.source, lambda: self.client, event_logger=events.append
        ).validate_connection()
        self.assertEqual("FEISHU_SCHEMA_INVALID", result["blocked_reason"])
        self.assertNotIn("FEISHU_FIELD_FETCH_FAILED", result["error_codes"])
        self.assertGreater(len(result["missing_fields"]), 0)
        self.assertTrue(all("remote_field_count=0" in item for item in events))
        self.assertTrue(all("primary_fetch_ok=true" in item for item in events))

    def test_auth_failure_is_logged_safely_before_field_fetch(self):
        events = []
        self.client.authenticate = lambda: (_ for _ in ()).throw(
            FeishuClientError(
                "AUTHENTICATION_FAILED", "secret-value", api_code=999,
                failure_stage="api", exception_class="HTTPError",
            )
        )
        result = FeishuSyncService(
            self.source, lambda: self.client, event_logger=events.append
        ).validate_connection()
        self.assertEqual("failed", result["status"])
        self.assertEqual(["AUTHENTICATION_FAILED"], result["error_codes"])
        field_event = next(item for item in events if item.startswith("feishu_field_fetch "))
        operation_event = next(
            item for item in events if item.startswith("feishu_operation_failure ")
        )
        self.assertIn("failure_stage=auth", field_event)
        self.assertIn("endpoint_category=tenant_access_token", operation_event)
        self.assertNotIn("secret-value", "\n".join(events))

    def test_record_permission_failure_logs_safe_endpoint_context(self):
        events = []
        self.client.list_records = lambda _table_id: (_ for _ in ()).throw(
            FeishuClientError(
                "PERMISSION_DENIED",
                "secret-response-message",
                http_status=403,
                api_code=1254302,
                failure_stage="api",
            )
        )
        result = FeishuSyncService(
            self.source, lambda: self.client, event_logger=events.append
        ).dry_run()

        self.assertEqual("PERMISSION_DENIED", result["blocked_reason"])
        self.assertEqual("creator_record_list", result["error_context"]["operation"])
        self.assertEqual("bitable_record_list", result["error_context"]["endpoint_category"])
        self.assertEqual("creator", result["error_context"]["table_role"])
        self.assertEqual(1254302, result["error_context"]["feishu_api_code"])
        diagnostic = next(
            item for item in events if item.startswith("feishu_operation_failure ")
        )
        self.assertIn("endpoint_category=bitable_record_list", diagnostic)
        self.assertIn("table_role=creator", diagnostic)
        self.assertIn("feishu_api_code=1254302", diagnostic)
        self.assertIn("failure_stage=api", diagnostic)
        self.assertNotIn("secret-response-message", diagnostic)
        self.assertNotIn("secret-response-message", str(result["error_context"]))

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
        synced = self.service.full_sync(confirm=True)
        self.assertEqual("success", synced["status"])
        self.assertEqual("legacy", self.client.records["creators"][0]["record_id"])

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

    def test_account_create_omits_missing_or_invalid_followers_and_preserves_zero(self):
        for local_value, expected in (("", None), ("not-a-number", None), (0, 0)):
            with self.subTest(local_value=local_value):
                client = FakeClient()
                service = FeishuSyncService(
                    Source([creator()], [account(followers=local_value)]),
                    lambda: client,
                )

                result = service.full_sync(confirm=True)

                self.assertEqual("success", result["status"])
                account_payload = next(
                    payloads[0]
                    for table_id, payloads in client.create_calls
                    if table_id == "accounts"
                )
                self.assertEqual("account-1", account_payload["账号唯一ID"])
                if expected is None:
                    self.assertNotIn("粉丝数", account_payload)
                else:
                    self.assertEqual(expected, account_payload["粉丝数"])

    def test_account_create_number_failure_logs_safe_field_names(self):
        events = []

        def fail_account_create(table_id, payloads):
            if table_id == "accounts":
                raise FeishuClientError(
                    "INVALID_FIELD_VALUE",
                    "private-provider-message secret-value",
                    api_code=1254061,
                    failure_stage="api",
                    http_status=200,
                )
            return FakeClient.batch_create(self.client, table_id, payloads)

        self.client.batch_create = fail_account_create
        service = FeishuSyncService(
            self.source,
            lambda: self.client,
            event_logger=events.append,
        )

        result = service.full_sync(confirm=True)

        self.assertEqual("partial", result["status"])
        self.assertEqual("INVALID_FIELD_VALUE", result["error_code"])
        self.assertEqual(["INVALID_FIELD_VALUE"], result["error_codes"])
        diagnostic = next(
            item for item in events
            if "endpoint_category=bitable_record_batch_create" in item
            and "table_role=account" in item
        )
        self.assertIn("feishu_api_code=1254061", diagnostic)
        self.assertIn("field_names=", diagnostic)
        self.assertIn("粉丝数", diagnostic)
        self.assertNotIn("1200", diagnostic)
        self.assertNotIn("secret-value", diagnostic)
        self.assertNotIn("private-provider-message", diagnostic)

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
