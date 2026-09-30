from __future__ import annotations

import sys
import inspect
import subprocess
import unittest
from unittest.mock import patch
from uuid import uuid4

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services import mail_secret_storage as storage
from runtime_paths import atomic_write_json, json_backup_path
from test_support.runtime_sandbox import test_runtime_sandbox


ACCOUNT = {
    "name": "Display name is not identity",
    "email": "owner@example.com",
    "username": "owner@example.com",
    "imap_host": "imap.example.test",
    "imap_port": "993",
}


class _FakeKeychain:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.delete_failures: set[tuple[str, str]] = set()
        self.fail_all_deletes = False
        self.interaction_policies: list[bool] = []

    def store(self, service: str, account: str, secret: str, *, allow_interaction: bool = True) -> None:
        self.interaction_policies.append(allow_interaction)
        self.values[(service, account)] = secret

    def read(self, service: str, account: str, *, allow_interaction: bool = True) -> str:
        self.interaction_policies.append(allow_interaction)
        try:
            return self.values[(service, account)]
        except KeyError as exc:
            raise storage._KeychainBackendError("read", -25300) from exc

    def delete(self, service: str, account: str, *, allow_interaction: bool = True) -> None:
        self.interaction_policies.append(allow_interaction)
        if self.fail_all_deletes or (service, account) in self.delete_failures:
            raise storage._KeychainBackendError("delete", -25293)
        if (service, account) not in self.values:
            raise storage._KeychainBackendError("delete", -25300)
        del self.values[(service, account)]


class _ImapClient:
    password = ""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def login(self, _username, password) -> None:
        type(self).password = password

    def logout(self) -> None:
        pass


class _SmtpClient(_ImapClient):
    def ehlo(self) -> None:
        pass

    def has_extn(self, _name) -> bool:
        return False

    def quit(self) -> None:
        pass


class MacOSKeychainContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keychain = _FakeKeychain()
        self.platform = patch.object(storage, "_current_platform", return_value="darwin")
        self.backend = patch.object(storage, "_get_keychain_backend", return_value=self.keychain)
        self.platform.start()
        self.backend.start()

    def tearDown(self) -> None:
        self.backend.stop()
        self.platform.stop()

    def _save_mail_state(self, state, previous_mail=None, *, fail_write=False):
        import server

        with test_runtime_sandbox("gate_d_keychain_lifecycle") as runtime:
            original_path = server.STATE_FILE
            try:
                server.STATE_FILE = runtime.settings_path
                if fail_write:
                    with patch.object(server, "_write_protected_state", side_effect=OSError("synthetic write failure")):
                        with self.assertRaises(OSError):
                            server.save_state(state, previous_mail=previous_mail)
                else:
                    server.save_state(state, previous_mail=previous_mail)
                return state
            finally:
                server.STATE_FILE = original_path

    def _saved_mail(self, secret="synthetic-secret"):
        reference = storage.protect_mail_secret(secret, account=ACCOUNT)
        return {"accounts": [{**ACCOUNT, "password": reference}]}, reference

    def _assert_masked_identity_component_migrates(self, component: str, value: str) -> None:
        import server

        previous_mail, old_reference = self._saved_mail()
        edited = {**ACCOUNT, component: value, "password": "********"}
        merged = server.merge_masked_mail_passwords({"accounts": [edited]}, previous_mail)
        self.assertEqual(old_reference, merged["accounts"][0]["password"])
        state = {"mail": merged}
        self._save_mail_state(state, previous_mail)
        new_reference = state["mail"]["accounts"][0]["password"]
        self.assertNotEqual(old_reference, new_reference)
        self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(new_reference))
        self.assertNotIn((old_reference["service"], old_reference["account"]), self.keychain.values)
        self.assertNotIn("pending_secret_cleanup", state["mail"])

    def test_mac_settings_store_only_a_versioned_keychain_reference(self):
        state = {"mail": {"accounts": [{**ACCOUNT, "password": "synthetic-secret"}]}}
        protected, changed = storage.protect_mail_state_for_storage(state)
        password = protected["mail"]["accounts"][0]["password"]
        self.assertTrue(changed)
        self.assertEqual(storage.KEYCHAIN_SECRET_FORMAT, password["format"])
        self.assertEqual(storage.KEYCHAIN_SERVICE, password["service"])
        self.assertNotIn("synthetic-secret", repr(protected))
        self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(password))

    def test_update_and_missing_item_fail_closed_without_plaintext_fallback(self):
        first = storage.protect_mail_secret("first", account=ACCOUNT)
        updated = storage.protect_mail_secret("second", account=ACCOUNT)
        self.assertEqual(first, updated)
        self.assertEqual("second", storage.unprotect_mail_secret(updated))
        self.keychain.values.clear()
        with self.assertRaisesRegex(storage.MailSecretProtectionError, "not found"):
            storage.unprotect_mail_secret(updated)

    def test_noninteractive_policy_is_forwarded_without_a_security_bypass(self):
        reference = storage.protect_mail_secret(
            "synthetic-secret",
            account=ACCOUNT,
            _keychain_interaction_allowed=False,
        )
        self.assertEqual(
            "synthetic-secret",
            storage.unprotect_mail_secret(reference, _keychain_interaction_allowed=False),
        )
        storage.cleanup_removed_mail_secrets(
            {"accounts": [{"password": reference}]},
            {"accounts": []},
            _keychain_interaction_allowed=False,
        )
        self.assertEqual([False, False, False], self.keychain.interaction_policies)

    def test_keychain_osstatus_failures_are_safely_classified(self):
        expected = {
            -25300: "not found",
            -25308: "interaction is unavailable",
            -25293: "access was denied",
            -25291: "is unavailable",
            -25299: "duplicate item",
            -1: "could not be read",
        }
        for status, message in expected.items():
            with self.subTest(status=status):
                error = storage._keychain_error(storage._KeychainBackendError("read", status))
                self.assertIn(message, str(error))

    def test_backend_declares_only_modern_secitem_operations(self):
        source = inspect.getsource(storage._MacOSKeychainBackend)
        for name in ("SecItemAdd", "SecItemCopyMatching", "SecItemUpdate", "SecItemDelete"):
            self.assertIn(name, source)
        self.assertNotIn("SecKeychain", source)

    def test_native_keychain_subprocess_has_a_bounded_timeout(self):
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            _run_native_keychain_subprocess("gate-d-timeout@example.invalid")
        self.assertEqual(45, run.call_args.kwargs["timeout"])
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_masked_identity_change_retains_existing_reference_and_delete_cleans_it(self):
        reference = storage.protect_mail_secret("synthetic-secret", account=ACCOUNT)
        old = {"accounts": [{**ACCOUNT, "password": reference}]}
        changed = {
            **ACCOUNT,
            "email": "new-owner@example.com",
            "username": "new-owner@example.com",
            "password": "********",
        }
        import server
        merged = server.merge_masked_mail_passwords({"accounts": [changed]}, old)
        self.assertEqual(reference, merged["accounts"][0]["password"])
        self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(reference))
        storage.cleanup_removed_mail_secrets(old, {"accounts": []})
        with self.assertRaises(storage.MailSecretProtectionError):
            storage.unprotect_mail_secret(reference)
        storage.cleanup_removed_mail_secrets(old, {"accounts": []})

    def test_masked_email_edit_migrates_the_secret_after_settings_persistence(self):
        self._assert_masked_identity_component_migrates("email", "new-owner@example.com")

    def test_masked_username_edit_migrates_the_secret_after_settings_persistence(self):
        self._assert_masked_identity_component_migrates("username", "new-owner")

    def test_masked_imap_host_edit_migrates_the_secret_after_settings_persistence(self):
        self._assert_masked_identity_component_migrates("imap_host", "imap.new-example.test")

    def test_masked_imap_port_edit_migrates_the_secret_after_settings_persistence(self):
        self._assert_masked_identity_component_migrates("imap_port", "1993")

    def test_settings_write_failure_rolls_back_new_keychain_item_and_keeps_old_secret(self):
        previous_mail, old_reference = self._saved_mail()
        changed = {**ACCOUNT, "imap_host": "imap.new-example.test", "password": old_reference}
        state = {"mail": {"accounts": [changed]}}
        self._save_mail_state(state, previous_mail, fail_write=True)
        new_reference = storage._keychain_reference_for_account(changed)
        self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(old_reference))
        self.assertNotIn(new_reference, self.keychain.values)

    def test_same_identity_real_secret_replacement_rolls_back_when_settings_write_fails(self):
        previous_mail, old_reference = self._saved_mail("old-secret")
        state = {"mail": {"accounts": [{**ACCOUNT, "password": "replacement-secret"}]}}
        self._save_mail_state(state, previous_mail, fail_write=True)
        self.assertEqual("old-secret", storage.unprotect_mail_secret(old_reference))
        self.assertNotIn("replacement-secret", self.keychain.values.values())

    def test_failed_staged_item_rollback_is_recorded_and_later_retried(self):
        import server

        previous_mail, old_reference = self._saved_mail()
        state = {"mail": {"accounts": [{**ACCOUNT, "password": "replacement-secret"}]}}
        self.keychain.fail_all_deletes = True
        with test_runtime_sandbox("gate_d2_rollback_recovery") as runtime:
            original_path = server.STATE_FILE
            try:
                server.STATE_FILE = runtime.settings_path
                with patch.object(server, "_write_protected_state", side_effect=OSError("synthetic write failure")):
                    with self.assertRaises(OSError):
                        server.save_state(state, previous_mail=previous_mail)
                recovery_path = storage.mail_secret_recovery_path(runtime.settings_path)
                recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
                self.assertEqual(1, len(recovery["pending"]))
                self.assertNotIn("replacement-secret", repr(recovery))
                self.assertNotIn("synthetic-secret", repr(recovery))
                self.assertEqual("rollback_cleanup", recovery["pending"][0]["operation"])
                self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(old_reference))

                self.assertFalse(storage.retry_failed_keychain_compensation(recovery_path))
                self.keychain.fail_all_deletes = False
                self.assertTrue(storage.retry_failed_keychain_compensation(recovery_path))
                self.assertEqual([], json.loads(recovery_path.read_text(encoding="utf-8"))["pending"])
                self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(old_reference))
                self.assertNotIn("replacement-secret", self.keychain.values.values())
            finally:
                server.STATE_FILE = original_path

    def test_identity_change_rollback_failure_tracks_only_the_staged_reference(self):
        import server

        previous_mail, old_reference = self._saved_mail()
        state = {"mail": {"accounts": [{**ACCOUNT, "imap_host": "imap.new-example.test", "password": old_reference}]}}
        self.keychain.fail_all_deletes = True
        with test_runtime_sandbox("gate_d2_identity_recovery") as runtime:
            original_path = server.STATE_FILE
            try:
                server.STATE_FILE = runtime.settings_path
                with patch.object(server, "_write_protected_state", side_effect=OSError("synthetic write failure")):
                    with self.assertRaises(OSError):
                        server.save_state(state, previous_mail=previous_mail)
                recovery = json.loads(storage.mail_secret_recovery_path(runtime.settings_path).read_text(encoding="utf-8"))
                self.assertEqual(1, len(recovery["pending"]))
                self.assertNotEqual(old_reference["account"], recovery["pending"][0]["account"])
                self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(old_reference))
            finally:
                server.STATE_FILE = original_path
                self.keychain.fail_all_deletes = False

    def test_recovery_sidecar_write_failure_surfaces_a_safe_error_without_changing_settings(self):
        import server

        previous_mail, old_reference = self._saved_mail()
        state = {"mail": {"accounts": [{**ACCOUNT, "password": "replacement-secret"}]}}
        self.keychain.fail_all_deletes = True
        with test_runtime_sandbox("gate_d2_recovery_persist_failure") as runtime:
            original_path = server.STATE_FILE
            try:
                server.STATE_FILE = runtime.settings_path
                atomic_write_json(runtime.settings_path, {"mail": previous_mail})
                with patch.object(server, "_write_protected_state", side_effect=OSError("synthetic write failure")), patch.object(
                    storage, "atomic_write_json", side_effect=OSError("synthetic recovery write failure")
                ):
                    with self.assertRaises(storage.MailSecretProtectionError):
                        server.save_state(state, previous_mail=previous_mail)
                self.assertEqual({"mail": previous_mail}, json.loads(runtime.settings_path.read_text(encoding="utf-8")))
                self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(old_reference))
            finally:
                server.STATE_FILE = original_path
                self.keychain.fail_all_deletes = False

    def test_settings_route_restores_in_memory_state_after_a_write_failure(self):
        import copy
        import server
        from http_handlers import settings_handler

        previous_mail, old_reference = self._saved_mail()
        state = {"mail": copy.deepcopy(previous_mail)}
        responses = []

        class Handler:
            def _api_error(self, code, message, status):
                responses.append((code, message, status))

        context = {
            "state": {
                "get": lambda: state,
                "save": lambda _previous_mail: (_ for _ in ()).throw(OSError("synthetic write failure")),
            },
            "services": {
                "normalize_mail_state": server.normalize_mail_state,
                "merge_masked_mail_passwords": server.merge_masked_mail_passwords,
            },
            "modules": {},
            "logging": {"error": lambda *_args: None},
        }
        request = {
            "method": "POST",
            "path": "/api/settings/mail",
            "get_payload": lambda: {"accounts": [{**ACCOUNT, "imap_host": "imap.new-example.test", "password": "********"}]},
        }
        self.assertTrue(settings_handler.handle(Handler(), request, context))
        self.assertEqual(previous_mail, state["mail"])
        self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(old_reference))
        self.assertEqual([("MAIL_SETTINGS_SAVE_FAILED", "邮箱设置未保存，请稍后重试。", 500)], responses)

    def test_failed_old_item_cleanup_is_durable_and_retried_on_next_save(self):
        previous_mail, old_reference = self._saved_mail()
        changed = {**ACCOUNT, "imap_host": "imap.new-example.test", "password": old_reference}
        self.keychain.delete_failures.add((old_reference["service"], old_reference["account"]))
        state = {"mail": {"accounts": [changed]}}
        self._save_mail_state(state, previous_mail)
        new_reference = state["mail"]["accounts"][0]["password"]
        self.assertEqual("synthetic-secret", storage.unprotect_mail_secret(new_reference))
        self.assertEqual(
            [{"format": storage.KEYCHAIN_SECRET_FORMAT, "service": old_reference["service"], "account": old_reference["account"]}],
            state["mail"]["pending_secret_cleanup"],
        )
        self.assertNotIn("synthetic-secret", repr(state["mail"]["pending_secret_cleanup"]))

        self.keychain.delete_failures.clear()
        self._save_mail_state(state)
        self.assertNotIn("pending_secret_cleanup", state["mail"])
        self.assertNotIn((old_reference["service"], old_reference["account"]), self.keychain.values)

    def test_account_delete_failure_keeps_durable_cleanup_reference_until_a_later_save(self):
        previous_mail, old_reference = self._saved_mail()
        self.keychain.delete_failures.add((old_reference["service"], old_reference["account"]))
        state = {"mail": {"accounts": []}}
        self._save_mail_state(state, previous_mail)
        self.assertIn("pending_secret_cleanup", state["mail"])
        self.keychain.delete_failures.clear()
        self._save_mail_state(state)
        self.assertNotIn("pending_secret_cleanup", state["mail"])
        self.assertNotIn((old_reference["service"], old_reference["account"]), self.keychain.values)

    def test_mask_placeholder_is_never_stored_as_a_keychain_secret_or_exposed_to_client(self):
        import server

        previous_mail, old_reference = self._saved_mail()
        merged = server.merge_masked_mail_passwords(
            {"accounts": [{**ACCOUNT, "imap_port": "1993", "password": "********"}]}, previous_mail
        )
        state = {"mail": merged}
        self._save_mail_state(state, previous_mail)
        self.assertNotIn("********", self.keychain.values.values())
        state["mail"]["pending_secret_cleanup"] = [
            {"format": storage.KEYCHAIN_SECRET_FORMAT, "service": old_reference["service"], "account": old_reference["account"]}
        ]
        self.assertNotIn("pending_secret_cleanup", server.state_for_client(state)["mail"])

    def test_legacy_plaintext_migration_is_idempotent_and_failure_keeps_original(self):
        legacy = {"mail": {"accounts": [{**ACCOUNT, "password": "legacy-synthetic"}]}}
        protected, changed = storage.protect_mail_state_for_storage(legacy)
        again, changed_again = storage.protect_mail_state_for_storage(protected)
        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertEqual(protected, again)
        unavailable = _FakeKeychain()
        with patch.object(storage, "_get_keychain_backend", return_value=unavailable), patch.object(
            unavailable, "store", side_effect=storage._KeychainBackendError("store", -25293)
        ):
            with self.assertRaises(storage.MailSecretProtectionError):
                storage.protect_mail_state_for_storage(legacy)
        self.assertEqual("legacy-synthetic", legacy["mail"]["accounts"][0]["password"])

    def test_server_migration_removes_plaintext_from_settings_and_backup(self):
        import json
        import server

        with test_runtime_sandbox("gate_d_keychain_migration") as runtime:
            original_path = server.STATE_FILE
            legacy = {"mail": {"accounts": [{**ACCOUNT, "password": "legacy-synthetic"}]}}
            try:
                server.STATE_FILE = runtime.settings_path
                atomic_write_json(runtime.settings_path, legacy)
                state = server.load_state()
                for path in (runtime.settings_path, json_backup_path(runtime.settings_path)):
                    self.assertNotIn("legacy-synthetic", path.read_text(encoding="utf-8"))
                self.assertEqual(
                    storage.KEYCHAIN_SECRET_FORMAT,
                    state["mail"]["accounts"][0]["password"]["format"],
                )
            finally:
                server.STATE_FILE = original_path

    def test_replacing_an_edited_account_removes_the_superseded_keychain_item(self):
        old_reference = storage.protect_mail_secret("old-secret", account=ACCOUNT)
        old = {"accounts": [{**ACCOUNT, "password": old_reference}]}
        changed_account = {**ACCOUNT, "email": "new-owner@example.com", "password": "new-secret"}
        current, changed = storage.protect_mail_state_for_storage({"mail": {"accounts": [changed_account]}})
        self.assertTrue(changed)
        storage.cleanup_removed_mail_secrets(old, current["mail"])
        with self.assertRaises(storage.MailSecretProtectionError):
            storage.unprotect_mail_secret(old_reference)
        self.assertEqual("new-secret", storage.unprotect_mail_secret(current["mail"]["accounts"][0]["password"]))

    def test_foreign_protected_values_are_never_reinterpreted(self):
        with self.assertRaises(storage.MailSecretProtectionError):
            storage.unprotect_mail_secret({"format": "dpapi-v1", "data": "AA=="})

    def test_imap_and_smtp_receive_keychain_secret_only_at_login_boundary(self):
        import server

        password = storage.protect_mail_secret("synthetic-secret", account=ACCOUNT)
        account = {
            **ACCOUNT,
            "password": password,
            "smtp_host": "smtp.example.test",
            "smtp_port": "465",
        }
        with patch.object(server.imaplib, "IMAP4_SSL", _ImapClient), patch.object(
            server.smtplib, "SMTP_SSL", _SmtpClient
        ):
            server.test_imap_login(account)
            server.test_smtp_login(account)
        self.assertEqual("synthetic-secret", _ImapClient.password)
        self.assertEqual("synthetic-secret", _SmtpClient.password)


@unittest.skipUnless(sys.platform == "darwin", "requires native macOS Keychain")
class NativeMacOSKeychainTests(unittest.TestCase):
    def test_native_keychain_round_trip_update_and_delete(self):
        account_email = f"gate-d-{uuid4().hex}@example.invalid"
        try:
            result = _run_native_keychain_subprocess(account_email)
        except subprocess.TimeoutExpired as exc:
            _best_effort_native_cleanup(account_email)
            self.fail(f"native non-interactive Keychain child timed out after 45s: {type(exc).__name__}")
        self.assertEqual(0, result.returncode, result.stderr.strip())


def _native_account(account_email: str) -> dict[str, str]:
    return {**ACCOUNT, "email": account_email, "username": account_email}


def _run_native_keychain_subprocess(account_email: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--native-keychain-child", account_email],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def _run_native_keychain_child(account_email: str) -> None:
    account = _native_account(account_email)
    reference = storage.protect_mail_secret(
        "gate-d-synthetic",
        account=account,
        _keychain_interaction_allowed=False,
    )
    try:
        if storage.unprotect_mail_secret(reference, _keychain_interaction_allowed=False) != "gate-d-synthetic":
            raise storage.MailSecretProtectionError("Native Keychain read did not return the expected value.")
        storage.protect_mail_secret(
            "gate-d-updated",
            account=account,
            _keychain_interaction_allowed=False,
        )
        if storage.unprotect_mail_secret(reference, _keychain_interaction_allowed=False) != "gate-d-updated":
            raise storage.MailSecretProtectionError("Native Keychain update did not return the expected value.")
    finally:
        storage.cleanup_removed_mail_secrets(
            {"accounts": [{"password": reference}]},
            {"accounts": []},
            _keychain_interaction_allowed=False,
        )


def _best_effort_native_cleanup(account_email: str) -> None:
    """Contain a blocked child and make one separately bounded cleanup attempt."""
    try:
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--native-keychain-cleanup", account_email],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] in {
    "--native-keychain-child",
    "--native-keychain-cleanup",
}:
    try:
        account = _native_account(sys.argv[2])
        if sys.argv[1] == "--native-keychain-child":
            _run_native_keychain_child(sys.argv[2])
        else:
            reference = {
                "format": storage.KEYCHAIN_SECRET_FORMAT,
                "service": storage.KEYCHAIN_SERVICE,
                "account": storage._keychain_account_identity(account),
            }
            storage.cleanup_removed_mail_secrets(
                {"accounts": [{"password": reference}]},
                {"accounts": []},
                _keychain_interaction_allowed=False,
            )
    except Exception as exc:
        print(f"Native Keychain test failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
