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
class ManualTaskCreateCommand:
    normalized_url: str
    task_name: str
    platform: str
    platform_summary: Mapping[str, int] = field(default_factory=dict)
    defer_library_import: bool = True


@dataclass(frozen=True)
class ManualTaskInitializationCommand:
    creator_name: str
    platform: str
    profile_url: str
    follower_count: str = ""
    email: str = ""
    whatsapp: str = ""
    note: str = ""
    source_contact_record_id: str = ""
    source_contact_name: str = ""
    local_source_contact_id: str = ""


@dataclass(frozen=True)
class ManualTaskCreationResult:
    task: TaskSnapshot
    account_uid: str
    modified_at: str


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
    profile: str = ""
    _response: Mapping[str, object] = field(
        default_factory=dict, repr=False, compare=False
    )

    def to_response(self) -> dict[str, object]:
        """Return detached public task metadata for compatibility responses."""
        return deepcopy(dict(self._response))


@dataclass(frozen=True)
class CreatedTask:
    task: TaskSnapshot


@dataclass(frozen=True)
class TaskReadResult:
    _response: Mapping[str, object] = field(repr=False)

    def to_response(self) -> dict[str, object]:
        """Return a detached read model without exposing task file locations."""
        return deepcopy(dict(self._response))


@dataclass(frozen=True)
class TaskLinksUpdateCommand:
    action: str
    index: object = None
    url: str = ""


@dataclass(frozen=True)
class RetryFailedResultsCommand:
    account_uids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmailRecheckTaskItem:
    account_uid: str
    platform: str
    profile_url: str
    username: str = ""


@dataclass(frozen=True)
class EmailRecheckTaskCommand:
    items: tuple[EmailRecheckTaskItem, ...]
    name: str
    platform_summary: Mapping[str, int] = field(default_factory=dict)
    skipped_count: int = 0


@dataclass(frozen=True)
class TaskResultImportLinkage:
    imported_at: str
    creator_ids: tuple[str, ...]
    account_ids: tuple[str, ...]
    summary: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskSyncStatusUpdate:
    status: str
    synced_at: str
    data_source: str
    summary: Mapping[str, object]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    sync_log: tuple[Mapping[str, object], ...] | None = None


class TaskPort(Protocol):
    def create_manual_task(self, command: ManualTaskCreateCommand) -> CreatedTask: ...

    def initialize_manual_task(
        self, task_id: str, command: ManualTaskInitializationCommand
    ) -> ManualTaskCreationResult: ...

    def create_manual_review_task(
        self, command: ManualReviewTaskCommand
    ) -> CreatedTask: ...

    def create_email_recheck_task(
        self, command: EmailRecheckTaskCommand
    ) -> CreatedTask: ...

    def get_task(self, task_id: str) -> TaskSnapshot: ...

    def get_tasks(self) -> TaskReadResult: ...

    def get_task_details(self, task_id: str) -> TaskReadResult: ...

    def get_task_results(self, task_id: str) -> TaskReadResult: ...

    def get_scrape_status(self) -> TaskReadResult: ...

    def resume_task(self, task_id: str) -> TaskSnapshot: ...

    def stop_task(self, task_id: str) -> TaskSnapshot: ...

    def rename_task(self, task_id: str, name: str) -> TaskSnapshot: ...

    def update_task_links(
        self, task_id: str, command: TaskLinksUpdateCommand
    ) -> TaskReadResult: ...

    def retry_failed_results(
        self, task_id: str, command: RetryFailedResultsCommand
    ) -> TaskReadResult: ...

    def attach_creator_import(
        self, task_id: str, linkage: CreatorImportLinkage
    ) -> TaskSnapshot: ...

    def attach_task_result_import(
        self, task_id: str, linkage: TaskResultImportLinkage
    ) -> TaskSnapshot: ...

    def update_sync_status(
        self, task_id: str, update: TaskSyncStatusUpdate
    ) -> TaskSnapshot: ...

    def delete_task(self, task_id: str) -> None: ...
