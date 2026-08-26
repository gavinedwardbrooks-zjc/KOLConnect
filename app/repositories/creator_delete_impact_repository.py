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
                snapshot.pop("account_id_owners"),
                snapshot.pop("account_uid_owners"),
                snapshot.pop("snapshot_id_owners"),
                set(snapshot.pop("known_creator_ids")),
            )
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError("删除影响扫描未完成。") from exc

        snapshot["impact"].update(artifacts["impact"])
        snapshot["structural_ids"].update(artifacts["structural_ids"])
        snapshot["resource_locators"].update(artifacts["resource_locators"])
        snapshot["safety_blocks"].extend(artifacts["safety_blocks"])
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

        known_creator_ids = {
            str(row.get("creator_id") or "") for row in rows["Creators"]
            if str(row.get("creator_id") or "")
        }
        account_id_owners: dict[str, set[str]] = {}
        account_uid_owners: dict[str, set[str]] = {}
        account_id_counts: dict[str, int] = {}
        for row in rows["CreatorAccounts"]:
            owner = str(row.get("creator_id") or "")
            account_id = str(row.get("account_id") or "")
            account_uid = str(row.get("account_uid") or "")
            if account_id and owner:
                account_id_owners.setdefault(account_id, set()).add(owner)
                account_id_counts[account_id] = account_id_counts.get(account_id, 0) + 1
            if account_uid and owner:
                account_uid_owners.setdefault(account_uid, set()).add(owner)

        accounts = self._matching(rows["CreatorAccounts"], "creator_id", creator_id)
        account_ids = {str(row.get("account_id") or "") for row in accounts}
        account_ids.discard("")
        account_uids = {str(row.get("account_uid") or "") for row in accounts}
        account_uids.discard("")
        snapshots = self._matching(rows["CreatorSnapshots"], "creator_id", creator_id)
        snapshot_ids = {str(row.get("snapshot_id") or "") for row in snapshots}
        snapshot_ids.discard("")

        snapshot_id_owners: dict[str, set[str]] = {}
        snapshot_id_counts: dict[str, int] = {}
        for row in rows["CreatorSnapshots"]:
            snapshot_id = str(row.get("snapshot_id") or "")
            owner = str(row.get("creator_id") or "")
            if snapshot_id:
                snapshot_id_counts[snapshot_id] = snapshot_id_counts.get(snapshot_id, 0) + 1
            if snapshot_id and owner:
                snapshot_id_owners.setdefault(snapshot_id, set()).add(owner)

        safety_blocks: list[dict[str, Any]] = []
        account_locators: list[dict[str, str]] = []
        for row in accounts:
            account_id = str(row.get("account_id") or "")
            if (
                not account_id
                or account_id_counts.get(account_id) != 1
                or account_id_owners.get(account_id) != {creator_id}
            ):
                safety_blocks.append({
                    "source": "creator_accounts",
                    "code": "CREATOR_ACCOUNT_LOCATOR_CONFLICT",
                    "stable_id": account_id,
                })
                continue
            account_locators.append(self._locator(
                "creator_accounts", account_id, "workbook:CreatorAccounts"
            ))
        creator_snapshot_locators: list[dict[str, str]] = []
        for row in snapshots:
            snapshot_id = str(row.get("snapshot_id") or "")
            if (
                not snapshot_id
                or snapshot_id_counts.get(snapshot_id) != 1
                or snapshot_id_owners.get(snapshot_id) != {creator_id}
            ):
                safety_blocks.append({
                    "source": "creator_snapshots",
                    "code": "CREATOR_SNAPSHOT_LOCATOR_CONFLICT",
                    "stable_id": snapshot_id,
                })
                continue
            creator_snapshot_locators.append(self._locator(
                "creator_snapshots", snapshot_id, "workbook:CreatorSnapshots"
            ))

        video_snapshots = [
            row for row in rows["VideoSnapshots"]
            if str(row.get("creator_id") or "") == creator_id
            or str(row.get("snapshot_id") or "") in snapshot_ids
        ]
        direct_video_snapshots = sum(
            1 for row in video_snapshots
            if str(row.get("creator_id") or "") == creator_id
        )
        video_snapshot_locators: list[dict[str, str]] = []
        video_snapshot_id_counts: dict[str, int] = {}
        for row in rows["VideoSnapshots"]:
            stable_id = str(row.get("video_snapshot_id") or "")
            if stable_id:
                video_snapshot_id_counts[stable_id] = (
                    video_snapshot_id_counts.get(stable_id, 0) + 1
                )
        for row in video_snapshots:
            video_snapshot_id = str(row.get("video_snapshot_id") or "")
            row_creator_id = str(row.get("creator_id") or "")
            row_snapshot_id = str(row.get("snapshot_id") or "")
            conflict = (
                (row_creator_id and row_creator_id != creator_id)
                or video_snapshot_id_counts.get(video_snapshot_id) != 1
                or (
                    row_snapshot_id in snapshot_ids
                    and snapshot_id_owners.get(row_snapshot_id) != {creator_id}
                )
                or (
                    row_creator_id == creator_id
                    and row_snapshot_id
                    and snapshot_id_owners.get(row_snapshot_id)
                    and snapshot_id_owners.get(row_snapshot_id) != {creator_id}
                )
            )
            if conflict or not video_snapshot_id:
                safety_blocks.append({
                    "source": "video_snapshots",
                    "code": "VIDEO_SNAPSHOT_OWNERSHIP_CONFLICT",
                    "stable_id": video_snapshot_id,
                })
                continue
            video_snapshot_locators.append(self._locator(
                "video_snapshots", video_snapshot_id, "workbook:VideoSnapshots"
            ))
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

        campaign_relation_locators: list[dict[str, str]] = []
        campaign_relation_id_counts: dict[str, int] = {}
        for row in rows["CampaignCreators"]:
            relation_id = str(row.get("id") or "")
            if relation_id:
                campaign_relation_id_counts[relation_id] = (
                    campaign_relation_id_counts.get(relation_id, 0) + 1
                )
        for row in campaign_relations:
            relation_id = str(row.get("id") or "")
            if not relation_id or campaign_relation_id_counts.get(relation_id) != 1:
                safety_blocks.append({
                    "source": "campaign_creators",
                    "code": "CAMPAIGN_RELATION_LOCATOR_MISSING",
                    "stable_id": "",
                })
                continue
            campaign_relation_locators.append(self._locator(
                "campaign_creators", relation_id, "workbook:CampaignCreators"
            ))

        cooperation_locators = [
            self._locator(
                "cooperations",
                str(row.get("cooperation_id") or ""),
                "workbook:Cooperations",
            )
            for row in cooperations
            if str(row.get("cooperation_id") or "")
        ]
        followup_locators: list[dict[str, str]] = []
        followup_id_counts: dict[str, int] = {}
        for row in rows["FollowUpLogs"]:
            followup_id = str(row.get("follow_up_id") or "")
            if followup_id:
                followup_id_counts[followup_id] = followup_id_counts.get(followup_id, 0) + 1
        for row in followups:
            followup_id = str(row.get("follow_up_id") or "")
            if not followup_id or followup_id_counts.get(followup_id) != 1:
                safety_blocks.append({
                    "source": "follow_up_logs",
                    "code": "FOLLOWUP_LOCATOR_MISSING",
                    "stable_id": "",
                })
                continue
            followup_locators.append(self._locator(
                "follow_up_logs", followup_id, "workbook:FollowUpLogs"
            ))

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
            "safety_blocks": safety_blocks,
            "account_ids": sorted(account_ids),
            "account_uids": sorted(account_uids),
            "snapshot_ids": sorted(snapshot_ids),
            "account_id_owners": {
                key: sorted(value) for key, value in account_id_owners.items()
            },
            "account_uid_owners": {
                key: sorted(value) for key, value in account_uid_owners.items()
            },
            "snapshot_id_owners": {
                key: sorted(value) for key, value in snapshot_id_owners.items()
            },
            "known_creator_ids": sorted(known_creator_ids),
            "resource_locators": {
                "creators": [self._locator(
                    "creators", creator_id, "workbook:Creators:creator_id"
                )],
                "creator_accounts": account_locators,
                "videos": [self._locator(
                    "videos", creator_id, "workbook:Videos:creator_id"
                )] if self._matching(rows["Videos"], "creator_id", creator_id) else [],
                "insights": [self._locator(
                    "insights", creator_id, "workbook:Insights:creator_id"
                )] if self._matching(rows["Insights"], "creator_id", creator_id) else [],
                "analysis_data": [self._locator(
                    "analysis_data", creator_id, "workbook:_AnalysisData:creator_id"
                )] if analysis_rows else [],
                "creator_snapshots": creator_snapshot_locators,
                "video_snapshots": video_snapshot_locators,
                "cooperations": cooperation_locators,
                "campaign_creators": campaign_relation_locators,
                "follow_up_logs": followup_locators,
            },
            "structural_ids": {
                "account_ids": sorted(account_ids),
                "account_uids": sorted(account_uids),
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
        account_id_owners: dict[str, list[str]],
        account_uid_owners: dict[str, list[str]],
        snapshot_id_owners: dict[str, list[str]],
        known_creator_ids: set[str],
    ) -> dict[str, Any]:
        task_locators, unmapped_task_ids, task_blocks = self._matching_task_artifacts(
            creator_id,
            account_ids,
            snapshot_ids,
            account_id_owners,
            snapshot_id_owners,
        )
        protection_locators, protection_blocks = self._matching_protection_entries(
            creator_id, account_uids, account_uid_owners
        )
        legacy_locators, legacy_blocks = self._matching_legacy_sources(
            creator_id, account_uids, account_uid_owners, known_creator_ids
        )
        task_ids = {str(item["stable_id"]) for item in task_locators}
        protection_uids = {str(item["stable_id"]) for item in protection_locators}
        legacy_ids = {str(item["stable_id"]) for item in legacy_locators}
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
                "data_protection_uids": sorted(protection_uids),
                "legacy_source_ids": sorted(legacy_ids),
            },
            "resource_locators": {
                "task_artifacts": task_locators,
                "data_protection": protection_locators,
                "legacy_sources": legacy_locators,
            },
            "safety_blocks": [*task_blocks, *protection_blocks, *legacy_blocks],
        }

    def _matching_task_artifacts(
        self,
        creator_id: str,
        account_ids: set[str],
        snapshot_ids: set[str],
        account_id_owners: dict[str, list[str]],
        snapshot_id_owners: dict[str, list[str]],
    ) -> tuple[list[dict[str, str]], set[str], list[dict[str, str]]]:
        if self._tasks_dir is None or not self._tasks_dir.exists():
            return [], set(), []
        locators: list[dict[str, str]] = []
        unmapped: set[str] = set()
        blocks: list[dict[str, str]] = []
        for root in self._tasks_dir.iterdir():
            if not root.is_dir() or not _TASK_ID_PATTERN.fullmatch(root.name):
                continue
            if root.is_symlink():
                blocks.append({
                    "source": "task_artifacts",
                    "code": "TASK_ARTIFACT_SYMLINK",
                    "stable_id": root.name,
                })
                continue
            metadata_path = root / "task.json"
            if not metadata_path.is_file():
                raise RuntimeError("任务元数据缺失。")
            if metadata_path.is_symlink():
                unmapped.add(root.name)
                blocks.append({
                    "source": "task_artifacts",
                    "code": "TASK_ARTIFACT_SYMLINK",
                    "stable_id": root.name,
                })
                continue
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
            has_ownership_fields = bool(
                analysis_id
                or direct_creator_id
                or linked_creators
                or linked_account_ids
                or task_snapshot_id
            )
            if not has_ownership_fields:
                unmapped.add(root.name)
                continue

            owners = set(linked_creators)
            owners.update(value for value in (analysis_id, direct_creator_id) if value)
            unresolved_reference = False
            for account_id in linked_account_ids:
                mapped = set(account_id_owners.get(account_id, []))
                if not mapped:
                    unresolved_reference = True
                owners.update(mapped)
            if task_snapshot_id:
                mapped = set(snapshot_id_owners.get(task_snapshot_id, []))
                if not mapped:
                    unresolved_reference = True
                owners.update(mapped)
            references_target = (
                creator_id in owners
                or bool(account_ids & linked_account_ids)
                or task_snapshot_id in snapshot_ids
            )
            if not references_target:
                continue
            ownership = "exclusive"
            if unresolved_reference:
                ownership = "unresolved"
            elif owners != {creator_id}:
                ownership = "shared"
            locator = self._locator(
                "task_artifacts", root.name, "filesystem:task_directory"
            )
            locator["ownership"] = ownership
            locators.append(locator)
            if ownership != "exclusive":
                blocks.append({
                    "source": "task_artifacts",
                    "code": (
                        "SHARED_TASK_CREATOR_REFERENCE"
                        if ownership == "shared"
                        else "UNRESOLVED_TASK_OWNERSHIP"
                    ),
                    "stable_id": root.name,
                })
        return locators, unmapped, blocks

    def _matching_protection_entries(
        self,
        creator_id: str,
        account_uids: set[str],
        account_uid_owners: dict[str, list[str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        path = self._data_protection_file
        if path is None:
            return [], []
        backup = json_backup_path(path)
        if not path.exists() and not backup.exists():
            return [], []
        data, source = load_json_with_backup(path)
        if source is None or not isinstance(data, dict):
            raise RuntimeError("数据保护文件无法读取。")
        locators: list[dict[str, str]] = []
        blocks: list[dict[str, str]] = []
        if source != path:
            blocks.append({
                "source": "data_protection",
                "code": "DATA_PROTECTION_PRIMARY_UNAVAILABLE",
                "stable_id": "primary",
            })
        for account_uid in sorted(account_uids & {str(key) for key in data if str(key)}):
            owners = set(account_uid_owners.get(account_uid, []))
            locator = self._locator(
                "data_protection", account_uid, "json:data_protection"
            )
            locator["ownership"] = "exclusive" if owners == {creator_id} else "shared"
            locators.append(locator)
            if owners != {creator_id}:
                blocks.append({
                    "source": "data_protection",
                    "code": "SHARED_DATA_PROTECTION_UID",
                    "stable_id": account_uid,
                })
        return locators, blocks

    def _matching_legacy_sources(
        self,
        creator_id: str,
        account_uids: set[str],
        account_uid_owners: dict[str, list[str]],
        known_creator_ids: set[str],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        locators: list[dict[str, str]] = []
        blocks: list[dict[str, str]] = []
        directory = self._legacy_analysis_dir
        if directory is not None and directory.exists():
            for path in directory.glob("analysis_task_*.json"):
                if path.is_symlink():
                    blocks.append({
                        "source": "legacy_sources",
                        "code": "UNRELIABLE_LEGACY_IDENTITY",
                        "stable_id": path.name,
                    })
                    continue
                data, source = load_json_with_backup(path)
                if source is None or not isinstance(data, dict):
                    raise RuntimeError("Legacy analysis 文件无法读取。")
                if source != path:
                    blocks.append({
                        "source": "legacy_sources",
                        "code": "LEGACY_PRIMARY_UNAVAILABLE",
                        "stable_id": path.name,
                    })
                owners, reliable = self._legacy_owners(
                    data, account_uid_owners, known_creator_ids
                )
                if creator_id in owners:
                    ownership = "exclusive" if owners == {creator_id} and reliable else "shared"
                    locator = self._locator(
                        "legacy_sources", path.name, "filesystem:legacy_analysis"
                    )
                    locator["ownership"] = ownership
                    locators.append(locator)
                    if ownership != "exclusive":
                        blocks.append({
                            "source": "legacy_sources",
                            "code": "SHARED_LEGACY_CREATOR_REFERENCE",
                            "stable_id": path.name,
                        })
                elif not reliable:
                    stable_id = f"unreliable:{path.name}"
                    locator = self._locator(
                        "legacy_sources", stable_id, "filesystem:legacy_analysis"
                    )
                    locator["ownership"] = "unresolved"
                    locators.append(locator)
                    blocks.append({
                        "source": "legacy_sources",
                        "code": "UNRELIABLE_LEGACY_IDENTITY",
                        "stable_id": stable_id,
                    })
        path = self._legacy_library_file
        if path is not None:
            backup = json_backup_path(path)
            if path.exists() or backup.exists():
                data, source = load_json_with_backup(path)
                if source is None or not isinstance(data, dict):
                    raise RuntimeError("Legacy Creator Library 文件无法读取。")
                if source != path:
                    blocks.append({
                        "source": "legacy_sources",
                        "code": "LEGACY_PRIMARY_UNAVAILABLE",
                        "stable_id": path.name,
                    })
                records = data.get("records")
                if not isinstance(records, dict):
                    raise RuntimeError("Legacy Creator Library 格式无效。")
                for key, value in records.items():
                    record = value if isinstance(value, dict) else {}
                    owners, reliable = self._legacy_owners(
                        record, account_uid_owners, known_creator_ids, record_key=str(key)
                    )
                    stable_id = f"library:{key}"
                    if creator_id in owners:
                        ownership = "exclusive" if owners == {creator_id} and reliable else "shared"
                        locator = self._locator(
                            "legacy_sources", stable_id, "json:legacy_library"
                        )
                        locator["ownership"] = ownership
                        locators.append(locator)
                        if ownership != "exclusive":
                            blocks.append({
                                "source": "legacy_sources",
                                "code": "SHARED_LEGACY_CREATOR_REFERENCE",
                                "stable_id": stable_id,
                            })
                    elif not reliable:
                        locator = self._locator(
                            "legacy_sources", f"unreliable:{stable_id}", "json:legacy_library"
                        )
                        locator["ownership"] = "unresolved"
                        locators.append(locator)
                        blocks.append({
                            "source": "legacy_sources",
                            "code": "UNRELIABLE_LEGACY_IDENTITY",
                            "stable_id": stable_id,
                        })
        return locators, blocks

    @staticmethod
    def _legacy_owners(
        data: dict[str, Any],
        account_uid_owners: dict[str, list[str]],
        known_creator_ids: set[str],
        *,
        record_key: str = "",
    ) -> tuple[set[str], bool]:
        owners: set[str] = set()
        for value in (data.get("creator_id"), data.get("analysis_id"), record_key):
            identity = str(value or "")
            if identity in known_creator_ids:
                owners.add(identity)
        account_uid = str(data.get("account_uid") or "")
        if account_uid:
            owners.update(account_uid_owners.get(account_uid, []))
        reliable = bool(owners) and (not account_uid or bool(account_uid_owners.get(account_uid)))
        return owners, reliable

    @staticmethod
    def _locator(resource_type: str, stable_id: str, storage_scope: str) -> dict[str, str]:
        return {
            "resource_type": resource_type,
            "stable_id": stable_id,
            "storage_scope": storage_scope,
        }

    @staticmethod
    def _matching(
        rows: list[dict[str, Any]], key: str, expected: str
    ) -> list[dict[str, Any]]:
        return [row for row in rows if str(row.get(key) or "") == expected]
