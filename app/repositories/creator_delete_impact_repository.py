from __future__ import annotations

"""Read-only structural scanner for a future Creator hard-delete operation."""

import json
import re
from pathlib import Path
from typing import Any

from data_repository_base import ExcelDataRepository
from excel_workbook_store import ExcelWorkbookStore
from runtime_paths import json_backup_path, load_json_with_backup


_TASK_ID_PATTERN = re.compile(r"^task_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
_REQUIRED_SHEETS = {
    "Creators", "CreatorAccounts", "Videos", "Insights", "_AnalysisData",
    "CreatorSnapshots", "VideoSnapshots", "Cooperations", "CampaignCreators",
    "FollowUpLogs", "Agencies", "AgencyContacts", "Products", "Campaigns",
    "_Metadata",
}


class CreatorDeleteImpactRepository(ExcelDataRepository):
    def __init__(
        self,
        workbook_path: Path | ExcelWorkbookStore,
        *,
        tasks_dir: Path | None = None,
        data_protection_file: Path | None = None,
        legacy_analysis_dir: Path | None = None,
        legacy_library_file: Path | None = None,
    ) -> None:
        super().__init__(workbook_path)
        self._tasks_dir = Path(tasks_dir) if tasks_dir is not None else None
        self._data_protection_file = (
            Path(data_protection_file) if data_protection_file is not None else None
        )
        self._legacy_analysis_dir = (
            Path(legacy_analysis_dir) if legacy_analysis_dir is not None else None
        )
        self._legacy_library_file = (
            Path(legacy_library_file) if legacy_library_file is not None else None
        )

    def scan_creator_delete_impact(self, creator_id: str) -> dict[str, Any]:
        creator_id = str(creator_id or "").strip()
        try:
            with self.store.read_only_workbook() as workbook:
                snapshot = self._scan_workbook(workbook, creator_id)
            artifacts = self._scan_artifacts(
                creator_id,
                set(snapshot.pop("account_ids")),
                set(snapshot.pop("account_uids")),
                set(snapshot.pop("snapshot_ids")),
            )
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError("删除影响扫描未完成。") from exc

        snapshot["impact"].update(artifacts["impact"])
        snapshot["structural_ids"].update(artifacts["structural_ids"])
        return snapshot

    def _scan_workbook(self, workbook, creator_id: str) -> dict[str, Any]:
        missing = sorted(_REQUIRED_SHEETS - set(workbook.sheetnames))
        if missing:
            raise RuntimeError(f"达人库缺少扫描所需工作表：{', '.join(missing)}")
        rows = {name: self.rows(workbook[name]) for name in _REQUIRED_SHEETS}
        creators = [
            row for row in rows["Creators"]
            if str(row.get("creator_id") or "") == creator_id
        ]
        if not creators:
            raise ValueError("未找到达人分析记录。")
        if len(creators) != 1:
            raise RuntimeError("Creator 主记录不唯一。")
        creator = creators[0]

        accounts = self._matching(rows["CreatorAccounts"], "creator_id", creator_id)
        account_ids = {str(row.get("account_id") or "") for row in accounts}
        account_ids.discard("")
        account_uids = {str(row.get("account_uid") or "") for row in accounts}
        account_uids.discard("")
        snapshots = self._matching(rows["CreatorSnapshots"], "creator_id", creator_id)
        snapshot_ids = {str(row.get("snapshot_id") or "") for row in snapshots}
        snapshot_ids.discard("")

        video_snapshots = [
            row for row in rows["VideoSnapshots"]
            if str(row.get("creator_id") or "") == creator_id
            or str(row.get("snapshot_id") or "") in snapshot_ids
        ]
        direct_video_snapshots = sum(
            1 for row in video_snapshots
            if str(row.get("creator_id") or "") == creator_id
        )
        campaign_relations = self._matching(
            rows["CampaignCreators"], "creator_id", creator_id
        )
        active_relations = [
            row for row in campaign_relations
            if not str(row.get("archived_at") or "").strip()
        ]
        archived_relations = [
            row for row in campaign_relations
            if str(row.get("archived_at") or "").strip()
        ]
        cooperations = self._matching(rows["Cooperations"], "creator_id", creator_id)

        followups: list[dict[str, Any]] = []
        unknown_followups = 0
        for row in rows["FollowUpLogs"]:
            if str(row.get("object_id") or "") != creator_id:
                continue
            if str(row.get("object_type") or "").strip().casefold() == "creator":
                followups.append(row)
            else:
                unknown_followups += 1

        analysis_rows = self._matching(rows["_AnalysisData"], "creator_id", creator_id)
        embedded_analysis_references = 0
        for row in rows["_AnalysisData"]:
            raw = row.get("analysis_json")
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                analysis = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("_AnalysisData 包含无法解析的结构化 JSON。") from exc
            if not isinstance(analysis, dict):
                raise RuntimeError("_AnalysisData 的结构化 JSON 格式无效。")
            if str(row.get("creator_id") or "") == creator_id:
                continue
            if (
                str(analysis.get("creator_id") or "") == creator_id
                or str(analysis.get("analysis_id") or "") == creator_id
                or str(analysis.get("account_uid") or "") in account_uids
            ):
                embedded_analysis_references += 1

        campaigns_by_id = {
            str(row.get("campaign_id") or ""): row for row in rows["Campaigns"]
            if str(row.get("campaign_id") or "")
        }
        products_by_id = {
            str(row.get("product_id") or ""): row for row in rows["Products"]
            if str(row.get("product_id") or "")
        }
        related_campaign_ids = {
            str(row.get("campaign_id") or "") for row in campaign_relations
            if str(row.get("campaign_id") or "") in campaigns_by_id
        }
        related_product_ids = {
            str(campaigns_by_id[campaign_id].get("product_id") or "")
            for campaign_id in related_campaign_ids
            if str(campaigns_by_id[campaign_id].get("product_id") or "") in products_by_id
        }

        agency_ids = {str(creator.get("agency_id") or "").strip()} - {""}
        contact_ids = {
            str(creator.get("current_contact_id") or "").strip(),
            str(creator.get("source_contact_id") or "").strip(),
        } - {""}
        existing_agency_ids = {
            str(row.get("agency_id") or "") for row in rows["Agencies"]
        }
        existing_contact_ids = {
            str(row.get("contact_id") or "") for row in rows["AgencyContacts"]
        }

        broken: list[str] = []
        account_owner = {
            str(row.get("account_id") or ""): str(row.get("creator_id") or "")
            for row in rows["CreatorAccounts"]
            if str(row.get("account_id") or "")
        }
        for relation in campaign_relations:
            account_id = str(relation.get("account_id") or "")
            campaign_id = str(relation.get("campaign_id") or "")
            if not account_id or account_owner.get(account_id) != creator_id:
                broken.append("campaign_creator_account")
            if not campaign_id or campaign_id not in campaigns_by_id:
                broken.append("campaign_creator_campaign")
        for row in video_snapshots:
            if str(row.get("snapshot_id") or "") not in snapshot_ids:
                broken.append("video_snapshot_parent")
        if agency_ids - existing_agency_ids:
            broken.append("creator_agency")
        if contact_ids - existing_contact_ids:
            broken.append("creator_contact")

        relation_ids = {
            str(row.get("id") or "") for row in campaign_relations
            if str(row.get("id") or "")
        }
        cooperation_ids = {
            str(row.get("cooperation_id") or "") for row in cooperations
            if str(row.get("cooperation_id") or "")
        }
        followup_ids = {
            str(row.get("follow_up_id") or "") for row in followups
            if str(row.get("follow_up_id") or "")
        }
        return {
            "creator_id": creator_id,
            "display_name": str(creator.get("name") or ""),
            "creator_updated_at": str(creator.get("updated_at") or ""),
            "is_archived": bool(str(creator.get("archived_at") or "").strip()),
            "impact": {
                "creators": 1,
                "creator_accounts": len(accounts),
                "videos": len(self._matching(rows["Videos"], "creator_id", creator_id)),
                "insights": len(self._matching(rows["Insights"], "creator_id", creator_id)),
                "analysis_data": len(analysis_rows),
                "creator_snapshots": len(snapshots),
                "video_snapshots": {
                    "total": len(video_snapshots),
                    "direct": direct_video_snapshots,
                    "indirect": len(video_snapshots) - direct_video_snapshots,
                },
                "cooperations": len(cooperations),
                "campaign_creators": {
                    "total": len(campaign_relations),
                    "active": len(active_relations),
                    "archived": len(archived_relations),
                },
                "follow_up_logs": len(followups),
                "embedded_analysis_references": embedded_analysis_references,
            },
            "retained": {
                "agencies": len(agency_ids & existing_agency_ids),
                "agency_contacts": len(contact_ids & existing_contact_ids),
                "products": len(related_product_ids),
                "campaigns": len(related_campaign_ids),
                "metadata": len(rows["_Metadata"]),
            },
            "unknown_followup_reference_count": unknown_followups,
            "broken_references": broken,
            "account_ids": sorted(account_ids),
            "account_uids": sorted(account_uids),
            "snapshot_ids": sorted(snapshot_ids),
            "structural_ids": {
                "account_ids": sorted(account_ids),
                "snapshot_ids": sorted(snapshot_ids),
                "campaign_relation_ids": sorted(relation_ids),
                "cooperation_ids": sorted(cooperation_ids),
                "followup_ids": sorted(followup_ids),
            },
        }

    def _scan_artifacts(
        self,
        creator_id: str,
        account_ids: set[str],
        account_uids: set[str],
        snapshot_ids: set[str],
    ) -> dict[str, Any]:
        task_ids, unmapped_task_ids = self._matching_task_ids(
            creator_id, account_ids, snapshot_ids
        )
        protection_uids = self._matching_protection_uids(account_uids)
        legacy_ids = self._matching_legacy_sources(creator_id, account_uids)
        return {
            "impact": {
                "task_artifacts": len(task_ids),
                "unmapped_task_artifacts": len(unmapped_task_ids),
                "data_protection": len(protection_uids),
                "legacy_sources": len(legacy_ids),
            },
            "structural_ids": {
                "task_ids": sorted(task_ids),
                "unmapped_task_ids": sorted(unmapped_task_ids),
                "legacy_source_ids": sorted(legacy_ids),
            },
        }

    def _matching_task_ids(
        self, creator_id: str, account_ids: set[str], snapshot_ids: set[str]
    ) -> tuple[set[str], set[str]]:
        if self._tasks_dir is None or not self._tasks_dir.exists():
            return set(), set()
        matched: set[str] = set()
        unmapped: set[str] = set()
        for root in self._tasks_dir.iterdir():
            if not root.is_dir() or not _TASK_ID_PATTERN.fullmatch(root.name):
                continue
            metadata_path = root / "task.json"
            if not metadata_path.is_file():
                raise RuntimeError("任务元数据缺失。")
            try:
                task = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("任务元数据无法读取。") from exc
            if not isinstance(task, dict) or str(task.get("id") or "") != root.name:
                raise RuntimeError("任务元数据格式无效。")
            creator_ids = task.get("creator_library_creator_ids")
            linked_creators = {
                str(value) for value in creator_ids if str(value)
            } if isinstance(creator_ids, list) else set()
            linked_accounts = task.get("creator_library_account_ids")
            linked_account_ids = {
                str(value) for value in linked_accounts if str(value)
            } if isinstance(linked_accounts, list) else set()
            analysis_id = str(task.get("creator_analysis_id") or "")
            direct_creator_id = str(task.get("creator_id") or "")
            task_snapshot_id = str(task.get("creator_snapshot_id") or "")
            if (
                analysis_id == creator_id
                or direct_creator_id == creator_id
                or creator_id in linked_creators
                or bool(account_ids & linked_account_ids)
                or task_snapshot_id in snapshot_ids
            ):
                matched.add(root.name)
            elif not (
                analysis_id
                or direct_creator_id
                or linked_creators
                or linked_account_ids
                or task_snapshot_id
            ):
                unmapped.add(root.name)
        return matched, unmapped

    def _matching_protection_uids(self, account_uids: set[str]) -> set[str]:
        path = self._data_protection_file
        if path is None:
            return set()
        backup = json_backup_path(path)
        if not path.exists() and not backup.exists():
            return set()
        data, source = load_json_with_backup(path)
        if source is None or not isinstance(data, dict):
            raise RuntimeError("数据保护文件无法读取。")
        return account_uids & {str(key) for key in data if str(key)}

    def _matching_legacy_sources(
        self, creator_id: str, account_uids: set[str]
    ) -> set[str]:
        matched: set[str] = set()
        directory = self._legacy_analysis_dir
        if directory is not None and directory.exists():
            for path in directory.glob("analysis_task_*.json"):
                data, source = load_json_with_backup(path)
                if source is None or not isinstance(data, dict):
                    raise RuntimeError("Legacy analysis 文件无法读取。")
                if (
                    str(data.get("analysis_id") or "") == creator_id
                    or str(data.get("creator_id") or "") == creator_id
                    or str(data.get("account_uid") or "") in account_uids
                ):
                    matched.add(path.name)
        path = self._legacy_library_file
        if path is not None:
            backup = json_backup_path(path)
            if path.exists() or backup.exists():
                data, source = load_json_with_backup(path)
                if source is None or not isinstance(data, dict):
                    raise RuntimeError("Legacy Creator Library 文件无法读取。")
                records = data.get("records")
                if not isinstance(records, dict):
                    raise RuntimeError("Legacy Creator Library 格式无效。")
                for key, value in records.items():
                    record = value if isinstance(value, dict) else {}
                    if (
                        str(key) == creator_id
                        or str(record.get("creator_id") or "") == creator_id
                        or str(record.get("analysis_id") or "") == creator_id
                        or str(record.get("account_uid") or "") in account_uids
                    ):
                        matched.add(f"library:{key}")
        return matched

    @staticmethod
    def _matching(
        rows: list[dict[str, Any]], key: str, expected: str
    ) -> list[dict[str, Any]]:
        return [row for row in rows if str(row.get(key) or "") == expected]
