from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT / "tests"))

import creator_repository
from campaign_creator_repository import CampaignCreatorRepository
from campaign_repository import CampaignRepository
from dashboard_service import DashboardService
from domain.money import apply_quote_contract, grouped_amounts
from http_handlers import campaign_handler
from product_repository import ProductRepository
from storage.connection import SQLiteConnectionFactory
from storage.authority import resolve_runtime_authority
from storage.paths import SQLiteStoragePaths
from storage.schema import apply_schema_migrations, schema_version
from storage.sqlite_campaign_repositories import SQLiteCampaignCreatorRepository
from storage.sqlite_workbook_store import SQLiteWorkbookStore
from test_support.runtime_sandbox import test_runtime_sandbox


def close_app_logger() -> None:
    app_logging = sys.modules.get("app_logging")
    if app_logging is None:
        return
    logger = app_logging.logging.getLogger(app_logging.LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    app_logging._CONFIGURED = False


class FakeHandler:
    def __init__(self) -> None:
        self.payload = None
        self.status = None

    def _json(self, payload, status=200):
        self.payload = payload
        self.status = status

    def _repository_error(self, exc):
        self._json({"ok": False, "error": str(exc)}, status=400)


class DashboardSource:
    def __init__(self, relations):
        self.relations = relations

    def get_creators(self):
        return []

    def get_campaign_creator_records(self, _creators=None):
        return list(self.relations)

    def get_creator_health_records(self):
        return []


class MultiCurrencyQuoteTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime = self.enterContext(test_runtime_sandbox("pre_m8_item7"))
        self.root = runtime.root
        self.addCleanup(close_app_logger)
        self.enterContext(mock.patch(
            "local_storage_lock.get_shared_storage_lock_path",
            return_value=runtime.lock_root / "shared_storage.lock",
        ))
        self.workbook_path = self.root / "Creator_Library.xlsx"
        creator_repository.CreatorRepository(self.workbook_path).getCreators()
        workbook = load_workbook(self.workbook_path)
        creator_headers = [str(cell.value or "") for cell in workbook["Creators"][1]]
        account_headers = [str(cell.value or "") for cell in workbook["CreatorAccounts"][1]]
        for index in (1, 2):
            creator_id = f"creator_{index}"
            account_id = f"account_{index}"
            workbook["Creators"].append([
                {
                    "creator_id": creator_id,
                    "name": f"Creator {index}",
                    "platform": "TikTok",
                    "status": "discovered",
                    "created_at": "2026-08-01T00:00:00Z",
                    "updated_at": "2026-08-01T00:00:00Z",
                }.get(header, "")
                for header in creator_headers
            ])
            workbook["CreatorAccounts"].append([
                {
                    "account_uid": f"tiktok|creator-{index}",
                    "account_id": account_id,
                    "creator_id": creator_id,
                    "platform": "TikTok",
                    "profile_url": f"https://tiktok.com/@creator-{index}",
                }.get(header, "")
                for header in account_headers
            ])
        workbook.save(self.workbook_path)
        workbook.close()
        product = ProductRepository(self.workbook_path).createProduct({"name": "Product"})
        self.campaign = CampaignRepository(self.workbook_path).createCampaign({
            "product_id": product["product_id"],
            "name": "Campaign",
            "platform": "TikTok",
        })
        self.repository = CampaignCreatorRepository(self.workbook_path)

    def _create(self, creator: int, **money):
        return self.repository.createCampaignCreator({
            "campaign_id": self.campaign["campaign_id"],
            "creator_id": f"creator_{creator}",
            "account_id": f"account_{creator}",
            **money,
        })

    def test_usd_and_brl_structured_quotes_calculate_total(self) -> None:
        usd = self._create(
            1, quote_currency="usd", quote_unit_amount=100,
            quote_quantity=2, quote_unit="video", cost=200,
        )
        brl = self._create(
            2, quote_currency="BRL", quote_unit_amount=500,
            quote_quantity=3, quote_unit="video", cost=1400,
            cost_currency="BRL",
        )
        self.assertEqual(("USD", 100, 2, "video", 200, "USD"), (
            usd["quote_currency"], usd["quote_unit_amount"], usd["quote_quantity"],
            usd["quote_unit"], usd["creator_quote"], usd["cost_currency"],
        ))
        self.assertEqual(1500, brl["creator_quote"])
        self.assertEqual("BRL", brl["cost_currency"])

    def test_legacy_total_only_row_remains_readable_without_invented_identity(self) -> None:
        legacy = self._create(1, creator_quote=200, cost=180)
        self.assertEqual(200, legacy["creator_quote"])
        self.assertEqual(180, legacy["cost"])
        for field in (
            "quote_currency", "quote_unit_amount", "quote_quantity", "quote_unit",
            "cost_currency",
        ):
            self.assertIn(legacy.get(field), (None, ""))

    def test_missing_currency_invalid_quantity_and_inconsistent_total_fail_closed(self) -> None:
        base = {
            "quote_unit_amount": 100,
            "quote_quantity": 2,
            "quote_unit": "video",
        }
        with self.assertRaisesRegex(ValueError, "报价币种"):
            apply_quote_contract(base, {})
        for quantity in (0, -1, "1.5", "invalid"):
            with self.subTest(quantity=quantity), self.assertRaisesRegex(ValueError, "正整数"):
                apply_quote_contract({**base, "quote_currency": "USD", "quote_quantity": quantity}, {})
        with self.assertRaisesRegex(ValueError, "必须等于"):
            apply_quote_contract({**base, "quote_currency": "USD", "creator_quote": 300}, {})

    def test_mixed_currency_aggregation_is_never_a_scalar_sum(self) -> None:
        mixed = grouped_amounts(
            [
                {"cost": 200, "cost_currency": "USD"},
                {"cost": 1000, "cost_currency": "BRL"},
            ],
            "cost",
            "cost_currency",
        )
        self.assertIsNone(mixed["total"])
        self.assertEqual({"BRL": 1000.0, "USD": 200.0}, mixed["totals_by_currency"])
        self.assertTrue(mixed["multiple_currencies"])
        same = grouped_amounts(
            [{"cost": 200, "cost_currency": "USD"}, {"cost": 50, "cost_currency": "USD"}],
            "cost",
            "cost_currency",
        )
        self.assertEqual(250, same["total"])
        self.assertFalse(same["multiple_currencies"])

    def test_dashboard_suppresses_mixed_currency_scalar(self) -> None:
        rows = [
            {"campaign_id": "one", "creator_id": "a", "stage": "completed", "cost": 200, "cost_currency": "USD"},
            {"campaign_id": "two", "creator_id": "b", "stage": "completed", "cost": 1000, "cost_currency": "BRL"},
        ]
        performance = DashboardService(DashboardSource(rows)).getCooperationPerformance()
        self.assertIsNone(performance["total_cost"])
        self.assertEqual({"BRL": 1000.0, "USD": 200.0}, performance["cost_totals_by_currency"])

    def test_api_round_trip_returns_structured_quote_fields(self) -> None:
        handler = FakeHandler()
        request = {
            "method": "POST",
            "path": f"/api/campaigns/{self.campaign['campaign_id']}/creators",
            "query": {},
            "get_payload": lambda: {
                "creator_id": "creator_1",
                "account_id": "account_1",
                "quote_currency": "USD",
                "quote_unit_amount": 100,
                "quote_quantity": 2,
                "quote_unit": "video",
                "cost": 200,
            },
        }
        context = {
            "repositories": {
                "campaign": lambda: CampaignRepository(self.workbook_path),
                "campaign_creator": lambda: self.repository,
            },
            "services": {"invalidate_dashboard_response_cache": lambda: None},
        }
        self.assertTrue(campaign_handler.handle(handler, request, context))
        self.assertEqual(201, handler.status)
        record = handler.payload["campaign_creator"]
        self.assertEqual(("USD", 100, 2, "video", 200), (
            record["quote_currency"], record["quote_unit_amount"],
            record["quote_quantity"], record["quote_unit"], record["creator_quote"],
        ))

    def test_sqlite_v1_to_v2_adds_nullable_fields_and_preserves_totals(self) -> None:
        database = self.root / "legacy.db"
        factory = SQLiteConnectionFactory(database)
        with factory.read_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE storage_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO storage_metadata(key,value) VALUES ('schema_version','1');
                CREATE TABLE campaign_creators (
                    id TEXT PRIMARY KEY, campaign_id TEXT, creator_id TEXT, account_id TEXT,
                    stage TEXT, owner TEXT, creator_quote REAL, cost REAL, publish_date TEXT,
                    views INTEGER, likes INTEGER, comments INTEGER, roi REAL,
                    performance_note TEXT, created_at TEXT, updated_at TEXT, archived_at TEXT
                );
                INSERT INTO campaign_creators(id, creator_quote, cost)
                VALUES ('legacy', 200, 180);
                CREATE TABLE campaign_creator_publish_links (
                    campaign_creator_id TEXT NOT NULL, position INTEGER NOT NULL,
                    publish_link TEXT NOT NULL,
                    PRIMARY KEY (campaign_creator_id, position),
                    UNIQUE (campaign_creator_id, publish_link)
                );
                """
            )
            apply_schema_migrations(connection, migration_reference="test-v1-v2")
            self.assertEqual(3, schema_version(connection))
            row = connection.execute(
                "SELECT creator_quote,cost,quote_currency,quote_unit_amount,"
                "quote_quantity,quote_unit,cost_currency FROM campaign_creators"
            ).fetchone()
            self.assertEqual((200, 180, None, None, None, None, None), tuple(row))

    def test_sqlite_structured_quote_round_trip(self) -> None:
        database = self.root / "roundtrip.db"
        SQLiteWorkbookStore.initialize_empty(database)
        store = SQLiteWorkbookStore(database)
        with store.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO products(product_id,name,created_at,updated_at) "
                "VALUES ('product','Product','2026-08-01','2026-08-01')"
            )
            connection.execute(
                "INSERT INTO campaigns(campaign_id,product_id,name,status,created_at,updated_at) "
                "VALUES ('campaign','product','Campaign','draft','2026-08-01','2026-08-01')"
            )
            connection.execute(
                "INSERT INTO creators(creator_id,name,status,created_at,updated_at) "
                "VALUES ('creator','Creator','discovered','2026-08-01','2026-08-01')"
            )
            connection.execute(
                "INSERT INTO campaign_creators(id,campaign_id,creator_id,stage,created_at,updated_at) "
                "VALUES ('relation','campaign','creator','quoted','2026-08-01','2026-08-01')"
            )
        repository = SQLiteCampaignCreatorRepository(store)
        updated = repository.updateCampaignCreator(
            "relation",
            {
                "quote_currency": "USD",
                "quote_unit_amount": 100,
                "quote_quantity": 2,
                "quote_unit": "video",
                "cost": 180,
            },
        )
        self.assertEqual(
            ("USD", 100, 2, "video", 200, 180, "USD"),
            (
                updated["quote_currency"],
                updated["quote_unit_amount"],
                updated["quote_quantity"],
                updated["quote_unit"],
                updated["creator_quote"],
                updated["cost"],
                updated["cost_currency"],
            ),
        )

    def test_runtime_v1_upgrade_backs_up_source_before_schema_change(self) -> None:
        paths = SQLiteStoragePaths.for_app_data(self.root / "runtime")
        paths.data_dir.mkdir(parents=True)
        factory = SQLiteConnectionFactory(paths.database_path)
        with factory.read_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE storage_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO storage_metadata(key,value) VALUES ('schema_version','1');
                CREATE TABLE creators (creator_id TEXT PRIMARY KEY);
                CREATE TABLE campaign_creators (
                    id TEXT PRIMARY KEY, creator_quote REAL, cost REAL
                );
                INSERT INTO creators(creator_id) VALUES ('creator');
                INSERT INTO campaign_creators(id,creator_quote,cost)
                VALUES ('legacy',200,180);
                CREATE TABLE campaign_creator_publish_links (
                    campaign_creator_id TEXT NOT NULL, position INTEGER NOT NULL,
                    publish_link TEXT NOT NULL,
                    PRIMARY KEY (campaign_creator_id, position),
                    UNIQUE (campaign_creator_id, publish_link)
                );
                """
            )
        paths.authority_marker_path.write_text(
            json.dumps(
                {
                    "authority": "sqlite",
                    "database_name": paths.database_path.name,
                    "schema_version": 1,
                }
            ),
            encoding="utf-8",
        )
        authority = resolve_runtime_authority(paths, self.root / "legacy.xlsx")
        self.assertEqual("sqlite", authority.kind)
        backups = list(paths.database_backup_dir.glob("kolconnect-pre-schema-v1-*.db"))
        self.assertEqual(1, len(backups))
        with factory.read_connection() as connection:
            self.assertEqual(3, schema_version(connection))
            row = connection.execute(
                "SELECT creator_quote,cost,quote_currency,cost_currency "
                "FROM campaign_creators WHERE id='legacy'"
            ).fetchone()
            self.assertEqual((200, 180, None, None), tuple(row))
        backup_factory = SQLiteConnectionFactory(backups[0])
        with backup_factory.read_connection() as connection:
            self.assertEqual(1, schema_version(connection))


if __name__ == "__main__":
    unittest.main()
