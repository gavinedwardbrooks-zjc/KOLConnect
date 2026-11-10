from __future__ import annotations

"""SQLite authority for short-lived, publication-scoped browser capture attempts."""

import json
from typing import Any

from local_storage_lock import shared_storage_lock
from storage.sqlite_workbook_store import SQLiteWorkbookStore


class PublicationCaptureRepository:
    def __init__(self, store: SQLiteWorkbookStore) -> None:
        if not isinstance(store, SQLiteWorkbookStore):
            raise RuntimeError("Publication capture attempts require SQLite authority.")
        self.store = store

    @staticmethod
    def _record(row: Any) -> dict[str, object] | None:
        if row is None:
            return None
        record = dict(row)
        try:
            provenance = json.loads(str(record.get("field_provenance") or "{}"))
        except (TypeError, ValueError):
            provenance = {}
        record["field_provenance"] = provenance if isinstance(provenance, dict) else {}
        record.pop("capability_hash", None)
        return record

    def create(self, attempt: dict[str, object]) -> dict[str, object]:
        columns = (
            "request_id", "publication_id", "campaign_creator_id", "refresh_operation_id",
            "platform", "video_id", "canonical_url", "capability_hash", "started_at", "expires_at",
            "capture_status", "collector_version", "contract_version", "safe_error_code",
            "completeness", "field_provenance", "observation_id", "submission_count",
        )
        values = tuple(attempt.get(column) for column in columns)
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            connection.execute(
                f"INSERT INTO publication_capture_attempts({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            row = connection.execute(
                "SELECT * FROM publication_capture_attempts WHERE request_id=?",
                (attempt["request_id"],),
            ).fetchone()
            self.store.increment_business_revision(connection)
        result = self._record(row)
        if result is None:
            raise RuntimeError("Publication capture request could not be persisted.")
        return result

    def get_with_secret(self, request_id: str) -> dict[str, object] | None:
        with self.store.factory.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM publication_capture_attempts WHERE request_id=?", (request_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def get(self, request_id: str) -> dict[str, object] | None:
        return self._record(self.get_with_secret(request_id))

    def complete(
        self,
        request_id: str,
        *,
        capture_status: str,
        completed_at: str,
        collector_version: str,
        safe_error_code: str,
        completeness: str,
        field_provenance: dict[str, object],
        observation_id: str | None,
    ) -> dict[str, object]:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE publication_capture_attempts SET capture_status=?,completed_at=?,collector_version=?,"
                "safe_error_code=?,completeness=?,field_provenance=?,observation_id=?,submission_count=1 "
                "WHERE request_id=? AND submission_count=0",
                (
                    capture_status, completed_at, collector_version, safe_error_code, completeness,
                    json.dumps(field_provenance, ensure_ascii=True, sort_keys=True), observation_id, request_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM publication_capture_attempts WHERE request_id=?", (request_id,)
            ).fetchone()
            if cursor.rowcount:
                self.store.increment_business_revision(connection)
        result = self._record(row)
        if result is None:
            raise ValueError("CAPTURE_REQUEST_NOT_FOUND")
        return result
