from __future__ import annotations

"""Fail-closed planning and atomic workbook mutation for manual Creator merge."""

import hashlib
import json
from pathlib import Path
from typing import Any

from data_repository_base import ExcelDataRepository
from excel_workbook_store import ExcelWorkbookStore


class CreatorMergePlanError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CreatorMergeRepository(ExcelDataRepository):
    _OWNERSHIP_SHEETS = (
        "CreatorAccounts",
        "Videos",
        "CreatorSnapshots",
        "VideoSnapshots",
        "Cooperations",
        "CampaignCreators",
    )

    def __init__(
        self,
        workbook_path: Path | ExcelWorkbookStore,
        *,
        tasks_dir: Path | None = None,
        mail_messages_path: Path | None = None,
        legacy_library_file: Path | None = None,
    ) -> None:
        super().__init__(workbook_path)
        self.tasks_dir = Path(tasks_dir) if tasks_dir is not None else None
        self.mail_messages_path = (
            Path(mail_messages_path) if mail_messages_path is not None else None
        )
        self.legacy_library_file = (
            Path(legacy_library_file) if legacy_library_file is not None else None
        )

    def preview(self, primary_creator_id: str, secondary_creator_id: str) -> dict[str, Any]:
        with self.store.read_only_workbook() as workbook:
            return self._build_plan(workbook, primary_creator_id, secondary_creator_id)

    def execute(
        self,
        primary_creator_id: str,
        secondary_creator_id: str,
        *,
        preview_fingerprint: str,
    ) -> dict[str, Any]:
        with self.store.workbook(write=True) as workbook:
            plan = self._build_plan(workbook, primary_creator_id, secondary_creator_id)
            if plan["preview_fingerprint"] != preview_fingerprint:
                raise CreatorMergePlanError("STALE_PREVIEW")
            self._require_safe(plan)
            counts = self._apply(workbook, plan)
            self._checkpoint("before_save")
            self._verify(workbook, plan)
            return {
                "primary_creator_id": plan["primary"]["creator_id"],
                "secondary_creator_id": plan["secondary"]["creator_id"],
                "migrated": counts,
            }

    def _build_plan(self, workbook, primary_id: str, secondary_id: str) -> dict[str, Any]:
        primary_id = str(primary_id or "").strip()
        secondary_id = str(secondary_id or "").strip()
        conflicts: list[dict[str, str]] = []
        if not primary_id or not secondary_id:
            conflicts.append(self._conflict("CREATOR_NOT_FOUND"))
        if primary_id and primary_id == secondary_id:
            conflicts.append(self._conflict("SAME_CREATOR"))

        creators = self.rows(workbook["Creators"])
        primary_rows = [row for row in creators if str(row.get("creator_id") or "") == primary_id]
        secondary_rows = [row for row in creators if str(row.get("creator_id") or "") == secondary_id]
        if len(primary_rows) != 1 or len(secondary_rows) != 1:
            conflicts.append(self._conflict("CREATOR_NOT_FOUND"))
        primary = primary_rows[0] if len(primary_rows) == 1 else {}
        secondary = secondary_rows[0] if len(secondary_rows) == 1 else {}

        accounts = self.rows(workbook["CreatorAccounts"])
        primary_accounts = [row for row in accounts if str(row.get("creator_id") or "") == primary_id]
        secondary_accounts = [row for row in accounts if str(row.get("creator_id") or "") == secondary_id]
        uid_counts: dict[str, int] = {}
        account_id_counts: dict[str, int] = {}
        for account in accounts:
            uid = str(account.get("account_uid") or "").strip()
            account_id = str(account.get("account_id") or "").strip()
            if uid:
                uid_counts[uid] = uid_counts.get(uid, 0) + 1
            if account_id:
                account_id_counts[account_id] = account_id_counts.get(account_id, 0) + 1
        if any(not uid for uid in uid_counts) or any(count != 1 for count in uid_counts.values()):
            conflicts.append(self._conflict("DUPLICATE_ACCOUNT_UID", "CreatorAccounts"))
        if any(
            not str(row.get("account_uid") or "").strip()
            or not str(row.get("account_id") or "").strip()
            for row in accounts
        ):
            conflicts.append(self._conflict("ORPHAN_REFERENCE", "CreatorAccounts"))
        if any(count != 1 for count in account_id_counts.values()):
            conflicts.append(self._conflict("ORPHAN_REFERENCE", "CreatorAccounts"))
        if any(not str(row.get("account_uid") or "").strip() for row in secondary_accounts):
            conflicts.append(self._conflict("ORPHAN_REFERENCE", "CreatorAccounts"))
        if any(uid_counts.get(str(row.get("account_uid") or "").strip(), 0) != 1 for row in secondary_accounts):
            conflicts.append(self._conflict("DUPLICATE_ACCOUNT_UID", "CreatorAccounts"))
        if any(
            not str(row.get("account_id") or "").strip()
            or account_id_counts.get(str(row.get("account_id") or "").strip(), 0) != 1
            for row in secondary_accounts
        ):
            conflicts.append(self._conflict("ORPHAN_REFERENCE", "CreatorAccounts"))

        primary_uids = {str(row.get("account_uid") or "").strip() for row in primary_accounts}
        secondary_uids = {str(row.get("account_uid") or "").strip() for row in secondary_accounts}
        if primary_uids & secondary_uids:
            conflicts.append(self._conflict("DUPLICATE_ACCOUNT_UID", "CreatorAccounts"))

        insights = self.rows(workbook["Insights"])
        primary_insights = [row for row in insights if str(row.get("creator_id") or "") == primary_id]
        secondary_insights = [row for row in insights if str(row.get("creator_id") or "") == secondary_id]
        if len(primary_insights) > 1 or len(secondary_insights) > 1 or (
            primary_insights and secondary_insights
        ):
            conflicts.append(self._conflict("INSIGHT_CONFLICT", "Insights"))

        campaign_rows = self.rows(workbook["CampaignCreators"])
        campaign_ids = {
            str(row.get("campaign_id") or "")
            for row in self.rows(workbook["Campaigns"])
            if str(row.get("campaign_id") or "")
        }
        primary_campaigns = {
            str(row.get("campaign_id") or "").strip()
            for row in campaign_rows
            if str(row.get("creator_id") or "") == primary_id
        }
        secondary_campaigns = {
            str(row.get("campaign_id") or "").strip()
            for row in campaign_rows
            if str(row.get("creator_id") or "") == secondary_id
        }
        if (primary_campaigns & secondary_campaigns) - {""}:
            conflicts.append(self._conflict("CAMPAIGN_DUPLICATE", "CampaignCreators"))

        account_owner = {
            str(row.get("account_id") or ""): str(row.get("creator_id") or "")
            for row in accounts
            if str(row.get("account_id") or "")
        }
        for row in campaign_rows:
            if str(row.get("creator_id") or "") != secondary_id:
                continue
            if account_owner.get(str(row.get("account_id") or "")) != secondary_id:
                conflicts.append(self._conflict("ORPHAN_REFERENCE", "CampaignCreators"))
            if str(row.get("campaign_id") or "") not in campaign_ids:
                conflicts.append(self._conflict("ORPHAN_REFERENCE", "CampaignCreators"))

        snapshots = self.rows(workbook["CreatorSnapshots"])
        snapshot_ids = {
            str(row.get("snapshot_id") or "")
            for row in snapshots
            if str(row.get("creator_id") or "") == secondary_id
        }
        all_snapshot_ids = {
            str(row.get("snapshot_id") or "") for row in snapshots
            if str(row.get("snapshot_id") or "")
        }
        known_uids = primary_uids | secondary_uids
        for row in snapshots:
            if str(row.get("creator_id") or "") != secondary_id:
                continue
            uid = str(row.get("account_uid") or "").strip()
            if uid and uid not in known_uids:
                conflicts.append(self._conflict("ORPHAN_REFERENCE", "CreatorSnapshots"))

        video_snapshots = self.rows(workbook["VideoSnapshots"])
        for row in video_snapshots:
            row_snapshot_id = str(row.get("snapshot_id") or "")
            if str(row.get("creator_id") or "") == secondary_id and row_snapshot_id not in all_snapshot_ids:
                conflicts.append(self._conflict("ORPHAN_REFERENCE", "VideoSnapshots"))
            if row_snapshot_id not in snapshot_ids:
                continue
            owner = str(row.get("creator_id") or "")
            if owner and owner != secondary_id:
                conflicts.append(self._conflict("ORPHAN_REFERENCE", "VideoSnapshots"))

        followups = self.rows(workbook["FollowUpLogs"])
        for row in followups:
            if str(row.get("object_id") or "") != secondary_id:
                continue
            if str(row.get("object_type") or "").strip().casefold() != "creator":
                conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "FollowUpLogs"))

        analysis_rows = self.rows(workbook["_AnalysisData"])
        primary_analysis = [row for row in analysis_rows if str(row.get("creator_id") or "") == primary_id]
        secondary_analysis = [row for row in analysis_rows if str(row.get("creator_id") or "") == secondary_id]
        if len(primary_analysis) > 1 or len(secondary_analysis) > 1:
            conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "_AnalysisData"))
        for row in secondary_analysis:
            raw = row.get("analysis_json")
            if raw not in (None, ""):
                try:
                    if not isinstance(json.loads(str(raw)), dict):
                        raise ValueError
                except (json.JSONDecodeError, ValueError):
                    conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "_AnalysisData"))

        conflicts.extend(self._external_reference_conflicts(secondary_id))
        summary = {
            "accounts": len(secondary_accounts),
            "creator_snapshots": sum(str(row.get("creator_id") or "") == secondary_id for row in snapshots),
            "videos": self._count(workbook, "Videos", "creator_id", secondary_id),
            "video_snapshots": sum(
                str(row.get("creator_id") or "") == secondary_id
                or str(row.get("snapshot_id") or "") in snapshot_ids
                for row in video_snapshots
            ),
            "insights": len(secondary_insights),
            "campaign_creators": self._count(workbook, "CampaignCreators", "creator_id", secondary_id),
            "cooperations": self._count(workbook, "Cooperations", "creator_id", secondary_id),
            "follow_up_logs": sum(
                str(row.get("object_id") or "") == secondary_id
                and str(row.get("object_type") or "").strip().casefold() == "creator"
                for row in followups
            ),
            "analysis_data": len(secondary_analysis),
        }
        plan = {
            "primary": self._creator_summary(primary, primary_accounts),
            "secondary": self._creator_summary(secondary, secondary_accounts),
            "migration_summary": summary,
            "conflicts": self._unique_conflicts(conflicts),
        }
        plan["safe_to_merge"] = not plan["conflicts"]
        evidence = {
            "primary_updated_at": str(primary.get("updated_at") or ""),
            "secondary_updated_at": str(secondary.get("updated_at") or ""),
            "secondary_account_ids": sorted(str(row.get("account_id") or "") for row in secondary_accounts),
            "secondary_account_uids": sorted(secondary_uids),
            "secondary_snapshot_ids": sorted(snapshot_ids),
            "secondary_campaign_relation_ids": sorted(
                str(row.get("id") or "") for row in campaign_rows
                if str(row.get("creator_id") or "") == secondary_id
            ),
            "secondary_cooperation_ids": sorted(
                str(row.get("cooperation_id") or "")
                for row in self.rows(workbook["Cooperations"])
                if str(row.get("creator_id") or "") == secondary_id
            ),
            "secondary_followup_ids": sorted(
                str(row.get("follow_up_id") or "") for row in followups
                if str(row.get("object_id") or "") == secondary_id
            ),
        }
        plan["preview_fingerprint"] = self._fingerprint({**plan, "_evidence": evidence})
        return plan

    def _apply(self, workbook, plan: dict[str, Any]) -> dict[str, int]:
        primary_id = plan["primary"]["creator_id"]
        secondary_id = plan["secondary"]["creator_id"]
        counts: dict[str, int] = {}
        for sheet_name in self._OWNERSHIP_SHEETS:
            counts[sheet_name] = self._replace_value(
                workbook[sheet_name], "creator_id", secondary_id, primary_id
            )
            if sheet_name == "CreatorAccounts":
                self._checkpoint("after_accounts")
            elif sheet_name == "CreatorSnapshots":
                self._checkpoint("after_snapshots")
            elif sheet_name == "CampaignCreators":
                self._checkpoint("after_campaigns")

        if plan["migration_summary"]["insights"]:
            counts["Insights"] = self._replace_value(
                workbook["Insights"], "creator_id", secondary_id, primary_id
            )
        else:
            counts["Insights"] = 0

        counts["FollowUpLogs"] = self._replace_followups(
            workbook["FollowUpLogs"], secondary_id, primary_id
        )
        counts["_AnalysisData"] = self._merge_analysis_data(
            workbook["_AnalysisData"], primary_id, secondary_id
        )
        if not self.delete_row(workbook["Creators"], "creator_id", secondary_id):
            raise CreatorMergePlanError("CREATOR_NOT_FOUND")
        counts["Creators"] = 1
        return counts

    def _verify(self, workbook, plan: dict[str, Any]) -> None:
        primary_id = plan["primary"]["creator_id"]
        secondary_id = plan["secondary"]["creator_id"]
        creators = self.rows(workbook["Creators"])
        creator_ids = [str(row.get("creator_id") or "") for row in creators]
        if creator_ids.count(primary_id) != 1 or secondary_id in creator_ids:
            raise CreatorMergePlanError("MERGE_FAILED")
        creator_id_set = set(creator_ids)
        accounts = self.rows(workbook["CreatorAccounts"])
        account_uids = [str(row.get("account_uid") or "") for row in accounts]
        if len(account_uids) != len(set(account_uids)):
            raise CreatorMergePlanError("DUPLICATE_ACCOUNT_UID")
        if any(str(row.get("creator_id") or "") not in creator_id_set for row in accounts):
            raise CreatorMergePlanError("ORPHAN_REFERENCE")
        for sheet_name in (*self._OWNERSHIP_SHEETS[1:], "Insights"):
            if any(str(row.get("creator_id") or "") == secondary_id for row in self.rows(workbook[sheet_name])):
                raise CreatorMergePlanError("MERGE_FAILED")
        if any(str(row.get("creator_id") or "") == secondary_id for row in self.rows(workbook["_AnalysisData"])):
            raise CreatorMergePlanError("MERGE_FAILED")
        if any(
            str(row.get("object_id") or "") == secondary_id
            for row in self.rows(workbook["FollowUpLogs"])
        ):
            raise CreatorMergePlanError("MERGE_FAILED")

    def _external_reference_conflicts(self, secondary_id: str) -> list[dict[str, str]]:
        conflicts: list[dict[str, str]] = []
        if self.tasks_dir and self.tasks_dir.is_dir():
            for path in self.tasks_dir.rglob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "Tasks"))
                    break
                if self._structured_creator_reference(data, secondary_id):
                    conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "Tasks"))
                    break
        if self.mail_messages_path and self.mail_messages_path.is_file():
            try:
                data = json.loads(self.mail_messages_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "Mail"))
            else:
                messages = data.get("messages") if isinstance(data, dict) else None
                if isinstance(messages, list) and any(
                    isinstance(item, dict)
                    and str(item.get("matched_creator_id") or "") == secondary_id
                    for item in messages
                ):
                    conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "Mail"))
        if self.legacy_library_file and self.legacy_library_file.is_file():
            try:
                data = json.loads(self.legacy_library_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "Legacy"))
            else:
                if self._structured_creator_reference(data, secondary_id):
                    conflicts.append(self._conflict("UNSUPPORTED_REFERENCE", "Legacy"))
        return conflicts

    @classmethod
    def _structured_creator_reference(cls, value: Any, creator_id: str) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"creator_id", "creator_analysis_id"} and str(item or "") == creator_id:
                    return True
                if key == "creator_library_creator_ids" and isinstance(item, list) and creator_id in map(str, item):
                    return True
                if cls._structured_creator_reference(item, creator_id):
                    return True
        elif isinstance(value, list):
            return any(cls._structured_creator_reference(item, creator_id) for item in value)
        return False

    @staticmethod
    def _creator_summary(creator: dict[str, Any], accounts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "creator_id": str(creator.get("creator_id") or ""),
            "display_name": str(creator.get("name") or ""),
            "archived": bool(str(creator.get("archived_at") or "").strip()),
            "account_count": len(accounts),
            "platforms": sorted({str(row.get("platform") or "") for row in accounts if str(row.get("platform") or "")}),
            "accounts": [
                {
                    "platform": str(row.get("platform") or ""),
                    "username": str(row.get("username") or ""),
                    "profile_url": str(row.get("profile_url") or ""),
                    "followers": row.get("followers") if row.get("followers") not in (None, "") else "",
                }
                for row in accounts
            ],
        }

    @staticmethod
    def _replace_value(sheet, key: str, old: str, new: str) -> int:
        headers = [str(cell.value or "") for cell in sheet[1]]
        column = headers.index(key) + 1
        count = 0
        for row_index in range(2, sheet.max_row + 1):
            if str(sheet.cell(row_index, column).value or "") == old:
                sheet.cell(row_index, column, new)
                count += 1
        return count

    @staticmethod
    def _replace_followups(sheet, old: str, new: str) -> int:
        headers = [str(cell.value or "") for cell in sheet[1]]
        type_column = headers.index("object_type") + 1
        id_column = headers.index("object_id") + 1
        count = 0
        for row_index in range(2, sheet.max_row + 1):
            if (
                str(sheet.cell(row_index, type_column).value or "").strip().casefold() == "creator"
                and str(sheet.cell(row_index, id_column).value or "") == old
            ):
                sheet.cell(row_index, id_column, new)
                count += 1
        return count

    @classmethod
    def _merge_analysis_data(cls, sheet, primary_id: str, secondary_id: str) -> int:
        headers = [str(cell.value or "") for cell in sheet[1]]
        creator_column = headers.index("creator_id") + 1
        json_column = headers.index("analysis_json") + 1
        primary_exists = any(
            str(sheet.cell(index, creator_column).value or "") == primary_id
            for index in range(2, sheet.max_row + 1)
        )
        secondary_rows = [
            index for index in range(2, sheet.max_row + 1)
            if str(sheet.cell(index, creator_column).value or "") == secondary_id
        ]
        for row_index in reversed(secondary_rows):
            if primary_exists:
                sheet.delete_rows(row_index, 1)
                continue
            sheet.cell(row_index, creator_column, primary_id)
            raw = sheet.cell(row_index, json_column).value
            if raw not in (None, ""):
                data = json.loads(str(raw))
                if str(data.get("creator_id") or "") == secondary_id:
                    data["creator_id"] = primary_id
                sheet.cell(row_index, json_column, json.dumps(data, ensure_ascii=False))
        return len(secondary_rows)

    @staticmethod
    def _count(workbook, sheet_name: str, key: str, value: str) -> int:
        return sum(
            str(row.get(key) or "") == value
            for row in CreatorMergeRepository.rows(workbook[sheet_name])
        )

    @staticmethod
    def _conflict(code: str, source: str = "") -> dict[str, str]:
        result = {"code": code}
        if source:
            result["source"] = source
        return result

    @staticmethod
    def _unique_conflicts(conflicts: list[dict[str, str]]) -> list[dict[str, str]]:
        unique = {(item.get("code", ""), item.get("source", "")): item for item in conflicts}
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _fingerprint(plan: dict[str, Any]) -> str:
        payload = {key: value for key, value in plan.items() if key != "preview_fingerprint"}
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _require_safe(plan: dict[str, Any]) -> None:
        if not plan.get("safe_to_merge"):
            code = str((plan.get("conflicts") or [{}])[0].get("code") or "MERGE_FAILED")
            raise CreatorMergePlanError(code)

    def _checkpoint(self, _name: str) -> None:
        """Test seam for proving that pre-save failures never persist partial mutation."""
