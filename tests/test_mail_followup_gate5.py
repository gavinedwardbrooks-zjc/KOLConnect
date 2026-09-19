from __future__ import annotations

import csv
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.mail_follow_up_preferences import (  # noqa: E402
    actionable_follow_up_queue,
    add_to_export_queue,
    clear_snooze,
    export_queue,
    follow_up_state,
    reconcile_export_queue_from_sent,
    remove_from_export_queue,
    resume_follow_up,
    set_snooze,
    stop_follow_up,
    write_export_csv,
    write_export_xlsx,
)
from services.mail_inbox_facts import sync_sent  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


NOW = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
ACCOUNT = {"email": "owner@example.com", "username": "owner@example.com", "password": "fake-secret",
           "imap_host": "imap.example.com", "imap_port": 993}


class FakeSentIMAP:
    def __init__(self, messages):
        self.messages = dict(messages)

    def login(self, *_args): return "OK", []
    def logout(self): return "BYE", []
    def list(self): return "OK", [b'(\\HasNoChildren \\Sent) "/" "Sent Mail"']
    def select(self, _folder, readonly=False): return "OK", [str(len(self.messages)).encode()]
    def response(self, _code): return "UIDVALIDITY", [b"1"]

    def uid(self, action, *args):
        if action == "search":
            return "OK", [b" ".join(uid.encode() for uid in self.messages)]
        if action == "fetch":
            uid, query = args
            raw = self.messages[uid]
            if "HEADER.FIELDS" in query:
                raw = raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
            return "OK", [(b'1 (INTERNALDATE "18-Sep-2026 11:00:00 +0000")', raw)]
        raise AssertionError(action)


def sent_message(email: str, date: str, *, extra_to: str = "") -> bytes:
    message = EmailMessage()
    message["From"] = "owner@example.com"
    message["To"] = ", ".join(item for item in (email, extra_to) if item)
    message["Date"] = date
    message["Message-ID"] = f"<{email}>"
    message["Subject"] = "Private subject"
    message.set_content("PRIVATE BODY")
    return message.as_bytes()


class MailFollowupGate5Tests(unittest.TestCase):
    def setUp(self):
        self.root = test_artifact_path("mail_followup_gate5", uuid4().hex)
        self.root.mkdir()
        self.factory = SQLiteConnectionFactory(self.root / "mail.db")
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection)
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name,status) VALUES ('a','Creator A','active')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('a1','a','a@example.com')")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _add_fact(self, *, email="a@example.com", direction="outbound", message_at="2026-09-17T10:00:00Z",
                  observed_at="2026-09-18T10:00:00Z", status="matched", suffix=None):
        suffix = suffix or uuid4().hex
        role = "from" if direction == "inbound" else "to"
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES ('mail','identity','2026-01-01T00:00:00Z')")
            connection.execute("INSERT OR IGNORE INTO mailbox_sync_states(mailbox_id,mail_account_id,folder_name,role,history_coverage) VALUES ('mailbox','mail','Sent','sent','bounded')")
            connection.execute("INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,message_at,observed_at,correspondent_email,match_status,matched_creator_id,matched_account_uid) VALUES (?,?,?,?,?,?,?,?,?)",
                               (f"fact_{suffix}", "mail", direction, message_at, observed_at, email, status,
                                "a" if status in {"matched", "matched_multi_account"} else None, "a1" if status == "matched" else None))
            connection.execute("INSERT INTO mail_message_observations(observation_id,mail_message_id,mailbox_id,uidvalidity,imap_uid,observed_at) VALUES (?,?,?,?,?,?)",
                               (f"obs_{suffix}", f"fact_{suffix}", "mailbox", "1", suffix[:8], observed_at))
            connection.execute("INSERT INTO mail_message_addresses(mail_message_id,role,position,original_address,normalized_address,match_status,matched_creator_id,matched_account_uid) VALUES (?,?,?,?,?,?,?,?)",
                               (f"fact_{suffix}", role, 0, email, email, status,
                                "a" if status in {"matched", "matched_multi_account"} else None, "a1" if status == "matched" else None))
        return f"fact_{suffix}"

    def _preference(self, email="a@example.com"):
        with self.factory.read_connection() as connection:
            row = connection.execute("SELECT * FROM mail_follow_up_preferences WHERE creator_id='a' AND correspondent_email_normalized=?", (email,)).fetchone()
        return dict(row) if row else None

    def test_snooze_update_clear_and_stop_precedence_are_group_local(self):
        self._add_fact(email="a@example.com")
        self._add_fact(email="b@example.com")
        set_snooze(self.factory, "a", "a@example.com", NOW + timedelta(days=2), now=NOW)
        set_snooze(self.factory, "a", "a@example.com", NOW + timedelta(days=3), now=NOW + timedelta(minutes=1))
        stop_follow_up(self.factory, "a", "a@example.com", now=NOW + timedelta(minutes=2))
        state = {row["correspondent_email"]: row for row in follow_up_state(self.factory, now=NOW + timedelta(days=1))}
        self.assertEqual(("stopped", "2026-09-21T10:00:00Z"), (state["a@example.com"]["actionability"], state["a@example.com"]["snooze_until"]))
        self.assertEqual("normal", state["b@example.com"]["actionability"])
        resume_follow_up(self.factory, "a", "a@example.com", now=NOW + timedelta(minutes=3))
        self.assertEqual("snoozed", follow_up_state(self.factory, now=NOW + timedelta(days=1))[0]["actionability"])
        self.assertEqual("normal", follow_up_state(self.factory, now=NOW + timedelta(days=3))[0]["actionability"])
        self.assertEqual("normal", follow_up_state(self.factory, now=NOW + timedelta(days=4))[0]["actionability"])
        clear_snooze(self.factory, "a", "a@example.com", now=NOW + timedelta(minutes=4))
        self.assertEqual({"a@example.com", "b@example.com"}, {row["correspondent_email"] for row in actionable_follow_up_queue(self.factory, now=NOW)})

    def test_snooze_expiry_reveals_current_gate4_state(self):
        self._add_fact(direction="outbound")
        set_snooze(self.factory, "a", "a@example.com", NOW + timedelta(days=1), now=NOW)
        self._add_fact(direction="inbound", message_at="2026-09-19T09:00:00Z")
        [row] = actionable_follow_up_queue(self.factory, now=NOW + timedelta(days=2))
        self.assertEqual(("me", "inbound"), (row["waiting_for"], row["latest_direction"]))

    def test_export_membership_is_persistent_idempotent_and_generation_is_side_effect_free(self):
        self._add_fact()
        add_to_export_queue(self.factory, "a", "a@example.com", now=NOW)
        first = self._preference()["export_queue_added_at"]
        add_to_export_queue(self.factory, "a", "a@example.com", now=NOW + timedelta(days=1))
        self.assertEqual(first, self._preference()["export_queue_added_at"])
        with self.factory.read_connection() as connection:
            before = dict(connection.execute("SELECT direction,message_at,observed_at FROM mail_messages").fetchone())
        before_derived = {key: follow_up_state(self.factory, now=NOW)[0][key] for key in (
            "waiting_for", "latest_direction", "last_outbound_at", "synced_outbound_count",
        )}
        csv_path = write_export_csv(self.factory, self.root / "queue.csv", now=NOW)
        xlsx_path = write_export_xlsx(self.factory, self.root / "queue.xlsx", now=NOW)
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        workbook = load_workbook(xlsx_path, read_only=True)
        values = list(workbook.active.values)
        workbook.close()
        self.assertEqual("a@example.com", csv_rows[0]["correspondent_email"])
        self.assertEqual("a@example.com", values[1][2])
        self.assertNotIn("PRIVATE BODY", csv_path.read_text(encoding="utf-8-sig"))
        self.assertTrue(self._preference()["export_queue_added_at"])
        with self.factory.read_connection() as connection:
            self.assertEqual(before, dict(connection.execute("SELECT direction,message_at,observed_at FROM mail_messages").fetchone()))
        self.assertEqual(before_derived, {key: follow_up_state(self.factory, now=NOW)[0][key] for key in before_derived})
        self.assertTrue(remove_from_export_queue(self.factory, "a", "a@example.com", now=NOW))
        self.assertFalse(remove_from_export_queue(self.factory, "a", "a@example.com", now=NOW))
        add_to_export_queue(self.factory, "a", "a@example.com", now=NOW + timedelta(days=2))
        self.assertEqual("2026-09-20T10:00:00Z", self._preference()["export_queue_added_at"])
        reopened = SQLiteConnectionFactory(self.root / "mail.db")
        with reopened.read_connection() as connection:
            persisted = connection.execute(
                "SELECT export_queue_added_at FROM mail_follow_up_preferences "
                "WHERE creator_id='a' AND correspondent_email_normalized='a@example.com'"
            ).fetchone()[0]
        self.assertEqual("2026-09-20T10:00:00Z", persisted)

    def test_orphan_export_decision_is_preserved_but_not_exported(self):
        add_to_export_queue(self.factory, "a", "orphan@example.com", now=NOW)
        self.assertEqual([], export_queue(self.factory, now=NOW))
        self.assertTrue(self._preference("orphan@example.com")["export_queue_added_at"])

    def test_reconciliation_requires_exact_reliable_group_and_both_time_boundaries(self):
        add_to_export_queue(self.factory, "a", "a@example.com", now=NOW)
        old = self._add_fact(message_at="2026-09-17T10:00:00Z", observed_at="2026-09-19T10:00:00Z")
        different = self._add_fact(email="b@example.com", message_at="2026-09-19T10:00:00Z", observed_at="2026-09-19T10:00:00Z")
        ambiguous = self._add_fact(message_at="2026-09-19T10:00:00Z", observed_at="2026-09-19T10:00:00Z", status="ambiguous")
        unmatched = self._add_fact(message_at="2026-09-19T10:00:00Z", observed_at="2026-09-19T10:00:00Z", status="unmatched")
        missing_time = self._add_fact(message_at=None, observed_at="2026-09-19T10:00:00Z")
        invalid_time = self._add_fact(message_at="not-a-time", observed_at="2026-09-19T10:00:00Z")
        self.assertEqual(0, reconcile_export_queue_from_sent(
            self.factory, [old, different, ambiguous, unmatched, missing_time, invalid_time], now=NOW,
        ))
        self.assertTrue(self._preference()["export_queue_added_at"])
        safe = self._add_fact(message_at="2026-09-19T10:00:00Z", observed_at="2026-09-19T10:00:00Z")
        self.assertEqual(1, reconcile_export_queue_from_sent(self.factory, [safe], now=NOW))
        self.assertIsNone(self._preference()["export_queue_added_at"])

    def test_normal_sent_sync_reconciles_only_a_safe_later_message(self):
        add_to_export_queue(self.factory, "a", "a@example.com", now=NOW)
        later = NOW + timedelta(hours=2)
        result = sync_sent(
            ACCOUNT, self.factory,
            imap_factory=lambda *_args, **_kwargs: FakeSentIMAP({"1": sent_message("a@example.com", "Fri, 18 Sep 2026 12:00:00 +0000")}),
            now=later,
        )
        self.assertEqual(1, result["export_queue_reconciled"])
        self.assertIsNone(self._preference()["export_queue_added_at"])

    def test_reconciliation_failure_does_not_rollback_public_sent_sync(self):
        with self.factory.read_connection() as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM mail_messages").fetchone()[0])
        with patch(
            "services.mail_follow_up_preferences.reconcile_export_queue_from_sent",
            side_effect=RuntimeError("reconciliation unavailable"),
        ):
            result = sync_sent(
                ACCOUNT, self.factory,
                imap_factory=lambda *_args, **_kwargs: FakeSentIMAP({
                    "1": sent_message("a@example.com", "Fri, 18 Sep 2026 12:00:00 +0000"),
                }),
                now=NOW + timedelta(hours=2),
            )
        self.assertEqual(1, result["new"])
        self.assertEqual(0, result["export_queue_reconciled"])
        self.assertIn("reconciliation unavailable", result["export_queue_reconciliation_error"])
        with self.factory.read_connection() as connection:
            fact = dict(connection.execute("SELECT * FROM mail_messages").fetchone())
            observation_count = connection.execute("SELECT COUNT(*) FROM mail_message_observations").fetchone()[0]
            address = dict(connection.execute(
                "SELECT * FROM mail_message_addresses WHERE mail_message_id=? AND role='to'", (fact["mail_message_id"],)
            ).fetchone())
        self.assertEqual(("outbound", "matched", "a"), tuple(fact[key] for key in (
            "direction", "match_status", "matched_creator_id",
        )))
        self.assertEqual(1, observation_count)
        self.assertEqual(("a@example.com", "matched", "a"), tuple(address[key] for key in (
            "normalized_address", "match_status", "matched_creator_id",
        )))

    def test_mixed_recipient_sent_reconciles_only_the_matched_group(self):
        add_to_export_queue(self.factory, "a", "a@example.com", now=NOW)
        add_to_export_queue(self.factory, "a", "other@example.com", now=NOW)
        result = sync_sent(
            ACCOUNT, self.factory,
            imap_factory=lambda *_args, **_kwargs: FakeSentIMAP({
                "1": sent_message(
                    "a@example.com", "Fri, 18 Sep 2026 12:00:00 +0000", extra_to="unknown@example.com",
                ),
            }),
            now=NOW + timedelta(hours=2),
        )
        self.assertEqual(1, result["export_queue_reconciled"])
        with self.factory.read_connection() as connection:
            fact = connection.execute("SELECT mail_message_id FROM mail_messages").fetchone()
            addresses = {
                row["normalized_address"]: dict(row)
                for row in connection.execute(
                    "SELECT * FROM mail_message_addresses WHERE mail_message_id=?", (fact["mail_message_id"],)
                )
            }
        self.assertEqual(("unmatched", None), tuple(
            addresses["owner@example.com"][key] for key in ("match_status", "matched_creator_id")
        ))
        self.assertEqual(("matched", "a"), tuple(
            addresses["a@example.com"][key] for key in ("match_status", "matched_creator_id")
        ))
        self.assertEqual(("unmatched", None), tuple(
            addresses["unknown@example.com"][key] for key in ("match_status", "matched_creator_id")
        ))
        self.assertIsNone(self._preference("a@example.com")["export_queue_added_at"])
        self.assertTrue(self._preference("other@example.com")["export_queue_added_at"])
        self.assertIsNone(self._preference("unknown@example.com"))

    def test_preferences_do_not_block_sent_ingestion_or_business_state(self):
        set_snooze(self.factory, "a", "a@example.com", NOW + timedelta(days=1), now=NOW)
        stop_follow_up(self.factory, "a", "a@example.com", now=NOW)
        add_to_export_queue(self.factory, "a", "a@example.com", now=NOW)
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO campaigns(campaign_id,name) VALUES ('campaign','Campaign')")
            connection.execute("INSERT INTO campaign_creators(id,campaign_id,creator_id,stage) VALUES ('cc','campaign','a','contacted')")
        result = sync_sent(
            ACCOUNT, self.factory,
            imap_factory=lambda *_args, **_kwargs: FakeSentIMAP({"1": sent_message("a@example.com", "Fri, 18 Sep 2026 12:00:00 +0000")}),
            now=NOW + timedelta(hours=2),
        )
        with self.factory.read_connection() as connection:
            creator = connection.execute("SELECT status FROM creators WHERE creator_id='a'").fetchone()[0]
            stage = connection.execute("SELECT stage FROM campaign_creators WHERE id='cc'").fetchone()[0]
            facts = connection.execute("SELECT COUNT(*) FROM mail_messages").fetchone()[0]
        self.assertEqual(1, result["new"])
        self.assertEqual(("active", "contacted", 1), (creator, stage, facts))


if __name__ == "__main__":
    unittest.main()
