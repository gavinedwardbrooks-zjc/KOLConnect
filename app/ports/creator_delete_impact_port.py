from __future__ import annotations

"""Read-only structural data required for a Creator delete-impact preview."""

from typing import Any, Protocol


class CreatorDeleteImpactPort(Protocol):
    def scan_creator_delete_impact(self, creator_id: str) -> dict[str, Any]: ...
