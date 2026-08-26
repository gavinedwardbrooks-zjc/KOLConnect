from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from feishu_client import FeishuClientError  # noqa: E402
from feishu_client import FeishuClient  # noqa: E402
from http_handlers import feishu_delete_handler  # noqa: E402
from runtime_paths import atomic_write_json  # noqa: E402
from services.feishu_delete_intent_service import (  # noqa: E402
    FeishuDeleteIntentStore,
    FeishuDeleteReconciliationService,
)
from services.feishu_sync_service import ACCOUNT_UID_FIELD, CREATOR_ID_FIELD  # noqa: E402


NOW = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)


class FakeClient:
    creator_table_id = "creator_table"
    account_table_id = "account_table"

    def __init__(self, creators=None, accounts=None) -> None:
        self.records = {
            self.creator_table_id: list(creators or []),
            self.account_table_id: list(accounts or []),
        }
        self.calls: list[tuple[str, str]] = []
        self.failures: dict[str, list[FeishuClientError]] = {}
        self.auth_error: FeishuClientError | None = None
        self.fields = {
            self.creator_table_id: [{"field_name": CREATOR_ID_FIELD, "type": 1}],
            self.account_table_id: [{"field_name": ACCOUNT_UID_FIELD, "type": 1}],
        }

    def authenticate(self) -> None:
        if self.auth_error:
            raise self.auth_error

    def list_records(self, table_id: str):
        return [dict(item) for item in self.records[table_id]]

    def list_fields(self, table_id: str):
        return [dict(item) for item in self.fields[table_id]]

    def batch_delete(self, table_id: str, record_ids):
        record_id = list(record_ids)[0]
        self.calls.append((table_id, record_id))
        failures = self.failures.get(record_id) or []
        if failures:
            raise failures.pop(0)
        existing = {item["record_id"] for item in self.records[table_id]}
        if record_id not in existing:
            raise FeishuClientError("NOT_FOUND", "missing")
        self.records[table_id] = [
            item for item in self.records[table_id] if item["record_id"] != record_id
        ]
        return [{"record_id": record_id}]


def creator(record_id: str, creator_id: str):
    return {"record_id": record_id, "fields": {CREATOR_ID_FIELD: creator_id}}


def account(record_id: str, account_uid: str):
    return {"record_id": record_id, "fields": {ACCOUNT_UID_FIELD: account_uid}}


class FeishuDeleteIntentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory(prefix="pre_m8_feishu_delete_")
        self.root = Path(self.temp.name)
        self.store = FeishuDeleteIntentStore(self.root, now_provider=lambda: NOW)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def prepare(self, creator_id="creator-1", account_uids=None, operation="delete_operation"):
        return self.store.prepare(
            local_delete_operation_id=operation,
            creator_id=creator_id,
            account_uids=list(account_uids or ["uid-1"]),
        )

    def commit_marker(self, operation="delete_operation", *, committed=True, phase="COMMITTED"):
        path = self.root / "delete_transactions" / operation / "manifest.json"
        atomic_write_json(path, {
            "transaction_id": operation,
            "phase": phase,
            "commit_marker": committed,
        })

    def service(self, client: FakeClient):
        return FeishuDeleteReconciliationService(
            self.store, lambda: client, now_provider=lambda: NOW
        )

    def test_manifest_is_independent_minimal_and_secret_free(self) -> None:
        intent = self.prepare(account_uids=["uid-2", "uid-1", "uid-1"])
        path = self.root / "feishu_delete_intents" / f"{intent['intent_id']}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(["uid-1", "uid-2"], payload["account_uids"])
        self.assertNotIn("app_secret", payload)
        self.assertNotIn("access_token", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("email", payload)
        self.assertNotIn("name", payload)
        self.assertTrue(path.is_relative_to(self.root / "feishu_delete_intents"))

    def test_archive_restore_and_merge_cannot_create_delete_intents(self) -> None:
        for relative_path in (
            "services/creator_service.py",
            "services/creator_merge_service.py",
            "repositories/creator_merge_repository.py",
        ):
            source = (APP_DIR / relative_path).read_text(encoding="utf-8-sig")
            self.assertNotIn("FeishuDeleteIntentStore", source, relative_path)
            self.assertNotIn("feishu_delete_intent", source, relative_path)

    def test_prepare_recovery_aborts_without_local_commit(self) -> None:
        intent = self.prepare()
        recovered = self.store.recover_prepared()
        self.assertEqual("aborted", recovered[0]["status"])
        self.assertEqual("aborted", self.store.load(intent["intent_id"])["status"])

    def test_prepare_recovery_promotes_committed_local_delete(self) -> None:
        intent = self.prepare()
        self.commit_marker()
        recovered = self.store.recover_prepared()
        self.assertEqual("pending_remote", recovered[0]["status"])
        self.assertEqual("pending_remote", self.store.load(intent["intent_id"])["status"])

    def test_precommit_manifest_stays_prepared_until_local_recovery_decides(self) -> None:
        intent = self.prepare()
        self.commit_marker(committed=False, phase="MUTATING")
        self.assertEqual([], self.store.recover_prepared())
        self.assertEqual("prepared", self.store.load(intent["intent_id"])["status"])

    def test_processing_restart_returns_to_pending(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        self.store.transition(intent["intent_id"], "processing")
        recovered = self.store.recover_prepared()
        self.assertEqual("pending_remote", recovered[0]["status"])

    def test_one_account_deletes_account_before_creator(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        client = FakeClient([creator("creator-record", "creator-1")], [account("account-record", "uid-1")])
        result = self.service(client).reconcile()
        self.assertEqual([
            (client.account_table_id, "account-record"),
            (client.creator_table_id, "creator-record"),
        ], client.calls)
        self.assertEqual(1, result["completed"])

    def test_multiple_accounts_delete_all_before_creator(self) -> None:
        intent = self.prepare(account_uids=["uid-1", "uid-2", "uid-3"])
        self.store.promote_committed(intent["intent_id"])
        client = FakeClient(
            [creator("creator-record", "creator-1")],
            [account(f"account-{i}", f"uid-{i}") for i in range(1, 4)],
        )
        self.service(client).reconcile()
        self.assertEqual(client.creator_table_id, client.calls[-1][0])
        self.assertTrue(all(table == client.account_table_id for table, _ in client.calls[:-1]))

    def test_missing_account_and_creator_converge_idempotently(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        client = FakeClient()
        service = self.service(client)
        first = service.reconcile()
        second = service.reconcile()
        self.assertEqual(1, first["completed"])
        self.assertEqual(0, second["processed"])
        self.assertEqual([], client.calls)

    def test_known_remote_record_already_missing_converges(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        self.store.transition(
            intent["intent_id"], "pending_remote",
            creator_record_id="gone-creator",
            account_record_ids={"uid-1": "gone-account"},
        )
        result = self.service(FakeClient()).reconcile()
        self.assertEqual(1, result["completed"])

    def test_transient_network_rate_limit_and_server_errors_schedule_retry(self) -> None:
        for code in ("TRANSIENT_NETWORK_ERROR", "RATE_LIMITED", "TRANSIENT_REMOTE_ERROR"):
            with self.subTest(code=code):
                root = self.root / code
                store = FeishuDeleteIntentStore(root, now_provider=lambda: NOW)
                intent = store.prepare(local_delete_operation_id="op", creator_id="c", account_uids=[])
                store.promote_committed(intent["intent_id"])
                client = FakeClient([creator("r", "c")], [])
                client.auth_error = FeishuClientError(code, "safe")
                service = FeishuDeleteReconciliationService(store, lambda: client, now_provider=lambda: NOW)
                result = service.reconcile()
                saved = store.load(intent["intent_id"])
                self.assertEqual("retry_wait", saved["status"])
                self.assertEqual(code, saved["last_error_code"])
                self.assertEqual(1, result["retrying"])

    def test_permission_auth_and_configuration_failures_block_safely(self) -> None:
        for code in ("PERMISSION_DENIED", "AUTHENTICATION_FAILED", "CONFIGURATION_ERROR"):
            with self.subTest(code=code):
                root = self.root / code
                store = FeishuDeleteIntentStore(root, now_provider=lambda: NOW)
                intent = store.prepare(local_delete_operation_id="op", creator_id="c", account_uids=[])
                store.promote_committed(intent["intent_id"])
                client = FakeClient()
                client.auth_error = FeishuClientError(code, "safe")
                FeishuDeleteReconciliationService(store, lambda: client, now_provider=lambda: NOW).reconcile()
                saved = store.load(intent["intent_id"])
                self.assertEqual("blocked", saved["status"])
                self.assertTrue(saved["operator_retryable"])

    def test_ambiguous_creator_identity_blocks_without_delete(self) -> None:
        intent = self.prepare(account_uids=[])
        self.store.promote_committed(intent["intent_id"])
        client = FakeClient([creator("r1", "creator-1"), creator("r2", "creator-1")], [])
        self.service(client).reconcile()
        saved = self.store.load(intent["intent_id"])
        self.assertEqual("blocked", saved["status"])
        self.assertEqual("AMBIGUOUS_REMOTE_IDENTITY", saved["last_error_code"])
        self.assertEqual([], client.calls)

    def test_missing_or_incompatible_identity_schema_blocks_fail_closed(self) -> None:
        for fields in ([], [{"field_name": CREATOR_ID_FIELD, "type": 20}]):
            with self.subTest(fields=fields):
                root = self.root / f"schema-{len(fields)}-{fields[0]['type'] if fields else 0}"
                store = FeishuDeleteIntentStore(root, now_provider=lambda: NOW)
                intent = store.prepare(local_delete_operation_id="op", creator_id="c", account_uids=[])
                store.promote_committed(intent["intent_id"])
                client = FakeClient([creator("remote", "c")], [])
                client.fields[client.creator_table_id] = fields
                FeishuDeleteReconciliationService(store, lambda: client, now_provider=lambda: NOW).reconcile()
                saved = store.load(intent["intent_id"])
                self.assertEqual("blocked", saved["status"])
                self.assertEqual("SCHEMA_INVALID", saved["last_error_code"])
                self.assertEqual([], client.calls)

    def test_ambiguous_account_identity_blocks_without_delete(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        client = FakeClient(
            [creator("creator-record", "creator-1")],
            [account("a1", "uid-1"), account("a2", "uid-1")],
        )
        self.service(client).reconcile()
        saved = self.store.load(intent["intent_id"])
        self.assertEqual("blocked", saved["status"])
        self.assertEqual([], client.calls)

    def test_partial_multi_account_failure_persists_progress_and_resumes(self) -> None:
        intent = self.prepare(account_uids=["uid-1", "uid-2", "uid-3"])
        self.store.promote_committed(intent["intent_id"])
        client = FakeClient(
            [creator("creator-record", "creator-1")],
            [account(f"account-{i}", f"uid-{i}") for i in range(1, 4)],
        )
        client.failures["account-3"] = [FeishuClientError("TRANSIENT_NETWORK_ERROR", "safe")]
        service = self.service(client)
        service.reconcile()
        saved = self.store.load(intent["intent_id"])
        self.assertEqual("retry_wait", saved["status"])
        self.assertEqual(["uid-1", "uid-2"], saved["deleted_account_uids"])
        self.assertNotIn((client.creator_table_id, "creator-record"), client.calls)
        self.store.transition(intent["intent_id"], "retry_wait", next_retry_at="2026-08-25T09:00:00Z")
        service.reconcile()
        saved = self.store.load(intent["intent_id"])
        self.assertEqual("completed", saved["status"])
        self.assertEqual(1, client.calls.count((client.account_table_id, "account-1")))
        self.assertEqual(1, client.calls.count((client.account_table_id, "account-2")))
        self.assertEqual((client.creator_table_id, "creator-record"), client.calls[-1])

    def test_restart_after_all_accounts_deleted_only_deletes_creator(self) -> None:
        intent = self.prepare(account_uids=["uid-1", "uid-2"])
        self.store.promote_committed(intent["intent_id"])
        self.store.transition(
            intent["intent_id"], "pending_remote",
            deleted_account_uids=["uid-1", "uid-2"],
            account_record_ids={"uid-1": "gone-1", "uid-2": "gone-2"},
        )
        client = FakeClient([creator("creator-record", "creator-1")], [])
        self.service(client).reconcile()
        self.assertEqual([(client.creator_table_id, "creator-record")], client.calls)

    def test_restart_after_creator_delete_before_completed_flag_converges(self) -> None:
        intent = self.prepare(account_uids=[])
        self.store.promote_committed(intent["intent_id"])
        self.store.transition(
            intent["intent_id"], "pending_remote",
            creator_record_id="gone-creator",
            creator_deleted=True,
        )
        client = FakeClient()
        self.service(client).reconcile()
        self.assertEqual("completed", self.store.load(intent["intent_id"])["status"])
        self.assertEqual([], client.calls)

    def test_completed_replay_and_unrelated_records_are_untouched(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        client = FakeClient(
            [creator("target-c", "creator-1"), creator("other-c", "creator-2")],
            [account("target-a", "uid-1"), account("other-a", "uid-2")],
        )
        service = self.service(client)
        service.reconcile()
        calls = list(client.calls)
        service.reconcile()
        self.assertEqual(calls, client.calls)
        self.assertEqual(["other-c"], [item["record_id"] for item in client.records[client.creator_table_id]])
        self.assertEqual(["other-a"], [item["record_id"] for item in client.records[client.account_table_id]])

    def test_status_is_safe_and_does_not_expose_remote_record_ids(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        self.store.transition(intent["intent_id"], "pending_remote", creator_record_id="private-record")
        status = self.service(FakeClient()).status()
        self.assertEqual(1, status["pending"])
        rendered = json.dumps(status)
        self.assertNotIn("private-record", rendered)
        self.assertNotIn("account_record_ids", rendered)

    def test_retry_wait_not_due_does_not_call_remote(self) -> None:
        intent = self.prepare()
        self.store.promote_committed(intent["intent_id"])
        self.store.transition(intent["intent_id"], "processing")
        self.store.transition(
            intent["intent_id"], "retry_wait",
            next_retry_at=(NOW + timedelta(hours=1)).isoformat(),
        )
        client = FakeClient()
        result = self.service(client).reconcile()
        self.assertEqual(0, result["processed"])
        self.assertEqual([], client.calls)

    def test_invalid_transition_and_identity_mutation_are_rejected(self) -> None:
        intent = self.prepare()
        with self.assertRaises(ValueError):
            self.store.transition(intent["intent_id"], "completed")
        with self.assertRaises(ValueError):
            self.store.transition(intent["intent_id"], "prepared", creator_id="other")

    def test_feishu_client_maps_http_404_to_not_found(self) -> None:
        class Response:
            status_code = 404
            headers = {}

            @staticmethod
            def json():
                return {"code": 0}

        class Transport:
            @staticmethod
            def request(*_args, **_kwargs):
                return Response()

        client = FeishuClient({
            "app_id": "app", "app_secret": "secret", "app_token": "base",
            "creator_table_id": "creators", "account_table_id": "accounts",
        }, transport=Transport())
        client._access_token = "test-token"
        with self.assertRaises(FeishuClientError) as caught:
            client.batch_delete("creators", ["missing"])
        self.assertEqual("NOT_FOUND", caught.exception.code)


class FeishuDeleteIntentHandlerTests(unittest.TestCase):
    class Handler:
        def __init__(self):
            self.response = None

        def _json(self, data, status=200):
            self.response = (status, data)

    class Service:
        def __init__(self):
            self.reconcile_calls = 0

        @staticmethod
        def status():
            return {"pending": 1, "blocked": 0}

        def reconcile(self, *, max_intents):
            self.reconcile_calls += 1
            return {"processed": 1, "max_intents": max_intents}

    def request(self, method, path, payload=None):
        return {
            "method": method,
            "path": path,
            "get_payload": lambda: dict(payload or {}),
        }

    def test_status_is_read_only_and_reconcile_requires_confirmation(self) -> None:
        handler = self.Handler()
        service = self.Service()
        context = {"services": {"feishu_delete_reconciliation": service}}
        self.assertTrue(feishu_delete_handler.handle(
            handler, self.request("GET", "/api/feishu-delete-intents/status"), context
        ))
        self.assertEqual(200, handler.response[0])
        self.assertEqual(0, service.reconcile_calls)
        feishu_delete_handler.handle(
            handler, self.request("POST", "/api/feishu-delete-intents/reconcile"), context
        )
        self.assertEqual(400, handler.response[0])
        self.assertEqual(0, service.reconcile_calls)
        feishu_delete_handler.handle(
            handler,
            self.request("POST", "/api/feishu-delete-intents/reconcile", {"confirm": True}),
            context,
        )
        self.assertEqual(200, handler.response[0])
        self.assertEqual(1, service.reconcile_calls)


if __name__ == "__main__":
    unittest.main()
