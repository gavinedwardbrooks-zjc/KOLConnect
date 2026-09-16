from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from dashboard_service import DashboardService  # noqa: E402
from repository_factory import RepositoryFactory  # noqa: E402
from storage.migration import ExcelToSQLiteMigrator  # noqa: E402
from storage.paths import SQLiteStoragePaths  # noqa: E402
from test_pre_m8_excel_sqlite_migration import build_fixture  # noqa: E402


class _DashboardV2Repository:
    def get_creators(self):
        return [
            {
                "creator_id": "creator_one",
                "creator_name": "Creator One",
                "country": "Brazil",
                "language": "Portuguese",
                "content_category": "Gaming",
            },
            {
                "creator_id": "creator_two",
                "creator_name": "Creator Two",
                "country": "",
                "language": "",
                "content_category": "",
            },
            {"creator_id": "archived", "creator_name": "Archived", "archived_at": "2026-01-01"},
        ]

    def get_creator_accounts(self):
        return [
            {
                "creator_id": "creator_one",
                "platform": "TikTok",
                "username": "one",
                "profile_url": "https://www.tiktok.com/@one",
                "account_email": "one@example.com",
                "account_uid": "private-account-identity",
            },
            {
                "creator_id": "creator_one",
                "platform": "YouTube",
                "username": "one-channel",
                "profile_url": "https://www.youtube.com/@one-channel",
                "account_email": "",
                "account_uid": "private-second-identity",
            },
            {
                "creator_id": "creator_two",
                "platform": "Instagram",
                "username": "two",
                "profile_url": "https://www.instagram.com/two",
                "account_email": "",
                "account_uid": "private-third-identity",
            },
        ]

    def get_campaigns(self):
        return [{"campaign_id": "campaign_one", "name": "Campaign One", "status": "running"}]

    def get_campaign_creator_records(self, creators):
        return [
            {"campaign_id": "campaign_one", "creator_id": "creator_one", "publish_links": "https://example.test/post"},
            {"campaign_id": "campaign_one", "creator_id": "creator_two", "publish_links": ""},
            {"campaign_id": "campaign_one", "creator_id": "creator_two", "publish_links": "[]"},
        ]


class DashboardV2SnapshotTests(unittest.TestCase):
    def test_snapshot_keeps_creator_and_account_metrics_distinct_and_drillable(self):
        snapshot = DashboardService(_DashboardV2Repository()).getV2Snapshot()

        self.assertEqual(2, snapshot["creator_count"])
        self.assertEqual(3, snapshot["account_count"])
        self.assertEqual(
            [
                {"platform": "Instagram", "count": 1},
                {"platform": "TikTok", "count": 1},
                {"platform": "YouTube", "count": 1},
            ],
            snapshot["platform_accounts"],
        )
        self.assertEqual(2, len(snapshot["missing"]["email_accounts"]))
        self.assertEqual(["creator_two"], [row["creator_id"] for row in snapshot["missing"]["country_creators"]])
        self.assertEqual(["creator_two"], [row["creator_id"] for row in snapshot["missing"]["language_creators"]])
        self.assertEqual(["creator_two"], [row["creator_id"] for row in snapshot["missing"]["content_type_creators"]])
        self.assertNotIn("account_uid", snapshot["missing"]["email_accounts"][0])

    def test_snapshot_reports_campaign_member_and_publication_progress(self):
        snapshot = DashboardService(_DashboardV2Repository()).getV2Snapshot()

        self.assertEqual(
            [{
                "campaign_id": "campaign_one",
                "name": "Campaign One",
                "status": "running",
                "creator_count": 3,
                "published_count": 1,
                "start_date": "",
            }],
            snapshot["campaigns"],
        )

    def test_sqlite_dashboard_projection_reads_campaigns_without_excel_fallback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook = root / "legacy.xlsx"
            paths = SQLiteStoragePaths.for_app_data(root / "appdata")
            build_fixture(workbook)
            migration = ExcelToSQLiteMigrator(paths).migrate(workbook)
            ExcelToSQLiteMigrator(paths).activate_synthetic(migration)
            factory = RepositoryFactory.for_runtime(workbook, storage_paths=paths)

            snapshot = DashboardService(factory.dashboard(factory.creator())).getV2Snapshot()

        self.assertGreater(snapshot["creator_count"], 0)
        self.assertIsInstance(snapshot["campaigns"], list)


if __name__ == "__main__":
    unittest.main()
