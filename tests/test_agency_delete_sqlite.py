from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from storage.sqlite_agency_repository import SQLiteAgencyRepository
from storage.sqlite_creator_repository import SQLiteCreatorRepository
from storage.sqlite_workbook_store import SQLiteWorkbookStore


class SQLiteAgencyDeleteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database = Path(self.temp.name) / "kolconnect.db"
        SQLiteWorkbookStore.initialize_empty(database)
        self.store = SQLiteWorkbookStore(database)
        self.repository = SQLiteAgencyRepository(self.store)
        self.creator_repository = SQLiteCreatorRepository(self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_unreferenced_agency_can_be_edited_then_deleted(self) -> None:
        agency = self.repository.save_agency({"name": "North", "country": "BR"})
        updated = self.repository.save_agency({"agency_id": agency["agency_id"], "name": "North Updated"})
        self.assertEqual("North Updated", updated["name"])
        self.assertTrue(self.repository.delete_agency(agency["agency_id"])["deleted"])
        self.assertEqual([], self.repository.list_agencies())

    def test_contact_can_be_edited_and_deleted_before_agency_deletion(self) -> None:
        agency = self.repository.save_agency({"name": "North"})
        contact = self.repository.save_contact(
            {"name": "Contact One", "agency_id": agency["agency_id"], "position": "Manager"}
        )
        updated = self.repository.save_contact(
            {"contact_id": contact["contact_id"], "email": "contact@example.com"}
        )
        self.assertEqual("Contact One", updated["name"])
        self.assertEqual("contact@example.com", updated["email"])
        with self.assertRaisesRegex(ValueError, "仍关联 0 位达人和 1 位联系人"):
            self.repository.delete_agency(agency["agency_id"])
        self.assertTrue(self.repository.delete_contact(contact["contact_id"])["deleted"])
        self.assertEqual([], self.repository.list_contacts(agency["agency_id"]))
        self.assertEqual(agency["agency_id"], self.repository.get_agency(agency["agency_id"])["agency_id"])
        self.assertTrue(self.repository.delete_agency(agency["agency_id"])["deleted"])

    def test_referenced_agency_fails_closed_without_partial_mutation(self) -> None:
        agency = self.repository.save_agency({"name": "Protected"})
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name,agency_id,status,created_at,updated_at) VALUES ('creator','Creator',?,'discovered','now','now')", (agency["agency_id"],))
        with self.assertRaisesRegex(ValueError, "仍关联 1 位达人"):
            self.repository.delete_agency(agency["agency_id"])
        self.assertEqual(agency["agency_id"], self.repository.get_agency(agency["agency_id"])["agency_id"])
        with self.store.factory.read_connection() as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM creators WHERE agency_id=?", (agency["agency_id"],)).fetchone()[0])

    def test_unlink_preserves_creator_account_campaign_and_publication_history(self) -> None:
        agency = self.repository.save_agency({"name": "Protected"})
        contact = self.repository.save_contact(
            {"name": "Contact", "agency_id": agency["agency_id"]}
        )
        with self.store.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO creators(creator_id,name,agency_id,current_contact_id,source_contact_id,status,created_at,updated_at) "
                "VALUES ('creator','Creator',?,?,?,'discovered','now','now')",
                (agency["agency_id"], contact["contact_id"], contact["contact_id"]),
            )
            connection.execute(
                "INSERT INTO creator_accounts(account_uid,creator_id,platform,created_at,updated_at) "
                "VALUES ('account','creator','TikTok','now','now')"
            )
            connection.execute("INSERT INTO campaigns(campaign_id,name) VALUES ('campaign','Campaign')")
            connection.execute(
                "INSERT INTO campaign_creators(id,campaign_id,creator_id,created_at,updated_at) "
                "VALUES ('campaign_creator','campaign','creator','now','now')"
            )
            connection.execute(
                "INSERT INTO campaign_creator_publish_links(campaign_creator_id,position,publish_link) "
                "VALUES ('campaign_creator',0,'https://example.com/post')"
            )
        with self.assertRaisesRegex(ValueError, "仍关联 1 位达人和 1 位联系人"):
            self.repository.delete_agency(agency["agency_id"])
        self.creator_repository.updateCreatorRelations(
            "creator",
            {"agency_id": "", "current_contact_id": "", "source_contact_id": ""},
            agency_port=self.repository,
        )
        self.assertTrue(self.repository.delete_contact(contact["contact_id"])["deleted"])
        self.assertTrue(self.repository.delete_agency(agency["agency_id"])["deleted"])
        with self.store.factory.read_connection() as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM creators WHERE creator_id='creator'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM creator_accounts WHERE account_uid='account'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM campaigns WHERE campaign_id='campaign'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM campaign_creators WHERE id='campaign_creator'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM campaign_creator_publish_links WHERE campaign_creator_id='campaign_creator'").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
