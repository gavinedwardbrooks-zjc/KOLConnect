from __future__ import annotations

"""SQLite authority adapter preserving the established repository workbook contract."""

from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
from typing import Any, Iterator
import uuid
from collections import defaultdict

from openpyxl import Workbook

from excel_workbook_store import ExcelWorkbookStore, WorkbookReadError, WorkbookSaveError
from local_storage_lock import shared_storage_lock
from storage.connection import DB_WRITE_LOCK, SQLiteConnectionFactory, backup_database
from storage.migration import BASE_TABLES, ExcelToSQLiteMigrator, _sheet_rows, _value
from storage.schema import apply_schema_migrations, validate_schema
from storage.sqlite_runtime import sqlite_module


_RELATION_TABLES = (
    "campaign_creator_publish_links",
    "campaign_creator_planned_dates",
    "campaign_creator_accounts",
    "campaign_platforms",
    "creator_tags",
)

_CREATOR_READ_SCOPE: ContextVar[str | None] = ContextVar(
    "kolconnect_sqlite_creator_read_scope",
    default=None,
)
_PROJECTION_SCOPE: ContextVar[frozenset[str] | None] = ContextVar(
    "kolconnect_sqlite_projection_scope",
    default=None,
)

_CREATOR_SCOPED_TABLE_FIELDS = {
    "creators": "creator_id",
    "creator_accounts": "creator_id",
    "videos": "creator_id",
    "insights": "creator_id",
    "creator_snapshots": "creator_id",
    "video_snapshots": "creator_id",
    "cooperations": "creator_id",
    "campaign_creators": "creator_id",
    "analysis_data": "creator_id",
}


class SQLiteWorkbookStore(ExcelWorkbookStore):
    """Materialize repository-compatible rows while persisting only to SQLite."""

    is_sqlite_authority = True

    def __init__(self, database_path: Path) -> None:
        super().__init__(database_path)
        self.database_path = self.workbook_path
        self.factory = SQLiteConnectionFactory(self.database_path)

    def open(self):
        try:
            with self.factory.read_connection() as connection:
                validate_schema(connection)
                return self._materialize(
                    connection,
                    _CREATOR_READ_SCOPE.get(),
                    _PROJECTION_SCOPE.get(),
                )
        except Exception as exc:
            raise WorkbookReadError("SQLite business store cannot be read.") from exc

    def save(self, workbook) -> None:
        try:
            with shared_storage_lock(), self.factory.write_transaction() as connection:
                self._prepare_and_replace(connection, workbook)
        except Exception as exc:
            raise WorkbookSaveError("SQLite business store cannot be saved.") from exc

    @contextmanager
    def read_only_workbook(self) -> Iterator[Any]:
        workbook = self.open()
        try:
            yield workbook
        finally:
            workbook.close()

    @contextmanager
    def workbook(self, *, write: bool = False) -> Iterator[Any]:
        if not write:
            with self.read_only_workbook() as workbook:
                yield workbook
            return
        with shared_storage_lock(), self.factory.write_transaction() as connection:
            validate_schema(connection)
            workbook = self._materialize(connection)
            try:
                yield workbook
                self._prepare_and_replace(connection, workbook)
            finally:
                workbook.close()

    @contextmanager
    def scope(
        self, *, write: bool = False, defer_writes: bool = False
    ) -> Iterator[SQLiteWorkbookStore]:
        # Repository methods own their precise SQLite transaction. Request scope
        # only supplies dependency identity and never shares a connection.
        yield self

    @contextmanager
    def creator_read_scope(self, creator_id: str) -> Iterator[SQLiteWorkbookStore]:
        """Limit Creator detail projections to rows owned by one Creator."""
        normalized = str(creator_id or "").strip()
        token = _CREATOR_READ_SCOPE.set(normalized or None)
        try:
            yield self
        finally:
            _CREATOR_READ_SCOPE.reset(token)

    @contextmanager
    def projection_scope(self, sources: tuple[str, ...]) -> Iterator[SQLiteWorkbookStore]:
        """Materialize only the workbook sheets required by a read contract."""
        token = _PROJECTION_SCOPE.set(frozenset(sources))
        try:
            yield self
        finally:
            _PROJECTION_SCOPE.reset(token)

    def create_backup(self, suffix: str) -> Path:
        destination = self.database_path.with_name(
            f"{self.database_path.stem}{suffix}{self.database_path.suffix}"
        )
        return backup_database(self.database_path, destination)

    def create_transaction_backup(self, backup_path: Path) -> Path:
        return backup_database(self.database_path, Path(backup_path))

    def restore_transaction_backup(self, backup_path: Path) -> None:
        backup_path = Path(backup_path)
        if not backup_path.is_file():
            raise WorkbookReadError("SQLite transaction backup is missing.")
        sqlite3 = sqlite_module()
        probe = sqlite3.connect(backup_path, isolation_level=None)
        try:
            probe.row_factory = sqlite3.Row
            validate_schema(probe)
        finally:
            probe.close()
        staged = self.database_path.with_name(
            f"{self.database_path.name}.{uuid.uuid4().hex}.restore.tmp"
        )
        try:
            backup_database(backup_path, staged)
            with shared_storage_lock(), DB_WRITE_LOCK:
                if self.database_path.is_file():
                    with self.factory.read_connection() as current:
                        current.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                os.replace(staged, self.database_path)
                for suffix in ("-wal", "-shm"):
                    self.database_path.with_name(
                        f"{self.database_path.name}{suffix}"
                    ).unlink(missing_ok=True)
                with self.factory.read_connection() as restored:
                    validate_schema(restored)
        except Exception as exc:
            raise WorkbookSaveError("SQLite transaction backup restore failed.") from exc
        finally:
            staged.unlink(missing_ok=True)

    def business_revision(self) -> int:
        with self.factory.read_connection() as connection:
            row = connection.execute(
                "SELECT value FROM storage_metadata WHERE key='business_revision'"
            ).fetchone()
            return int(row[0]) if row else 0

    @staticmethod
    def increment_business_revision(connection) -> int:
        row = connection.execute(
            "SELECT value FROM storage_metadata WHERE key='business_revision'"
        ).fetchone()
        revision = int(row[0]) + 1 if row else 1
        connection.execute(
            "INSERT OR REPLACE INTO storage_metadata(key, value) "
            "VALUES ('business_revision', ?)",
            (str(revision),),
        )
        return revision

    @staticmethod
    def initialize_empty(database_path: Path, *, reference: str = "new-install") -> SQLiteWorkbookStore:
        store = SQLiteWorkbookStore(database_path)
        with store.factory.read_connection() as connection:
            apply_schema_migrations(connection, migration_reference=reference)
            validate_schema(connection)
        return store

    def export_workbook(self, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        workbook = self.open()
        staged = destination.with_name(
            f"{destination.stem}.{uuid.uuid4().hex}.tmp.xlsx"
        )
        try:
            workbook.save(staged)
            os.replace(staged, destination)
            return destination
        finally:
            workbook.close()
            staged.unlink(missing_ok=True)

    def replace_from_workbook(self, workbook) -> None:
        with shared_storage_lock(), self.factory.write_transaction() as connection:
            self._prepare_and_replace(connection, workbook)

    def _prepare_and_replace(self, connection, workbook) -> None:
        for callback in self._before_save_callbacks:
            callback(workbook)
        source_rows: dict[str, list[dict[str, object]]] = {}
        desired_tables = []
        for source, table, identity, columns in BASE_TABLES:
            _headers, rows = _sheet_rows(workbook, source)
            source_rows[source] = rows
            desired_tables.append(
                (table, identity, columns, self._desired_rows(table, identity, columns, rows))
            )

        # Child arrays are ordered projections and are rebuilt inside the same
        # transaction; normalized base entities are synchronized by identity.
        for table in _RELATION_TABLES:
            connection.execute(f"DELETE FROM {table}")
        for table, identity, columns, desired in desired_tables:
            self._upsert_changed_rows(connection, table, identity, columns, desired)
        for table, identity, columns, desired in reversed(desired_tables):
            self._delete_missing_rows(connection, table, identity, columns, desired)
        ExcelToSQLiteMigrator._insert_relations(connection, source_rows)
        ExcelToSQLiteMigrator._import_workbook_metadata(connection, workbook)
        self.increment_business_revision(connection)
        validate_schema(connection)

    @staticmethod
    def _desired_rows(table, identity, columns, rows):
        from storage.errors import SQLiteMigrationAmbiguousIdentityError

        identity_fields = (identity,) if isinstance(identity, str) else identity
        desired = {}
        for row in rows:
            key = tuple(str(row.get(field) or "").strip() for field in identity_fields)
            if any(not value for value in key) or key in desired:
                raise SQLiteMigrationAmbiguousIdentityError(
                    f"Missing or duplicate identity in {table}."
                )
            desired[key] = tuple(_value(field, row.get(field)) for field in columns)
        return desired

    @staticmethod
    def _upsert_changed_rows(connection, table, identity, columns, desired) -> None:
        identity_fields = (identity,) if isinstance(identity, str) else identity
        identity_indexes = tuple(columns.index(field) for field in identity_fields)
        existing = {
            tuple(str(row[index]) for index in identity_indexes): tuple(row)
            for row in connection.execute(f"SELECT {','.join(columns)} FROM {table}")
        }
        insert_sql = (
            f"INSERT INTO {table} ({','.join(columns)}) VALUES "
            f"({','.join('?' for _ in columns)})"
        )
        mutable = tuple(field for field in columns if field not in identity_fields)
        update_sql = (
            f"UPDATE {table} SET {','.join(f'{field}=?' for field in mutable)} "
            f"WHERE {' AND '.join(f'{field}=?' for field in identity_fields)}"
        )
        mutable_indexes = tuple(columns.index(field) for field in mutable)
        for key, values in desired.items():
            current = existing.get(key)
            if current is None:
                connection.execute(insert_sql, values)
            elif current != values and mutable:
                connection.execute(
                    update_sql,
                    tuple(values[index] for index in mutable_indexes) + key,
                )

    @staticmethod
    def _delete_missing_rows(connection, table, identity, columns, desired) -> None:
        identity_fields = (identity,) if isinstance(identity, str) else identity
        existing = {
            tuple(str(value) for value in row)
            for row in connection.execute(
                f"SELECT {','.join(identity_fields)} FROM {table}"
            )
        }
        delete_sql = (
            f"DELETE FROM {table} WHERE "
            f"{' AND '.join(f'{field}=?' for field in identity_fields)}"
        )
        for key in existing - set(desired):
            connection.execute(delete_sql, key)

    @staticmethod
    def _materialize(
        connection,
        creator_id: str | None = None,
        projection: frozenset[str] | None = None,
    ) -> Workbook:
        from creator_repository import _WORKBOOK_SHEETS

        workbook = Workbook()
        workbook.remove(workbook.active)
        for name, headers in _WORKBOOK_SHEETS.items():
            sheet = workbook.create_sheet(name)
            sheet.append(list(headers))

        account_external_ids = {}
        if projection is None or "CampaignCreators" in projection:
            account_external_ids = {
                str(row["account_uid"]): str(row["account_id"] or row["account_uid"])
                for row in connection.execute(
                    "SELECT account_uid, account_id FROM creator_accounts"
                )
            }
        creator_tags: dict[str, list[str]] = defaultdict(list)
        if projection is None or "Creators" in projection:
            sql = "SELECT creator_id, tag FROM creator_tags"
            parameters: tuple[str, ...] = ()
            if creator_id:
                sql += " WHERE creator_id=?"
                parameters = (creator_id,)
            sql += " ORDER BY creator_id, position"
            for owner_id, value in connection.execute(sql, parameters):
                creator_tags[str(owner_id)].append(str(value))

        campaign_platforms: dict[str, list[str]] = defaultdict(list)
        if projection is None or "Campaigns" in projection:
            for owner_id, value in connection.execute(
                "SELECT campaign_id, platform FROM campaign_platforms "
                "ORDER BY campaign_id, position"
            ):
                campaign_platforms[str(owner_id)].append(str(value))

        relation_accounts: dict[str, list[str]] = defaultdict(list)
        relation_dates: dict[str, list[str]] = defaultdict(list)
        relation_links: dict[str, list[str]] = defaultdict(list)
        if projection is None or "CampaignCreators" in projection:
            relation_filter = ""
            parameters = ()
            if creator_id:
                relation_filter = (
                    " JOIN campaign_creators AS cc ON cc.id = child.campaign_creator_id"
                    " WHERE cc.creator_id=?"
                )
                parameters = (creator_id,)
            child_queries = (
                (
                    "campaign_creator_accounts",
                    "account_uid",
                    relation_accounts,
                ),
                (
                    "campaign_creator_planned_dates",
                    "planned_date",
                    relation_dates,
                ),
                (
                    "campaign_creator_publish_links",
                    "publish_link",
                    relation_links,
                ),
            )
            for table, value_column, destination in child_queries:
                sql = (
                    f"SELECT child.campaign_creator_id, child.{value_column} "
                    f"FROM {table} AS child{relation_filter} "
                    "ORDER BY child.campaign_creator_id, child.position"
                )
                for owner_id, value in connection.execute(sql, parameters):
                    destination[str(owner_id)].append(str(value))
        for source, table, _identity, columns in BASE_TABLES:
            if projection is not None and source not in projection:
                continue
            scoped_field = _CREATOR_SCOPED_TABLE_FIELDS.get(table) if creator_id else None
            if scoped_field:
                rows = connection.execute(
                    f"SELECT {','.join(columns)} FROM {table} WHERE {scoped_field}=?",
                    (creator_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"SELECT {','.join(columns)} FROM {table}"
                ).fetchall()
            sheet = workbook[source]
            headers = [str(cell.value or "") for cell in sheet[1]]
            for raw in rows:
                record = dict(raw)
                if source == "Creators":
                    record["tags"] = json.dumps(
                        creator_tags.get(str(record["creator_id"]), []),
                        ensure_ascii=False,
                    )
                elif source == "Campaigns":
                    record["platforms"] = json.dumps(
                        campaign_platforms.get(str(record["campaign_id"]), []),
                        ensure_ascii=False,
                    )
                elif source == "CampaignCreators":
                    relation_id = record["id"]
                    external_ids = [
                        account_external_ids.get(account_uid, account_uid)
                        for account_uid in relation_accounts.get(str(relation_id), [])
                    ]
                    record["account_ids"] = json.dumps(external_ids, ensure_ascii=False)
                    record["planned_publish_dates"] = json.dumps(
                        relation_dates.get(str(relation_id), []),
                        ensure_ascii=False,
                    )
                    record["publish_links"] = json.dumps(
                        relation_links.get(str(relation_id), []),
                        ensure_ascii=False,
                    )
                sheet.append([record.get(header) for header in headers])

        metadata = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT key, value FROM storage_metadata WHERE key LIKE 'source_workbook_%'"
            )
        }
        workbook["_Metadata"].append([
            metadata.get("source_workbook_schema_version", ""),
            metadata.get("source_workbook_last_update_time", ""),
        ])
        workbook["_AnalysisData"].sheet_state = "hidden"
        workbook["_Metadata"].sheet_state = "hidden"
        return workbook
