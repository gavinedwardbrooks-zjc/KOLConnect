from __future__ import annotations

"""Set-based SQLite source records for the existing Dashboard service."""

from collections import defaultdict
from typing import Any

from creator_repository import CreatorRepository
from dashboard_repository import DashboardRepository
from storage.schema import validate_schema


class SQLiteDashboardRepository(DashboardRepository):
    """Avoid workbook projections while preserving Dashboard source contracts."""

    def __init__(self, creator_repository: CreatorRepository) -> None:
        super().__init__(creator_repository)
        self._store = creator_repository.store

    def get_creators(self) -> list[dict[str, Any]]:
        if self._creators is not None:
            return self._creators
        with self._store.factory.read_connection() as connection:
            validate_schema(connection)
            creator_rows = connection.execute(
                """
                SELECT c.creator_id, c.name, c.platform, c.profile_url,
                       c.followers, c.content_category, c.country, c.language,
                       c.status, c.created_at, c.updated_at, c.archived_at,
                       COUNT(a.account_uid) AS account_count
                FROM creators AS c
                LEFT JOIN creator_accounts AS a ON a.creator_id = c.creator_id
                WHERE COALESCE(TRIM(c.archived_at), '') = ''
                GROUP BY c.creator_id
                ORDER BY c.created_at DESC, c.creator_id DESC
                """
            ).fetchall()
            snapshot_rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT s.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY s.creator_id
                               ORDER BY s.captured_at DESC, s.snapshot_id DESC
                           ) AS snapshot_rank
                    FROM creator_snapshots AS s
                )
                WHERE snapshot_rank <= 2
                ORDER BY creator_id, snapshot_rank
                """
            ).fetchall()

        snapshots: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in snapshot_rows:
            item = dict(row)
            item.pop("snapshot_rank", None)
            snapshots[str(item.get("creator_id") or "")].append(item)

        self._creators = []
        for raw in creator_rows:
            creator = dict(raw)
            creator_id = str(creator.get("creator_id") or "")
            history = snapshots.get(creator_id, [])
            latest = history[0] if history else {}
            self._creators.append(
                {
                    "analysis_id": creator_id,
                    "creator_id": creator_id,
                    "creator_name": str(creator.get("name") or ""),
                    "platform": str(latest.get("platform") or creator.get("platform") or ""),
                    "profile_url": str(creator.get("profile_url") or ""),
                    "followers": str(creator.get("followers") or latest.get("followers") or ""),
                    "content_category": str(creator.get("content_category") or ""),
                    "country": str(creator.get("country") or ""),
                    "language": str(creator.get("language") or ""),
                    "analysis_time": str(creator.get("created_at") or ""),
                    "created_at": str(creator.get("created_at") or ""),
                    "last_analysis_time": str(
                        latest.get("captured_at") or creator.get("created_at") or ""
                    ),
                    "updated_at": str(creator.get("updated_at") or creator.get("created_at") or ""),
                    "status": CreatorRepository._status_value(creator.get("status")),
                    "trend": CreatorRepository._trend_from_snapshots(history),
                    "account_count": int(creator.get("account_count") or 0),
                    "archived_at": creator.get("archived_at"),
                }
            )
        return self._creators

    def get_campaign_creator_records(
        self,
        creators: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if self._campaign_creators is not None:
            return self._campaign_creators
        with self._store.factory.read_connection() as connection:
            validate_schema(connection)
            rows = connection.execute(
                """
                SELECT cc.*, c.name AS creator_name,
                       COALESCE(a.platform, c.platform, '') AS creator_platform,
                       COALESCE(a.profile_url, c.profile_url, '') AS profile_url,
                       campaign.name AS campaign_name,
                       campaign.archived_at AS campaign_archived_at
                FROM campaign_creators AS cc
                JOIN creators AS c ON c.creator_id = cc.creator_id
                JOIN campaigns AS campaign ON campaign.campaign_id = cc.campaign_id
                LEFT JOIN creator_accounts AS a ON a.account_id = cc.account_id
                WHERE COALESCE(TRIM(cc.archived_at), '') = ''
                ORDER BY cc.created_at DESC, cc.id DESC
                """
            ).fetchall()
        self._campaign_creators = []
        for row in rows:
            relation = dict(row)
            platform = str(relation.pop("creator_platform", "") or "")
            campaign_name = str(relation.pop("campaign_name", "") or "")
            relation.update(
                {
                    "creator_name": str(relation.get("creator_name") or ""),
                    "platform": platform,
                    "creator_platform": platform,
                    "campaign": campaign_name,
                    "campaign_name": campaign_name,
                    "campaign_archived_at": (
                        str(relation.get("campaign_archived_at") or "").strip() or None
                    ),
                }
            )
            self._campaign_creators.append(relation)
        return self._campaign_creators
