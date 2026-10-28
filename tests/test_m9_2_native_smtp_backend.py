from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import multiprocessing
import os
import smtplib
import sys
import threading
import unittest
from unittest import mock
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from http_handlers import mail_send_handler  # noqa: E402
from services.mail_inbox_facts import mail_account_identity  # noqa: E402
from services.mail_send_security import COOKIE_NAME, CSRF_HEADER, MailSendSessionStore  # noqa: E402
from services.mail_send_service import (  # noqa: E402
    MailSendError,
    MailSendService,
    SMTPExecutionResult,
    SMTPExecutor,
)
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import CURRENT_SCHEMA_VERSION, apply_schema_migrations, schema_version  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


NOW = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
ACCOUNT = {
    "name": "Primary",
    "provider": "custom",
    "email": "sender@example.com",
    "sender_name": "KOLConnect User",
    "imap_host": "imap.example.com",
    "imap_port": "993",
    "smtp_host": "smtp.example.com",
    "smtp_port": "465",
    "username": "sender@example.com",
    "password": {"format": "mock"},
    "enabled": True,
}
ACCOUNT_ID = mail_account_identity(ACCOUNT)[0]


def _process_account_resolver(account_id):
    if account_id != ACCOUNT_ID:
        raise MailSendError("MAIL_ACCOUNT_NOT_FOUND", "missing", status=404)
    return dict(ACCOUNT)


class ProcessRecordingExecutor:
    def __init__(self, marker_directory):
        self.marker_directory = Path(marker_directory)

    def send(self, _account, _snapshot, _message_id):
        self.marker_directory.mkdir(parents=True, exist_ok=True)
        (self.marker_directory / f"call-{os.getpid()}-{uuid4().hex}").write_text("called", encoding="utf-8")
        return SMTPExecutionResult("accepted", "data", None, tuple())


def _process_send_worker(database_path, marker_directory, start_event, result_queue, payload, session_id):
    try:
        factory = SQLiteConnectionFactory(Path(database_path))
        service = MailSendService(
            lambda: factory,
            _process_account_resolver,
            executor=ProcessRecordingExecutor(marker_directory),
            now=lambda: NOW,
        )
        start_event.wait(timeout=10)
        result_queue.put(("ok", service.send(payload, session_id)["attempt_id"]))
    except Exception as exc:  # pragma: no cover - returned to parent for assertion
        result_queue.put(("error", f"{type(exc).__name__}:{exc}"))


class Clock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value


class RecordingExecutor:
    def __init__(self, result=None, started=None, release=None):
        self.calls = []
        self.result = result or SMTPExecutionResult("accepted", "data", None, tuple())
        self.started = started
        self.release = release

    def send(self, account, snapshot, message_id):
        self.calls.append((dict(account), dict(snapshot), message_id))
        if self.started:
            self.started.set()
        if self.release:
            self.release.wait(timeout=5)
        return self.result


class FakeSMTP:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.message = b""
        self.rcpt_results = {}
        self.data_result = (250, b"accepted")
        self.data_error = None
        self.auth_error = None

    def ehlo(self):
        self.calls.append("ehlo")
        return 250, b"ok"

    def has_extn(self, name):
        return name == "starttls"

    def starttls(self, context=None):
        self.calls.append("starttls")
        return 220, b"ready"

    def login(self, username, password):
        self.calls.append(("login", username, password))
        if self.auth_error:
            raise self.auth_error
        return 235, b"ok"

    def mail(self, sender):
        self.calls.append(("mail", sender))
        return 250, b"ok"

    def rcpt(self, recipient):
        self.calls.append(("rcpt", recipient))
        return self.rcpt_results.get(recipient, (250, b"ok"))

    def data(self, message):
        self.calls.append("data")
        self.message = message
        if self.data_error:
            raise self.data_error
        return self.data_result

    def quit(self):
        self.calls.append("quit")


class M92NativeSMTPBackendTests(unittest.TestCase):
    def setUp(self):
        self.root = test_artifact_path("m9_2_native_smtp", uuid4().hex)
        self.root.mkdir(parents=True)
        self.factory = SQLiteConnectionFactory(self.root / "mail.db")
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection)
        self.clock = Clock()
        self.executor = RecordingExecutor()
        self.service = MailSendService(
            lambda: self.factory,
            self.resolve_account,
            executor=self.executor,
            now=self.clock,
        )

    @staticmethod
    def resolve_account(account_id):
        if account_id != ACCOUNT_ID:
            raise MailSendError("MAIL_ACCOUNT_NOT_FOUND", "missing", status=404)
        return dict(ACCOUNT)

    def draft_payload(self, **overrides):
        payload = {
            "context_type": "initial",
            "mail_account_id": ACCOUNT_ID,
            "from_address": "sender@example.com",
            "to_addresses": ["creator@example.com"],
            "cc_addresses": [],
            "reply_to_address": "",
            "subject": "Hello",
            "body_text": "A safe body.",
        }
        payload.update(overrides)
        return payload

    def authorized(self, source="human_direct", session="session-a"):
        draft = self.service.create_draft(self.draft_payload())
        preview = self.service.create_preview(draft["draft_id"])
        authorization = self.service.authorize_preview(preview["preview_id"], session, source)
        return draft, preview, authorization

    def test_schema_six_to_seven_is_lossless_and_idempotent(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('kept','Kept')")
            for table in (
                "mail_ai_draft_candidates", "mail_templates",
                "mail_send_recipient_results", "mail_send_attempts", "mail_send_authorizations",
                "mail_send_previews", "mail_drafts",
            ):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("UPDATE storage_metadata SET value='6' WHERE key='schema_version'")
        with self.factory.read_connection() as connection:
            self.assertEqual(6, schema_version(connection))
            self.assertEqual(8, apply_schema_migrations(connection))
            self.assertEqual(8, apply_schema_migrations(connection))
            self.assertEqual("Kept", connection.execute("SELECT name FROM creators WHERE creator_id='kept'").fetchone()[0])
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(8, CURRENT_SCHEMA_VERSION)
        self.assertTrue({"mail_drafts", "mail_send_previews", "mail_send_authorizations",
                         "mail_send_attempts", "mail_send_recipient_results"} <= names)

    def test_migration_failure_rolls_back_without_partial_schema(self):
        with self.factory.write_transaction() as connection:
            for table in (
                "mail_ai_draft_candidates", "mail_templates",
                "mail_send_recipient_results", "mail_send_attempts", "mail_send_authorizations",
                "mail_send_previews", "mail_drafts",
            ):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("UPDATE storage_metadata SET value='6' WHERE key='schema_version'")

        class FailingConnection:
            def __init__(self, inner):
                self.inner = inner

            def execute(self, sql, parameters=()):
                if "CREATE TABLE mail_send_authorizations" in sql:
                    raise RuntimeError("injected migration failure")
                return self.inner.execute(sql, parameters)

            def commit(self):
                return self.inner.commit()

            def rollback(self):
                return self.inner.rollback()

        with self.factory.read_connection() as connection:
            with self.assertRaisesRegex(RuntimeError, "injected"):
                apply_schema_migrations(FailingConnection(connection))
            self.assertEqual(6, schema_version(connection))
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("mail_drafts", names)

    def test_edit_increments_version_and_invalidates_preview(self):
        draft = self.service.create_draft(self.draft_payload())
        preview = self.service.create_preview(draft["draft_id"])
        updated = self.service.update_draft(draft["draft_id"], {"version": 1, "subject": "Changed"})
        self.assertEqual(2, updated["version"])
        self.assertEqual("Changed", updated["subject"])
        self.assertTrue(self.service.get_preview(preview["preview_id"])["invalidated_at"])
        with self.assertRaisesRegex(MailSendError, "失效"):
            self.service.authorize_preview(preview["preview_id"], "session-a", "human_direct")

    def test_headers_and_addresses_reject_crlf_injection(self):
        cases = (
            {"from_address": "sender@example.com\r\nBcc: evil@example.com"},
            {"to_addresses": ["creator@example.com\r\nBcc: evil@example.com"]},
            {"cc_addresses": ["cc@example.com\nX-Test: bad"]},
            {"reply_to_address": "reply@example.com\r\nX-Test: bad"},
            {"subject": "Hello\r\nBcc: evil@example.com"},
        )
        for override in cases:
            with self.subTest(override=override), self.assertRaises(MailSendError):
                self.service.create_draft(self.draft_payload(**override))

    def test_reply_requires_authoritative_message_id_and_matching_mailbox(self):
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES (?,?,?)",
                (ACCOUNT_ID, mail_account_identity(ACCOUNT)[1], "2026-10-28T00:00:00Z"),
            )
            connection.execute(
                "INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,rfc_message_id,reference_ids,"
                "observed_at,match_status) VALUES ('reply-fact',?,'inbound','<source@example.com>',?,?,'matched')",
                (ACCOUNT_ID, '["<older@example.com>"]', "2026-10-28T00:00:00Z"),
            )
        draft = self.service.create_draft(self.draft_payload(
            context_type="reply", reply_mail_message_id="reply-fact", subject="Re: Hello"
        ))
        self.assertEqual("<source@example.com>", draft["in_reply_to"])
        self.assertEqual(["<older@example.com>", "<source@example.com>"], draft["reference_ids"])
        with self.assertRaises(MailSendError):
            self.service.create_draft(self.draft_payload(context_type="reply", reply_mail_message_id="missing"))

    def test_confirmation_is_session_bound_single_use_and_future_source_is_disabled(self):
        _draft, preview, authorization = self.authorized()
        with self.assertRaisesRegex(MailSendError, "会话"):
            self.service.send({
                "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
                "idempotency_key": "send-session-mismatch-0001",
            }, "session-b")
        first = self.service.send({
            "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
            "idempotency_key": "send-session-correct-00001",
        }, "session-a")
        self.assertEqual("accepted", first["outcome"])
        with self.assertRaisesRegex(MailSendError, "已使用"):
            self.service.send({
                "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
                "idempotency_key": "send-replay-new-key-000001",
            }, "session-a")
        with self.assertRaisesRegex(MailSendError, "尚未启用"):
            self.service.authorize_preview(preview["preview_id"], "session-a", "future_scoped_ai_authorization")

    def test_confirmation_expiry_and_preview_tampering_fail_closed(self):
        draft, preview, authorization = self.authorized()
        self.clock.value += timedelta(minutes=6)
        with self.assertRaisesRegex(MailSendError, "过期"):
            self.service.send({
                "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
                "idempotency_key": "send-expired-confirm-0001",
            }, "session-a")
        self.clock.value = NOW
        _draft2, preview2, authorization2 = self.authorized(session="session-b")
        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE mail_send_previews SET subject='tampered' WHERE preview_id=?", (preview2["preview_id"],))
        with self.assertRaisesRegex(MailSendError, "变化"):
            self.service.send({
                "preview_id": preview2["preview_id"], "confirmation_token": authorization2["confirmation_token"],
                "idempotency_key": "send-tampered-preview-001",
            }, "session-b")
        self.assertEqual(0, len(self.executor.calls))

    def test_duplicate_idempotency_key_executes_transport_once(self):
        _draft, preview, authorization = self.authorized()
        payload = {
            "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
            "idempotency_key": "send-idempotent-request-001",
        }
        first = self.service.send(payload, "session-a")
        second = self.service.send({**payload, "confirmation_token": "not-reused"}, "session-a")
        self.assertEqual(first["attempt_id"], second["attempt_id"])
        self.assertEqual(1, len(self.executor.calls))
        self.assertRegex(first["rfc_message_id"], r"^<[^<>\s]+@[^<>\s]+>$")

    def test_human_approved_ai_proposal_still_requires_and_accepts_human_confirmation(self):
        _draft, preview, authorization = self.authorized(source="human_approved_ai_proposal")
        result = self.service.send({
            "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
            "idempotency_key": "send-human-approved-ai-0001",
        }, "session-a")
        self.assertEqual("accepted", result["outcome"])
        self.assertEqual("human_approved_ai_proposal", result["authorization_source"])

    def test_request_transport_overrides_are_ignored(self):
        draft = self.service.create_draft(self.draft_payload(
            smtp_host="evil.example", smtp_port=25, password="attacker-secret"
        ))
        preview = self.service.create_preview(draft["draft_id"])
        authorization = self.service.authorize_preview(preview["preview_id"], "session-a", "human_direct")
        self.service.send({
            "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
            "idempotency_key": "send-ignore-transport-0001", "smtp_host": "evil.example", "password": "bad",
        }, "session-a")
        [account, _snapshot, _message_id] = self.executor.calls[0]
        self.assertEqual("smtp.example.com", account["smtp_host"])
        self.assertNotEqual("attacker-secret", account["password"])

    def test_concurrent_duplicate_post_has_one_durable_execution(self):
        started, release = threading.Event(), threading.Event()
        executor = RecordingExecutor(started=started, release=release)
        service = MailSendService(lambda: self.factory, self.resolve_account, executor=executor, now=self.clock)
        draft = service.create_draft(self.draft_payload())
        preview = service.create_preview(draft["draft_id"])
        authorization = service.authorize_preview(preview["preview_id"], "session-a", "human_direct")
        payload = {"preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
                   "idempotency_key": "send-concurrent-request-001"}
        results, errors = [], []

        def worker():
            try:
                results.append(service.send(payload, "session-a"))
            except Exception as exc:  # pragma: no cover - assertion captures it
                errors.append(exc)

        first = threading.Thread(target=worker)
        second = threading.Thread(target=worker)
        first.start()
        self.assertTrue(started.wait(timeout=5))
        second.start()
        second.join(timeout=5)
        release.set()
        first.join(timeout=5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        self.assertEqual(1, len(executor.calls))
        self.assertEqual(1, len({row["attempt_id"] for row in results}))

    def test_cross_process_duplicate_uses_database_unique_constraint(self):
        _draft, preview, authorization = self.authorized()
        payload = {
            "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
            "idempotency_key": "send-cross-process-request-01",
        }
        context = multiprocessing.get_context("spawn")
        start = context.Event()
        results = context.Queue()
        marker_directory = self.root / "transport-calls"
        processes = [
            context.Process(
                target=_process_send_worker,
                args=(str(self.factory.database_path), str(marker_directory), start, results, payload, "session-a"),
            )
            for _index in range(2)
        ]
        for process in processes:
            process.start()
        start.set()
        outcomes = [results.get(timeout=20) for _process in processes]
        for process in processes:
            process.join(timeout=20)
            self.assertEqual(0, process.exitcode)
        self.assertEqual(["ok", "ok"], sorted(item[0] for item in outcomes))
        self.assertEqual(1, len({item[1] for item in outcomes}))
        self.assertEqual(1, len(list(marker_directory.glob("call-*"))))

    def test_restart_marks_started_attempt_unknown_and_never_executes(self):
        _draft, preview, authorization = self.authorized()
        original = self.executor

        def interrupt(_account, _snapshot, _message_id):
            raise KeyboardInterrupt()

        self.service._executor = mock.Mock(send=interrupt)
        with self.assertRaises(KeyboardInterrupt):
            self.service.send({
                "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
                "idempotency_key": "send-crash-recovery-00001",
            }, "session-a")
        recovered = MailSendService(lambda: self.factory, self.resolve_account, executor=original, now=self.clock)
        self.assertEqual(1, recovered.recover_interrupted_attempts())
        with self.factory.read_connection() as connection:
            row = connection.execute("SELECT outcome,safe_error_code FROM mail_send_attempts").fetchone()
        self.assertEqual(("unknown", "MAIL_SMTP_RESULT_UNKNOWN"), tuple(row))
        self.assertEqual(0, len(original.calls))

    def test_account_and_business_authority_are_not_mutated(self):
        with self.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name,status) VALUES ('creator','Creator','active')")
            connection.execute("INSERT INTO campaigns(campaign_id,name,status) VALUES ('campaign','Campaign','进行中')")
        _draft, preview, authorization = self.authorized()
        self.service.send({"preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
                           "idempotency_key": "send-no-business-mutation-1"}, "session-a")
        with self.factory.read_connection() as connection:
            creator = connection.execute("SELECT status FROM creators WHERE creator_id='creator'").fetchone()[0]
            campaign = connection.execute("SELECT status FROM campaigns WHERE campaign_id='campaign'").fetchone()[0]
        self.assertEqual("active", creator)
        self.assertEqual("进行中", campaign)

    def test_draft_deletion_purges_unsent_content_and_redacts_sent_content(self):
        unsent = self.service.create_draft(self.draft_payload(subject="Unsent", body_text="private unsent"))
        self.assertEqual(
            {"draft_id": unsent["draft_id"], "deleted": True, "content_redacted": False},
            self.service.delete_draft(unsent["draft_id"], unsent["version"]),
        )
        with self.assertRaisesRegex(MailSendError, "不存在"):
            self.service.get_draft(unsent["draft_id"])

        draft, preview, authorization = self.authorized()
        self.service.send({
            "preview_id": preview["preview_id"], "confirmation_token": authorization["confirmation_token"],
            "idempotency_key": "send-before-content-delete-1",
        }, "session-a")
        result = self.service.delete_draft(draft["draft_id"], draft["version"])
        self.assertTrue(result["content_redacted"])
        redacted = self.service.get_draft(draft["draft_id"])
        self.assertEqual(("", "", [], []), (redacted["subject"], redacted["body_text"],
                                             redacted["to_addresses"], redacted["cc_addresses"]))
        self.assertTrue(redacted["content_deleted_at"])
        with self.factory.read_connection() as connection:
            attempt_id = connection.execute(
                "SELECT attempt_id FROM mail_send_attempts WHERE draft_id=?", (draft["draft_id"],)
            ).fetchone()[0]
        attempt = self.service.get_attempt(attempt_id, "session-a")
        self.assertEqual("accepted", attempt["outcome"])
        with self.assertRaisesRegex(MailSendError, "已删除"):
            self.service.create_preview(draft["draft_id"])


class SMTPExecutorClassificationTests(unittest.TestCase):
    def snapshot(self):
        return {
            "from_address": "sender@example.com", "to_addresses": ["one@example.com", "two@example.com"],
            "cc_addresses": [], "reply_to_address": None, "subject": "Unicode 主题", "body_text": "正文",
            "in_reply_to": None, "reference_ids": [],
        }

    def executor(self, fake):
        return SMTPExecutor(smtp_ssl_factory=lambda *_a, **_k: fake, secret_resolver=lambda _value: "secret")

    def test_data_accept_and_partial_recipient_rejection(self):
        fake = FakeSMTP()
        fake.rcpt_results["two@example.com"] = (550, b"rejected")
        result = self.executor(fake).send(ACCOUNT, self.snapshot(), "<message@kolconnect.local>")
        self.assertEqual("accepted", result.outcome)
        self.assertEqual(["accepted", "rejected"], [row["outcome"] for row in result.recipients])
        self.assertIn(b"Message-ID: <message@kolconnect.local>", fake.message)
        self.assertNotIn(b"secret", fake.message)

    def test_explicit_data_rejection_is_failed(self):
        fake = FakeSMTP()
        fake.data_result = (554, b"rejected")
        result = self.executor(fake).send(ACCOUNT, self.snapshot(), "<message@kolconnect.local>")
        self.assertEqual(("failed", "data", "MAIL_SMTP_DATA_REJECTED"),
                         (result.outcome, result.stage, result.safe_error_code))

    def test_data_timeout_is_unknown_but_auth_failure_is_failed(self):
        timed_out = FakeSMTP()
        timed_out.data_error = TimeoutError("private remote response")
        result = self.executor(timed_out).send(ACCOUNT, self.snapshot(), "<message@kolconnect.local>")
        self.assertEqual(("unknown", "data"), (result.outcome, result.stage))
        auth_failed = FakeSMTP()
        auth_failed.auth_error = smtplib.SMTPAuthenticationError(535, b"private")
        result = self.executor(auth_failed).send(ACCOUNT, self.snapshot(), "<message@kolconnect.local>")
        self.assertEqual(("failed", "auth"), (result.outcome, result.stage))

    def test_all_recipients_rejected_never_enters_data(self):
        fake = FakeSMTP()
        fake.rcpt_results = {"one@example.com": (550, b"no"), "two@example.com": (550, b"no")}
        result = self.executor(fake).send(ACCOUNT, self.snapshot(), "<message@kolconnect.local>")
        self.assertEqual("failed", result.outcome)
        self.assertNotIn("data", fake.calls)

    def test_secret_storage_is_resolved_only_at_authentication_boundary(self):
        fake = FakeSMTP()
        resolver = mock.Mock(return_value="native-secret")
        executor = SMTPExecutor(smtp_ssl_factory=lambda *_a, **_k: fake, secret_resolver=resolver)
        result = executor.send(ACCOUNT, self.snapshot(), "<message@kolconnect.local>")
        self.assertEqual("accepted", result.outcome)
        resolver.assert_called_once_with(ACCOUNT["password"])
        self.assertIn(("login", "sender@example.com", "native-secret"), fake.calls)
        self.assertNotIn(b"native-secret", fake.message)

    def test_gmail_app_password_normalization_matches_connection_validation(self):
        gmail = {
            **ACCOUNT,
            "provider": "gmail",
            "email": "sender@gmail.com",
            "username": "sender@gmail.com",
            "smtp_host": "smtp.gmail.com",
        }
        snapshot = {**self.snapshot(), "from_address": "sender@gmail.com"}
        spaced = FakeSMTP()
        stored_secret = "abcd efgh ijkl mnop"
        resolver = mock.Mock(return_value=stored_secret)
        SMTPExecutor(
            smtp_ssl_factory=lambda *_a, **_k: spaced,
            secret_resolver=resolver,
        ).send(gmail, snapshot, "<gmail@kolconnect.local>")
        self.assertIn(("login", "sender@gmail.com", "abcdefghijklmnop"), spaced.calls)
        resolver.assert_called_once_with(gmail["password"])
        self.assertEqual("abcd efgh ijkl mnop", stored_secret)

        compact = FakeSMTP()
        SMTPExecutor(
            smtp_ssl_factory=lambda *_a, **_k: compact,
            secret_resolver=lambda _value: "abcdefghijklmnop",
        ).send(gmail, snapshot, "<gmail-compact@kolconnect.local>")
        self.assertIn(("login", "sender@gmail.com", "abcdefghijklmnop"), compact.calls)

    def test_non_gmail_password_spaces_are_preserved(self):
        fake = FakeSMTP()
        SMTPExecutor(
            smtp_ssl_factory=lambda *_a, **_k: fake,
            secret_resolver=lambda _value: "legitimate password with spaces",
        ).send(ACCOUNT, self.snapshot(), "<custom@kolconnect.local>")
        self.assertIn(("login", "sender@example.com", "legitimate password with spaces"), fake.calls)


class MailSendSecurityTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = MailSendSessionStore(now=self.clock, ttl_seconds=30)
        self.port = 8765
        self.same_origin = {
            "Origin": "http://127.0.0.1:8765", "Referer": "http://127.0.0.1:8765/",
            "Sec-Fetch-Site": "same-origin",
        }

    def test_bootstrap_and_mutation_require_same_origin_cookie_and_csrf(self):
        issued = self.store.issue(self.same_origin, self.port)
        headers = {**self.same_origin, "Cookie": f"{COOKIE_NAME}={issued['session_id']}",
                   CSRF_HEADER: issued["csrf_token"]}
        self.assertEqual(issued["session_id"], self.store.validate(headers, self.port))
        for changed in (
            {**headers, "Origin": "https://evil.example"},
            {**headers, CSRF_HEADER: "wrong"},
            {key: value for key, value in headers.items() if key != "Cookie"},
        ):
            with self.subTest(headers=changed), self.assertRaises(MailSendError):
                self.store.validate(changed, self.port)
        with self.assertRaises(MailSendError):
            self.store.issue({"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}, self.port)

    def test_session_expires_fail_closed(self):
        issued = self.store.issue(self.same_origin, self.port)
        self.clock.value += timedelta(seconds=31)
        with self.assertRaisesRegex(MailSendError, "失效"):
            self.store.validate({**self.same_origin, "Cookie": f"{COOKIE_NAME}={issued['session_id']}",
                                 CSRF_HEADER: issued["csrf_token"]}, self.port)


class Handler:
    def __init__(self, headers, port=8765):
        self.headers = headers
        self.server = type("Server", (), {"server_port": port})()
        self.payload = None
        self.status = None
        self.response_headers = {}

    def _json(self, payload, status=200):
        self.payload, self.status = payload, status

    def _json_with_headers(self, payload, headers, status=200):
        self.payload, self.status, self.response_headers = payload, status, headers

    def _api_error(self, code, message, status=400, **_kwargs):
        self.payload, self.status = {"ok": False, "error": {"code": code, "message": message}}, status


class MailSendHandlerTests(unittest.TestCase):
    @staticmethod
    def secure_context():
        sessions = MailSendSessionStore(now=lambda: NOW)
        issued = sessions.issue({"Referer": "http://127.0.0.1:8765/", "Sec-Fetch-Site": "same-origin"}, 8765)
        headers = {
            "Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin",
            "Cookie": f"{COOKIE_NAME}={issued['session_id']}", CSRF_HEADER: issued["csrf_token"],
        }
        return sessions, headers

    def test_security_bootstrap_and_send_route_do_not_expose_token_hash(self):
        sessions = MailSendSessionStore(now=lambda: NOW)
        headers = {"Referer": "http://127.0.0.1:8765/", "Sec-Fetch-Site": "same-origin"}
        handler = Handler(headers)
        service = mock.Mock()
        context = {"services": {"mail_send_sessions": sessions, "mail_send": service}}
        handled = mail_send_handler.handle(handler, {
            "method": "GET", "path": "/api/mail/send-security/session", "get_payload": lambda: {},
        }, context)
        self.assertTrue(handled)
        self.assertIn("Set-Cookie", handler.response_headers)
        csrf = handler.payload["csrf_token"]
        cookie = handler.response_headers["Set-Cookie"].split(";", 1)[0]
        secure_headers = {"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin",
                          "Cookie": cookie, CSRF_HEADER: csrf}
        handler = Handler(secure_headers)
        service.send.return_value = {"attempt_id": "attempt", "outcome": "accepted"}
        mail_send_handler.handle(handler, {
            "method": "POST", "path": "/api/mail/send", "get_payload": lambda: {"safe": True},
        }, context)
        self.assertEqual(200, handler.status)
        self.assertNotIn("token_hash", str(handler.payload))
        service.send.assert_called_once()

    def test_cross_site_send_is_rejected_before_service_call(self):
        sessions = MailSendSessionStore(now=lambda: NOW)
        handler = Handler({"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
        service = mock.Mock()
        mail_send_handler.handle(handler, {
            "method": "POST", "path": "/api/mail/send", "get_payload": lambda: {},
        }, {"services": {"mail_send_sessions": sessions, "mail_send": service}})
        self.assertEqual(403, handler.status)
        service.send.assert_not_called()

    def test_all_backend_routes_are_explicit_and_get_never_sends(self):
        sessions, headers = self.secure_context()
        service = mock.Mock()
        service.create_draft.return_value = {"draft_id": "draft"}
        service.update_draft.return_value = {"draft_id": "draft", "version": 2}
        service.create_preview.return_value = {"preview_id": "preview"}
        service.authorize_preview.return_value = {"confirmation_token": "one-time"}
        service.delete_draft.return_value = {"draft_id": "draft", "deleted": True}
        service.get_attempt.return_value = {"attempt_id": "attempt", "outcome": "accepted"}
        context = {"services": {"mail_send_sessions": sessions, "mail_send": service}}
        requests = (
            ("POST", "/api/mail/drafts", {"field": "value"}),
            ("PUT", "/api/mail/drafts/draft", {"version": 1}),
            ("POST", "/api/mail/drafts/draft/preview", {}),
            ("POST", "/api/mail/drafts/draft/preview", {"confirm": True, "preview_id": "preview",
                                                         "authorization_source": "human_direct"}),
            ("DELETE", "/api/mail/drafts/draft", {"version": 2}),
            ("GET", "/api/mail/send-attempts/attempt", {}),
        )
        for method, path, payload in requests:
            with self.subTest(method=method, path=path, payload=payload):
                handler = Handler(headers)
                self.assertTrue(mail_send_handler.handle(handler, {
                    "method": method, "path": path, "get_payload": lambda payload=payload: payload,
                }, context))
                self.assertLess(handler.status, 400)
        service.send.assert_not_called()
        service.get_attempt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
