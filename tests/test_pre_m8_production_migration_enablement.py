from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = ROOT / "tests"
for value in (str(APP), str(TESTS)):
    if value not in sys.path:
        sys.path.insert(0, value)

from services.assistant_confirmation_store import AssistantConfirmationStore
from services.production_migration_service import ProductionMigrationError, ProductionMigrationService
from storage.migration import ExcelToSQLiteMigrator, resolve_authority
from storage.paths import SQLiteStoragePaths
from test_pre_m8_excel_sqlite_migration import build_fixture
from runtime_paths import atomic_write_json


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductionMigrationEnablementTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = ROOT / ".pre_m8_batch3_acceptance"
        parent.mkdir(exist_ok=True)
        self.root = parent / f"production_enablement_{uuid4().hex}"
        self.root.mkdir()
        self.app_data = self.root / "fake_production"
        self.app_data.mkdir()
        self.source = self.app_data / "Creator_Library.xlsx"
        build_fixture(self.source)
        self.paths = SQLiteStoragePaths.for_app_data(self.app_data)
        self.lock_patch = patch(
            "local_storage_lock.get_shared_storage_lock_path",
            return_value=self.root / "locks" / "shared_storage.lock",
        )
        self.lock_patch.start()

    def tearDown(self) -> None:
        self.lock_patch.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def service(self, **kwargs) -> ProductionMigrationService:
        return ProductionMigrationService(
            self.paths,
            lambda: self.source,
            production_root_provider=lambda: self.app_data,
            **kwargs,
        )

    def test_prepare_creates_valid_backup_and_requires_confirmation(self) -> None:
        before = digest(self.source)
        result = self.service().prepare(session_id="settings-a")
        self.assertEqual("ready_for_activation", result["status"])
        self.assertTrue(result["confirmation_required"])
        self.assertEqual(before, result["source_sha256"])
        self.assertEqual(before, digest(self.source))
        backup = self.paths.migration_backup_dir / result["backup"]["filename"]
        self.assertTrue(backup.is_file())
        self.assertEqual(before, digest(backup))
        self.assertTrue(self.paths.staged_database_path(result["migration_id"]).is_file())
        self.assertEqual("legacy_excel", resolve_authority(self.paths))

    def test_activation_requires_matching_single_use_session_confirmation(self) -> None:
        service = self.service()
        prepared = service.prepare(session_id="settings-a")
        with self.assertRaisesRegex(ProductionMigrationError, "CONFIRMATION_MISMATCH"):
            service.confirm(
                migration_id=prepared["migration_id"],
                token=prepared["confirmation_token"],
                session_id="settings-b",
            )
        activated = service.confirm(
            migration_id=prepared["migration_id"],
            token=prepared["confirmation_token"],
            session_id="settings-a",
        )
        self.assertEqual("sqlite_active", activated["authority"])
        self.assertTrue(self.source.is_file())
        with self.assertRaisesRegex(ProductionMigrationError, "CONFIRMATION_ALREADY_USED"):
            service.confirm(
                migration_id=prepared["migration_id"],
                token=prepared["confirmation_token"],
                session_id="settings-a",
            )

    def test_source_change_staged_missing_and_corrupt_fail_closed(self) -> None:
        cases = ("source", "missing", "corrupt")
        for case in cases:
            with self.subTest(case=case):
                child = self.root / case
                child.mkdir()
                source = child / "Creator_Library.xlsx"
                build_fixture(source)
                paths = SQLiteStoragePaths.for_app_data(child)
                service = ProductionMigrationService(
                    paths,
                    lambda source=source: source,
                    production_root_provider=lambda child=child: child,
                )
                prepared = service.prepare(session_id="s")
                staged = paths.staged_database_path(prepared["migration_id"])
                if case == "source":
                    source.write_bytes(source.read_bytes() + b"changed")
                elif case == "missing":
                    staged.unlink()
                else:
                    staged.write_bytes(b"not sqlite")
                with self.assertRaises(ProductionMigrationError):
                    service.confirm(
                        migration_id=prepared["migration_id"],
                        token=prepared["confirmation_token"],
                        session_id="s",
                    )
                self.assertEqual("legacy_excel", resolve_authority(paths))

    def test_cancel_invalidates_confirmation_retains_backup_and_source(self) -> None:
        service = self.service()
        before = digest(self.source)
        prepared = service.prepare(session_id="s")
        backup = self.paths.migration_backup_dir / prepared["backup"]["filename"]
        result = service.cancel(
            migration_id=prepared["migration_id"],
            token=prepared["confirmation_token"],
            session_id="s",
        )
        self.assertEqual("cancelled", result["status"])
        self.assertTrue(backup.is_file())
        self.assertEqual(before, digest(self.source))
        self.assertFalse(self.paths.staged_database_path(prepared["migration_id"]).exists())
        self.assertEqual("legacy_excel", resolve_authority(self.paths))

    def test_new_preparation_invalidates_previous_confirmation(self) -> None:
        service = self.service()
        first = service.prepare(session_id="s")
        second = service.prepare(session_id="s")
        self.assertEqual(first["migration_id"], second["migration_id"])
        with self.assertRaisesRegex(ProductionMigrationError, "CONFIRMATION_ALREADY_USED"):
            service.confirm(
                migration_id=first["migration_id"],
                token=first["confirmation_token"],
                session_id="s",
            )

    def test_confirmation_expiry_fails_closed(self) -> None:
        current = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        store = AssistantConfirmationStore(ttl_seconds=1, now=lambda: current[0])
        service = self.service(confirmations=store)
        prepared = service.prepare(session_id="s")
        current[0] += timedelta(seconds=2)
        with self.assertRaisesRegex(ProductionMigrationError, "CONFIRMATION_EXPIRED"):
            service.confirm(
                migration_id=prepared["migration_id"],
                token=prepared["confirmation_token"],
                session_id="s",
            )
        self.assertEqual("legacy_excel", resolve_authority(self.paths))

    def test_interrupted_activation_recovers_only_after_database_commit_point(self) -> None:
        def migrator() -> ExcelToSQLiteMigrator:
            return ExcelToSQLiteMigrator(
                self.paths,
                production_root_provider=lambda: self.app_data,
                failure_injector=lambda phase: (
                    (_ for _ in ()).throw(RuntimeError("stop after db publication"))
                    if phase == "database_activated" else None
                ),
            )

        service = self.service(migrator_factory=migrator)
        prepared = service.prepare(session_id="s")
        with self.assertRaises(ProductionMigrationError):
            service.confirm(
                migration_id=prepared["migration_id"],
                token=prepared["confirmation_token"],
                session_id="s",
            )
        self.assertTrue(self.paths.database_path.is_file())
        self.assertEqual("legacy_excel", resolve_authority(self.paths))
        recovery = self.service().recover(prepared["migration_id"])
        self.assertEqual("sqlite_active", recovery["authority"])

    def test_crash_after_authority_marker_recovers_manifest_completion(self) -> None:
        def migrator() -> ExcelToSQLiteMigrator:
            return ExcelToSQLiteMigrator(
                self.paths,
                production_root_provider=lambda: self.app_data,
                failure_injector=lambda phase: (
                    (_ for _ in ()).throw(RuntimeError("stop after marker"))
                    if phase == "authority_marker_written" else None
                ),
            )

        service = self.service(migrator_factory=migrator)
        prepared = service.prepare(session_id="s")
        with self.assertRaises(ProductionMigrationError):
            service.confirm(
                migration_id=prepared["migration_id"],
                token=prepared["confirmation_token"],
                session_id="s",
            )
        self.assertEqual("sqlite_active", resolve_authority(self.paths))
        recovered = self.service().recover(prepared["migration_id"])
        self.assertEqual("sqlite_active", recovered["authority"])

    def test_database_publication_failure_returns_to_explicit_confirmation(self) -> None:
        def migrator() -> ExcelToSQLiteMigrator:
            return ExcelToSQLiteMigrator(
                self.paths,
                production_root_provider=lambda: self.app_data,
                failure_injector=lambda phase: (
                    (_ for _ in ()).throw(RuntimeError("stop before publication"))
                    if phase == "activation_authorized" else None
                ),
            )

        service = self.service(migrator_factory=migrator)
        prepared = service.prepare(session_id="s")
        with self.assertRaises(ProductionMigrationError):
            service.confirm(
                migration_id=prepared["migration_id"],
                token=prepared["confirmation_token"],
                session_id="s",
            )
        self.assertEqual("legacy_excel", resolve_authority(self.paths))
        recovery = self.service().recover(prepared["migration_id"])
        self.assertEqual("ready_for_activation", recovery["status"])
        replacement = self.service().prepare(session_id="s")
        self.assertNotEqual(prepared["confirmation_token"], replacement["confirmation_token"])

    def test_in_progress_failed_and_ready_status_are_explicit(self) -> None:
        self.paths.ensure_migration_directories()
        migration_id = "status-case"
        manifest_path = self.paths.migration_manifest_path(migration_id)
        manifest_path.parent.mkdir(parents=True)
        base = {"migration_id": migration_id, "backup_name": "backup.xlsx", "failure_code": ""}
        atomic_write_json(manifest_path, {**base, "phase": "data_imported"})
        self.assertEqual("migration_in_progress", self.service().status()["migration_status"])
        atomic_write_json(manifest_path, {**base, "phase": "failed", "failure_code": "SQLITE_MIGRATION_FAILED"})
        status = self.service().status()
        self.assertEqual("migration_error", status["migration_status"])
        self.assertEqual("SQLITE_MIGRATION_FAILED", status["last_error_code"])

    def test_wrong_production_root_is_rejected_without_touching_source(self) -> None:
        before = digest(self.source)
        service = ProductionMigrationService(
            self.paths,
            lambda: self.source,
            production_root_provider=lambda: self.root / "different-root",
        )
        with self.assertRaisesRegex(ProductionMigrationError, "SQLITE_PRODUCTION_ROOT_MISMATCH"):
            service.prepare(session_id="s")
        self.assertEqual(before, digest(self.source))
        self.assertFalse(self.paths.migrations_dir.exists())

    def test_already_active_new_install_and_real_root_are_protected(self) -> None:
        service = self.service()
        prepared = service.prepare(session_id="s")
        service.confirm(
            migration_id=prepared["migration_id"],
            token=prepared["confirmation_token"],
            session_id="s",
        )
        with self.assertRaisesRegex(ProductionMigrationError, "SQLITE_ALREADY_ACTIVE"):
            service.prepare(session_id="s")

        empty = self.root / "new_install"
        empty.mkdir()
        status = ProductionMigrationService(
            SQLiteStoragePaths.for_app_data(empty),
            lambda: empty / "Creator_Library.xlsx",
            production_root_provider=lambda: empty,
        ).status()
        self.assertFalse(status["migration_required"])
        self.assertEqual("not_required", status["migration_status"])

    def test_local_origin_policy_blocks_originless_and_remote_migration_mutations(self) -> None:
        from local_request_security import allowed_mutation_origin

        path = "/api/settings/storage-migration/prepare"
        self.assertFalse(allowed_mutation_origin("", path, 8765))
        self.assertFalse(allowed_mutation_origin("https://example.com", path, 8765))
        self.assertTrue(allowed_mutation_origin("http://127.0.0.1:8765", path, 8765))

    def test_assistant_and_feishu_handlers_do_not_expose_migration(self) -> None:
        assistant = (APP / "http_handlers" / "assistant_handler.py").read_text(encoding="utf-8")
        chat = (APP / "http_handlers" / "feishu_chat_handler.py").read_text(encoding="utf-8")
        self.assertNotIn("storage-migration", assistant)
        self.assertNotIn("storage-migration", chat)


if __name__ == "__main__":
    unittest.main()
