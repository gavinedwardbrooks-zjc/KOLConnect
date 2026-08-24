from __future__ import annotations

"""One-time, fail-closed cleanup of exactly 16 unmanaged Feishu Creator rows."""

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Callable, Protocol

from feishu_client import FeishuClient, FeishuClientError
from services.feishu_sync_service import (
    ACCOUNT_CREATOR_ID_FIELD,
    ACCOUNT_UID_FIELD,
    CREATOR_ID_FIELD,
    LEGACY_CREATOR_RELATION_FIELD,
    FeishuSyncService,
)


EXPECTED_TARGET_COUNT = 16
CREATOR_NAME_FIELD = "达人名称"
LEGACY_CREATOR_ID_FIELD = "达人ID"


class CreatorIdentitySource(Protocol):
    def getCreatorAccountIdentityRows(self) -> dict[str, list[dict[str, Any]]]: ...


class LegacyCreatorCleanupService:
    """Delete only the currently revalidated unmanaged Creator inventory."""

    MODE = "legacy_unmanaged_creator_cleanup"

    def __init__(
        self,
        repository: CreatorIdentitySource,
        client_provider: Callable[[], FeishuClient],
    ) -> None:
        self._repository = repository
        self._client_provider = client_provider

    def preview(self) -> dict[str, Any]:
        return self._public_plan(self._build_plan(expected_count=EXPECTED_TARGET_COUNT))

    def execute(self, *, confirm: object) -> dict[str, Any]:
        if confirm is not True:
            raise ValueError("FEISHU_LEGACY_CREATOR_CLEANUP_CONFIRMATION_REQUIRED")

        initial = self._build_plan(expected_count=EXPECTED_TARGET_COUNT)
        result = self._public_plan(initial)
        if initial["status"] == "blocked":
            return result

        initial_ids = [item["remote_record_id"] for item in initial["targets"]]
        pending = list(initial_ids)
        account_before = self._account_snapshot(initial["remote_account_records"])
        local_before = initial["local_snapshot"]
        managed_before = initial["summary"]["managed_remote_creators"]
        result.update({
            "attempted": 0,
            "succeeded": 0,
            "failed": 0,
            "remaining": len(pending),
            "error_codes": [],
            "batches": [],
            "creator_create_count": 0,
            "creator_update_count": 0,
            "creator_delete_count": 0,
            "account_create_count": 0,
            "account_update_count": 0,
            "account_delete_count": 0,
            "excel_write_count": 0,
        })

        while pending:
            current = self._build_plan(
                expected_count=len(pending), expected_record_ids=set(pending)
            )
            if current["status"] == "blocked":
                return self._stop(result, current.get("blocked_reason", "CLEANUP_BLOCKED"))
            client = current["client"]
            self._assert_creator_only_delete(client)
            batch_ids = pending[: max(1, int(client.batch_size))]
            batch_result = {
                "batch": len(result["batches"]) + 1,
                "attempted": len(batch_ids),
                "succeeded": 0,
                "failed": 0,
                "status": "pending",
            }
            result["attempted"] += len(batch_ids)
            try:
                deleted = client.batch_delete(client.creator_table_id, batch_ids)
                deleted_ids = {
                    self._text(item.get("record_id") or item.get("id"))
                    for item in deleted
                    if isinstance(item, dict) and item.get("deleted") is True
                }
                if deleted_ids != set(batch_ids):
                    raise FeishuClientError(
                        "REMOTE_ERROR", "飞书 Creator 删除结果数量或身份不一致。"
                    )
            except FeishuClientError as exc:
                batch_result.update({
                    "failed": len(batch_ids), "status": "failed", "error_code": exc.code,
                })
                result["batches"].append(batch_result)
                result["failed"] = len(batch_ids)
                result["error_codes"] = [exc.code]
                return self._stop(result, "FEISHU_CREATOR_DELETE_FAILED")

            result["succeeded"] += len(batch_ids)
            result["creator_delete_count"] += len(batch_ids)
            pending = pending[len(batch_ids):]
            result["remaining"] = len(pending)
            batch_result.update({"succeeded": len(batch_ids), "status": "success"})
            result["batches"].append(batch_result)

        verification = self._verify_after_delete(
            account_before=account_before,
            local_before=local_before,
            managed_before=managed_before,
            deleted_ids=set(initial_ids),
        )
        result["verification"] = verification
        if verification["status"] != "success":
            result["status"] = "partial"
            result["blocked_reason"] = verification["blocked_reason"]
            return result
        result["status"] = "success"
        result["blocked_reason"] = ""
        return result

    def _build_plan(
        self,
        *,
        expected_count: int,
        expected_record_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        client = self._client_provider()
        try:
            client.authenticate()
            creator_schema = FeishuSyncService._field_index(
                client.list_fields(client.creator_table_id)
            )
            account_schema = FeishuSyncService._field_index(
                client.list_fields(client.account_table_id)
            )
            missing = []
            if CREATOR_ID_FIELD not in creator_schema:
                missing.append({"table": "creator", "field": CREATOR_ID_FIELD})
            for field in (ACCOUNT_UID_FIELD, ACCOUNT_CREATOR_ID_FIELD):
                if field not in account_schema:
                    missing.append({"table": "account", "field": field})
            if missing:
                return self._blocked("FEISHU_CLEANUP_SCHEMA_INVALID", missing_fields=missing)
            local = self._repository.getCreatorAccountIdentityRows()
            remote_creators = client.list_records(client.creator_table_id)
            remote_accounts = client.list_records(client.account_table_id)
        except FeishuClientError as exc:
            return self._blocked(exc.code, error_codes=[exc.code])

        creator_rows = [dict(row) for row in local.get("creators", [])]
        account_rows = [dict(row) for row in local.get("accounts", [])]
        local_creator_counts = Counter(self._text(row.get("creator_id")) for row in creator_rows)
        local_account_counts = Counter(self._text(row.get("account_uid")) for row in account_rows)
        local_creator_ids = {identity for identity in local_creator_counts if identity}
        local_accounts = {
            self._text(row.get("account_uid")): row
            for row in account_rows
            if self._text(row.get("account_uid"))
            and local_account_counts[self._text(row.get("account_uid"))] == 1
        }
        creator_index, creator_conflicts, unmanaged = FeishuSyncService._remote_index(
            remote_creators, CREATOR_ID_FIELD, "creator"
        )
        remote_unknown_ids = sorted(set(creator_index) - local_creator_ids)
        identity_conflicts = list(creator_conflicts)
        identity_conflicts.extend({
            "entity_type": "creator", "identity": identity,
            "reason": "remote_creator_id_not_in_local_inventory",
        } for identity in remote_unknown_ids)
        if any(not identity for identity in local_creator_counts):
            identity_conflicts.append({
                "entity_type": "creator", "identity": "",
                "reason": "missing_local_creator_id",
            })
        identity_conflicts.extend({
            "entity_type": "creator", "identity": identity,
            "reason": "duplicate_local_creator_id",
        } for identity, count in local_creator_counts.items() if identity and count > 1)

        incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        remote_uid_counts = Counter()
        account_record_ids = [self._text(account.get("record_id")) for account in remote_accounts]
        account_snapshot_safe = (
            all(account_record_ids) and len(account_record_ids) == len(set(account_record_ids))
        )
        for account in remote_accounts:
            fields = dict(account.get("fields") or {})
            uid = FeishuSyncService._field_text(fields.get(ACCOUNT_UID_FIELD))
            if uid:
                remote_uid_counts[uid] += 1
            for creator_record_id in FeishuSyncService._relation_ids(
                fields.get(LEGACY_CREATOR_RELATION_FIELD)
            ):
                incoming[creator_record_id].append(account)

        targets = []
        record_ids = []
        relation_blocked = False
        for record in unmanaged:
            record_id = self._text(record.get("record_id"))
            fields = dict(record.get("fields") or {})
            relations = incoming.get(record_id, [])
            relation_status, relation_safe = self._relation_status(
                relations, local_accounts, remote_uid_counts, local_creator_ids
            )
            relation_blocked = relation_blocked or not relation_safe
            record_ids.append(record_id)
            targets.append({
                "remote_record_id": record_id,
                "display_name": FeishuSyncService._field_text(fields.get(CREATOR_NAME_FIELD)),
                "legacy_id": FeishuSyncService._field_text(fields.get(LEGACY_CREATOR_ID_FIELD)),
                "current_creator_id": FeishuSyncService._field_text(fields.get(CREATOR_ID_FIELD)),
                "incoming_account_relation_count": len(relations),
                "relation_status": relation_status,
                "delete_eligible": bool(record_id and relation_safe),
            })
        targets.sort(key=lambda item: item["remote_record_id"])

        blocked_reason = ""
        if len(unmanaged) != expected_count:
            blocked_reason = "CLEANUP_BLOCKED_COUNT_MISMATCH"
        elif expected_record_ids is not None and set(record_ids) != expected_record_ids:
            blocked_reason = "CLEANUP_TARGET_SET_CHANGED"
        elif not all(record_ids) or len(record_ids) != len(set(record_ids)):
            blocked_reason = "CLEANUP_TARGET_IDENTITY_INVALID"
        elif identity_conflicts:
            blocked_reason = "CLEANUP_BLOCKED_IDENTITY_CONFLICT"
        elif relation_blocked or not account_snapshot_safe:
            blocked_reason = "CLEANUP_BLOCKED_RELATION_RISK"
        elif client.creator_table_id == client.account_table_id:
            blocked_reason = "FEISHU_ACCOUNT_AND_CREATOR_TABLE_IDS_MUST_DIFFER"

        gates = {
            "G1_unmanaged_count_exact": len(unmanaged) == expected_count,
            "G2_target_count_exact": len(targets) == expected_count,
            "G3_unique_record_ids": bool(record_ids) and len(record_ids) == len(set(record_ids)),
            "G4_targets_have_no_managed_id": all(not item["current_creator_id"] for item in targets),
            "G5_managed_records_excluded": not (set(record_ids) & {
                self._text(item.get("record_id")) for item in creator_index.values()
            }),
            "G6_identity_conflicts_zero": not identity_conflicts,
            "G7_excel_writes_zero": True,
            "G8_account_mutations_zero": True,
            "G9_relation_risk_zero": not relation_blocked and account_snapshot_safe,
            "G10_sensitive_fields_not_required": True,
        }
        return {
            "mode": self.MODE,
            "status": "blocked" if blocked_reason else "success",
            "blocked_reason": blocked_reason,
            "summary": {
                "local_creators": len(creator_rows),
                "local_accounts": len(account_rows),
                "remote_creators": len(remote_creators),
                "remote_accounts": len(remote_accounts),
                "managed_remote_creators": len(creator_index),
                "unmanaged_remote_creators": len(unmanaged),
                "identity_conflicts": len(identity_conflicts),
            },
            "targets": targets,
            "gates": gates,
            "error_codes": [],
            "missing_fields": [],
            "client": client,
            "remote_account_records": deepcopy(remote_accounts),
            "local_snapshot": self._local_snapshot(creator_rows, account_rows),
        }

    @classmethod
    def _relation_status(
        cls,
        relations: list[dict[str, Any]],
        local_accounts: dict[str, dict[str, Any]],
        remote_uid_counts: Counter,
        local_creator_ids: set[str],
    ) -> tuple[str, bool]:
        if not relations:
            return "NO_RELATION", True
        managed = 0
        ambiguous = 0
        for account in relations:
            fields = dict(account.get("fields") or {})
            uid = FeishuSyncService._field_text(fields.get(ACCOUNT_UID_FIELD))
            creator_id = FeishuSyncService._field_text(fields.get(ACCOUNT_CREATOR_ID_FIELD))
            local = local_accounts.get(uid)
            if (
                uid and remote_uid_counts[uid] == 1 and local is not None
                and creator_id in local_creator_ids
                and creator_id == cls._text(local.get("creator_id"))
            ):
                managed += 1
            elif uid or creator_id:
                ambiguous += 1
        if ambiguous:
            return "AMBIGUOUS_RELATION", False
        if managed:
            # The relation is legacy/non-authoritative; UID and Creator ID remain protected.
            return "ACTIVE_MANAGED_ACCOUNT_RELATION", True
        return "LEGACY_RELATION_ONLY", True

    def _verify_after_delete(
        self,
        *,
        account_before: dict[str, Any],
        local_before: dict[str, Any],
        managed_before: int,
        deleted_ids: set[str],
    ) -> dict[str, Any]:
        client = self._client_provider()
        try:
            client.authenticate()
            creators = client.list_records(client.creator_table_id)
            accounts = client.list_records(client.account_table_id)
            local = self._repository.getCreatorAccountIdentityRows()
        except FeishuClientError as exc:
            return {"status": "failed", "blocked_reason": exc.code}
        creator_index, creator_conflicts, unmanaged = FeishuSyncService._remote_index(
            creators, CREATOR_ID_FIELD, "creator"
        )
        remaining_deleted_ids = deleted_ids & {
            self._text(record.get("record_id")) for record in creators
        }
        local_after = self._local_snapshot(
            [dict(row) for row in local.get("creators", [])],
            [dict(row) for row in local.get("accounts", [])],
        )
        account_after = self._account_snapshot(accounts)
        reason = ""
        if remaining_deleted_ids or unmanaged or creator_conflicts:
            reason = "POST_DELETE_CREATOR_VERIFICATION_FAILED"
        elif len(creators) != managed_before or len(creator_index) != managed_before:
            reason = "POST_DELETE_CREATOR_COUNT_MISMATCH"
        elif account_after != account_before:
            reason = "UNEXPECTED_ACCOUNT_SIDE_EFFECT"
        elif local_after != local_before:
            reason = "UNEXPECTED_LOCAL_INVENTORY_CHANGE"
        return {
            "status": "failed" if reason else "success",
            "blocked_reason": reason,
            "remote_creator_total": len(creators),
            "managed_remote_creators": len(creator_index),
            "unmanaged_remote_creators": len(unmanaged),
            "remote_account_total": len(accounts),
            "account_authoritative_fields_unchanged": account_after == account_before,
            "local_inventory_unchanged": local_after == local_before,
        }

    @staticmethod
    def _account_snapshot(records: list[dict[str, Any]]) -> dict[str, Any]:
        result = {}
        for record in records:
            record_id = str(record.get("record_id") or "").strip()
            fields = deepcopy(dict(record.get("fields") or {}))
            fields.pop(LEGACY_CREATOR_RELATION_FIELD, None)
            result[record_id] = fields
        return result

    @staticmethod
    def _local_snapshot(
        creators: list[dict[str, Any]], accounts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "creator_ids": sorted(str(row.get("creator_id") or "").strip() for row in creators),
            "account_uids": sorted(str(row.get("account_uid") or "").strip() for row in accounts),
        }

    @staticmethod
    def _assert_creator_only_delete(client: FeishuClient) -> None:
        if not client.creator_table_id or client.creator_table_id == client.account_table_id:
            raise RuntimeError("FEISHU_CREATOR_DELETE_SCOPE_VIOLATION")

    @classmethod
    def _public_plan(cls, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": cls.MODE,
            "status": plan["status"],
            "blocked_reason": plan.get("blocked_reason", ""),
            "summary": dict(plan.get("summary") or {}),
            "targets": [dict(item) for item in plan.get("targets") or []],
            "gates": dict(plan.get("gates") or {}),
            "error_codes": list(plan.get("error_codes") or []),
            "missing_fields": list(plan.get("missing_fields") or []),
        }

    @classmethod
    def _blocked(cls, reason: str, **details: Any) -> dict[str, Any]:
        return {
            "mode": cls.MODE,
            "status": "blocked",
            "blocked_reason": reason,
            "summary": {},
            "targets": [],
            "gates": {},
            "error_codes": [],
            "missing_fields": [],
            **details,
        }

    @staticmethod
    def _stop(result: dict[str, Any], reason: str) -> dict[str, Any]:
        result["status"] = "partial" if result.get("succeeded") else "blocked"
        result["blocked_reason"] = reason
        return result

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()
