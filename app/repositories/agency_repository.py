from __future__ import annotations

"""Excel persistence for local Agencies and Agency contacts."""

import hashlib
import uuid
from pathlib import Path
from typing import Any

from data_repository_base import ExcelDataRepository, utc_now
from excel_workbook_store import ExcelWorkbookStore


AGENCIES_HEADERS = [
    "agency_id", "name", "country", "website", "public_email", "whatsapp",
    "cooperation_stage", "tags", "last_contact_time", "next_follow_up_time",
    "owner", "note", "resource_files", "created_at", "updated_at",
]
AGENCY_CONTACTS_HEADERS = [
    "contact_id", "name", "agency_id", "position", "email", "whatsapp", "language",
    "status", "last_contact_time", "next_follow_up_time", "owner", "note",
    "external_record_id", "source", "created_at", "updated_at",
]


class AgencyRepository(ExcelDataRepository):
    def __init__(self, workbook_path: Path | ExcelWorkbookStore) -> None:
        super().__init__(workbook_path)

    def list_agencies(self) -> list[dict[str, Any]]:
        with self.workbook() as workbook:
            agencies = self.rows(workbook["Agencies"])
        agencies.sort(key=lambda row: str(row.get("name") or "").casefold())
        return agencies

    def get_agency(self, agency_id: str) -> dict[str, Any]:
        agency_id = str(agency_id or "").strip()
        with self.workbook() as workbook:
            agency = self.row_by_key(workbook["Agencies"], "agency_id", agency_id)
        if not agency:
            raise ValueError("未找到 Agency。")
        return agency

    def save_agency(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Agency 数据无效。")
        with self.workbook(write=True) as workbook:
            agency_id = str(payload.get("agency_id") or "").strip()
            existing = (
                self.row_by_key(workbook["Agencies"], "agency_id", agency_id)
                if agency_id
                else {}
            )
            if agency_id and not existing:
                raise ValueError("未找到 Agency。")
            agency_id = agency_id or f"agency_{uuid.uuid4().hex[:16]}"
            name = str(
                payload.get("name") if "name" in payload else existing.get("name") or ""
            ).strip()
            if not name:
                raise ValueError("Agency 名称不能为空。")
            now = utc_now()
            values = {
                **existing,
                "agency_id": agency_id,
                "name": name,
                "created_at": str(existing.get("created_at") or now),
                "updated_at": now,
            }
            for field in AGENCIES_HEADERS:
                if field in {"agency_id", "created_at", "updated_at"}:
                    continue
                if field in payload:
                    values[field] = str(payload.get(field) or "").strip()
            self.upsert_row(workbook["Agencies"], "agency_id", agency_id, values)
        return values

    def list_contacts(self, agency_id: str = "") -> list[dict[str, Any]]:
        agency_id = str(agency_id or "").strip()
        with self.workbook() as workbook:
            contacts = self.rows(workbook["AgencyContacts"])
        if agency_id:
            contacts = [
                row
                for row in contacts
                if str(row.get("agency_id") or "") == agency_id
            ]
        contacts.sort(key=lambda row: str(row.get("name") or "").casefold())
        return contacts

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        contact_id = str(contact_id or "").strip()
        with self.workbook() as workbook:
            contact = self.row_by_key(
                workbook["AgencyContacts"], "contact_id", contact_id
            )
        if not contact:
            raise ValueError("未找到 Agency 联系人。")
        return contact

    def save_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("联系人数据无效。")
        with self.workbook(write=True) as workbook:
            contact_id = str(payload.get("contact_id") or "").strip()
            existing = (
                self.row_by_key(
                    workbook["AgencyContacts"], "contact_id", contact_id
                )
                if contact_id
                else {}
            )
            if contact_id and not existing:
                raise ValueError("未找到 Agency 联系人。")
            agency_id = str(
                payload.get("agency_id")
                if "agency_id" in payload
                else existing.get("agency_id") or ""
            ).strip()
            if agency_id and not self.row_by_key(
                workbook["Agencies"], "agency_id", agency_id
            ):
                raise ValueError("联系人关联的 Agency 不存在。")
            name = str(
                payload.get("name") if "name" in payload else existing.get("name") or ""
            ).strip()
            if not name:
                raise ValueError("联系人姓名不能为空。")
            contact_id = contact_id or f"contact_{uuid.uuid4().hex[:16]}"
            now = utc_now()
            values = {
                **existing,
                "contact_id": contact_id,
                "name": name,
                "agency_id": agency_id,
                "created_at": str(existing.get("created_at") or now),
                "updated_at": now,
            }
            for field in AGENCY_CONTACTS_HEADERS:
                if field in {"contact_id", "name", "agency_id", "created_at", "updated_at"}:
                    continue
                if field in payload:
                    values[field] = str(payload.get(field) or "").strip()
            self.upsert_row(
                workbook["AgencyContacts"], "contact_id", contact_id, values
            )
        return values

    def upsert_external_contact(
        self,
        external_record_id: str,
        *,
        name: str,
        whatsapp: str = "",
        source: str = "feishu_compat",
    ) -> dict[str, Any]:
        external_record_id = str(external_record_id or "").strip()
        if not external_record_id:
            raise ValueError("外部联系人标识不能为空。")
        with self.workbook(write=True) as workbook:
            existing = self.row_by_key(
                workbook["AgencyContacts"],
                "external_record_id",
                external_record_id,
            )
            contact_id = str(
                existing.get("contact_id")
                or f"contact_{hashlib.sha256(external_record_id.encode('utf-8')).hexdigest()[:16]}"
            )
            now = utc_now()
            values = {
                **existing,
                "contact_id": contact_id,
                "name": str(name or existing.get("name") or "").strip(),
                "agency_id": str(existing.get("agency_id") or ""),
                "whatsapp": str(whatsapp or existing.get("whatsapp") or "").strip(),
                "external_record_id": external_record_id,
                "source": str(source or "feishu_compat"),
                "created_at": str(existing.get("created_at") or now),
                "updated_at": now,
            }
            self.upsert_row(
                workbook["AgencyContacts"], "contact_id", contact_id, values
            )
        return values
