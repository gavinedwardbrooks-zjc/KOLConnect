from __future__ import annotations

"""Small local task storage for scrape inputs and task-scoped output files."""

import json
import os
import re
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


TASK_ID_PATTERN = re.compile(r"^task_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
_TASK_LOCK = threading.RLock()
DEFAULT_HEARTBEAT_INTERVAL = 240
PLATFORM_KEYS = ("tiktok", "instagram", "youtube")
PLATFORM_KEY_ALIASES = {
    "tiktok": "tiktok",
    "instagram": "instagram",
    "youtube": "youtube",
    "全部": "all",
    "all": "all",
}


def normalize_platforms(value: object, legacy_platform: object = "") -> list[str]:
    """Normalize new multi-platform metadata while accepting older single-platform tasks."""
    candidates = value if isinstance(value, list) else [value]
    if not candidates or not any(str(item or "").strip() for item in candidates):
        candidates = [legacy_platform]
    selected: set[str] = set()
    for item in candidates:
        raw = str(item or "").strip()
        key = PLATFORM_KEY_ALIASES.get(raw.lower(), PLATFORM_KEY_ALIASES.get(raw, ""))
        if key == "all":
            return list(PLATFORM_KEYS)
        if key in PLATFORM_KEYS:
            selected.add(key)
    return [key for key in PLATFORM_KEYS if key in selected] or list(PLATFORM_KEYS)


def _apply_task_defaults(task: dict) -> dict:
    """Keep task metadata backward compatible as task controls evolve."""
    task["platforms"] = normalize_platforms(
        task.get("platforms"),
        task.get("platform") or task.get("target_platform"),
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


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"task_{timestamp}_{uuid.uuid4().hex[:8]}"


def _default_task_name() -> str:
    return f"未命名任务-{datetime.now(timezone.utc).strftime('%Y%m%d')}"


def _atomic_write_json(path: Path, data: dict) -> None:
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


@contextmanager
def task_lock():
    with _TASK_LOCK:
        yield


def atomic_write_files(contents: dict[Path, bytes]) -> None:
    """Replace related task files together, restoring originals if replacement fails."""
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


def _validate_task_id(task_id: str) -> str:
    value = str(task_id or "").strip()
    if not TASK_ID_PATTERN.fullmatch(value):
        raise ValueError("任务 ID 无效。")
    return value


def task_paths(tasks_dir: Path, task_id: str) -> dict[str, Path]:
    task_id = _validate_task_id(task_id)
    root = tasks_dir / task_id
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


def create_task(
    tasks_dir: Path,
    normalized_links: list[str],
    invalid_links: list[str],
    input_count: int,
    *,
    name: str = "",
    target_platform: str = "全部",
    platform_summary: dict[str, int] | None = None,
    platforms: list[str] | None = None,
    filtered_links: list[dict] | None = None,
    task_type: str = "scrape",
) -> dict:
    if not normalized_links:
        raise ValueError("没有可创建任务的有效链接。")

    with _TASK_LOCK:
        task_id = _task_id()
        paths = task_paths(tasks_dir, task_id)
        paths["root"].mkdir(parents=True, exist_ok=False)
        paths["links"].write_text("\n".join(normalized_links) + "\n", encoding="utf-8")
        filtered_links = filtered_links or []
        _atomic_write_json(paths["filtered_links"], filtered_links)
        normalized_task_type = str(task_type or "").strip()
        if normalized_task_type not in {"scrape", "manual", "email_recheck"}:
            normalized_task_type = "scrape"
        task = {
            "id": task_id,
            "name": str(name or "").strip() or _default_task_name(),
            "task_type": normalized_task_type,
            "status": "created",
            "created_at": _now(),
            "started_at": "",
            "finished_at": "",
            "profile": "",
            "feishu_enabled": False,
            "sync_mode": "four_tables",
            "input_count": input_count,
            "valid_count": len(normalized_links),
            "invalid_count": len(invalid_links),
            "target_platform": target_platform or "全部",
            "platforms": normalize_platforms(platforms, target_platform),
            "platform_summary": platform_summary or {},
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
        _atomic_write_json(paths["metadata"], task)
        return task


def load_task(tasks_dir: Path, task_id: str) -> tuple[dict, dict[str, Path]]:
    paths = task_paths(tasks_dir, task_id)
    if not paths["metadata"].exists() or not paths["links"].exists():
        raise ValueError("任务不存在或任务文件不完整。")
    try:
        task = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取任务信息：{exc}") from exc
    if not isinstance(task, dict) or task.get("id") != task_id:
        raise ValueError("任务信息无效。")
    return _apply_task_defaults(task), paths


def list_tasks(tasks_dir: Path) -> list[dict]:
    """Return valid task metadata for local task selection without changing tasks."""
    if not tasks_dir.exists():
        return []

    tasks: list[dict] = []
    with _TASK_LOCK:
        for root in tasks_dir.iterdir():
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
                tasks.append(_apply_task_defaults(task))
    return sorted(tasks, key=lambda task: str(task.get("created_at") or ""), reverse=True)


def update_task(tasks_dir: Path, task_id: str, **changes) -> dict:
    with _TASK_LOCK:
        task, paths = load_task(tasks_dir, task_id)
        task.update(changes)
        _atomic_write_json(paths["metadata"], task)
        return task


def delete_task(tasks_dir: Path, task_id: str) -> None:
    """Delete only one validated local task directory."""
    task_id = _validate_task_id(task_id)
    with _TASK_LOCK:
        root = (tasks_dir / task_id).resolve()
        tasks_root = tasks_dir.resolve()
        if root.parent != tasks_root or not root.exists() or not root.is_dir():
            raise ValueError("任务不存在。")
        shutil.rmtree(root)


def load_modifications(tasks_dir: Path, task_id: str) -> list[dict]:
    _task, paths = load_task(tasks_dir, task_id)
    if not paths["modifications"].exists():
        return []
    try:
        data = json.loads(paths["modifications"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取修改记录：{exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("修改记录格式无效。")
    return data
