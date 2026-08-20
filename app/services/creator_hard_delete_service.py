from __future__ import annotations

"""Confirmed Creator hard-delete orchestration over frozen safety boundaries."""

from pathlib import Path
from typing import Any, Callable

from local_storage_lock import SharedStorageLockTimeout, shared_storage_lock
from repositories.creator_hard_delete_repository import (
    CreatorHardDeleteRepository,
    UnsafeCreatorDeletePlan,
)
from services.creator_delete_impact_service import CreatorDeleteImpactService
from staged_delete_transaction import (
    StagedDeleteTransaction,
    list_blocking_delete_transactions,
)


class CreatorHardDeleteError(RuntimeError):
    def __init__(
        self,
        code: str,
        status: int,
        *,
        blockers: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.blockers = list(blockers or [])

    def to_response(self) -> dict[str, Any]:
        response: dict[str, Any] = {"ok": False, "error": self.code}
        if self.code == "DELETE_BLOCKED" and self.blockers:
            response["blockers"] = self.blockers
        return response


ImpactServiceProvider = Callable[[], CreatorDeleteImpactService]
RepositoryProvider = Callable[[], CreatorHardDeleteRepository]
RuntimeDataDirProvider = Callable[[], Path]
ErrorLogger = Callable[[BaseException], None]
CacheInvalidator = Callable[[], None]


class CreatorHardDeleteService:
    """Re-scan and execute one exact delete plan inside one shared lock."""

    def __init__(
        self,
        impact_service_provider: ImpactServiceProvider,
        repository_provider: RepositoryProvider,
        runtime_data_dir_provider: RuntimeDataDirProvider,
        error_logger: ErrorLogger | None = None,
        *,
        lock_timeout: float | None = None,
        creator_library_cache_invalidator: CacheInvalidator | None = None,
    ) -> None:
        self._impact_service_provider = impact_service_provider
        self._repository_provider = repository_provider
        self._runtime_data_dir_provider = runtime_data_dir_provider
        self._error_logger = error_logger or (lambda _exc: None)
        self._lock_timeout = lock_timeout
        self._creator_library_cache_invalidator = creator_library_cache_invalidator

    def delete_creator(
        self,
        creator_id: str,
        *,
        confirm: object,
        preview_fingerprint: object,
    ) -> dict[str, Any]:
        creator_id = str(creator_id or "").strip()
        if confirm is not True:
            raise CreatorHardDeleteError("DELETE_CONFIRMATION_REQUIRED", 400)
        if not isinstance(preview_fingerprint, str) or not preview_fingerprint.strip():
            raise CreatorHardDeleteError("DELETE_PREVIEW_REQUIRED", 400)
        fingerprint = preview_fingerprint.strip()
        lock_options = (
            {} if self._lock_timeout is None else {"timeout": self._lock_timeout}
        )
        try:
            with shared_storage_lock(**lock_options):
                result = self._delete_locked(creator_id, fingerprint)
                if self._creator_library_cache_invalidator is not None:
                    self._creator_library_cache_invalidator()
                return result
        except SharedStorageLockTimeout as exc:
            raise CreatorHardDeleteError("SHARED_STORAGE_LOCK_TIMEOUT", 409) from exc

    def _delete_locked(self, creator_id: str, fingerprint: str) -> dict[str, Any]:
        runtime_data_dir = Path(self._runtime_data_dir_provider())
        if list_blocking_delete_transactions(runtime_data_dir):
            raise CreatorHardDeleteError("CREATOR_DELETE_FAILED", 500)

        try:
            assessment = self._impact_service_provider().inspect_delete_impact(
                creator_id
            )
        except ValueError as exc:
            raise CreatorHardDeleteError("CREATOR_NOT_FOUND", 404) from exc
        except RuntimeError as exc:
            self._log_error_safe(exc)
            raise CreatorHardDeleteError("CREATOR_DELETE_FAILED", 500) from exc

        preview = assessment["preview"]
        blockers = list(preview.get("blockers") or [])
        if not preview.get("can_delete") or blockers:
            raise CreatorHardDeleteError(
                "DELETE_BLOCKED", 409, blockers=blockers
            )
        if preview.get("preview_fingerprint") != fingerprint:
            raise CreatorHardDeleteError("DELETE_PREVIEW_STALE", 409)

        plan = assessment["plan"]
        repository = self._repository_provider()
        transaction = StagedDeleteTransaction(runtime_data_dir, creator_id)
        prepared = False
        committed = False
        try:
            inputs = repository.transaction_inputs(plan)
            preflight = transaction.preflight(
                plan,
                workbook_path=repository.workbook_path,
                artifact_paths=inputs["artifacts"],
                json_paths=inputs["json_paths"],
            )
            if preflight["status"] != "READY":
                raise UnsafeCreatorDeletePlan("Hard-delete preflight failed.")

            protected_state = repository.capture_protected_state(creator_id, plan)
            transaction.prepare()
            prepared = True
            transaction.backup_workbook(repository.store)
            for index, path in enumerate(inputs["json_paths"], start=1):
                transaction.backup_json(path, label=f"shared_json_{index}")
            for path in inputs["artifacts"]:
                transaction.stage_path(path)
            transaction.transition("STAGED")
            transaction.transition("MUTATING")
            repository.apply_json_deletes(transaction, plan)
            repository.delete_workbook_resources(creator_id, plan)
            repository.verify_delete(
                creator_id,
                plan,
                protected_state,
                transaction,
            )
            transaction.transition("COMMITTED")
            committed = True
            cleanup = transaction.finalize_cleanup()
            result = {"creator_id": creator_id, "deleted": True}
            if cleanup["phase"] == "CLEANUP_PENDING":
                result["cleanup_pending"] = True
            return result
        except Exception as exc:
            self._log_error_safe(exc)
            if prepared and not committed:
                try:
                    transaction.rollback()
                except Exception as rollback_exc:
                    self._log_error_safe(rollback_exc)
            if committed:
                return {
                    "creator_id": creator_id,
                    "deleted": True,
                    "cleanup_pending": True,
                }
            raise CreatorHardDeleteError("CREATOR_DELETE_FAILED", 500) from exc

    def _log_error_safe(self, exc: BaseException) -> None:
        try:
            self._error_logger(exc)
        except Exception:
            pass
