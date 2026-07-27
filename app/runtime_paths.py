from __future__ import annotations

"""Runtime paths shared by source and frozen KOL Connect builds."""

import os
import json
import shutil
import sys
from pathlib import Path
from typing import Any


APP_NAME = "KOLConnect"


def get_resource_dir() -> Path:
    """Return the read-only source directory or PyInstaller extraction directory."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return get_code_dir().parent


def get_code_dir() -> Path:
    """Return the directory containing the Python application modules."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def get_app_data_dir() -> Path:
    """Return the per-user writable directory used by KOLConnect."""
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    path = get_app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_external_resources_dir() -> Path:
    """Return the optional release-side resource folder next to the executable."""
    if is_frozen():
        return Path(sys.executable).resolve().parent / "resources"
    return get_resource_dir() / "resources"


def json_backup_path(path: Path) -> Path:
    return path.with_suffix(f"{path.suffix}.bak")


def load_json_with_backup(path: Path) -> tuple[Any | None, Path | None]:
    """Read a JSON file, falling back to its last known-good backup."""
    for candidate in (path, json_backup_path(path)):
        if not candidate.is_file():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8")), candidate
        except (OSError, json.JSONDecodeError):
            continue
    return None, None


def atomic_write_json(path: Path, data: Any) -> None:
    """Validate a temporary JSON file, retain a valid backup, then replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    backup_path = json_backup_path(path)
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        temp_path.write_text(serialized, encoding="utf-8")
        json.loads(temp_path.read_text(encoding="utf-8"))
        if path.is_file():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            else:
                shutil.copy2(path, backup_path)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def scraper_worker_command() -> list[str]:
    """Build a scraper subprocess command for source and frozen runtimes."""
    if is_frozen():
        return [sys.executable, "--scraper-worker"]
    return [sys.executable, str(get_code_dir() / "scraper.py")]
