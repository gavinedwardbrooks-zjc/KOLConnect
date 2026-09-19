from __future__ import annotations

import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import mail_sync  # noqa: E402
from services.mail_follow_up import derive_follow_up_queue  # noqa: E402
from services.mail_inbox_facts import sync_sent  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


NOW = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
MAIL_ACCOUNT = {
    "email": "owner@example.com",
    "username": "owner@example.com",
    "password": "fake-secret",
    "imap_host": "imap.example.com",
    "imap_port": 993,
}


class FakeSentIMAP:
    def __init__(self, messages):
        self.messages = dict(messages)

    def login(self, *_args):
        return "OK", []

    def logout(self):
        return "BYE", []

    def list(self):
        return "OK", [b'(\\HasNoChildren \\Sent) "/" "Sent Mail"']

    def select(self, _folder, readonly=False):
        return "OK", [str(len(self.messages)).encode()]

    def response(self, _code):
        return "UIDVALIDITY", [b"1"]

    def uid(self, action, *args):
        if action == "search":
            return "OK", [b" ".join(uid.encode() for uid in self.messages)]
        if action == "fetch":
            uid, query = args
            raw = self.messages[uid]
            if "HEADER.FIELDS" in query:
                raw = raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
            return "OK", [(b'1 (INTERNALDATE "18-Sep-2026 09:00:00 +0000")', raw)]
        raise AssertionError(action)


def make_outbound_message():
    message = EmailMessage()
    message["From"] = "owner@example.com"
    message["To"] = "creator@example.com, outside@example.com"
    message["Date"] = "Fri, 18 Sep 2026 09:00:00 +0000"
    message["Message-ID"] = "<mixed-recipient@example.com>"
    message["Subject"] = "Collaboration"
    message.set_content("PRIVATE BODY")
    return message.as_bytes()


class MailFollowupGate4Tests(unittest.TestCase):
    def setUp(self):
        base = test_artifact_path("mail_followup_gate4")
        base.mkdir(exist_ok=True)
        self.root = base / uuid4().hex
        self.root.mkdir()
        self.factory = SQLiteConnectionFactory(self.root / "mail.db")
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection)
        self._add_creator("a")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _add_creator(self, creator_id, status="active"):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO creators(creator_id,name,status) VALUES (?,?,?)", (creator_id, creator_id, status))
            connection.execute("UPDATE creators SET status=? WHERE creator_id=?", (status, creator_id))

    def _add_fact(self, *, creator_id="a", email="a@example.com", direction="outbound", message_at="2026-09-17T10:00:00Z", status="matched", coverage="bounded", account_uid="a1", mailbox_id=None, suffix=None):
        suffix = suffix or uuid4().hex
        role = "from" if direction == "inbound" else "to"
        mailbox_id = mailbox_id or f"mailbox_{direction}"
        folder_name = mailbox_id if mailbox_id != f"mailbox_{direction}" else direction.upper()
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES ('mail','identity','2026-01-01T00:00:00Z')")
            connection.execute(
                "INSERT OR IGNORE INTO mailbox_sync_states(mailbox_id,mail_account_id,folder_name,role,history_coverage) VALUES (?,?,?,?,?)",
                (mailbox_id, "mail", folder_name, "inbox" if direction == "inbound" else "sent", coverage),
            )
            connection.execute("UPDATE mailbox_sync_states SET history_coverage=? WHERE mailbox_id=?", (coverage, mailbox_id))
            connection.execute(
                "INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,message_at,observed_at,correspondent_email,match_status,matched_creator_id,matched_account_uid) VALUES (?,?,?,?,?,?,?,?,?)",
                (f"fact_{suffix}", "mail", direction, message_at, "2026-09-18T10:00:00Z", email, status, creator_id if status != "ambiguous" else None, account_uid if status != "ambiguous" else None),
            )
            connection.execute(
                "INSERT INTO mail_message_observations(observation_id,mail_message_id,mailbox_id,uidvalidity,imap_uid,observed_at) VALUES (?,?,?,?,?,?)",
                (f"observation_{suffix}", f"fact_{suffix}", mailbox_id, "1", suffix[:8], "2026-09-18T10:00:00Z"),
            )
            connection.execute(
                "INSERT INTO mail_message_addresses(mail_message_id,role,position,original_address,normalized_address,match_status,matched_creator_id,matched_account_uid) VALUES (?,?,?,?,?,?,?,?)",
                (f"fact_{suffix}", role, 0, email, email, status, creator_id if status != "ambiguous" else None, account_uid if status != "ambiguous" else None),
            )
        return f"fact_{suffix}"

    def _queue(self):
        return derive_follow_up_queue(self.factory, now=NOW)

    def test_latest_direction_counts_and_days_are_group_local(self):
        self._add_fact(email="a@example.com", direction="outbound", message_at="2026-09-16T10:00:00Z")
        self._add_fact(email="a@example.com", direction="inbound", message_at="2026-09-17T10:00:00Z")
        self._add_fact(email="a@example.com", direction="outbound", message_at="2026-09-18T09:00:00Z")
        [row] = self._queue()
        self.assertEqual(("creator", "outbound", 1, 2, 0), tuple(row[key] for key in ("waiting_for", "latest_direction", "synced_inbound_count", "synced_outbound_count", "days_waiting")))
        self.assertEqual(("2026-09-17T10:00:00Z", "2026-09-18T09:00:00Z"), (row["last_inbound_at"], row["last_outbound_at"]))

    def test_latest_inbound_waits_for_me(self):
        self._add_fact(direction="outbound", message_at="2026-09-16T10:00:00Z")
        self._add_fact(direction="inbound", message_at="2026-09-17T10:00:00Z")
        [row] = self._queue()
        self.assertEqual(("me", "inbound", 1), tuple(row[key] for key in ("waiting_for", "latest_direction", "days_waiting")))

    def test_null_future_and_same_timestamp_conflicts_fail_closed(self):
        self._add_fact(email="null@example.com", message_at=None)
        self._add_fact(email="tie@example.com", direction="inbound", message_at="2026-09-17T10:00:00Z")
        self._add_fact(email="tie@example.com", direction="outbound", message_at="2026-09-17T10:00:00Z")
        self._add_fact(email="future@example.com", message_at="2026-09-19T10:00:00Z")
        rows = {row["correspondent_email"]: row for row in self._queue()}
        for email in ("null@example.com", "tie@example.com", "future@example.com"):
            self.assertEqual(("unknown", "unknown", None), tuple(rows[email][key] for key in ("waiting_for", "latest_direction", "days_waiting")))

    def test_days_waiting_uses_utc_elapsed_day_boundaries(self):
        self._add_fact(email="under-day@example.com", message_at="2026-09-17T10:01:00Z")
        self._add_fact(email="one-day@example.com", message_at="2026-09-17T10:00:00Z")
        self._add_fact(email="two-days@example.com", message_at="2026-09-16T10:00:00Z")
        self._add_fact(email="offset@example.com", message_at="2026-09-17T18:00:00+08:00")
        rows = {row["correspondent_email"]: row for row in self._queue()}
        self.assertEqual(0, rows["under-day@example.com"]["days_waiting"])
        self.assertEqual(1, rows["one-day@example.com"]["days_waiting"])
        self.assertEqual(2, rows["two-days@example.com"]["days_waiting"])
        self.assertEqual(1, rows["offset@example.com"]["days_waiting"])

    def test_history_coverage_preserves_unknown_completeness_as_none(self):
        self._add_fact(email="partial@example.com", coverage="partial", mailbox_id="partial_mailbox")
        self._add_fact(email="bounded@example.com", coverage="bounded", mailbox_id="bounded_mailbox")
        self._add_fact(email="unknown@example.com", coverage="unknown", mailbox_id="unknown_mailbox")
        rows = {row["correspondent_email"]: row for row in self._queue()}
        self.assertEqual(("partial", True), (rows["partial@example.com"]["history_coverage"], rows["partial@example.com"]["partial_history"]))
        self.assertEqual(("bounded", None), (rows["bounded@example.com"]["history_coverage"], rows["bounded@example.com"]["partial_history"]))
        self.assertEqual(("unknown", None), (rows["unknown@example.com"]["history_coverage"], rows["unknown@example.com"]["partial_history"]))

    def test_archived_and_rejected_are_excluded_completed_is_included(self):
        self._add_creator("archived", "archived")
        self._add_creator("rejected", "rejected")
        self._add_creator("completed", "completed")
        self._add_fact(creator_id="archived", email="archived@example.com")
        self._add_fact(creator_id="rejected", email="rejected@example.com")
        self._add_fact(creator_id="completed", email="completed@example.com")
        self.assertEqual({"completed"}, {row["creator_id"] for row in self._queue()})

    def test_historical_snapshot_grouping_does_not_reresolve_creator_accounts(self):
        self._add_fact(email="historical@example.com", account_uid="a1")
        self._add_creator("b")
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('a1','a','historical@example.com')")
            connection.execute("UPDATE creator_accounts SET creator_id='b' WHERE account_uid='a1'")
        [row] = self._queue()
        self.assertEqual(("a", "historical@example.com", "a1"), tuple(row[key] for key in ("creator_id", "correspondent_email", "creator_account_uid")))

    def test_no_history_unmatched_and_ambiguous_facts_create_no_confident_entry(self):
        self._add_creator("empty")
        self._add_fact(email="unmatched@example.com", status="unmatched")
        self._add_fact(email="ambiguous@example.com", status="ambiguous")
        self.assertEqual([], self._queue())

    def test_two_historical_correspondents_remain_separate_and_p1_snapshot_is_used(self):
        self._add_fact(email="first@example.com", direction="outbound", account_uid="a1")
        self._add_fact(email="second@example.com", direction="inbound", account_uid="a2")
        rows = {row["correspondent_email"]: row for row in self._queue()}
        self.assertEqual({"first@example.com", "second@example.com"}, set(rows))
        self.assertEqual(("creator", "first@example.com"), (rows["first@example.com"]["waiting_for"], rows["first@example.com"]["correspondent_email"]))

    def test_counts_use_mail_facts_not_multiple_observation_rows(self):
        fact_id = self._add_fact()
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO mail_message_observations(observation_id,mail_message_id,mailbox_id,uidvalidity,imap_uid,observed_at) VALUES ('second-observation',?,'mailbox_outbound','1','second','2026-09-18T10:00:00Z')",
                (fact_id,),
            )
        [row] = self._queue()
        self.assertEqual((0, 1), (row["synced_inbound_count"], row["synced_outbound_count"]))

    def test_gate3_mixed_recipient_snapshots_drive_one_historical_gate4_group(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('b','B')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('a1','a','creator@example.com')")

        def imap_factory(*_args, **_kwargs):
            return FakeSentIMAP({"1": make_outbound_message()})

        sync_sent(MAIL_ACCOUNT, self.factory, imap_factory=imap_factory, now=NOW)
        with self.factory.read_connection() as connection:
            addresses = {
                (row["role"], row["normalized_address"]): tuple(
                    row[key] for key in ("match_status", "matched_creator_id", "matched_account_uid")
                )
                for row in connection.execute("SELECT * FROM mail_message_addresses")
            }
        self.assertEqual(("unmatched", None, None), addresses[("from", "owner@example.com")])
        self.assertEqual(("matched", "a", "a1"), addresses[("to", "creator@example.com")])
        self.assertEqual(("unmatched", None, None), addresses[("to", "outside@example.com")])

        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE creator_accounts SET creator_id='b' WHERE account_uid='a1'")
        [row] = self._queue()
        self.assertEqual(("a", "creator@example.com", "outbound", "creator", 0, 1), tuple(
            row[key] for key in (
                "creator_id", "correspondent_email", "latest_direction", "waiting_for",
                "synced_inbound_count", "synced_outbound_count",
            )
        ))

    def test_derivation_is_read_only_and_independent_of_feishu_json_and_preferences(self):
        self._add_fact()
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO mail_follow_up_preferences(creator_id,correspondent_email_normalized,created_at,updated_at) VALUES ('a','a@example.com','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
            connection.execute("INSERT INTO campaigns(campaign_id,name) VALUES ('campaign','Campaign')")
            connection.execute("INSERT INTO campaign_creators(id,campaign_id,creator_id,stage) VALUES ('campaign_creator','campaign','a','contacted')")
            before = connection.execute("SELECT status FROM creators WHERE creator_id='a'").fetchone()[0]
        with patch.object(mail_sync, "fetch_four_table_match_records", side_effect=AssertionError("Feishu must not run")), patch.object(mail_sync, "load_mail_messages", side_effect=AssertionError("JSON must not run")):
            [row] = self._queue()
        with self.factory.read_connection() as connection:
            after = connection.execute("SELECT status FROM creators WHERE creator_id='a'").fetchone()[0]
            stage = connection.execute("SELECT stage FROM campaign_creators WHERE id='campaign_creator'").fetchone()[0]
            preferences = connection.execute("SELECT COUNT(*) FROM mail_follow_up_preferences").fetchone()[0]
        self.assertEqual("a", row["creator_id"])
        self.assertEqual(before, after)
        self.assertEqual("contacted", stage)
        self.assertEqual(1, preferences)


if __name__ == "__main__":
    unittest.main()
