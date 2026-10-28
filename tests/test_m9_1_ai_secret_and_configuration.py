from __future__ import annotations

import json
import sys
import tempfile
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
)
from services.ai_secret_storage import (  # noqa: E402
    AI_KEYCHAIN_ACCOUNT,
    AI_KEYCHAIN_SERVICE,
    AISecretStorage,
    AISecretStorageError,
)


SECRET_1 = "fake-ai-key-one"
SECRET_2 = "fake-ai-key-two"


class KeychainError(RuntimeError):
    def __init__(self, status):
        self.status = status


class Keychain:
    def __init__(self):
        self.values = {}
        self.fail_store = False
        self.fail_delete = False

    def store(self, service, account, secret, *, allow_interaction):
        self.assert_noninteractive(allow_interaction)
        if self.fail_store:
            raise KeychainError(-25291)
        self.values[(service, account)] = secret

    def read(self, service, account, *, allow_interaction):
        self.assert_noninteractive(allow_interaction)
        return self.values[(service, account)]

    def delete(self, service, account, *, allow_interaction):
        self.assert_noninteractive(allow_interaction)
        if self.fail_delete:
            raise KeychainError(-25291)
        self.values.pop((service, account), None)

    @staticmethod
    def assert_noninteractive(value):
        if value is not False:
            raise AssertionError("AI Keychain operations must be non-interactive")


class Provider:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def health_check(self, *, remote=False):
        return {"ok": True, "status": "available", "remote": remote}


class AISecretAndConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def windows_store(self):
        return AISecretStorage(
            self.root / "ai.secret.json",
            platform="win32",
            protect_bytes=lambda value: value[::-1].hex(),
            unprotect_bytes=lambda value: bytes.fromhex(value)[::-1],
        )

    def test_windows_dpapi_contract_saves_reads_replaces_and_deletes_without_plaintext(self):
        store = self.windows_store()
        store.replace(SECRET_1)
        self.assertTrue(store.is_configured())
        self.assertEqual(SECRET_1, store.read())
        self.assertNotIn(SECRET_1, store.path.read_text(encoding="utf-8"))
        store.replace(SECRET_2)
        self.assertEqual(SECRET_2, store.read())
        store.delete()
        self.assertFalse(store.is_configured())

    def test_macos_keychain_uses_independent_namespace_and_noninteractive_operations(self):
        keychain = Keychain()
        store = AISecretStorage(self.root / "ai.secret.json", platform="darwin", keychain_backend=keychain)
        store.replace(SECRET_1)
        self.assertEqual(SECRET_1, store.read())
        self.assertEqual({(AI_KEYCHAIN_SERVICE, AI_KEYCHAIN_ACCOUNT): SECRET_1}, keychain.values)
        self.assertNotIn(SECRET_1, store.path.read_text(encoding="utf-8"))
        self.assertNotIn("mail", AI_KEYCHAIN_SERVICE)
        store.delete()
        self.assertFalse(store.is_configured())

    def test_unsupported_platform_fails_closed(self):
        store = AISecretStorage(self.root / "ai.secret.json", platform="linux")
        with self.assertRaises(AISecretStorageError):
            store.replace(SECRET_1)
        self.assertFalse(store.path.exists())

    def test_macos_reference_write_failure_rolls_keychain_back(self):
        keychain = Keychain()
        store = AISecretStorage(self.root / "ai.secret.json", platform="darwin", keychain_backend=keychain)
        store.replace(SECRET_1)
        with mock.patch("services.ai_secret_storage.atomic_write_json", side_effect=OSError("synthetic")):
            with self.assertRaises(AISecretStorageError):
                store.replace(SECRET_2)
        self.assertEqual(SECRET_1, keychain.values[(AI_KEYCHAIN_SERVICE, AI_KEYCHAIN_ACCOUNT)])
        self.assertEqual(SECRET_1, store.read())

    def test_macos_reference_delete_failure_rolls_keychain_back(self):
        keychain = Keychain()
        store = AISecretStorage(self.root / "ai.secret.json", platform="darwin", keychain_backend=keychain)
        store.replace(SECRET_1)
        with mock.patch.object(Path, "unlink", side_effect=OSError("synthetic")):
            with self.assertRaises(AISecretStorageError):
                store.delete()
        self.assertEqual(SECRET_1, keychain.values[(AI_KEYCHAIN_SERVICE, AI_KEYCHAIN_ACCOUNT)])

    def test_configuration_is_redacted_and_factory_reads_one_secret_boundary(self):
        store = self.windows_store()
        config_path = self.root / "ai_provider.json"
        service = AIProviderConfigurationService(
            config_path,
            store,
            provider_builders={"openai_compatible": Provider},
        )
        client = service.update({
            "enabled": True,
            "model": "model-1",
            "timeout": 12,
            "max_retries": 1,
            "api_key": SECRET_1,
        })
        self.assertTrue(client["key_configured"])
        self.assertNotIn("api_key", client)
        self.assertNotIn(SECRET_1, config_path.read_text(encoding="utf-8"))
        provider = service.create_provider()
        self.assertEqual(SECRET_1, provider.kwargs["api_key"])
        self.assertNotIn("tools", provider.kwargs)
        self.assertNotIn("repository", provider.kwargs)

    def test_disabled_and_incomplete_configuration_returns_fail_closed_provider(self):
        service = AIProviderConfigurationService(
            self.root / "ai_provider.json",
            self.windows_store(),
            provider_builders={"openai_compatible": Provider},
        )
        self.assertIsInstance(service.create_provider(), UnavailableAIProvider)
        service.update({"enabled": True, "model": ""})
        self.assertIsInstance(service.create_provider(), UnavailableAIProvider)
        self.assertEqual("configuration_incomplete", service.health_check()["status"])

    def test_config_save_failure_rolls_secret_back(self):
        store = self.windows_store()
        service = AIProviderConfigurationService(self.root / "ai_provider.json", store)
        service.update({"api_key": SECRET_1})
        real_atomic_write = __import__("services.ai_provider_configuration", fromlist=["atomic_write_json"]).atomic_write_json

        def fail_config_only(path, data):
            if Path(path) == service.path:
                raise OSError("synthetic")
            return real_atomic_write(path, data)

        with mock.patch("services.ai_provider_configuration.atomic_write_json", side_effect=fail_config_only):
            with self.assertRaises(AIProviderConfigurationError):
                service.update({"api_key": SECRET_2, "model": "changed"})
        self.assertEqual(SECRET_1, store.read())
        self.assertEqual("", service.load().model)

    def test_unsafe_url_and_retry_bounds_are_rejected_without_network(self):
        service = AIProviderConfigurationService(self.root / "ai_provider.json", self.windows_store())
        for payload in (
            {"base_url": "http://api.openai.com/v1"},
            {"base_url": "https://localhost/v1"},
            {"timeout": 0},
            {"max_retries": 4},
        ):
            with self.subTest(payload=payload), self.assertRaises(AIProviderConfigurationError):
                service.update(payload)

    def test_local_health_check_never_builds_remote_provider(self):
        builds = []

        def builder(**kwargs):
            builds.append(kwargs)
            return Provider(**kwargs)

        store = self.windows_store()
        service = AIProviderConfigurationService(
            self.root / "ai_provider.json",
            store,
            provider_builders={"openai_compatible": builder},
        )
        service.update({"enabled": True, "model": "model-1", "api_key": SECRET_1})
        self.assertTrue(service.health_check()["ok"])
        self.assertEqual([], builds)
        self.assertTrue(service.health_check(remote=True)["ok"])
        self.assertEqual(1, len(builds))


if __name__ == "__main__":
    unittest.main()
