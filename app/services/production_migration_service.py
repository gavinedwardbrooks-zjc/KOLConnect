from __future__ import annotations

"""Two-stage, local-user-controlled production SQLite migration."""

from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Callable

from local_storage_lock import shared_storage_lock
from runtime_paths import load_json_with_backup
from services.assistant_confirmation_store import AssistantConfirmationStore, ConfirmationError
from storage.errors import SQLiteActivationError, StorageError
from storage.migration import (
    ExcelToSQLiteMigrator,
    MigrationResult,
    ProductionActivationAuthorization,
    resolve_authority,
    validate_source_workbook,
)
from storage.paths import SQLiteStoragePaths


MIGRATION_CONFIRMATION_INTENT = "production_sqlite_activation"


class ProductionMigrationError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ProductionMigrationService:
    def __init__(
        self,
        paths: SQLiteStoragePaths,
        source_workbook_provider: Callable[[], Path],
        *,
        production_root_provider: Callable[[], Path],
        confirmations: AssistantConfirmationStore | None = None,
        migrator_factory: Callable[[], ExcelToSQLiteMigrator] | None = None,
    ) -> None:
        self.paths = paths
        self.source_workbook_provider = source_workbook_provider
        self.production_root_provider = production_root_provider
        self.confirmations = confirmations or AssistantConfirmationStore(ttl_seconds=300)
        self.migrator_factory = migrator_factory or (
            lambda: ExcelToSQLiteMigrator(
                self.paths,
                production_root_provider=self.production_root_provider,
            )
        )
        self._lock = threading.RLock()

    def status(self) -> dict[str, object]:
        authority = resolve_authority(self.paths)
        source = Path(self.source_workbook_provider())
        latest = self._latest_manifest()
        phase = str(latest.get("phase") or "") if latest else ""
        migration_id = str(latest.get("migration_id") or "") if latest else ""
        if phase in {"activation_authorized", "database_activated", "authority_activated"}:
            migration_status = "activation_recovery_required"
        elif authority == "sqlite_active":
            migration_status = "completed"
        elif phase == "ready_for_activation":
            migration_status = "ready_for_activation"
        elif phase in {"prepared", "source_validated", "backup_created", "schema_created", "data_imported", "validated"}:
            migration_status = "migration_in_progress"
        elif phase == "failed":
            migration_status = "migration_error"
        elif phase == "cancelled":
            migration_status = "cancelled"
        else:
            migration_status = "available" if source.is_file() else "not_required"
        return {
            "status": "success",
            "authority": authority,
            "migration_required": authority == "legacy_excel" and source.is_file(),
            "migration_status": migration_status,
            "migration_id": migration_id,
            "source_valid": source.is_file(),
            "backup_ready": bool(latest and latest.get("backup_name")),
            "staged_ready": phase == "ready_for_activation",
            "confirmation_required": phase == "ready_for_activation",
            "last_error_code": str(latest.get("failure_code") or "") if latest else "",
        }

    def prepare(self, *, session_id: str) -> dict[str, object]:
        session_id = self._session(session_id)
        with self._lock, shared_storage_lock():
            self._assert_canonical_root()
            authority = resolve_authority(self.paths)
            if authority == "sqlite_active":
                raise ProductionMigrationError("SQLITE_ALREADY_ACTIVE")
            if authority != "legacy_excel":
                raise ProductionMigrationError("SQLITE_MIGRATION_STATE_INVALID")
            latest = self._latest_manifest()
            if latest:
                phase = str(latest.get("phase") or "")
                if phase == "ready_for_activation":
                    result = self._result_from_manifest(latest)
                    return self._prepared_response(result, session_id)
                if phase in {"prepared", "source_validated", "backup_created", "schema_created", "data_imported", "validated"}:
                    raise ProductionMigrationError("SQLITE_MIGRATION_IN_PROGRESS")
            source = Path(self.source_workbook_provider())
            if not source.is_file():
                raise ProductionMigrationError("SQLITE_MIGRATION_SOURCE_MISSING")
            try:
                result = self.migrator_factory().migrate(source)
            except StorageError as exc:
                raise ProductionMigrationError(getattr(exc, "code", "SQLITE_MIGRATION_FAILED")) from exc
            return self._prepared_response(result, session_id)

    def confirm(self, *, migration_id: str, token: str, session_id: str) -> dict[str, object]:
        session_id = self._session(session_id)
        with self._lock, shared_storage_lock():
            try:
                record = self.confirmations.consume(token, session_id)
            except ConfirmationError as exc:
                raise ProductionMigrationError(str(exc)) from exc
            if (
                record.intent != MIGRATION_CONFIRMATION_INTENT
                or str(record.arguments.get("migration_id") or "") != str(migration_id or "")
            ):
                raise ProductionMigrationError("CONFIRMATION_MISMATCH")
            manifest = self._manifest(migration_id)
            result = self._result_from_manifest(manifest)
            authorization = ProductionActivationAuthorization(
                migration_id=result.migration_id,
                source_sha256=str(record.arguments.get("source_sha256") or ""),
                confirmed_at=_utc_now(),
            )
            try:
                path = self.migrator_factory().activate_production(
                    result,
                    source_workbook=Path(self.source_workbook_provider()),
                    authorization=authorization,
                )
            except Exception as exc:
                code = getattr(exc, "code", "") or str(exc)
                if "SOURCE_CHANGED" in code:
                    code = "SQLITE_MIGRATION_SOURCE_CHANGED"
                raise ProductionMigrationError(code or "SQLITE_ACTIVATION_FAILED") from exc
            return {
                "status": "success",
                "authority": "sqlite_active",
                "migration_id": result.migration_id,
                "database_name": path.name,
                "legacy_workbook_retained": True,
            }

    def cancel(self, *, migration_id: str, token: str, session_id: str) -> dict[str, object]:
        session_id = self._session(session_id)
        with self._lock, shared_storage_lock():
            if not self.confirmations.discard(token, session_id):
                raise ProductionMigrationError("CONFIRMATION_MISMATCH")
            manifest = self._manifest(migration_id)
            if manifest.get("phase") != "ready_for_activation":
                raise ProductionMigrationError("SQLITE_MIGRATION_NOT_CANCELLABLE")
            staged = self.paths.staged_database_path(migration_id)
            if staged.exists():
                staged.unlink()
            manifest["phase"] = "cancelled"
            manifest["activation_state"] = "inactive"
            manifest["updated_at"] = _utc_now()
            from runtime_paths import atomic_write_json
            atomic_write_json(self.paths.migration_manifest_path(migration_id), manifest)
            return {"status": "cancelled", "authority": "legacy_excel", "migration_id": migration_id}

    def recover(self, migration_id: str) -> dict[str, object]:
        with self._lock, shared_storage_lock():
            try:
                path = self.migrator_factory().recover_production_activation(migration_id)
            except SQLiteActivationError as exc:
                if "did not cross commit point" in str(exc):
                    return {
                        "status": "ready_for_activation",
                        "authority": "legacy_excel",
                        "migration_id": migration_id,
                        "confirmation_required": True,
                    }
                raise ProductionMigrationError(str(exc) or "SQLITE_ACTIVATION_RECOVERY_FAILED") from exc
            return {"status": "success", "authority": "sqlite_active", "database_name": path.name}

    def _assert_canonical_root(self) -> None:
        if self.paths.app_data_dir.resolve() != Path(self.production_root_provider()).resolve():
            raise ProductionMigrationError("SQLITE_PRODUCTION_ROOT_MISMATCH")

    def _prepared_response(self, result: MigrationResult, session_id: str) -> dict[str, object]:
        self.confirmations.discard_intent(MIGRATION_CONFIRMATION_INTENT)
        record = self.confirmations.create(
            session_id,
            MIGRATION_CONFIRMATION_INTENT,
            {"migration_id": result.migration_id, "source_sha256": result.source_sha256_before},
            result.migration_id,
        )
        return {
            "status": "ready_for_activation",
            "migration_id": result.migration_id,
            "source_sha256": result.source_sha256_before,
            "backup": {"filename": result.backup_path.name},
            "counts": dict(result.counts),
            "validation_status": "passed",
            "staged_ready": True,
            "authority_before": "legacy_excel",
            "warnings": [],
            "confirmation_required": True,
            "confirmation_token": record.token,
            "confirmation_expires_at": record.expires_at.isoformat(),
        }

    def _latest_manifest(self) -> dict[str, object] | None:
        if not self.paths.migrations_dir.is_dir():
            return None
        manifests = sorted(self.paths.migrations_dir.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for path in manifests:
            value, _source = load_json_with_backup(path)
            if isinstance(value, dict):
                return value
        return None

    def _manifest(self, migration_id: str) -> dict[str, object]:
        value, _source = load_json_with_backup(self.paths.migration_manifest_path(str(migration_id or "")))
        if not isinstance(value, dict) or value.get("migration_id") != migration_id:
            raise ProductionMigrationError("SQLITE_MIGRATION_NOT_FOUND")
        return value

    def _result_from_manifest(self, manifest: dict[str, object]) -> MigrationResult:
        migration_id = str(manifest.get("migration_id") or "")
        if not migration_id or manifest.get("phase") != "ready_for_activation":
            raise ProductionMigrationError("SQLITE_MIGRATION_NOT_READY")
        return MigrationResult(
            migration_id=migration_id,
            manifest_path=self.paths.migration_manifest_path(migration_id),
            staged_database_path=self.paths.staged_database_path(migration_id),
            backup_path=self.paths.migration_backup_dir / str(manifest.get("backup_name") or ""),
            source_sha256_before=str(manifest.get("source_sha256") or ""),
            source_sha256_after=str(manifest.get("source_sha256") or ""),
            counts=dict(manifest.get("counts") or {}),
            semantic_digest=str(manifest.get("semantic_digest") or ""),
        )

    @staticmethod
    def _session(value: str) -> str:
        session = str(value or "").strip()
        if not session:
            raise ProductionMigrationError("MIGRATION_SESSION_REQUIRED")
        return session
