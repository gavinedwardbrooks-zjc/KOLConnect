from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PreM8LegacyClosureContractTests(unittest.TestCase):
    def test_legacy_tiktok_passive_capture_is_not_production_wired(self) -> None:
        manifest = json.loads(
            (ROOT / "chrome_extension" / "manifest.json").read_text(encoding="utf-8")
        )
        active_scripts = {
            script
            for entry in manifest.get("content_scripts", [])
            for script in entry.get("js", [])
        }
        self.assertNotIn("content/passive_capture_bridge.js", active_scripts)
        self.assertNotIn("capture/passive_capture_main.js", active_scripts)
        self.assertTrue((ROOT / "chrome_extension" / "platform" / "tiktok_network.js").exists())
        boundary = (ROOT / "docs" / "post_m8_tiktok_passive_capture_v2.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("not supported in the current release", boundary)

    def test_current_mail_contract_does_not_claim_outlook_oauth_support(self) -> None:
        server = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
        frontend = (ROOT / "webapp" / "app.js").read_text(encoding="utf-8")
        proposal = (ROOT / "docs" / "microsoft_oauth2_mail_proposal.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"outlook": {', server)
        self.assertNotIn('value: "outlook"', frontend)
        self.assertNotIn("outlook.office365.com", frontend)
        self.assertIn('"gmail": {', server)
        self.assertIn('"netease": {', server)
        self.assertIn('"custom"', server)
        self.assertIn("DEPRECATED_REFERENCE_ONLY", proposal)

    def test_video_snapshot_history_identity_and_indexes_are_frozen(self) -> None:
        schema = (ROOT / "app" / "storage" / "schema.py").read_text(encoding="utf-8")
        repository = (
            ROOT / "app" / "storage" / "sqlite_creator_repository.py"
        ).read_text(encoding="utf-8")
        architecture = (
            ROOT / "docs" / "pre_m8_storage_architecture.md"
        ).read_text(encoding="utf-8")

        self.assertIn("video_snapshot_id TEXT PRIMARY KEY", schema)
        self.assertIn("idx_video_snapshots_video_time", schema)
        self.assertIn("idx_video_snapshots_creator_time", schema)
        self.assertIn('DELETE FROM video_snapshots WHERE snapshot_id=?', repository)
        self.assertIn('f"{snapshot_id}:{video_id}"', repository)
        self.assertIn("historical time-series data", architecture)
        self.assertIn("100,000 VideoSnapshot rows", architecture)

    def test_manual_artifact_rules_are_narrow_and_documented(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        expected = {
            "/.pre_m8_diag_direct/",
            "/.pre_m8_diag_fixed/",
            "/KOLConnect_acceptance/",
            "/packaging/.startup-diag-dist-onedir/",
            "/packaging/.startup-diag-dist-onedir-optimized/",
        }
        self.assertTrue(expected.issubset(set(ignore)))
        self.assertNotIn("packaging/", ignore)
        policy = (ROOT / "docs" / "test_runtime.md").read_text(encoding="utf-8")
        for path in expected:
            self.assertIn(path.strip("/"), policy)

    def test_campaign_and_settings_handlers_do_not_bypass_storage(self) -> None:
        forbidden_import_roots = {
            "excel_workbook_store",
            "openpyxl",
            "sqlite3",
            "storage",
        }
        forbidden_calls = {"open", "unlink", "remove", "rmtree", "write_text", "write_bytes"}

        for filename in ("campaign_handler.py", "settings_handler.py"):
            source = (ROOT / "app" / "http_handlers" / filename).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=filename)
            imported = set()
            called = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        called.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        called.add(node.func.attr)
            self.assertTrue(forbidden_import_roots.isdisjoint(imported), filename)
            self.assertTrue(forbidden_calls.isdisjoint(called), filename)


if __name__ == "__main__":
    unittest.main()
