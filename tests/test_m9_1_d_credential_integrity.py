from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from services.ai_provider import UnavailableAIProvider  # noqa: E402
from services.ai_provider_configuration import (  # noqa: E402
    AIProviderConfigurationError,
    AIProviderConfigurationService,
    endpoint_identity,
)
from services.ai_secret_storage import AISecretStorage, AISecretStorageError  # noqa: E402
from services.openai_compatible_ai_provider import validate_provider_base_url  # noqa: E402


ENDPOINT_A = "https://AI.Example.com:443/openai/v1/"
CANONICAL_A = "https://ai.example.com/openai/v1"
ENDPOINT_B = "https://api.other-example.com/v1"
KEY_A = "test-key-a"
KEY_B = "test-key-b"


class Provider:
    builds: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.builds.append(kwargs)

    def health_check(self, *, remote=False):
        return {"ok": True, "remote": remote}


class Keychain:
    def __init__(self):
        self.values = {}

    def store(self, service, account, secret, *, allow_interaction):
        if allow_interaction is not False:
            raise AssertionError("Keychain access must be non-interactive")
        self.values[(service, account)] = secret

    def read(self, service, account, *, allow_interaction):
        if allow_interaction is not False:
            raise AssertionError("Keychain access must be non-interactive")
        return self.values[(service, account)]

    def delete(self, service, account, *, allow_interaction):
        if allow_interaction is not False:
            raise AssertionError("Keychain access must be non-interactive")
        self.values.pop((service, account), None)


class CredentialIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        Provider.builds = []

    def tearDown(self):
        self.temp.cleanup()

    def storage(self, provider="custom", *, platform="win32", keychain=None):
        return AISecretStorage(
            self.root / f"{provider}.secret.json",
            platform=platform,
            profile_id=provider,
            protect_bytes=lambda value: value[::-1].hex(),
            unprotect_bytes=lambda value: bytes.fromhex(value)[::-1],
            keychain_backend=keychain,
        )

    def service(self):
        return AIProviderConfigurationService(
            self.root / "ai_provider.json",
            self.storage("openai"),
            secret_storage_factory=self.storage,
            provider_builders={"openai_compatible": Provider},
        )

    @staticmethod
    def custom_payload(endpoint, key=None, **changes):
        payload = {
            "provider": "custom",
            "base_url": endpoint,
            "model": "model-1",
            "enabled": True,
            **changes,
        }
        if key is not None:
            payload["api_key"] = key
        return payload

    def test_endpoint_change_without_new_key_is_rejected_and_preserves_old_pair(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        with self.assertRaises(AIProviderConfigurationError) as caught:
            service.update(self.custom_payload(ENDPOINT_B, model="model-2"))
        self.assertEqual("AI_PROVIDER_ENDPOINT_KEY_REBIND_REQUIRED", caught.exception.code)
        self.assertEqual(CANONICAL_A, service.load().base_url)
        provider = service.create_provider()
        self.assertEqual((CANONICAL_A, KEY_A), (provider.kwargs["base_url"], provider.kwargs["api_key"]))

    def test_endpoint_change_with_new_key_commits_one_bound_pair(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        service.update(self.custom_payload(ENDPOINT_B, KEY_B, model="model-2"))
        provider = service.create_provider()
        self.assertEqual((ENDPOINT_B, KEY_B), (provider.kwargs["base_url"], provider.kwargs["api_key"]))
        self.assertEqual(endpoint_identity(ENDPOINT_B), self.storage().binding_identity())

    def test_same_endpoint_model_and_timeout_change_retains_key(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        service.update(self.custom_payload(CANONICAL_A, model="model-2", timeout=18))
        provider = service.create_provider()
        self.assertEqual(KEY_A, provider.kwargs["api_key"])
        self.assertEqual("model-2", provider.kwargs["model"])
        self.assertEqual(18, provider.kwargs["timeout"])

    def test_endpoint_identity_normalization_preserves_security_boundaries(self):
        canonical = validate_provider_base_url(ENDPOINT_A, custom_endpoint=True)
        self.assertEqual(CANONICAL_A, canonical)
        self.assertEqual(
            endpoint_identity(canonical),
            endpoint_identity(validate_provider_base_url(CANONICAL_A, custom_endpoint=True)),
        )
        self.assertNotEqual(
            endpoint_identity(canonical),
            endpoint_identity(validate_provider_base_url("https://ai.example.com/other/v1", custom_endpoint=True)),
        )
        self.assertNotEqual(
            endpoint_identity(canonical),
            endpoint_identity(validate_provider_base_url("https://other.example.com/openai/v1", custom_endpoint=True)),
        )

    def test_provider_keys_remain_isolated(self):
        service = self.service()
        service.update({"provider": "openai", "model": "gpt", "api_key": KEY_A, "enabled": True})
        service.update({"provider": "deepseek", "model": "deep", "api_key": KEY_B, "enabled": True})
        self.assertEqual(KEY_A, self.storage("openai").read())
        self.assertEqual(KEY_B, self.storage("deepseek").read())

    def test_concurrent_endpoint_saves_cannot_cross_pair(self):
        service = self.service()
        entered_first_replace = threading.Event()
        release_first_replace = threading.Event()
        second_started = threading.Event()
        real_replace = AISecretStorage.replace
        calls = 0
        calls_lock = threading.Lock()

        def controlled_replace(storage, secret, **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
                call = calls
            if call == 1:
                entered_first_replace.set()
                self.assertTrue(release_first_replace.wait(5))
            return real_replace(storage, secret, **kwargs)

        errors = []
        with mock.patch.object(AISecretStorage, "replace", autospec=True, side_effect=controlled_replace):
            first = threading.Thread(
                target=lambda: self._capture(errors, service.update, self.custom_payload(ENDPOINT_A, KEY_A)),
            )
            second = threading.Thread(
                target=lambda: (second_started.set(), self._capture(errors, service.update, self.custom_payload(ENDPOINT_B, KEY_B))),
            )
            first.start()
            self.assertTrue(entered_first_replace.wait(5))
            second.start()
            self.assertTrue(second_started.wait(5))
            release_first_replace.set()
            first.join(5)
            second.join(5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual([], errors)
        provider = service.create_provider()
        self.assertIn(
            (provider.kwargs["base_url"], provider.kwargs["api_key"]),
            {(CANONICAL_A, KEY_A), (ENDPOINT_B, KEY_B)},
        )
        self.assertEqual(endpoint_identity(provider.kwargs["base_url"]), self.storage().binding_identity())

    def test_concurrent_update_and_delete_end_in_consistent_unconfigured_state(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        entered_replace = threading.Event()
        release_replace = threading.Event()
        delete_started = threading.Event()
        real_replace = AISecretStorage.replace

        def controlled_replace(storage, secret, **kwargs):
            if secret == KEY_B:
                entered_replace.set()
                self.assertTrue(release_replace.wait(5))
            return real_replace(storage, secret, **kwargs)

        errors = []
        with mock.patch.object(AISecretStorage, "replace", autospec=True, side_effect=controlled_replace):
            update = threading.Thread(
                target=lambda: self._capture(errors, service.update, self.custom_payload(ENDPOINT_B, KEY_B)),
            )
            delete = threading.Thread(
                target=lambda: (delete_started.set(), self._capture(errors, service.update, {"provider": "custom", "clear_api_key": True})),
            )
            update.start()
            self.assertTrue(entered_replace.wait(5))
            delete.start()
            self.assertTrue(delete_started.wait(5))
            release_replace.set()
            update.join(5)
            delete.join(5)
        self.assertEqual([], errors)
        self.assertFalse(self.storage().is_configured())
        self.assertIsInstance(service.create_provider(), UnavailableAIProvider)

    def test_config_write_failure_restores_secret_and_binding(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        real_atomic = __import__("services.ai_provider_configuration", fromlist=["atomic_write_json"]).atomic_write_json

        def fail_config(path, data):
            if Path(path) == service.path:
                raise OSError("synthetic config failure")
            return real_atomic(path, data)

        with mock.patch("services.ai_provider_configuration.atomic_write_json", side_effect=fail_config):
            with self.assertRaises(AIProviderConfigurationError):
                service.update(self.custom_payload(ENDPOINT_B, KEY_B))
        provider = service.create_provider()
        self.assertEqual((CANONICAL_A, KEY_A), (provider.kwargs["base_url"], provider.kwargs["api_key"]))
        self.assertEqual(endpoint_identity(CANONICAL_A), self.storage().binding_identity())

    def test_config_or_secret_read_failure_prevents_provider_creation(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        with mock.patch.object(AISecretStorage, "read", side_effect=AISecretStorageError("safe failure")):
            self.assertIsInstance(service.create_provider(), UnavailableAIProvider)
        with mock.patch.object(service, "_load_document", side_effect=AIProviderConfigurationError("safe failure")):
            self.assertIsInstance(service.create_provider(), UnavailableAIProvider)

    def test_stale_secret_binding_never_builds_provider_for_new_endpoint(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        document = json.loads(service.path.read_text(encoding="utf-8"))
        profile = document["profiles"]["custom"]
        profile["base_url"] = ENDPOINT_B
        profile["endpoint_identity"] = endpoint_identity(ENDPOINT_B)
        service.path.write_text(json.dumps(document), encoding="utf-8")
        self.assertIsInstance(service.create_provider(), UnavailableAIProvider)
        self.assertEqual([], Provider.builds)

    def test_dpapi_and_keychain_envelopes_bind_without_exposing_secret(self):
        identity = endpoint_identity(CANONICAL_A)
        windows = self.storage()
        windows.replace(KEY_A, endpoint_identity=identity)
        self.assertEqual(identity, windows.binding_identity())
        self.assertNotIn(KEY_A, windows.path.read_text(encoding="utf-8"))

        keychain = Keychain()
        mac = self.storage("custom-mac", platform="darwin", keychain=keychain)
        mac.replace(KEY_B, endpoint_identity=identity)
        self.assertEqual(identity, mac.binding_identity())
        self.assertEqual(KEY_B, mac.read(expected_endpoint_identity=identity, allow_legacy_unbound=False))
        self.assertNotIn(KEY_B, mac.path.read_text(encoding="utf-8"))

    def test_provider_creation_rechecks_binding_after_configuration_read(self):
        service = self.service()
        service.update(self.custom_payload(ENDPOINT_A, KEY_A))
        secret_path = self.storage().path
        envelope = json.loads(secret_path.read_text(encoding="utf-8"))
        envelope["endpoint_identity"] = endpoint_identity(ENDPOINT_B)
        secret_path.write_text(json.dumps(envelope), encoding="utf-8")
        self.assertIsInstance(service.create_provider(), UnavailableAIProvider)
        self.assertEqual([], Provider.builds)

    @staticmethod
    def _capture(errors, operation, payload):
        try:
            operation(payload)
        except Exception as exc:  # pragma: no cover - assertion reports captured exception
            errors.append(exc)


if __name__ == "__main__":
    unittest.main()
