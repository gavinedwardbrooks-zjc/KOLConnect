from __future__ import annotations

"""Narrow task capabilities required by future Creator workflows."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class ManualReviewTaskCommand:
    normalized_links: tuple[str, ...]
    invalid_links: tuple[str, ...] = ()
    input_count: int = 0
    name: str = ""
    target_platform: str = "全部"
    platforms: tuple[str, ...] = ()
    platform_summary: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorImportLinkage:
    creator_id: str
    snapshot_id: str
    imported_at: str
    country: str = ""
    language: str = ""
    content_category: str = ""


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    name: str
    task_type: str
    status: str
    created_at: str
    started_at: str = ""
    finished_at: str = ""
    input_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    target_platform: str = "全部"
    platforms: tuple[str, ...] = ()
    creator_analysis_id: str = ""
    creator_snapshot_id: str = ""
    creator_analysis_imported_at: str = ""
    extension_country: str = ""
    extension_language: str = ""
    extension_content_category: str = ""
    _response: Mapping[str, object] = field(
        default_factory=dict, repr=False, compare=False
    )

    def to_response(self) -> dict[str, object]:
        """Return detached public task metadata for compatibility responses."""
        return deepcopy(dict(self._response))


@dataclass(frozen=True)
class CreatedTask:
    task: TaskSnapshot


class TaskPort(Protocol):
    def create_manual_review_task(
        self, command: ManualReviewTaskCommand
    ) -> CreatedTask: ...

    def get_task(self, task_id: str) -> TaskSnapshot: ...

    def attach_creator_import(
        self, task_id: str, linkage: CreatorImportLinkage
    ) -> TaskSnapshot: ...

    def delete_task(self, task_id: str) -> None: ...
