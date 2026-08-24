from __future__ import annotations

"""Reciprocal-relation identity backfill for legacy Feishu Creator rows."""

from collections import Counter, defaultdict
from typing import Any, Callable, Protocol

from feishu_client import FeishuClient, FeishuClientError
from services.feishu_sync_service import (
    ACCOUNT_CREATOR_ID_FIELD,
    ACCOUNT_UID_FIELD,
    CREATOR_ID_FIELD,
    LEGACY_CREATOR_RELATION_FIELD,
    FeishuSyncService,
)


CREATOR_ACCOUNT_RELATION_FIELD = "社媒账号"


class CreatorIdentitySource(Protocol):
    def getCreatorAccountIdentityRows(self) -> dict[str, list[dict[str, Any]]]: ...


class CreatorIdentityBackfillService:
    """Claim only legacy Creator identity fields using reciprocal Account evidence."""

    MODE = "creator_identity_backfill"
    DETAIL_LIMIT = 50
    ALLOWED_WRITE_FIELDS = frozenset({CREATOR_ID_FIELD})

    def __init__(
        self,
        repository: CreatorIdentitySource,
        client_provider: Callable[[], FeishuClient],
    ) -> None:
        self._repository = repository
        self._client_provider = client_provider

    def dry_run(self) -> dict[str, Any]:
        return self._public_plan(self._build_plan())

    def execute(self, *, confirm: object) -> dict[str, Any]:
        if confirm is not True:
            raise ValueError("FEISHU_CREATOR_BACKFILL_CONFIRMATION_REQUIRED")

        initial = self._build_plan()
        result = self._public_plan(initial)
        if initial["status"] == "blocked":
            return result

        pending = [item["remote_record_id"] for item in initial["candidates"]]
        result.update({
            "attempted": 0,
            "succeeded": 0,
            "failed": 0,
            "remaining": len(pending),
            "error_codes": [],
            "batches": [],
            "creator_create_count": 0,
            "creator_delete_count": 0,
            "creator_business_update_count": 0,
            "account_mutation_count": 0,
            "excel_mutation_count": 0,
        })
        batch_number = 0
        while pending:
            # Re-read both systems before every batch; only candidates still present
            # in this newly built plan may enter the write payload.
            current = self._build_plan()
            if current["status"] == "blocked":
                result["status"] = "partial" if result["succeeded"] else "blocked"
                result["blocked_reason"] = current.get("blocked_reason", "")
                result["remaining"] = len(pending)
                return result
            client = current["client"]
            current_candidates = {
                item["remote_record_id"]: item for item in current["candidates"]
            }
            current_unchanged = set(current["unchanged_record_ids"])
            pending = [record_id for record_id in pending if record_id not in current_unchanged]
            if not pending:
                break
            batch_ids = [
                record_id for record_id in pending if record_id in current_candidates
            ][: max(1, int(client.batch_size))]
            if not batch_ids:
                result["status"] = "partial" if result["succeeded"] else "blocked"
                result["blocked_reason"] = "CREATOR_IDENTITY_EVIDENCE_CHANGED"
                result["remaining"] = len(pending)
                return result

            batch = [current_candidates[record_id] for record_id in batch_ids]
            updates = [
                {
                    "record_id": item["remote_record_id"],
                    "fields": {CREATOR_ID_FIELD: item["creator_id"]},
                }
                for item in batch
            ]
            self._assert_creator_identity_only_updates(client, updates)
            batch_number += 1
            batch_result = {
                "batch": batch_number,
                "attempted": len(batch),
                "succeeded": 0,
                "failed": 0,
                "status": "pending",
            }
            result["attempted"] += len(batch)
            try:
                updated = client.batch_update(client.creator_table_id, updates)
                if len(updated) != len(batch):
                    raise FeishuClientError(
                        "REMOTE_ERROR", "飞书 Creator 身份认领结果数量不一致。"
                    )
            except FeishuClientError as exc:
                result["failed"] = len(batch)
                result["remaining"] = len(pending)
                result["error_codes"] = [exc.code]
                batch_result.update({
                    "failed": len(batch), "status": "failed", "error_code": exc.code,
                })
                result["batches"].append(batch_result)
                result["status"] = "partial" if result["succeeded"] else "failed"
                return result

            result["succeeded"] += len(batch)
            pending = [record_id for record_id in pending if record_id not in batch_ids]
            result["remaining"] = len(pending)
            batch_result.update({"succeeded": len(batch), "status": "success"})
            result["batches"].append(batch_result)

        result["status"] = "success"
        return result

    def _build_plan(self) -> dict[str, Any]:
        client = self._client_provider()
        try:
            client.authenticate()
            creator_schema = self._field_index(client.list_fields(client.creator_table_id))
            account_schema = self._field_index(client.list_fields(client.account_table_id))
            required_creator = {CREATOR_ID_FIELD, CREATOR_ACCOUNT_RELATION_FIELD}
            required_account = {
                ACCOUNT_UID_FIELD, ACCOUNT_CREATOR_ID_FIELD, LEGACY_CREATOR_RELATION_FIELD,
            }
            missing = [
                {"table": "creator", "field": field}
                for field in sorted(required_creator - set(creator_schema))
            ] + [
                {"table": "account", "field": field}
                for field in sorted(required_account - set(account_schema))
            ]
            if missing:
                return self._blocked_plan("FEISHU_CREATOR_BACKFILL_SCHEMA_INVALID", missing_fields=missing)
            if int(creator_schema[CREATOR_ID_FIELD].get("type") or 0) != 1:
                return self._blocked_plan(
                    "FEISHU_CREATOR_BACKFILL_SCHEMA_INVALID",
                    incompatible_fields=[{"table": "creator", "field": CREATOR_ID_FIELD}],
                )
            local = self._repository.getCreatorAccountIdentityRows()
            remote_creators = client.list_records(client.creator_table_id)
            remote_accounts = client.list_records(client.account_table_id)
        except FeishuClientError as exc:
            return self._blocked_plan(exc.code, error_codes=[exc.code])

        creator_rows = [dict(row) for row in local.get("creators", [])]
        account_rows = [dict(row) for row in local.get("accounts", [])]
        creator_counts = Counter(self._text(row.get("creator_id")) for row in creator_rows)
        valid_creator_ids = {
            identity for identity, count in creator_counts.items() if identity and count == 1
        }
        local_uid_counts = Counter(self._text(row.get("account_uid")) for row in account_rows)
        local_by_uid = {
            self._text(row.get("account_uid")): row
            for row in account_rows
            if self._text(row.get("account_uid"))
            and local_uid_counts[self._text(row.get("account_uid"))] == 1
        }

        remote_account_rows = [self._remote_row(record) for record in remote_accounts]
        remote_uid_counts = Counter(
            self._field_text(row["fields"].get(ACCOUNT_UID_FIELD))
            for row in remote_account_rows
            if self._field_text(row["fields"].get(ACCOUNT_UID_FIELD))
        )
        verified_accounts: dict[str, dict[str, Any]] = {}
        for remote in remote_account_rows:
            record_id = remote["remote_record_id"]
            uid = self._field_text(remote["fields"].get(ACCOUNT_UID_FIELD))
            local_account = local_by_uid.get(uid)
            if not record_id or not uid or remote_uid_counts[uid] != 1 or local_account is None:
                continue
            local_creator_id = self._text(local_account.get("creator_id"))
            remote_creator_id = self._field_text(
                remote["fields"].get(ACCOUNT_CREATOR_ID_FIELD)
            )
            if (
                local_creator_id not in valid_creator_ids
                or remote_creator_id != local_creator_id
            ):
                continue
            verified_accounts[record_id] = {
                "remote_record_id": record_id,
                "account_uid": uid,
                "creator_id": local_creator_id,
                "platform": self._field_text(remote["fields"].get("平台")),
                "creator_relations": FeishuSyncService._relation_ids(
                    remote["fields"].get(LEGACY_CREATOR_RELATION_FIELD)
                ),
            }

        forward_by_creator: dict[str, set[str]] = defaultdict(set)
        for account_id, account in verified_accounts.items():
            for creator_record_id in account["creator_relations"]:
                forward_by_creator[creator_record_id].add(account_id)

        remote_creator_rows = [self._remote_row(record) for record in remote_creators]
        remote_identity_counts = Counter(
            self._field_text(row["fields"].get(CREATOR_ID_FIELD))
            for row in remote_creator_rows
            if self._field_text(row["fields"].get(CREATOR_ID_FIELD))
        )
        tentative: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        unchanged_record_ids: list[str] = []
        counts = Counter()
        for remote in remote_creator_rows:
            record_id = remote["remote_record_id"]
            fields = remote["fields"]
            display_name = self._field_text(fields.get("达人名称"))
            current_id = self._field_text(fields.get(CREATOR_ID_FIELD))
            base = {"remote_record_id": record_id, "creator_name": display_name}
            if not record_id:
                counts["blocked"] += 1
                blocked.append({**base, "reason": "MISSING_REMOTE_RECORD_ID"})
                continue
            forward_ids = set(forward_by_creator.get(record_id, set()))
            reverse_ids = set(FeishuSyncService._relation_ids(
                fields.get(CREATOR_ACCOUNT_RELATION_FIELD)
            ))
            reverse_verified = reverse_ids & set(verified_accounts)
            evidence_ids = forward_ids | reverse_verified
            creator_ids = {
                verified_accounts[account_id]["creator_id"] for account_id in evidence_ids
            }
            if current_id:
                evidence_conflict = bool(creator_ids and creator_ids != {current_id})
                if (
                    current_id in valid_creator_ids
                    and remote_identity_counts[current_id] == 1
                    and not evidence_conflict
                ):
                    counts["already_correct"] += 1
                    unchanged_record_ids.append(record_id)
                else:
                    counts["conflicts"] += 1
                    counts["blocked"] += 1
                    blocked.append({**base, "remote_creator_id": current_id, "reason": "CREATOR_ID_CONFLICT"})
                continue
            evidence = [
                {
                    "remote_account_record_id": account_id,
                    "account_uid": verified_accounts[account_id]["account_uid"],
                    "platform": verified_accounts[account_id]["platform"],
                }
                for account_id in sorted(evidence_ids)
            ]
            candidate = {**base, "creator_id": next(iter(creator_ids), ""), "accounts": evidence}
            if not forward_ids and not reverse_ids:
                counts["unmatched"] += 1
                counts["blocked"] += 1
                blocked.append({**candidate, "reason": "NO_RECIPROCAL_ACCOUNT_EVIDENCE"})
            elif reverse_ids - set(verified_accounts):
                counts["tier_b_manual_review"] += 1
                counts["blocked"] += 1
                blocked.append({**candidate, "reason": "UNVERIFIED_REVERSE_ACCOUNT_RELATION"})
            elif not forward_ids:
                counts["tier_b_manual_review"] += 1
                counts["blocked"] += 1
                blocked.append({**candidate, "reason": "MISSING_FORWARD_RELATION"})
            elif not reverse_verified:
                counts["tier_b_manual_review"] += 1
                counts["blocked"] += 1
                blocked.append({**candidate, "reason": "MISSING_REVERSE_RELATION"})
            elif forward_ids != reverse_verified:
                counts["ambiguous"] += 1
                counts["blocked"] += 1
                blocked.append({**candidate, "reason": "RECIPROCAL_RELATION_DISAGREEMENT"})
            elif len(creator_ids) != 1:
                counts["ambiguous"] += 1
                counts["blocked"] += 1
                blocked.append({**candidate, "reason": "MULTIPLE_LOCAL_CREATOR_IDS"})
            else:
                tentative.append(candidate)

        by_creator_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in tentative:
            by_creator_id[item["creator_id"]].append(item)
        candidates: list[dict[str, Any]] = []
        for creator_id, items in by_creator_id.items():
            if len(items) == 1:
                candidates.append(items[0])
                continue
            counts["ambiguous"] += len(items)
            counts["blocked"] += len(items)
            blocked.extend({**item, "reason": "LOCAL_CREATOR_MULTIPLE_REMOTE_CREATORS"} for item in items)

        candidates.sort(key=lambda item: (item["creator_id"], item["remote_record_id"]))
        blocked.sort(key=lambda item: (
            item.get("reason", ""), item.get("creator_id", ""), item.get("remote_record_id", "")
        ))
        summary = {
            "remote_creators": len(remote_creator_rows),
            "verified_accounts": len(verified_accounts),
            "tier_a_eligible": len(candidates),
            "already_correct": counts["already_correct"],
            "tier_b_manual_review": counts["tier_b_manual_review"],
            "ambiguous": counts["ambiguous"],
            "unmatched": counts["unmatched"],
            "conflicts": counts["conflicts"],
            "blocked": counts["blocked"],
        }
        return {
            "mode": self.MODE,
            "status": "success",
            "summary": summary,
            "candidates": candidates,
            "blocked": blocked,
            "unchanged_record_ids": unchanged_record_ids,
            "warnings": ["TIER_B_AND_BLOCKED_ROWS_WILL_NOT_BE_MODIFIED"] if blocked else [],
            "client": client,
        }

    @classmethod
    def _public_plan(cls, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": cls.MODE,
            "status": plan["status"],
            "summary": dict(plan.get("summary") or {}),
            "candidates": [dict(item) for item in (plan.get("candidates") or [])[:cls.DETAIL_LIMIT]],
            "blocked": [dict(item) for item in (plan.get("blocked") or [])[:cls.DETAIL_LIMIT]],
            "warnings": list(plan.get("warnings") or []),
            "blocked_reason": plan.get("blocked_reason", ""),
            "error_codes": list(plan.get("error_codes") or []),
            "missing_fields": list(plan.get("missing_fields") or []),
            "incompatible_fields": list(plan.get("incompatible_fields") or []),
        }

    @classmethod
    def _blocked_plan(cls, reason: str, **details: Any) -> dict[str, Any]:
        return {
            "mode": cls.MODE,
            "status": "blocked",
            "summary": {},
            "candidates": [],
            "blocked": [],
            "unchanged_record_ids": [],
            "warnings": [],
            "blocked_reason": reason,
            **details,
        }

    @classmethod
    def _assert_creator_identity_only_updates(
        cls, client: FeishuClient, updates: list[dict[str, Any]]
    ) -> None:
        if client.creator_table_id == client.account_table_id:
            raise RuntimeError("FEISHU_ACCOUNT_AND_CREATOR_TABLE_IDS_MUST_DIFFER")
        for update in updates:
            if not cls._text(update.get("record_id")):
                raise RuntimeError("MISSING_REMOTE_RECORD_ID")
            if set(update.get("fields") or {}) != cls.ALLOWED_WRITE_FIELDS:
                raise RuntimeError("CREATOR_IDENTITY_WRITE_SCOPE_VIOLATION")

    @staticmethod
    def _remote_row(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "remote_record_id": CreatorIdentityBackfillService._text(record.get("record_id")),
            "fields": dict(record.get("fields") or {}),
        }

    @staticmethod
    def _field_index(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("field_name") or item.get("name") or "").strip(): item
            for item in fields
            if str(item.get("field_name") or item.get("name") or "").strip()
        }

    @staticmethod
    def _field_text(value: Any) -> str:
        return FeishuSyncService._field_text(value)

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()
