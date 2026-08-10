from __future__ import annotations

"""Creator domain capabilities required by future Task workflows."""

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


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
class EmailRecheckCandidate:
    creator_id: str
    account_id: str
    account_uid: str
    platform: str
    profile_url: str
    username: str = ""
    account_email: str = ""


@dataclass(frozen=True)
class CreatorAnalysisSnapshot:
    creator_id: str
    analysis: Mapping[str, Any]


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
    def import_task_results(
        self, command: ImportTaskResultsCommand
    ) -> CreatorImportSummary: ...

    def get_email_recheck_candidates(self) -> tuple[EmailRecheckCandidate, ...]: ...

    def get_creator_analysis(self, creator_id: str) -> CreatorAnalysisSnapshot: ...

    def upsert_external_agency_contact(
        self, contact: ExternalAgencyContactCommand
    ) -> ExternalAgencyContact: ...
