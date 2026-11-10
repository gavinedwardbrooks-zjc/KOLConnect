from __future__ import annotations

"""SQLite queue for explicitly authorized Campaign publication capture batches."""

from typing import Any

from local_storage_lock import shared_storage_lock
from storage.sqlite_workbook_store import SQLiteWorkbookStore


class PublicationCaptureBatchRepository:
    def __init__(self, store: SQLiteWorkbookStore) -> None:
        if not isinstance(store, SQLiteWorkbookStore):
            raise RuntimeError("Publication capture batches require SQLite authority.")
        self.store = store

    @staticmethod
    def _row(row: Any) -> dict[str, object] | None:
        return dict(row) if row is not None else None

    def create(self, run: dict[str, object], items: list[dict[str, object]]) -> dict[str, object]:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO publication_capture_batch_runs("
                "batch_run_id,campaign_id,status,claim_token_hash,manifest_hash,created_at,updated_at,safe_error_code) "
                "VALUES (?,?,?,?,?,?,?,?)",
                tuple(run.get(key) for key in (
                    "batch_run_id", "campaign_id", "status", "claim_token_hash", "manifest_hash",
                    "created_at", "updated_at", "safe_error_code",
                )),
            )
            for item in items:
                columns = (
                    "item_id", "batch_run_id", "publication_id", "campaign_creator_id", "position",
                    "platform", "video_id", "canonical_url", "status", "safe_error_code",
                    "duplicate_of_item_id", "created_at", "updated_at",
                )
                connection.execute(
                    f"INSERT INTO publication_capture_batch_items({','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in columns)})",
                    tuple(item.get(key) for key in columns),
                )
            self.store.increment_business_revision(connection)
        return self.get(str(run["batch_run_id"])) or {}

    def active_for_campaign(self, campaign_id: str) -> dict[str, object] | None:
        with self.store.factory.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM publication_capture_batch_runs WHERE campaign_id=? "
                "AND status IN ('pending_claim','running','paused','interrupted') ORDER BY created_at DESC LIMIT 1",
                (campaign_id,),
            ).fetchone()
        return self._row(row)

    def get_secret(self, batch_run_id: str) -> dict[str, object] | None:
        with self.store.factory.read_connection() as connection:
            return self._row(connection.execute(
                "SELECT * FROM publication_capture_batch_runs WHERE batch_run_id=?", (batch_run_id,)
            ).fetchone())

    def get(self, batch_run_id: str) -> dict[str, object] | None:
        row = self.get_secret(batch_run_id)
        if row:
            for key in ("claim_token_hash", "executor_token_hash", "executor_origin_hash"):
                row.pop(key, None)
        return row

    def items(self, batch_run_id: str) -> list[dict[str, object]]:
        with self.store.factory.read_connection() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM publication_capture_batch_items WHERE batch_run_id=? ORDER BY position,item_id",
                (batch_run_id,),
            )]

    def bind_executor(
        self, batch_run_id: str, *, claim_consumed_at: str, origin_hash: str,
        token_hash: str, expires_at: str, updated_at: str,
    ) -> dict[str, object]:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE publication_capture_batch_runs SET status='running',claim_consumed_at=?,"
                "executor_origin_hash=?,executor_token_hash=?,executor_expires_at=?,updated_at=? "
                "WHERE batch_run_id=? AND status='pending_claim'",
                (claim_consumed_at, origin_hash, token_hash, expires_at, updated_at, batch_run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("BATCH_NOT_CLAIMABLE")
            self.store.increment_business_revision(connection)
        return self.get_secret(batch_run_id) or {}

    def rotate_claim(self, batch_run_id: str, claim_hash: str, updated_at: str) -> None:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE publication_capture_batch_runs SET status='pending_claim',claim_token_hash=?,"
                "claim_consumed_at=NULL,executor_origin_hash=NULL,executor_token_hash=NULL,executor_expires_at=NULL,updated_at=? "
                "WHERE batch_run_id=? AND status IN ('paused','interrupted')",
                (claim_hash, updated_at, batch_run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("BATCH_NOT_RESUMABLE")
            connection.execute(
                "UPDATE publication_capture_batch_items SET status='pending',request_id=NULL,lease_expires_at=NULL,"
                "updated_at=? WHERE batch_run_id=? AND status='interrupted'",
                (updated_at, batch_run_id),
            )
            self.store.increment_business_revision(connection)
    def next_pending(self, batch_run_id: str) -> dict[str, object] | None:
        with self.store.factory.read_connection() as connection:
            return self._row(connection.execute(
                "SELECT * FROM publication_capture_batch_items WHERE batch_run_id=? AND status='pending' "
                "ORDER BY position,item_id LIMIT 1", (batch_run_id,)
            ).fetchone())

    def finish_if_exhausted(self, batch_run_id: str, completed_at: str) -> bool:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            remaining = connection.execute(
                "SELECT COUNT(*) FROM publication_capture_batch_items WHERE batch_run_id=? "
                "AND status IN ('pending','opening','collecting','interrupted')", (batch_run_id,)
            ).fetchone()[0]
            if remaining:
                return False
            cursor = connection.execute(
                "UPDATE publication_capture_batch_runs SET status='completed',completed_at=?,updated_at=? "
                "WHERE batch_run_id=? AND status='running'", (completed_at, completed_at, batch_run_id)
            )
            if cursor.rowcount:
                self.store.increment_business_revision(connection)
            return cursor.rowcount == 1

    def interrupt_stale(self, batch_run_id: str, now: str) -> bool:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            item_cursor = connection.execute(
                "UPDATE publication_capture_batch_items SET status='interrupted',"
                "safe_error_code='CAPTURE_ITEM_INTERRUPTED',lease_expires_at=NULL,updated_at=? "
                "WHERE batch_run_id=? AND status IN ('opening','collecting') "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at<=?",
                (now, batch_run_id, now),
            )
            run_cursor = connection.execute(
                "UPDATE publication_capture_batch_runs SET status='interrupted',"
                "safe_error_code='BATCH_EXECUTOR_INTERRUPTED',updated_at=? "
                "WHERE batch_run_id=? AND status='running' AND "
                "(executor_expires_at<=? OR EXISTS(SELECT 1 FROM publication_capture_batch_items "
                "WHERE batch_run_id=? AND status='interrupted'))",
                (now, batch_run_id, now, batch_run_id),
            )
            changed = bool(item_cursor.rowcount or run_cursor.rowcount)
            if changed:
                self.store.increment_business_revision(connection)
            return changed

    def lease_item(
        self, item_id: str, *, request_id: str, opened_at: str, lease_expires_at: str, updated_at: str,
    ) -> dict[str, object]:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE publication_capture_batch_items SET status='opening',request_id=?,attempt_count=attempt_count+1,"
                "opened_at=?,lease_expires_at=?,updated_at=? WHERE item_id=? AND status='pending'",
                (request_id, opened_at, lease_expires_at, updated_at, item_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("BATCH_ITEM_NOT_PENDING")
            row = connection.execute(
                "SELECT * FROM publication_capture_batch_items WHERE item_id=?", (item_id,)
            ).fetchone()
            self.store.increment_business_revision(connection)
        return dict(row)

    def item_for_request(self, request_id: str) -> dict[str, object] | None:
        with self.store.factory.read_connection() as connection:
            return self._row(connection.execute(
                "SELECT * FROM publication_capture_batch_items WHERE request_id=?", (request_id,)
            ).fetchone())

    def complete_item(self, request_id: str, *, status: str, safe_error_code: str, completed_at: str) -> None:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            row = connection.execute(
                "SELECT batch_run_id FROM publication_capture_batch_items WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is None:
                return
            connection.execute(
                "UPDATE publication_capture_batch_items SET status=?,safe_error_code=?,completed_at=?,"
                "lease_expires_at=NULL,updated_at=? WHERE request_id=?",
                (status, safe_error_code, completed_at, completed_at, request_id),
            )
            batch_id = str(row["batch_run_id"])
            pending = connection.execute(
                "SELECT COUNT(*) FROM publication_capture_batch_items WHERE batch_run_id=? "
                "AND status IN ('pending','opening','collecting','interrupted')", (batch_id,)
            ).fetchone()[0]
            if not pending:
                connection.execute(
                    "UPDATE publication_capture_batch_runs SET status='completed',completed_at=?,updated_at=? "
                    "WHERE batch_run_id=? AND status IN ('running','paused')", (completed_at, completed_at, batch_id)
                )
            self.store.increment_business_revision(connection)

    def set_status(
        self, batch_run_id: str, status: str, updated_at: str, *, safe_error_code: str | None = None,
    ) -> dict[str, object]:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            current = connection.execute(
                "SELECT status FROM publication_capture_batch_runs WHERE batch_run_id=?", (batch_run_id,)
            ).fetchone()
            if current is None:
                raise ValueError("BATCH_NOT_FOUND")
            connection.execute(
                "UPDATE publication_capture_batch_runs SET status=?,updated_at=?,safe_error_code=COALESCE(?,safe_error_code),"
                "completed_at=CASE WHEN ? IN ('completed','cancelled') THEN ? ELSE completed_at END "
                "WHERE batch_run_id=?", (status, updated_at, safe_error_code, status, updated_at, batch_run_id)
            )
            if status == "cancelled":
                connection.execute(
                    "UPDATE publication_capture_batch_items SET status='cancelled',safe_error_code='BATCH_CANCELLED',"
                    "completed_at=?,updated_at=? WHERE batch_run_id=? AND status IN ('pending','opening','collecting','interrupted')",
                    (updated_at, updated_at, batch_run_id),
                )
            elif status == "paused":
                connection.execute(
                    "UPDATE publication_capture_batch_items SET status='interrupted',"
                    "safe_error_code='BATCH_PAUSED',lease_expires_at=NULL,updated_at=? "
                    "WHERE batch_run_id=? AND status IN ('opening','collecting')",
                    (updated_at, batch_run_id),
                )
            self.store.increment_business_revision(connection)
        return self.get(batch_run_id) or {}

    def retry_item(self, batch_run_id: str, item_id: str, updated_at: str) -> None:
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            run = connection.execute(
                "SELECT campaign_id,status FROM publication_capture_batch_runs WHERE batch_run_id=?",
                (batch_run_id,),
            ).fetchone()
            if run is None or str(run["status"]) == "cancelled":
                raise ValueError("BATCH_ITEM_NOT_RETRYABLE")
            if str(run["status"]) == "completed":
                conflict = connection.execute(
                    "SELECT 1 FROM publication_capture_batch_runs WHERE campaign_id=? AND batch_run_id<>? "
                    "AND status IN ('pending_claim','running','paused','interrupted') LIMIT 1",
                    (run["campaign_id"], batch_run_id),
                ).fetchone()
                if conflict:
                    raise ValueError("BATCH_ALREADY_ACTIVE")
                connection.execute(
                    "UPDATE publication_capture_batch_runs SET status='interrupted',completed_at=NULL,"
                    "safe_error_code='',updated_at=? WHERE batch_run_id=?",
                    (updated_at, batch_run_id),
                )
            cursor = connection.execute(
                "UPDATE publication_capture_batch_items SET status='pending',safe_error_code='',request_id=NULL,"
                "lease_expires_at=NULL,opened_at=NULL,completed_at=NULL,updated_at=? "
                "WHERE batch_run_id=? AND item_id=? AND status IN ('failed','insufficient','interrupted')",
                (updated_at, batch_run_id, item_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("BATCH_ITEM_NOT_RETRYABLE")
            self.store.increment_business_revision(connection)
