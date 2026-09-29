from __future__ import annotations

import importlib
import json
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

from runtime_paths import atomic_write_json, json_backup_path  # noqa: E402
from services.mail_secret_storage import (  # noqa: E402
    MailSecretProtectionError,
    is_protected_mail_secret,
    protect_mail_secret,
    protect_mail_state_for_storage,
    unprotect_mail_secret,
)
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _ImapClient:
    password = ""

    def __init__(self, *_args, **_kwargs):
        pass

    def login(self, _username, password):
        type(self).password = password

    def logout(self):
        pass


class _SmtpClient(_ImapClient):
    def ehlo(self):
        pass

    def has_extn(self, _name):
        return False

    def quit(self):
        pass


class MailSecretStorageTests(unittest.TestCase):
    def test_dpapi_value_is_opaque_and_round_trips_for_current_user(self):
        protected = protect_mail_secret("mail-app-password")
        self.assertTrue(is_protected_mail_secret(protected))
        self.assertNotIn("mail-app-password", json.dumps(protected))
        self.assertEqual("mail-app-password", unprotect_mail_secret(protected))

    def test_non_windows_does_not_fall_back_to_plaintext(self):
        with patch("services.mail_secret_storage.sys.platform", "linux"):
            with self.assertRaises(MailSecretProtectionError):
                protect_mail_secret("mail-app-password")
            with self.assertRaises(MailSecretProtectionError):
                unprotect_mail_secret({"format": "dpapi-v1", "data": "AA=="})

    def test_persisted_sync_rejects_plaintext_but_transient_connection_test_can_use_it(self):
        with self.assertRaises(MailSecretProtectionError):
            unprotect_mail_secret("legacy-secret")
        self.assertEqual(
            "newly-entered-secret",
            unprotect_mail_secret("newly-entered-secret", allow_transient_plaintext=True),
        )

    def test_protected_write_masks_client_preserves_mask_and_secures_backup(self):
        with test_runtime_sandbox("gate_c_storage") as runtime:
            server = importlib.import_module("server")
            original_path = server.STATE_FILE
            try:
                server.STATE_FILE = runtime.settings_path
                legacy = {
                    "mail": {"accounts": [{"name": "Primary", "email": "mail@example.com", "username": "mail@example.com", "password": "mail-app-password"}]}
                }
                atomic_write_json(runtime.settings_path, legacy)
                state = server.load_state()
                stored = json.loads(runtime.settings_path.read_text(encoding="utf-8"))
                backup = json.loads(json_backup_path(runtime.settings_path).read_text(encoding="utf-8"))
                for saved in (stored, backup):
                    self.assertNotIn("mail-app-password", json.dumps(saved))
                    self.assertTrue(is_protected_mail_secret(saved["mail"]["accounts"][0]["password"]))

                client_state = server.state_for_client(state)
                self.assertEqual("********", client_state["mail"]["accounts"][0]["password"])
                merged = server.merge_masked_mail_passwords(client_state["mail"], state["mail"])
                self.assertEqual(
                    state["mail"]["accounts"][0]["password"],
                    merged["accounts"][0]["password"],
                )

                state["mail"] = server.normalize_mail_state(
                    {"accounts": [{**merged["accounts"][0], "password": "replacement-app-password"}]}
                )
                server.save_state(state)
                replaced = json.loads(runtime.settings_path.read_text(encoding="utf-8"))
                self.assertNotIn("replacement-app-password", json.dumps(replaced))
                self.assertEqual(
                    "replacement-app-password",
                    unprotect_mail_secret(replaced["mail"]["accounts"][0]["password"]),
                )
            finally:
                server.STATE_FILE = original_path

    def test_failed_legacy_migration_leaves_original_file_untouched_without_secret_logging(self):
        with test_runtime_sandbox("gate_c_failure") as runtime:
            server = importlib.import_module("server")
            original_path = server.STATE_FILE
            original = {"mail": {"accounts": [{"username": "mail@example.com", "password": "legacy-secret"}]}}
            try:
                server.STATE_FILE = runtime.settings_path
                atomic_write_json(runtime.settings_path, original)
                with patch.object(server, "protect_mail_state_for_storage", side_effect=MailSecretProtectionError("safe")), patch.object(server, "log_error") as log_error:
                    state = server.load_state()
                self.assertEqual("legacy-secret", state["mail"]["accounts"][0]["password"])
                self.assertEqual(original, json.loads(runtime.settings_path.read_text(encoding="utf-8")))
                self.assertNotIn("legacy-secret", " ".join(map(str, log_error.call_args.args)))
            finally:
                server.STATE_FILE = original_path

    def test_backup_recovery_migrates_the_recovered_legacy_secret_too(self):
        with test_runtime_sandbox("gate_c_backup_recovery") as runtime:
            server = importlib.import_module("server")
            original_path = server.STATE_FILE
            legacy = {"mail": {"accounts": [{"username": "mail@example.com", "password": "legacy-secret"}]}}
            try:
                server.STATE_FILE = runtime.settings_path
                runtime.settings_path.write_text("{not-json", encoding="utf-8")
                json_backup_path(runtime.settings_path).write_text(json.dumps(legacy), encoding="utf-8")
                server.load_state()
                for path in (runtime.settings_path, json_backup_path(runtime.settings_path)):
                    saved = json.loads(path.read_text(encoding="utf-8"))
                    self.assertNotIn("legacy-secret", json.dumps(saved))
                    self.assertTrue(is_protected_mail_secret(saved["mail"]["accounts"][0]["password"]))
            finally:
                server.STATE_FILE = original_path

    def test_imap_and_smtp_receive_plaintext_only_at_login_boundary(self):
        with test_runtime_sandbox("gate_c_login"):
            server = importlib.import_module("server")
            account = {
                "imap_host": "imap.example.test", "imap_port": "993",
                "smtp_host": "smtp.example.test", "smtp_port": "465",
                "username": "mail@example.com", "password": protect_mail_secret("mail-app-password"),
            }
            with patch.object(server.imaplib, "IMAP4_SSL", _ImapClient), patch.object(server.smtplib, "SMTP_SSL", _SmtpClient):
                server.test_imap_login(account)
                server.test_smtp_login(account)
            self.assertEqual("mail-app-password", _ImapClient.password)
            self.assertEqual("mail-app-password", _SmtpClient.password)

    def test_protect_mail_state_is_idempotent(self):
        state = {"mail": {"accounts": [{"password": "mail-app-password"}]}}
        protected, changed = protect_mail_state_for_storage(state)
        again, changed_again = protect_mail_state_for_storage(protected)
        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertEqual(protected, again)


if __name__ == "__main__":
    unittest.main()
