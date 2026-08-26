from __future__ import annotations

"""Request-scoped construction for repositories sharing one workbook store."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from campaign_creator_repository import CampaignCreatorRepository
from campaign_repository import CampaignRepository
from creator_repository import CreatorRepository
from dashboard_repository import DashboardRepository
from excel_workbook_store import ExcelWorkbookStore
from product_repository import ProductRepository
from repositories.agency_repository import AgencyRepository
from repositories.creator_delete_impact_repository import CreatorDeleteImpactRepository
from repositories.creator_hard_delete_repository import CreatorHardDeleteRepository
from repositories.creator_merge_repository import CreatorMergeRepository
from repositories.risk_repository import RiskRepository
from storage.authority import resolve_runtime_authority
from storage.paths import SQLiteStoragePaths
from storage.sqlite_workbook_store import SQLiteWorkbookStore
from storage.sqlite_creator_repository import SQLiteCreatorRepository
from storage.sqlite_campaign_repositories import (
    SQLiteCampaignCreatorRepository,
    SQLiteCampaignRepository,
    SQLiteProductRepository,
)
from storage.sqlite_dashboard_repository import SQLiteDashboardRepository


_ACTIVE_FACTORY: ContextVar[RepositoryFactory | None] = ContextVar(
    "kolconnect_repository_factory",
    default=None,
)


class RepositoryFactory:
    """Create each repository at most once within one request."""

    def __init__(
        self,
        store: ExcelWorkbookStore,
        *,
        legacy_analysis_dir: Path | None = None,
        legacy_library_file: Path | None = None,
        tasks_dir: Path | None = None,
        data_protection_file: Path | None = None,
    ) -> None:
        self.store = store
        self.legacy_analysis_dir = legacy_analysis_dir
        self.legacy_library_file = legacy_library_file
        self.tasks_dir = tasks_dir
        self.data_protection_file = data_protection_file
        self._creator: CreatorRepository | None = None
        self._agency: AgencyRepository | None = None
        self._creator_delete_impact: CreatorDeleteImpactRepository | None = None
        self._creator_hard_delete: CreatorHardDeleteRepository | None = None
        self._creator_merge: CreatorMergeRepository | None = None
        self._product: ProductRepository | None = None
        self._campaign: CampaignRepository | None = None
        self._campaign_creator: CampaignCreatorRepository | None = None
        self._dashboard: DashboardRepository | None = None
        self._risk: RiskRepository | None = None

    @classmethod
    def for_path(
        cls,
        workbook_path: Path,
        *,
        legacy_analysis_dir: Path | None = None,
        legacy_library_file: Path | None = None,
        tasks_dir: Path | None = None,
        data_protection_file: Path | None = None,
    ) -> RepositoryFactory:
        return cls(
            ExcelWorkbookStore(workbook_path),
            legacy_analysis_dir=legacy_analysis_dir,
            legacy_library_file=legacy_library_file,
            tasks_dir=tasks_dir,
            data_protection_file=data_protection_file,
        )

    @classmethod
    def for_runtime(
        cls,
        workbook_path: Path,
        *,
        storage_paths: SQLiteStoragePaths | None = None,
        bootstrap_new_install: bool = False,
        legacy_analysis_dir: Path | None = None,
        legacy_library_file: Path | None = None,
        tasks_dir: Path | None = None,
        data_protection_file: Path | None = None,
    ) -> RepositoryFactory:
        paths = storage_paths or SQLiteStoragePaths.for_app_data()
        authority = resolve_runtime_authority(
            paths,
            workbook_path,
            bootstrap_new_install=bootstrap_new_install,
        )
        store = (
            SQLiteWorkbookStore(authority.database_path)
            if authority.kind == "sqlite" and authority.database_path is not None
            else ExcelWorkbookStore(authority.workbook_path)
        )
        return cls(
            store,
            legacy_analysis_dir=legacy_analysis_dir,
            legacy_library_file=legacy_library_file,
            tasks_dir=tasks_dir,
            data_protection_file=data_protection_file,
        )

    def creator(self) -> CreatorRepository:
        if self._creator is None:
            repository_type = (
                SQLiteCreatorRepository
                if isinstance(self.store, SQLiteWorkbookStore)
                else CreatorRepository
            )
            self._creator = repository_type(
                self.store,
                self.legacy_analysis_dir,
                self.legacy_library_file,
            )
        return self._creator

    def agency(self) -> AgencyRepository:
        if self._agency is None:
            self._agency = AgencyRepository(self.store)
        return self._agency

    def creator_delete_impact(self) -> CreatorDeleteImpactRepository:
        if self._creator_delete_impact is None:
            self._creator_delete_impact = CreatorDeleteImpactRepository(
                self.store,
                tasks_dir=self.tasks_dir,
                data_protection_file=self.data_protection_file,
                legacy_analysis_dir=self.legacy_analysis_dir,
                legacy_library_file=self.legacy_library_file,
            )
        return self._creator_delete_impact

    def creator_hard_delete(self) -> CreatorHardDeleteRepository:
        if self._creator_hard_delete is None:
            self._creator_hard_delete = CreatorHardDeleteRepository(
                self.store,
                tasks_dir=self.tasks_dir,
                data_protection_file=self.data_protection_file,
                legacy_analysis_dir=self.legacy_analysis_dir,
                legacy_library_file=self.legacy_library_file,
            )
        return self._creator_hard_delete

    def creator_merge(self, *, mail_messages_path: Path | None = None) -> CreatorMergeRepository:
        if self._creator_merge is None:
            self._creator_merge = CreatorMergeRepository(
                self.store,
                tasks_dir=self.tasks_dir,
                mail_messages_path=mail_messages_path,
                legacy_library_file=self.legacy_library_file,
            )
        return self._creator_merge

    def product(self) -> ProductRepository:
        if self._product is None:
            repository_type = (
                SQLiteProductRepository
                if isinstance(self.store, SQLiteWorkbookStore)
                else ProductRepository
            )
            self._product = repository_type(self.store)
        return self._product

    def campaign(self) -> CampaignRepository:
        if self._campaign is None:
            repository_type = (
                SQLiteCampaignRepository
                if isinstance(self.store, SQLiteWorkbookStore)
                else CampaignRepository
            )
            self._campaign = repository_type(self.store)
        return self._campaign

    def campaign_creator(self) -> CampaignCreatorRepository:
        if self._campaign_creator is None:
            repository_type = (
                SQLiteCampaignCreatorRepository
                if isinstance(self.store, SQLiteWorkbookStore)
                else CampaignCreatorRepository
            )
            self._campaign_creator = repository_type(self.store)
        return self._campaign_creator

    def risk(self) -> RiskRepository:
        if self._risk is None:
            self._risk = RiskRepository(self.store)
        return self._risk

    def dashboard(
        self,
        creator_repository: CreatorRepository | None = None,
        campaign_creator_repository: CampaignCreatorRepository | None = None,
        campaign_repository: CampaignRepository | None = None,
    ) -> DashboardRepository:
        if self._dashboard is None:
            creator = creator_repository or self.creator()
            if isinstance(self.store, SQLiteWorkbookStore):
                self._dashboard = SQLiteDashboardRepository(creator)
            elif campaign_creator_repository is None and campaign_repository is None:
                self._dashboard = DashboardRepository(creator)
            else:
                self._dashboard = DashboardRepository(
                    creator,
                    campaign_creator_repository or self.campaign_creator(),
                    campaign_repository or self.campaign(),
                )
        return self._dashboard

    @contextmanager
    def request_scope(self) -> Iterator[RepositoryFactory]:
        token = _ACTIVE_FACTORY.set(self)
        try:
            # Keep current immediate-save behavior; deferred transactions are a later phase.
            with self.store.scope(defer_writes=False):
                yield self
        finally:
            _ACTIVE_FACTORY.reset(token)


def get_active_repository_factory() -> RepositoryFactory | None:
    return _ACTIVE_FACTORY.get()
