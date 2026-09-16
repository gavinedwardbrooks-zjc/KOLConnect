from __future__ import annotations

"""SQLite authority adapter for Agency and Agency contact records."""

import uuid
from typing import Any

from data_repository_base import utc_now
from local_storage_lock import shared_storage_lock
from repositories.agency_repository import AGENCIES_HEADERS, AGENCY_CONTACTS_HEADERS
from storage.sqlite_workbook_store import SQLiteWorkbookStore


class SQLiteAgencyRepository:
    def __init__(self, store: SQLiteWorkbookStore) -> None:
        self.store = store

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        return dict(row) if row is not None else {}

    def list_agencies(self) -> list[dict[str, Any]]:
        with self.store.factory.read_connection() as connection:
            rows = connection.execute("SELECT * FROM agencies ORDER BY lower(name), agency_id").fetchall()
        return [self._row(row) for row in rows]

    def get_agency(self, agency_id: str) -> dict[str, Any]:
        with self.store.factory.read_connection() as connection:
            row = connection.execute("SELECT * FROM agencies WHERE agency_id=?", (str(agency_id or "").strip(),)).fetchone()
        if row is None:
            raise ValueError("未找到 Agency。")
        return self._row(row)

    def save_agency(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Agency 数据无效。")
        agency_id = str(payload.get("agency_id") or "").strip()
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            existing_row = connection.execute("SELECT * FROM agencies WHERE agency_id=?", (agency_id,)).fetchone() if agency_id else None
            if agency_id and existing_row is None:
                raise ValueError("未找到 Agency。")
            existing = self._row(existing_row)
            agency_id = agency_id or f"agency_{uuid.uuid4().hex[:16]}"
            name = str(payload.get("name", existing.get("name") or "")).strip()
            if not name:
                raise ValueError("Agency 名称不能为空。")
            now = utc_now()
            values = {**existing, "agency_id": agency_id, "name": name, "created_at": existing.get("created_at") or now, "updated_at": now}
            for field in AGENCIES_HEADERS:
                if field not in {"agency_id", "created_at", "updated_at"} and field in payload:
                    values[field] = str(payload.get(field) or "").strip()
            columns = tuple(AGENCIES_HEADERS)
            connection.execute(
                f"INSERT INTO agencies({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(agency_id) DO UPDATE SET " + ",".join(f"{column}=excluded.{column}" for column in columns if column not in {"agency_id", "created_at"}),
                tuple(values.get(column) for column in columns),
            )
            self.store.increment_business_revision(connection)
        return values

    def delete_agency(self, agency_id: str) -> dict[str, Any]:
        agency_id = str(agency_id or "").strip()
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            if connection.execute("SELECT 1 FROM agencies WHERE agency_id=?", (agency_id,)).fetchone() is None:
                raise ValueError("未找到 Agency。")
            creator_count = int(connection.execute("SELECT COUNT(*) FROM creators WHERE agency_id=?", (agency_id,)).fetchone()[0])
            contact_count = int(connection.execute("SELECT COUNT(*) FROM agency_contacts WHERE agency_id=?", (agency_id,)).fetchone()[0])
            if creator_count or contact_count:
                raise ValueError(f"该 Agency 仍关联 {creator_count} 位达人和 {contact_count} 位联系人，无法删除。请先解除关联。")
            connection.execute("DELETE FROM agencies WHERE agency_id=?", (agency_id,))
            self.store.increment_business_revision(connection)
        return {"agency_id": agency_id, "deleted": True}

    def list_contacts(self, agency_id: str = "") -> list[dict[str, Any]]:
        with self.store.factory.read_connection() as connection:
            rows = connection.execute("SELECT * FROM agency_contacts WHERE (?='' OR agency_id=?) ORDER BY lower(name), contact_id", (str(agency_id or "").strip(), str(agency_id or "").strip())).fetchall()
        return [self._row(row) for row in rows]

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        with self.store.factory.read_connection() as connection:
            row = connection.execute("SELECT * FROM agency_contacts WHERE contact_id=?", (str(contact_id or "").strip(),)).fetchone()
        if row is None:
            raise ValueError("未找到 Agency 联系人。")
        return self._row(row)

    def save_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("联系人数据无效。")
        contact_id = str(payload.get("contact_id") or "").strip()
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            existing_row = connection.execute("SELECT * FROM agency_contacts WHERE contact_id=?", (contact_id,)).fetchone() if contact_id else None
            if contact_id and existing_row is None:
                raise ValueError("未找到 Agency 联系人。")
            existing = self._row(existing_row)
            agency_id = str(payload.get("agency_id", existing.get("agency_id") or "")).strip()
            if agency_id and connection.execute("SELECT 1 FROM agencies WHERE agency_id=?", (agency_id,)).fetchone() is None:
                raise ValueError("联系人关联的 Agency 不存在。")
            name = str(payload.get("name", existing.get("name") or "")).strip()
            if not name:
                raise ValueError("联系人姓名不能为空。")
            contact_id = contact_id or f"contact_{uuid.uuid4().hex[:16]}"
            now = utc_now()
            values = {**existing, "contact_id": contact_id, "name": name, "agency_id": agency_id, "created_at": existing.get("created_at") or now, "updated_at": now}
            for field in AGENCY_CONTACTS_HEADERS:
                if field not in {"contact_id", "name", "agency_id", "created_at", "updated_at"} and field in payload:
                    values[field] = str(payload.get(field) or "").strip()
            columns = tuple(AGENCY_CONTACTS_HEADERS)
            connection.execute(
                f"INSERT INTO agency_contacts({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                "ON CONFLICT(contact_id) DO UPDATE SET " + ",".join(f"{column}=excluded.{column}" for column in columns if column not in {"contact_id", "created_at"}),
                tuple(values.get(column) for column in columns),
            )
            self.store.increment_business_revision(connection)
        return values

    def delete_contact(self, contact_id: str) -> dict[str, Any]:
        contact_id = str(contact_id or "").strip()
        with shared_storage_lock(), self.store.factory.write_transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM agency_contacts WHERE contact_id=?", (contact_id,)
            ).fetchone() is None:
                raise ValueError("未找到 Agency 联系人。")
            creator_count = int(connection.execute(
                "SELECT COUNT(*) FROM creators WHERE current_contact_id=? OR source_contact_id=?",
                (contact_id, contact_id),
            ).fetchone()[0])
            if creator_count:
                raise ValueError(
                    f"该联系人仍被 {creator_count} 位达人关联，无法删除。请先解除达人关系。"
                )
            connection.execute("DELETE FROM agency_contacts WHERE contact_id=?", (contact_id,))
            self.store.increment_business_revision(connection)
        return {"contact_id": contact_id, "deleted": True}

    def upsert_external_contact(self, external_record_id: str, *, name: str, whatsapp: str = "", source: str = "feishu_compat") -> dict[str, Any]:
        external_record_id = str(external_record_id or "").strip()
        if not external_record_id:
            raise ValueError("外部联系人标识不能为空。")
        with self.store.factory.read_connection() as connection:
            row = connection.execute("SELECT * FROM agency_contacts WHERE external_record_id=?", (external_record_id,)).fetchone()
        return self.save_contact({
            "contact_id": self._row(row).get("contact_id", ""), "name": name,
            "whatsapp": whatsapp, "external_record_id": external_record_id, "source": source,
        })
