from __future__ import annotations

"""Creator workflows over request-aware repository and port providers."""

from typing import Any, Callable, Protocol

from ports.task_port import TaskPort


class CreatorRepositoryReader(Protocol):
    def saveCreator(self, analysis: dict[str, Any]) -> dict[str, Any]: ...

    def getCreatorsPage(self, **kwargs: Any) -> dict[str, Any]: ...

    def getCreatorDetail(self, creator_id: str) -> dict[str, Any]: ...

    def getCreatorTrend(self, creator_id: str) -> dict[str, Any]: ...

    def getCreatorSnapshots(self, creator_id: str) -> list[dict[str, Any]]: ...

    def getAgencies(self) -> list[dict[str, Any]]: ...

    def getAgencyDetail(self, agency_id: str) -> dict[str, Any]: ...

    def getAgencyContacts(self, agency_id: str = "") -> list[dict[str, Any]]: ...

    def updateCreator(self, creator_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def updateCreatorStatus(self, creator_id: str, status: object) -> dict[str, Any]: ...

    def updateCreatorRelations(
        self, creator_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]: ...

    def saveAgency(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def saveAgencyContact(self, payload: dict[str, Any]) -> dict[str, Any]: ...


RepositoryProvider = Callable[[], CreatorRepositoryReader]
TaskPortProvider = Callable[[], TaskPort]


class CreatorService:
    """Resolve a repository per operation instead of retaining scoped state."""

    def __init__(
        self,
        repository_provider: RepositoryProvider,
        task_port_provider: TaskPortProvider,
    ) -> None:
        self._repository_provider = repository_provider
        self._task_port_provider = task_port_provider

    def get_creator_library(
        self,
        *,
        include_archived: bool = False,
        page: int = 1,
        page_size: int = 24,
        sort: str = "created_at",
        order: str = "desc",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self._repository_provider().getCreatorsPage(
            include_archived=include_archived,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
            filters=filters,
        )
        # Preserve the legacy records alias while clients migrate to creators.
        return {**result, "records": result["creators"]}

    def get_creator_detail(self, creator_id: str) -> dict[str, Any]:
        return self._repository_provider().getCreatorDetail(creator_id)

    def get_creator_trend(self, creator_id: str) -> dict[str, Any]:
        return self._repository_provider().getCreatorTrend(creator_id)

    def get_creator_snapshots(self, creator_id: str) -> dict[str, Any]:
        return {
            "creator_id": creator_id,
            "snapshots": self._repository_provider().getCreatorSnapshots(creator_id),
        }

    def get_agencies(self) -> dict[str, Any]:
        return {"agencies": self._repository_provider().getAgencies()}

    def get_agency_detail(self, agency_id: str) -> dict[str, Any]:
        return self._repository_provider().getAgencyDetail(agency_id)

    def get_agency_contacts(self, agency_id: str = "") -> dict[str, Any]:
        return {"contacts": self._repository_provider().getAgencyContacts(agency_id)}

    def update_creator_profile(
        self, creator_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {"creator": self._repository_provider().updateCreator(creator_id, payload)}

    def update_creator_status(self, creator_id: str, status: object) -> dict[str, Any]:
        return self._repository_provider().updateCreatorStatus(creator_id, status)

    def update_creator_relations(
        self, creator_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._repository_provider().updateCreatorRelations(creator_id, payload)

    def save_agency(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"agency": self._repository_provider().saveAgency(payload)}

    def save_agency_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"contact": self._repository_provider().saveAgencyContact(payload)}

    def import_creator_from_extension(
        self,
        analysis: dict[str, Any],
        *,
        compensation_task_id: str,
    ) -> dict[str, Any]:
        """Persist one prepared Extension analysis through the Creator boundary."""
        try:
            return self._repository_provider().saveCreator(analysis)
        except Exception:
            # Preserve the original import failure even when task cleanup also fails.
            try:
                self._task_port_provider().delete_task(compensation_task_id)
            except Exception:
                pass
            raise

    def get_creator_task(self, creator_id: str) -> dict[str, Any]:
        """Return the existing review task linked to one Creator."""
        detail = self._repository_provider().getCreatorDetail(creator_id)
        task_id = str(detail["record"].get("task_id") or "")
        task = self._task_port_provider().get_task(task_id)
        return {
            "task": task.to_response(),
            "created": False,
            "message": "已打开关联的审核任务。",
        }
