from __future__ import annotations

"""Read-only SQLite projection for the manual Google Sheets data replica."""

from typing import Any, Protocol


class CreatorInventorySource(Protocol):
    def getCreatorInventoryRows(self) -> dict[str, list[dict[str, Any]]]: ...


class GoogleSheetsDataSyncService:
    """Export the active Feishu-equivalent Creator and Account domains only."""

    def __init__(self, repository: CreatorInventorySource) -> None:
        self._repository = repository

    def assemble(self) -> dict[str, Any]:
        inventory = self._repository.getCreatorInventoryRows()
        creators = sorted(inventory.get("creators") or [], key=lambda row: str(row.get("creator_id") or ""))
        accounts = sorted(inventory.get("accounts") or [], key=lambda row: str(row.get("account_uid") or ""))
        return {"worksheets": [
            self._worksheet("KOLConnect Creators", ("creator_id", "name", "country", "language", "content_category", "archived_at", "created_at", "updated_at"), creators),
            self._worksheet("KOLConnect Creator Accounts", ("account_uid", "creator_id", "platform", "profile_url", "account_name", "followers", "account_email", "created_at", "updated_at"), accounts),
        ]}

    def sync(self, client, spreadsheet: object) -> dict[str, Any]:
        return client.sync_managed_worksheets(spreadsheet, self.assemble()["worksheets"])

    @staticmethod
    def _worksheet(title: str, headers: tuple[str, ...], source: list[dict[str, Any]]) -> dict[str, Any]:
        def cell(value: object) -> object:
            return "" if value is None else value if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
        return {"title": title, "schema_version": "1", "headers": list(headers), "rows": [[cell(row.get(header)) for header in headers] for row in source]}
