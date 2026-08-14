from __future__ import annotations

"""Agency domain operations exposed without persistence details."""

from typing import Any, Protocol


class AgencyPort(Protocol):
    def list_agencies(self) -> list[dict[str, Any]]: ...

    def get_agency(self, agency_id: str) -> dict[str, Any]: ...

    def save_agency(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def list_contacts(self, agency_id: str = "") -> list[dict[str, Any]]: ...

    def get_contact(self, contact_id: str) -> dict[str, Any]: ...

    def save_contact(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def upsert_external_contact(
        self,
        external_record_id: str,
        *,
        name: str,
        whatsapp: str = "",
        source: str = "feishu_compat",
    ) -> dict[str, Any]: ...
