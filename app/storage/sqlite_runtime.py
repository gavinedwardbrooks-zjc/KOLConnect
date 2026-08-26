from __future__ import annotations

"""Load and verify the SQLite runtime approved for WAL authority."""

import ctypes
import os
from pathlib import Path
import sys
from typing import Any

from storage.errors import SQLiteRuntimeUnsafeError


MINIMUM_PREFERRED_SQLITE = (3, 51, 3)
FIXED_BACKPORT_MINIMUMS = {(3, 50): 7, (3, 44): 6}
VENDORED_WINDOWS_SQLITE_SHA256 = (
    "09435aa9de52c533f69fc3f6a23337e0276ad54567c808b80db64923c871257e"
)
_VENDORED_HANDLE: Any | None = None


def parse_version(value: str) -> tuple[int, int, int]:
    parts = str(value or "").split(".")
    try:
        parsed = tuple(int(part) for part in parts[:3])
    except ValueError as exc:
        raise SQLiteRuntimeUnsafeError("SQLite runtime version is invalid.") from exc
    if len(parsed) != 3:
        raise SQLiteRuntimeUnsafeError("SQLite runtime version is incomplete.")
    return parsed


def is_wal_safe_version(value: str | tuple[int, int, int]) -> bool:
    version = parse_version(value) if isinstance(value, str) else value
    if version >= MINIMUM_PREFERRED_SQLITE:
        return True
    minimum_patch = FIXED_BACKPORT_MINIMUMS.get(version[:2])
    return minimum_patch is not None and version[2] >= minimum_patch


def _vendored_windows_dll() -> Path | None:
    if sys.platform != "win32":
        return None
    if getattr(sys, "frozen", False):
        candidate = Path(getattr(sys, "_MEIPASS")) / "sqlite3.dll"
    else:
        candidate = (
            Path(__file__).resolve().parents[2]
            / "packaging"
            / "vendor"
            / "sqlite"
            / "windows-x64"
            / "sqlite3.dll"
        )
    return candidate if candidate.is_file() else None


def _preload_vendored_windows_sqlite() -> None:
    global _VENDORED_HANDLE
    if _VENDORED_HANDLE is not None or "sqlite3" in sys.modules:
        return
    candidate = _vendored_windows_dll()
    if candidate is None:
        return
    _VENDORED_HANDLE = ctypes.WinDLL(str(candidate))


def sqlite_module():
    _preload_vendored_windows_sqlite()
    import sqlite3

    return sqlite3


def runtime_version() -> str:
    return str(sqlite_module().sqlite_version)


def require_safe_sqlite_runtime() -> str:
    version = runtime_version()
    if not is_wal_safe_version(version):
        raise SQLiteRuntimeUnsafeError(
            "SQLite runtime does not satisfy the approved WAL safety policy."
        )
    return version


def vendored_runtime_digest() -> str:
    candidate = _vendored_windows_dll()
    if candidate is None:
        return ""
    import hashlib

    return hashlib.sha256(candidate.read_bytes()).hexdigest()
