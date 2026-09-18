from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.campaign_execution_service import CampaignExecutionService
from storage.schema import CURRENT_SCHEMA_VERSION, apply_schema_migrations, schema_version
from storage.sqlite_workbook_store import SQLiteWorkbookStore
from test_support.runtime_sandbox import test_runtime_sandbox


class CampaignExecutionFoundationTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = test_runtime_sandbox("campaign_execution")
        runtime = self.sandbox.__enter__()
        self.store = SQLiteWorkbookStore.initialize_empty(runtime.root / "execution.db")
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO products(product_id,name) VALUES ('product','Product')")
            connection.execute("INSERT INTO campaigns(campaign_id,product_id,name) VALUES ('campaign','product','Campaign')")
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('creator','Creator')")
            connection.execute("INSERT INTO campaign_creators(id,campaign_id,creator_id,stage,updated_at) VALUES ('relation','campaign','creator','executing','2026-01-01T00:00:00Z')")
        self.service = CampaignExecutionService(lambda: self.store.factory)

    def tearDown(self):
        self.sandbox.__exit__(None, None, None)

    def test_execution_derives_overdue_and_preserves_terminal_records(self):
        execution = self.service.update_execution("relation", {
            "owner": "Alice", "next_action": "等待视频", "due_date": "2020-01-01",
            "waiting_on": "creator", "need_my_decision": True,
        })
        self.assertTrue(execution["overdue"])
        self.assertTrue(execution["need_my_decision"])
        self.assertEqual("creator", execution["waiting_on"])
        self.service.update_execution("relation", {"stage": "completed"})
        self.assertFalse(self.service.execution_for("relation")["overdue"])
        self.assertFalse(self.service.execution_for("relation")["stalled"])

    def test_brief_and_human_review_are_separate_from_publication(self):
        brief = self.service.save_brief("campaign", {"title": "Brief", "must_include": "Brand", "must_avoid": "guaranteed"})
        self.assertEqual("Brief", brief["title"])
        submission = self.service.create_submission("relation", {"content_type": "script", "content_reference": "draft text"})
        reviewed = self.service.review_submission(submission["submission_id"], {"review_status": "changes_requested", "review_note": "补充卖点"})
        self.assertEqual("changes_requested", reviewed["review_status"])
        self.assertEqual("补充卖点", reviewed["review_note"])
        ai = self.service.ai_review_submission(submission["submission_id"])
        self.assertEqual("success", ai["status"])
        self.assertEqual("changes_requested", ai["human_review_status"])
        self.assertTrue(ai["findings"])  # AI findings do not overwrite human review.
        with self.store.factory.read_connection() as connection:
            self.assertEqual(1, connection.execute(
                "SELECT COUNT(*) FROM content_submission_ai_findings WHERE submission_id=?",
                (submission["submission_id"],),
            ).fetchone()[0])

    def test_v4_to_v5_preserves_existing_campaign_publication_and_identity_data(self):
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,platform) VALUES ('account','creator','TikTok')")
            connection.execute(
                "INSERT INTO campaign_creator_publish_links("
                "campaign_creator_id,position,publish_link,publication_id,source"
                ") VALUES ('relation',0,'https://example.test/video','publication','manual')"
            )
            connection.execute("INSERT INTO publication_performance_observations(observation_id,publication_id,refresh_operation_id,observed_at,source,confidence) VALUES ('observation','publication','refresh','2026-01-01T00:00:00Z','manual','high')")
            for table in ("mail_message_addresses", "mail_message_observations", "mail_messages",
                          "mailbox_sync_states", "mail_accounts", "mail_follow_up_preferences"):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("UPDATE storage_metadata SET value='4' WHERE key='schema_version'")
        with self.store.factory.read_connection() as connection:
            self.assertEqual(CURRENT_SCHEMA_VERSION, apply_schema_migrations(connection))
            self.assertEqual(CURRENT_SCHEMA_VERSION, schema_version(connection))
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM campaigns WHERE campaign_id='campaign'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM campaign_creators WHERE id='relation'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM campaign_creator_publish_links WHERE publication_id='publication'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM publication_performance_observations WHERE observation_id='observation'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM creators WHERE creator_id='creator'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM creator_accounts WHERE account_uid='account'").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
