from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.mail_inbox_facts import mail_account_identity  # noqa: E402
from services.mail_send_service import MailSendError, MailSendService, SMTPExecutionResult  # noqa: E402
from services.mail_template_service import MailTemplateService  # noqa: E402
from services.mail_workspace_service import MailWorkspaceService, reconcile_sent_attempts, safe_message_text  # noqa: E402
from services.extension_workspace_service import ExtensionWorkspaceError, ExtensionWorkspaceService  # noqa: E402
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


class MissingMailbox(FakeMailbox):
    def uid(self, operation, uid, query):
        self.fetches.append(query)
        return "NO", [b"message no longer exists"]


class TimeoutMailbox(FakeMailbox):
    def uid(self, operation, uid, query):
        raise socket.timeout("timed out")


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
        with self.assertRaises(MailSendError) as raised:
            service.read_body("message-source")
        self.assertEqual("MAIL_UID_GENERATION_CHANGED", raised.exception.code)

    def test_body_size_is_rejected_before_full_body_fetch(self):
        self.insert_message_fact()
        mailbox = FakeMailbox(b"x" * (2 * 1024 * 1024 + 1))
        service = MailWorkspaceService(lambda: self.factory, self.resolver)
        with mock.patch("services.mail_workspace_service.open_imap_connection", return_value=(mailbox, {})):
            with self.assertRaisesRegex(MailSendError, "超出安全读取限制"):
                service.read_body("message-source")
        self.assertEqual(mailbox.fetches, ["(RFC822.SIZE)"])

    def test_body_read_classifies_remote_delete_and_timeout(self):
        self.insert_message_fact()
        service = MailWorkspaceService(lambda: self.factory, self.resolver)
        for mailbox, code in (
            (MissingMailbox(b""), "MAIL_MESSAGE_MOVED_OR_DELETED"),
            (TimeoutMailbox(b""), "MAIL_BODY_FETCH_TIMEOUT"),
        ):
            with self.subTest(code=code), mock.patch(
                "services.mail_workspace_service.open_imap_connection", return_value=(mailbox, {})
            ):
                with self.assertRaises(MailSendError) as raised:
                    service.read_body("message-source")
                self.assertEqual(code, raised.exception.code)

    def test_body_read_classifies_authentication_and_uid_generation(self):
        self.insert_message_fact()
        service = MailWorkspaceService(lambda: self.factory, self.resolver)
        from services.mail_auth_service import MailAuthenticationError

        with mock.patch(
            "services.mail_workspace_service.open_imap_connection",
            side_effect=MailAuthenticationError("MAIL_IMAP_AUTH_FAILED", "denied", protocol="imap", stage="auth"),
        ):
            with self.assertRaises(MailSendError) as raised:
                service.read_body("message-source")
        self.assertEqual("MAIL_AUTH_REQUIRED", raised.exception.code)

        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE mailbox_sync_states SET uidvalidity='8' WHERE mailbox_id='mailbox-inbox'")
        with self.assertRaises(MailSendError) as raised:
            service.read_body("message-source")
        self.assertEqual("MAIL_UID_GENERATION_CHANGED", raised.exception.code)

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

    def extension_workspace(self):
        identity = {
            "state": "recorded", "canonical_url": "https://www.tiktok.com/@creator",
            "creator_id": "creator-1", "creator_name": "Creator Name", "account_uid": "tiktok:creator",
            "account_email": "creator@example.com", "email_state": "present",
        }
        creator = mock.Mock()
        creator.get_extension_account_context.return_value = identity
        creator.lookup_extension_candidates.return_value = []
        templates = MailTemplateService(lambda: self.factory)
        sender = MailSendService(lambda: self.factory, self.resolver)
        service = ExtensionWorkspaceService(
            lambda: self.factory, lambda: creator, lambda: templates, lambda: sender, lambda: [dict(ACCOUNT)]
        )
        return service, templates

    def test_extension_workspace_persists_one_idempotent_draft_from_authoritative_template(self):
        service, templates = self.extension_workspace()
        options = service.options(
            platform="TikTok", profile_url="https://www.tiktok.com/@creator", audience_type="kol", language="en"
        )
        self.assertTrue(any(row["name"] == "Creator collaboration introduction" for row in options["templates"]))
        self.assertEqual(options["mail_accounts"][0]["mail_account_id"], ACCOUNT_ID)
        template = templates.get_template("builtin-initial-outreach-en-v1")
        payload = {
            "platform": "TikTok", "profile_url": "https://www.tiktok.com/@creator",
            "recipient_email": "creator@example.com", "creator_name": "Creator Name",
            "audience_type": "kol", "language": "en", "template_id": template["template_id"],
            "template_version": template["template_version"], "mail_account_id": ACCOUNT_ID,
            "idempotency_key": "extension-draft-request-1",
        }
        first = service.create_draft(payload)
        second = service.create_draft(payload)
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["draft"]["draft_id"], second["draft"]["draft_id"])
        self.assertEqual(first["draft"]["to_addresses"], ["creator@example.com"])
        self.assertIn("Creator Name", first["draft"]["body_text"])
        with self.factory.read_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM mail_drafts").fetchone()[0], 1)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(mail_templates)")}
            self.assertIn("audience_type", columns)

    def test_extension_workspace_rejects_recipient_or_template_version_mismatch(self):
        service, templates = self.extension_workspace()
        template = templates.get_template("builtin-initial-outreach-en-v1")
        base = {
            "platform": "TikTok", "profile_url": "https://www.tiktok.com/@creator",
            "recipient_email": "other@example.com", "creator_name": "Creator Name",
            "audience_type": "kol", "language": "en", "template_id": template["template_id"],
            "template_version": template["template_version"], "mail_account_id": ACCOUNT_ID,
            "idempotency_key": "extension-draft-request-2",
        }
        with self.assertRaises(ExtensionWorkspaceError) as recipient_error:
            service.create_draft(base)
        self.assertEqual(recipient_error.exception.code, "EXTENSION_RECIPIENT_MISMATCH")
        with self.assertRaises(ExtensionWorkspaceError) as version_error:
            service.create_draft({**base, "recipient_email": "creator@example.com", "template_version": 99})
        self.assertEqual(version_error.exception.code, "MAIL_TEMPLATE_VERSION_CONFLICT")


if __name__ == "__main__":
    unittest.main()
