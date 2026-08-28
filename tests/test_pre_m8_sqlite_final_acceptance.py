from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_sqlite_cutover import run_acceptance
from test_support.runtime_sandbox import test_artifact_path


class SQLiteFinalSyntheticAcceptanceTests(unittest.TestCase):
    def test_complete_legacy_migration_restart_restore_and_reimport(self) -> None:
        parent = test_artifact_path("pre_m8_batch3_acceptance")
        parent.mkdir(exist_ok=True)
        sandbox = parent / f"test_{uuid4().hex}"
        try:
            result = run_acceptance(sandbox)
            self.assertEqual("legacy_excel", result["authority_before"])
            self.assertEqual("sqlite", result["authority_after"])
            self.assertTrue(result["source_unchanged_by_migration"])
            self.assertTrue(result["legacy_excel_edit_ignored"])
            self.assertTrue(result["sqlite_write_does_not_touch_excel"])
            self.assertEqual("Portugal", result["backup_restore_country"])
            self.assertTrue(result["export_reimport_parity"])
            self.assertEqual("sqlite", result["restart_authority"])
            self.assertEqual(100, len(result["projection"]["creator_ids"]))
            self.assertEqual(102, len(result["projection"]["account_ownership"]))
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
