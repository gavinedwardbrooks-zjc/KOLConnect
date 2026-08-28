from __future__ import annotations

import sys
import shutil
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from storage.connection import SQLiteConnectionFactory, backup_database
from storage.errors import SQLiteSchemaUnsupportedError
from storage.paths import SQLiteStoragePaths
from storage.schema import (
    CURRENT_SCHEMA_VERSION,
    apply_schema_migrations,
    schema_version,
    validate_schema,
)
from storage.sqlite_runtime import (
    VENDORED_WINDOWS_SQLITE_SHA256,
    is_wal_safe_version,
    require_safe_sqlite_runtime,
    runtime_version,
    sqlite_module,
    vendored_runtime_digest,
)


class SQLiteStorageFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime = ROOT / ".pre_m8_c0_c3_test_runtime"
        runtime.mkdir(exist_ok=True)
        self.root = runtime / f"foundation_{uuid4().hex}"
        self.root.mkdir()
        self.paths = SQLiteStoragePaths.for_app_data(self.root / "appdata")
        self.factory = SQLiteConnectionFactory(self.paths.database_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _initialize(self) -> None:
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection, migration_reference="test")

    def test_runtime_gate_accepts_the_active_approved_runtime(self) -> None:
        self.assertTrue(is_wal_safe_version("3.51.3"))
        self.assertTrue(is_wal_safe_version("3.50.7"))
        self.assertTrue(is_wal_safe_version("3.44.6"))
        self.assertFalse(is_wal_safe_version("3.50.4"))
        self.assertFalse(is_wal_safe_version("3.51.2"))
        approved_version = require_safe_sqlite_runtime()
        self.assertTrue(is_wal_safe_version(approved_version))
        self.assertEqual(approved_version, runtime_version())

    def test_windows_vendored_runtime_version_and_digest(self) -> None:
        if sys.platform == "win32":
            self.assertEqual("3.53.1", runtime_version())
            self.assertEqual(VENDORED_WINDOWS_SQLITE_SHA256, vendored_runtime_digest())

    def test_canonical_paths_are_persistent_and_isolated(self) -> None:
        self.assertEqual(self.root / "appdata" / "data" / "kolconnect.db", self.paths.database_path)
        self.assertEqual(
            self.root / "appdata" / "storage_migrations" / "m1" / "manifest.json",
            self.paths.migration_manifest_path("m1"),
        )
        self.assertNotIn("tmp", str(self.paths.database_path).casefold().split("appdata")[-1])

    def test_capability_wal_foreign_keys_commit_rollback_reopen_and_backup(self) -> None:
        self._initialize()
        with self.factory.read_connection() as connection:
            self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0])
            self.assertEqual(2, connection.execute("PRAGMA synchronous").fetchone()[0])
            self.assertEqual(1, connection.execute("PRAGMA foreign_keys").fetchone()[0])
            self.assertEqual(5000, connection.execute("PRAGMA busy_timeout").fetchone()[0])
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO products(product_id, name) VALUES (?, ?)", ("product_ok", "OK")
            )
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.factory.write_transaction() as connection:
                connection.execute(
                    "INSERT INTO products(product_id, name) VALUES (?, ?)",
                    ("product_rollback", "Rollback"),
                )
                raise RuntimeError("rollback")
        with self.factory.read_connection() as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM products").fetchone()[0])
            self.assertEqual(CURRENT_SCHEMA_VERSION, schema_version(connection))
            self.assertEqual("ok", validate_schema(connection)["quick_check"])
        backup_path = backup_database(
            self.paths.database_path, self.paths.database_backup_dir / "foundation.db"
        )
        sqlite3 = sqlite_module()
        reopened = sqlite3.connect(backup_path)
        try:
            self.assertEqual(1, reopened.execute("SELECT COUNT(*) FROM products").fetchone()[0])
            self.assertEqual("ok", reopened.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            reopened.close()

    def test_concurrent_reader_observes_stable_snapshot_during_writer(self) -> None:
        self._initialize()
        writer_ready = threading.Event()
        reader_done = threading.Event()

        def writer() -> None:
            with self.factory.write_transaction() as connection:
                connection.execute(
                    "INSERT INTO products(product_id, name) VALUES ('pending', 'Pending')"
                )
                writer_ready.set()
                self.assertTrue(reader_done.wait(5))

        def reader() -> int:
            self.assertTrue(writer_ready.wait(5))
            with self.factory.read_connection() as connection:
                count = int(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0])
            reader_done.set()
            return count

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer_future = pool.submit(writer)
            reader_future = pool.submit(reader)
            self.assertEqual(0, reader_future.result(timeout=8))
            writer_future.result(timeout=8)
        with self.factory.read_connection() as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM products").fetchone()[0])

    def test_concurrent_writers_are_serialized_without_lost_commits(self) -> None:
        self._initialize()

        def write(index: int) -> None:
            with self.factory.write_transaction() as connection:
                connection.execute(
                    "INSERT INTO products(product_id, name) VALUES (?, ?)",
                    (f"product_{index}", f"Product {index}"),
                )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(24)))
        with self.factory.read_connection() as connection:
            self.assertEqual(24, connection.execute("SELECT COUNT(*) FROM products").fetchone()[0])

    def test_schema_inventory_indexes_and_foreign_keys(self) -> None:
        self._initialize()
        with self.factory.read_connection() as connection:
            report = validate_schema(connection)
            self.assertEqual(20, report["table_count"])
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            self.assertTrue({"creators", "creator_accounts", "campaign_creators", "analysis_data"} <= tables)
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
            self.assertIn("idx_creator_accounts_creator", indexes)
            self.assertIn("idx_video_snapshots_video_time", indexes)
            with self.assertRaises(Exception):
                connection.execute(
                    "INSERT INTO creator_accounts(account_uid, creator_id) VALUES ('orphan', 'missing')"
                )

    def test_newer_schema_is_rejected_without_mutation(self) -> None:
        self._initialize()
        with self.factory.write_transaction() as connection:
            connection.execute(
                "UPDATE storage_metadata SET value='999' WHERE key='schema_version'"
            )
        with self.factory.read_connection() as connection:
            with self.assertRaises(SQLiteSchemaUnsupportedError):
                apply_schema_migrations(connection)
            self.assertEqual("999", connection.execute(
                "SELECT value FROM storage_metadata WHERE key='schema_version'"
            ).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
