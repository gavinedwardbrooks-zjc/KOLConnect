from __future__ import annotations

"""Creator Library storage contract backed by a cloud-syncable Excel workbook.

The public methods are intentionally storage-neutral. A future Supabase or
PostgreSQL adapter can keep this contract without changing the HTTP API or UI.
"""

import json
import hashlib
import os
import re
import shutil
import threading
import uuid
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app_logging import log_event
from runtime_paths import load_json_with_backup


CREATOR_LIBRARY_STATUSES = {
    "discovered",
    "contacted",
    "negotiating",
    "cooperating",
    "completed",
    "rejected",
}

_TASK_ID_PATTERN = re.compile(r"^task_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
CREATOR_LIBRARY_SCHEMA_VERSION = "1.3"
_CREATORS_HEADERS = [
    "creator_id", "name", "platform", "profile_url", "country", "language",
    "content_category", "followers", "insight_level", "status", "created_at", "tags", "updated_at",
]
_VIDEOS_HEADERS = ["creator_id", "video_url", "views", "likes", "comments", "captured_at"]
_INSIGHTS_HEADERS = ["creator_id", "average_views", "median_views", "stability", "risks", "recommendation"]
_CREATOR_SNAPSHOTS_HEADERS = [
    "snapshot_id", "creator_id", "platform", "account_uid", "followers", "average_views",
    "median_views", "video_count", "creator_score", "insight_level", "captured_at", "source",
]
_VIDEO_SNAPSHOTS_HEADERS = [
    "video_snapshot_id", "snapshot_id", "creator_id", "video_id", "video_url", "platform",
    "views", "likes", "comments", "captured_at",
]
_COOPERATIONS_HEADERS = [
    "cooperation_id", "creator_id", "campaign", "platform", "contact_date", "price",
    "published_count", "total_views", "average_views", "roi", "result", "note", "created_at",
]
# Hidden technical metadata preserves the full snapshot and review-task handoff.
_ANALYSIS_METADATA_HEADERS = ["creator_id", "task_id", "account_uid", "status_updated_at", "analysis_json", "source"]
_WORKBOOK_METADATA_HEADERS = ["schema_version", "last_update_time"]
_WORKBOOK_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _synchronized(method):
    """Serialize workbook access within the local desktop process."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with _WORKBOOK_LOCK:
            return method(self, *args, **kwargs)
    return wrapped


class CreatorRepository:
    """Excel adapter for Creator Library data, suitable for WPS/OneDrive cloud folders."""

    def __init__(
        self,
        workbook_path: Path,
        legacy_analysis_dir: Path | None = None,
        legacy_library_file: Path | None = None,
    ) -> None:
        self.workbook_path = workbook_path
        self.legacy_analysis_dir = legacy_analysis_dir
        self.legacy_library_file = legacy_library_file

    @_synchronized
    def saveCreator(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Save the latest creator view and append an immutable analysis snapshot."""
        self._validate_analysis(analysis)
        workbook = self._load_workbook()
        requested_creator_id = str(analysis["analysis_id"])
        creator_id = self._creator_id_for_account_uid(workbook, str(analysis.get("account_uid") or "")) or requested_creator_id
        existing = self._creator_row(workbook["Creators"], creator_id)
        is_new_creator = not bool(existing)
        status = str(existing.get("status") or "discovered") if existing else "discovered"
        existing_metadata = self._metadata_row(workbook["_AnalysisData"], creator_id)
        status_updated_at = existing_metadata.get("status_updated_at", "")
        creator_values = self._creator_values(analysis, status, creator_id)
        if existing:
            # Extension imports should never erase optional data already curated in Excel.
            for field in ("country", "language", "tags"):
                if not creator_values.get(field) and existing.get(field):
                    creator_values[field] = existing[field]
            creator_values["created_at"] = existing.get("created_at") or creator_values["created_at"]
        self._upsert_row(workbook["Creators"], "creator_id", creator_id, creator_values)
        self._replace_video_rows(workbook["Videos"], creator_id, analysis.get("videos"))
        self._upsert_row(
            workbook["Insights"],
            "creator_id",
            creator_id,
            self._insight_values(analysis, creator_id),
        )
        self._upsert_row(
            workbook["_AnalysisData"],
            "creator_id",
            creator_id,
            {
                "creator_id": creator_id,
                "task_id": str(analysis.get("task_id") or ""),
                "account_uid": str(analysis.get("account_uid") or ""),
                "source": str(analysis.get("source") or ""),
                "status_updated_at": status_updated_at,
                "analysis_json": json.dumps(analysis, ensure_ascii=False),
            },
        )
        snapshot = self.createSnapshot(analysis, creator_id, workbook)
        self._save_workbook(workbook)
        return {
            **analysis,
            "creator_id": creator_id,
            "snapshot_id": snapshot["snapshot_id"],
            "is_new_creator": is_new_creator,
        }

    @_synchronized
    def createSnapshot(self, analysis: dict[str, Any], creator_id: str, workbook=None) -> dict[str, Any]:
        """Append one time-stamped analysis without replacing earlier snapshots."""
        should_save = workbook is None
        workbook = workbook or self._load_workbook()
        snapshot_id = f"snapshot_{analysis['task_id']}"
        creator = analysis.get("creator") if isinstance(analysis.get("creator"), dict) else {}
        metrics = analysis.get("video_analysis") if isinstance(analysis.get("video_analysis"), dict) else {}
        insight = analysis.get("creator_insight") if isinstance(analysis.get("creator_insight"), dict) else {}
        captured_at = str(analysis.get("imported_at") or _utc_now())
        snapshot = {
            "snapshot_id": snapshot_id,
            "creator_id": creator_id,
            "platform": str(creator.get("platform") or ""),
            "account_uid": str(analysis.get("account_uid") or ""),
            "followers": str(creator.get("followers") or ""),
            "average_views": metrics.get("average_views", ""),
            "median_views": metrics.get("median_views", ""),
            "video_count": len(analysis.get("videos") if isinstance(analysis.get("videos"), list) else []),
            "creator_score": insight.get("creator_score", insight.get("rule_score", "")),
            "insight_level": str(insight.get("level") or insight.get("grade") or "insufficient"),
            "captured_at": captured_at,
            "source": str(analysis.get("source") or ""),
        }
        self._upsert_row(workbook["CreatorSnapshots"], "snapshot_id", snapshot_id, snapshot)
        self._replace_video_snapshot_rows(workbook["VideoSnapshots"], snapshot_id, creator_id, analysis.get("videos"), captured_at)
        if should_save:
            self._save_workbook(workbook)
        return snapshot

    @_synchronized
    def getCreatorSnapshots(self, creator_id: str) -> list[dict[str, Any]]:
        workbook = self._load_workbook()
        return self._snapshots_from_workbook(workbook, creator_id)

    @_synchronized
    def getCreatorTrend(self, creator_id: str) -> dict[str, Any]:
        """Return latest/previous snapshots, field deltas, and data freshness."""
        workbook = self._load_workbook()
        if not self._creator_row(workbook["Creators"], str(creator_id or "")):
            raise ValueError("未找到达人分析记录。")
        snapshots = self._snapshots_from_workbook(workbook, creator_id)
        return {
            "creator_id": str(creator_id or ""),
            "snapshots": snapshots,
            **self._trend_from_snapshots(snapshots),
        }

    @_synchronized
    def getCreators(self) -> list[dict[str, Any]]:
        """Return concise Creator Library records from the Excel workbook."""
        workbook = self._load_workbook()
        insights = {row["creator_id"]: row for row in self._rows(workbook["Insights"]) if row.get("creator_id")}
        metadata = {row["creator_id"]: row for row in self._rows(workbook["_AnalysisData"]) if row.get("creator_id")}
        records = []
        for creator in self._rows(workbook["Creators"]):
            creator_id = str(creator.get("creator_id") or "")
            if not creator_id:
                continue
            insight = insights.get(creator_id, {})
            meta = metadata.get(creator_id, {})
            snapshots = self._snapshots_from_workbook(workbook, creator_id)
            snapshot = snapshots[0] if snapshots else {}
            trend = self._trend_from_snapshots(snapshots)
            records.append({
                "analysis_id": creator_id,
                "creator_id": creator_id,
                "task_id": str(meta.get("task_id") or ""),
                "account_uid": str(meta.get("account_uid") or ""),
                "creator_name": str(creator.get("name") or ""),
                "platform": str(creator.get("platform") or ""),
                "profile_url": str(creator.get("profile_url") or ""),
                "followers": str(snapshot.get("followers") or creator.get("followers") or ""),
                "content_category": str(creator.get("content_category") or ""),
                "country": str(creator.get("country") or ""),
                "language": str(creator.get("language") or ""),
                "tags": str(creator.get("tags") or ""),
                "insight_level": str(snapshot.get("insight_level") or creator.get("insight_level") or "insufficient"),
                "average_views": snapshot.get("average_views", insight.get("average_views")),
                "median_views": snapshot.get("median_views", insight.get("median_views")),
                "analysis_time": str(creator.get("created_at") or ""),
                "last_analysis_time": str(snapshot.get("captured_at") or creator.get("created_at") or ""),
                "data_updated_at": str(creator.get("updated_at") or creator.get("created_at") or ""),
                "source": str(snapshot.get("source") or meta.get("source") or "excel"),
                "status": self._status_value(creator.get("status")),
                "status_updated_at": str(meta.get("status_updated_at") or ""),
                "trend": trend,
            })
        records.sort(key=lambda item: item["analysis_time"], reverse=True)
        return records

    @_synchronized
    def getCreatorDetail(self, analysis_id: str) -> dict[str, Any]:
        """Return one full analysis snapshot reconstructed from the workbook."""
        creator_id = str(analysis_id or "").strip()
        workbook = self._load_workbook()
        creator = self._creator_row(workbook["Creators"], creator_id)
        if not creator:
            raise ValueError("未找到达人分析记录。")
        metadata = self._metadata_row(workbook["_AnalysisData"], creator_id)
        analysis = self._decode_analysis(metadata.get("analysis_json"))
        if not analysis:
            analysis = self._rebuild_analysis(workbook, creator, metadata)
        record = next((item for item in self.getCreators() if item["analysis_id"] == creator_id), None)
        if not record:
            raise ValueError("达人分析记录不可用。")
        snapshots = self._snapshots_from_workbook(workbook, creator_id)
        history_times = [str(item.get("captured_at") or "") for item in snapshots]
        if not history_times and creator.get("created_at"):
            history_times = [str(creator["created_at"])]
        cooperations = self.getCreatorCooperations(creator_id, workbook)
        return {
            "record": record,
            "analysis": analysis,
            "snapshots": snapshots,
            "trend": self._trend_from_snapshots(snapshots),
            "history_analysis_times": sorted(history_times, reverse=True),
            "cooperations": cooperations,
            "cooperation_statistics": self._cooperation_statistics(cooperations),
        }

    @_synchronized
    def getCreatorCooperations(self, creator_id: str, workbook=None) -> list[dict[str, Any]]:
        """Return one creator's cooperation history, latest contact first."""
        workbook = workbook or self._load_workbook()
        rows = [
            row for row in self._rows(workbook["Cooperations"])
            if str(row.get("creator_id") or "") == str(creator_id or "")
        ]
        rows.sort(key=lambda row: (str(row.get("contact_date") or ""), str(row.get("created_at") or "")), reverse=True)
        return rows

    @_synchronized
    def saveCooperation(self, creator_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append a local cooperation record and optionally update the Creator Library status."""
        if not isinstance(payload, dict):
            raise ValueError("合作记录数据无效。")
        creator_id = str(creator_id or "").strip()
        workbook = self._load_workbook()
        creator = self._creator_row(workbook["Creators"], creator_id)
        if not creator:
            raise ValueError("未找到达人分析记录。")
        now = _utc_now()
        status = str(payload.get("status") or "").strip()
        if status:
            self._upsert_row(
                workbook["Creators"],
                "creator_id",
                creator_id,
                {**creator, "status": self._status_value(status), "updated_at": now},
            )
        cooperation = {
            "cooperation_id": f"cooperation_{uuid.uuid4().hex[:12]}",
            "creator_id": creator_id,
            "campaign": str(payload.get("campaign") or "").strip(),
            "platform": str(payload.get("platform") or creator.get("platform") or "").strip(),
            "contact_date": str(payload.get("contact_date") or "").strip(),
            "price": self._optional_number(payload.get("price"), "合作价格"),
            "published_count": self._optional_number(payload.get("published_count"), "发布数量", integer=True),
            "total_views": self._optional_number(payload.get("total_views"), "总播放"),
            "average_views": self._optional_number(payload.get("average_views"), "平均播放"),
            "roi": self._optional_number(payload.get("roi"), "ROI"),
            "result": str(payload.get("result") or "").strip(),
            "note": str(payload.get("note") or "").strip(),
            "created_at": now,
        }
        self._upsert_row(workbook["Cooperations"], "cooperation_id", cooperation["cooperation_id"], cooperation)
        self._save_workbook(workbook)
        return cooperation

    @_synchronized
    def updateCreatorStatus(self, analysis_id: str, status: object) -> dict[str, str]:
        """Update only the local Creator Library status in the Excel workbook."""
        creator_id = str(analysis_id or "").strip()
        status_value = self._status_value(status)
        workbook = self._load_workbook()
        creator = self._creator_row(workbook["Creators"], creator_id)
        if not creator:
            raise ValueError("未找到达人分析记录。")
        self._upsert_row(
            workbook["Creators"],
            "creator_id",
            creator_id,
            {**creator, "status": status_value, "updated_at": _utc_now()},
        )
        metadata = self._metadata_row(workbook["_AnalysisData"], creator_id)
        self._upsert_row(
            workbook["_AnalysisData"],
            "creator_id",
            creator_id,
            {**metadata, "creator_id": creator_id, "status_updated_at": _utc_now()},
        )
        self._save_workbook(workbook)
        return {"analysis_id": creator_id, "status": status_value, "updated_at": _utc_now()}

    def _load_workbook(self):
        if not self.workbook_path.exists():
            workbook = self._new_workbook()
            self._migrate_legacy_json(workbook)
            self._save_workbook(workbook)
            log_event("Excel", f"已创建达人库文件: {self.workbook_path}")
            return workbook
        try:
            workbook = load_workbook(self.workbook_path)
        except Exception as exc:
            log_event("Excel", f"读取失败: {self.workbook_path} | {exc}")
            raise RuntimeError(f"无法读取达人库 Excel 文件：{exc}") from exc
        log_event("Excel", f"打开成功: {self.workbook_path}")
        if self._ensure_sheets(workbook):
            self._save_workbook(workbook)
        return workbook

    def _new_workbook(self):
        workbook = Workbook()
        creators = workbook.active
        creators.title = "Creators"
        self._set_headers(creators, _CREATORS_HEADERS)
        self._set_headers(workbook.create_sheet("Videos"), _VIDEOS_HEADERS)
        self._set_headers(workbook.create_sheet("Insights"), _INSIGHTS_HEADERS)
        self._set_headers(workbook.create_sheet("CreatorSnapshots"), _CREATOR_SNAPSHOTS_HEADERS)
        self._set_headers(workbook.create_sheet("VideoSnapshots"), _VIDEO_SNAPSHOTS_HEADERS)
        self._set_headers(workbook.create_sheet("Cooperations"), _COOPERATIONS_HEADERS)
        metadata = workbook.create_sheet("_AnalysisData")
        self._set_headers(metadata, _ANALYSIS_METADATA_HEADERS)
        metadata.sheet_state = "hidden"
        workbook_metadata = workbook.create_sheet("_Metadata")
        self._set_headers(workbook_metadata, _WORKBOOK_METADATA_HEADERS)
        workbook_metadata.sheet_state = "hidden"
        return workbook

    def _ensure_sheets(self, workbook) -> bool:
        sheets = {
            "Creators": _CREATORS_HEADERS,
            "Videos": _VIDEOS_HEADERS,
            "Insights": _INSIGHTS_HEADERS,
            "CreatorSnapshots": _CREATOR_SNAPSHOTS_HEADERS,
            "VideoSnapshots": _VIDEO_SNAPSHOTS_HEADERS,
            "Cooperations": _COOPERATIONS_HEADERS,
            "_AnalysisData": _ANALYSIS_METADATA_HEADERS,
            "_Metadata": _WORKBOOK_METADATA_HEADERS,
        }
        changed = False
        for name, headers in sheets.items():
            if name not in workbook.sheetnames:
                self._set_headers(workbook.create_sheet(name), headers)
                changed = True
            else:
                changed = self._set_headers(workbook[name], headers) or changed
        workbook["_AnalysisData"].sheet_state = "hidden"
        workbook["_Metadata"].sheet_state = "hidden"
        return changed

    @staticmethod
    def _set_headers(sheet, headers: list[str]) -> bool:
        existing = [cell.value for cell in sheet[1]] if sheet.max_row else []
        changed = existing != headers
        if existing != headers:
            for column, header in enumerate(headers, start=1):
                sheet.cell(1, column, header)
                sheet.cell(1, column).font = Font(bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{chr(64 + min(len(headers), 26))}{max(sheet.max_row, 1)}"
        return changed

    def _save_workbook(self, workbook) -> None:
        self.workbook_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.workbook_path.with_suffix(".tmp.xlsx")
        backup_path = self.workbook_path.with_suffix(".xlsx.bak")
        try:
            self._upsert_row(
                workbook["_Metadata"],
                "schema_version",
                CREATOR_LIBRARY_SCHEMA_VERSION,
                {"schema_version": CREATOR_LIBRARY_SCHEMA_VERSION, "last_update_time": _utc_now()},
            )
            workbook.save(temp_path)
            load_workbook(temp_path, read_only=True).close()
            if self.workbook_path.exists():
                shutil.copy2(self.workbook_path, backup_path)
            os.replace(temp_path, self.workbook_path)
            log_event("Excel", f"保存成功: {self.workbook_path}")
        except PermissionError as exc:
            log_event("Excel", f"保存失败，文件可能被占用: {self.workbook_path} | {exc}")
            raise RuntimeError("无法保存达人库 Excel 文件。请先关闭 WPS 或 Excel 中打开的该文件。") from exc
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _rows(sheet) -> list[dict[str, Any]]:
        headers = [str(cell.value or "") for cell in sheet[1]]
        rows = []
        for values in sheet.iter_rows(min_row=2, values_only=True):
            row = {headers[index]: values[index] for index in range(min(len(headers), len(values))) if headers[index]}
            if any(value not in (None, "") for value in row.values()):
                rows.append(row)
        return rows

    def _creator_row(self, sheet, creator_id: str) -> dict[str, Any]:
        return next((row for row in self._rows(sheet) if str(row.get("creator_id") or "") == creator_id), {})

    def _metadata_row(self, sheet, creator_id: str) -> dict[str, Any]:
        return self._creator_row(sheet, creator_id)

    def _snapshots_from_workbook(self, workbook, creator_id: str) -> list[dict[str, Any]]:
        snapshots = [
            row for row in self._rows(workbook["CreatorSnapshots"])
            if str(row.get("creator_id") or "") == str(creator_id or "")
        ]
        # Captures can occur within the same second; later appended rows are newer in that tie.
        indexed = enumerate(snapshots)
        return [row for _index, row in sorted(indexed, key=lambda item: (str(item[1].get("captured_at") or ""), item[0]), reverse=True)]

    @staticmethod
    def _metric_number(value: object) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        raw = str(value).strip().lower().replace(",", "")
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb])?", raw)
        if not match:
            return None
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(match.group(2) or "", 1)
        return float(match.group(1)) * multiplier

    @classmethod
    def _metric_change(cls, latest: object, previous: object) -> dict[str, Any]:
        latest_number = cls._metric_number(latest)
        previous_number = cls._metric_number(previous)
        if latest_number is None or previous_number is None:
            return {"status": "unavailable", "direction": "", "delta": None}
        delta = latest_number - previous_number
        direction = "growth" if delta > 0 else "decline" if delta < 0 else "stable"
        return {"status": "available", "direction": direction, "delta": delta}

    @staticmethod
    def _freshness(captured_at: object) -> dict[str, Any]:
        raw = str(captured_at or "").strip()
        try:
            captured = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
        except ValueError:
            return {"status": "unknown", "days": None}
        days = max(0, (datetime.now(timezone.utc) - captured).days)
        status = "fresh" if days <= 7 else "update_recommended" if days <= 30 else "stale"
        return {"status": status, "days": days}

    @classmethod
    def _trend_from_snapshots(cls, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        latest = snapshots[0] if snapshots else {}
        previous = snapshots[1] if len(snapshots) > 1 else {}
        if not previous:
            changes = {
                key: {"status": "no_history", "direction": "", "delta": None}
                for key in ("followers", "median_views", "creator_score")
            }
        else:
            changes = {
                "followers": cls._metric_change(latest.get("followers"), previous.get("followers")),
                "median_views": cls._metric_change(latest.get("median_views"), previous.get("median_views")),
                "creator_score": cls._metric_change(latest.get("creator_score"), previous.get("creator_score")),
            }
        return {
            "latest": latest,
            "previous": previous,
            "changes": changes,
            "freshness": cls._freshness(latest.get("captured_at")),
        }

    def _creator_id_for_account_uid(self, workbook, account_uid: str) -> str:
        account_uid = str(account_uid or "").strip()
        if not account_uid:
            return ""
        for snapshot in self._rows(workbook["CreatorSnapshots"]):
            if str(snapshot.get("account_uid") or "") == account_uid:
                candidate = str(snapshot.get("creator_id") or "")
                if self._creator_row(workbook["Creators"], candidate):
                    return candidate
        for metadata in self._rows(workbook["_AnalysisData"]):
            if str(metadata.get("account_uid") or "") == account_uid:
                candidate = str(metadata.get("creator_id") or "")
                if self._creator_row(workbook["Creators"], candidate):
                    return candidate
        return ""

    @staticmethod
    def _upsert_row(sheet, key: str, key_value: str, values: dict[str, Any]) -> None:
        headers = [str(cell.value or "") for cell in sheet[1]]
        key_index = headers.index(key) + 1
        row_index = next((row for row in range(2, sheet.max_row + 1) if str(sheet.cell(row, key_index).value or "") == key_value), sheet.max_row + 1)
        for column, header in enumerate(headers, start=1):
            if header in values:
                sheet.cell(row_index, column, values[header])

    def _replace_video_rows(self, sheet, creator_id: str, videos: object) -> None:
        headers = [str(cell.value or "") for cell in sheet[1]]
        existing = self._rows(sheet)
        retained = [row for row in existing if str(row.get("creator_id") or "") != creator_id]
        sheet.delete_rows(2, max(sheet.max_row - 1, 0))
        for row in retained:
            sheet.append([row.get(header, "") for header in headers])
        for video in videos if isinstance(videos, list) else []:
            if not isinstance(video, dict):
                continue
            sheet.append([
                creator_id,
                str(video.get("video_url") or ""),
                video.get("views", ""),
                video.get("likes", ""),
                video.get("comments", ""),
                str(video.get("captured_at") or ""),
            ])

    def _replace_video_snapshot_rows(self, sheet, snapshot_id: str, creator_id: str, videos: object, captured_at: str) -> None:
        headers = [str(cell.value or "") for cell in sheet[1]]
        retained = [row for row in self._rows(sheet) if str(row.get("snapshot_id") or "") != snapshot_id]
        sheet.delete_rows(2, max(sheet.max_row - 1, 0))
        for row in retained:
            sheet.append([row.get(header, "") for header in headers])
        for index, video in enumerate(videos if isinstance(videos, list) else []):
            if not isinstance(video, dict):
                continue
            video_url = str(video.get("video_url") or "")
            video_id = str(video.get("video_id") or video.get("video_key") or "").strip()
            if not video_id:
                video_id = hashlib.sha256(video_url.encode("utf-8")).hexdigest()[:16] if video_url else str(index + 1)
            sheet.append([
                f"{snapshot_id}:{video_id}", snapshot_id, creator_id, video_id, video_url,
                str(video.get("platform") or ""), video.get("views", ""), video.get("likes", ""),
                video.get("comments", ""), str(video.get("captured_at") or captured_at),
            ])

    @staticmethod
    def _optional_number(value: object, label: str, integer: bool = False) -> int | float | str:
        raw = str(value if value is not None else "").strip()
        if not raw:
            return ""
        try:
            number = float(raw.replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"{label}必须是数字。") from exc
        if integer:
            if not number.is_integer() or number < 0:
                raise ValueError(f"{label}必须是非负整数。")
            return int(number)
        return number

    @staticmethod
    def _cooperation_statistics(cooperations: list[dict[str, Any]]) -> dict[str, Any]:
        def values(field: str) -> list[float]:
            result = []
            for cooperation in cooperations:
                value = cooperation.get(field)
                if isinstance(value, (int, float)):
                    result.append(float(value))
                elif isinstance(value, str) and value.strip():
                    try:
                        result.append(float(value.replace(",", "")))
                    except ValueError:
                        continue
            return result

        prices = values("price")
        average_views = values("average_views")
        rois = values("roi")
        return {
            "cooperation_count": len(cooperations),
            "total_spend": sum(prices) if prices else 0,
            "average_views": sum(average_views) / len(average_views) if average_views else 0,
            "average_roi": sum(rois) / len(rois) if rois else 0,
        }

    @staticmethod
    def _creator_values(analysis: dict[str, Any], status: str, creator_id: str) -> dict[str, Any]:
        creator = analysis.get("creator") if isinstance(analysis.get("creator"), dict) else {}
        insight = analysis.get("creator_insight") if isinstance(analysis.get("creator_insight"), dict) else {}
        return {
            "creator_id": creator_id,
            "name": str(creator.get("creator_name") or ""),
            "platform": str(creator.get("platform") or ""),
            "profile_url": str(creator.get("profile_url") or ""),
            "country": str(creator.get("country") or ""),
            "language": str(creator.get("language") or ""),
            "content_category": str(analysis.get("content_category") or ""),
            "tags": CreatorRepository._tags_value(analysis),
            "followers": str(creator.get("followers") or ""),
            "insight_level": str(insight.get("level") or insight.get("grade") or "insufficient"),
            "status": status,
            "created_at": str(analysis.get("imported_at") or _utc_now()),
            "updated_at": _utc_now(),
        }

    @staticmethod
    def _insight_values(analysis: dict[str, Any], creator_id: str) -> dict[str, Any]:
        metrics = analysis.get("video_analysis") if isinstance(analysis.get("video_analysis"), dict) else {}
        insight = analysis.get("creator_insight") if isinstance(analysis.get("creator_insight"), dict) else {}
        return {
            "creator_id": creator_id,
            "average_views": metrics.get("average_views", ""),
            "median_views": metrics.get("median_views", ""),
            "stability": metrics.get("view_stability", ""),
            "risks": json.dumps(insight.get("risks") if isinstance(insight.get("risks"), list) else [], ensure_ascii=False),
            "recommendation": str(insight.get("recommendation") or ""),
        }

    def _rebuild_analysis(self, workbook, creator: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        creator_id = str(creator.get("creator_id") or "")
        insight = self._creator_row(workbook["Insights"], creator_id)
        videos = [row for row in self._rows(workbook["Videos"]) if str(row.get("creator_id") or "") == creator_id]
        risks = self._decode_json_list(insight.get("risks"))
        return {
            "schema_version": "1.0",
            "analysis_id": creator_id,
            "task_id": str(metadata.get("task_id") or ""),
            "account_uid": str(metadata.get("account_uid") or ""),
            "imported_at": str(creator.get("created_at") or ""),
            "source": str(metadata.get("source") or "excel"),
            "creator": {
                "creator_name": str(creator.get("name") or ""),
                "platform": str(creator.get("platform") or ""),
                "profile_url": str(creator.get("profile_url") or ""),
                "followers": str(creator.get("followers") or ""),
                "bio": "",
                "country": str(creator.get("country") or ""),
                "language": str(creator.get("language") or ""),
            },
            "content_category": str(creator.get("content_category") or ""),
            "tags": str(creator.get("tags") or ""),
            "video_analysis": {
                "sample_size": len(videos),
                "average_views": insight.get("average_views"),
                "median_views": insight.get("median_views"),
                "view_stability": insight.get("stability"),
            },
            "videos": videos,
            "creator_insight": {
                "level": str(creator.get("insight_level") or "insufficient"),
                "risks": risks,
                "recommendation": str(insight.get("recommendation") or ""),
                "strengths": [],
            },
        }

    def _migrate_legacy_json(self, workbook) -> None:
        if not self.legacy_analysis_dir or not self.legacy_analysis_dir.exists():
            return
        statuses = self._legacy_statuses()
        for path in self.legacy_analysis_dir.glob("analysis_task_*.json"):
            analysis, _source_path = load_json_with_backup(path)
            if not isinstance(analysis, dict):
                continue
            try:
                self._validate_analysis(analysis)
            except ValueError:
                continue
            creator_id = str(analysis["analysis_id"])
            state = statuses.get(creator_id, {})
            self._upsert_row(
                workbook["Creators"],
                "creator_id",
                creator_id,
                self._creator_values(analysis, self._status_value(state.get("status")), creator_id),
            )
            self._replace_video_rows(workbook["Videos"], creator_id, analysis.get("videos"))
            self._upsert_row(
                workbook["Insights"],
                "creator_id",
                creator_id,
                self._insight_values(analysis, creator_id),
            )
            self._upsert_row(workbook["_AnalysisData"], "creator_id", creator_id, {
                "creator_id": creator_id,
                "task_id": str(analysis.get("task_id") or ""),
                "account_uid": str(analysis.get("account_uid") or ""),
                "source": str(analysis.get("source") or "legacy_json"),
                "status_updated_at": str(state.get("updated_at") or ""),
                "analysis_json": json.dumps(analysis, ensure_ascii=False),
            })

    def _legacy_statuses(self) -> dict[str, Any]:
        if not self.legacy_library_file:
            return {}
        data, _source_path = load_json_with_backup(self.legacy_library_file)
        return data.get("records", {}) if isinstance(data, dict) and isinstance(data.get("records"), dict) else {}

    @staticmethod
    def _validate_analysis(analysis: dict[str, Any]) -> None:
        task_id = str(analysis.get("task_id") or "").strip()
        analysis_id = str(analysis.get("analysis_id") or "").strip()
        if not _TASK_ID_PATTERN.fullmatch(task_id) or analysis_id != f"analysis_{task_id}":
            raise ValueError("达人分析标识无效。")

    @staticmethod
    def _status_value(value: object) -> str:
        status = str(value or "discovered").strip()
        if status not in CREATOR_LIBRARY_STATUSES:
            raise ValueError("达人状态无效。")
        return status

    @staticmethod
    def _tags_value(analysis: dict[str, Any]) -> str:
        raw_tags = analysis.get("tags")
        if isinstance(raw_tags, list):
            return ", ".join(str(tag).strip() for tag in raw_tags if str(tag).strip())
        creator = analysis.get("creator") if isinstance(analysis.get("creator"), dict) else {}
        return str(creator.get("tags") or raw_tags or "").strip()

    @staticmethod
    def _decode_analysis(value: object) -> dict[str, Any]:
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _decode_json_list(value: object) -> list[Any]:
        if not isinstance(value, str):
            return []
        try:
            data = json.loads(value)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
