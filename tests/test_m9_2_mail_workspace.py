from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import sys
import unittest
from unittest import mock
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.mail_inbox_facts import mail_account_identity  # noqa: E402
from services.mail_send_service import MailSendError, MailSendService, SMTPExecutionResult  # noqa: E402
from services.mail_workspace_service import MailWorkspaceService, reconcile_sent_attempts, safe_message_text  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


ACCOUNT = {
    "name": "Primary", "provider": "custom", "email": "sender@example.com",
    "imap_host": "imap.example.com", "imap_port": "993", "smtp_host": "smtp.example.com",
    "smtp_port": "465", "username": "sender@example.com", "password": {"mock": True}, "enabled": True,
}
ACCOUNT_ID = mail_account_identity(ACCOUNT)[0]


class FakeMailbox:
    def __init__(self, raw: bytes, validity: str = "7"):
        self.raw = raw
        self.validity = validity
        self.selected = None
        self.fetches = []

    def login(self, *_args): return "OK", []
    def select(self, folder, readonly=False): self.selected = (folder, readonly); return "OK", [b"1"]
    def response(self, name): return name, [self.validity.encode()]
    def uid(self, operation, uid, query):
        self.fetches.append(query)
        if (operation, uid, query) == ("fetch", "42", "(RFC822.SIZE)"):
            return "OK", [(f"1 FETCH (RFC822.SIZE {len(self.raw)})".encode(), b"")]
        assert (operation, uid, query) == ("fetch", "42", "(BODY.PEEK[])")
        return "OK", [(b"1 FETCH", self.raw)]
    def logout(self): return "BYE", []


class AcceptExecutor:
    def send(self, *_args): return SMTPExecutionResult("accepted", "data", None, tuple())


class M92MailWorkspaceTests(unittest.TestCase):
    def setUp(self):
        root = test_artifact_path("m9_2_mail_workspace", uuid4().hex)
        root.mkdir(parents=True)
        self.factory = SQLiteConnectionFactory(root / "mail.db")
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection)
        self.now = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)

    def resolver(self, account_id):
        if account_id != ACCOUNT_ID:
            raise MailSendError("MAIL_ACCOUNT_NOT_FOUND", "missing", status=404)
        return dict(ACCOUNT)

    def insert_message_fact(self, *, rfc_message_id="<source@example.com>", observation_id="obs-source"):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO mail_accounts VALUES (?,?,?)", (ACCOUNT_ID, mail_account_identity(ACCOUNT)[1], "2026-10-28T08:00:00Z"))
            connection.execute(
                "INSERT INTO mailbox_sync_states(mailbox_id,mail_account_id,folder_name,role,uidvalidity) VALUES (?,?,?,?,?)",
                ("mailbox-inbox", ACCOUNT_ID, "INBOX", "inbox", "7"),
            )
            connection.execute(
                "INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,rfc_message_id,subject,observed_at,match_status) VALUES (?,?,?,?,?,?,?)",
                ("message-source", ACCOUNT_ID, "inbound", rfc_message_id, "Hello", "2026-10-28T08:00:00Z", "unmatched"),
            )
            connection.execute(
                "INSERT INTO mail_message_observations VALUES (?,?,?,?,?,?)",
                (observation_id, "message-source", "mailbox-inbox", "7", "42", "2026-10-28T08:00:00Z"),
            )

    def test_body_read_is_authority_bound_plain_preferred_and_not_persisted(self):
        self.insert_message_fact()
        message = EmailMessage()
        message["Subject"] = "Hello"
        message.set_content("safe plain body")
        message.add_alternative("<p>html body</p><script>secret()</script><img src='https://tracker'>", subtype="html")
        message.add_attachment(b"private attachment", maintype="application", subtype="octet-stream", filename="x.bin")
        mailbox = FakeMailbox(message.as_bytes())
        service = MailWorkspaceService(lambda: self.factory, self.resolver)
        with mock.patch("services.mail_workspace_service.open_imap_connection", return_value=(mailbox, {})) as opener:
            result = service.read_body("message-source")
        self.assertEqual(result["body_text"].strip(), "safe plain body")
        self.assertEqual(result["body_source"], "plain")
        self.assertTrue(result["attachments_omitted"])
        self.assertFalse(result["persisted"])
        self.assertEqual(opener.call_args.kwargs["folder"], "INBOX")
        with self.factory.read_connection() as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(mail_messages)")}
        self.assertNotIn("body_text", columns)

    def test_body_read_rejects_unknown_ambiguous_and_changed_uidvalidity(self):
        service = MailWorkspaceService(lambda: self.factory, self.resolver)
        with self.assertRaisesRegex(MailSendError, "不存在"):
            service.read_body("missing")
        self.insert_message_fact()
        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE mailbox_sync_states SET uidvalidity='8' WHERE mailbox_id='mailbox-inbox'")
        with self.assertRaisesRegex(MailSendError, "身份已变化"):
            service.read_body("message-source")

    def test_body_size_is_rejected_before_full_body_fetch(self):
        self.insert_message_fact()
        mailbox = FakeMailbox(b"x" * (2 * 1024 * 1024 + 1))
        service = MailWorkspaceService(lambda: self.factory, self.resolver)
        with mock.patch("services.mail_workspace_service.open_imap_connection", return_value=(mailbox, {})):
            with self.assertRaisesRegex(MailSendError, "超出安全读取限制"):
                service.read_body("message-source")
        self.assertEqual(mailbox.fetches, ["(RFC822.SIZE)"])

    def test_html_fallback_strips_active_content_and_attachments(self):
        message = EmailMessage()
        message.set_content("<p>Hello <b>Creator</b></p><style>.x{}</style><script>steal()</script>", subtype="html")
        text, source = safe_message_text(message.as_bytes())
        self.assertEqual(source, "html_text")
        self.assertIn("Hello Creator", text)
        self.assertNotIn("steal", text)
        self.assertNotIn(".x", text)

    def accepted_attempt(self):
        service = MailSendService(lambda: self.factory, self.resolver, executor=AcceptExecutor(), now=lambda: self.now)
        draft = service.create_draft({
            "context_type": "initial", "mail_account_id": ACCOUNT_ID, "from_address": ACCOUNT["email"],
            "to_addresses": ["creator@example.com"], "cc_addresses": [], "subject": "Hello", "body_text": "Body",
        })
        preview = service.create_preview(draft["draft_id"])
        authorization = service.authorize_preview(preview["preview_id"], "session", "human_direct")
        return service.send({
            "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
            "idempotency_key": f"test-{uuid4().hex}",
        }, "session")

    def insert_sent_observation(self, rfc_message_id, suffix):
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO mailbox_sync_states(mailbox_id,mail_account_id,folder_name,role,uidvalidity) VALUES (?,?,?,?,?)",
                ("mailbox-sent", ACCOUNT_ID, "Sent", "sent", "9"),
            )
            message_id = f"message-{suffix}"
            connection.execute(
                "INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,rfc_message_id,observed_at,match_status) VALUES (?,?,?,?,?,?)",
                (message_id, ACCOUNT_ID, "outbound", rfc_message_id, "2026-10-28T08:01:00Z", "unmatched"),
            )
            connection.execute(
                "INSERT INTO mail_message_observations VALUES (?,?,?,?,?,?)",
                (f"obs-{suffix}", message_id, "mailbox-sent", "9", suffix, "2026-10-28T08:01:00Z"),
            )

    def test_sent_reconciliation_requires_one_exact_same_account_rfc_match(self):
        attempt = self.accepted_attempt()
        first = reconcile_sent_attempts(self.factory, ACCOUNT_ID)
        self.assertEqual(first["unmatched"], 1)
        self.insert_sent_observation(attempt["rfc_message_id"], "1")
        second = reconcile_sent_attempts(self.factory, ACCOUNT_ID)
        self.assertEqual(second["reconciled"], 1)
        with self.factory.read_connection() as connection:
            row = connection.execute("SELECT reconciliation_status,sent_observation_id FROM mail_send_attempts").fetchone()
        self.assertEqual(tuple(row), ("reconciled", "obs-1"))

    def test_sent_reconciliation_marks_multiple_exact_observations_ambiguous(self):
        attempt = self.accepted_attempt()
        self.insert_sent_observation(attempt["rfc_message_id"], "1")
        self.insert_sent_observation(attempt["rfc_message_id"], "2")
        result = reconcile_sent_attempts(self.factory, ACCOUNT_ID)
        self.assertEqual(result["ambiguous"], 1)


if __name__ == "__main__":
    unittest.main()
