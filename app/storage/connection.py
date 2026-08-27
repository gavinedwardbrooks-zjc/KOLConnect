from __future__ import annotations

"""Thread-affine SQLite connections and explicit write transactions."""

from contextlib import contextmanager
from pathlib import Path
import os
import threading
from typing import Iterator
import uuid

from storage.errors import SQLiteBackupError, SQLiteBusyError, SQLiteWalUnavailableError
from storage.sqlite_runtime import require_safe_sqlite_runtime, sqlite_module


DB_WRITE_LOCK = threading.RLock()


class SQLiteConnectionFactory:
    def __init__(self, database_path: Path, *, require_safe_runtime: bool = True) -> None:
        self.database_path = Path(database_path)
        self.require_safe_runtime = require_safe_runtime

    def connect(self):
        if self.require_safe_runtime:
            require_safe_sqlite_runtime()
        sqlite3 = sqlite_module()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.database_path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=True,
        )
        connection.row_factory = sqlite3.Row
        try:
            mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
            if mode != "wal":
                raise SQLiteWalUnavailableError("SQLite WAL mode is unavailable.")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA cache_size=-32768")
            connection.execute("PRAGMA wal_autocheckpoint=1000")
            connection.execute("PRAGMA journal_size_limit=67108864")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise SQLiteWalUnavailableError("SQLite foreign keys are unavailable.")
            return connection
        except Exception:
            connection.close()
            raise

    @contextmanager
    def read_connection(self) -> Iterator[object]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def write_transaction(self) -> Iterator[object]:
        sqlite3 = sqlite_module()
        with DB_WRITE_LOCK:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except sqlite3.OperationalError as exc:
                connection.rollback()
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    raise SQLiteBusyError("SQLite write contention timed out.") from exc
                raise
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()


def backup_database(
    source_path: Path,
    destination_path: Path,
    *,
    expected_schema_version: int | None = None,
) -> Path:
    """Publish a validated online backup without copying live WAL files."""
    source_path = Path(source_path)
    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staged = destination_path.with_name(
        f"{destination_path.name}.{uuid.uuid4().hex}.tmp"
    )
    sqlite3 = sqlite_module()
    source = destination = None
    try:
        source = SQLiteConnectionFactory(source_path).connect()
        destination = sqlite3.connect(staged, isolation_level=None, check_same_thread=True)
        source.backup(destination)
        destination.close()
        destination = None
        probe = sqlite3.connect(staged, isolation_level=None, check_same_thread=True)
        try:
            probe.row_factory = sqlite3.Row
            from storage.schema import schema_version, validate_schema

            if expected_schema_version is None:
                validate_schema(probe)
            else:
                version = schema_version(probe)
                quick_check = str(probe.execute("PRAGMA quick_check").fetchone()[0])
                foreign_keys = list(probe.execute("PRAGMA foreign_key_check"))
                if version != expected_schema_version or quick_check != "ok" or foreign_keys:
                    raise SQLiteBackupError("SQLite source-version backup validation failed.")
            probe.execute("SELECT COUNT(*) FROM creators").fetchone()
        finally:
            probe.close()
        os.replace(staged, destination_path)
        return destination_path
    except Exception as exc:
        if isinstance(exc, SQLiteBackupError):
            raise
        raise SQLiteBackupError("SQLite backup failed.") from exc
    finally:
        if source is not None:
            source.close()
        if destination is not None:
            destination.close()
        if staged.exists():
            staged.unlink()
