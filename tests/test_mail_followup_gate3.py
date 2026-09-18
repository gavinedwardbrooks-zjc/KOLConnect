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

from services.mail_inbox_facts import (  # noqa: E402
    discover_sent_mailbox,
    rfc_correlation,
    sync_inbox,
    sync_sent,
)
import mail_sync  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


NOW = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
ACCOUNT = {
    "email": "owner@example.com",
    "username": "owner@example.com",
    "password": "fake-secret",
    "imap_host": "imap.example.com",
    "imap_port": 993,
}


def make_message(
    sender="creator@example.com", *, to="owner@example.com", cc="", message_id="<message@example.com>",
    in_reply_to=None, references=None, bcc="",
):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    message["Date"] = "Fri, 18 Sep 2026 09:00:00 +0000"
    if message_id is not None:
        message["Message-ID"] = message_id
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    message["Subject"] = "Collaboration"
    message.set_content("PRIVATE BODY")
    return message.as_bytes()


class FakeIMAP:
    def __init__(self, messages, *, folders=None, validity="1", internal_dates=None):
        self.messages = dict(messages)
        self.folders = folders if folders is not None else [b'(\\HasNoChildren \\Sent) "/" "Sent Mail"']
        self.validity = validity
        self.internal_dates = internal_dates or {}
        self.calls = []

    def login(self, *_args):
        return "OK", []

    def logout(self):
        return "BYE", []

    def list(self):
        return "OK", self.folders

    def select(self, _folder, readonly=False):
        self.calls.append(("select", _folder, readonly))
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code):
        self.assert_code = code
        return "UIDVALIDITY", [self.validity.encode()]

    def uid(self, action, *args):
        self.calls.append((action, args))
        if action == "search":
            if args[1] == "SINCE":
                selected = list(self.messages)
            else:
                low = int(args[2].split(":")[0])
                selected = [uid for uid in self.messages if int(uid) >= low]
            return "OK", [" ".join(selected).encode()]
        if action == "fetch":
            uid, query = args
            raw = self.messages[uid]
            internal_date = self.internal_dates.get(uid, NOW - timedelta(hours=1))
            metadata = internal_date.strftime("%d-%b-%Y %H:%M:%S %z")
            if "HEADER.FIELDS" in query:
                raw = raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
            return "OK", [(f'{uid} (INTERNALDATE "{metadata}")'.encode(), raw)]
        raise AssertionError(action)


class MailFollowupGate3Tests(unittest.TestCase):
    def setUp(self):
        base = test_artifact_path("mail_followup_gate3")
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

    def sync_sent(self, messages, *, folders=None, validity="1", internal_dates=None):
        instances = []

        def factory(*_args, **_kwargs):
            instance = FakeIMAP(messages, folders=folders, validity=validity, internal_dates=internal_dates)
            instances.append(instance)
            return instance

        return sync_sent(ACCOUNT, self.factory, imap_factory=factory, now=NOW), instances

    def test_special_use_and_conventional_sent_discovery_fail_closed_when_ambiguous(self):
        self.assertEqual("Archive", discover_sent_mailbox(FakeIMAP({}, folders=[b'(\\Sent) "/" "Archive"'])))
        self.assertEqual("Sent Items", discover_sent_mailbox(FakeIMAP({}, folders=[b'(\\HasNoChildren) "/" "Sent Items"'])))
        with self.assertRaisesRegex(RuntimeError, "not found"):
            discover_sent_mailbox(FakeIMAP({}, folders=[b'(\\HasNoChildren) "/" "Archive"']))
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            discover_sent_mailbox(FakeIMAP({}, folders=[b'(\\Sent) "/" "Sent"', b'(\\Sent) "/" "Sent Mail"']))

    def test_sent_first_sync_is_bounded_and_incremental_cursor_is_forward_only(self):
        messages = {str(uid): make_message(message_id=f"<{uid}@example.com>") for uid in range(1, 202)}
        result, instances = self.sync_sent(messages)
        self.assertEqual((200, "partial", 201, "Sent Mail"), (
            result["new"], result["history_coverage"], result["high_water_uid"], result["folder_name"],
        ))
        self.assertEqual("SINCE", instances[1].calls[1][1][1])
        next_result, instances = self.sync_sent({"202": make_message(message_id="<202@example.com>")})
        self.assertEqual(1, next_result["new"])
        self.assertEqual("UID", instances[1].calls[1][1][1])
        self.assertEqual(201, len(self.rows("mail_messages")))

    def test_sent_first_sync_excludes_internaldate_older_than_thirty_days_and_is_idempotent(self):
        result, _instances = self.sync_sent(
            {"1": make_message(message_id="<old@example.com>"), "2": make_message(message_id="<recent@example.com>")},
            internal_dates={"1": NOW - timedelta(days=31), "2": NOW - timedelta(days=30)},
        )
        self.assertEqual((1, "bounded", 2), (result["new"], result["history_coverage"], result["high_water_uid"]))
        repeated, _instances = self.sync_sent({"1": make_message(message_id="<old@example.com>"), "2": make_message(message_id="<recent@example.com>")})
        self.assertEqual(0, repeated["new"])
        self.assertEqual(1, len(self.rows("mail_messages")))

    def test_sent_uidvalidity_reset_and_remote_absence_preserve_facts_without_merge(self):
        self.sync_sent({"1": make_message(message_id="<same@example.com>")})
        reset, _ = self.sync_sent({"1": make_message(message_id="<same@example.com>")}, validity="2")
        self.assertEqual(1, reset["new"])
        self.assertEqual(2, len(self.rows("mail_messages")))
        self.assertEqual({"1", "2"}, {row["uidvalidity"] for row in self.rows("mail_message_observations")})
        absent, _ = self.sync_sent({}, validity="2")
        self.assertEqual(0, absent["new"])
        self.assertEqual(2, len(self.rows("mail_messages")))

    def test_sent_missing_rfc_message_id_is_a_valid_idempotent_observation_without_correlation(self):
        result, _instances = self.sync_sent({"1": make_message(message_id=None)})
        self.assertEqual(1, result["new"])
        [fact] = self.rows("mail_messages")
        self.assertIsNone(fact["rfc_message_id"])
        self.assertEqual("outbound", fact["direction"])
        repeated, _instances = self.sync_sent({"1": make_message(message_id=None)})
        self.assertEqual(0, repeated["new"])
        self.assertEqual(1, len(self.rows("mail_messages")))
        self.assertEqual("none", rfc_correlation(self.factory)["status"])

    def test_sent_direction_and_to_cc_ownership_rules_are_exact_and_fail_closed(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('a','A'),('b','B')")
            connection.execute(
                "INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES "
                "('a1','a','a@example.com'),('a2','a','alias-a@example.com'),('b1','b','b@example.com')"
            )
        self.sync_sent({
            "1": make_message("owner@example.com", to="a@example.com, outside@example.com", message_id="<one@example.com>"),
            "2": make_message("owner@example.com", to="a@example.com, alias-a@example.com", message_id="<multi@example.com>"),
            "3": make_message("owner@example.com", to="a@example.com, b@example.com", message_id="<to-conflict@example.com>"),
            "4": make_message("owner@example.com", to="a@example.com", cc="b@example.com", message_id="<cc-conflict@example.com>"),
            "5": make_message("owner@example.com", to="outside@example.com", cc="a@example.com", message_id="<cc-only@example.com>"),
        })
        facts = {row["rfc_message_id"]: row for row in self.rows("mail_messages")}
        self.assertEqual(("outbound", "matched", "a"), tuple(facts["<one@example.com>"][key] for key in ("direction", "match_status", "matched_creator_id")))
        self.assertEqual("matched_multi_account", facts["<multi@example.com>"]["match_status"])
        for key in ("<to-conflict@example.com>", "<cc-conflict@example.com>"):
            self.assertEqual(("ambiguous", None), (facts[key]["match_status"], facts[key]["matched_creator_id"]))
        self.assertEqual(("unmatched", None), (facts["<cc-only@example.com>"]["match_status"], facts["<cc-only@example.com>"]["matched_creator_id"]))
        addresses = {
            rfc_id: {
                (row["role"], row["normalized_address"]): row
                for row in self.rows("mail_message_addresses")
                if row["mail_message_id"] == fact["mail_message_id"]
            }
            for rfc_id, fact in facts.items()
        }
        single = addresses["<one@example.com>"]
        self.assertEqual(("unmatched", None, None), tuple(single[("from", "owner@example.com")][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))
        self.assertEqual(("matched", "a", "a1"), tuple(single[("to", "a@example.com")][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))
        self.assertEqual(("unmatched", None, None), tuple(single[("to", "outside@example.com")][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))
        conflict = addresses["<cc-conflict@example.com>"]
        self.assertEqual(("unmatched", None, None), tuple(conflict[("from", "owner@example.com")][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))
        self.assertEqual(("matched", "a", "a1"), tuple(conflict[("to", "a@example.com")][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))
        self.assertEqual(("unmatched", None, None), tuple(conflict[("cc", "b@example.com")][key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))

    def test_sent_fact_persistence_does_not_invoke_legacy_feishu_matching(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('a','A')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('a1','a','a@example.com')")
        with patch.object(mail_sync, "fetch_four_table_match_records", side_effect=AssertionError("Feishu must not run")):
            result, _instances = self.sync_sent({"1": make_message(to="a@example.com")})
        self.assertEqual(1, result["new"])
        [fact] = self.rows("mail_messages")
        self.assertEqual(("outbound", "matched", "a"), tuple(fact[key] for key in ("direction", "match_status", "matched_creator_id")))

    def test_mailbox_context_defines_direction_and_local_sender_is_not_creator_owned(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('owner','Owner')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('owner-a','owner','owner@example.com')")
        fake = FakeIMAP({"1": make_message("owner@example.com", message_id="<inbound@example.com>")})
        sync_inbox(ACCOUNT, self.factory, imap_factory=lambda *_a, **_k: fake, now=NOW)
        [fact] = self.rows("mail_messages")
        self.assertEqual(("inbound", "unmatched", None), tuple(fact[key] for key in ("direction", "match_status", "matched_creator_id")))

    def test_outbound_snapshot_survives_later_creator_account_reassignment(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('a','A'),('b','B')")
            connection.execute("INSERT INTO creator_accounts(account_uid,creator_id,account_email) VALUES ('a1','a','a@example.com')")
        self.sync_sent({"1": make_message(to="a@example.com", message_id="<snapshot@example.com>")})
        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE creator_accounts SET creator_id='b' WHERE account_uid='a1'")
        [fact] = self.rows("mail_messages")
        self.assertEqual(("matched", "a", "a1"), tuple(fact[key] for key in ("match_status", "matched_creator_id", "matched_account_uid")))

    def test_rfc_correlation_is_read_only_and_ambiguous_candidates_never_merge(self):
        inbound = FakeIMAP({"1": make_message(message_id="<inbound@example.com>")})
        sync_inbox(ACCOUNT, self.factory, imap_factory=lambda *_a, **_k: inbound, now=NOW)
        self.sync_sent({"1": make_message(to="creator@example.com", message_id="<outbound@example.com>", in_reply_to="<inbound@example.com>")})
        self.assertEqual("correlated", rfc_correlation(self.factory, in_reply_to="<inbound@example.com>")["status"])
        self.assertEqual("correlated", rfc_correlation(self.factory, references="<root@example.com> <outbound@example.com>")["status"])
        self.assertEqual("none", rfc_correlation(self.factory)["status"])
        self.sync_sent({"2": make_message(message_id="<inbound@example.com>")})
        correlation = rfc_correlation(self.factory, in_reply_to="<inbound@example.com>")
        self.assertEqual(("ambiguous", 2), (correlation["status"], len(correlation["mail_message_ids"])))
        self.assertEqual(3, len(self.rows("mail_messages")))

    def test_inbound_reply_correlates_to_outbound_without_identity_merge(self):
        self.sync_sent({"1": make_message(to="creator@example.com", message_id="<outbound@example.com>")})
        inbound = FakeIMAP({"1": make_message(message_id="<inbound-reply@example.com>", in_reply_to="<outbound@example.com>")})
        sync_inbox(ACCOUNT, self.factory, imap_factory=lambda *_a, **_k: inbound, now=NOW)
        correlation = rfc_correlation(self.factory, in_reply_to="<outbound@example.com>")
        self.assertEqual(("correlated", 1), (correlation["status"], len(correlation["mail_message_ids"])))
        self.assertEqual(2, len(self.rows("mail_messages")))

    def test_sent_privacy_excludes_bcc_body_html_and_attachment_metadata(self):
        message = EmailMessage()
        message["From"] = "owner@example.com"
        message["To"] = "creator@example.com"
        message["Bcc"] = "hidden@example.com"
        message["Date"] = "Fri, 18 Sep 2026 09:00:00 +0000"
        message["Message-ID"] = "<private@example.com>"
        message["Subject"] = "Private"
        message.set_content("PRIVATE BODY")
        message.add_attachment(b"private", maintype="application", subtype="octet-stream", filename="private.pdf")
        self.sync_sent({"1": message.as_bytes()})
        with self.factory.read_connection() as connection:
            fact = dict(connection.execute("SELECT * FROM mail_messages").fetchone())
            addresses = [dict(row) for row in connection.execute("SELECT * FROM mail_message_addresses")]
        self.assertNotIn("PRIVATE BODY", str(fact))
        self.assertNotIn("hidden@example.com", str(fact))
        self.assertNotIn("hidden@example.com", str(addresses))
        self.assertNotIn("private.pdf", str(fact))
        self.assertNotIn("private.pdf", str(addresses))


if __name__ == "__main__":
    unittest.main()
