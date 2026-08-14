from __future__ import annotations

"""Agency business facade over request-scoped persistence providers."""

from typing import Any, Callable, Protocol

from ports.agency_port import AgencyPort


class CreatorAgencyReader(Protocol):
    def getCreatorsByAgency(self, agency_id: str) -> list[dict[str, Any]]: ...

    def getCreatorCountsByAgency(self) -> dict[str, int]: ...


AgencyPortProvider = Callable[[], AgencyPort]
CreatorReaderProvider = Callable[[], CreatorAgencyReader]


class AgencyService:
    def __init__(
        self,
        agency_port_provider: AgencyPortProvider,
        creator_reader_provider: CreatorReaderProvider,
    ) -> None:
        self._agency_port_provider = agency_port_provider
        self._creator_reader_provider = creator_reader_provider

    def get_agencies(self) -> dict[str, Any]:
        port = self._agency_port_provider()
        creator_counts = self._creator_reader_provider().getCreatorCountsByAgency()
        contact_counts: dict[str, int] = {}
        for contact in port.list_contacts():
            agency_id = str(contact.get("agency_id") or "")
            if agency_id:
                contact_counts[agency_id] = contact_counts.get(agency_id, 0) + 1
        agencies = [
            {
                **agency,
                "creator_count": creator_counts.get(
                    str(agency.get("agency_id") or ""), 0
                ),
                "contact_count": contact_counts.get(
                    str(agency.get("agency_id") or ""), 0
                ),
            }
            for agency in port.list_agencies()
        ]
        return {"agencies": agencies}

    def get_agency_detail(self, agency_id: str) -> dict[str, Any]:
        port = self._agency_port_provider()
        agency = port.get_agency(agency_id)
        return {
            "agency": agency,
            "contacts": port.list_contacts(agency_id),
            "creators": self._creator_reader_provider().getCreatorsByAgency(agency_id),
        }

    def get_agency_contacts(self, agency_id: str = "") -> dict[str, Any]:
        return {"contacts": self._agency_port_provider().list_contacts(agency_id)}

    def save_agency(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"agency": self._agency_port_provider().save_agency(payload)}

    def save_agency_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"contact": self._agency_port_provider().save_contact(payload)}

    def upsert_external_contact(
        self,
        external_record_id: str,
        *,
        name: str,
        whatsapp: str = "",
        source: str = "feishu_compat",
    ) -> dict[str, Any]:
        return self._agency_port_provider().upsert_external_contact(
            external_record_id,
            name=name,
            whatsapp=whatsapp,
            source=source,
        )
