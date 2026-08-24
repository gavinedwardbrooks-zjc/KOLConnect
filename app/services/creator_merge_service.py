from __future__ import annotations

"""Manual-only Creator merge orchestration."""

from typing import Any, Callable

from local_storage_lock import SharedStorageLockTimeout, shared_storage_lock
from repositories.creator_merge_repository import CreatorMergePlanError, CreatorMergeRepository


class CreatorMergeError(RuntimeError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status

    def to_response(self) -> dict[str, Any]:
        return {"ok": False, "error": self.code}


class CreatorMergeService:
    def __init__(
        self,
        repository_provider: Callable[[], CreatorMergeRepository],
        *,
        cache_invalidators: tuple[Callable[[], None], ...] = (),
        lock_timeout: float | None = None,
    ) -> None:
        self.repository_provider = repository_provider
        self.cache_invalidators = cache_invalidators
        self.lock_timeout = lock_timeout

    def preview(self, primary_creator_id: object, secondary_creator_id: object) -> dict[str, Any]:
        plan = self.repository_provider().preview(
            str(primary_creator_id or "").strip(),
            str(secondary_creator_id or "").strip(),
        )
        return plan

    def execute(
        self,
        primary_creator_id: object,
        secondary_creator_id: object,
        *,
        confirm: object,
        preview_fingerprint: object,
    ) -> dict[str, Any]:
        if confirm is not True:
            raise CreatorMergeError("MERGE_CONFIRMATION_REQUIRED", 400)
        fingerprint = str(preview_fingerprint or "").strip()
        if not fingerprint:
            raise CreatorMergeError("STALE_PREVIEW", 409)
        options = {} if self.lock_timeout is None else {"timeout": self.lock_timeout}
        try:
            with shared_storage_lock(**options):
                result = self.repository_provider().execute(
                    str(primary_creator_id or "").strip(),
                    str(secondary_creator_id or "").strip(),
                    preview_fingerprint=fingerprint,
                )
                for invalidate in self.cache_invalidators:
                    invalidate()
                return {"merged": True, **result}
        except SharedStorageLockTimeout as exc:
            raise CreatorMergeError("SHARED_STORAGE_LOCK_TIMEOUT", 409) from exc
        except CreatorMergePlanError as exc:
            status = 404 if exc.code == "CREATOR_NOT_FOUND" else 409
            raise CreatorMergeError(exc.code, status) from exc
        except Exception as exc:
            raise CreatorMergeError("MERGE_FAILED", 500) from exc
