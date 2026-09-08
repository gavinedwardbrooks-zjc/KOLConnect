from __future__ import annotations

"""Append-only metric observations anchored to canonical Publications."""

from typing import Any

from local_storage_lock import shared_storage_lock
from storage.sqlite_workbook_store import SQLiteWorkbookStore


class PublicationPerformanceRepository:
    def __init__(self, store: SQLiteWorkbookStore) -> None:
        if not isinstance(store, SQLiteWorkbookStore):
            raise RuntimeError("Publication performance history requires SQLite authority.")
        self.store = store

    @staticmethod
    def _record(row: Any) -> dict[str, object] | None:
        if row is None:
            return None
        record = dict(row)
        return {
            "observation_id": str(record["observation_id"]),
            "publication_id": str(record["publication_id"]),
            "refresh_operation_id": str(record["refresh_operation_id"]),
            "observed_at": str(record["observed_at"]),
            "views": record["views"],
            "likes": record["likes"],
            "comments": record["comments"],
            "shares": record["shares"],
            "engagement_rate": record["engagement_rate"],
            "source": str(record["source"]),
            "confidence": str(record["confidence"]),
        }

    def append(self, observation: dict[str, object]) -> tuple[dict[str, object], bool]:
        columns = (
            "observation_id", "publication_id", "refresh_operation_id", "observed_at",
            "views", "likes", "comments", "shares", "engagement_rate", "source", "confidence",
        )
        values = tuple(observation.get(column) for column in columns)
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            publication = connection.execute(
                "SELECT 1 FROM campaign_creator_publish_links WHERE publication_id=?",
                (observation["publication_id"],),
            ).fetchone()
            if publication is None:
                raise ValueError("实际发布内容不存在。")
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO publication_performance_observations({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            row = connection.execute(
                "SELECT * FROM publication_performance_observations "
                "WHERE publication_id=? AND refresh_operation_id=?",
                (observation["publication_id"], observation["refresh_operation_id"]),
            ).fetchone()
            if cursor.rowcount:
                self.store.increment_business_revision(connection)
        record = self._record(row)
        if record is None:
            raise RuntimeError("Publication observation could not be persisted.")
        return record, bool(cursor.rowcount)

    def latest(self, publication_id: str) -> dict[str, object] | None:
        with self.store.factory.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM publication_performance_observations WHERE publication_id=? "
                "ORDER BY observed_at DESC, observation_id DESC LIMIT 1",
                (publication_id,),
            ).fetchone()
        return self._record(row)

    def history(self, publication_id: str) -> list[dict[str, object]]:
        with self.store.factory.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM publication_performance_observations WHERE publication_id=? "
                "ORDER BY observed_at, observation_id",
                (publication_id,),
            ).fetchall()
        return [record for row in rows if (record := self._record(row)) is not None]

    def analytics_rows(
        self,
        *,
        campaign_id: str = "",
        creator_id: str = "",
        creator_ids: list[str] | None = None,
        campaign_creator_id: str = "",
        publication_id: str = "",
    ) -> list[dict[str, object]]:
        where = ["COALESCE(cc.archived_at, '')=''", "COALESCE(c.archived_at, '')=''"]
        parameters: list[object] = []
        if campaign_id:
            where.append("cc.campaign_id=?")
            parameters.append(campaign_id)
        if creator_id:
            where.append("cc.creator_id=?")
            parameters.append(creator_id)
        if creator_ids:
            normalized_ids = sorted({str(value) for value in creator_ids if str(value)})
            if normalized_ids:
                where.append(f"cc.creator_id IN ({','.join('?' for _ in normalized_ids)})")
                parameters.extend(normalized_ids)
        if campaign_creator_id:
            where.append("cc.id=?")
            parameters.append(campaign_creator_id)
        if publication_id:
            where.append("p.publication_id=?")
            parameters.append(publication_id)
        sql = (
            "SELECT cc.id AS campaign_creator_id, cc.campaign_id, c.name AS campaign_name, "
            "c.status AS campaign_status, c.start_date, c.end_date, cc.creator_id, "
            "cr.name AS creator_name, cc.creator_quote, cc.quote_currency, cc.cost, "
            "cc.cost_currency, p.publication_id, p.publish_link AS publication_url, "
            "p.actual_account_uid, p.platform, p.video_id, p.published_at, "
            "o.observation_id, o.observed_at, "
            "o.views, o.likes, o.comments, o.shares, o.engagement_rate, o.source, o.confidence "
            "FROM campaign_creators cc JOIN campaigns c ON c.campaign_id=cc.campaign_id "
            "JOIN creators cr ON cr.creator_id=cc.creator_id "
            "LEFT JOIN campaign_creator_publish_links p ON p.campaign_creator_id=cc.id "
            "LEFT JOIN publication_performance_observations o ON o.publication_id=p.publication_id "
            f"WHERE {' AND '.join(where)} ORDER BY cc.campaign_id, cc.id, p.position, "
            "o.observed_at, o.observation_id"
        )
        with self.store.factory.read_connection() as connection:
            return [dict(row) for row in connection.execute(sql, parameters)]
