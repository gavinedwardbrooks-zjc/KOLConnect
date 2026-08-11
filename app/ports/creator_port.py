from __future__ import annotations

"""Creator domain capabilities required by future Task workflows."""

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ManualTaskPreparationCommand:
    payload: Mapping[str, object]


@dataclass(frozen=True)
class PreparedManualTask:
    task_name: str
    creator_name: str
    platform: str
    profile_url: str
    follower_count: str
    email: str
    whatsapp: str
    note: str
    source_contact_record_id: str = ""
    source_contact_name: str = ""
    source_contact_whatsapp: str = ""
    protected_values: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ManualTaskProtectionCommand:
    task_id: str
    account_uid: str
    values: Mapping[str, str]
    updated_at: str


@dataclass(frozen=True)
class CreatorImportItem:
    account_uid: str
    platform: str
    profile_url: str
    creator_name: str = ""
    followers: str = ""
    email: str = ""
    whatsapp: str = ""
    country: str = ""
    language: str = ""
    content_category: str = ""
    note: str = ""
    latest_post_date: str = ""
    last_scrape_time: str = ""
    data_source: str = ""
    scrape_status: str = ""
    source_contact_id: str = ""
    email_recheck: bool = False


@dataclass(frozen=True)
class ImportTaskResultsCommand:
    task_id: str
    items: tuple[CreatorImportItem, ...]
    source: str
    imported_at: str = ""


@dataclass(frozen=True)
class CreatorImportSummary:
    input_records: int
    created_creators: int
    created_accounts: int
    updated_accounts: int
    duplicate_records: int
    skipped_failed: int
    skipped_invalid: int
    creator_ids: tuple[str, ...]
    account_ids: tuple[str, ...]


@dataclass(frozen=True)
class TaskResultUpdateCommand:
    task_id: str
    account_uid: str
    fields: Mapping[str, object]
    task_type: str
    updated_at: str
    result_fieldnames: tuple[str, ...]
    result_rows: tuple[Mapping[str, object], ...]
    progress_fieldnames: tuple[str, ...]
    progress_rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class PreparedTaskResultUpdate:
    account_uid: str
    modified_fields: Mapping[str, Mapping[str, str]]
    updated_at: str
    data_status: str
    result_fieldnames: tuple[str, ...]
    result_rows: tuple[Mapping[str, object], ...]
    progress_fieldnames: tuple[str, ...]
    progress_rows: tuple[Mapping[str, object], ...]
    protection_values: Mapping[str, str]
    protection_source: str


@dataclass(frozen=True)
class TaskResultImportCommand:
    task_id: str
    task: Mapping[str, object]
    rows: tuple[Mapping[str, object], ...]
    allowed_statuses: tuple[str, ...]


@dataclass(frozen=True)
class CreatorImportResult:
    response: Mapping[str, object]
    imported_at: str = ""
    creator_ids: tuple[str, ...] = ()
    account_ids: tuple[str, ...] = ()
    summary: Mapping[str, object] | None = None


@dataclass(frozen=True)
class EmailRecheckCandidate:
    creator_id: str
    account_id: str
    account_uid: str
    platform: str
    profile_url: str
    username: str = ""
    account_email: str = ""


@dataclass(frozen=True)
class EmailRecheckCandidateScan:
    scanned_accounts: int
    candidates: tuple[EmailRecheckCandidate, ...]
    skipped: tuple[str, ...] = ()
    duplicate_uids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreatorAnalysisSnapshot:
    creator_id: str
    analysis: Mapping[str, Any]


@dataclass(frozen=True)
class FourTableSyncCommand:
    task_id: str
    task: Mapping[str, object]
    rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class PreparedFourTableSync:
    task_id: str
    record_count: int
    results: tuple[Mapping[str, object], ...]
    validation_errors: tuple[str, ...]
    warnings: tuple[str, ...]
    skipped: tuple[str, ...]
    success_records: int
    partial_records: int
    skipped_abnormal: int
    email_recheck_only: bool
    data_source: str
    email_source: str
    source_contact_record_id: str


@dataclass(frozen=True)
class FourTableSyncResult:
    created_creators: int
    created_accounts: int
    updated_accounts: int
    updated_creators: int
    skipped: int
    errors: tuple[str, ...]
    sync_logs: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True)
class ExternalAgencyContactCommand:
    external_record_id: str
    name: str
    whatsapp: str = ""
    source: str = "feishu_compat"


@dataclass(frozen=True)
class ExternalAgencyContact:
    contact_id: str
    external_record_id: str
    name: str
    agency_id: str = ""
    whatsapp: str = ""
    source: str = ""
    created_at: str = ""
    updated_at: str = ""


class CreatorPort(Protocol):
    def prepare_four_table_sync(
        self, command: FourTableSyncCommand
    ) -> PreparedFourTableSync: ...

    def execute_four_table_sync(
        self, prepared: PreparedFourTableSync
    ) -> FourTableSyncResult: ...

    def prepare_manual_task(
        self, command: ManualTaskPreparationCommand
    ) -> PreparedManualTask: ...

    def commit_manual_task_protection(
        self, command: ManualTaskProtectionCommand
    ) -> None: ...

    def import_task_results(
        self, command: ImportTaskResultsCommand | TaskResultImportCommand
    ) -> CreatorImportSummary | CreatorImportResult: ...

    def prepare_task_result_update(
        self, command: TaskResultUpdateCommand
    ) -> PreparedTaskResultUpdate: ...

    def commit_task_result_protection(
        self, task_id: str, update: PreparedTaskResultUpdate
    ) -> None: ...

    def get_email_recheck_candidates(self) -> EmailRecheckCandidateScan: ...

    def get_creator_analysis(self, creator_id: str) -> CreatorAnalysisSnapshot: ...

    def upsert_external_agency_contact(
        self, contact: ExternalAgencyContactCommand
    ) -> ExternalAgencyContact: ...
