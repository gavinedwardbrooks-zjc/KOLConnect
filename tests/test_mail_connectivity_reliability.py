from __future__ import annotations

import socket
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import server  # noqa: E402
from http_handlers import settings_handler  # noqa: E402
from services.mail_auth_service import MailAuthenticationError  # noqa: E402
from services.mail_connection_service import (  # noqa: E402
    mail_tls_mode,
    normalize_gmail_app_password,
    open_imap_connection,
    test_imap_connection as check_imap_connection,
    test_smtp_connection as check_smtp_connection,
    validate_mail_account,
)


class _Imap:
    password = None
    starttls_called = False

    def __init__(self, *_args, **_kwargs):
        pass

    def starttls(self, **_kwargs):
        type(self).starttls_called = True

    def login(self, _username, password):
        type(self).password = password

    def select(self, _folder, readonly=True):
        return "OK", [b"0"]

    def logout(self):
        pass


class _Smtp:
    password = None
    starttls_called = False
    supports_starttls = True

    def __init__(self, *_args, **_kwargs):
        pass

    def ehlo(self):
        pass

    def has_extn(self, name):
        return name == "starttls" and type(self).supports_starttls

    def starttls(self, **_kwargs):
        type(self).starttls_called = True

    def login(self, _username, password):
        type(self).password = password

    def quit(self):
        pass


class _AuthFailSmtp(_Smtp):
    def login(self, _username, _password):
        raise RuntimeError("provider rejected synthetic credential")


class MailConnectivityReliabilityTests(unittest.TestCase):
    def setUp(self):
        _Imap.password = None
        _Imap.starttls_called = False
        _Smtp.password = None
        _Smtp.starttls_called = False
        _Smtp.supports_starttls = True
        self.gmail = {
            "provider": "gmail",
            "email": "owner@gmail.com",
            "username": "owner@gmail.com",
            "password": "abcd efgh ijkl mnop",
            "imap_host": "imap.gmail.com",
            "imap_port": "993",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
        }

    def test_provider_presets_cover_supported_products_and_aliases(self):
        expected = {
            "gmail": ("imap.gmail.com", "993", "smtp.gmail.com", "587"),
            "qq": ("imap.qq.com", "993", "smtp.qq.com", "465"),
            "netease": ("imap.163.com", "993", "smtp.163.com", "465"),
            "netease126": ("imap.126.com", "993", "smtp.126.com", "465"),
            "aliyun": ("imap.qiye.aliyun.com", "993", "smtp.qiye.aliyun.com", "465"),
        }
        for provider, values in expected.items():
            preset = server.get_mail_provider_preset(provider)
            self.assertEqual(values, tuple(preset[key] for key in ("imap_host", "imap_port", "smtp_host", "smtp_port")))
        self.assertEqual(server.get_mail_provider_preset("163"), server.get_mail_provider_preset("netease"))
        self.assertEqual(server.get_mail_provider_preset("126"), server.get_mail_provider_preset("netease126"))

    def test_gmail_spaced_app_password_is_normalized_only_when_unambiguous(self):
        self.assertEqual("abcdefghijklmnop", normalize_gmail_app_password(self.gmail, "abcd efgh ijkl mnop"))
        self.assertEqual("short value", normalize_gmail_app_password(self.gmail, "short value"))
        non_gmail = {**self.gmail, "provider": "custom", "imap_host": "imap.example.test"}
        self.assertEqual("abcd efgh ijkl mnop", normalize_gmail_app_password(non_gmail, "abcd efgh ijkl mnop"))
        result = check_imap_connection(self.gmail, imap_factory=_Imap)
        self.assertEqual("pass", result["status"])
        self.assertEqual("abcdefghijklmnop", _Imap.password)

    def test_gmail_requires_full_email_username(self):
        result = check_imap_connection({**self.gmail, "username": "owner"}, imap_factory=_Imap)
        self.assertEqual("fail", result["status"])
        self.assertEqual("GMAIL_USERNAME_MUST_BE_FULL_EMAIL", result["code"])

    def test_tls_modes_are_deterministic(self):
        self.assertEqual("implicit_tls", mail_tls_mode("imap", 993))
        self.assertEqual("implicit_tls", mail_tls_mode("smtp", 465))
        self.assertEqual("starttls", mail_tls_mode("smtp", 587))
        self.assertEqual("starttls", mail_tls_mode("imap", 143))

        imap = check_imap_connection({**self.gmail, "provider": "custom", "imap_port": "143"}, imap_factory=_Imap)
        self.assertEqual("pass", imap["status"])
        self.assertTrue(_Imap.starttls_called)
        smtp = check_smtp_connection(self.gmail, smtp_factory=_Smtp)
        self.assertEqual("pass", smtp["status"])
        self.assertTrue(_Smtp.starttls_called)

    def test_imap_success_smtp_auth_failure_remains_usable(self):
        result = validate_mail_account(
            self.gmail, imap_factory=_Imap, smtp_factory=_AuthFailSmtp
        )
        self.assertTrue(result["usable"])
        self.assertEqual("pass", result["imap"]["status"])
        self.assertEqual("fail", result["smtp"]["status"])
        self.assertEqual("auth", result["smtp"]["stage"])
        self.assertIn("不影响邮件同步", result["warning"])

    def test_smtp_starttls_is_required_on_587(self):
        _Smtp.supports_starttls = False
        result = check_smtp_connection(self.gmail, smtp_factory=_Smtp)
        self.assertEqual("fail", result["status"])
        self.assertEqual("MAIL_SMTP_TLS_FAILED", result["code"])

    def test_stage_specific_timeout_dns_auth_and_aliyun_typo(self):
        def timeout_factory(*_args, **_kwargs):
            raise TimeoutError("synthetic timeout")

        timeout = check_imap_connection(self.gmail, imap_factory=timeout_factory)
        self.assertEqual("MAIL_IMAP_CONNECT_TIMEOUT", timeout["code"])
        self.assertEqual("connect", timeout["stage"])

        def dns_factory(*_args, **_kwargs):
            raise socket.gaierror("synthetic dns")

        dns = check_imap_connection(self.gmail, imap_factory=dns_factory)
        self.assertEqual("MAIL_DNS_FAILED", dns["code"])
        typo = check_imap_connection(
            {**self.gmail, "provider": "aliyun", "imap_host": "Map.qiye.aliyun.com"},
            imap_factory=_Imap,
        )
        self.assertEqual("MAIL_IMAP_HOST_TYPO", typo["code"])
        self.assertIn("imap.qiye.aliyun.com", typo["message"])

        class _AuthTimeoutImap(_Imap):
            def login(self, _username, _password):
                raise TimeoutError("synthetic auth timeout")

        auth_timeout = check_imap_connection(self.gmail, imap_factory=_AuthTimeoutImap)
        self.assertEqual("MAIL_IMAP_AUTH_TIMEOUT", auth_timeout["code"])
        self.assertEqual("auth", auth_timeout["stage"])

    def test_actual_sync_and_validation_share_imap_connection_core(self):
        from services import mail_inbox_facts

        class _Connection:
            def execute(self, *_args, **_kwargs):
                return self

            def fetchone(self):
                return {
                    "first_sync_completed_at": None,
                    "uidvalidity": None,
                    "high_water_uid": 0,
                    "history_coverage": "none",
                }

        class _Factory:
            def write_transaction(self):
                return nullcontext(_Connection())

            def read_connection(self):
                return nullcontext(_Connection())

        with patch.object(mail_inbox_facts, "open_imap_connection") as shared:
            shared.side_effect = MailAuthenticationError(
                "MAIL_IMAP_CONNECT_FAILED", "safe", protocol="imap", stage="connect"
            )
            with self.assertRaises(MailAuthenticationError):
                mail_inbox_facts.sync_inbox(self.gmail, _Factory())
        shared.assert_called_once()

    def test_http_result_keeps_smtp_failure_informational_and_logs_safely(self):
        result = {
            "usable": True,
            "imap": {"status": "pass", "host": "imap.gmail.com", "port": 993, "stage": "folder"},
            "smtp": {"status": "fail", "host": "smtp.gmail.com", "port": 587, "stage": "auth"},
            "warning": "safe warning",
            "elapsed_ms": 12,
        }

        class _Handler:
            def _ok(self, **payload):
                self.payload = {"ok": True, **payload}

        events = []
        handler = _Handler()
        context = {
            "state": {"get": lambda: {"mail": {"accounts": []}}},
            "services": {
                "merge_masked_mail_passwords": lambda payload, _existing: payload,
                "normalize_mail_account": lambda account: account,
                "validate_mail_account": lambda _account: result,
            },
            "modules": {},
            "logging": {"event": lambda category, message: events.append((category, message))},
            "request": {"trace_id": "trace_mail_test"},
        }
        request = {
            "method": "POST",
            "path": "/api/mail/test",
            "query": {},
            "get_payload": lambda: {"account": self.gmail},
        }
        self.assertTrue(settings_handler.handle(handler, request, context))
        self.assertTrue(handler.payload["usable"])
        self.assertEqual("fail", handler.payload["smtp"]["status"])
        logged = str(events)
        self.assertIn("smtp_stage=auth", logged)
        self.assertIn("trace_id=trace_mail_test", logged)
        self.assertNotIn("abcd efgh", logged)


if __name__ == "__main__":
    unittest.main()
