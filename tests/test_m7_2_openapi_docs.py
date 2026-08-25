from __future__ import annotations

import sys
import unittest
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # PyYAML is validation tooling, not a runtime dependency.
    yaml = None


ROOT = Path(__file__).resolve().parents[1]


class OpenApiDocumentationTests(unittest.TestCase):
    def test_openapi_is_parseable_and_documents_registered_key_routes(self):
        path = ROOT / "docs" / "openapi.yaml"
        if yaml is None:
            self.skipTest("PyYAML is not available for syntax validation")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual("3.0.3", document["openapi"])
        documented = set(document["paths"])
        expected = {
            "/api/creator-library",
            "/api/creator-library/{creator_id}",
            "/api/creator-library/merge/preview",
            "/api/campaigns",
            "/api/campaigns/{campaign_id}",
            "/api/tasks",
            "/api/tasks/{task_id}/results/review",
            "/api/feishu-sync/validate",
            "/api/feishu-sync/dry-run",
            "/api/feishu-sync/full-sync",
        }
        self.assertTrue(expected.issubset(documented))

        sources = "\n".join(
            path.read_text(encoding="utf-8-sig")
            for path in (ROOT / "app" / "http_handlers").glob("*.py")
        )
        for route in (
            "/api/creator-library",
            "/api/campaigns",
            "/api/tasks",
            "/api/feishu-sync/validate",
            "/api/feishu-sync/dry-run",
            "/api/feishu-sync/full-sync",
        ):
            self.assertIn(route, sources)

    def test_retired_feishu_migration_routes_are_not_publicly_documented(self):
        source = (ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8")
        for retired in (
            "account-backfill",
            "creator-backfill",
            "legacy-creator-cleanup",
            "sync-valid-results",
        ):
            self.assertNotIn(retired, source)

    def test_reference_and_openclaw_docs_freeze_local_api_boundary(self):
        reference = (ROOT / "docs" / "api_reference.md").read_text(encoding="utf-8")
        skill = (ROOT / "docs" / "feishu-openclaw-skill.md").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", reference)
        self.assertIn("trace_id", reference)
        self.assertIn("OpenClaw must not read or edit `Creator_Library.xlsx`", skill)
        self.assertIn("Full Sync", skill)


if __name__ == "__main__":
    unittest.main()
