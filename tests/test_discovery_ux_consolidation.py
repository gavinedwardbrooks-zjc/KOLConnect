from __future__ import annotations

import hashlib
import io
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from creator_batch_import import TEMPLATE_HEADERS
from repository_factory import RepositoryFactory
from services.creator_service import CreatorService
from storage.migration import ExcelToSQLiteMigrator
from storage.paths import SQLiteStoragePaths
from storage.sqlite_creator_repository import SQLiteCreatorRepository
from test_pre_m8_excel_sqlite_migration import build_fixture
from test_support.runtime_sandbox import test_artifact_path


def import_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(TEMPLATE_HEADERS)
    sheet.append([
        "TikTok", "https://www.tiktok.com/@sqlite_imported", "SQLite Imported",
        "Brazil", "Portuguese", "Gaming", "", "", "", "",
    ])
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


class DiscoveryUXConsolidationContracts(unittest.TestCase):
    def setUp(self) -> None:
        root = test_artifact_path("discovery_ux_consolidation")
        root.mkdir(exist_ok=True)
        self.root = root / uuid4().hex
        self.root.mkdir()
        self.workbook = self.root / "Creator_Library.xlsx"
        build_fixture(self.workbook, creator_count=0, include_campaign=False)
        self.paths = SQLiteStoragePaths.for_app_data(self.root / "appdata")
        migration = ExcelToSQLiteMigrator(self.paths).migrate(self.workbook)
        ExcelToSQLiteMigrator(self.paths).activate_synthetic(migration)
        self.lock_patch = patch(
            "local_storage_lock.get_shared_storage_lock_path",
            return_value=self.root / "locks" / "shared_storage.lock",
        )
        self.lock_patch.start()

    def tearDown(self) -> None:
        self.lock_patch.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_template_import_uses_sqlite_and_exposes_creator_account_inventory(self) -> None:
        source_digest = hashlib.sha256(self.workbook.read_bytes()).hexdigest()
        factory = RepositoryFactory.for_runtime(self.workbook, storage_paths=self.paths)
        self.assertIsInstance(factory.creator(), SQLiteCreatorRepository)
        service = CreatorService(lambda: factory.creator(), lambda: None)

        result = service.import_creator_batch(import_workbook())

        self.assertEqual({"total_rows": 1, "created": 1, "skipped_existing": 0}, result)
        creators = factory.creator().getCreators(include_archived=True)
        creator = next(row for row in creators if row["creator_name"] == "SQLite Imported")
        accounts = factory.creator().getCreatorAccounts(creator["creator_id"])
        self.assertEqual(1, len(accounts))
        self.assertEqual("TikTok", accounts[0]["platform"])
        self.assertEqual(
            "https://www.tiktok.com/@sqlite_imported", accounts[0]["profile_url"]
        )
        inventory = factory.creator().getCreatorInventoryRows()
        self.assertIn(creator["creator_id"], {row["creator_id"] for row in inventory["creators"]})
        self.assertIn(accounts[0]["account_uid"], {row["account_uid"] for row in inventory["accounts"]})
        self.assertEqual(source_digest, hashlib.sha256(self.workbook.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
