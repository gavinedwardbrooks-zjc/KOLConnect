import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.google_sheets_data_sync_service import GoogleSheetsDataSyncService


class Inventory:
    def getCreatorInventoryRows(self):
        return {
            "creators": [{"creator_id": "creator_b", "name": "B", "country": "BR"}, {"creator_id": "creator_a", "name": "A", "archived_at": None}],
            "accounts": [{"account_uid": "youtube:b", "creator_id": "creator_b", "followers": 0}, {"account_uid": "tiktok:a", "creator_id": "creator_a", "account_email": "a@example.com"}],
        }


class Client:
    def __init__(self): self.received = None
    def sync_managed_worksheets(self, spreadsheet, worksheets):
        self.received = (spreadsheet, worksheets)
        return {"status": "SUCCESS", "worksheets": [{"status": "SUCCESS"} for _ in worksheets]}


class GoogleSheetsDataSyncTests(unittest.TestCase):
    def test_creator_account_replica_is_deterministic_and_preserves_null_zero(self):
        report = GoogleSheetsDataSyncService(Inventory()).assemble()
        self.assertEqual(["KOLConnect Creators", "KOLConnect Creator Accounts"], [item["title"] for item in report["worksheets"]])
        creators, accounts = report["worksheets"]
        self.assertEqual("creator_a", creators["rows"][0][0])
        self.assertEqual("", creators["rows"][0][5])
        self.assertEqual("tiktok:a", accounts["rows"][0][0])
        self.assertEqual(0, accounts["rows"][1][5])

    def test_sync_only_delegates_the_controlled_replica_worksheets(self):
        client = Client()
        result = GoogleSheetsDataSyncService(Inventory()).sync(client, "a-valid_sheet-ID_123456789")
        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual("a-valid_sheet-ID_123456789", client.received[0])
        self.assertEqual(2, len(client.received[1]))


if __name__ == "__main__": unittest.main()
