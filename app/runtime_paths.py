from __future__ import annotations

"""Runtime paths shared by source and frozen KOL Connect builds."""

import os
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from local_storage_lock import shared_storage_lock


APP_NAME = "KOLConnect"
WINDOWS_REPLACE_MAX_RETRIES = 5
WINDOWS_REPLACE_RETRY_DELAYS = (0.05, 0.10, 0.20, 0.40, 0.80)
WINDOWS_TRANSIENT_REPLACE_WINERRORS = frozenset({5, 32, 33})


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
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        roaming = os.environ.get("APPDATA")
        base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
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
    with shared_storage_lock():
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = json_backup_path(path)
        serialized = json.dumps(data, ensure_ascii=False, indent=2)
        fd, temp_path = _open_sibling_temp(path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            json.loads(temp_path.read_text(encoding="utf-8"))
            if path.is_file():
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
                else:
                    shutil.copy2(path, backup_path)
            _replace_json_file(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace a file with complete bytes on the same filesystem."""
    if not isinstance(data, bytes):
        raise TypeError("atomic_write_bytes data must be bytes")
    with shared_storage_lock():
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = _open_sibling_temp(path)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_file(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def _open_sibling_temp(path: Path) -> tuple[int, Path]:
    fd, raw_temp_path = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent
    )
    return fd, Path(raw_temp_path)


def _replace_json_file(temp_path: Path, path: Path) -> None:
    """Replace a JSON file, tolerating only transient Windows sharing denial."""
    _replace_file(temp_path, path)


def _replace_file(temp_path: Path, path: Path) -> None:
    """Replace a file, tolerating only transient Windows sharing denial."""
    for retry_index in range(WINDOWS_REPLACE_MAX_RETRIES):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            if not _is_windows_transient_replace_error(exc):
                raise
            time.sleep(WINDOWS_REPLACE_RETRY_DELAYS[retry_index])
    os.replace(temp_path, path)


def _is_windows_transient_replace_error(exc: PermissionError) -> bool:
    return (
        os.name == "nt"
        and getattr(exc, "winerror", None) in WINDOWS_TRANSIENT_REPLACE_WINERRORS
    )


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def scraper_worker_command() -> list[str]:
    """Build a scraper subprocess command for source and frozen runtimes."""
    if is_frozen():
        return [sys.executable, "--scraper-worker"]
    return [sys.executable, str(get_code_dir() / "scraper.py")]
