from __future__ import annotations

"""Read-only dashboard data access built on top of CreatorRepository."""

from typing import Any

from creator_repository import CreatorRepository


class DashboardRepository:
    """Collect Dashboard source records without exposing workbook access to callers."""

    def __init__(self, creator_repository: CreatorRepository) -> None:
        self._creator_repository = creator_repository
        self._creators: list[dict[str, Any]] | None = None
        self._cooperations: list[dict[str, Any]] | None = None

    def get_creators(self) -> list[dict[str, Any]]:
        if self._creators is None:
            self._creators = self._creator_repository.getCreators()
        return self._creators

    def get_creator_health_records(self) -> list[dict[str, Any]]:
        """Creator records already include the latest snapshot trend and freshness."""
        return self.get_creators()

    def get_cooperation_records(self, creators: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Return cooperation records paired with their Creator Library identity.

        CreatorRepository remains the only component that reads the Excel workbook.
        """
        creators = creators if creators is not None else self.get_creators()
        if self._cooperations is None:
            self._cooperations = self._creator_repository.getCooperations()
        creators_by_id = {
            str(creator.get("creator_id") or creator.get("analysis_id") or ""): creator
            for creator in creators
        }
        cooperations: list[dict[str, Any]] = []
        for cooperation in self._cooperations:
            creator_id = str(cooperation.get("creator_id") or "")
            if not creator_id:
                continue
            creator = creators_by_id.get(creator_id, {})
            cooperations.append({
                **cooperation,
                "creator_id": creator_id,
                "creator_name": str(creator.get("creator_name") or ""),
                "creator_platform": str(creator.get("platform") or ""),
            })
        return cooperations
