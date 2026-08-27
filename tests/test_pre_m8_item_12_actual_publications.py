from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT / "tests"))

import creator_repository
from campaign_creator_repository import CampaignCreatorRepository
from campaign_repository import CampaignRepository
from http_handlers import campaign_handler
from product_repository import ProductRepository
from storage.sqlite_campaign_repositories import SQLiteCampaignCreatorRepository
from storage.sqlite_workbook_store import SQLiteWorkbookStore
from storage.schema import SCHEMA_V1_SQL, SCHEMA_V2_COLUMNS, apply_schema_migrations, schema_version
from storage.sqlite_runtime import sqlite_module
from test_support.runtime_sandbox import test_runtime_sandbox


class ActualPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime = self.enterContext(test_runtime_sandbox("pre_m8_item12"))
        self.root = runtime.root
        self.workbook_path = runtime.root / "Creator_Library.xlsx"
        creator_repository.CreatorRepository(self.workbook_path).getCreators()
        workbook = load_workbook(self.workbook_path)
        creator_headers = [str(cell.value or "") for cell in workbook["Creators"][1]]
        account_headers = [str(cell.value or "") for cell in workbook["CreatorAccounts"][1]]
        workbook["Creators"].append([
            {"creator_id": "creator_1", "name": "Creator One"}.get(header, "")
            for header in creator_headers
        ])
        for account_id, platform, creator_id in (
            ("tt_1", "TikTok", "creator_1"),
            ("yt_1", "YouTube", "creator_1"),
            ("tt_other", "TikTok", "creator_2"),
        ):
            if creator_id == "creator_2":
                workbook["Creators"].append([
                    {"creator_id": creator_id, "name": "Other"}.get(header, "")
                    for header in creator_headers
                ])
            workbook["CreatorAccounts"].append([
                {
                    "account_uid": f"{platform.lower()}|{account_id}",
                    "account_id": account_id,
                    "creator_id": creator_id,
                    "platform": platform,
                    "profile_url": f"https://example.test/{account_id}",
                }.get(header, "")
                for header in account_headers
            ])
        workbook.save(self.workbook_path)
        workbook.close()
        product = ProductRepository(self.workbook_path).createProduct({"name": "Game"})
        self.campaign = CampaignRepository(self.workbook_path).createCampaign({
            "name": "Launch", "product_id": product["product_id"],
            "platforms": ["TikTok", "YouTube"],
        })

    def _create(self, **extra):
        payload = {
            "campaign_id": self.campaign["campaign_id"],
            "creator_id": "creator_1",
            "account_ids": ["yt_1"],
            "planned_publish_dates": ["2026-09-20"],
        }
        payload.update(extra)
        return CampaignCreatorRepository(self.workbook_path).createCampaignCreator(payload)

    def test_multiple_publications_preserve_planned_actual_separation_and_roundtrip(self):
        relation = self._create(publications=[
            {
                "actual_publish_url": "https://www.tiktok.com/@one/video/1",
                "actual_account_id": "tt_1",
                "actual_published_at": "2026-09-22T12:30:00-03:00",
            },
            {
                "actual_publish_url": "https://youtube.com/shorts/abc",
                "actual_account_id": "yt_1",
                "actual_published_at": "",
            },
        ])
        self.assertEqual(["yt_1"], relation["account_ids"])
        self.assertEqual(["2026-09-20"], relation["planned_publish_dates"])
        self.assertEqual(2, len(relation["publications"]))
        first, second = relation["publications"]
        self.assertEqual("tt_1", first["actual_account_id"])
        self.assertEqual("2026-09-22T15:30:00Z", first["actual_published_at"])
        self.assertTrue(first["observed_at"].endswith("Z"))
        self.assertEqual("", second["actual_published_at"])
        self.assertEqual(2, len(json.loads(relation["publish_links"])))
        reopened = CampaignCreatorRepository(self.workbook_path).getCampaignCreator(relation["id"])
        self.assertEqual(relation["publications"], reopened["publications"])
        self.assertEqual("tt_1", reopened["publications"][0]["actual_account"]["account_id"])

    def test_idempotent_duplicate_and_account_validation(self):
        relation = self._create(publications=[
            {"actual_publish_url": "https://tiktok.com/@one/video/1/", "actual_account_id": "tt_1"},
            {"actual_publish_url": "https://TIKTOK.com/@one/video/1", "actual_account_id": "tt_1"},
        ])
        self.assertEqual(1, len(relation["publications"]))
        original_id = relation["publications"][0]["publication_id"]
        updated = CampaignCreatorRepository(self.workbook_path).updateCampaignCreator(
            relation["id"], {"publications": relation["publications"]}
        )
        self.assertEqual(original_id, updated["publications"][0]["publication_id"])
        with self.assertRaisesRegex(ValueError, "不属于"):
            CampaignCreatorRepository(self.workbook_path).updateCampaignCreator(
                relation["id"], {"publications": [{
                    "actual_publish_url": "https://tiktok.com/@other/video/2",
                    "actual_account_id": "tt_other",
                }]}
            )
        with self.assertRaisesRegex(ValueError, "平台"):
            CampaignCreatorRepository(self.workbook_path).updateCampaignCreator(
                relation["id"], {"publications": [{
                    "actual_publish_url": "https://youtube.com/shorts/wrong",
                    "actual_account_id": "tt_1",
                }]}
            )

    def test_legacy_link_has_unknown_actual_metadata_and_no_fabricated_time(self):
        relation = self._create(publish_links=["https://example.test/post/legacy"])
        publication = relation["publications"][0]
        self.assertEqual("", publication["actual_account_id"])
        self.assertEqual("", publication["actual_published_at"])
        self.assertEqual("", publication["observed_at"])
        self.assertEqual("legacy", publication["source"])
        self.assertNotEqual(relation["publish_date"], publication["actual_published_at"])

    def test_api_and_sqlite_storage_roundtrip(self):
        class Handler:
            def _json(inner, payload, status=200):
                inner.payload = payload
                inner.status = status

            def _repository_error(inner, exc):
                raise exc

        handler = Handler()
        publication = {
            "actual_publish_url": "https://tiktok.com/@one/video/api",
            "actual_account_id": "tt_1",
            "actual_published_at": "2026-09-25T10:00:00Z",
        }
        handled = campaign_handler.handle(handler, {
            "method": "POST",
            "path": f"/api/campaigns/{self.campaign['campaign_id']}/creators",
            "query": {},
            "get_payload": lambda: {
                "creator_id": "creator_1", "account_ids": ["tt_1"],
                "publications": [publication],
            },
        }, {
            "repositories": {
                "campaign_creator": lambda: CampaignCreatorRepository(self.workbook_path),
            },
            "services": {"invalidate_dashboard_response_cache": lambda: None},
        })
        self.assertTrue(handled)
        self.assertEqual(201, handler.status)
        self.assertEqual("tt_1", handler.payload["campaign_creator"]["publications"][0]["actual_account_id"])

        database = self.root / "publications.db"
        SQLiteWorkbookStore.initialize_empty(database)
        store = SQLiteWorkbookStore(database)
        with store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('creator','Creator')")
            connection.execute(
                "INSERT INTO creator_accounts(account_uid,account_id,creator_id,platform,profile_url) "
                "VALUES ('tiktok|creator','account','creator','TikTok','https://tiktok.com/@creator')"
            )
            connection.execute("INSERT INTO campaigns(campaign_id,name) VALUES ('campaign','Campaign')")
        relation = SQLiteCampaignCreatorRepository(store).createCampaignCreator({
            "campaign_id": "campaign", "creator_id": "creator", "account_ids": ["account"],
            "publications": [{
                "actual_publish_url": "https://tiktok.com/@creator/video/1",
                "actual_account_id": "account",
                "actual_published_at": "2026-09-25T10:00:00Z",
            }],
        })
        self.assertEqual("account", relation["publications"][0]["actual_account_id"])
        with store.factory.read_connection() as connection:
            row = connection.execute(
                "SELECT actual_account_uid,published_at,observed_at FROM campaign_creator_publish_links"
            ).fetchone()
        self.assertEqual("tiktok|creator", row[0])
        self.assertEqual("2026-09-25T10:00:00Z", row[1])
        self.assertTrue(str(row[2]).endswith("Z"))


class PublicationSchemaMigrationTests(unittest.TestCase):
    def _v2_connection(self):
        connection = sqlite_module().connect(":memory:", isolation_level=None)
        connection.executescript(SCHEMA_V1_SQL)
        connection.executemany(
            "INSERT INTO storage_metadata(key, value) VALUES (?, ?)",
            (("schema_version", "1"), ("created_at", "2026-01-01T00:00:00Z")),
        )
        existing = {row[1] for row in connection.execute("PRAGMA table_info(campaign_creators)")}
        for column, data_type in SCHEMA_V2_COLUMNS:
            if column not in existing:
                connection.execute(f"ALTER TABLE campaign_creators ADD COLUMN {column} {data_type}")
        connection.execute("UPDATE storage_metadata SET value='2' WHERE key='schema_version'")
        connection.execute("INSERT INTO creators(creator_id) VALUES ('creator_1')")
        connection.execute("INSERT INTO campaigns(campaign_id) VALUES ('campaign_1')")
        connection.execute(
            "INSERT INTO campaign_creators(id, campaign_id, creator_id) VALUES ('relation_1','campaign_1','creator_1')"
        )
        connection.execute(
            "INSERT INTO campaign_creator_publish_links(campaign_creator_id, position, publish_link) "
            "VALUES ('relation_1',0,'https://example.test/post/1')"
        )
        return connection

    def test_v2_to_v3_preserves_legacy_link_without_fabricating_actual_fields(self):
        connection = self._v2_connection()
        self.addCleanup(connection.close)
        self.assertEqual(3, apply_schema_migrations(connection))
        row = connection.execute(
            "SELECT publication_id, publish_link, actual_account_uid, published_at, observed_at, source "
            "FROM campaign_creator_publish_links"
        ).fetchone()
        self.assertTrue(str(row[0]).startswith("publication_legacy_"))
        self.assertEqual("https://example.test/post/1", row[1])
        self.assertIsNone(row[2])
        self.assertIsNone(row[3])
        self.assertIsNone(row[4])
        self.assertEqual("legacy", row[5])

    def test_v3_migration_rolls_back_when_legacy_row_update_fails(self):
        connection = self._v2_connection()
        self.addCleanup(connection.close)
        connection.execute(
            "CREATE TRIGGER block_publication_upgrade BEFORE UPDATE ON campaign_creator_publish_links "
            "BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
        with self.assertRaises(Exception):
            apply_schema_migrations(connection)
        self.assertEqual(2, schema_version(connection))
        columns = {row[1] for row in connection.execute("PRAGMA table_info(campaign_creator_publish_links)")}
        self.assertNotIn("publication_id", columns)


if __name__ == "__main__":
    unittest.main()
