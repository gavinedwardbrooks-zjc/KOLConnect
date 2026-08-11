from __future__ import annotations

"""Filesystem persistence boundary for local task data."""

import csv
import io
import json
import os
import re
import shutil
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


TASK_ID_PATTERN = re.compile(r"^task_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
DEFAULT_HEARTBEAT_INTERVAL = 240
PLATFORM_KEYS = ("tiktok", "instagram", "youtube")
PLATFORM_KEY_ALIASES = {
    "tiktok": "tiktok",
    "instagram": "instagram",
    "youtube": "youtube",
    "全部": "all",
    "all": "all",
}
_TASK_LOCK = threading.RLock()


@dataclass(frozen=True)
class TaskCsvDocument:
    fieldnames: tuple[str, ...]
    rows: tuple[Mapping[str, object], ...]


class TaskRepository:
    """Read and persist task files without exposing filesystem paths upstream."""

    def __init__(self, tasks_dir: Path) -> None:
        self._tasks_dir = Path(tasks_dir)

    @contextmanager
    def operation_lock(self):
        """Keep compatible multi-file task updates within one storage transaction."""
        with _TASK_LOCK:
            yield

    @staticmethod
    def normalize_platforms(value: object, legacy_platform: object = "") -> list[str]:
        candidates = value if isinstance(value, list) else [value]
        if not candidates or not any(str(item or "").strip() for item in candidates):
            candidates = [legacy_platform]
        selected: set[str] = set()
        for item in candidates:
            raw = str(item or "").strip()
            key = PLATFORM_KEY_ALIASES.get(
                raw.lower(), PLATFORM_KEY_ALIASES.get(raw, "")
            )
            if key == "all":
                return list(PLATFORM_KEYS)
            if key in PLATFORM_KEYS:
                selected.add(key)
        return [key for key in PLATFORM_KEYS if key in selected] or list(
            PLATFORM_KEYS
        )

    def create_task(
        self,
        normalized_links: list[str],
        invalid_links: list[str],
        input_count: int,
        *,
        name: str = "",
        target_platform: str = "全部",
        platform_summary: Mapping[str, int] | None = None,
        platforms: list[str] | None = None,
        filtered_links: list[dict] | None = None,
        task_type: str = "scrape",
    ) -> dict:
        if not normalized_links:
            raise ValueError("没有可创建任务的有效链接。")

        with _TASK_LOCK:
            task_id = self._new_task_id()
            paths = self._paths(task_id)
            paths["root"].mkdir(parents=True, exist_ok=False)
            paths["links"].write_text(
                "\n".join(normalized_links) + "\n", encoding="utf-8"
            )
            filtered_links = filtered_links or []
            self._atomic_write_json(paths["filtered_links"], filtered_links)
            normalized_task_type = str(task_type or "").strip()
            if normalized_task_type not in {"scrape", "manual", "email_recheck"}:
                normalized_task_type = "scrape"
            task = {
                "id": task_id,
                "name": str(name or "").strip() or self._default_task_name(),
                "task_type": normalized_task_type,
                "status": "created",
                "created_at": self._now(),
                "started_at": "",
                "finished_at": "",
                "profile": "",
                "feishu_enabled": False,
                "sync_mode": "four_tables",
                "input_count": input_count,
                "valid_count": len(normalized_links),
                "invalid_count": len(invalid_links),
                "target_platform": target_platform or "全部",
                "platforms": self.normalize_platforms(platforms, target_platform),
                "platform_summary": dict(platform_summary or {}),
                "filtered_count": len(filtered_links),
                "completed_count": 0,
                "modified_count": 0,
                "last_modified_time": "",
                "last_error": "",
                "pause_requested": False,
                "stop_requested": False,
                "heartbeat_time": "",
                "heartbeat_interval": DEFAULT_HEARTBEAT_INTERVAL,
                "last_progress_time": "",
                "current_item": "",
                "last_successful_index": 0,
                "browser_status": "closed",
                "worker_status": "idle",
                "interrupted_time": "",
                "interrupted_reason": "",
                "instagram_error_count": 0,
                "instagram_status": "",
                "instagram_message": "",
                "retry_round": 0,
                "retry_history": [],
                "retry_requested_urls": [],
                "creator_library_import_eligible": True,
                "creator_library_imported_at": "",
                "creator_library_creator_ids": [],
                "creator_library_account_ids": [],
                "creator_library_import_summary": {},
                "creator_library_import_error": "",
            }
            self._atomic_write_json(paths["metadata"], task)
            return task

    def get_task(self, task_id: str) -> dict:
        paths = self._paths(task_id)
        if not paths["metadata"].exists() or not paths["links"].exists():
            raise ValueError("任务不存在或任务文件不完整。")
        try:
            task = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取任务信息：{exc}") from exc
        if not isinstance(task, dict) or task.get("id") != task_id:
            raise ValueError("任务信息无效。")
        return self._apply_task_defaults(task)

    def list_tasks(self) -> list[dict]:
        if not self._tasks_dir.exists():
            return []
        tasks: list[dict] = []
        with _TASK_LOCK:
            for root in self._tasks_dir.iterdir():
                if not root.is_dir() or not TASK_ID_PATTERN.fullmatch(root.name):
                    continue
                metadata_path = root / "task.json"
                if not metadata_path.exists():
                    continue
                try:
                    task = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(task, dict) and task.get("id") == root.name:
                    tasks.append(self._apply_task_defaults(task))
        return sorted(
            tasks, key=lambda task: str(task.get("created_at") or ""), reverse=True
        )

    def update_task(self, task_id: str, **changes: object) -> dict:
        with _TASK_LOCK:
            task = self.get_task(task_id)
            task.update(changes)
            self._atomic_write_json(self._paths(task_id)["metadata"], task)
            return task

    def delete_task(self, task_id: str) -> None:
        task_id = self._validate_task_id(task_id)
        with _TASK_LOCK:
            root = (self._tasks_dir / task_id).resolve()
            tasks_root = self._tasks_dir.resolve()
            if root.parent != tasks_root or not root.exists() or not root.is_dir():
                raise ValueError("任务不存在。")
            shutil.rmtree(root)

    def read_links(self, task_id: str) -> list[str]:
        path = self._paths(task_id)["links"]
        if not path.exists():
            raise ValueError("未找到任务链接文件。")
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def write_links(self, task_id: str, links: list[str]) -> None:
        path = self._paths(task_id)["links"]
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            temp_path.write_text(
                "\n".join(links) + ("\n" if links else ""), encoding="utf-8"
            )
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)

    def results_exist(self, task_id: str) -> bool:
        return self._paths(task_id)["results"].exists()

    def read_results(self, task_id: str) -> list[dict[str, str]]:
        return self._read_csv(self._paths(task_id)["results"])

    def read_results_document(self, task_id: str) -> TaskCsvDocument:
        return self._read_csv_document(self._paths(task_id)["results"])

    def write_results(
        self, task_id: str, rows: list[Mapping[str, object]], fieldnames: list[str]
    ) -> None:
        self.get_task(task_id)
        self._write_csv(self._paths(task_id)["results"], rows, fieldnames)

    def read_progress(self, task_id: str) -> list[dict[str, str]]:
        path = self._paths(task_id)["progress"]
        if not path.exists():
            return []
        with path.open(
            encoding="utf-8-sig", newline="", errors="ignore"
        ) as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return []
            return [dict(row) for row in reader]

    def read_progress_document(self, task_id: str) -> TaskCsvDocument:
        return self._read_csv_document(self._paths(task_id)["progress"])

    def write_progress(
        self, task_id: str, rows: list[Mapping[str, object]], fieldnames: list[str]
    ) -> None:
        self.get_task(task_id)
        self._write_csv(self._paths(task_id)["progress"], rows, fieldnames)

    def read_modifications(self, task_id: str) -> list[dict]:
        self.get_task(task_id)
        path = self._paths(task_id)["modifications"]
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取修改记录：{exc}") from exc
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("修改记录格式无效。")
        return data

    def write_modifications(self, task_id: str, modifications: list[dict]) -> None:
        self.get_task(task_id)
        self._atomic_write_json(self._paths(task_id)["modifications"], modifications)

    def read_filtered_links(self, task_id: str) -> list[dict]:
        self.get_task(task_id)
        data = self._read_json(self._paths(task_id)["filtered_links"], [])
        return data if isinstance(data, list) else []

    def write_filtered_links(self, task_id: str, links: list[dict]) -> None:
        self.get_task(task_id)
        self._atomic_write_json(self._paths(task_id)["filtered_links"], links)

    def read_sync_result(self, task_id: str) -> dict:
        self.get_task(task_id)
        data = self._read_json(self._paths(task_id)["sync_result"], {})
        return data if isinstance(data, dict) else {}

    def write_sync_result(self, task_id: str, result: Mapping[str, object]) -> None:
        self.get_task(task_id)
        self._atomic_write_json(self._paths(task_id)["sync_result"], dict(result))

    def write_review_update(
        self,
        task_id: str,
        *,
        results: TaskCsvDocument,
        progress: TaskCsvDocument,
        modifications: list[Mapping[str, object]],
        metadata_changes: Mapping[str, object],
    ) -> dict:
        """Atomically replace all task files changed by one review operation."""
        return self.write_task_documents(
            task_id,
            results=results,
            progress=progress,
            modifications=modifications,
            metadata_changes=metadata_changes,
        )

    def write_task_documents(
        self,
        task_id: str,
        *,
        results: TaskCsvDocument,
        progress: TaskCsvDocument,
        modifications: list[Mapping[str, object]],
        metadata_changes: Mapping[str, object],
    ) -> dict:
        """Atomically replace task data documents without exposing their paths."""
        task = self.get_task(task_id)
        task.update(metadata_changes)
        paths = self._paths(task_id)
        self._atomic_write_files(
            {
                paths["results"]: self._csv_bytes(results),
                paths["progress"]: self._csv_bytes(progress),
                paths["modifications"]: json.dumps(
                    modifications, ensure_ascii=False, indent=2
                ).encode("utf-8"),
                paths["metadata"]: json.dumps(
                    task, ensure_ascii=False, indent=2
                ).encode("utf-8"),
            }
        )
        return task

    @staticmethod
    def _read_csv(
        path: Path, *, errors: str | None = None
    ) -> list[dict[str, str]]:
        return [dict(row) for row in TaskRepository._read_csv_document(path, errors=errors).rows]

    @staticmethod
    def _read_csv_document(
        path: Path, *, errors: str | None = None
    ) -> TaskCsvDocument:
        if not path.exists():
            raise ValueError(f"未找到任务文件：{path.name}")
        with path.open(encoding="utf-8-sig", newline="", errors=errors) as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError(f"任务文件格式无效：{path.name}")
            return TaskCsvDocument(
                fieldnames=tuple(reader.fieldnames),
                rows=tuple(dict(row) for row in reader),
            )

    @staticmethod
    def _read_json(path: Path, default: object) -> object:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    @classmethod
    def _write_csv(
        cls,
        path: Path,
        rows: list[Mapping[str, object]],
        fieldnames: list[str],
    ) -> None:
        if not fieldnames:
            raise ValueError("任务文件字段不能为空。")
        cls._atomic_write_bytes(
            path,
            cls._csv_bytes(
                TaskCsvDocument(tuple(fieldnames), tuple(dict(row) for row in rows))
            ),
        )

    @staticmethod
    def _csv_bytes(document: TaskCsvDocument) -> bytes:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer, fieldnames=list(document.fieldnames), extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(document.rows)
        return buffer.getvalue().encode("utf-8-sig")

    @staticmethod
    def _atomic_write_files(contents: Mapping[Path, bytes]) -> None:
        temp_paths: dict[Path, Path] = {}
        backup_paths: dict[Path, Path] = {}
        replaced: list[Path] = []
        with _TASK_LOCK:
            try:
                for path, content in contents.items():
                    temp_path = path.with_name(f".{path.name}.review.tmp")
                    temp_path.write_bytes(content)
                    temp_paths[path] = temp_path
                for path in contents:
                    if path.exists():
                        backup_path = path.with_name(f".{path.name}.review.bak")
                        os.replace(path, backup_path)
                        backup_paths[path] = backup_path
                for path, temp_path in temp_paths.items():
                    os.replace(temp_path, path)
                    replaced.append(path)
            except Exception:
                for path in replaced:
                    path.unlink(missing_ok=True)
                for path, backup_path in backup_paths.items():
                    if backup_path.exists():
                        os.replace(backup_path, path)
                raise
            finally:
                for temp_path in temp_paths.values():
                    temp_path.unlink(missing_ok=True)
                for backup_path in backup_paths.values():
                    backup_path.unlink(missing_ok=True)

    @staticmethod
    def _atomic_write_json(path: Path, data: object) -> None:
        TaskRepository._atomic_write_bytes(
            path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        )

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            temp_path.write_bytes(data)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _paths(self, task_id: str) -> dict[str, Path]:
        task_id = self._validate_task_id(task_id)
        root = self._tasks_dir / task_id
        return {
            "root": root,
            "links": root / "links.txt",
            "progress": root / "progress.csv",
            "results": root / "results.csv",
            "metadata": root / "task.json",
            "sync_result": root / ".sync_result.json",
            "modifications": root / "modifications.json",
            "filtered_links": root / "filtered_links.json",
        }

    @staticmethod
    def _validate_task_id(task_id: str) -> str:
        value = str(task_id or "").strip()
        if not TASK_ID_PATTERN.fullmatch(value):
            raise ValueError("任务 ID 无效。")
        return value

    @classmethod
    def _apply_task_defaults(cls, task: dict) -> dict:
        task["platforms"] = cls.normalize_platforms(
            task.get("platforms"), task.get("platform") or task.get("target_platform")
        )
        defaults = {
            "name": "未命名任务",
            "task_type": "scrape",
            "target_platform": "全部",
            "platform_summary": {},
            "filtered_count": 0,
            "pause_requested": False,
            "stop_requested": False,
            "heartbeat_time": "",
            "heartbeat_interval": DEFAULT_HEARTBEAT_INTERVAL,
            "last_progress_time": "",
            "current_item": "",
            "last_successful_index": 0,
            "browser_status": "closed",
            "worker_status": "idle",
            "interrupted_time": "",
            "interrupted_reason": "",
            "instagram_error_count": 0,
            "instagram_status": "",
            "instagram_message": "",
            "retry_round": 0,
            "retry_history": [],
            "retry_requested_urls": [],
            "creator_library_import_eligible": False,
            "creator_library_imported_at": "",
            "creator_library_creator_ids": [],
            "creator_library_account_ids": [],
            "creator_library_import_summary": {},
            "creator_library_import_error": "",
        }
        for key, value in defaults.items():
            task.setdefault(key, value)
        return task

    @staticmethod
    def _now() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _new_task_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"task_{timestamp}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _default_task_name() -> str:
        return f"未命名任务-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
