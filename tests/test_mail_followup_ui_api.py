from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from http_handlers import mail_follow_up_handler  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


class Handler:
    def __init__(self):
        self.payload = None
        self.status = None
        self.binary = None

    def _json(self, payload, status=200):
        self.payload, self.status = payload, status

    def _binary(self, data, content_type, filename):
        self.binary = (data, content_type, filename)
        self.status = 200


class MailFollowUpUiApiTests(unittest.TestCase):
    def setUp(self):
        self.root = test_artifact_path("mail_followup_ui", uuid4().hex)
        self.root.mkdir()
        self.factory = SQLiteConnectionFactory(self.root / "mail.db")
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection)
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name,status) VALUES ('a','Creator A','active')")
            connection.execute("INSERT INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES ('mail','id','2026-01-01T00:00:00Z')")
            connection.execute("INSERT INTO mailbox_sync_states(mailbox_id,mail_account_id,folder_name,role,history_coverage) VALUES ('box','mail','INBOX','inbox','bounded')")
            connection.execute("INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,message_at,observed_at,correspondent_email,match_status,matched_creator_id) VALUES ('fact','mail','inbound','2026-09-17T10:00:00Z','2026-09-17T10:01:00Z','a@example.com','matched','a')")
            connection.execute("INSERT INTO mail_message_observations(observation_id,mail_message_id,mailbox_id,uidvalidity,imap_uid,observed_at) VALUES ('obs','fact','box','1','1','2026-09-17T10:01:00Z')")
            connection.execute("INSERT INTO mail_message_addresses(mail_message_id,role,position,original_address,normalized_address,match_status,matched_creator_id) VALUES ('fact','from',0,'a@example.com','a@example.com','matched','a')")

    def request(self, method, path, payload=None, query=None):
        handler = Handler()
        handled = mail_follow_up_handler.handle(handler, {
            "method": method, "path": path, "query": query or {}, "get_payload": lambda: payload or {},
        }, {"services": {"get_mail_connection_factory": lambda: self.factory}})
        self.assertTrue(handled)
        return handler

    def test_groups_keep_creator_and_correspondent_identity_and_honest_uncertainty(self):
        second = self.request("GET", "/api/mail/follow-up")
        self.assertTrue(second.payload["ok"])
        [group] = second.payload["groups"]
        self.assertEqual(("a", "Creator A", "a@example.com", "me", None), tuple(
            group[key] for key in ("creator_id", "creator_name", "correspondent_email", "waiting_for", "partial_history")
        ))
        missing = mail_follow_up_handler._with_creator_names(self.factory, [{
            "creator_id": "missing", "correspondent_email": "missing@example.com",
        }])
        self.assertEqual(("missing", "", "missing@example.com"), tuple(
            missing[0][key] for key in ("creator_id", "creator_name", "correspondent_email")
        ))

    def test_actions_use_group_local_preferences_without_business_mutation(self):
        self.request("POST", "/api/mail/follow-up/actions", {
            "action": "export_add", "creator_id": "a", "correspondent_email": "a@example.com",
        })
        self.request("POST", "/api/mail/follow-up/actions", {
            "action": "stop", "creator_id": "a", "correspondent_email": "a@example.com",
        })
        with self.factory.read_connection() as connection:
            preference = connection.execute("SELECT stopped_at,export_queue_added_at FROM mail_follow_up_preferences").fetchone()
            creator = connection.execute("SELECT status FROM creators WHERE creator_id='a'").fetchone()[0]
        self.assertTrue(preference[0])
        self.assertTrue(preference[1])
        self.assertEqual("active", creator)

    def test_actions_do_not_key_two_correspondents_by_creator_only(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,message_at,observed_at,correspondent_email,match_status,matched_creator_id) VALUES ('fact_b','mail','inbound','2026-09-18T10:00:00Z','2026-09-18T10:01:00Z','b@example.com','matched','a')")
            connection.execute("INSERT INTO mail_message_observations(observation_id,mail_message_id,mailbox_id,uidvalidity,imap_uid,observed_at) VALUES ('obs_b','fact_b','box','1','2','2026-09-18T10:01:00Z')")
            connection.execute("INSERT INTO mail_message_addresses(mail_message_id,role,position,original_address,normalized_address,match_status,matched_creator_id) VALUES ('fact_b','from',0,'b@example.com','b@example.com','matched','a')")
        self.request("POST", "/api/mail/follow-up/actions", {
            "action": "stop", "creator_id": "a", "correspondent_email": "a@example.com",
        })
        listed = self.request("GET", "/api/mail/follow-up").payload["groups"]
        rows = {row["correspondent_email"]: row for row in listed}
        self.assertEqual("stopped", rows["a@example.com"]["actionability"])
        self.assertEqual("normal", rows["b@example.com"]["actionability"])
        self.assertEqual("Creator A", rows["a@example.com"]["creator_name"])
        self.assertEqual("Creator A", rows["b@example.com"]["creator_name"])

    def test_csv_and_xlsx_exports_use_existing_queue_service(self):
        self.request("POST", "/api/mail/follow-up/actions", {
            "action": "export_add", "creator_id": "a", "correspondent_email": "a@example.com",
        })
        csv_result = self.request("GET", "/api/mail/follow-up/export", query={"format": ["csv"]})
        xlsx_result = self.request("GET", "/api/mail/follow-up/export", query={"format": ["xlsx"]})
        self.assertEqual("KOLConnect_Mail_Follow_Up_Queue.csv", csv_result.binary[2])
        self.assertIn(b"a@example.com", csv_result.binary[0])
        self.assertEqual("KOLConnect_Mail_Follow_Up_Queue.xlsx", xlsx_result.binary[2])
        self.assertGreater(len(xlsx_result.binary[0]), 100)


if __name__ == "__main__":
    unittest.main()
