from __future__ import annotations

"""SQLite-specific indexed read boundary for snapshot-heavy Creator views."""

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
from typing import Iterator
from urllib.parse import urlparse

from creator_repository import CreatorRepository, _mutation_synchronized, _utc_now
from storage.migration import _value
from storage.sqlite_workbook_store import SQLiteWorkbookStore


class SQLiteCreatorRepository(CreatorRepository):
    """Preserve CreatorRepository contracts while scoping expensive reads."""

    store: SQLiteWorkbookStore

    @contextmanager
    def _creator_scope(
        self, creator_id: str, sources: tuple[str, ...]
    ) -> Iterator[None]:
        with self.store.projection_scope(sources), self.store.creator_read_scope(creator_id):
            yield

    @contextmanager
    def _projection(self, *sources: str) -> Iterator[None]:
        with self.store.projection_scope(tuple(sources)):
            yield

    def getCreatorSnapshots(self, creator_id: str):
        with self._creator_scope(creator_id, ("CreatorSnapshots",)):
            return super().getCreatorSnapshots(creator_id)

    def getCreatorTrend(self, creator_id: str):
        with self._creator_scope(creator_id, ("Creators", "CreatorSnapshots")):
            return super().getCreatorTrend(creator_id)

    def getCreatorDetail(self, analysis_id: str):
        with self._creator_scope(analysis_id, (
            "Creators", "CreatorAccounts", "Videos", "Insights",
            "CreatorSnapshots", "Cooperations", "Agencies", "_AnalysisData",
        )):
            return super().getCreatorDetail(analysis_id)

    def getCreatorSummarySourceData(self, creator_id: str):
        with self._creator_scope(creator_id, (
            "Creators", "Insights", "CreatorSnapshots", "CampaignCreators",
        )):
            return super().getCreatorSummarySourceData(creator_id)

    def getCreatorIntelligenceSourceData(self, creator_id: str):
        with self._creator_scope(creator_id, (
            "Creators", "CreatorAccounts", "CreatorSnapshots",
            "CampaignCreators", "_AnalysisData",
        )):
            return super().getCreatorIntelligenceSourceData(creator_id)

    def getCreatorCooperations(self, creator_id: str, workbook=None):
        if workbook is not None:
            return super().getCreatorCooperations(creator_id, workbook)
        with self._creator_scope(creator_id, ("Cooperations",)):
            return super().getCreatorCooperations(creator_id)

    def getCreators(self, include_archived: bool = False):
        with self._projection(
            "Creators", "CreatorAccounts", "Insights", "CreatorSnapshots",
            "Agencies", "_AnalysisData",
        ):
            return super().getCreators(include_archived)

    def getCreatorLibrarySnapshot(self):
        with self._projection(
            "Creators", "CreatorAccounts", "Insights", "CreatorSnapshots",
            "Agencies", "AgencyContacts", "_AnalysisData",
        ):
            return super().getCreatorLibrarySnapshot()

    def getCreatorAccounts(self, creator_id: str = ""):
        with self._projection("CreatorAccounts"):
            return super().getCreatorAccounts(creator_id)

    def getCreatorInventoryRows(self):
        with self._projection(
            "Creators", "CreatorAccounts", "Insights", "CreatorSnapshots"
        ):
            return super().getCreatorInventoryRows()

    def getCreatorAccountIdentityRows(self):
        with self._projection("Creators", "CreatorAccounts"):
            return super().getCreatorAccountIdentityRows()

    def getExistingCreatorAccountUids(self, account_uids: set[str]):
        with self._projection("Creators", "CreatorAccounts"):
            return super().getExistingCreatorAccountUids(account_uids)

    def getCreatorsByAgency(self, agency_id: str):
        with self._projection("Creators"):
            return super().getCreatorsByAgency(agency_id)

    def getCreatorCountsByAgency(self):
        with self._projection("Creators"):
            return super().getCreatorCountsByAgency()

    def getCooperations(self):
        with self._projection("Cooperations"):
            return super().getCooperations()

    @_mutation_synchronized
    def updateCreator(self, creator_id: str, payload: dict, *, agency_port=None):
        if not isinstance(payload, dict) or not payload:
            raise ValueError("缺少可更新的达人资料。")
        allowed = {
            "creator_name", "profile_url", "followers", "country", "language",
            "content_category", "bio", "agency_id", "archived_at",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"不允许修改达人字段：{', '.join(sorted(unknown))}")
        creator_id = str(creator_id or "").strip()
        now = _utc_now()
        with self.store.factory.write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM creators WHERE creator_id=?", (creator_id,)
            ).fetchone()
            if row is None:
                raise ValueError("未找到达人记录。")
            creator = dict(row)
            metadata_row = connection.execute(
                "SELECT * FROM analysis_data WHERE creator_id=?", (creator_id,)
            ).fetchone()
            metadata = dict(metadata_row) if metadata_row else {}
            try:
                analysis = json.loads(str(metadata.get("analysis_json") or "{}"))
            except (TypeError, ValueError):
                analysis = {}
            if not isinstance(analysis, dict):
                analysis = {}
            analysis_creator = dict(
                analysis.get("creator") if isinstance(analysis.get("creator"), dict) else {}
            )
            crm = dict(analysis.get("_crm") if isinstance(analysis.get("_crm"), dict) else {})
            updates = {"updated_at": now}
            if "creator_name" in payload:
                value = str(payload.get("creator_name") or "").strip()
                if not value:
                    raise ValueError("达人名称不能为空。")
                updates["name"] = value
                analysis_creator["creator_name"] = crm["creator_name"] = value
            if "profile_url" in payload:
                value = str(payload.get("profile_url") or "").strip()
                parsed = urlparse(value)
                if not value or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError("主页链接必须是有效的 HTTP 或 HTTPS 地址。")
                updates["profile_url"] = value
                analysis_creator["profile_url"] = crm["profile_url"] = value
            if "followers" in payload:
                raw = str(payload.get("followers") or "").strip()
                updates["followers"] = _value("followers", raw)
                analysis_creator["followers"] = crm["followers"] = raw
            for field in ("country", "language", "bio"):
                if field in payload:
                    value = str(payload.get(field) or "").strip()
                    updates[field] = value or None
                    analysis_creator[field] = crm[field] = value
            if "content_category" in payload:
                value = str(payload.get("content_category") or "").strip()
                updates["content_category"] = value or None
                analysis["content_category"] = value
                crm["content_category"] = value
            if "agency_id" in payload:
                value = str(payload.get("agency_id") or "").strip()
                if value:
                    if agency_port is not None:
                        agency_port.get_agency(value)
                    elif connection.execute(
                        "SELECT 1 FROM agencies WHERE agency_id=?", (value,)
                    ).fetchone() is None:
                        raise ValueError("关联的 Agency 不存在。")
                updates["agency_id"] = value or None
                crm["agency_id"] = value
            if "archived_at" in payload:
                value = payload.get("archived_at")
                if value is not None:
                    value = str(value or "").strip()
                    try:
                        datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise ValueError("归档时间必须是有效的 ISO 时间。") from exc
                updates["archived_at"] = value or None
                crm["archived_at"] = value
            connection.execute(
                f"UPDATE creators SET {','.join(f'{field}=?' for field in updates)} "
                "WHERE creator_id=?",
                tuple(updates.values()) + (creator_id,),
            )
            if "profile_url" in payload or "followers" in payload:
                account = connection.execute(
                    "SELECT * FROM creator_accounts WHERE creator_id=? "
                    "ORDER BY CASE WHEN account_uid=? THEN 0 ELSE 1 END, created_at, account_uid LIMIT 1",
                    (creator_id, str(metadata.get("account_uid") or "")),
                ).fetchone()
                if account:
                    account_updates = {"updated_at": now}
                    if "profile_url" in payload:
                        account_updates["profile_url"] = updates["profile_url"]
                    if "followers" in payload:
                        account_updates["followers"] = updates["followers"]
                    connection.execute(
                        f"UPDATE creator_accounts SET {','.join(f'{field}=?' for field in account_updates)} "
                        "WHERE account_uid=?",
                        tuple(account_updates.values()) + (str(account["account_uid"]),),
                    )
            analysis["creator"] = analysis_creator
            analysis["_crm"] = crm
            connection.execute(
                "INSERT INTO analysis_data(creator_id,task_id,account_uid,status_updated_at,analysis_json,source) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(creator_id) DO UPDATE SET analysis_json=excluded.analysis_json",
                (creator_id, metadata.get("task_id"), metadata.get("account_uid"),
                 metadata.get("status_updated_at"), json.dumps(analysis, ensure_ascii=False),
                 metadata.get("source")),
            )
            self.store.increment_business_revision(connection)
        updated_row = {**creator, **updates}
        return {
            "creator_id": creator_id,
            "creator_name": str(updated_row.get("name") or ""),
            "profile_url": str(updated_row.get("profile_url") or ""),
            "followers": str(updated_row.get("followers") or ""),
            "content_category": str(updated_row.get("content_category") or ""),
            "bio": str(updated_row.get("bio") or crm.get("bio") or ""),
            "agency_id": str(updated_row.get("agency_id") or ""),
            "archived_at": updated_row.get("archived_at") or None,
            "updated_at": now,
        }

    @_mutation_synchronized
    def createSnapshot(self, analysis: dict, creator_id: str, workbook=None):
        if workbook is not None:
            return super().createSnapshot(analysis, creator_id, workbook)
        creator_id = str(creator_id or "").strip()
        snapshot_id = f"snapshot_{analysis['task_id']}"
        creator = analysis.get("creator") if isinstance(analysis.get("creator"), dict) else {}
        metrics = analysis.get("video_analysis") if isinstance(analysis.get("video_analysis"), dict) else {}
        insight = analysis.get("creator_insight") if isinstance(analysis.get("creator_insight"), dict) else {}
        captured_at = str(analysis.get("imported_at") or _utc_now())
        snapshot = {
            "snapshot_id": snapshot_id, "creator_id": creator_id,
            "platform": str(creator.get("platform") or ""),
            "account_uid": str(analysis.get("account_uid") or "") or None,
            "followers": _value("followers", creator.get("followers")),
            "average_views": _value("average_views", metrics.get("average_views")),
            "median_views": _value("median_views", metrics.get("median_views")),
            "video_count": len(analysis.get("videos") if isinstance(analysis.get("videos"), list) else []),
            "creator_score": _value("creator_score", insight.get("creator_score", insight.get("rule_score"))),
            "insight_level": str(insight.get("level") or insight.get("grade") or "insufficient"),
            "captured_at": captured_at, "source": str(analysis.get("source") or ""),
        }
        with self.store.factory.write_transaction() as connection:
            if connection.execute("SELECT 1 FROM creators WHERE creator_id=?", (creator_id,)).fetchone() is None:
                raise ValueError("未找到达人记录。")
            if snapshot["account_uid"] and connection.execute(
                "SELECT 1 FROM creator_accounts WHERE account_uid=? AND creator_id=?",
                (snapshot["account_uid"], creator_id),
            ).fetchone() is None:
                raise ValueError("达人账号不属于所选达人。")
            columns = tuple(snapshot)
            connection.execute(
                f"INSERT INTO creator_snapshots({','.join(columns)}) VALUES "
                f"({','.join('?' for _ in columns)}) ON CONFLICT(snapshot_id) DO UPDATE SET "
                + ",".join(f"{field}=excluded.{field}" for field in columns if field != "snapshot_id"),
                tuple(snapshot.values()),
            )
            connection.execute("DELETE FROM video_snapshots WHERE snapshot_id=?", (snapshot_id,))
            for index, video in enumerate(analysis.get("videos") if isinstance(analysis.get("videos"), list) else []):
                if not isinstance(video, dict):
                    continue
                video_url = str(video.get("video_url") or "")
                video_id = str(video.get("video_id") or video.get("video_key") or "").strip()
                if not video_id:
                    video_id = hashlib.sha256(video_url.encode("utf-8")).hexdigest()[:16] if video_url else str(index + 1)
                connection.execute(
                    "INSERT INTO video_snapshots(video_snapshot_id,snapshot_id,creator_id,video_id,video_url,platform,views,likes,comments,captured_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f"{snapshot_id}:{video_id}", snapshot_id, creator_id, video_id, video_url,
                     str(video.get("platform") or ""), _value("views", video.get("views")),
                     _value("likes", video.get("likes")), _value("comments", video.get("comments")),
                     str(video.get("captured_at") or captured_at)),
                )
            self.store.increment_business_revision(connection)
        return snapshot
