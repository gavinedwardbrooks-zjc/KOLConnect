from __future__ import annotations

"""Read-only dashboard data access built on top of CreatorRepository."""

from typing import Any

from creator_repository import CreatorRepository


class DashboardRepository:
    """Collect Dashboard source records without exposing workbook access to callers."""

    def __init__(self, creator_repository: CreatorRepository) -> None:
        self._creator_repository = creator_repository

    def get_creators(self) -> list[dict[str, Any]]:
        return self._creator_repository.getCreators()

    def get_creator_health_records(self) -> list[dict[str, Any]]:
        """Creator records already include the latest snapshot trend and freshness."""
        return self.get_creators()

    def get_cooperation_records(self, creators: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Return cooperation records paired with their Creator Library identity.

        CreatorRepository remains the only component that reads the Excel workbook.
        """
        creators = creators if creators is not None else self.get_creators()
        cooperations: list[dict[str, Any]] = []
        for creator in creators:
            creator_id = str(creator.get("creator_id") or creator.get("analysis_id") or "")
            if not creator_id:
                continue
            for cooperation in self._creator_repository.getCreatorCooperations(creator_id):
                cooperations.append({
                    **cooperation,
                    "creator_id": creator_id,
                    "creator_name": str(creator.get("creator_name") or ""),
                    "creator_platform": str(creator.get("platform") or ""),
                })
        return cooperations
