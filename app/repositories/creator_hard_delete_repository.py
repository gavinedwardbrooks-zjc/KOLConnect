from __future__ import annotations

"""Exact mutation boundary for scanner-approved Creator hard-delete plans."""

import json
import re
from pathlib import Path
from typing import Any

from data_repository_base import ExcelDataRepository
from excel_workbook_store import ExcelWorkbookStore
from staged_delete_transaction import StagedDeleteTransaction


_TASK_ID_PATTERN = re.compile(r"^task_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
_WORKBOOK_MUTATIONS = (
    ("creator_accounts", "CreatorAccounts", "account_id"),
    ("videos", "Videos", "creator_id"),
    ("insights", "Insights", "creator_id"),
    ("analysis_data", "_AnalysisData", "creator_id"),
    ("video_snapshots", "VideoSnapshots", "video_snapshot_id"),
    ("creator_snapshots", "CreatorSnapshots", "snapshot_id"),
    ("campaign_creators", "CampaignCreators", "id"),
    ("follow_up_logs", "FollowUpLogs", "follow_up_id"),
    ("creators", "Creators", "creator_id"),
)
_WORKBOOK_SCOPES = {
    "creator_accounts": "workbook:CreatorAccounts",
    "videos": "workbook:Videos:creator_id",
    "insights": "workbook:Insights:creator_id",
    "analysis_data": "workbook:_AnalysisData:creator_id",
    "video_snapshots": "workbook:VideoSnapshots",
    "creator_snapshots": "workbook:CreatorSnapshots",
    "campaign_creators": "workbook:CampaignCreators",
    "follow_up_logs": "workbook:FollowUpLogs",
    "creators": "workbook:Creators:creator_id",
}
_PROTECTED_SHEETS = ("Products", "Campaigns", "Agencies")
_GROUPED_WORKBOOK_RESOURCES = frozenset({"videos", "insights", "analysis_data"})


class UnsafeCreatorDeletePlan(RuntimeError):
    pass


class CreatorHardDeleteRepository(ExcelDataRepository):
    """Apply exact plan locators without making retention or ownership decisions."""

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

    def transaction_inputs(self, plan: dict[str, Any]) -> dict[str, list[Path]]:
        artifacts: list[Path] = []
        json_paths: list[Path] = []
        seen_json: set[Path] = set()
        for locator in self._validated_locators(plan):
            resource = locator["resource_type"]
            stable_id = locator["stable_id"]
            scope = locator["storage_scope"]
            if resource in _WORKBOOK_SCOPES:
                continue
            if resource == "task_artifacts" and scope == "filesystem:task_directory":
                if self._tasks_dir is None or not _TASK_ID_PATTERN.fullmatch(stable_id):
                    raise UnsafeCreatorDeletePlan("Task artifact locator is unsafe.")
                artifacts.append(self._child_path(self._tasks_dir, stable_id))
            elif resource == "data_protection" and scope == "json:data_protection":
                if self._data_protection_file is None:
                    raise UnsafeCreatorDeletePlan("Data protection store is unavailable.")
                if self._data_protection_file.is_symlink():
                    raise UnsafeCreatorDeletePlan("Data protection store is unsafe.")
                seen_json.add(self._data_protection_file)
            elif resource == "legacy_sources" and scope == "filesystem:legacy_analysis":
                if self._legacy_analysis_dir is None or Path(stable_id).name != stable_id:
                    raise UnsafeCreatorDeletePlan("Legacy artifact locator is unsafe.")
                artifacts.append(self._child_path(self._legacy_analysis_dir, stable_id))
            elif resource == "legacy_sources" and scope == "json:legacy_library":
                if self._legacy_library_file is None or not stable_id.startswith("library:"):
                    raise UnsafeCreatorDeletePlan("Legacy JSON locator is unsafe.")
                if self._legacy_library_file.is_symlink():
                    raise UnsafeCreatorDeletePlan("Legacy JSON store is unsafe.")
                seen_json.add(self._legacy_library_file)
            else:
                raise UnsafeCreatorDeletePlan("Delete plan contains an unsupported locator.")
        json_paths.extend(sorted(seen_json, key=str))
        return {"artifacts": artifacts, "json_paths": json_paths}

    def capture_protected_state(
        self, creator_id: str, plan: dict[str, Any]
    ) -> dict[str, Any]:
        grouped = self._group_locators(plan)
        with self.store.read_only_workbook() as workbook:
            expected_workbook = {
                name: self.rows(workbook[name]) for name in _PROTECTED_SHEETS
            }
            for resource, sheet_name, key in _WORKBOOK_MUTATIONS:
                stable_ids = {
                    item["stable_id"] for item in grouped.get(resource, [])
                }
                expected_workbook[sheet_name] = [
                    row for row in self.rows(workbook[sheet_name])
                    if str(row.get(key) or "") not in stable_ids
                ]
        protected: dict[str, Any] = {"workbook": expected_workbook}
        protection = grouped.get("data_protection", [])
        if protection:
            data = self._read_object(
                self._require_file(self._data_protection_file, "Data protection")
            )
            for locator in protection:
                data.pop(locator["stable_id"], None)
            protected["data_protection"] = data
        legacy = [
            item for item in grouped.get("legacy_sources", [])
            if item["storage_scope"] == "json:legacy_library"
        ]
        if legacy:
            data = self._read_object(
                self._require_file(self._legacy_library_file, "Legacy Creator Library")
            )
            records = data.get("records")
            if not isinstance(records, dict):
                raise UnsafeCreatorDeletePlan("Legacy Creator Library is invalid.")
            for locator in legacy:
                records.pop(locator["stable_id"].split(":", 1)[1], None)
            protected["legacy_library"] = data
        return protected

    def apply_json_deletes(
        self,
        transaction: StagedDeleteTransaction,
        plan: dict[str, Any],
    ) -> dict[str, int]:
        grouped = self._group_locators(plan)
        deleted: dict[str, int] = {}
        protection = grouped.get("data_protection", [])
        if protection:
            path = self._require_file(self._data_protection_file, "Data protection")
            data = self._read_object(path)
            for locator in protection:
                stable_id = locator["stable_id"]
                if stable_id not in data:
                    raise UnsafeCreatorDeletePlan("Data protection locator changed.")
                del data[stable_id]
            transaction.write_json(path, data)
            deleted["data_protection"] = len(protection)

        legacy = [
            item for item in grouped.get("legacy_sources", [])
            if item["storage_scope"] == "json:legacy_library"
        ]
        if legacy:
            path = self._require_file(self._legacy_library_file, "Legacy Creator Library")
            data = self._read_object(path)
            records = data.get("records")
            if not isinstance(records, dict):
                raise UnsafeCreatorDeletePlan("Legacy Creator Library is invalid.")
            for locator in legacy:
                key = locator["stable_id"].split(":", 1)[1]
                if key not in records:
                    raise UnsafeCreatorDeletePlan("Legacy locator changed.")
                del records[key]
            transaction.write_json(path, data)
            deleted["legacy_sources"] = len(legacy)
        return deleted

    def delete_workbook_resources(
        self,
        creator_id: str,
        plan: dict[str, Any],
    ) -> dict[str, int]:
        grouped = self._group_locators(plan)
        expected = {
            item["source"]: int(item["count"])
            for item in plan.get("decisions", [])
            if item.get("classification") == "DELETE"
        }
        deleted: dict[str, int] = {}
        with self.store.workbook(write=True) as workbook:
            for resource, sheet_name, key in _WORKBOOK_MUTATIONS:
                locators = grouped.get(resource, [])
                if not locators:
                    continue
                if resource == "creators" and {item["stable_id"] for item in locators} != {creator_id}:
                    raise UnsafeCreatorDeletePlan("Creator root locator changed.")
                stable_ids = {item["stable_id"] for item in locators}
                count = self._delete_matching_rows(workbook[sheet_name], key, stable_ids)
                if count != expected.get(resource, 0):
                    raise UnsafeCreatorDeletePlan(f"{resource} locator count changed.")
                deleted[resource] = count
        return deleted

    def verify_delete(
        self,
        creator_id: str,
        plan: dict[str, Any],
        protected_state: dict[str, Any],
        transaction: StagedDeleteTransaction,
    ) -> None:
        grouped = self._group_locators(plan)
        with self.store.read_only_workbook() as workbook:
            for sheet_name, expected_rows in protected_state["workbook"].items():
                if self.rows(workbook[sheet_name]) != expected_rows:
                    raise UnsafeCreatorDeletePlan(
                        f"Protected workbook rows changed in {sheet_name}."
                    )

        self._verify_json_absent(grouped)
        if "data_protection" in protected_state:
            current = self._read_object(
                self._require_file(self._data_protection_file, "Data protection")
            )
            if current != protected_state["data_protection"]:
                raise UnsafeCreatorDeletePlan("Unrelated data protection entries changed.")
        if "legacy_library" in protected_state:
            current = self._read_object(
                self._require_file(self._legacy_library_file, "Legacy Creator Library")
            )
            if current != protected_state["legacy_library"]:
                raise UnsafeCreatorDeletePlan("Unrelated legacy records changed.")
        for move in transaction.load_manifest().get("quarantine_moves", []):
            if Path(move["original"]).exists() or not Path(move["quarantine"]).exists():
                raise UnsafeCreatorDeletePlan("Artifact quarantine verification failed.")

    def _validated_locators(self, plan: dict[str, Any]) -> list[dict[str, str]]:
        if plan.get("blocked"):
            raise UnsafeCreatorDeletePlan("Delete plan is blocked.")
        locators = list(plan.get("delete_locators", []))
        if not locators:
            raise UnsafeCreatorDeletePlan("Delete plan has no exact locators.")
        decisions = {
            str(item.get("source") or ""): int(item.get("count") or 0)
            for item in plan.get("decisions", [])
            if item.get("classification") == "DELETE"
        }
        by_resource: dict[str, list[dict[str, str]]] = {}
        for locator in locators:
            resource = str(locator.get("resource_type") or "")
            stable_id = str(locator.get("stable_id") or "")
            scope = str(locator.get("storage_scope") or "")
            if not resource or not stable_id or not scope:
                raise UnsafeCreatorDeletePlan("Delete plan locator is incomplete.")
            expected_scope = _WORKBOOK_SCOPES.get(resource)
            if expected_scope is not None and scope != expected_scope:
                raise UnsafeCreatorDeletePlan("Workbook locator scope is invalid.")
            if resource not in decisions:
                raise UnsafeCreatorDeletePlan("Delete locator has no policy decision.")
            by_resource.setdefault(resource, []).append(locator)
        for resource, expected_count in decisions.items():
            resource_locators = by_resource.get(resource, [])
            if expected_count and not resource_locators:
                raise UnsafeCreatorDeletePlan("Delete plan is missing exact locators.")
            stable_ids = {item["stable_id"] for item in resource_locators}
            if len(stable_ids) != len(resource_locators):
                raise UnsafeCreatorDeletePlan("Delete plan contains duplicate locators.")
            if (
                resource not in _GROUPED_WORKBOOK_RESOURCES
                and len(resource_locators) != expected_count
            ):
                raise UnsafeCreatorDeletePlan("Delete locator coverage is incomplete.")
        return locators

    def _group_locators(self, plan: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = {}
        for locator in self._validated_locators(plan):
            grouped.setdefault(locator["resource_type"], []).append(locator)
        return grouped

    def _verify_json_absent(self, grouped: dict[str, list[dict[str, str]]]) -> None:
        protection = grouped.get("data_protection", [])
        if protection:
            data = self._read_object(self._require_file(self._data_protection_file, "Data protection"))
            if any(item["stable_id"] in data for item in protection):
                raise UnsafeCreatorDeletePlan("Data protection delete verification failed.")
        legacy = [
            item for item in grouped.get("legacy_sources", [])
            if item["storage_scope"] == "json:legacy_library"
        ]
        if legacy:
            data = self._read_object(self._require_file(self._legacy_library_file, "Legacy Creator Library"))
            records = data.get("records")
            if not isinstance(records, dict) or any(
                item["stable_id"].split(":", 1)[1] in records for item in legacy
            ):
                raise UnsafeCreatorDeletePlan("Legacy delete verification failed.")

    @staticmethod
    def _delete_matching_rows(sheet, key: str, stable_ids: set[str]) -> int:
        headers = [str(cell.value or "") for cell in sheet[1]]
        key_index = headers.index(key) + 1
        rows = [
            row_index for row_index in range(2, sheet.max_row + 1)
            if str(sheet.cell(row_index, key_index).value or "") in stable_ids
        ]
        for row_index in reversed(rows):
            sheet.delete_rows(row_index, 1)
        return len(rows)

    @staticmethod
    def _child_path(parent: Path, name: str) -> Path:
        if parent.is_symlink():
            raise UnsafeCreatorDeletePlan("Artifact storage root is unsafe.")
        candidate = parent / name
        if candidate.parent != parent:
            raise UnsafeCreatorDeletePlan("Artifact path escapes its storage root.")
        return candidate

    @staticmethod
    def _require_file(path: Path | None, label: str) -> Path:
        if path is None or not path.is_file() or path.is_symlink():
            raise UnsafeCreatorDeletePlan(f"{label} store is unavailable.")
        return path

    @staticmethod
    def _read_object(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UnsafeCreatorDeletePlan("JSON store cannot be read safely.") from exc
        if not isinstance(data, dict):
            raise UnsafeCreatorDeletePlan("JSON store is invalid.")
        return data
