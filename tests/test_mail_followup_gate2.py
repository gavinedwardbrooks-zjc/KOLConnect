from __future__ import annotations

import shutil
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from services.mail_inbox_facts import mail_account_identity, sync_inbox  # noqa: E402
import mail_sync  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import CURRENT_SCHEMA_VERSION, apply_schema_migrations, schema_version  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


NOW = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
ACCOUNT = {"email": "owner@example.com", "username": "owner@example.com",
           "password": "fake-secret", "imap_host": "imap.example.com", "imap_port": 993}


def make_message(sender="creator@example.com", *, date="Fri, 18 Sep 2026 09:00:00 +0000",
                 message_id="<shared@example.com>", to="owner@example.com, other@example.com",
                 cc="agency@example.com, reviewer@example.com"):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Cc"] = cc
    if date is not None:
        message["Date"] = date
    if message_id is not None:
        message["Message-ID"] = message_id
    message["In-Reply-To"] = "<parent@example.com>"
    message["References"] = "<root@example.com> <parent@example.com>"
    message["Subject"] = "Public collaboration"
    message.set_content("PRIVATE BODY MUST NOT BE IN SQLITE")
    return message.as_bytes()


class FakeIMAP:
    def __init__(self, messages, *, validity="123", internal_dates=None):
        self.messages = messages
        self.validity = validity
        self.internal_dates = internal_dates or {}
        self.calls = []

    def login(self, *_args):
        return "OK", []

    def select(self, folder, readonly=False):
        assert (folder, readonly) == ("INBOX", True)
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code):
        assert code == "UIDVALIDITY"
        return "UIDVALIDITY", [self.validity.encode()]

    def uid(self, action, *args):
        self.calls.append((action, args))
        if action == "search":
            if args[1] == "SINCE":
                uids = list(self.messages)
            else:
                low = int(args[2].split(":")[0])
                uids = [uid for uid in self.messages if int(uid) >= low]
            return "OK", [" ".join(uids).encode()]
        if action == "fetch":
            uid, query = args
            raw = self.messages[uid]
            internal_date = self.internal_dates.get(uid, NOW - timedelta(hours=1))
            date_text = internal_date.strftime("%d-%b-%Y %H:%M:%S %z")
            if "HEADER.FIELDS" in query:
                raw = raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
            return "OK", [(f'{uid} (INTERNALDATE "{date_text}")'.encode(), raw)]
        raise AssertionError(action)

    def logout(self):
        return "BYE", []


class MailFollowupGate2Tests(unittest.TestCase):
    def setUp(self):
        base = test_artifact_path("mail_followup_gate2")
        base.mkdir(exist_ok=True)
        self.root = base / uuid4().hex
        self.root.mkdir()
        self.factory = SQLiteConnectionFactory(self.root / "mail.db")
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def rows(self, table):
        with self.factory.read_connection() as connection:
            return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]

    def sync(self, messages, *, validity="123", dates=None, account=None):
        fake = FakeIMAP(messages, validity=validity, internal_dates=dates)
        result = sync_inbox(account or ACCOUNT, self.factory, imap_factory=lambda *_a, **_k: fake, now=NOW)
        return result, fake

    def test_schema_six_identity_constraints_and_nonsecret_account(self):
        self.assertEqual(6, CURRENT_SCHEMA_VERSION)
        with self.factory.read_connection() as connection:
            self.assertEqual(6, schema_version(connection))
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"mail_accounts", "mailbox_sync_states", "mail_messages",
                             "mail_message_observations", "mail_message_addresses",
                             "mail_follow_up_preferences"} <= names)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(mail_accounts)")}
            self.assertEqual({"mail_account_id", "identity_key", "created_at"}, columns)
        self.assertEqual([], self.rows("mail_follow_up_preferences"))
        first = mail_account_identity(ACCOUNT)[0]
        self.assertEqual(first, mail_account_identity({**ACCOUNT, "name": "New", "password": "rotated"})[0])
        self.assertNotEqual(first, mail_account_identity({**ACCOUNT, "imap_host": "new.host"})[0])
        self.assertNotEqual(first, mail_account_identity({**ACCOUNT, "imap_port": 143})[0])
        self.assertNotEqual(first, mail_account_identity({**ACCOUNT, "username": "different@example.com"})[0])
        self.assertNotEqual(first, mail_account_identity({**ACCOUNT, "email": "different@example.com"})[0])
        self.assertEqual(first, mail_account_identity(ACCOUNT)[0])

    def test_schema_five_migration_preserves_business_rows_and_is_idempotent(self):
        old_factory = SQLiteConnectionFactory(self.root / "old.db")
        with old_factory.read_connection() as connection:
            apply_schema_migrations(connection)
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('old_creator','Original')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('old_account','old_creator','old@example.com')")
            connection.execute("INSERT INTO products(product_id,name) VALUES ('old_product','Product')")
            for table in ("mail_message_addresses", "mail_message_observations", "mail_messages",
                          "mailbox_sync_states", "mail_accounts", "mail_follow_up_preferences"):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("UPDATE storage_metadata SET value='5' WHERE key='schema_version'")
        with old_factory.read_connection() as connection:
            self.assertEqual(5, schema_version(connection))
            self.assertEqual(6, apply_schema_migrations(connection))
            self.assertEqual(6, apply_schema_migrations(connection))
            self.assertEqual("Original", connection.execute("SELECT name FROM creators WHERE creator_id='old_creator'").fetchone()[0])
            self.assertEqual("old@example.com", connection.execute("SELECT account_email FROM creator_accounts WHERE account_uid='old_account'").fetchone()[0])
            self.assertEqual("Product", connection.execute("SELECT name FROM products WHERE product_id='old_product'").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM mail_messages").fetchone()[0])

    def test_feishu_unavailable_does_not_block_inbox_authority(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('c1','Creator')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('a1','c1','creator@example.com')")
        fake = FakeIMAP({"1": make_message()})
        with patch.object(mail_sync, "MAIL_MESSAGES_FILE", self.root / "cache.json"), patch.object(
            mail_sync, "fetch_four_table_match_records", side_effect=AssertionError("Feishu must not run")
        ), patch.object(
            mail_sync, "sync_inbox", side_effect=lambda account, factory, **kwargs: sync_inbox(account, factory, now=NOW, **kwargs)
        ):
            result = mail_sync.sync_enabled_mail_accounts(
                [{**ACCOUNT, "enabled": True}],
                {"connection_factory": self.factory, "imap_factory": lambda *_a, **_k: fake},
            )
            self.assertEqual([], result["errors"])
            self.assertEqual(1, result["messages_new"])
            self.assertEqual(1, result["matched_messages"])
            cache = mail_sync.load_mail_messages()
            self.assertEqual("c1", cache["messages"][0]["matched_creator_id"])
            cache["messages"].append({"id": "cache-only", "reply_status": "matched"})
            mail_sync.save_mail_messages(cache)
            again = mail_sync.sync_enabled_mail_accounts(
                [{**ACCOUNT, "enabled": True}],
                {"connection_factory": self.factory, "imap_factory": lambda *_a, **_k: FakeIMAP({"1": make_message()})},
            )
            self.assertEqual(0, again["messages_new"])
            self.assertEqual(1, again["messages_total"])
            self.assertEqual(1, again["matched_messages"])
        self.assertEqual("c1", self.rows("mail_messages")[0]["matched_creator_id"])
        self.assertEqual([], self.rows("mail_follow_up_preferences"))

    def test_duplicate_configured_mailbox_is_rejected_without_network(self):
        with patch.object(mail_sync, "MAIL_MESSAGES_FILE", self.root / "cache.json"):
            with self.assertRaisesRegex(ValueError, "配置了多次"):
                mail_sync.sync_enabled_mail_accounts(
                    [{**ACCOUNT, "enabled": True}, {**ACCOUNT, "enabled": True, "name": "Duplicate"}],
                    {"connection_factory": self.factory, "imap_factory": lambda *_a, **_k: self.fail("network")},
                )
        self.assertEqual([], self.rows("mail_accounts"))

    def test_sqlite_fact_recovers_missing_display_cache_without_json_bootstrap(self):
        self.sync({"1": make_message()})
        with patch.object(mail_sync, "MAIL_MESSAGES_FILE", self.root / "missing-cache.json"), patch.object(
            mail_sync, "sync_inbox", side_effect=lambda account, factory, **kwargs: sync_inbox(account, factory, now=NOW, **kwargs)
        ):
            result = mail_sync.sync_enabled_mail_accounts(
                [{**ACCOUNT, "enabled": True}],
                {"connection_factory": self.factory, "imap_factory": lambda *_a, **_k: FakeIMAP({"1": make_message()})},
            )
            self.assertEqual(0, result["messages_new"])
            [row] = mail_sync.load_mail_messages()["messages"]
            self.assertEqual("Public collaboration", row["subject"])
            self.assertEqual("creator@example.com", row["from_email"])
            self.assertEqual("", row["snippet"])
        self.assertEqual(1, len(self.rows("mail_messages")))

    def test_message_fact_headers_addresses_privacy_and_idempotency(self):
        result, _ = self.sync({"1": make_message()})
        self.assertEqual(1, result["new"])
        fact = self.rows("mail_messages")[0]
        self.assertEqual("2026-09-18T09:00:00Z", fact["message_at"])
        self.assertEqual("2026-09-18T10:00:00Z", fact["observed_at"])
        self.assertEqual("inbound", fact["direction"])
        self.assertEqual("<parent@example.com>", fact["in_reply_to"])
        self.assertIn("<root@example.com>", fact["reference_ids"])
        self.assertEqual(5, len(self.rows("mail_message_addresses")))
        self.assertEqual(0, self.sync({"1": make_message()})[0]["new"])
        self.assertEqual(1, len(self.rows("mail_message_observations")))
        self.assertEqual(1, len(self.rows("mail_messages")))
        self.assertNotIn("secret", str(self.rows("mail_accounts")))
        self.assertNotIn("PRIVATE BODY", str(self.rows("mail_messages")))
        self.assertNotIn("PRIVATE BODY", str(self.rows("mail_message_addresses")))

    def test_missing_duplicate_rfc_ids_and_invalid_dates(self):
        self.sync({"1": make_message(message_id=None, date=None),
                   "2": make_message(date="bad-date"), "3": make_message()})
        facts = self.rows("mail_messages")
        self.assertEqual(3, len(facts))
        self.assertEqual(2, sum(item["message_at"] is None for item in facts))
        self.assertEqual(2, sum(item["rfc_message_id"] == "<shared@example.com>" for item in facts))

    def test_two_configured_accounts_are_distinct_and_login_identity_is_not_inbound(self):
        first_account = {**ACCOUNT, "username": "login@example.com"}
        second_account = {**ACCOUNT, "email": "other-owner@example.com", "username": "other-owner@example.com"}
        self.sync({"1": make_message("login@example.com")}, account=first_account)
        self.sync({"1": make_message("creator@example.com")}, account=second_account)
        self.assertEqual(2, len(self.rows("mail_accounts")))
        # Mailbox context, rather than sender heuristics, is the authoritative
        # direction source once Gate 3 Sent observations exist.
        self.assertEqual({"inbound"}, {row["direction"] for row in self.rows("mail_messages")})

    def test_server_change_does_not_reuse_old_mailbox_cursor(self):
        self.sync({"1": make_message()})
        moved = {**ACCOUNT, "imap_host": "replacement.example.com"}
        result, fake = self.sync({"1": make_message()}, account=moved)
        self.assertEqual(1, result["new"])
        self.assertEqual("SINCE", fake.calls[0][1][1])
        self.assertEqual(2, len(self.rows("mail_accounts")))
        self.assertEqual(2, len(self.rows("mail_messages")))

    def test_observation_composite_identity_is_enforced_by_sqlite(self):
        self.sync({"1": make_message()})
        [observation] = self.rows("mail_message_observations")
        with self.assertRaises(Exception):
            with self.factory.write_transaction() as connection:
                connection.execute(
                    "INSERT INTO mail_message_observations(observation_id,mail_message_id,mailbox_id,uidvalidity,imap_uid,observed_at) VALUES (?,?,?,?,?,?)",
                    ("different", observation["mail_message_id"], observation["mailbox_id"],
                     observation["uidvalidity"], observation["imap_uid"], NOW.isoformat()),
                )

    def test_sqlite_local_matching_and_historical_snapshot(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('c1','Creator 1'),('c2','Creator 2')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('a1','c1',' Creator@Example.com '),('a2','c1','creator@example.com'),('a3','c2','other@example.com')")
        self.sync({"1": make_message(), "2": make_message("other@example.com"),
                   "3": make_message("nobody@example.com"), "4": make_message("owner@example.com")})
        facts = {row["correspondent_email"]: row for row in self.rows("mail_messages")}
        self.assertEqual(("matched_multi_account", "c1", None),
                         tuple(facts["creator@example.com"][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))
        self.assertEqual(("matched", "c2", "a3"),
                         tuple(facts["other@example.com"][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))
        self.assertEqual("unmatched", facts["nobody@example.com"]["match_status"])
        self.assertEqual("inbound", facts["owner@example.com"]["direction"])
        matched_fact_id = facts["other@example.com"]["mail_message_id"]
        matched_addresses = {
            (row["role"], row["normalized_address"]): row
            for row in self.rows("mail_message_addresses")
            if row["mail_message_id"] == matched_fact_id
        }
        self.assertEqual(("matched", "c2", "a3"), tuple(
            matched_addresses[("from", "other@example.com")][key]
            for key in ("match_status", "matched_creator_id", "matched_account_uid")
        ))
        self.assertEqual(("unmatched", None, None), tuple(
            matched_addresses[("to", "owner@example.com")][key]
            for key in ("match_status", "matched_creator_id", "matched_account_uid")
        ))
        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE creator_accounts SET creator_id='c2' WHERE account_uid='a2'")
        self.assertEqual("c1", next(row for row in self.rows("mail_messages") if row["correspondent_email"] == "creator@example.com")["matched_creator_id"])
        self.sync({"1": make_message(), "2": make_message("other@example.com"),
                   "3": make_message("nobody@example.com"), "4": make_message("owner@example.com"),
                   "5": make_message("creator@example.com")})
        newest = next(row for row in self.rows("mail_message_observations") if row["imap_uid"] == "5")
        with self.factory.read_connection() as connection:
            fact = connection.execute("SELECT * FROM mail_messages WHERE mail_message_id=?", (newest["mail_message_id"],)).fetchone()
        self.assertEqual("ambiguous", fact["match_status"])
        self.assertIsNone(fact["matched_creator_id"])

    def test_bounded_first_sync_incremental_and_remote_delete(self):
        recent = {str(uid): make_message() for uid in range(1, 241)}
        recent["1"] = make_message(date="Fri, 18 Sep 2037 09:00:00 +0000")
        dates = {"1": NOW - timedelta(days=31)}
        result, fake = self.sync(recent, dates=dates)
        self.assertEqual(200, result["new"])
        self.assertEqual("partial", result["history_coverage"])
        self.assertEqual(240, result["high_water_uid"])
        self.assertEqual("SINCE", fake.calls[0][1][1])
        self.assertEqual(200, len(self.rows("mail_messages")))
        second, fake = self.sync({"241": make_message()}, dates=dates)
        self.assertEqual(1, second["new"])
        self.assertEqual("partial", second["history_coverage"])
        self.assertEqual("UID", fake.calls[0][1][1])
        self.assertEqual(201, len(self.rows("mail_messages")))
        self.assertEqual(0, self.sync({})[0]["new"])
        self.assertEqual(201, len(self.rows("mail_messages")))

    def test_uidvalidity_reset_preserves_history_without_speculative_merge(self):
        self.sync({"1": make_message()})
        reset, fake = self.sync({"1": make_message()}, validity="124")
        self.assertEqual(1, reset["new"])
        self.assertEqual("SINCE", fake.calls[0][1][1])
        self.assertEqual(2, len(self.rows("mail_messages")))
        self.assertEqual({"123", "124"}, {row["uidvalidity"] for row in self.rows("mail_message_observations")})
        self.assertEqual(1, len({row["rfc_message_id"] for row in self.rows("mail_messages")}))

    def test_first_sync_under_cap_and_exact_mailbox_date_boundary(self):
        messages = {str(uid): make_message() for uid in range(1, 38)}
        dates = {"1": NOW - timedelta(days=31)}
        result, _ = self.sync(messages, dates=dates)
        self.assertEqual(36, result["new"])
        self.assertEqual("bounded", result["history_coverage"])
        self.assertEqual(37, result["high_water_uid"])
        self.assertEqual(36, len(self.rows("mail_messages")))

    def test_first_sync_uses_internaldate_not_uid_or_rfc_date_for_newest_cap(self):
        messages = {str(uid): make_message() for uid in range(1, 202)}
        dates = {"1": NOW, "201": NOW - timedelta(days=29)}
        result, _ = self.sync(messages, dates=dates)
        self.assertEqual(200, result["new"])
        observed_uids = {row["imap_uid"] for row in self.rows("mail_message_observations")}
        self.assertIn("1", observed_uids)
        self.assertNotIn("201", observed_uids)
        self.assertEqual("partial", result["history_coverage"])
        self.assertEqual(201, result["high_water_uid"])
        self.assertEqual(0, self.sync(messages)[0]["new"])

    def test_missing_uidvalidity_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "UIDVALIDITY"):
            self.sync({"1": make_message()}, validity="")
        self.assertEqual([], self.rows("mail_messages"))
        self.assertIsNone(self.rows("mailbox_sync_states")[0]["last_sync_at"])


if __name__ == "__main__":
    unittest.main()
