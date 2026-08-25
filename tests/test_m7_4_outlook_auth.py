from __future__ import annotations

import imaplib
import json
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

from services.mail_auth_service import classify_imap_error  # noqa: E402
from runtime_paths import atomic_write_json  # noqa: E402


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

    def test_synthetic_macos_settings_path_handles_spaces_and_unicode(self):
        import runtime_paths

        home = Path("/Users/测试 User")
        with patch.object(runtime_paths.sys, "platform", "darwin"), patch.object(runtime_paths.Path, "home", return_value=home), patch.object(runtime_paths.Path, "mkdir"):
            self.assertEqual(
                home / "Library" / "Application Support" / "KOLConnect",
                runtime_paths.get_app_data_dir(),
            )

    def test_synthetic_macos_style_path_save_reload_update_restart_and_delete(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as root, patch("runtime_paths.shared_storage_lock", return_value=nullcontext()):
            settings_path = Path(root) / "Library" / "Application Support" / "KOLConnect 用户" / "settings.json"
            atomic_write_json(settings_path, {"mail": {"accounts": [{"username": "user@example.com"}]}})
            self.assertEqual("user@example.com", json.loads(settings_path.read_text(encoding="utf-8"))["mail"]["accounts"][0]["username"])
            atomic_write_json(settings_path, {"mail": {"accounts": [{"username": "updated@example.com"}]}})
            restarted_path = Path(str(settings_path))
            self.assertEqual("updated@example.com", json.loads(restarted_path.read_text(encoding="utf-8"))["mail"]["accounts"][0]["username"])
            settings_path.unlink()
            self.assertFalse(settings_path.exists())

    def test_saved_configuration_and_authentication_are_independent_states(self):
        stored = {"mail": {"accounts": [{"username": "user@example.com", "password": "saved-secret"}]}}
        encoded = json.dumps(stored)
        self.assertIn("saved-secret", json.loads(encoded)["mail"]["accounts"][0]["password"])
        auth = classify_imap_error(imaplib.IMAP4.error(b"Basic authentication is disabled."))
        self.assertEqual("IMAP_BASIC_AUTH_REJECTED", auth.code)


if __name__ == "__main__":
    unittest.main()
