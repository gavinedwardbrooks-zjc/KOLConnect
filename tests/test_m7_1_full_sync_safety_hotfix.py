from __future__ import annotations

import copy
import math
import sys
import unittest
from collections import Counter
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


def field_schema(specs):
    types = {"boolean": 7, "url": 15, "number": 2, "datetime": 5, "text": 1}
    return {spec.remote_name: {"field_name": spec.remote_name, "type": types[spec.kind]} for spec in specs}


def creator(identity="creator-1", **changes):
    row = {
        "creator_id": identity,
        "name": f"Creator {identity}",
        "country": "Brazil",
        "language": "Portuguese",
        "content_category": "Gaming",
        "archived_at": "",
        "insight_level": "high",
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
        "email": "private@example.com",
        "notes": "private note",
        "cost": "500",
    }
    row.update(changes)
    return row


def account(identity="account-1", creator_id="creator-1", **changes):
    row = {
        "account_uid": identity,
        "creator_id": creator_id,
        "platform": "TikTok",
        "profile_url": f"https://example.com/{identity}",
        "followers": 1200,
        "email": "private@example.com",
        "whatsapp": "+123",
    }
    row.update(changes)
    return row


class Source:
    def __init__(self, creators=None, accounts=None, snapshots=None):
        self.data = {
            "creators": list(creators if creators is not None else []),
            "accounts": list(accounts if accounts is not None else []),
            "insights": [],
            "snapshots": list(snapshots if snapshots is not None else []),
        }

    def getCreatorInventoryRows(self):
        return copy.deepcopy(self.data)


class StatefulClient:
    creator_table_id = "creators"
    account_table_id = "accounts"
    batch_size = 2

    def __init__(self):
        self.schemas = {
            "creators": [
                *field_schema(CREATOR_FIELDS).values(),
                {"field_name": CREATOR_ACCOUNT_RELATION_FIELD, "type": 18},
            ],
            "accounts": [
                *field_schema(ACCOUNT_FIELDS).values(),
                {"field_name": ACCOUNT_CREATOR_RELATION_FIELD, "type": 18},
            ],
        }
        self.records = {"creators": [], "accounts": []}
        self.calls = []
        self.call_counts = Counter()
        self.fail_on = None
        self.commit_before_failure = False

    def authenticate(self):
        return None

    def list_fields(self, table_id):
        return copy.deepcopy(self.schemas[table_id])

    def list_records(self, table_id):
        return copy.deepcopy(self.records[table_id])

    def batch_create(self, table_id, payloads):
        payloads = copy.deepcopy(list(payloads))
        attempt = self._record_call("create", table_id, payloads)
        should_fail = self.fail_on == ("create", table_id, attempt)
        created = self._create_records(table_id, payloads) if not should_fail or self.commit_before_failure else []
        if should_fail:
            raise FeishuClientError("TRANSIENT_NETWORK_ERROR", "temporary", "2")
        return copy.deepcopy(created)

    def batch_update(self, table_id, updates):
        updates = copy.deepcopy(list(updates))
        attempt = self._record_call("update", table_id, updates)
        should_fail = self.fail_on == ("update", table_id, attempt)
        if not should_fail or self.commit_before_failure:
            for update in updates:
                record = next(row for row in self.records[table_id] if row["record_id"] == update["record_id"])
                record["fields"].update(update["fields"])
        if should_fail:
            raise FeishuClientError("RATE_LIMITED", "temporary", "3")
        return copy.deepcopy(updates)

    def _record_call(self, operation, table_id, payload):
        key = (operation, table_id)
        self.call_counts[key] += 1
        self.calls.append((operation, table_id, payload))
        return self.call_counts[key]

    def _create_records(self, table_id, payloads):
        created = []
        for payload in payloads:
            record = {
                "record_id": f"{table_id}-{len(self.records[table_id]) + 1}",
                "fields": copy.deepcopy(payload),
            }
            self.records[table_id].append(record)
            created.append(record)
        return created


class FullSyncSafetyHotfixTests(unittest.TestCase):
    def service(self, source, client):
        return FeishuSyncService(
            source,
            lambda: client,
            now_provider=lambda: datetime(2026, 8, 24, tzinfo=timezone.utc),
        )

    def test_creator_create_failure_stops_all_later_batches_and_phases(self):
        source = Source(
            [creator(f"creator-{index}") for index in range(5)],
            [account(f"account-{index}", f"creator-{index}") for index in range(5)],
        )
        client = StatefulClient()
        client.fail_on = ("create", "creators", 2)
        result = self.service(source, client).full_sync(confirm=True)
        self.assertEqual("partial", result["status"])
        self.assertEqual("creator_create", result["phase"])
        self.assertEqual((4, 2, 2, 13), (
            result["attempted"], result["succeeded"], result["failed"], result["remaining"],
        ))
        self.assertEqual(2, client.call_counts[("create", "creators")])
        self.assertEqual(0, client.call_counts[("update", "creators")])
        self.assertEqual(0, client.call_counts[("create", "accounts")])
        self.assertEqual(0, client.call_counts[("update", "accounts")])
        self.assertIn("FULL_SYNC_STOPPED_AFTER_BATCH_FAILURE", result["warnings"])
        self.assertEqual("TRANSIENT_NETWORK_ERROR", result["error_code"])
        self.assertEqual("2", result["retry_after"])

    def test_first_batch_failure_is_failed_not_partial(self):
        source = Source([creator()], [account()])
        client = StatefulClient()
        client.fail_on = ("create", "creators", 1)
        result = self.service(source, client).full_sync(confirm=True)
        self.assertEqual("failed", result["status"])
        self.assertEqual(0, result["succeeded"])
        self.assertEqual(3, result["remaining"])

    def test_creator_update_failure_stops_later_updates_and_account_phases(self):
        source = Source([creator(f"creator-{i}") for i in range(5)], [account("account-1", "creator-0")])
        client = StatefulClient()
        seed = self.service(source, client)
        seed.full_sync(confirm=True)
        client.calls.clear(); client.call_counts.clear()
        for row in source.data["creators"]:
            row["country"] = "Portugal"
        source.data["accounts"][0]["followers"] = 1300
        client.fail_on = ("update", "creators", 2)
        result = seed.full_sync(confirm=True)
        self.assertEqual("partial", result["status"])
        self.assertEqual("creator_update", result["phase"])
        self.assertEqual(2, client.call_counts[("update", "creators")])
        self.assertEqual(0, client.call_counts[("update", "accounts")])

    def test_account_create_failure_stops_later_creates_and_updates(self):
        source = Source([creator()], [account("account-existing")])
        client = StatefulClient()
        service = self.service(source, client)
        service.full_sync(confirm=True)
        source.data["accounts"][0]["followers"] = 1300
        source.data["accounts"].extend(account(f"new-{i}") for i in range(5))
        client.calls.clear(); client.call_counts.clear()
        client.fail_on = ("create", "accounts", 2)
        result = service.full_sync(confirm=True)
        self.assertEqual("partial", result["status"])
        self.assertEqual("account_create", result["phase"])
        self.assertEqual(2, client.call_counts[("create", "accounts")])
        self.assertEqual(0, client.call_counts[("update", "accounts")])

    def test_account_update_failure_stops_later_update_batches(self):
        creators = [creator()]
        accounts = [account(f"account-{i}") for i in range(5)]
        source = Source(creators, accounts)
        client = StatefulClient()
        service = self.service(source, client)
        service.full_sync(confirm=True)
        for row in source.data["accounts"]:
            row["followers"] = 1300
        client.calls.clear(); client.call_counts.clear()
        client.fail_on = ("update", "accounts", 2)
        result = service.full_sync(confirm=True)
        self.assertEqual("partial", result["status"])
        self.assertEqual("account_update", result["phase"])
        self.assertEqual(2, client.call_counts[("update", "accounts")])

    def test_ambiguous_creator_create_failure_rerun_does_not_duplicate(self):
        source = Source([creator(f"creator-{i}") for i in range(3)])
        client = StatefulClient()
        client.fail_on = ("create", "creators", 1)
        client.commit_before_failure = True
        service = self.service(source, client)
        first = service.full_sync(confirm=True)
        self.assertEqual("failed", first["status"])
        self.assertEqual(2, len(client.records["creators"]))
        client.fail_on = None
        second = service.full_sync(confirm=True)
        self.assertEqual(1, second["creator_created"])
        self.assertEqual(3, len(client.records["creators"]))
        identities = [row["fields"]["KOLConnect Creator ID"] for row in client.records["creators"]]
        self.assertEqual(3, len(set(identities)))

    def test_ambiguous_account_create_failure_rerun_does_not_duplicate(self):
        source = Source([creator()], [account(f"account-{i}") for i in range(3)])
        client = StatefulClient()
        service = self.service(source, client)
        client.fail_on = ("create", "accounts", 1)
        client.commit_before_failure = True
        first = service.full_sync(confirm=True)
        self.assertEqual("partial", first["status"])
        self.assertEqual(2, len(client.records["accounts"]))
        client.fail_on = None
        second = service.full_sync(confirm=True)
        self.assertEqual(1, second["account_created"])
        identities = [row["fields"]["账号唯一ID"] for row in client.records["accounts"]]
        self.assertEqual(3, len(set(identities)))

    def test_creator_update_omits_missing_values_and_preserves_false_archive(self):
        service = self.service(Source(), StatefulClient())
        specs = CREATOR_FIELDS
        schema = field_schema(specs)
        canonical = {
            "creator_id": "creator-1", "name": "", "country": "", "language": " ",
            "content_category": None, "archived": False, "insight_level": "N/A",
            "last_analysis_at": "invalid",
        }
        remote = {"record_id": "remote-1", "fields": {
            "KOLConnect Creator ID": "creator-1", "达人名称": "Remote Name",
            "国家/地区": "Brazil", "语言": "Portuguese", "内容类型": "Gaming",
            "已归档": True, "Insight等级": "high", "最后分析时间": 123,
        }}
        item = service._plan_item("creator-1", canonical, remote, specs, schema)
        self.assertEqual("update", item["action"])
        self.assertEqual({"KOLConnect Creator ID", "已归档"}, set(item["payload"]))
        self.assertIs(False, item["payload"]["已归档"])
        self.assertEqual(6, len(item["preserved_remote_fields"]))

    def test_meaningful_text_overwrites_but_missing_only_is_unchanged(self):
        service = self.service(Source(), StatefulClient())
        schema = field_schema(CREATOR_FIELDS)
        remote = {"record_id": "remote-1", "fields": {
            "KOLConnect Creator ID": "creator-1", "达人名称": "Remote",
            "国家/地区": "Brasil", "语言": "Portuguese", "内容类型": "Gaming",
            "已归档": False,
        }}
        canonical = {
            "creator_id": "creator-1", "name": "", "country": "Brazil",
            "language": "", "content_category": "", "archived": False,
            "insight_level": "", "last_analysis_at": "",
        }
        changed = service._plan_item("creator-1", canonical, remote, CREATOR_FIELDS, schema)
        self.assertEqual(["国家/地区"], changed["changed_fields"])
        self.assertEqual("Brazil", changed["payload"]["国家/地区"])
        canonical["country"] = ""
        unchanged = service._plan_item("creator-1", canonical, remote, CREATOR_FIELDS, schema)
        self.assertEqual("unchanged", unchanged["action"])

    def test_account_missing_numeric_and_invalid_date_preserve_remote_values(self):
        service = self.service(Source(), StatefulClient())
        schema = field_schema(ACCOUNT_FIELDS)
        remote = {"record_id": "account-remote", "fields": {
            "账号唯一ID": "account-1", "KOLConnect Creator ID": "creator-1",
            "平台": "TikTok", "主页链接": {"text": "remote", "link": "https://remote"},
            "粉丝数": 300000, "平均播放量": 180000, "最后分析时间": 123,
        }}
        canonical = {
            "account_uid": "account-1", "creator_id": "creator-1", "platform": "",
            "profile_url": "", "followers": "", "average_views": math.nan,
            "last_analysis_at": "invalid",
        }
        item = service._plan_item("account-1", canonical, remote, ACCOUNT_FIELDS, schema)
        self.assertEqual("unchanged", item["action"])
        self.assertEqual({"账号唯一ID", "KOLConnect Creator ID"}, set(item["payload"]))
        self.assertEqual(5, len(item["preserved_remote_fields"]))

    def test_zero_is_meaningful_and_non_finite_numbers_are_omitted(self):
        service = self.service(Source(), StatefulClient())
        schema = field_schema(ACCOUNT_FIELDS)
        base = {
            "account_uid": "account-1", "creator_id": "creator-1", "platform": "TikTok",
            "profile_url": "https://example.com", "followers": 0, "average_views": 0,
            "last_analysis_at": "",
        }
        remote = {"record_id": "remote", "fields": {
            "账号唯一ID": "account-1", "KOLConnect Creator ID": "creator-1", "平台": "TikTok",
            "主页链接": {"text": "https://example.com", "link": "https://example.com"},
            "粉丝数": 10, "平均播放量": 20,
        }}
        zero = service._plan_item("account-1", base, remote, ACCOUNT_FIELDS, schema)
        self.assertEqual(0, zero["payload"]["粉丝数"])
        self.assertEqual(0, zero["payload"]["平均播放量"])
        for value in (math.nan, math.inf, -math.inf, "not-a-number"):
            with self.subTest(value=value):
                canonical = {**base, "followers": value, "average_views": value}
                item = service._plan_item("account-1", canonical, remote, ACCOUNT_FIELDS, schema)
                self.assertNotIn("粉丝数", item["payload"])
                self.assertNotIn("平均播放量", item["payload"])

    def test_archive_and_restore_are_both_authoritative(self):
        service = self.service(Source(), StatefulClient())
        schema = field_schema(CREATOR_FIELDS)
        base = {"creator_id": "creator-1", "name": "Creator", "archived": False}
        archived_remote = {"record_id": "r", "fields": {
            "KOLConnect Creator ID": "creator-1", "达人名称": "Creator", "已归档": True,
        }}
        restored = service._plan_item("creator-1", base, archived_remote, CREATOR_FIELDS, schema)
        self.assertIs(False, restored["payload"]["已归档"])
        active_remote = copy.deepcopy(archived_remote); active_remote["fields"]["已归档"] = False
        archived = service._plan_item(
            "creator-1", {**base, "archived": True}, active_remote, CREATOR_FIELDS, schema
        )
        self.assertIs(True, archived["payload"]["已归档"])

    def test_create_keeps_identities_and_excludes_non_finite_numbers(self):
        service = self.service(Source(), StatefulClient())
        schema = field_schema(ACCOUNT_FIELDS)
        canonical = {
            "account_uid": "account-1", "creator_id": "creator-1", "platform": "",
            "profile_url": "", "followers": math.inf, "average_views": math.nan,
            "last_analysis_at": "",
        }
        item = service._plan_item("account-1", canonical, None, ACCOUNT_FIELDS, schema)
        self.assertEqual("create", item["action"])
        self.assertEqual("account-1", item["payload"]["账号唯一ID"])
        self.assertEqual("creator-1", item["payload"]["KOLConnect Creator ID"])
        self.assertNotIn("粉丝数", item["payload"])
        self.assertNotIn("平均播放量", item["payload"])

    def test_payload_safety_summary_and_privacy_whitelist(self):
        source = Source([creator(country="", language="", content_category="")], [account(followers="")])
        client = StatefulClient()
        service = self.service(source, client)
        service.full_sync(confirm=True)
        client.records["creators"][0]["fields"].update({"国家/地区": "Brazil", "语言": "PT", "内容类型": "Gaming"})
        client.records["accounts"][0]["fields"]["粉丝数"] = 300000
        dry = service.dry_run()
        safety = dry["payload_safety"]
        self.assertEqual(0, safety["destructive_empty_overwrites"])
        self.assertGreaterEqual(safety["creator_remote_nonempty_values_preserved"], 3)
        self.assertGreaterEqual(safety["account_remote_nonempty_values_preserved"], 1)
        serialized = repr(client.create_calls if hasattr(client, "create_calls") else client.calls).casefold()
        for forbidden in (
            "private@example.com", "whatsapp", "notes", "cost", "performance_note",
            "mail", "quote", "roi", "token", "task", "local path",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
