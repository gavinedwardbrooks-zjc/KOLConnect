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
    ) -> None:
        self.store = store
        self.legacy_analysis_dir = legacy_analysis_dir
        self.legacy_library_file = legacy_library_file
        self._creator: CreatorRepository | None = None
        self._product: ProductRepository | None = None
        self._campaign: CampaignRepository | None = None
        self._campaign_creator: CampaignCreatorRepository | None = None
        self._dashboard: DashboardRepository | None = None

    @classmethod
    def for_path(
        cls,
        workbook_path: Path,
        *,
        legacy_analysis_dir: Path | None = None,
        legacy_library_file: Path | None = None,
    ) -> RepositoryFactory:
        return cls(
            ExcelWorkbookStore(workbook_path),
            legacy_analysis_dir=legacy_analysis_dir,
            legacy_library_file=legacy_library_file,
        )

    def creator(self) -> CreatorRepository:
        if self._creator is None:
            self._creator = CreatorRepository(
                self.store,
                self.legacy_analysis_dir,
                self.legacy_library_file,
            )
        return self._creator

    def product(self) -> ProductRepository:
        if self._product is None:
            self._product = ProductRepository(self.store)
        return self._product

    def campaign(self) -> CampaignRepository:
        if self._campaign is None:
            self._campaign = CampaignRepository(self.store)
        return self._campaign

    def campaign_creator(self) -> CampaignCreatorRepository:
        if self._campaign_creator is None:
            self._campaign_creator = CampaignCreatorRepository(self.store)
        return self._campaign_creator

    def dashboard(
        self,
        creator_repository: CreatorRepository | None = None,
        campaign_creator_repository: CampaignCreatorRepository | None = None,
        campaign_repository: CampaignRepository | None = None,
    ) -> DashboardRepository:
        if self._dashboard is None:
            creator = creator_repository or self.creator()
            if campaign_creator_repository is None and campaign_repository is None:
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
