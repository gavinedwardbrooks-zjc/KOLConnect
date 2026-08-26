from __future__ import annotations

"""Explicit runtime authority selection without timestamp or presence guessing."""

from dataclasses import dataclass
from pathlib import Path

from runtime_paths import atomic_write_json, load_json_with_backup
from storage.errors import SQLiteActivationError
from storage.migration import resolve_authority
from storage.paths import SQLiteStoragePaths
from storage.schema import CURRENT_SCHEMA_VERSION
from storage.sqlite_workbook_store import SQLiteWorkbookStore


@dataclass(frozen=True)
class StorageAuthority:
    kind: str
    database_path: Path | None
    workbook_path: Path


def resolve_runtime_authority(
    paths: SQLiteStoragePaths,
    workbook_path: Path,
    *,
    bootstrap_new_install: bool = False,
) -> StorageAuthority:
    workbook_path = Path(workbook_path)
    marker, _source = load_json_with_backup(paths.authority_marker_path)
    if marker is not None:
        state = resolve_authority(paths)
        if state == "sqlite_active":
            return StorageAuthority("sqlite", paths.database_path, workbook_path)
        if state == "legacy_excel":
            return StorageAuthority("legacy_excel", None, workbook_path)
        raise SQLiteActivationError(f"SQLite authority is unavailable: {state}.")

    if workbook_path.is_file():
        return StorageAuthority("legacy_excel", None, workbook_path)
    if paths.database_path.exists():
        raise SQLiteActivationError("Unmarked SQLite database cannot become authority.")
    if not bootstrap_new_install:
        return StorageAuthority("legacy_excel", None, workbook_path)

    paths.ensure_migration_directories()
    SQLiteWorkbookStore.initialize_empty(paths.database_path)
    atomic_write_json(paths.authority_marker_path, {
        "authority": "sqlite",
        "database_name": paths.database_path.name,
        "migration_id": "new-install",
        "schema_version": CURRENT_SCHEMA_VERSION,
    })
    if resolve_authority(paths) != "sqlite_active":
        raise SQLiteActivationError("New-install SQLite authority validation failed.")
    return StorageAuthority("sqlite", paths.database_path, workbook_path)
