from __future__ import annotations

import imaplib
import json
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

import app_logging  # noqa: E402
import mail_sync  # noqa: E402
from http_handlers import settings_handler  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


SENSITIVE_PROVIDER_TEXT = (
    "AUTHENTICATIONFAILED user=test@example.com "
    "secret=SYNTHETIC-SECRET provider-detail=XYZ"
)


class _Handler:
    def __init__(self) -> None:
        self.payload: dict | None = None
        self.status: int | None = None

    def _ok(self, **payload) -> None:
        self.payload = {"ok": True, **payload}
        self.status = 200

    def _error(self, message: str, status: int = 400) -> None:
        self.payload = {"ok": False, "error": message}
        self.status = status


class MailSyncProviderErrorRedactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = test_runtime_sandbox("gate_c1_mail_sync_redaction")
        self.runtime = self.sandbox.__enter__()
        self.factory = SQLiteConnectionFactory(self.runtime.root / "mail.db")
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection)
        self.account = {
            "name": "Mailbox",
            "email": "owner@example.com",
            "username": "owner@example.com",
            "password": {"format": "test-fixture", "data": "opaque"},
            "imap_host": "imap.example.test",
            "imap_port": 993,
            "enabled": True,
        }
        self.cache_path = self.runtime.root / "mail_messages.json"
        self._secret_unprotectors = [
            patch("services.mail_inbox_facts.unprotect_mail_secret", return_value="fixture-password"),
            patch("mail_sync.unprotect_mail_secret", return_value="fixture-password"),
        ]
        for patcher in self._secret_unprotectors:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in self._secret_unprotectors:
            patcher.stop()
        self.sandbox.__exit__(None, None, None)

    def _inbox_failure(self, exc: BaseException) -> tuple[dict, str]:
        with patch.object(mail_sync, "MAIL_MESSAGES_FILE", self.cache_path), patch.object(
            mail_sync, "sync_inbox", side_effect=exc
        ), patch.object(app_logging, "get_logger") as get_logger:
            result = mail_sync.sync_enabled_mail_accounts(
                [self.account], {"connection_factory": self.factory}
            )
        log_args = get_logger.return_value.error.call_args
        return result, str((log_args.args, log_args.kwargs))

    def test_raw_provider_failure_is_redacted_from_result_cache_api_and_logs(self):
        result, logged = self._inbox_failure(imaplib.IMAP4.error(SENSITIVE_PROVIDER_TEXT))
        serialized_result = json.dumps(result)
        cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        serialized_cache = json.dumps(cache)

        self.assertEqual("MAIL_CREDENTIAL_REJECTED", result["errors"][0]["code"])
        for value in (serialized_result, serialized_cache, logged):
            self.assertNotIn(SENSITIVE_PROVIDER_TEXT, value)
            self.assertNotIn("SYNTHETIC-SECRET", value)
        last_result = cache["accounts"][mail_sync.build_account_key(self.account)]["last_result"]
        self.assertEqual(["MAIL_CREDENTIAL_REJECTED"], last_result["error_codes"])

        handler = _Handler()
        context = {
            "state": {"get": lambda: {"mail": {"accounts": [self.account]}}},
            "services": {"get_mail_connection_factory": lambda: self.factory},
            "modules": {"mail_sync": mail_sync},
        }
        with patch.object(mail_sync, "MAIL_MESSAGES_FILE", self.cache_path), patch.object(
            mail_sync, "sync_inbox", side_effect=imaplib.IMAP4.error(SENSITIVE_PROVIDER_TEXT)
        ), patch.object(app_logging, "get_logger"):
            self.assertTrue(settings_handler.handle(handler, {
                "method": "POST", "path": "/api/mail/inbox/sync", "query": {}, "get_payload": lambda: {},
            }, context))
        api_payload = json.dumps(handler.payload)
        self.assertEqual(200, handler.status)
        self.assertNotIn(SENSITIVE_PROVIDER_TEXT, api_payload)
        self.assertNotIn("SYNTHETIC-SECRET", api_payload)

    def test_unknown_provider_exception_fails_closed_with_generic_sync_error(self):
        result, logged = self._inbox_failure(RuntimeError(SENSITIVE_PROVIDER_TEXT))
        [error] = result["errors"]
        self.assertEqual("MAIL_SYNC_FAILED", error["code"])
        self.assertEqual(mail_sync.MAIL_SYNC_FAILED_MESSAGE, error["error"])
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result))
        self.assertNotIn("SYNTHETIC-SECRET", logged)

    def test_gmail_and_non_gmail_auth_errors_remain_safely_distinct(self):
        gmail = {**self.account, "imap_host": "imap.gmail.com"}
        self.account = gmail
        gmail_result, _logged = self._inbox_failure(imaplib.IMAP4.error(SENSITIVE_PROVIDER_TEXT))
        self.assertEqual("GMAIL_AUTH_REJECTED", gmail_result["errors"][0]["code"])
        self.assertIn("应用专用密码", gmail_result["errors"][0]["error"])
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(gmail_result))

        self.account = {**gmail, "imap_host": "imap.example.test"}
        generic_result, _logged = self._inbox_failure(imaplib.IMAP4.error(SENSITIVE_PROVIDER_TEXT))
        self.assertEqual("MAIL_CREDENTIAL_REJECTED", generic_result["errors"][0]["code"])
        self.assertNotIn("Gmail", generic_result["errors"][0]["error"])

    def test_connection_and_tls_errors_are_safely_classified(self):
        timeout, _logged = self._inbox_failure(TimeoutError(SENSITIVE_PROVIDER_TEXT))
        self.assertEqual("MAIL_AUTH_TIMEOUT", timeout["errors"][0]["code"])

        connection, _logged = self._inbox_failure(ConnectionRefusedError(SENSITIVE_PROVIDER_TEXT))
        self.assertEqual("MAIL_NETWORK_ERROR", connection["errors"][0]["code"])

        tls, _logged = self._inbox_failure(ssl.SSLError(SENSITIVE_PROVIDER_TEXT))
        self.assertEqual("MAIL_TLS_FAILED", tls["errors"][0]["code"])
        for result in (timeout, connection, tls):
            self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result))

    def test_sent_sync_response_is_redacted(self):
        with patch.object(mail_sync, "sync_sent", side_effect=RuntimeError(SENSITIVE_PROVIDER_TEXT)), patch.object(
            app_logging, "get_logger"
        ) as get_logger:
            result = mail_sync.sync_enabled_sent_mail_accounts(
                [self.account], {"connection_factory": self.factory}
            )
        self.assertEqual("MAIL_SYNC_FAILED", result["errors"][0]["code"])
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result))
        self.assertNotIn("SYNTHETIC-SECRET", str(get_logger.return_value.error.call_args))

        handler = _Handler()
        context = {
            "state": {"get": lambda: {"mail": {"accounts": [self.account]}}},
            "services": {"get_mail_connection_factory": lambda: self.factory},
            "modules": {"mail_sync": mail_sync},
        }
        with patch.object(mail_sync, "sync_sent", side_effect=RuntimeError(SENSITIVE_PROVIDER_TEXT)), patch.object(
            app_logging, "get_logger"
        ):
            self.assertTrue(settings_handler.handle(handler, {
                "method": "POST", "path": "/api/mail/sent/sync", "query": {}, "get_payload": lambda: {},
            }, context))
        self.assertEqual(200, handler.status)
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(handler.payload))


if __name__ == "__main__":
    unittest.main()
