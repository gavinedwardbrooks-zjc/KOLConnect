from __future__ import annotations

import imaplib
import json
import ssl
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT / "tests"))

from services.mail_auth_service import classify_imap_error, classify_smtp_error  # noqa: E402
from runtime_paths import atomic_write_json  # noqa: E402
from test_support.runtime_sandbox import test_artifact_directory  # noqa: E402


class M74OutlookAuthTests(unittest.TestCase):
    def test_basic_auth_disabled_is_specific_and_sanitized(self):
        exc = classify_imap_error(imaplib.IMAP4.error(b"Basic authentication is disabled."))
        self.assertEqual("IMAP_BASIC_AUTH_REJECTED", exc.code)
        self.assertIn("配置已保存", str(exc))
        self.assertNotIn("b'", str(exc))

    def test_invalid_credentials_remain_distinct(self):
        exc = classify_imap_error(imaplib.IMAP4.error(b"LOGIN failed"))
        self.assertEqual("MAIL_CREDENTIAL_REJECTED", exc.code)

    def test_timeout_and_network_are_classified(self):
        self.assertEqual("MAIL_AUTH_TIMEOUT", classify_imap_error(TimeoutError()).code)
        self.assertEqual("MAIL_NETWORK_ERROR", classify_imap_error(ConnectionError()).code)

    def test_gmail_auth_rejection_is_safe_and_provider_specific(self):
        account = {"imap_host": "imap.gmail.com"}
        exc = classify_imap_error(imaplib.IMAP4.error(b"AUTHENTICATIONFAILED"), account=account)
        self.assertEqual("GMAIL_AUTH_REJECTED", exc.code)
        self.assertIn("应用专用密码", str(exc))
        self.assertIn("OAuth2", str(exc))
        self.assertNotIn("AUTHENTICATIONFAILED", str(exc))

    def test_gmail_app_password_and_web_login_signals_are_narrowly_classified(self):
        account = {"imap_host": "imap.gmail.com"}
        app_password = classify_imap_error(
            imaplib.IMAP4.error(b"Application-specific password required"), account=account
        )
        web_login = classify_imap_error(
            imaplib.IMAP4.error(b"Web login required"), account=account
        )
        self.assertEqual("GMAIL_APP_PASSWORD_MAY_BE_REQUIRED", app_password.code)
        self.assertEqual("GMAIL_WEB_LOGIN_REQUIRED", web_login.code)

    def test_non_gmail_and_transport_failures_do_not_make_gmail_claims(self):
        generic = classify_imap_error(
            imaplib.IMAP4.error(b"LOGIN failed"), account={"imap_host": "imap.example.test"}
        )
        self.assertEqual("MAIL_CREDENTIAL_REJECTED", generic.code)
        self.assertNotIn("Gmail", str(generic))
        self.assertEqual(
            "MAIL_TLS_FAILED",
            classify_imap_error(ssl.SSLError("certificate verify failed")).code,
        )
        self.assertEqual(
            "GMAIL_AUTH_REJECTED",
            classify_smtp_error(
                RuntimeError("AUTHENTICATIONFAILED"), account={"smtp_host": "smtp.gmail.com"}
            ).code,
        )

    def test_synthetic_macos_settings_path_handles_spaces_and_unicode(self):
        import runtime_paths

        home = Path("/Users/测试 User")
        with patch.object(runtime_paths.sys, "platform", "darwin"), patch.object(runtime_paths.Path, "home", return_value=home), patch.object(runtime_paths.Path, "mkdir"):
            self.assertEqual(
                home / "Library" / "Application Support" / "KOLConnect",
                runtime_paths.get_app_data_dir(),
            )

    def test_synthetic_macos_style_path_save_reload_update_restart_and_delete(self):
        with tempfile.TemporaryDirectory(
            dir=test_artifact_directory("temporary")
        ) as root, patch("runtime_paths.shared_storage_lock", return_value=nullcontext()):
            settings_path = Path(root) / "Library" / "Application Support" / "KOLConnect 用户" / "settings.json"
            atomic_write_json(settings_path, {"mail": {"accounts": [{"username": "user@example.com"}]}})
            self.assertEqual("user@example.com", json.loads(settings_path.read_text(encoding="utf-8"))["mail"]["accounts"][0]["username"])
            atomic_write_json(settings_path, {"mail": {"accounts": [{"username": "updated@example.com"}]}})
            restarted_path = Path(str(settings_path))
            self.assertEqual("updated@example.com", json.loads(restarted_path.read_text(encoding="utf-8"))["mail"]["accounts"][0]["username"])
            settings_path.unlink()
            self.assertFalse(settings_path.exists())

    def test_saved_configuration_and_authentication_are_independent_states(self):
        stored = {"mail": {"accounts": [{"username": "user@example.com", "password": "protected-by-settings-layer"}]}}
        encoded = json.dumps(stored)
        self.assertEqual(
            "protected-by-settings-layer",
            json.loads(encoded)["mail"]["accounts"][0]["password"],
        )
        auth = classify_imap_error(imaplib.IMAP4.error(b"Basic authentication is disabled."))
        self.assertEqual("IMAP_BASIC_AUTH_REJECTED", auth.code)


if __name__ == "__main__":
    unittest.main()
