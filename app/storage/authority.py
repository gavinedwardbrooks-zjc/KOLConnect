from __future__ import annotations

"""Explicit runtime authority selection without timestamp or presence guessing."""

from dataclasses import dataclass
from pathlib import Path
import uuid

from runtime_paths import atomic_write_json, load_json_with_backup
from local_storage_lock import shared_storage_lock
from storage.connection import SQLiteConnectionFactory, backup_database
from storage.errors import SQLiteActivationError
from storage.migration import resolve_authority
from storage.paths import SQLiteStoragePaths
from storage.schema import CURRENT_SCHEMA_VERSION, apply_schema_migrations, schema_version
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
        if (
            isinstance(marker, dict)
            and str(marker.get("authority") or "") == "sqlite"
            and paths.database_path.is_file()
        ):
            factory = SQLiteConnectionFactory(paths.database_path)
            try:
                with factory.read_connection() as connection:
                    current = schema_version(connection)
            except Exception:
                # Preserve the existing fail-closed authority classification for
                # corrupt or unreadable databases; only readable databases migrate.
                current = None
            if current is not None and current < CURRENT_SCHEMA_VERSION:
                with shared_storage_lock():
                    paths.database_backup_dir.mkdir(parents=True, exist_ok=True)
                    backup_database(
                        paths.database_path,
                        paths.database_backup_dir
                        / f"kolconnect-pre-schema-v{current}-{uuid.uuid4().hex}.db",
                        expected_schema_version=current,
                    )
                    with factory.read_connection() as connection:
                        apply_schema_migrations(
                            connection, migration_reference="runtime-schema-upgrade"
                        )
                marker = {**marker, "schema_version": CURRENT_SCHEMA_VERSION}
                atomic_write_json(paths.authority_marker_path, marker)
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
