from __future__ import annotations

"""Exact, account-only identity backfill for existing Feishu records."""

from collections import Counter
from typing import Any, Callable, Protocol

from feishu_client import FeishuClient, FeishuClientError
from services.feishu_sync_service import ACCOUNT_CREATOR_ID_FIELD, ACCOUNT_UID_FIELD


class AccountIdentitySource(Protocol):
    def getCreatorAccountIdentityRows(self) -> dict[str, list[dict[str, Any]]]: ...


class AccountIdentityBackfillService:
    """Claim existing Account rows without touching business data or Creator rows."""

    MODE = "account_identity_backfill"
    ALLOWED_WRITE_FIELDS = frozenset({ACCOUNT_UID_FIELD, ACCOUNT_CREATOR_ID_FIELD})

    def __init__(
        self,
        repository: AccountIdentitySource,
        client_provider: Callable[[], FeishuClient],
    ) -> None:
        self._repository = repository
        self._client_provider = client_provider

    def dry_run(self) -> dict[str, Any]:
        plan = self._build_plan()
        return self._public_plan(plan, writable=False)

    def execute(self, *, confirm: object) -> dict[str, Any]:
        if confirm is not True:
            raise ValueError("FEISHU_ACCOUNT_BACKFILL_CONFIRMATION_REQUIRED")

        # Never trust a previous preview. Both inventories and every conflict are
        # evaluated again immediately before the first Account-only write.
        plan = self._build_plan()
        result = self._public_plan(plan, writable=False)
        if plan["status"] == "blocked":
            return result

        candidates = plan["candidates"]
        result.update({
            "attempted": 0,
            "succeeded": 0,
            "failed": 0,
            "remaining": len(candidates),
            "error_codes": [],
            "batches": [],
            "creator_create_count": 0,
            "creator_update_count": 0,
            "creator_delete_count": 0,
            "account_create_count": 0,
            "account_delete_count": 0,
        })
        client = plan["client"]
        batch_size = max(1, int(client.batch_size))
        for offset in range(0, len(candidates), batch_size):
            batch = candidates[offset:offset + batch_size]
            updates = [
                {
                    "record_id": item["remote_record_id"],
                    "fields": {
                        ACCOUNT_UID_FIELD: item["account_uid"],
                        ACCOUNT_CREATOR_ID_FIELD: item["creator_id"],
                    },
                }
                for item in batch
            ]
            if any(result[key] for key in (
                "creator_create_count", "creator_update_count", "creator_delete_count"
            )):
                raise RuntimeError("CREATOR_TABLE_WRITE_SCOPE_VIOLATION")
            self._assert_account_only_updates(client, updates)
            result["attempted"] += len(batch)
            batch_result = {
                "batch": (offset // batch_size) + 1,
                "attempted": len(batch),
                "succeeded": 0,
                "failed": 0,
                "status": "pending",
            }
            try:
                updated = client.batch_update(client.account_table_id, updates)
                if len(updated) != len(batch):
                    raise FeishuClientError(
                        "REMOTE_ERROR", "飞书账号身份认领结果数量不一致。"
                    )
            except FeishuClientError as exc:
                result["failed"] = len(batch)
                result["remaining"] = len(candidates) - result["succeeded"]
                result["error_codes"] = [exc.code]
                batch_result.update({
                    "failed": len(batch), "status": "failed", "error_code": exc.code,
                })
                result["batches"].append(batch_result)
                result["status"] = "partial" if result["succeeded"] else "failed"
                return result
            result["succeeded"] += len(batch)
            result["remaining"] = len(candidates) - result["succeeded"]
            batch_result.update({"succeeded": len(batch), "status": "success"})
            result["batches"].append(batch_result)

        result["status"] = "success"
        result["writable"] = False
        return result

    def _build_plan(self) -> dict[str, Any]:
        client = self._client_provider()
        try:
            client.authenticate()
            schema = self._field_index(client.list_fields(client.account_table_id))
            missing = [field for field in self.ALLOWED_WRITE_FIELDS if field not in schema]
            if missing:
                return self._blocked_plan(
                    "FEISHU_ACCOUNT_SCHEMA_INVALID",
                    missing_fields=sorted(missing),
                )
            incompatible = [
                field for field in self.ALLOWED_WRITE_FIELDS
                if int(schema[field].get("type") or 0) != 1
            ]
            if incompatible:
                return self._blocked_plan(
                    "FEISHU_ACCOUNT_SCHEMA_INVALID",
                    incompatible_fields=sorted(incompatible),
                )
            local_source = self._repository.getCreatorAccountIdentityRows()
            remote_records = client.list_records(client.account_table_id)
        except FeishuClientError as exc:
            return self._blocked_plan(exc.code, error_codes=[exc.code])

        creator_counts = Counter(
            self._text(row.get("creator_id"))
            for row in local_source.get("creators", [])
            if self._text(row.get("creator_id"))
        )
        local_rows = [dict(row) for row in local_source.get("accounts", [])]
        local_counts = Counter(self._text(row.get("account_uid")) for row in local_rows)
        local_by_uid = {
            self._text(row.get("account_uid")): row
            for row in local_rows
            if self._text(row.get("account_uid"))
            and local_counts[self._text(row.get("account_uid"))] == 1
        }

        remote_rows = [
            {
                "remote_record_id": self._text(record.get("record_id")),
                "fields": dict(record.get("fields") or {}),
            }
            for record in remote_records
        ]
        remote_counts = Counter(
            self._field_text(row["fields"].get(ACCOUNT_UID_FIELD))
            for row in remote_rows
            if self._field_text(row["fields"].get(ACCOUNT_UID_FIELD))
        )

        candidates: list[dict[str, str]] = []
        blocked: list[dict[str, str]] = []
        unchanged = 0
        counts = Counter()
        for remote in remote_rows:
            record_id = remote["remote_record_id"]
            fields = remote["fields"]
            account_uid = self._field_text(fields.get(ACCOUNT_UID_FIELD))
            platform = self._field_text(fields.get("平台"))
            profile_url = self._field_text(fields.get("主页链接"))
            base = {
                "remote_record_id": record_id,
                "account_uid": account_uid,
                "creator_id": "",
                "platform": platform,
                "profile_url": profile_url,
            }
            if not record_id:
                counts["blocked"] += 1
                blocked.append({**base, "reason": "MISSING_REMOTE_RECORD_ID"})
                continue
            if not account_uid:
                counts["missing_uid"] += 1
                counts["blocked"] += 1
                blocked.append({**base, "reason": "MISSING_ACCOUNT_UID"})
                continue
            if remote_counts[account_uid] != 1:
                counts["duplicate_remote_uid"] += 1
                counts["blocked"] += 1
                blocked.append({**base, "reason": "DUPLICATE_REMOTE_ACCOUNT_UID"})
                continue
            if local_counts[account_uid] > 1:
                counts["duplicate_local_uid"] += 1
                counts["blocked"] += 1
                blocked.append({**base, "reason": "DUPLICATE_LOCAL_ACCOUNT_UID"})
                continue
            local = local_by_uid.get(account_uid)
            if local is None:
                counts["unmatched"] += 1
                counts["blocked"] += 1
                blocked.append({**base, "reason": "UNMATCHED_ACCOUNT_UID"})
                continue
            creator_id = self._text(local.get("creator_id"))
            base["creator_id"] = creator_id
            if not creator_id or creator_counts[creator_id] != 1:
                counts["blocked"] += 1
                blocked.append({**base, "reason": "INVALID_LOCAL_CREATOR_ID"})
                continue
            remote_creator_id = self._field_text(fields.get(ACCOUNT_CREATOR_ID_FIELD))
            if remote_creator_id and remote_creator_id != creator_id:
                counts["conflict"] += 1
                counts["blocked"] += 1
                blocked.append({
                    **base,
                    "remote_creator_id": remote_creator_id,
                    "local_creator_id": creator_id,
                    "reason": "CREATOR_ID_CONFLICT",
                })
                continue
            if remote_creator_id == creator_id:
                unchanged += 1
                continue
            candidates.append(base)

        candidates.sort(key=lambda item: (item["account_uid"], item["remote_record_id"]))
        blocked.sort(key=lambda item: (
            item.get("reason", ""), item.get("account_uid", ""), item.get("remote_record_id", "")
        ))
        summary = {
            "remote_accounts": len(remote_rows),
            "local_accounts": len(local_rows),
            "eligible": len(candidates),
            "unchanged": unchanged,
            "blocked": counts["blocked"],
            "unmatched": counts["unmatched"],
            "missing_uid": counts["missing_uid"],
            "duplicate_remote_uid": counts["duplicate_remote_uid"],
            "duplicate_local_uid": counts["duplicate_local_uid"],
            "conflicts": counts["conflict"],
        }
        status = "blocked" if not candidates and not unchanged and blocked else "success"
        return {
            "mode": self.MODE,
            "status": status,
            "summary": summary,
            "candidates": candidates,
            "blocked": blocked,
            "warnings": ["BLOCKED_ROWS_WILL_NOT_BE_MODIFIED"] if blocked else [],
            "client": client,
        }

    @classmethod
    def _public_plan(cls, plan: dict[str, Any], *, writable: bool) -> dict[str, Any]:
        summary = dict(plan.get("summary") or {})
        return {
            "mode": cls.MODE,
            "status": plan["status"],
            "summary": summary,
            "eligible_count": int(summary.get("eligible") or 0),
            "unchanged_count": int(summary.get("unchanged") or 0),
            "blocked_count": int(summary.get("blocked") or 0),
            "unmatched_count": int(summary.get("unmatched") or 0),
            "missing_uid_count": int(summary.get("missing_uid") or 0),
            "duplicate_uid_count": (
                int(summary.get("duplicate_remote_uid") or 0)
                + int(summary.get("duplicate_local_uid") or 0)
            ),
            "candidates": [dict(item) for item in plan.get("candidates") or []],
            "blocked": [dict(item) for item in plan.get("blocked") or []],
            "warnings": list(plan.get("warnings") or []),
            "blocked_reason": plan.get("blocked_reason", ""),
            "error_codes": list(plan.get("error_codes") or []),
            "missing_fields": list(plan.get("missing_fields") or []),
            "incompatible_fields": list(plan.get("incompatible_fields") or []),
            "writable": writable,
        }

    @classmethod
    def _blocked_plan(cls, reason: str, **details: Any) -> dict[str, Any]:
        return {
            "mode": cls.MODE,
            "status": "blocked",
            "summary": {},
            "candidates": [],
            "blocked": [],
            "warnings": [],
            "blocked_reason": reason,
            **details,
        }

    @classmethod
    def _assert_account_only_updates(
        cls, client: FeishuClient, updates: list[dict[str, Any]]
    ) -> None:
        if client.account_table_id == client.creator_table_id:
            raise RuntimeError("FEISHU_ACCOUNT_AND_CREATOR_TABLE_IDS_MUST_DIFFER")
        for update in updates:
            if not cls._text(update.get("record_id")):
                raise RuntimeError("MISSING_REMOTE_RECORD_ID")
            if set(update.get("fields") or {}) != cls.ALLOWED_WRITE_FIELDS:
                raise RuntimeError("ACCOUNT_IDENTITY_WRITE_SCOPE_VIOLATION")

    @staticmethod
    def _field_index(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("field_name") or item.get("name") or "").strip(): item
            for item in fields
            if str(item.get("field_name") or item.get("name") or "").strip()
        }

    @classmethod
    def _field_text(cls, value: Any) -> str:
        if isinstance(value, dict):
            return cls._text(value.get("text") or value.get("link") or value.get("value"))
        if isinstance(value, list):
            return cls._field_text(value[0]) if len(value) == 1 else ""
        return cls._text(value)

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()
