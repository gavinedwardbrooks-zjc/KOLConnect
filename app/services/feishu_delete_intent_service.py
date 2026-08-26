from __future__ import annotations

"""Durable lifecycle outbox for Feishu replicas of hard-deleted Creators."""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from feishu_client import FeishuClient, FeishuClientError
from local_storage_lock import shared_storage_lock
from runtime_paths import atomic_write_json
from services.feishu_sync_service import ACCOUNT_UID_FIELD, CREATOR_ID_FIELD


INTENT_STATES = frozenset({
    "prepared", "pending_remote", "processing", "retry_wait", "blocked",
    "completed", "aborted",
})
ALLOWED_TRANSITIONS = {
    "prepared": frozenset({"pending_remote", "aborted", "blocked"}),
    "pending_remote": frozenset({"processing", "completed", "blocked"}),
    "processing": frozenset({"pending_remote", "retry_wait", "blocked", "completed"}),
    "retry_wait": frozenset({"processing", "blocked", "completed"}),
    "blocked": frozenset({"processing"}),
    "completed": frozenset(),
    "aborted": frozenset(),
}
INTENT_ID_PATTERN = re.compile(r"^feishu_delete_[0-9a-f]{32}$")
RETRYABLE_ERROR_CODES = frozenset({
    "TRANSIENT_NETWORK_ERROR", "RATE_LIMITED", "TRANSIENT_REMOTE_ERROR",
})
OPERATOR_RETRYABLE_ERROR_CODES = frozenset({
    "CONFIGURATION_ERROR", "AUTHENTICATION_FAILED", "PERMISSION_DENIED",
    "SCHEMA_INVALID",
})
RETRY_DELAYS_SECONDS = (60, 300, 900, 1800, 3600, 7200, 14400, 28800)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class FeishuDeleteIntentStore:
    """Persist minimal external-lifecycle state independently from business data."""

    def __init__(
        self,
        runtime_data_dir: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.runtime_data_dir = Path(runtime_data_dir)
        self.root = self.runtime_data_dir / "feishu_delete_intents"
        self._now_provider = now_provider or _utc_now

    def prepare(
        self,
        *,
        local_delete_operation_id: str,
        creator_id: str,
        account_uids: list[str],
    ) -> dict[str, Any]:
        operation_id = str(local_delete_operation_id or "").strip()
        creator_id = str(creator_id or "").strip()
        normalized_uids = sorted({str(item or "").strip() for item in account_uids if str(item or "").strip()})
        if not operation_id or not creator_id:
            raise ValueError("Delete intent requires exact local identities.")
        now = _iso(self._now_provider())
        intent = {
            "intent_id": f"feishu_delete_{uuid.uuid4().hex}",
            "local_delete_operation_id": operation_id,
            "creator_id": creator_id,
            "account_uids": normalized_uids,
            "creator_record_id": "",
            "account_record_ids": {},
            "deleted_account_uids": [],
            "creator_deleted": False,
            "status": "prepared",
            "attempt_count": 0,
            "last_error_code": "",
            "next_retry_at": "",
            "operator_retryable": False,
            "created_at": now,
            "updated_at": now,
        }
        self._validate(intent)
        with shared_storage_lock():
            self.root.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self._path(intent["intent_id"]), intent)
        return dict(intent)

    def load(self, intent_id: str) -> dict[str, Any]:
        path = self._path(intent_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Feishu delete intent cannot be read safely.") from exc
        self._validate(value)
        return value

    def list(self) -> list[dict[str, Any]]:
        with shared_storage_lock():
            if not self.root.is_dir():
                return []
            result: list[dict[str, Any]] = []
            for path in sorted(self.root.glob("feishu_delete_*.json")):
                try:
                    result.append(self.load(path.stem))
                except (RuntimeError, ValueError):
                    result.append({
                        "intent_id": path.stem,
                        "status": "blocked",
                        "last_error_code": "MALFORMED_INTENT",
                    })
            return result

    def transition(
        self, intent_id: str, status: str, **updates: Any
    ) -> dict[str, Any]:
        with shared_storage_lock():
            intent = self.load(intent_id)
            current = intent["status"]
            if status != current and status not in ALLOWED_TRANSITIONS[current]:
                raise ValueError("Invalid Feishu delete intent transition.")
            forbidden = {
                "intent_id", "local_delete_operation_id", "creator_id", "account_uids",
                "created_at",
            }
            if forbidden & set(updates):
                raise ValueError("Immutable Feishu delete intent identity cannot change.")
            intent.update(updates)
            intent["status"] = status
            intent["updated_at"] = _iso(self._now_provider())
            self._validate(intent)
            atomic_write_json(self._path(intent_id), intent)
            return intent

    def promote_committed(self, intent_id: str) -> dict[str, Any]:
        return self.transition(
            intent_id,
            "pending_remote",
            last_error_code="",
            next_retry_at="",
        )

    def abort(self, intent_id: str) -> dict[str, Any]:
        return self.transition(
            intent_id,
            "aborted",
            last_error_code="LOCAL_DELETE_NOT_COMMITTED",
            next_retry_at="",
        )

    def recover_prepared(self) -> list[dict[str, Any]]:
        """Resolve prepared/processing intents from durable local commit markers."""
        recovered: list[dict[str, Any]] = []
        for intent in self.list():
            status = intent.get("status")
            if status == "processing":
                recovered.append(self.transition(
                    intent["intent_id"], "pending_remote", last_error_code="PROCESS_INTERRUPTED"
                ))
                continue
            if status != "prepared":
                continue
            local_state = self._local_delete_state(intent["local_delete_operation_id"])
            if local_state == "committed":
                recovered.append(self.promote_committed(intent["intent_id"]))
            elif local_state == "not_committed":
                recovered.append(self.abort(intent["intent_id"]))
        return recovered

    def _local_delete_state(self, operation_id: str) -> str:
        path = self.runtime_data_dir / "delete_transactions" / operation_id / "manifest.json"
        if not path.is_file():
            return "not_committed"
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "unknown"
        if manifest.get("transaction_id") != operation_id:
            return "unknown"
        if manifest.get("commit_marker") is True:
            return "committed"
        if manifest.get("phase") == "ROLLED_BACK":
            return "not_committed"
        return "unknown"

    def _path(self, intent_id: str) -> Path:
        value = str(intent_id or "").strip()
        if not INTENT_ID_PATTERN.fullmatch(value):
            raise ValueError("Feishu delete intent ID is invalid.")
        return self.root / f"{value}.json"

    @staticmethod
    def _validate(value: Any) -> None:
        if not isinstance(value, dict):
            raise RuntimeError("Feishu delete intent is invalid.")
        required = {
            "intent_id", "local_delete_operation_id", "creator_id", "account_uids",
            "creator_record_id", "account_record_ids", "deleted_account_uids",
            "creator_deleted", "status", "attempt_count", "last_error_code",
            "next_retry_at", "created_at", "updated_at",
            "operator_retryable",
        }
        if not required.issubset(value) or not INTENT_ID_PATTERN.fullmatch(str(value.get("intent_id") or "")):
            raise RuntimeError("Feishu delete intent is invalid.")
        if value.get("status") not in INTENT_STATES:
            raise RuntimeError("Feishu delete intent state is invalid.")
        if not str(value.get("local_delete_operation_id") or "").strip() or not str(value.get("creator_id") or "").strip():
            raise RuntimeError("Feishu delete intent identity is invalid.")
        account_uids = value.get("account_uids")
        if not isinstance(account_uids, list) or any(not str(item or "").strip() for item in account_uids):
            raise RuntimeError("Feishu delete account identity is invalid.")
        if len(account_uids) != len(set(account_uids)):
            raise RuntimeError("Feishu delete account identity is ambiguous.")
        if not isinstance(value.get("account_record_ids"), dict) or not isinstance(value.get("deleted_account_uids"), list):
            raise RuntimeError("Feishu delete progress is invalid.")
        if not isinstance(value.get("attempt_count"), int) or value["attempt_count"] < 0:
            raise RuntimeError("Feishu delete retry state is invalid.")
        if not isinstance(value.get("operator_retryable"), bool):
            raise RuntimeError("Feishu delete operator state is invalid.")


class FeishuDeleteReconciliationService:
    """Converge durable delete intents without coupling remote availability to local delete."""

    def __init__(
        self,
        store: FeishuDeleteIntentStore,
        client_provider: Callable[[], FeishuClient],
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._client_provider = client_provider
        self._now_provider = now_provider or _utc_now

    def status(self) -> dict[str, Any]:
        intents = self.store.list()
        counts = {state: 0 for state in INTENT_STATES}
        for intent in intents:
            counts[str(intent.get("status") or "blocked")] += 1
        return {
            "total": len(intents),
            "pending": sum(counts[state] for state in ("prepared", "pending_remote", "processing", "retry_wait")),
            "retrying": counts["retry_wait"],
            "blocked": counts["blocked"],
            "completed": counts["completed"],
            "aborted": counts["aborted"],
            "items": [self._public_item(item) for item in intents],
        }

    def reconcile(self, *, max_intents: int = 10) -> dict[str, Any]:
        self.store.recover_prepared()
        now = self._now_provider()
        candidates = []
        for intent in self.store.list():
            status = intent.get("status")
            due = _parse_time(intent.get("next_retry_at"))
            retryable_block = bool(intent.get("operator_retryable"))
            if status == "pending_remote" or (status == "retry_wait" and (due is None or due <= now)) or (status == "blocked" and retryable_block):
                candidates.append(intent)
        processed = []
        for intent in candidates[:max(0, int(max_intents))]:
            processed.append(self._process(intent))
        result = self.status()
        result["processed"] = len(processed)
        return result

    def _process(self, intent: dict[str, Any]) -> dict[str, Any]:
        intent = self.store.transition(
            intent["intent_id"],
            "processing",
            attempt_count=int(intent.get("attempt_count") or 0) + 1,
            last_error_code="",
            next_retry_at="",
            operator_retryable=False,
        )
        try:
            client = self._client_provider()
            client.authenticate()
            self._require_identity_field(
                client.list_fields(client.creator_table_id), CREATOR_ID_FIELD
            )
            self._require_identity_field(
                client.list_fields(client.account_table_id), ACCOUNT_UID_FIELD
            )
            creator_records = client.list_records(client.creator_table_id)
            account_records = client.list_records(client.account_table_id)
            creator_record_id = self._resolve_exact(
                creator_records, CREATOR_ID_FIELD, intent["creator_id"], intent.get("creator_record_id")
            )
            account_ids = dict(intent.get("account_record_ids") or {})
            for account_uid in intent["account_uids"]:
                account_ids[account_uid] = self._resolve_exact(
                    account_records, ACCOUNT_UID_FIELD, account_uid, account_ids.get(account_uid)
                )
            intent = self.store.transition(
                intent["intent_id"], "processing",
                creator_record_id=creator_record_id,
                account_record_ids=account_ids,
            )
            deleted = set(intent.get("deleted_account_uids") or [])
            for account_uid in intent["account_uids"]:
                if account_uid in deleted:
                    continue
                record_id = account_ids.get(account_uid, "")
                if record_id:
                    self._delete_one(client, client.account_table_id, record_id)
                deleted.add(account_uid)
                intent = self.store.transition(
                    intent["intent_id"], "processing",
                    deleted_account_uids=sorted(deleted),
                )
            if not intent.get("creator_deleted"):
                if creator_record_id:
                    self._delete_one(client, client.creator_table_id, creator_record_id)
                intent = self.store.transition(
                    intent["intent_id"], "processing", creator_deleted=True
                )
            return self.store.transition(
                intent["intent_id"], "completed",
                last_error_code="",
                next_retry_at="",
                operator_retryable=False,
            )
        except FeishuClientError as exc:
            return self._record_error(intent["intent_id"], exc.code)
        except AmbiguousRemoteIdentity:
            return self.store.transition(
                intent["intent_id"], "blocked",
                last_error_code="AMBIGUOUS_REMOTE_IDENTITY",
                next_retry_at="",
                operator_retryable=False,
            )
        except (RuntimeError, ValueError, TypeError):
            return self.store.transition(
                intent["intent_id"], "blocked",
                last_error_code="MALFORMED_INTENT",
                next_retry_at="",
                operator_retryable=False,
            )

    def _record_error(self, intent_id: str, code: str) -> dict[str, Any]:
        intent = self.store.load(intent_id)
        attempts = int(intent.get("attempt_count") or 0)
        if code in RETRYABLE_ERROR_CODES and attempts <= len(RETRY_DELAYS_SECONDS):
            retry_at = self._now_provider() + timedelta(seconds=RETRY_DELAYS_SECONDS[attempts - 1])
            return self.store.transition(
                intent_id, "retry_wait",
                last_error_code=code,
                next_retry_at=_iso(retry_at),
                operator_retryable=False,
            )
        return self.store.transition(
            intent_id, "blocked",
            last_error_code=code,
            next_retry_at="",
            operator_retryable=code in OPERATOR_RETRYABLE_ERROR_CODES,
        )

    @classmethod
    def _resolve_exact(
        cls,
        records: list[dict[str, Any]],
        field_name: str,
        identity: str,
        known_record_id: object = "",
    ) -> str:
        known = str(known_record_id or "").strip()
        by_record_id = {
            str(item.get("record_id") or "").strip(): item
            for item in records if str(item.get("record_id") or "").strip()
        }
        if known:
            return known if known in by_record_id else ""
        matches = [
            str(item.get("record_id") or "").strip()
            for item in records
            if cls._field_text((item.get("fields") or {}).get(field_name)) == identity
        ]
        matches = [item for item in matches if item]
        if len(matches) > 1:
            raise AmbiguousRemoteIdentity(identity)
        return matches[0] if matches else ""

    @staticmethod
    def _field_text(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("text") or value.get("link") or value.get("value") or "").strip()
        if isinstance(value, list):
            return FeishuDeleteReconciliationService._field_text(value[0]) if len(value) == 1 else ""
        return str(value or "").strip()

    @staticmethod
    def _require_identity_field(fields: list[dict[str, Any]], name: str) -> None:
        matches = [
            item for item in fields
            if str(item.get("field_name") or item.get("name") or "").strip() == name
        ]
        if len(matches) != 1 or int(matches[0].get("type") or 0) != 1:
            raise FeishuClientError("SCHEMA_INVALID", "飞书身份字段结构不兼容。")

    @staticmethod
    def _delete_one(client: FeishuClient, table_id: str, record_id: str) -> None:
        try:
            client.batch_delete(table_id, [record_id])
        except FeishuClientError as exc:
            if exc.code != "NOT_FOUND":
                raise

    @staticmethod
    def _public_item(intent: dict[str, Any]) -> dict[str, Any]:
        return {
            "intent_id": str(intent.get("intent_id") or ""),
            "creator_id": str(intent.get("creator_id") or ""),
            "status": str(intent.get("status") or "blocked"),
            "attempt_count": int(intent.get("attempt_count") or 0),
            "last_error_code": str(intent.get("last_error_code") or ""),
            "next_retry_at": str(intent.get("next_retry_at") or ""),
            "created_at": str(intent.get("created_at") or ""),
            "updated_at": str(intent.get("updated_at") or ""),
        }


class AmbiguousRemoteIdentity(RuntimeError):
    pass
