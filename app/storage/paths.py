from __future__ import annotations

"""Canonical and test-overridable paths for SQLite migration artifacts."""

from dataclasses import dataclass
from pathlib import Path

from runtime_paths import get_app_data_dir


@dataclass(frozen=True)
class SQLiteStoragePaths:
    app_data_dir: Path

    @classmethod
    def for_app_data(cls, app_data_dir: Path | None = None) -> "SQLiteStoragePaths":
        return cls(Path(app_data_dir) if app_data_dir is not None else get_app_data_dir())

    @property
    def data_dir(self) -> Path:
        return self.app_data_dir / "data"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "kolconnect.db"

    @property
    def database_backup_dir(self) -> Path:
        return self.app_data_dir / "backups" / "database"

    @property
    def migration_backup_dir(self) -> Path:
        return self.app_data_dir / "backups" / "migration"

    @property
    def migrations_dir(self) -> Path:
        return self.app_data_dir / "storage_migrations"

    @property
    def authority_marker_path(self) -> Path:
        return self.app_data_dir / "storage_authority.json"

    def staged_database_path(self, migration_id: str) -> Path:
        return self.data_dir / f"kolconnect.db.migrating.{migration_id}"

    def migration_manifest_path(self, migration_id: str) -> Path:
        return self.migrations_dir / migration_id / "manifest.json"

    def ensure_migration_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.migration_backup_dir.mkdir(parents=True, exist_ok=True)
        self.migrations_dir.mkdir(parents=True, exist_ok=True)
