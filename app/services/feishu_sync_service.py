from __future__ import annotations

"""Manual, one-way KOLConnect to Feishu synchronization foundation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from feishu_client import FeishuClient, FeishuClientError


CREATOR_ID_FIELD = "KOLConnect Creator ID"
ACCOUNT_UID_FIELD = "账号唯一ID"
ACCOUNT_CREATOR_ID_FIELD = "KOLConnect Creator ID"
LEGACY_CREATOR_RELATION_FIELD = "达人"


class CreatorInventorySource(Protocol):
    def getCreatorInventoryRows(self) -> dict[str, list[dict[str, Any]]]: ...


@dataclass(frozen=True)
class FieldSpec:
    key: str
    remote_name: str
    kind: str
    compatible_types: frozenset[int]
    required: bool = True


CREATOR_FIELDS = (
    FieldSpec("creator_id", CREATOR_ID_FIELD, "text", frozenset({1})),
    FieldSpec("name", "达人名称", "text", frozenset({1})),
    FieldSpec("country", "国家/地区", "text", frozenset({1, 3})),
    FieldSpec("language", "语言", "text", frozenset({1, 3})),
    FieldSpec("content_category", "内容类型", "text", frozenset({1, 3})),
    FieldSpec("archived", "已归档", "boolean", frozenset({1, 3, 7})),
    FieldSpec("insight_level", "Insight等级", "text", frozenset({1, 3}), False),
    FieldSpec("last_analysis_at", "最后分析时间", "datetime", frozenset({1, 5}), False),
    FieldSpec("last_synced_at", "最近同步时间", "datetime", frozenset({1, 5})),
)
ACCOUNT_FIELDS = (
    FieldSpec("account_uid", ACCOUNT_UID_FIELD, "text", frozenset({1})),
    FieldSpec("creator_id", ACCOUNT_CREATOR_ID_FIELD, "text", frozenset({1})),
    FieldSpec("platform", "平台", "text", frozenset({1, 3})),
    FieldSpec("profile_url", "主页链接", "url", frozenset({1, 15})),
    FieldSpec("followers", "粉丝数", "number", frozenset({1, 2})),
    FieldSpec("average_views", "平均播放量", "number", frozenset({1, 2}), False),
    FieldSpec("last_analysis_at", "最后分析时间", "datetime", frozenset({1, 5}), False),
    FieldSpec("last_synced_at", "最近同步时间", "datetime", frozenset({1, 5})),
)


class FeishuSyncService:
    """Build and execute explicit, privacy-safe manual synchronization plans."""

    DETAIL_LIMIT = 50

    def __init__(
        self,
        repository: CreatorInventorySource,
        client_provider: Callable[[], FeishuClient],
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._client_provider = client_provider
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def validate_connection(self) -> dict[str, Any]:
        started_at = self._now()
        result = self._validate_client(self._client_provider(), started_at)
        result.pop("_creator_schema", None)
        result.pop("_account_schema", None)
        return result

    def _validate_client(
        self, client: FeishuClient, started_at: str
    ) -> dict[str, Any]:
        try:
            client.authenticate()
        except FeishuClientError as exc:
            return {
                "status": "failed",
                "started_at": started_at,
                "completed_at": self._now(),
                "connection_ok": False,
                "creator_table_ok": False,
                "account_table_ok": False,
                "missing_fields": [],
                "incompatible_fields": [],
                "warnings": [],
                "error_codes": [exc.code],
            }

        creator_fields, creator_error = self._safe_fields(client, client.creator_table_id)
        account_fields, account_error = self._safe_fields(client, client.account_table_id)
        missing, incompatible, warnings = self._validate_schema(
            creator_fields or {}, account_fields or {}
        )
        error_codes = [
            error.code for error in (creator_error, account_error) if error is not None
        ]
        if not error_codes:
            warnings.append("WRITE_PERMISSION_NOT_TESTED_WITHOUT_MUTATION")
        ready = not error_codes and not missing and not incompatible
        blocked_reason = "FEISHU_SCHEMA_INVALID" if missing or incompatible else ""
        return {
            "status": "success" if ready else "blocked",
            "blocked_reason": blocked_reason,
            "started_at": started_at,
            "completed_at": self._now(),
            "connection_ok": True,
            "creator_table_ok": creator_error is None,
            "account_table_ok": account_error is None,
            "missing_fields": missing,
            "incompatible_fields": incompatible,
            "warnings": sorted(set(warnings)),
            "error_codes": sorted(set(error_codes)),
            "_creator_schema": creator_fields or {},
            "_account_schema": account_fields or {},
        }

    def dry_run(self) -> dict[str, Any]:
        return self._public_plan(self._build_plan())

    def full_sync(self, *, confirm: object) -> dict[str, Any]:
        if confirm is not True:
            raise ValueError("FEISHU_SYNC_CONFIRMATION_REQUIRED")
        plan = self._build_plan()
        if plan["blocked_reason"]:
            result = self._public_plan(plan)
            result["status"] = "blocked"
            return result

        client: FeishuClient = plan["client"]
        synced_at = self._now()
        result = {
            "status": "success",
            "started_at": plan["started_at"],
            "completed_at": "",
            "creator_created": 0,
            "creator_updated": 0,
            "creator_unchanged": plan["creator_unchanged_count"],
            "creator_failed": 0,
            "account_created": 0,
            "account_updated": 0,
            "account_unchanged": plan["account_unchanged_count"],
            "account_failed": 0,
            "conflicts": list(plan["conflicts"]),
            "warnings": list(plan["warnings"]),
            "error_codes": [],
            "failed_entities": [],
        }

        creator_record_ids = dict(plan["remote_creator_record_ids"])
        self._execute_creates(
            client,
            client.creator_table_id,
            plan["creator_creates"],
            CREATOR_FIELDS,
            synced_at,
            result,
            entity="creator",
            record_id_index=creator_record_ids,
        )
        self._execute_updates(
            client,
            client.creator_table_id,
            plan["creator_updates"],
            CREATOR_FIELDS,
            synced_at,
            result,
            entity="creator",
        )
        self._execute_creates(
            client,
            client.account_table_id,
            plan["account_creates"],
            ACCOUNT_FIELDS,
            synced_at,
            result,
            entity="account",
        )
        self._execute_updates(
            client,
            client.account_table_id,
            plan["account_updates"],
            ACCOUNT_FIELDS,
            synced_at,
            result,
            entity="account",
        )

        failed = result["creator_failed"] + result["account_failed"]
        changed = (
            result["creator_created"] + result["creator_updated"]
            + result["account_created"] + result["account_updated"]
        )
        if failed:
            result["status"] = "partial" if changed else "failed"
        result["error_codes"] = sorted(set(result["error_codes"]))
        result["completed_at"] = self._now()
        return result

    def _build_plan(self) -> dict[str, Any]:
        started_at = self._now()
        client = self._client_provider()
        validation = self._validate_client(client, started_at)
        base = {
            "status": "blocked",
            "started_at": started_at,
            "completed_at": "",
            "local_creator_count": 0,
            "local_active_creator_count": 0,
            "local_archived_creator_count": 0,
            "local_account_count": 0,
            "local_creators_missing_creator_id": 0,
            "local_accounts_missing_account_uid": 0,
            "local_creator_id_duplicate_count": 0,
            "local_account_uid_duplicate_count": 0,
            "remote_creator_count": 0,
            "remote_account_count": 0,
            "creator_create_count": 0,
            "creator_update_count": 0,
            "creator_unchanged_count": 0,
            "creator_conflict_count": 0,
            "account_create_count": 0,
            "account_update_count": 0,
            "account_unchanged_count": 0,
            "account_conflict_count": 0,
            "remote_unmanaged_count": 0,
            "duplicate_identity_count": 0,
            "blocked_reason": "",
            "warnings": list(validation.get("warnings") or []),
            "conflicts": [],
            "error_codes": list(validation.get("error_codes") or []),
            "missing_fields": list(validation.get("missing_fields") or []),
            "incompatible_fields": list(validation.get("incompatible_fields") or []),
        }
        if validation["status"] != "success":
            base["blocked_reason"] = (
                validation.get("blocked_reason")
                or "FEISHU_SCHEMA_OR_CONNECTION_INVALID"
            )
            base["completed_at"] = self._now()
            return base

        try:
            creator_schema = validation["_creator_schema"]
            account_schema = validation["_account_schema"]
            local = self._local_inventory()
            remote = self._remote_inventory(client)
        except FeishuClientError as exc:
            base["blocked_reason"] = exc.code
            base["error_codes"].append(exc.code)
            base["completed_at"] = self._now()
            return base

        base.update({
            "local_creator_count": local["creator_total"],
            "local_active_creator_count": local["active_count"],
            "local_archived_creator_count": local["archived_count"],
            "local_account_count": local["account_total"],
            "local_creators_missing_creator_id": local["missing_creator_ids"],
            "local_accounts_missing_account_uid": local["missing_account_uids"],
            "local_creator_id_duplicate_count": local["duplicate_creator_ids"],
            "local_account_uid_duplicate_count": local["duplicate_account_uids"],
            "remote_creator_count": len(remote["creator_records"]),
            "remote_account_count": len(remote["account_records"]),
        })
        identity_conflicts = local["conflicts"] + remote["conflicts"]
        if identity_conflicts:
            base["conflicts"] = identity_conflicts[: self.DETAIL_LIMIT]
            base["duplicate_identity_count"] = len(identity_conflicts)
            base["creator_conflict_count"] = sum(
                1 for item in identity_conflicts if item["entity_type"] == "creator"
            )
            base["account_conflict_count"] = sum(
                1 for item in identity_conflicts if item["entity_type"] == "account"
            )
            base["blocked_reason"] = "IDENTITY_CONFLICT"
            base["completed_at"] = self._now()
            return base

        legacy_matches, legacy_conflicts = self._legacy_creator_matches(local, remote)
        if legacy_conflicts:
            base["conflicts"] = legacy_conflicts[: self.DETAIL_LIMIT]
            base["creator_conflict_count"] = len(legacy_conflicts)
            base["blocked_reason"] = "AMBIGUOUS_LEGACY_MAPPING"
            base["completed_at"] = self._now()
            return base

        creator_creates: list[dict[str, Any]] = []
        creator_updates: list[dict[str, Any]] = []
        creator_unchanged = 0
        remote_creator_ids = dict(remote["creator_index"])
        for creator_id, canonical in local["creators"].items():
            record = remote["creator_index"].get(creator_id)
            if record is None and creator_id in legacy_matches:
                record = legacy_matches[creator_id]
            item = self._plan_item(
                creator_id, canonical, record, CREATOR_FIELDS, creator_schema
            )
            if item["action"] == "create":
                creator_creates.append(item)
            elif item["action"] == "update":
                creator_updates.append(item)
                remote_creator_ids[creator_id] = item["record_id"]
            else:
                creator_unchanged += 1
                remote_creator_ids[creator_id] = item["record_id"]

        account_creates: list[dict[str, Any]] = []
        account_updates: list[dict[str, Any]] = []
        account_unchanged = 0
        for account_uid, canonical in local["accounts"].items():
            item = self._plan_item(
                account_uid,
                canonical,
                remote["account_index"].get(account_uid),
                ACCOUNT_FIELDS,
                account_schema,
            )
            if item["action"] == "create":
                account_creates.append(item)
            elif item["action"] == "update":
                account_updates.append(item)
            else:
                account_unchanged += 1

        unmanaged_creator_ids = {
            item["record_id"] for item in remote["unmanaged_creators"]
        } - {item["record_id"] for item in legacy_matches.values()}
        base.update({
            "status": "success",
            "creator_create_count": len(creator_creates),
            "creator_update_count": len(creator_updates),
            "creator_unchanged_count": creator_unchanged,
            "account_create_count": len(account_creates),
            "account_update_count": len(account_updates),
            "account_unchanged_count": account_unchanged,
            "remote_unmanaged_count": len(unmanaged_creator_ids) + len(remote["unmanaged_accounts"]),
            "blocked_reason": "",
            "warnings": sorted(set(base["warnings"] + (["REMOTE_UNMANAGED_RECORDS_PRESENT"] if unmanaged_creator_ids or remote["unmanaged_accounts"] else []))),
            "client": client,
            "creator_schema": creator_schema,
            "account_schema": account_schema,
            "creator_creates": creator_creates,
            "creator_updates": creator_updates,
            "account_creates": account_creates,
            "account_updates": account_updates,
            "remote_creator_record_ids": remote_creator_ids,
            "completed_at": self._now(),
        })
        return base

    def _local_inventory(self) -> dict[str, Any]:
        source = self._repository.getCreatorInventoryRows()
        creator_rows = [dict(row) for row in source.get("creators", [])]
        account_rows = [dict(row) for row in source.get("accounts", [])]
        insight_by_creator = {
            self._text(row.get("creator_id")): row
            for row in source.get("insights", [])
            if self._text(row.get("creator_id"))
        }
        latest_snapshot: dict[str, dict[str, Any]] = {}
        latest_snapshot_by_account: dict[str, dict[str, Any]] = {}
        for row in source.get("snapshots", []):
            creator_id = self._text(row.get("creator_id"))
            if not creator_id:
                continue
            current = latest_snapshot.get(creator_id)
            if current is None or self._text(row.get("captured_at")) > self._text(current.get("captured_at")):
                latest_snapshot[creator_id] = row
            account_uid = self._text(row.get("account_uid"))
            account_current = latest_snapshot_by_account.get(account_uid)
            if account_uid and (
                account_current is None
                or self._text(row.get("captured_at"))
                > self._text(account_current.get("captured_at"))
            ):
                latest_snapshot_by_account[account_uid] = row

        conflicts: list[dict[str, str]] = []
        missing_creator_ids = 0
        missing_account_uids = 0
        creators: dict[str, dict[str, Any]] = {}
        creator_counts: dict[str, int] = {}
        for row in creator_rows:
            creator_id = self._text(row.get("creator_id"))
            if not creator_id:
                missing_creator_ids += 1
                conflicts.append({"entity_type": "creator", "identity": "", "reason": "missing_creator_id"})
                continue
            creator_counts[creator_id] = creator_counts.get(creator_id, 0) + 1
            snapshot = latest_snapshot.get(creator_id, {})
            insight = insight_by_creator.get(creator_id, {})
            creators[creator_id] = {
                "creator_id": creator_id,
                "name": self._text(row.get("name")),
                "country": self._text(row.get("country")),
                "language": self._text(row.get("language")),
                "content_category": self._text(row.get("content_category")),
                "archived": bool(self._text(row.get("archived_at"))),
                "insight_level": self._text(snapshot.get("insight_level") or row.get("insight_level")),
                "last_analysis_at": self._text(snapshot.get("captured_at") or row.get("updated_at") or row.get("created_at")),
                "average_views": snapshot.get("average_views", insight.get("average_views", "")),
            }
        for identity, count in creator_counts.items():
            if count > 1:
                conflicts.append({"entity_type": "creator", "identity": identity, "reason": "duplicate_creator_id"})

        accounts: dict[str, dict[str, Any]] = {}
        account_counts: dict[str, int] = {}
        for row in account_rows:
            account_uid = self._text(row.get("account_uid"))
            if not account_uid:
                missing_account_uids += 1
                conflicts.append({"entity_type": "account", "identity": "", "reason": "missing_account_uid"})
                continue
            account_counts[account_uid] = account_counts.get(account_uid, 0) + 1
            creator_id = self._text(row.get("creator_id"))
            if not creator_id or creator_id not in creators:
                conflicts.append({"entity_type": "account", "identity": account_uid, "reason": "missing_account_creator_id"})
                continue
            account_snapshot = latest_snapshot_by_account.get(account_uid, {})
            accounts[account_uid] = {
                "account_uid": account_uid,
                "creator_id": creator_id,
                "platform": self._text(row.get("platform")),
                "profile_url": self._text(row.get("profile_url")),
                "followers": row.get("followers", ""),
                "average_views": account_snapshot.get("average_views", ""),
                "last_analysis_at": self._text(account_snapshot.get("captured_at")),
            }
        for identity, count in account_counts.items():
            if count > 1:
                conflicts.append({"entity_type": "account", "identity": identity, "reason": "duplicate_account_uid"})
        return {
            "creators": creators,
            "accounts": accounts,
            "creator_total": len(creator_rows),
            "account_total": len(account_rows),
            "active_count": sum(not item["archived"] for item in creators.values()),
            "archived_count": sum(item["archived"] for item in creators.values()),
            "missing_creator_ids": missing_creator_ids,
            "missing_account_uids": missing_account_uids,
            "duplicate_creator_ids": sum(count > 1 for count in creator_counts.values()),
            "duplicate_account_uids": sum(count > 1 for count in account_counts.values()),
            "conflicts": conflicts,
        }

    def _remote_inventory(self, client: FeishuClient) -> dict[str, Any]:
        creator_records = client.list_records(client.creator_table_id)
        account_records = client.list_records(client.account_table_id)
        creator_index, creator_duplicates, unmanaged_creators = self._remote_index(
            creator_records, CREATOR_ID_FIELD, "creator"
        )
        account_index, account_duplicates, unmanaged_accounts = self._remote_index(
            account_records, ACCOUNT_UID_FIELD, "account"
        )
        return {
            "creator_records": creator_records,
            "account_records": account_records,
            "creator_index": creator_index,
            "account_index": account_index,
            "unmanaged_creators": unmanaged_creators,
            "unmanaged_accounts": unmanaged_accounts,
            "conflicts": creator_duplicates + account_duplicates,
        }

    def _legacy_creator_matches(
        self, local: dict[str, Any], remote: dict[str, Any]
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
        linked: dict[str, list[str | None]] = {}
        for account in remote["account_records"]:
            fields = account.get("fields") or {}
            account_uid = self._field_text(fields.get(ACCOUNT_UID_FIELD))
            local_creator_id = (local["accounts"].get(account_uid) or {}).get("creator_id")
            for record_id in self._legacy_relation_ids(
                fields.get(LEGACY_CREATOR_RELATION_FIELD)
            ):
                linked.setdefault(record_id, []).append(local_creator_id or None)

        matches: dict[str, dict[str, Any]] = {}
        conflicts: list[dict[str, str]] = []
        managed_ids = set(remote["creator_index"])
        for record in remote["unmanaged_creators"]:
            record_id = record["record_id"]
            candidates = linked.get(record_id, [])
            known = {item for item in candidates if item}
            if not candidates:
                continue
            if len(known) != 1 or any(item is None for item in candidates):
                conflicts.append({"entity_type": "creator", "identity": record_id, "reason": "ambiguous_legacy_mapping"})
                continue
            creator_id = next(iter(known))
            if creator_id in managed_ids or creator_id in matches:
                conflicts.append({"entity_type": "creator", "identity": creator_id, "reason": "duplicate_legacy_mapping"})
                continue
            matches[creator_id] = record
        return matches, conflicts

    def _plan_item(
        self,
        identity: str,
        canonical: dict[str, Any],
        remote: dict[str, Any] | None,
        specs: tuple[FieldSpec, ...],
        schema: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        desired = self._encode_payload(canonical, specs, schema, include_sync=False)
        if remote is None:
            return {"identity": identity, "action": "create", "canonical": canonical, "payload": desired, "schema": schema}
        remote_fields = remote.get("fields") or {}
        changed = any(
            not self._equivalent(remote_fields.get(name), value, schema[name], self._spec_by_name(specs, name))
            for name, value in desired.items()
        )
        return {
            "identity": identity,
            "record_id": self._text(remote.get("record_id")),
            "action": "update" if changed else "unchanged",
            "canonical": canonical,
            "payload": desired,
            "schema": schema,
        }

    def _execute_creates(
        self,
        client: FeishuClient,
        table_id: str,
        items: list[dict[str, Any]],
        specs: tuple[FieldSpec, ...],
        synced_at: str,
        result: dict[str, Any],
        *,
        entity: str,
        record_id_index: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        for batch in self._chunks(items, client.batch_size):
            payloads = [
                self._payload_with_sync(item["payload"], synced_at, specs, item["schema"])
                for item in batch
            ]
            try:
                created = client.batch_create(table_id, payloads)
                if len(created) != len(batch):
                    raise FeishuClientError("REMOTE_ERROR", "飞书创建结果数量不一致。")
                result[f"{entity}_created"] += len(batch)
                if record_id_index is not None:
                    for item, remote in zip(batch, created):
                        record_id_index[item["identity"]] = remote
            except FeishuClientError as exc:
                self._record_batch_failure(result, entity, batch, exc)

    def _execute_updates(
        self,
        client: FeishuClient,
        table_id: str,
        items: list[dict[str, Any]],
        specs: tuple[FieldSpec, ...],
        synced_at: str,
        result: dict[str, Any],
        *,
        entity: str,
    ) -> None:
        for batch in self._chunks(items, client.batch_size):
            updates = [
                {
                    "record_id": item["record_id"],
                    "fields": self._payload_with_sync(
                        item["payload"], synced_at, specs, item["schema"]
                    ),
                }
                for item in batch
            ]
            try:
                client.batch_update(table_id, updates)
                result[f"{entity}_updated"] += len(batch)
            except FeishuClientError as exc:
                self._record_batch_failure(result, entity, batch, exc)

    def _payload_with_sync(
        self,
        payload: dict[str, Any],
        synced_at: str,
        specs: tuple[FieldSpec, ...],
        schema: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        result = dict(payload)
        sync_spec = next(spec for spec in specs if spec.key == "last_synced_at")
        result[sync_spec.remote_name] = self._encode_value(
            synced_at, sync_spec, schema.get(sync_spec.remote_name, {"type": 1})
        )
        return result

    @staticmethod
    def _record_batch_failure(
        result: dict[str, Any], entity: str, batch: list[dict[str, Any]], exc: FeishuClientError
    ) -> None:
        result[f"{entity}_failed"] += len(batch)
        result["error_codes"].append(exc.code)
        remaining = max(0, FeishuSyncService.DETAIL_LIMIT - len(result["failed_entities"]))
        result["failed_entities"].extend(
            {"entity_type": entity, "identity": item["identity"], "error_code": exc.code}
            for item in batch[:remaining]
        )

    def _validate_schema(
        self,
        creator_schema: dict[str, dict[str, Any]],
        account_schema: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[str]]:
        missing: list[dict[str, str]] = []
        incompatible: list[dict[str, Any]] = []
        warnings: list[str] = []
        for table, schema, specs in (
            ("creator", creator_schema, CREATOR_FIELDS),
            ("account", account_schema, ACCOUNT_FIELDS),
        ):
            for spec in specs:
                field = schema.get(spec.remote_name)
                if field is None:
                    if spec.required:
                        missing.append({"table": table, "field": spec.remote_name})
                    else:
                        warnings.append(f"OPTIONAL_FIELD_MISSING:{table}:{spec.remote_name}")
                    continue
                field_type = int(field.get("type") or 0)
                if field_type not in spec.compatible_types:
                    incompatible.append({
                        "table": table,
                        "field": spec.remote_name,
                        "actual_type": field_type,
                    })
        return missing, incompatible, warnings

    def _encode_payload(
        self,
        canonical: dict[str, Any],
        specs: tuple[FieldSpec, ...],
        schema: dict[str, dict[str, Any]],
        *,
        include_sync: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for spec in specs:
            if spec.key == "last_synced_at" and not include_sync:
                continue
            field = schema.get(spec.remote_name)
            if field is None:
                continue
            payload[spec.remote_name] = self._encode_value(
                canonical.get(spec.key, ""), spec, field
            )
        return payload

    def _encode_value(self, value: Any, spec: FieldSpec, field: dict[str, Any]) -> Any:
        field_type = int(field.get("type") or 0)
        if spec.kind == "boolean":
            boolean = bool(value)
            return boolean if field_type == 7 else ("是" if boolean else "否")
        if spec.kind == "url":
            text = self._text(value)
            return {"link": text, "text": text} if field_type == 15 and text else text
        if spec.kind == "number" and field_type == 2:
            return self._number(value)
        if spec.kind == "datetime" and field_type == 5:
            return self._milliseconds(value)
        return self._text(value)

    def _equivalent(
        self,
        remote: Any,
        desired: Any,
        field: dict[str, Any],
        spec: FieldSpec,
    ) -> bool:
        field_type = int(field.get("type") or 0)
        if spec.kind == "url" and field_type == 15:
            remote = self._field_text(remote)
            desired = self._field_text(desired)
        elif spec.kind == "number" and field_type == 2:
            remote = self._number(remote)
            desired = self._number(desired)
        elif spec.kind == "datetime" and field_type == 5:
            try:
                remote = int(remote or 0)
            except (TypeError, ValueError):
                remote = 0
            desired = int(desired or 0)
        elif spec.kind == "boolean" and field_type == 7:
            remote = bool(remote)
            desired = bool(desired)
        else:
            remote = self._field_text(remote)
            desired = self._field_text(desired)
        return remote == desired

    @staticmethod
    def _spec_by_name(specs: tuple[FieldSpec, ...], name: str) -> FieldSpec:
        return next(spec for spec in specs if spec.remote_name == name)

    @staticmethod
    def _field_index(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("field_name") or item.get("name") or "").strip(): item
            for item in fields
            if str(item.get("field_name") or item.get("name") or "").strip()
        }

    @classmethod
    def _remote_index(
        cls, records: list[dict[str, Any]], field_name: str, entity_type: str
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
        indexed: dict[str, dict[str, Any]] = {}
        duplicate_ids: set[str] = set()
        unmanaged: list[dict[str, Any]] = []
        for raw in records:
            record = {"record_id": cls._text(raw.get("record_id")), "fields": dict(raw.get("fields") or {})}
            identity = cls._field_text(record["fields"].get(field_name))
            if not identity:
                unmanaged.append(record)
                continue
            if identity in indexed:
                duplicate_ids.add(identity)
                continue
            indexed[identity] = record
        conflicts = [
            {"entity_type": entity_type, "identity": identity, "reason": f"duplicate_remote_{field_name}"}
            for identity in sorted(duplicate_ids)
        ]
        return indexed, conflicts, unmanaged

    @staticmethod
    def _safe_fields(
        client: FeishuClient, table_id: str
    ) -> tuple[dict[str, dict[str, Any]] | None, FeishuClientError | None]:
        try:
            return FeishuSyncService._field_index(client.list_fields(table_id)), None
        except FeishuClientError as exc:
            return None, exc

    @staticmethod
    def _relation_ids(value: Any) -> list[str]:
        result: list[str] = []

        def collect(item: Any, *, explicit: bool = False) -> None:
            if isinstance(item, dict):
                if "record_id" in item:
                    collect(item.get("record_id"), explicit=True)
                if "record_ids" in item:
                    collect(item.get("record_ids"), explicit=True)
                return
            if isinstance(item, (list, tuple)):
                for nested in item:
                    collect(nested, explicit=explicit)
                return
            identity = FeishuSyncService._text(item)
            if identity and (explicit or isinstance(value, (str, int))) and identity not in result:
                result.append(identity)

        collect(value, explicit=isinstance(value, (list, tuple)))
        return result

    @staticmethod
    def _legacy_relation_ids(value: Any) -> list[str]:
        """Preserve the frozen M7.1 one-way legacy matching contract."""
        items = value if isinstance(value, list) else [value]
        result: list[str] = []
        for item in items:
            identity = FeishuSyncService._text(
                item.get("record_id") if isinstance(item, dict) else item
            )
            if identity and identity not in result:
                result.append(identity)
        return result

    @staticmethod
    def _field_text(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("text") or value.get("link") or value.get("value") or "").strip()
        if isinstance(value, list):
            if len(value) == 1:
                return FeishuSyncService._field_text(value[0])
            return ""
        return str(value or "").strip()

    @staticmethod
    def _number(value: Any) -> int | float | str:
        text = str(value if value is not None else "").replace(",", "").strip()
        if not text:
            return ""
        try:
            number = float(text)
        except ValueError:
            return ""
        return int(number) if number.is_integer() else number

    @staticmethod
    def _milliseconds(value: Any) -> int | str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return ""
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)

    @staticmethod
    def _chunks(items: list[dict[str, Any]], size: int):
        for index in range(0, len(items), size):
            yield items[index:index + size]

    def _public_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        public_keys = (
            "status", "started_at", "completed_at", "local_creator_count",
            "local_active_creator_count", "local_archived_creator_count",
            "local_account_count", "local_creators_missing_creator_id",
            "local_accounts_missing_account_uid", "local_creator_id_duplicate_count",
            "local_account_uid_duplicate_count", "remote_creator_count", "remote_account_count",
            "creator_create_count", "creator_update_count", "creator_unchanged_count",
            "creator_conflict_count", "account_create_count", "account_update_count",
            "account_unchanged_count", "account_conflict_count", "remote_unmanaged_count",
            "duplicate_identity_count", "blocked_reason", "warnings", "conflicts",
            "error_codes", "missing_fields", "incompatible_fields",
        )
        return {key: plan.get(key) for key in public_keys}

    def _now(self) -> str:
        return self._now_provider().astimezone(timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()
