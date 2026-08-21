from __future__ import annotations

"""Read-only source data for campaign publishing and data-quality risks."""

from pathlib import Path
from typing import Any

from data_repository_base import ExcelDataRepository
from excel_workbook_store import ExcelWorkbookStore


class RiskRepository(ExcelDataRepository):
    def __init__(self, workbook_path: Path | ExcelWorkbookStore) -> None:
        super().__init__(workbook_path)

    def read_risk_source(self) -> dict[str, list[dict[str, Any]]]:
        with self.workbook() as workbook:
            return {
                "campaigns": self.rows(workbook["Campaigns"]),
                "campaign_creators": self.rows(workbook["CampaignCreators"]),
                "creators": self.rows(workbook["Creators"]),
                "creator_accounts": self.rows(workbook["CreatorAccounts"]),
            }
